"""The model-run record: one row per model invocation, everywhere.

A "run" is a single unit of model work — one chat completion, one embedding
call, one diffusion job, one transcription, one HF job submission. It is
deliberately *not* the same entity as an assistant session (see the
``ai_sessions`` table): sessions are conversations, runs are invocations.

Every field is optional except the identity quartet (run_id, provider, runtime,
model) because no single backend reports all of them. Unknown fields set through
``ModelRun.set()`` land in ``extra`` and survive to the API's JSONB column.
"""

from __future__ import annotations

import hashlib
import os
import platform
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1

# Terminal states. `rejected` covers budget-guard/rate-limit refusals that never
# reached the model — separating them from `error` keeps failure-rate widgets
# honest, since a budget stop is a policy outcome, not a fault.
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_TIMEOUT = "timeout"
STATUS_CANCELLED = "cancelled"
STATUS_REJECTED = "rejected"
TERMINAL_STATUSES = {STATUS_OK, STATUS_ERROR, STATUS_TIMEOUT, STATUS_CANCELLED, STATUS_REJECTED}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if dt else None


def hash_text(value: str) -> str:
    """Stable short digest, so repeated prompts can be correlated without
    storing their content."""
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:32]


@dataclass
class RunRecord:
    # ── identity ──────────────────────────────────────────────────────────
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    parent_run_id: Optional[str] = None
    # provider = who bills/serves it: huggingface | nvidia-nim | ngc | nemo |
    #            openai | anthropic | local | ollama | comfyui | replicate
    provider: str = "unknown"
    # runtime = how it executed: hf-inference | hf-endpoint | hf-job | hf-space |
    #           transformers | vllm | llama.cpp | ollama | diffusers | comfyui |
    #           triton | nim | faster-whisper
    runtime: str = "unknown"
    model: str = "unknown"
    model_revision: Optional[str] = None
    quantization: Optional[str] = None
    # task = chat | completion | embedding | rerank | image | video | audio-tts |
    #        audio-asr | vision | classification | job
    task: Optional[str] = None

    # ── attribution ───────────────────────────────────────────────────────
    host: Optional[str] = None
    project: Optional[str] = None
    service: Optional[str] = None
    session_id: Optional[str] = None
    caller: Optional[str] = None
    environment: Optional[str] = None

    # ── timing (ms, wall clock) ───────────────────────────────────────────
    queued_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    first_token_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    queue_ms: Optional[float] = None
    ttft_ms: Optional[float] = None
    duration_ms: Optional[float] = None
    tokens_per_second: Optional[float] = None

    # ── tokens ────────────────────────────────────────────────────────────
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cached_input_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

    # ── request parameters ────────────────────────────────────────────────
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    seed: Optional[int] = None
    stream: Optional[bool] = None
    batch_size: Optional[int] = None
    context_length: Optional[int] = None

    # ── outcome ───────────────────────────────────────────────────────────
    status: str = STATUS_OK
    finish_reason: Optional[str] = None
    error_class: Optional[str] = None
    error_message: Optional[str] = None
    http_status: Optional[int] = None
    retries: int = 0

    # ── provider round-trip ───────────────────────────────────────────────
    # `request_id` is HF's X-Request-ID: it makes a row traceable back to them
    # and gives ingest a natural dedupe key alongside run_id.
    request_id: Optional[str] = None
    served_model: Optional[str] = None
    upstream_provider: Optional[str] = None
    # provider_ms is the provider's own time. latency_ms - provider_ms is our
    # gateway overhead, which is the part we can actually fix — worth its own
    # column rather than being recomputed by every reader.
    provider_ms: Optional[float] = None
    backend: Optional[str] = None
    role: Optional[str] = None
    load_ms: Optional[float] = None

    # ── cost / budget ─────────────────────────────────────────────────────
    cost_usd: Optional[float] = None
    credits_used: Optional[float] = None
    billing_source: Optional[str] = None
    budget_remaining: Optional[float] = None
    is_free: Optional[bool] = None
    # `priced_exactly` distinguishes a real figure from a worst-case guess;
    # `cost_state` distinguishes a settled cost from one still to be corrected
    # by the reconciliation pass (embeddings bill by time, not tokens).
    priced_exactly: Optional[bool] = None
    cost_state: str = "settled"

    # ── hardware ──────────────────────────────────────────────────────────
    device: Optional[str] = None
    gpu_name: Optional[str] = None
    gpu_index: Optional[int] = None
    gpu_util_pct: Optional[float] = None
    gpu_temp_c: Optional[float] = None
    gpu_power_w: Optional[float] = None
    vram_used_mb: Optional[float] = None
    vram_peak_mb: Optional[float] = None
    vram_total_mb: Optional[float] = None
    cpu_pct: Optional[float] = None
    rss_mb: Optional[float] = None

    # ── payload shape (never content) ─────────────────────────────────────
    prompt_chars: Optional[int] = None
    prompt_hash: Optional[str] = None
    completion_chars: Optional[int] = None
    image_count: Optional[int] = None
    audio_seconds: Optional[float] = None
    video_frames: Optional[int] = None
    output_bytes: Optional[int] = None

    # ── diffusion / media specifics ───────────────────────────────────────
    steps: Optional[int] = None
    sampler: Optional[str] = None
    scheduler: Optional[str] = None
    cfg_scale: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    lora_count: Optional[int] = None

    # ── anything a backend reports that has no column yet ──────────────────
    tags: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def finalize(self) -> "RunRecord":
        """Fill every derivable field. Idempotent — safe to call twice."""
        if self.ended_at is None:
            self.ended_at = utc_now()

        # Backfill the start. Pollers observe work that has already finished
        # (a ComfyUI history entry, an Ollama response, a completed HF job), so
        # they report a duration and no start time. Left NULL, such a row is
        # invisible to every time-windowed query over ai_runs while the hourly
        # rollup still counts it — the two grains then disagree about how much
        # ran, which is worse than an approximate timestamp.
        if self.started_at is None and self.ended_at is not None:
            if self.duration_ms:
                self.started_at = self.ended_at - timedelta(milliseconds=self.duration_ms)
            else:
                self.started_at = self.ended_at

        if self.started_at is not None:
            if self.duration_ms is None:
                self.duration_ms = _ms_between(self.started_at, self.ended_at)
            if self.ttft_ms is None and self.first_token_at is not None:
                self.ttft_ms = _ms_between(self.started_at, self.first_token_at)
            if self.queue_ms is None and self.queued_at is not None:
                self.queue_ms = _ms_between(self.queued_at, self.started_at)

        if self.total_tokens is None:
            parts = [t for t in (self.input_tokens, self.output_tokens) if t is not None]
            if parts:
                self.total_tokens = sum(parts)

        # Decode throughput measures generation, so it runs from first token to
        # end — not from request start, which would fold queue + prefill into
        # the rate and understate every streamed run.
        if self.tokens_per_second is None and self.output_tokens:
            if self.first_token_at is not None and self.ended_at is not None:
                decode_ms = _ms_between(self.first_token_at, self.ended_at)
            else:
                decode_ms = self.duration_ms
            if decode_ms and decode_ms > 0:
                self.tokens_per_second = round(self.output_tokens / (decode_ms / 1000.0), 3)

        if self.vram_peak_mb is None:
            self.vram_peak_mb = self.vram_used_mb

        for name in ("duration_ms", "ttft_ms", "queue_ms"):
            value = getattr(self, name)
            if value is not None:
                setattr(self, name, round(value, 3))

        if self.status not in TERMINAL_STATUSES:
            self.status = STATUS_ERROR
        if self.error_message:
            self.error_message = self.error_message[:2000]
        return self

    def to_json(self, public_surface: bool = False) -> Dict[str, Any]:
        """Wire form: ISO timestamps, no None padding, no empty containers.

        ``public_surface`` applies the narrower allowlist — see
        PUBLIC_SURFACE_FIELDS.
        """
        raw = asdict(self)
        for key in ("queued_at", "started_at", "first_token_at", "ended_at"):
            raw[key] = iso(getattr(self, key))
        payload = {
            k: v
            for k, v in raw.items()
            if v is not None and not (isinstance(v, (dict, list)) and not v)
        }
        if public_surface:
            payload = scrub_public(payload)
        return payload


