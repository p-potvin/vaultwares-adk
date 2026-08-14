"""One loop that drives every poller.

Runs as a small long-lived process (a scheduled task on clopeux-desktop) rather
than inside any one application, because the runtimes it watches outlive any
single caller and must be observed even when nothing is calling them.

A runtime being down is normal, not an error: ComfyUI is often not running.
The loop reports that as a skipped cycle and keeps going, so a stopped service
never turns into a crash-looping poller.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from ..config import get_config
from ..worker import get_worker
from . import comfyui, ollama
from .cursor import SeenCursor


def poll_once(
    *,
    comfyui_url: Optional[str] = comfyui.DEFAULT_BASE_URL,
    ollama_url: Optional[str] = ollama.DEFAULT_BASE_URL,
    seen_prompts: Optional[Any] = None,
    project: Optional[str] = None,
    sample_ollama_residency: bool = True,
) -> Dict[str, int]:
    """Run every enabled poller once. Never raises."""
    counts = {"comfyui_runs": 0, "ollama_residency": 0, "errors": 0}

    if comfyui_url:
        try:
            counts["comfyui_runs"] = len(
                comfyui.poll_history(comfyui_url, seen=seen_prompts, project=project)
            )
        except Exception:
            counts["errors"] += 1

    if ollama_url and sample_ollama_residency:
        try:
            counts["ollama_residency"] = len(
                ollama.sample_loaded_models(ollama_url, project=project)
            )
        except Exception:
            counts["errors"] += 1

    return counts


class PollerLoop:
    """Background thread that polls on an interval until stopped."""

    def __init__(
        self,
        *,
        interval_s: float = 60.0,
        comfyui_url: Optional[str] = comfyui.DEFAULT_BASE_URL,
        ollama_url: Optional[str] = ollama.DEFAULT_BASE_URL,
        project: Optional[str] = None,
        # Bounded so the cursor cannot grow without limit. Eviction is
        # oldest-first and ComfyUI trims its own history, so an id old enough to
        # fall out here will not be re-observed anyway.
        max_seen: int = 5000,
    ) -> None:
        self.interval_s = interval_s
        self.comfyui_url = comfyui_url
        self.ollama_url = ollama_url
        self.project = project
        self.max_seen = max_seen
        # Persisted, not in-memory: see cursor.py. A restart is exactly when a
        # poller re-reads history it has already recorded, and the rollup grain
        # has no second line of defence against that.
        self._seen = SeenCursor("comfyui-prompts", max_ids=max_seen)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.totals: Dict[str, int] = {"cycles": 0, "comfyui_runs": 0,
                                       "ollama_residency": 0, "errors": 0}

    def poll(self) -> Dict[str, int]:
        counts = poll_once(
            comfyui_url=self.comfyui_url,
            ollama_url=self.ollama_url,
            seen_prompts=self._seen,
            project=self.project,
        )
        # Written after each cycle rather than at shutdown: a poller that is
        # killed rather than stopped would otherwise lose the cursor and
        # re-record everything it had just seen.
        self._seen.flush()
        self.totals["cycles"] += 1
        for key, value in counts.items():
            self.totals[key] = self.totals.get(key, 0) + value
        return counts

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll()
            except Exception:
                self.totals["errors"] = self.totals.get("errors", 0) + 1
            self._stop.wait(self.interval_s)

    def start(self) -> "PollerLoop":
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="vw-pollers", daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None
        # The recorder batches hourly, so a poller that exits without flushing
        # would discard up to an hour of observations.
        get_worker().shutdown(timeout=timeout)


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for the scheduled task."""
    import argparse

    parser = argparse.ArgumentParser(description="Poll local model runtimes for telemetry.")
    parser.add_argument("--interval", type=float, default=60.0, help="seconds between polls")
    parser.add_argument("--comfyui-url", default=comfyui.DEFAULT_BASE_URL)
    parser.add_argument("--ollama-url", default=ollama.DEFAULT_BASE_URL)
    parser.add_argument("--project", default=None)
    parser.add_argument("--once", action="store_true", help="poll a single time and exit")
    args = parser.parse_args(argv)

    loop = PollerLoop(
        interval_s=args.interval,
        comfyui_url=args.comfyui_url,
        ollama_url=args.ollama_url,
        project=args.project,
    )

    if args.once:
        counts = loop.poll()
        get_worker().shutdown(timeout=20.0)
        print(f"[vw-pollers] {counts}")
        return 0

    loop.start()
    print(
        f"[vw-pollers] polling every {args.interval}s "
        f"(comfyui={args.comfyui_url} ollama={args.ollama_url}), "
        f"sending to {get_config().api_url}"
    )
    try:
        while True:
            loop._stop.wait(3600)
    except KeyboardInterrupt:
        pass
    finally:
        loop.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
