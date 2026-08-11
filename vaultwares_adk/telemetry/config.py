"""Environment-driven configuration for the model-run recorder.

Everything is read once at import and can be overridden at runtime through
``telemetry.configure(...)``. Defaults are chosen so that dropping the recorder
into a project with no environment set up at all still works: it spools to a
local directory and never raises.
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional

# Mirrors the agent-ledger input tracker: spool lives beside the consuming repo
# unless an absolute location is pinned. D:\AiHistory\spool is the convention on
# the Windows hosts, but a relative fallback keeps Linux hosts working.
_DEFAULT_SPOOL = Path(os.environ.get("VW_RUNS_SPOOL_DIR") or r"D:\AiHistory\run-spool")


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class TelemetryConfig:
    """Immutable recorder settings. Replace via ``configure()``."""

    api_url: str = field(
        default_factory=lambda: _env(
            "VW_API_URL", "VW_PIPELINES_URL", default="https://api.vaultwares.ca"
        ).rstrip("/")
    )
    api_key: str = field(
        default_factory=lambda: _env("VW_TELEMETRY_API_KEY", "VW_PIPELINES_API_KEY")
    )
    ingest_path: str = "/api/telemetry/ai-runs/batches"

    spool_dir: Path = field(default_factory=lambda: _DEFAULT_SPOOL)
    rollup_ingest_path: str = "/api/telemetry/ai-runs/rollups/batches"
    host: str = field(default_factory=lambda: _env("VW_HOST", default=socket.gethostname()))

    # Project/service attribution. Consumers usually pass these per-run, but a
    # repo-wide default saves every call site from repeating itself.
    project: Optional[str] = field(default_factory=lambda: _env("VW_PROJECT") or None)
    service: Optional[str] = field(default_factory=lambda: _env("VW_SERVICE") or None)

    # Two cadences, deliberately separate.
    #
    # `drain_interval_s` moves runs off the in-memory queue into the local
    # rollup and onto disk. It is short because anything still on the queue is
    # lost if the process dies.
    #
    # `send_interval_s` is how often we talk to the API. Hourly: the durable
    # grain is the hourly rollup, so a faster send would multiply API writes
    # without making the dashboard any fresher.
    drain_interval_s: float = field(default_factory=lambda: _env_float("VW_RUNS_DRAIN_INTERVAL", 30.0))
    send_interval_s: float = field(default_factory=lambda: _env_float("VW_RUNS_SEND_INTERVAL", 3600.0))
    batch_max: int = field(default_factory=lambda: _env_int("VW_RUNS_BATCH_MAX", 200))

    # Ship per-run rows alongside the rollups. They are the short debugging
    # window; the rollup is the durable record. Turning this off on a very
    # chatty host keeps only the aggregate.
    send_raw_runs: bool = field(default_factory=lambda: _env_bool("VW_RUNS_SEND_RAW", True))

    # Bound the in-memory queue so a recorder that outruns the network sheds
    # load instead of growing without limit. Overflow is counted, not raised.
    queue_max: int = field(default_factory=lambda: _env_int("VW_RUNS_QUEUE_MAX", 10000))

    post_timeout_s: float = field(default_factory=lambda: _env_float("VW_RUNS_POST_TIMEOUT", 5.0))

    # GPU sampling costs an NVML round-trip per run; on by default because the
    # mandate asks for VRAM/util, but cheap to switch off on headless hosts.
    sample_gpu: bool = field(default_factory=lambda: _env_bool("VW_RUNS_SAMPLE_GPU", True))

    # Prompt content AND prompt hashes are both off by default. See
    # ModelRun.prompt() — a hash still correlates a user across records, so it
    # is not a safe default. Never enable this on a public surface.
    capture_prompt_text: bool = field(
        default_factory=lambda: _env_bool("VW_RUNS_CAPTURE_PROMPTS", False)
    )

    # Marks this process as serving the public (an HF Space). Records from a
    # public surface are stripped to a narrower field set before they leave,
    # because they describe strangers' usage, not ours — and they must not
    # describe our internal estate back to them either.
    public_surface: bool = field(
        default_factory=lambda: _env_bool("VW_RUNS_PUBLIC_SURFACE", False)
    )

    # Kill switch: makes every recorder call a no-op without touching call sites.
    enabled: bool = field(default_factory=lambda: _env_bool("VW_RUNS_ENABLED", True))

    # Emit recorder problems to stderr. Off by default — telemetry must never
    # be the noisiest thing in an inference log.
    debug: bool = field(default_factory=lambda: _env_bool("VW_RUNS_DEBUG", False))

    @property
    def ingest_url(self) -> str:
        return f"{self.api_url}{self.ingest_path}"

    @property
    def rollup_ingest_url(self) -> str:
        return f"{self.api_url}{self.rollup_ingest_path}"


_config = TelemetryConfig()


def get_config() -> TelemetryConfig:
    return _config


def configure(**overrides) -> TelemetryConfig:
    """Override settings at runtime.

    Call before the first recorded run where possible; the worker reads the
    config on each flush, so later changes still take effect for the next batch
    but will not retroactively move already-spooled files.
    """
    global _config
    unknown = set(overrides) - {f.name for f in TelemetryConfig.__dataclass_fields__.values()}
    if unknown:
        raise TypeError(f"unknown telemetry config field(s): {', '.join(sorted(unknown))}")
    if "spool_dir" in overrides and overrides["spool_dir"] is not None:
        overrides["spool_dir"] = Path(overrides["spool_dir"])
    if "api_url" in overrides and overrides["api_url"]:
        overrides["api_url"] = str(overrides["api_url"]).rstrip("/")
    _config = replace(_config, **overrides)
    return _config
