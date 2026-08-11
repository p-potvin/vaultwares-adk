"""Transport: POST a batch, fall back to an NDJSON spool file.

Deliberately identical in shape to agent-ledger's input tracker
(``scripts/track-input.py`` + ``scripts/drain-spool.ps1``):

  * one spool file per day, ``YYYY-MM-DD.jsonl``
  * one **whole batch object** per line, not one run per line
  * the drainer POSTs each line and renames the file ``.jsonl.sent`` on success

Keeping the layout the same means the existing drain script works against the
run spool with only its URL changed.
"""

from __future__ import annotations

import json
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import TelemetryConfig

_write_lock = threading.Lock()

USER_AGENT = "vaultwares-adk-runs/1"


class PostFailed(Exception):
    """Raised by ``post_batch`` so the caller knows to spool instead."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def post_batch(batch: Dict[str, Any], config: TelemetryConfig, kind: str = "runs") -> None:
    body = json.dumps(batch, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    if config.api_key:
        headers["x-api-key"] = config.api_key

    url = config.rollup_ingest_url if kind == "rollups" else config.ingest_url
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=config.post_timeout_s) as response:
            if response.status >= 300:
                raise PostFailed(f"status {response.status}", response.status)
    except HTTPError as exc:
        raise PostFailed(f"http {exc.code}: {exc.reason}", exc.code) from exc
    except URLError as exc:
        raise PostFailed(f"unreachable: {exc.reason}") from exc
    except Exception as exc:  # socket timeouts, TLS errors, DNS
        raise PostFailed(str(exc)) from exc


def spool_batch(batch: Dict[str, Any], config: TelemetryConfig, kind: str = "runs") -> Path:
    """Append a batch as one NDJSON line. Returns the file written.

    Runs and rollups go to separate files because the drain script posts each
    to a different endpoint — one file per day per kind keeps that a filename
    match rather than a per-line inspection.
    """
    spool_dir = Path(config.spool_dir)
    prefix = "rollups-" if kind == "rollups" else ""
    path = spool_dir / f"{prefix}{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    line = json.dumps(batch, separators=(",", ":"), ensure_ascii=False) + "\n"
    with _write_lock:
        spool_dir.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
    return path


def deliver(batch: Dict[str, Any], config: TelemetryConfig, kind: str = "runs") -> str:
    """Try the API, spool on any failure. Never raises.

    Returns ``"posted"``, ``"spooled"``, or ``"dropped"`` — the last only when
    even writing to disk failed, which is the one case worth a stderr line.
    """
    size = len(batch.get("rollups" if kind == "rollups" else "runs", []))
    try:
        post_batch(batch, config, kind)
        return "posted"
    except PostFailed as exc:
        if config.debug:
            _warn(f"post failed ({exc}) — spooling {size} {kind} record(s)")
    except Exception as exc:
        if config.debug:
            _warn(f"post error ({exc!r}) — spooling")

    try:
        spool_batch(batch, config, kind)
        return "spooled"
    except Exception as exc:
        _warn(f"spool write failed, dropping {size} {kind} record(s): {exc!r}")
        return "dropped"


def spool_backlog(config: TelemetryConfig) -> Dict[str, int]:
    """Count undelivered batches on disk, for health reporting."""
    spool_dir = Path(config.spool_dir)
    batches = 0
    total_bytes = 0
    try:
        if not spool_dir.exists():
            return {"batches": 0, "bytes": 0, "files": 0}
        files = list(spool_dir.glob("*.jsonl"))
        for path in files:
            total_bytes += path.stat().st_size
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                batches += sum(1 for line in handle if line.strip())
        return {"batches": batches, "bytes": total_bytes, "files": len(files)}
    except Exception:
        return {"batches": batches, "bytes": total_bytes, "files": 0}


def _warn(message: str) -> None:
    print(f"[vw-telemetry] {message}", file=sys.stderr)
