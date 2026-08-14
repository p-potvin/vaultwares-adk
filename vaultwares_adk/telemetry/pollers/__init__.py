"""Pollers for model runtimes we do not own.

ComfyUI and Ollama are third-party servers with no hook to wrap, so their runs
are observed from outside rather than instrumented from within. Each module
documents what it can and cannot see; the honest summary is:

* ComfyUI keeps a full execution history, so the poller sees every job whoever
  submitted it.
* Ollama keeps nothing, so per-run KPIs only exist for callers that route
  through OllamaClient / record_response. The /api/ps sampler covers the rest
  with residency and VRAM, which is genuinely less -- and is recorded as
  task="residency" rather than dressed up as invocations.
"""

from . import comfyui, ollama
from .runner import PollerLoop, poll_once

__all__ = ["comfyui", "ollama", "PollerLoop", "poll_once"]
