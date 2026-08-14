"""Best-effort GPU + process sampling.

Every probe here is optional and failure-silent: a host with no NVIDIA driver,
no ``pynvml``, and no ``psutil`` still records runs, just without the hardware
columns. NVML is initialised once and reused — ``nvmlInit`` per call is a
measurable cost inside a tight embedding loop.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional, Tuple

_nvml: Any = None
_nvml_state = "unloaded"  # unloaded | ready | unavailable
_lock = threading.Lock()


def _load_nvml() -> Any:
    """Import and init NVML once. Returns the module, or None if unavailable."""
    global _nvml, _nvml_state
    if _nvml_state != "unloaded":
        return _nvml
    with _lock:
        if _nvml_state != "unloaded":
            return _nvml
        try:
            try:
                import pynvml  # type: ignore
            except ImportError:  # newer driver packaging
                from nvidia_ml_py import pynvml  # type: ignore
            pynvml.nvmlInit()
            _nvml = pynvml
            _nvml_state = "ready"
        except Exception:
            _nvml = None
            _nvml_state = "unavailable"
    return _nvml


def _decode(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def sample_gpu(index: Optional[int] = None) -> Dict[str, Any]:
    """Snapshot one GPU. Defaults to the device CUDA would pick.

    Returns ``{}`` when NVML is unavailable so callers can splat it
    unconditionally into a record.
    """
    nvml = _load_nvml()
    if nvml is None:
        return {}

    if index is None:
        index = _default_device_index()

    out: Dict[str, Any] = {}
    try:
        handle = nvml.nvmlDeviceGetHandleByIndex(index)
    except Exception:
        return {}

    out["gpu_index"] = index
    try:
        out["gpu_name"] = _decode(nvml.nvmlDeviceGetName(handle))
    except Exception:
        pass
    try:
        mem = nvml.nvmlDeviceGetMemoryInfo(handle)
        out["vram_used_mb"] = round(mem.used / 1048576, 1)
        out["vram_total_mb"] = round(mem.total / 1048576, 1)
    except Exception:
        pass
    try:
        util = nvml.nvmlDeviceGetUtilizationRates(handle)
        out["gpu_util_pct"] = float(util.gpu)
    except Exception:
        pass
    try:
        out["gpu_temp_c"] = float(nvml.nvmlDeviceGetTemperature(handle, nvml.NVML_TEMPERATURE_GPU))
    except Exception:
        pass
    try:
        out["gpu_power_w"] = round(nvml.nvmlDeviceGetPowerUsage(handle) / 1000.0, 2)
    except Exception:
        pass
    return out


def device_count() -> int:
    nvml = _load_nvml()
    if nvml is None:
        return 0
    try:
        return int(nvml.nvmlDeviceGetCount())
    except Exception:
        return 0


def _visible_devices() -> Optional[list]:
    """CUDA_VISIBLE_DEVICES as physical NVML indices, if set and numeric."""
    raw = os.environ.get("CUDA_VISIBLE_DEVICES", "").strip()
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return [int(p) for p in parts if p.isdigit()] or None


def resolve_device_index() -> Tuple[Optional[int], str]:
    """Work out which physical GPU a run actually used.

    Returns ``(index, how)`` where ``how`` records the confidence, because on a
    multi-GPU host guessing wrong is worse than admitting ignorance: this box
    has a 12 GB 3060 at index 0 and a 6 GB 2060 at index 1, so attributing a
    2060 run to device 0 would report more than double its real VRAM ceiling.

    Order of preference:
      torch's current device (authoritative for in-process runs)
      -> CUDA_VISIBLE_DEVICES (authoritative for a pinned worker)
      -> the only device present
      -> the busiest device, flagged as inferred
    """
    import sys

    visible = _visible_devices()

    torch = sys.modules.get("torch")
    if torch is not None:
        try:
            if torch.cuda.is_available():
                logical = int(torch.cuda.current_device())
                # torch indexes the *visible* subset; map back to physical.
                if visible and logical < len(visible):
                    return visible[logical], "torch"
                return logical, "torch"
        except Exception:
            pass

    if visible:
        return visible[0], "cuda_visible_devices"

    count = device_count()
    if count == 1:
        return 0, "only_device"
    if count == 0:
        return None, "no_nvml"

    busiest = _busiest_device(count)
    return busiest, "inferred_busiest"


def _busiest_device(count: int) -> Optional[int]:
    """The device with the most memory in use — a guess, labelled as one."""
    nvml = _load_nvml()
    if nvml is None:
        return None
    best_index, best_used = None, -1
    for index in range(count):
        try:
            handle = nvml.nvmlDeviceGetHandleByIndex(index)
            used = nvml.nvmlDeviceGetMemoryInfo(handle).used
        except Exception:
            continue
        if used > best_used:
            best_index, best_used = index, used
    return best_index


def _default_device_index() -> int:
    index, _ = resolve_device_index()
    return index if index is not None else 0


def torch_vram_peak_mb() -> Optional[float]:
    """Peak VRAM this process actually allocated, if torch is already loaded.

    Only reads torch when it is *already* imported — importing torch from a
    telemetry probe would add seconds of startup to a process that may not use
    it at all.
    """
    import sys

    torch = sys.modules.get("torch")
    if torch is None:
        return None
    try:
        if not torch.cuda.is_available():
            return None
        return round(torch.cuda.max_memory_allocated() / 1048576, 1)
    except Exception:
        return None


def reset_torch_peak() -> None:
    """Zero torch's peak-memory counter so the next run measures only itself."""
    import sys

    torch = sys.modules.get("torch")
    if torch is None:
        return
    try:
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except Exception:
        pass


def probe_status() -> Dict[str, Any]:
    """Which hardware probes are actually working.

    Exposed through telemetry.stats() because the failure mode here is silent:
    without nvidia-ml-py every VRAM/GPU column is null, which is
    indistinguishable from a host that genuinely has no GPU. This ran for a
    while on a two-GPU box collecting nothing before anyone noticed.
    """
    try:
        import psutil  # type: ignore  # noqa: F401

        has_psutil = True
    except ImportError:
        has_psutil = False

    count = device_count()
    index, how = resolve_device_index()
    return {
        "nvml": _load_nvml() is not None,
        "psutil": has_psutil,
        "gpu_count": count,
        "gpu_index": index,
        "gpu_attribution": how,
    }


def sample_process() -> Dict[str, Any]:
    """Process CPU + RSS via psutil when present."""
    try:
        import psutil  # type: ignore
    except ImportError:
        return {}
    try:
        proc = psutil.Process()
        return {
            # interval=None returns the delta since this process object's last
            # call, which is what we want — a blocking interval would stall the
            # inference thread.
            "cpu_pct": proc.cpu_percent(interval=None),
            "rss_mb": round(proc.memory_info().rss / 1048576, 1),
        }
    except Exception:
        return {}


def sample_all(index: Optional[int] = None) -> Dict[str, Any]:
    how = "explicit"
    if index is None:
        index, how = resolve_device_index()

    out = sample_gpu(index)
    if out:
        count = device_count()
        if count > 1:
            # Which card a number came from matters once the host is mixed:
            # 12 GB and 6 GB cards produce very different VRAM headroom, and a
            # reader comparing them needs to know the attribution was a guess.
            out["gpu_count"] = count
            out["gpu_attribution"] = how
    out.update(sample_process())
    peak = torch_vram_peak_mb()
    if peak is not None:
        out["vram_peak_mb"] = peak
    return out
