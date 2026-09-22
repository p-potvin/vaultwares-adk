"""audio.cpp telemetry.

audio.cpp runs an inference server (port 8099 by default) exposing /v1/models
and /health. Like Ollama, residency and loaded model status can be polled
periodically to record active ASR/audio model residency in VRAM/RAM.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from ..record import RunRecord
from ..runs import record_run

DEFAULT_BASE_URL = "http://127.0.0.1:8099"


def _get_json(url: str, timeout: float = 5.0) -> Optional[Any]:
    try:
        with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError, OSError):
        return None


def list_loaded(base_url: str = DEFAULT_BASE_URL, timeout: float = 5.0) -> List[Dict[str, Any]]:
    """Models currently resident/loaded in audio.cpp, via /v1/models."""
    payload = _get_json(f"{base_url.rstrip('/')}/v1/models", timeout)
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    return [m for m in data if isinstance(m, dict) and m.get("loaded", True)]


def check_health(base_url: str = DEFAULT_BASE_URL, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
    """Check /health endpoint for server status and backend info."""
    payload = _get_json(f"{base_url.rstrip('/')}/health", timeout)
    return payload if isinstance(payload, dict) else None


def sample_loaded_models(
    base_url: str = DEFAULT_BASE_URL,
    *,
    project: Optional[str] = None,
    timeout: float = 5.0,
) -> List[RunRecord]:
    """Record a residency sample per loaded model in audio.cpp.

    Emitted with task="residency" to reflect active model presence in compute memory.
    """
    records = []
    models = list_loaded(base_url, timeout)
    health = check_health(base_url, timeout) or {}
    backend = health.get("backend", "cuda")

    for entry in models:
        model_id = entry.get("id") or entry.get("path") or "audiocpp-model"
        records.append(
            record_run(
                provider="audiocpp",
                runtime="audiocpp",
                model=model_id,
                task="residency",
                project=project,
                service="audiocpp-poller",
                status="ok",
                duration_ms=0.0,
                cost_usd=0.0,
                is_free=True,
                backend=backend,
            )
        )
    return records
