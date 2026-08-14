"""Persistent set of already-observed ids, shared by the pollers.

Needed because deterministic run ids only protect the RAW grain: ingest
discards a duplicate insert, but the hourly rollup is aggregated on the host
before the API ever sees a run id, so a re-observed job increments the bucket
again. An in-memory cursor closes that window only until the process restarts
-- which is precisely when a poller re-reads a history it has already seen.

Kept deliberately dumb: a JSON list beside the spool, rewritten atomically.
The volumes involved (hundreds of ids) do not justify anything more, and a
store that can itself fail is worse than the problem.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Iterable, Optional, Set

from ..config import get_config

_lock = threading.Lock()


class SeenCursor:
    """A bounded, persisted set of ids."""

    def __init__(self, name: str, *, max_ids: int = 5000, path: Optional[Path] = None) -> None:
        self.name = name
        self.max_ids = max_ids
        self._path = Path(path) if path else Path(get_config().spool_dir) / f"seen-{name}.json"
        self._ids: list = []
        self._set: Set[str] = set()
        self._load()

    # ── persistence ───────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                self._ids = [str(x) for x in raw][-self.max_ids:]
                self._set = set(self._ids)
        except (OSError, ValueError):
            # A missing or corrupt cursor must not stop collection; the worst
            # case is re-observing a job, which the raw grain still dedupes.
            self._ids, self._set = [], set()

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic replace: a half-written cursor read on the next start
            # would be indistinguishable from a corrupt one.
            temp = self._path.with_suffix(".tmp")
            temp.write_text(json.dumps(self._ids), encoding="utf-8")
            os.replace(temp, self._path)
        except OSError:
            pass

    # ── set behaviour ─────────────────────────────────────────────────────

    def __contains__(self, value: object) -> bool:
        return str(value) in self._set

    def __len__(self) -> int:
        return len(self._set)

    def add(self, value: str) -> None:
        key = str(value)
        with _lock:
            if key in self._set:
                return
            self._set.add(key)
            self._ids.append(key)
            if len(self._ids) > self.max_ids:
                # Oldest-first eviction: ComfyUI trims its own history, so an
                # id old enough to fall out here will not be re-observed.
                dropped, self._ids = self._ids[:-self.max_ids], self._ids[-self.max_ids:]
                self._set.difference_update(dropped)

    def update(self, values: Iterable[str]) -> None:
        for value in values:
            self.add(value)

    def flush(self) -> None:
        with _lock:
            self._save()

    def clear(self) -> None:
        with _lock:
            self._ids, self._set = [], set()
            self._save()
