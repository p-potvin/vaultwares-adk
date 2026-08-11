"""The async worker: a bounded queue plus one daemon thread that ships batches.

Why a thread and not an asyncio task: the recorder is imported by sync scripts
(python-zipper), asyncio services (vault-inference, vaultwares-api), and code
running inside someone else's loop (ComfyUI nodes). A daemon thread has no
opinion about which loop exists, cannot be starved by a blocked loop, and
survives a loop being closed and recreated. ``record()`` is a lock-free queue
put from the caller's perspective and never blocks on the network.
"""

from __future__ import annotations

import atexit
import queue
import sys
import threading
import time
from typing import Dict, List, Optional

from .config import TelemetryConfig, get_config
from .record import RunRecord, build_batch
from .rollup import RollupAggregator, build_rollup_batch
from .spool import deliver, spool_backlog, spool_batch


class RunWorker:
    """Owns the queue, the flush thread, and the batch counter."""

    def __init__(self, source: str = "vw-ai-runs") -> None:
        self._source = source
        self._queue: "queue.Queue[Optional[RunRecord]]" = queue.Queue(
            maxsize=get_config().queue_max
        )
        self._thread: Optional[threading.Thread] = None
        self._start_lock = threading.Lock()
        self._stopping = threading.Event()
        self._flush_now = threading.Event()
        self._batch_index = 0
        self._stats = {"queued": 0, "drained": 0, "posted": 0, "spooled": 0,
                       "dropped": 0, "overflow": 0}
        self._stats_lock = threading.Lock()
        # Rollups are maintained continuously; only complete hours are sent.
        self.rollups = RollupAggregator()
        self._pending: List[RunRecord] = []
        self._last_send = time.monotonic()

    # ── public surface ────────────────────────────────────────────────────

    def record(self, run: RunRecord) -> None:
        """Hand a finished run to the worker. Never blocks, never raises."""
        config = get_config()
        if not config.enabled:
            return
        try:
            self._ensure_started()
            self._queue.put_nowait(run)
            self._bump("queued")
            # Trip an early flush rather than waiting out the interval once a
            # full batch is available.
            if self._queue.qsize() >= config.batch_max:
                self._flush_now.set()
        except queue.Full:
            # Shedding the newest run is the right call: the backlog already on
            # the queue is older and closer to being delivered.
            self._bump("overflow")
        except Exception:
            # A telemetry recorder must never take down an inference call.
            pass

    def flush(self, timeout: float = 5.0) -> None:
        """Force an immediate drain + send, bypassing the hourly cadence.

        Waits (bounded) for the queue to empty. Note this sends only *closed*
        hours; the open hour keeps accumulating. Use shutdown() to force the
        partial hour out.
        """
        if self._thread is None:
            # Nothing was ever recorded, or the worker never started — do it
            # inline so a short-lived script still ships.
            config = get_config()
            self._drain_once(config)
            self._send_once(config)
            return
        self._flush_now.set()
        waiter = threading.Event()
        # Poll rather than join: the worker thread is long-lived by design.
        waited = 0.0
        step = 0.05
        while (not self._queue.empty() or self._pending) and waited < timeout:
            waiter.wait(step)
            waited += step

    def shutdown(self, timeout: float = 5.0) -> None:
        """Flush everything, including the open hour, and stop the thread."""
        if self._thread is None:
            config = get_config()
            self._drain_once(config)
            self._send_once(config, final=True)
            return
        self._stopping.set()
        self._flush_now.set()
        try:
            self._queue.put_nowait(None)  # wake a blocked get()
        except queue.Full:
            pass
        self._thread.join(timeout=timeout)
        self._thread = None

    def stats(self) -> Dict[str, int]:
        with self._stats_lock:
            out = dict(self._stats)
        out["queue_depth"] = self._queue.qsize()
        out["pending_runs"] = len(self._pending)
        out.update(self.rollups.stats())
        out.update({f"spool_{k}": v for k, v in spool_backlog(get_config()).items()})
        return out

    # ── internals ─────────────────────────────────────────────────────────

    def _ensure_started(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        with self._start_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stopping.clear()
            thread = threading.Thread(
                target=self._run, name="vw-telemetry-runs", daemon=True
            )
            thread.start()
            self._thread = thread
            atexit.register(self._atexit)

    def _atexit(self) -> None:
        try:
            self.shutdown(timeout=3.0)
        except Exception:
            pass

    def _run(self) -> None:
        while not self._stopping.is_set():
            config = get_config()
            # Wake on the short drain interval, or early when record() signals
            # a full batch. Whether to *send* is decided separately.
            self._flush_now.wait(timeout=config.drain_interval_s)
            forced = self._flush_now.is_set()
            self._flush_now.clear()
            self._guarded("drain", self._drain_once, config)
            if forced or self._send_due(config):
                self._guarded("send", self._send_once, config)
        # Shutdown: drain what is left, then send everything including the
        # still-open hour. A partial hour delivered beats a lost one — ingest
        # overwrites the row when the rest of it arrives.
        config = get_config()
        self._guarded("drain", self._drain_once, config)
        self._guarded("send", self._send_once, config, True)

    def _send_due(self, config: TelemetryConfig) -> bool:
        return (time.monotonic() - self._last_send) >= config.send_interval_s

    def _guarded(self, label: str, fn, *args) -> None:
        """Run a worker phase, turning any fault into a counter.

        Swallowing silently here once made a worker bug invisible: runs left the
        queue and never arrived anywhere. The counter (and, under
        VW_RUNS_DEBUG, a traceback) is what makes that state observable.
        """
        try:
            fn(*args)
        except Exception as exc:
            self._bump("worker_errors")
            if get_config().debug:
                import traceback

                print(
                    f"[vw-telemetry] worker {label} failed: {exc!r}\n"
                    + traceback.format_exc(),
                    file=sys.stderr,
                )

    def _drain_once(self, config: TelemetryConfig) -> None:
        """Move runs off the queue into the rollup and the pending buffer.

        This is the cadence that protects against process death: anything still
        on the in-memory queue is lost if we crash, so it runs often and does no
        network I/O.
        """
        while True:
            records = self._take(config.batch_max)
            if not records:
                break
            finalized = [r.finalize() for r in records]
            self.rollups.add_many(finalized)
            self._bump("drained", len(finalized))
            if config.send_raw_runs:
                self._pending.extend(finalized)
            if len(records) < config.batch_max:
                break

        # Bound the pending buffer. Holding an hour of raw runs in memory is
        # fine on a quiet host and ruinous on a busy one, so past a threshold
        # they go straight to disk; the drain script picks them up from there.
        cap = config.batch_max * 5
        if len(self._pending) >= cap:
            overflow, self._pending = self._pending[:-cap], self._pending[-cap:]
            if overflow:
                self._spool_runs(overflow, config)

    def _send_once(self, config: TelemetryConfig, final: bool = False) -> None:
        """Talk to the API: closed rollups first, then the raw rows."""
        self._last_send = time.monotonic()

        buckets = self.rollups.take_all() if final else self.rollups.take_closed()
        if buckets:
            self._batch_index += 1
            batch = build_rollup_batch(
                buckets, host=config.host, source=self._source,
                batch_index=self._batch_index,
            )
            outcome = deliver(batch, config, kind="rollups")
            self._bump(f"rollups_{outcome}", len(buckets))

        while self._pending:
            chunk, self._pending = self._pending[:config.batch_max], self._pending[config.batch_max:]
            self._batch_index += 1
            batch = build_batch(
                chunk, host=config.host, source=self._source,
                batch_index=self._batch_index,
                public_surface=config.public_surface,
            )
            outcome = deliver(batch, config)
            self._bump(outcome, len(chunk))

    def _spool_runs(self, records: List[RunRecord], config: TelemetryConfig) -> None:
        """Write raw runs straight to disk without attempting the network."""
        for i in range(0, len(records), config.batch_max):
            chunk = records[i:i + config.batch_max]
            self._batch_index += 1
            batch = build_batch(
                chunk, host=config.host, source=self._source,
                batch_index=self._batch_index,
                public_surface=config.public_surface,
            )
            try:
                spool_batch(batch, config)
                self._bump("spooled", len(chunk))
            except Exception:
                self._bump("dropped", len(chunk))

    def _take(self, limit: int) -> List[RunRecord]:
        records: List[RunRecord] = []
        while len(records) < limit:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is None:  # shutdown sentinel
                continue
            records.append(item)
        return records

    def _bump(self, key: str, amount: int = 1) -> None:
        with self._stats_lock:
            self._stats[key] = self._stats.get(key, 0) + amount


_worker: Optional[RunWorker] = None
_worker_lock = threading.Lock()


def get_worker() -> RunWorker:
    global _worker
    if _worker is None:
        with _worker_lock:
            if _worker is None:
                _worker = RunWorker()
    return _worker
