"""Ollama telemetry.

Ollama has no history endpoint: once a response is returned, the numbers are
gone. But the response *body* carries the richest per-run metrics of any
backend we talk to -- load time, prompt-eval time and token count, decode time
and token count, all in nanoseconds -- so a run recorded at the call site is
strictly better than anything a poller could reconstruct.

Hence two entry points, covering the two situations:

* ``record_response()`` / ``OllamaClient`` -- for code we control. Full
  per-run KPIs.
* ``sample_loaded_models()`` -- a background sampler over /api/ps, which is the
  only visibility available for traffic we do not own. It reports model
  residency and VRAM, not invocations, and is recorded as such rather than
  being dressed up as runs that never happened.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from ..record import RunRecord
from ..runs import record_run

DEFAULT_BASE_URL = "http://127.0.0.1:11434"

# Ollama reports every duration in nanoseconds.
_NS_PER_MS = 1_000_000
_NS_PER_S = 1_000_000_000


def _ms(nanoseconds: Optional[Any]) -> Optional[float]:
    if not nanoseconds:
        return None
    try:
        return round(float(nanoseconds) / _NS_PER_MS, 3)
    except (TypeError, ValueError):
        return None


def metrics_from_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """Map an Ollama response body onto RunRecord fields.

    Time to first token is modelled as load + prompt-eval: that is everything
    that happens before the first output token can be emitted, which is what
    TTFT means for every other backend in this table. Throughput is derived
    from eval_duration alone rather than total_duration, so a cold model load
    does not get charged against decode speed.
    """
    out: Dict[str, Any] = {}

    model = response.get("model")
    if model:
        out["model"] = model

    load_ms = _ms(response.get("load_duration"))
    prompt_ms = _ms(response.get("prompt_eval_duration"))
    eval_ms = _ms(response.get("eval_duration"))
    total_ms = _ms(response.get("total_duration"))

    if total_ms is not None:
        out["duration_ms"] = total_ms
    if load_ms is not None:
        out["load_ms"] = load_ms
    if load_ms is not None or prompt_ms is not None:
        out["ttft_ms"] = round((load_ms or 0.0) + (prompt_ms or 0.0), 3)

    prompt_tokens = response.get("prompt_eval_count")
    eval_tokens = response.get("eval_count")
    if prompt_tokens is not None:
        out["input_tokens"] = int(prompt_tokens)
    if eval_tokens is not None:
        out["output_tokens"] = int(eval_tokens)

    if eval_tokens and response.get("eval_duration"):
        seconds = float(response["eval_duration"]) / _NS_PER_S
        if seconds > 0:
            out["tokens_per_second"] = round(int(eval_tokens) / seconds, 3)

    reason = response.get("done_reason")
    if reason:
        out["finish_reason"] = reason
        # Ollama says "length" when it hit num_predict. That is a truncated
        # answer that was still paid for in compute, so it stays visible rather
        # than being flattened into a plain success.
        out["status"] = "ok"

    return out


def record_response(
    response: Dict[str, Any],
    *,
    project: Optional[str] = None,
    service: Optional[str] = None,
    task: str = "chat",
    model: Optional[str] = None,
    **extra: Any,
) -> RunRecord:
    """Record one Ollama call from its response body."""
    fields = metrics_from_response(response)
    fields.setdefault("model", model or "unknown")
    return record_run(
        provider="ollama",
        runtime="ollama",
        task=task,
        project=project,
        service=service,
        backend="ollama",
        # Local weights: a real zero, not a missing measurement. The free-vs-paid
        # split depends on telling those apart.
        cost_usd=0.0,
        priced_exactly=True,
        is_free=True,
        **{**fields, **extra},
    )


def _get_json(url: str, timeout: float = 5.0) -> Optional[Any]:
    try:
        with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError, OSError):
        return None


def list_loaded(base_url: str = DEFAULT_BASE_URL, timeout: float = 5.0) -> List[Dict[str, Any]]:
    """Models currently resident in memory, via /api/ps."""
    payload = _get_json(f"{base_url.rstrip('/')}/api/ps", timeout)
    if not isinstance(payload, dict):
        return []
    return payload.get("models") or []


def sample_loaded_models(
    base_url: str = DEFAULT_BASE_URL,
    *,
    project: Optional[str] = None,
    timeout: float = 5.0,
) -> List[RunRecord]:
    """Record a residency sample per loaded model.

    These are emitted with task="residency", never as chat runs. A loaded model
    is not an invocation, and counting it as one would inflate every volume
    widget with work that never happened.
    """
    records = []
    for entry in list_loaded(base_url, timeout):
        name = entry.get("name") or entry.get("model") or "unknown"
        vram = entry.get("size_vram")
        records.append(
            record_run(
                provider="ollama",
                runtime="ollama",
                model=name,
                task="residency",
                project=project,
                service="ollama-poller",
                status="ok",
                duration_ms=0.0,
                cost_usd=0.0,
                is_free=True,
                vram_used_mb=round(vram / 1048576, 1) if vram else None,
                vram_peak_mb=round(vram / 1048576, 1) if vram else None,
                digest=entry.get("digest"),
                expires_at=entry.get("expires_at"),
                size_bytes=entry.get("size"),
            )
        )
    return records


class OllamaClient:
    """Minimal recording client for code we control.

    Wraps /api/chat and /api/generate so a caller gets telemetry for free.
    Streaming is deliberately not supported here: the per-run metrics only
    arrive in the final frame, and a partial reader would silently record
    nothing. Callers who stream should hand their final frame to
    ``record_response()`` instead.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        project: Optional[str] = None,
        service: Optional[str] = None,
        timeout: float = 300.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.project = project
        self.service = service
        self.timeout = timeout

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def chat(self, model: str, messages: List[Dict[str, str]], **options: Any) -> Dict[str, Any]:
        payload = {"model": model, "messages": messages, "stream": False, **options}
        return self._call("/api/chat", payload, model, "chat")

    def generate(self, model: str, prompt: str, **options: Any) -> Dict[str, Any]:
        payload = {"model": model, "prompt": prompt, "stream": False, **options}
        return self._call("/api/generate", payload, model, "completion")

    def embed(self, model: str, text: str, **options: Any) -> Dict[str, Any]:
        payload = {"model": model, "input": text, **options}
        return self._call("/api/embed", payload, model, "embedding")

    def _call(self, path: str, payload: Dict[str, Any], model: str, task: str) -> Dict[str, Any]:
        run_id = uuid.uuid4().hex
        try:
            response = self._post(path, payload)
        except Exception as exc:
            # A failed call is the one most worth recording, so it is recorded
            # before the exception is re-raised.
            record_run(
                provider="ollama", runtime="ollama", model=model, task=task,
                project=self.project, service=self.service, run_id=run_id,
                status="error", error_class=type(exc).__name__,
                error_message=str(exc), cost_usd=0.0, is_free=True,
            )
            raise
        record_response(
            response, project=self.project, service=self.service,
            task=task, model=model, run_id=run_id,
        )
        return response
