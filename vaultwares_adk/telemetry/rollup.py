"""Local hourly rollups, updated per run.

The hourly grain is the durable one: per-run rows stay only for a short
debugging window, so every KPI that has to survive is computed here, on the
host, as runs happen. Sending is hourly; aggregating is continuous, so a
crash loses at most the current partial hour rather than a whole batch.

WHY A HISTOGRAM AND NOT A PERCENTILE
------------------------------------
A rollup has to be *mergeable* — across hosts, and across the same hour
arriving in two different sends. Percentiles are not: you cannot average a p95.
So each bucket carries a fixed-edge histogram of durations, which merges by
elementwise addition and still answers p50/p95 by interpolation. The edges match
the API's latency endpoint exactly, so a chart drawn from rollups and one drawn
from raw rows agree.

Sums are paired with their own counts. A run that never reported TTFT must not
drag the average toward zero — it has to be absent from the denominator, not
present as a nought.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .record import RunRecord, iso

# Shared with vaultwares-api's /latency endpoint. Changing these invalidates
# comparison between rollup-derived and raw-derived charts, so they change
# together or not at all.
DURATION_EDGES_MS: Tuple[float, ...] = (
    0, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000, 300000,
)

# The dimensions an hourly bucket is keyed by. Deliberately excludes anything
# unbounded (run_id, request_id, prompt hashes) — a rollup whose cardinality
# grows with traffic is not a rollup.
KEY_FIELDS = (
    "provider", "runtime", "model", "task", "project", "host", "status",
)


def hour_floor(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _bucket_index(value: float) -> int:
    """Index of the histogram bucket a duration falls in."""
    index = 0
    for i, edge in enumerate(DURATION_EDGES_MS):
        if value >= edge:
            index = i
        else:
            break
    return index


class Bucket:
    """One (hour, dimensions) cell. Accumulates; never stores a raw run."""

    __slots__ = (
        "hour", "key", "runs", "failures", "input_tokens", "output_tokens",
        "cached_input_tokens", "reasoning_tokens", "total_tokens", "cost_usd",
        "cost_usd_provisional", "duration_sum", "duration_min", "duration_max",
        "duration_hist", "ttft_sum", "ttft_count", "ttft_max", "queue_sum",
        "queue_count", "tps_sum", "tps_count", "vram_peak_max", "gpu_util_sum",
        "gpu_util_count", "retries", "free_runs",
    )

    def __init__(self, hour: datetime, key: Tuple[str, ...]) -> None:
        self.hour = hour
        self.key = key
        self.runs = 0
        self.failures = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_input_tokens = 0
        self.reasoning_tokens = 0
        self.total_tokens = 0
        self.cost_usd = 0.0
        self.cost_usd_provisional = 0.0
        self.duration_sum = 0.0
        self.duration_min: Optional[float] = None
        self.duration_max: Optional[float] = None
        self.duration_hist = [0] * len(DURATION_EDGES_MS)
        self.ttft_sum = 0.0
        self.ttft_count = 0
        self.ttft_max: Optional[float] = None
        self.queue_sum = 0.0
        self.queue_count = 0
        self.tps_sum = 0.0
        self.tps_count = 0
        self.vram_peak_max: Optional[float] = None
        self.gpu_util_sum = 0.0
        self.gpu_util_count = 0
        self.retries = 0
        self.free_runs = 0

    def add(self, record: RunRecord) -> None:
        self.runs += 1
        # `rejected` and `cancelled` are policy outcomes, not faults — the same
        # rule the failure-rate KPI uses, applied here so the rollup and the raw
        # query cannot disagree.
        if record.status in ("error", "timeout"):
            self.failures += 1
        self.retries += record.retries or 0
        if record.is_free:
            self.free_runs += 1

        for name in ("input_tokens", "output_tokens", "cached_input_tokens",
                     "reasoning_tokens", "total_tokens"):
            value = getattr(record, name)
            if value:
                setattr(self, name, getattr(self, name) + int(value))

        if record.cost_usd:
            if record.cost_state == "provisional":
                self.cost_usd_provisional += float(record.cost_usd)
            else:
                self.cost_usd += float(record.cost_usd)

        if record.duration_ms is not None:
            d = float(record.duration_ms)
            self.duration_sum += d
            self.duration_min = d if self.duration_min is None else min(self.duration_min, d)
            self.duration_max = d if self.duration_max is None else max(self.duration_max, d)
            self.duration_hist[_bucket_index(d)] += 1

        if record.ttft_ms is not None:
            t = float(record.ttft_ms)
            self.ttft_sum += t
            self.ttft_count += 1
            self.ttft_max = t if self.ttft_max is None else max(self.ttft_max, t)

        if record.queue_ms is not None:
            self.queue_sum += float(record.queue_ms)
            self.queue_count += 1

        if record.tokens_per_second is not None:
            self.tps_sum += float(record.tokens_per_second)
            self.tps_count += 1

        if record.vram_peak_mb is not None:
            v = float(record.vram_peak_mb)
            self.vram_peak_max = v if self.vram_peak_max is None else max(self.vram_peak_max, v)

        if record.gpu_util_pct is not None:
            self.gpu_util_sum += float(record.gpu_util_pct)
            self.gpu_util_count += 1

    def to_json(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"hour": iso(self.hour)}
        payload.update(dict(zip(KEY_FIELDS, self.key)))
        payload.update({
            "runs": self.runs,
            "failures": self.failures,
            "retries": self.retries,
            "free_runs": self.free_runs,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 10),
            "cost_usd_provisional": round(self.cost_usd_provisional, 10),
            "duration_ms_sum": round(self.duration_sum, 3),
            "duration_ms_min": self.duration_min,
            "duration_ms_max": self.duration_max,
            "duration_hist": list(self.duration_hist),
            "ttft_ms_sum": round(self.ttft_sum, 3),
            "ttft_ms_count": self.ttft_count,
            "ttft_ms_max": self.ttft_max,
            "queue_ms_sum": round(self.queue_sum, 3),
            "queue_ms_count": self.queue_count,
            "tokens_per_second_sum": round(self.tps_sum, 3),
            "tokens_per_second_count": self.tps_count,
            "vram_peak_mb_max": self.vram_peak_max,
            "gpu_util_pct_sum": round(self.gpu_util_sum, 3),
            "gpu_util_pct_count": self.gpu_util_count,
        })
        # Drop nulls so an hour with no GPU present does not ship a row of
        # nulls that reads as "measured zero".
        return {k: v for k, v in payload.items() if v is not None}


class RollupAggregator:
    """Thread-safe map of (hour, dimensions) -> Bucket."""

    def __init__(self, max_buckets: int = 20000) -> None:
        self._buckets: Dict[Tuple[Any, ...], Bucket] = {}
        self._lock = threading.Lock()
        self._max_buckets = max_buckets
        self._dropped = 0

    def add(self, record: RunRecord) -> None:
        moment = record.started_at or record.ended_at
        if moment is None:
            return
        hour = hour_floor(moment)
        key = tuple(str(getattr(record, f) or "unknown") for f in KEY_FIELDS)
        full = (hour,) + key
        with self._lock:
            bucket = self._buckets.get(full)
            if bucket is None:
                if len(self._buckets) >= self._max_buckets:
                    # Pathological cardinality (a model name with a uuid in it,
                    # say). Shedding is better than unbounded growth; the raw
                    # rows still carry the detail.
                    self._dropped += 1
                    return
                bucket = Bucket(hour, key)
                self._buckets[full] = bucket
            bucket.add(record)

    def add_many(self, records: Iterable[RunRecord]) -> None:
        for record in records:
            self.add(record)

    def take_closed(self, now: Optional[datetime] = None) -> List[Bucket]:
        """Remove and return buckets whose hour has ended.

        The current hour stays open so it keeps accumulating; only complete
        hours are shipped, which is what makes a rollup row final and lets
        ingest treat a replay as an overwrite rather than an addition.
        """
        current = hour_floor(now or datetime.now(timezone.utc))
        with self._lock:
            closed_keys = [k for k in self._buckets if k[0] < current]
            return [self._buckets.pop(k) for k in closed_keys]

    def take_all(self, ) -> List[Bucket]:
        """Remove and return every bucket, including the open hour.

        Used at shutdown: a partial hour on disk beats a lost one, and ingest
        overwrites the row when the rest of the hour arrives later.
        """
        with self._lock:
            buckets = list(self._buckets.values())
            self._buckets.clear()
            return buckets

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {"open_buckets": len(self._buckets), "dropped_buckets": self._dropped}


def build_rollup_batch(
    buckets: List[Bucket], host: str, source: str, batch_index: int
) -> Dict[str, Any]:
    from .record import SCHEMA_VERSION, utc_now

    return {
        "schema": SCHEMA_VERSION,
        "source": source,
        "host": host,
        "collectedAt": iso(utc_now()),
        "batchIndex": batch_index,
        "grain": "hour",
        "rollups": [b.to_json() for b in buckets],
    }


def percentile_from_hist(hist: List[int], quantile: float) -> Optional[float]:
    """Interpolate a percentile out of the fixed-edge histogram.

    Approximate by construction — the point of the histogram is mergeability,
    and a p95 that is right to the nearest bucket is worth far more than an
    exact one that cannot be combined across hosts.
    """
    total = sum(hist)
    if total == 0:
        return None
    target = quantile * total
    cumulative = 0
    for i, count in enumerate(hist):
        if count == 0:
            continue
        if cumulative + count >= target:
            lo = DURATION_EDGES_MS[i]
            hi = DURATION_EDGES_MS[i + 1] if i + 1 < len(DURATION_EDGES_MS) else lo * 2
            within = (target - cumulative) / count
            return lo + (hi - lo) * within
        cumulative += count
    return float(DURATION_EDGES_MS[-1])
