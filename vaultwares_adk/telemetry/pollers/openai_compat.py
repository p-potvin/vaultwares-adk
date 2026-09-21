"""Generic OpenAI-compatible model server poller (vLLM, llama.cpp, etc.).

Scans local endpoints (e.g. port 8000 and ports 8080 through 8100) for active
OpenAI-compatible inference engines exposing /v1/models.
"""

from __future__ import annotations

import json
import socket
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.error import URLError
from urllib.request import Request, urlopen

from ..record import RunRecord
from ..runs import record_run

# Standard vLLM/FastAPI is 8000; llama.cpp and local engines often bind 8080-8100.
DEFAULT_PORTS: List[int] = [8000] + list(range(8080, 8101))
DEFAULT_EXCLUDE_PORTS: Set[int] = {8099, 8123}  # Covered by dedicated audiocpp and nemo pollers


def _is_port_open(host: str, port: int, timeout: float = 0.15) -> bool:
    """Fast TCP probe before attempting HTTP."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, TimeoutError):
        return False


def _get_json(url: str, timeout: float = 1.0) -> Optional[Any]:
    try:
        req = Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "vaultwares-adk/openai-compat"},
        )
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError, OSError):
        return None


def probe_endpoint(base_url: str, timeout: float = 1.0) -> List[Dict[str, Any]]:
    """Query /v1/models on an OpenAI-compatible server."""
    endpoint = f"{base_url.rstrip('/')}/v1/models"
    data = _get_json(endpoint, timeout=timeout)
    if isinstance(data, dict):
        if isinstance(data.get("data"), list):
            return data["data"]
        if isinstance(data.get("models"), list):
            return data["models"]
    elif isinstance(data, list):
        return data
    return []


def scan_and_sample(
    ports: Optional[Iterable[int]] = None,
    host: str = "127.0.0.1",
    *,
    exclude_ports: Optional[Set[int]] = None,
    project: Optional[str] = None,
    probe_timeout: float = 0.15,
    http_timeout: float = 1.0,
) -> List[RunRecord]:
    """Scan configured ports, probe /v1/models on open ones, and record residency."""
    target_ports = DEFAULT_PORTS if ports is None else list(ports)
    excludes = DEFAULT_EXCLUDE_PORTS if exclude_ports is None else exclude_ports
    records: List[RunRecord] = []

    for port in target_ports:
        if port in excludes:
            continue
        if not _is_port_open(host, port, timeout=probe_timeout):
            continue

        base_url = f"http://{host}:{port}"
        models = probe_endpoint(base_url, timeout=http_timeout)
        for m in models:
            model_id = m.get("id") or m.get("name") or "unknown"
            owned_by = str(m.get("owned_by") or "").lower()
            runtime = (
                "vllm"
                if "vllm" in owned_by or "vllm" in model_id.lower()
                else (
                    "llama.cpp"
                    if "llama" in owned_by or "llama" in model_id.lower()
                    else "openai-compat"
                )
            )

            rec = record_run(
                provider="local",
                runtime=runtime,
                model=model_id,
                task="residency",
                project=project,
                service=f"openai-compat-{port}",
                status="ok",
                is_free=True,
                cost_usd=0.0,
                extra={"port": port, "endpoint": base_url, "meta": m},
            )
            if rec:
                records.append(rec)

    return records
