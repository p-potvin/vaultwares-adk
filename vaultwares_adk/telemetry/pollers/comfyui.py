"""ComfyUI telemetry, by polling /history.

ComfyUI is not our code and there is no hook to wrap, but it keeps a complete
history of executed prompts including per-stage timestamps, so a poller sees
every job regardless of which client submitted it. That matters: jobs arrive
from vault-flows, from the API proxy, and from the desktop UI, and only the
server sees all three.

DEDUPE. /history returns the whole retained history on every call, so the same
prompt would be recorded on every poll. The run id is derived deterministically
from the prompt id, which makes a re-send a no-op at the API (ingest is
ON CONFLICT DO NOTHING) even if the local cursor is lost -- the cursor is an
optimisation, not the correctness mechanism.

The response shapes here are read defensively: this is a third-party API we do
not control, and a schema change should cost us a field, not a crash.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.error import URLError
from urllib.request import Request, urlopen

from ..record import RunRecord
from ..runs import record_run

DEFAULT_BASE_URL = "http://127.0.0.1:8188"

# Class types worth reading numbers off. ComfyUI graphs are arbitrary, so this
# is a best-effort extraction rather than a schema.
_SAMPLER_TYPES = {"KSampler", "KSamplerAdvanced", "SamplerCustom", "KSamplerSelect"}
_CHECKPOINT_TYPES = {
    "CheckpointLoaderSimple", "CheckpointLoader", "UNETLoader",
    "DiffusersLoader", "UnetLoaderGGUF",
}
_LORA_TYPES = {"LoraLoader", "LoraLoaderModelOnly"}
_LATENT_TYPES = {"EmptyLatentImage", "EmptySD3LatentImage", "EmptyLatentImagePresets"}


def run_id_for(prompt_id: str) -> str:
    """Deterministic id so a replayed history entry cannot double-insert."""
    return "comfy-" + hashlib.sha256(str(prompt_id).encode("utf-8")).hexdigest()[:26]


def _get_json(url: str, timeout: float = 10.0) -> Optional[Any]:
    try:
        with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError, OSError):
        return None


def fetch_history(base_url: str = DEFAULT_BASE_URL, timeout: float = 10.0) -> Dict[str, Any]:
    payload = _get_json(f"{base_url.rstrip('/')}/history", timeout)
    return payload if isinstance(payload, dict) else {}


def fetch_system_stats(base_url: str = DEFAULT_BASE_URL, timeout: float = 5.0) -> Dict[str, Any]:
    payload = _get_json(f"{base_url.rstrip('/')}/system_stats", timeout)
    return payload if isinstance(payload, dict) else {}


def _nodes_of(entry: Dict[str, Any]) -> Dict[str, Any]:
    """The workflow graph, which sits at index 2 of the `prompt` tuple."""
    prompt = entry.get("prompt")
    if isinstance(prompt, list) and len(prompt) > 2 and isinstance(prompt[2], dict):
        return prompt[2]
    return {}


def _timestamps(entry: Dict[str, Any]) -> Dict[str, float]:
    """Pull execution_start / terminal timestamps out of status.messages."""
    out: Dict[str, float] = {}
    status = entry.get("status")
    if not isinstance(status, dict):
        return out
    for message in status.get("messages") or []:
        if not (isinstance(message, (list, tuple)) and len(message) >= 2):
            continue
        name, data = message[0], message[1]
        if not isinstance(data, dict):
            continue
        stamp = data.get("timestamp")
        if isinstance(stamp, (int, float)):
            out[str(name)] = float(stamp)
    return out


def _graph_metrics(nodes: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    lora_count = 0
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            inputs = {}

        if class_type in _CHECKPOINT_TYPES:
            name = inputs.get("ckpt_name") or inputs.get("unet_name") or inputs.get("model_name")
            if isinstance(name, str):
                out.setdefault("model", name)
        elif class_type in _SAMPLER_TYPES:
            for key, field in (("steps", "steps"), ("cfg", "cfg_scale"),
                               ("sampler_name", "sampler"), ("scheduler", "scheduler"),
                               ("seed", "seed"), ("noise_seed", "seed")):
                value = inputs.get(key)
                # Wired inputs arrive as ["node_id", slot] rather than a value.
                if value is not None and not isinstance(value, list):
                    out.setdefault(field, value)
        elif class_type in _LORA_TYPES:
            lora_count += 1
        elif class_type in _LATENT_TYPES:
            for key in ("width", "height"):
                value = inputs.get(key)
                if isinstance(value, (int, float)):
                    out.setdefault(key, int(value))

    if lora_count:
        out["lora_count"] = lora_count
    return out


def _output_metrics(entry: Dict[str, Any]) -> Dict[str, Any]:
    images = 0
    for node_output in (entry.get("outputs") or {}).values():
        if isinstance(node_output, dict):
            for key in ("images", "gifs", "videos"):
                value = node_output.get(key)
                if isinstance(value, list):
                    images += len(value)
    return {"image_count": images} if images else {}


def record_from_history_entry(
    prompt_id: str,
    entry: Dict[str, Any],
    *,
    project: Optional[str] = None,
    gpu_name: Optional[str] = None,
) -> Optional[RunRecord]:
    """Turn one /history entry into a run. Returns None if still running."""
    status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
    if not status.get("completed", False) and not status.get("status_str"):
        return None  # still executing; it will be picked up on a later poll

    stamps = _timestamps(entry)
    start = stamps.get("execution_start")
    end = (
        stamps.get("execution_success")
        or stamps.get("execution_error")
        or stamps.get("execution_interrupted")
    )
    duration_ms = round(end - start, 3) if (start and end and end >= start) else None

    status_str = str(status.get("status_str") or "").lower()
    if "error" in status_str:
        run_status, error_class = "error", "ComfyExecutionError"
    elif "interrupt" in status_str or "cancel" in status_str:
        run_status, error_class = "cancelled", None
    else:
        run_status, error_class = "ok", None

    fields: Dict[str, Any] = {
        "model": "unknown",
        **_graph_metrics(_nodes_of(entry)),
        **_output_metrics(entry),
    }
    if gpu_name:
        fields.setdefault("gpu_name", gpu_name)

    return record_run(
        run_id=run_id_for(prompt_id),
        provider="comfyui",
        runtime="comfyui",
        task="image",
        project=project,
        service="comfyui-poller",
        backend="comfyui",
        status=run_status,
        error_class=error_class,
        duration_ms=duration_ms,
        # Local GPU: a real zero rather than an unmeasured cost.
        cost_usd=0.0,
        priced_exactly=True,
        is_free=True,
        comfy_prompt_id=str(prompt_id),
        **fields,
    )


def poll_history(
    base_url: str = DEFAULT_BASE_URL,
    *,
    seen: Optional[Set[str]] = None,
    project: Optional[str] = None,
    limit: int = 500,
) -> List[RunRecord]:
    """Record every completed prompt not already seen.

    ``seen`` is an optional cursor the caller keeps between polls. Losing it is
    harmless -- the deterministic run id makes a resend a no-op at the API --
    it only saves the round trip.
    """
    history = fetch_history(base_url)
    if not history:
        return []

    stats = fetch_system_stats(base_url)
    gpu_name = None
    devices = stats.get("devices") if isinstance(stats, dict) else None
    if isinstance(devices, list) and devices and isinstance(devices[0], dict):
        gpu_name = devices[0].get("name")

    records: List[RunRecord] = []
    for prompt_id, entry in list(history.items())[:limit]:
        if seen is not None and prompt_id in seen:
            continue
        if not isinstance(entry, dict):
            continue
        record = record_from_history_entry(
            prompt_id, entry, project=project, gpu_name=gpu_name
        )
        if record is not None:
            records.append(record)
            if seen is not None:
                seen.add(prompt_id)
    return records
