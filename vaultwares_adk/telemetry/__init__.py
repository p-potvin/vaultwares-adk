"""Model-run telemetry for every VaultWares surface that touches a model.

One record per invocation — local weights, HuggingFace inference/jobs/spaces,
NVIDIA NGC/NIM/NeMo, Ollama, ComfyUI — collected off the hot path by a daemon
worker, batched into NDJSON, and delivered to
``POST /api/telemetry/ai-runs/batches`` with a local spool fallback.

In-process instrumentation::

    from vaultwares_adk.telemetry import ModelRun

    with ModelRun(provider="huggingface", runtime="hf-inference",
                  model=name, task="chat", project="vault-inference") as run:
        response = client.chat.completions.create(**kwargs)
        run.usage(prompt=..., completion=...)

Out-of-process observation (ComfyUI, Ollama, HF jobs)::

    from vaultwares_adk.telemetry import record_run

    record_run(provider="comfyui", runtime="comfyui", model=ckpt,
               task="image", duration_ms=elapsed, status="ok")

This subpackage is stdlib-only. ``pynvml``/``psutil``/``torch`` are used when
already present and skipped otherwise, so importing it costs nothing.
"""

from .config import TelemetryConfig, configure, get_config
from .record import (
    SCHEMA_VERSION,
    STATUS_CANCELLED,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_REJECTED,
    STATUS_TIMEOUT,
    RunRecord,
    build_batch,
)
from .rollup import (
    DURATION_EDGES_MS,
    Bucket,
    RollupAggregator,
    build_rollup_batch,
    percentile_from_hist,
)
from .runs import ModelRun, instrument, record_run, usage_from_openai
from .spool import spool_backlog
from .worker import get_worker


def flush(timeout: float = 5.0) -> None:
    """Ship everything queued now. Call before a short-lived process exits."""
    get_worker().flush(timeout=timeout)


def shutdown(timeout: float = 5.0) -> None:
    """Flush and stop the worker thread. Also runs automatically at exit."""
    get_worker().shutdown(timeout=timeout)


def stats() -> dict:
    """Recorder counters plus spool backlog — for /health endpoints."""
    return get_worker().stats()


__all__ = [
    "ModelRun",
    "RunRecord",
    "RollupAggregator",
    "Bucket",
    "DURATION_EDGES_MS",
    "build_rollup_batch",
    "percentile_from_hist",
    "TelemetryConfig",
    "SCHEMA_VERSION",
    "STATUS_OK",
    "STATUS_ERROR",
    "STATUS_TIMEOUT",
    "STATUS_CANCELLED",
    "STATUS_REJECTED",
    "build_batch",
    "configure",
    "get_config",
    "flush",
    "instrument",
    "record_run",
    "shutdown",
    "spool_backlog",
    "stats",
    "usage_from_openai",
]