def _ms_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() * 1000.0


# Fields a PUBLIC surface (an HF Space serving strangers) may send. This is an
# allowlist, not a denylist, and that is deliberate: a denylist fails open, so
# the day someone adds a field it ships by default and nobody notices until it
# is already in the database. Adding a name here is meant to be a reviewed edit.
#
# Rationale and the banned list live in
# vault-inference/docs/hf-telemetry-design.md. Never emitted from a public
# surface: anything identifying an end user, anything from the request body,
# any file path, and anything describing our internal estate (host, project,
# caller, service, session, gpu/host hardware).
PUBLIC_SURFACE_FIELDS = frozenset({
    "run_id", "provider", "runtime", "model", "served_model", "task",
    "request_id", "queued_at", "started_at", "ended_at", "queue_ms", "ttft_ms",
    "duration_ms", "provider_ms", "tokens_per_second", "input_tokens",
    "output_tokens", "cached_input_tokens", "reasoning_tokens", "total_tokens",
    "status", "finish_reason", "error_class", "http_status", "retries",
    "cost_usd", "priced_exactly", "cost_state", "is_free", "role",
    "prompt_chars", "completion_chars", "image_count", "audio_seconds",
    "steps", "width", "height",
})


def scrub_public(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce a record to the fields a public surface may emit.

    Applied by the sender, and again by the API on ingest. Filtering only at the
    sender would trust a client we do not control: a Space's posting key can
    leak, and whatever holds it can then POST arbitrary JSON at the endpoint.
    """
    return {k: v for k, v in payload.items() if k in PUBLIC_SURFACE_FIELDS}


def build_batch(
    records: List[RunRecord],
    host: str,
    source: str,
    batch_index: int,
    public_surface: bool = False,
) -> Dict[str, Any]:
    """Wrap finalized records in the batch envelope the ingest endpoint takes.

    ``batch_id`` is deterministic on (host, collected_at, batch_index) at the
    API side, mirroring ai_sessions, so a spool file replayed after a partial
    failure upserts rather than duplicating.
    """
    envelope: Dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "source": source,
        "host": host,
        "collectedAt": iso(utc_now()),
        "batchIndex": batch_index,
        "runs": [r.to_json(public_surface=public_surface) for r in records],
    }
    if public_surface:
        # The envelope names the host too, and a public Space must not report
        # our machine names. It still needs *a* host for batch identity, so it
        # sends its surface name rather than its hostname.
        envelope["host"] = source
        envelope["publicSurface"] = True
    else:
        envelope["agent"] = {
            "pid": os.getpid(),
            "platform": platform.platform(),
            "python": platform.python_version(),
        }
    return envelope


class _Clock:
    """Monotonic stopwatch paired with wall-clock stamps.

    Durations come from ``time.monotonic`` so an NTP correction mid-run cannot
    produce a negative latency, while the stored timestamps stay wall-clock so
    they line up with the rest of the telemetry.
    """

    __slots__ = ("_start_mono", "_start_wall")

    def __init__(self) -> None:
        self._start_mono = time.monotonic()
        self._start_wall = utc_now()

    @property
    def started_at(self) -> datetime:
        return self._start_wall

    def elapsed_ms(self) -> float:
        return (time.monotonic() - self._start_mono) * 1000.0

    def stamp(self) -> datetime:
        """Wall-clock time for 'now', derived from the monotonic delta."""
        from datetime import timedelta

        return self._start_wall + timedelta(milliseconds=self.elapsed_ms())
