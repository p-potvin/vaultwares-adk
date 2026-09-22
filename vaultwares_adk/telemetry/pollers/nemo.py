"""NeMo-Speech.cpp telemetry.

NeMo-Speech.cpp runs as an inference server (port 8080 by default) exposing /ready,
/health, and /v1/models, or as a standalone CLI process (nemo-speech.exe).
Polls model residency and server readiness.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from ..record import RunRecord
from ..runs import record_run

DEFAULT_BASE_URL = "http://127.0.0.1:8123"


def _get_json(url: str, timeout: float = 5.0) -> Optional[Any]:
    try:
        with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError, OSError):
        return None


def _get_text(url: str, timeout: float = 5.0) -> Optional[str]:
    try:
        with urlopen(Request(url), timeout=timeout) as r:
            return r.read().decode("utf-8")
    except (URLError, TimeoutError, ValueError, OSError):
        return None


def list_loaded(base_url: str = DEFAULT_BASE_URL, timeout: float = 5.0) -> List[Dict[str, Any]]:
    """Models currently resident in NeMo-Speech.cpp, via /v1/models or /ready."""
    payload = _get_json(f"{base_url.rstrip('/')}/v1/models", timeout)
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [m for m in payload["data"] if isinstance(m, dict)]

    # Fallback: check /ready or /health
    ready = _get_text(f"{base_url.rstrip('/')}/ready", timeout)
    if ready is not None:
        return [{"id": "nemo-speech-ready", "loaded": True}]
    return []


def sample_loaded_models(
    base_url: str = DEFAULT_BASE_URL,
    *,
    project: Optional[str] = None,
    timeout: float = 5.0,
) -> List[RunRecord]:
    """Record residency samples for NeMo-Speech.cpp models."""
    records = []
    models = list_loaded(base_url, timeout)

    for entry in models:
        model_id = entry.get("id") or "nemo-speech"
        records.append(
            record_run(
                provider="nemo-speech",
                runtime="nemo-speech",
                model=model_id,
                task="residency",
                project=project,
                service="nemo-speech-poller",
                status="ok",
                duration_ms=0.0,
                cost_usd=0.0,
                is_free=True,
                backend="cuda",
            )
        )
    return records
