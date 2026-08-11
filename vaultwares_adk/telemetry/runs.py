"""Public recording surface: ``ModelRun`` and ``@instrument``.

    from vaultwares_adk.telemetry import ModelRun

    with ModelRun(provider="huggingface", runtime="hf-inference",
                  model="Qwen/Qwen3.6-35B", task="chat", project="vault-inference") as run:
        stream = client.chat.completions.create(..., stream=True)
        for chunk in stream:
            run.first_token()          # first call wins, later ones are no-ops
        run.usage(prompt=120, completion=480)

Leaving the block records the run. An exception propagates unchanged but is
captured first, so failures are measured rather than silently missing — a
telemetry layer that only records successes makes every reliability widget lie.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from typing import Any, Callable, Dict, Optional

from . import gpu as gpu_probe
from .config import get_config
from .record import (
    STATUS_CANCELLED,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_REJECTED,
    STATUS_TIMEOUT,
    RunRecord,
    _Clock,
    hash_text,
    utc_now,
)
from .worker import get_worker


class ModelRun:
    """Context manager that times one model invocation and records it."""

    __slots__ = ("record", "_clock", "_sampled_gpu", "_finished", "_gpu_index")

    def __init__(
        self,
        *,
        provider: str,
        runtime: str,
        model: str,
        task: Optional[str] = None,
        project: Optional[str] = None,
        service: Optional[str] = None,
        session_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        caller: Optional[str] = None,
        gpu_index: Optional[int] = None,
        queued_at: Optional[Any] = None,
        **fields: Any,
    ) -> None:
        config = get_config()
        known = set(RunRecord.__dataclass_fields__)
        passthrough = {k: v for k, v in fields.items() if k in known}
        extra = {k: v for k, v in fields.items() if k not in known}

        self.record = RunRecord(
            provider=provider,
            runtime=runtime,
            model=model,
            task=task,
            host=config.host,
            project=project or config.project,
            service=service or config.service,
            session_id=session_id,
            parent_run_id=parent_run_id,
            caller=caller,
            queued_at=queued_at,
            **passthrough,
        )
        if extra:
            self.record.extra.update(extra)

        self._clock: Optional[_Clock] = None
        self._sampled_gpu = False
        self._finished = False
        self._gpu_index = gpu_index

    # ── lifecycle ─────────────────────────────────────────────────────────

    def __enter__(self) -> "ModelRun":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._close(exc_type, exc)
        return False  # never swallow

    async def __aenter__(self) -> "ModelRun":
        return self.start()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        self._close(exc_type, exc)
        return False

    def start(self) -> "ModelRun":
        self._clock = _Clock()
        self.record.started_at = self._clock.started_at
        if get_config().sample_gpu:
            # Zero torch's peak counter so vram_peak_mb measures this run only.
            gpu_probe.reset_torch_peak()
        return self

    # ── measurement ───────────────────────────────────────────────────────

    def first_token(self) -> "ModelRun":
        """Mark time-to-first-token. Only the first call has any effect."""
        if self.record.first_token_at is None and self._clock is not None:
            self.record.first_token_at = self._clock.stamp()
        return self

    def usage(
        self,
        *,
        prompt: Optional[int] = None,
        completion: Optional[int] = None,
        cached: Optional[int] = None,
        reasoning: Optional[int] = None,
        total: Optional[int] = None,
    ) -> "ModelRun":
        """Record token counts using the names most SDKs use."""
        if prompt is not None:
            self.record.input_tokens = int(prompt)
        if completion is not None:
            self.record.output_tokens = int(completion)
        if cached is not None:
            self.record.cached_input_tokens = int(cached)
        if reasoning is not None:
            self.record.reasoning_tokens = int(reasoning)
        if total is not None:
            self.record.total_tokens = int(total)
        return self

    def prompt(self, text: str) -> "ModelRun":
        """Record prompt *shape* only — length, never content.

        Neither the text nor a hash of it is recorded by default. The hash is
        not a safe middle ground: it still correlates one user across every
        record they appear in, and a short prompt brute-forces trivially. That
        rule comes from vault-inference/docs/hf-telemetry-design.md, which
        governs the public HF Spaces on this same pipeline, and it is applied
        here for every surface rather than per-call-site — a privacy default
        that has to be remembered is one that eventually is not.

        VW_RUNS_CAPTURE_PROMPTS opts a private, internal-only surface into
        hashing. It must never be set on a public surface.
        """
        if text is None:
            return self
        self.record.prompt_chars = len(text)
        config = get_config()
        if config.capture_prompt_text:
            self.record.prompt_hash = hash_text(text)
        return self

    def completion(self, text: str) -> "ModelRun":
        if text is not None:
            self.record.completion_chars = len(text)
        return self

    def cost(
        self,
        usd: Optional[float] = None,
        *,
        credits: Optional[float] = None,
        source: Optional[str] = None,
        remaining: Optional[float] = None,
    ) -> "ModelRun":
        if usd is not None:
            self.record.cost_usd = float(usd)
        if credits is not None:
            self.record.credits_used = float(credits)
        if source is not None:
            self.record.billing_source = source
        if remaining is not None:
            self.record.budget_remaining = float(remaining)
        return self

    def set(self, **fields: Any) -> "ModelRun":
        """Set any record field; unknown names land in ``extra``."""
        known = set(RunRecord.__dataclass_fields__)
        for key, value in fields.items():
            if key in known:
                setattr(self.record, key, value)
            else:
                self.record.extra[key] = value
        return self

    def tag(self, *tags: str) -> "ModelRun":
        for t in tags:
            if t not in self.record.tags:
                self.record.tags.append(t)
        return self

    def retry(self) -> "ModelRun":
        self.record.retries += 1
        return self

    # ── outcomes ──────────────────────────────────────────────────────────

    def ok(self, finish_reason: Optional[str] = None) -> "ModelRun":
        self.record.status = STATUS_OK
        if finish_reason:
            self.record.finish_reason = finish_reason
        return self

    def fail(self, exc: BaseException, *, http_status: Optional[int] = None) -> "ModelRun":
        self.record.status = _status_for(type(exc), exc)
        self.record.error_class = type(exc).__name__
        self.record.error_message = str(exc)
        if http_status is not None:
            self.record.http_status = http_status
        else:
            inferred = _http_status_of(exc)
            if inferred is not None:
                self.record.http_status = inferred
        return self

    def reject(self, reason: str, *, error_class: str = "BudgetRejected") -> "ModelRun":
        """A run stopped by policy (budget guard, rate limit) — not a fault."""
        self.record.status = STATUS_REJECTED
        self.record.error_class = error_class
        self.record.error_message = reason
        return self

    # ── emit ──────────────────────────────────────────────────────────────

    def _close(self, exc_type=None, exc=None) -> None:
        if self._finished:
            return
        self._finished = True

        if self._clock is not None:
            self.record.ended_at = self._clock.stamp()
            self.record.duration_ms = self._clock.elapsed_ms()
        else:
            self.record.ended_at = utc_now()

        if exc is not None:
            self.fail(exc)
        elif exc_type is not None:
            self.record.status = STATUS_ERROR
            self.record.error_class = getattr(exc_type, "__name__", "Error")

        if get_config().sample_gpu and not self._sampled_gpu:
            self._sampled_gpu = True
            try:
                self.record.__dict__.update(
                    {
                        k: v
                        for k, v in gpu_probe.sample_all(self._gpu_index).items()
                        if getattr(self.record, k, None) is None
                    }
                )
            except Exception:
                pass

        get_worker().record(self.record.finalize())

    def close(self) -> None:
        """Record the run without a ``with`` block (for callback-style APIs)."""
        self._close()


def _status_for(exc_type: type, exc: BaseException) -> str:
    if issubclass(exc_type, (TimeoutError, asyncio.TimeoutError)):
        return STATUS_TIMEOUT
    if issubclass(exc_type, asyncio.CancelledError) or issubclass(exc_type, KeyboardInterrupt):
        return STATUS_CANCELLED
    name = exc_type.__name__.lower()
    if "timeout" in name:
        return STATUS_TIMEOUT
    if "cancel" in name:
        return STATUS_CANCELLED
    return STATUS_ERROR


def _http_status_of(exc: BaseException) -> Optional[int]:
    """Dig an HTTP status out of the common client-library exception shapes."""
    for attr in ("status_code", "status", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value < 600:
            return value
    response = getattr(exc, "response", None)
    if response is not None:
        for attr in ("status_code", "status"):
            value = getattr(response, attr, None)
            if isinstance(value, int) and 100 <= value < 600:
                return value
    return None


def instrument(
    *,
    provider: str,
    runtime: str,
    model: str | Callable[..., str] = "unknown",
    task: Optional[str] = None,
    project: Optional[str] = None,
    extract: Optional[Callable[[ModelRun, Any], None]] = None,
    **defaults: Any,
) -> Callable:
    """Decorator form, for call sites that are a single function.

    ``model`` may be a callable taking the wrapped function's ``(args, kwargs)``
    so a per-call model name can be pulled off the arguments. ``extract`` is
    handed ``(run, result)`` after a successful call to pull usage off whatever
    the function returned.

    Works on sync functions, coroutines, and async generators (the generator
    case times the full drain, and marks TTFT on the first yield).
    """

    def decorate(fn: Callable) -> Callable:
        def _open(args, kwargs) -> ModelRun:
            resolved = model(*args, **kwargs) if callable(model) else model
            return ModelRun(
                provider=provider,
                runtime=runtime,
                model=resolved,
                task=task,
                project=project,
                caller=getattr(fn, "__qualname__", getattr(fn, "__name__", None)),
                **defaults,
            )

        if inspect.isasyncgenfunction(fn):

            @functools.wraps(fn)
            async def async_gen_wrapper(*args, **kwargs):
                async with _open(args, kwargs) as run:
                    async for item in fn(*args, **kwargs):
                        run.first_token()
                        yield item

            return async_gen_wrapper

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                async with _open(args, kwargs) as run:
                    result = await fn(*args, **kwargs)
                    if extract is not None:
                        try:
                            extract(run, result)
                        except Exception:
                            pass
                    return result

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            with _open(args, kwargs) as run:
                result = fn(*args, **kwargs)
                if extract is not None:
                    try:
                        extract(run, result)
                    except Exception:
                        pass
                return result

        return sync_wrapper

    return decorate


def record_run(**fields: Any) -> RunRecord:
    """One-shot recording for work that was already timed elsewhere (pollers).

    Pollers observe a finished job — they have no block to wrap — so they build
    the record directly and hand it straight to the worker.
    """
    known = set(RunRecord.__dataclass_fields__)
    config = get_config()
    passthrough = {k: v for k, v in fields.items() if k in known}
    extra = {k: v for k, v in fields.items() if k not in known}
    passthrough.setdefault("host", config.host)
    passthrough.setdefault("project", config.project)
    record = RunRecord(**passthrough)
    if extra:
        record.extra.update(extra)
    get_worker().record(record.finalize())
    return record


def usage_from_openai(run: ModelRun, response: Any) -> None:
    """Pull token usage off an OpenAI-shaped response (dict or SDK object)."""
    usage = response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)
    if usage is None:
        return
    get = (lambda k: usage.get(k)) if isinstance(usage, dict) else (lambda k: getattr(usage, k, None))
    run.usage(
        prompt=get("prompt_tokens"),
        completion=get("completion_tokens"),
        total=get("total_tokens"),
    )
    details = get("prompt_tokens_details")
    if details is not None:
        cached = details.get("cached_tokens") if isinstance(details, dict) else getattr(details, "cached_tokens", None)
        if cached is not None:
            run.usage(cached=cached)
    out_details = get("completion_tokens_details")
    if out_details is not None:
        reasoning = (
            out_details.get("reasoning_tokens")
            if isinstance(out_details, dict)
            else getattr(out_details, "reasoning_tokens", None)
        )
        if reasoning is not None:
            run.usage(reasoning=reasoning)

    choices = response.get("choices") if isinstance(response, dict) else getattr(response, "choices", None)
    if choices:
        first = choices[0]
        reason = first.get("finish_reason") if isinstance(first, dict) else getattr(first, "finish_reason", None)
        if reason:
            run.ok(reason)
