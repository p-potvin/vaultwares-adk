"""Best-effort GPU + process sampling.

Every probe here is optional and failure-silent: a host with no NVIDIA driver,
no ``pynvml``, and no ``psutil`` still records runs, just without the hardware
columns. NVML is initialised once and reused — ``nvmlInit`` per call is a
measurable cost inside a tight embedding loop.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional

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


def _default_device_index() -> int:
    """Honour CUDA_VISIBLE_DEVICES so a pinned worker reports its own card.

    NVML indexes physical devices, whereas CUDA_VISIBLE_DEVICES remaps them, so
    the first entry of that list is the physical index of the process's cuda:0.
    """
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "").strip()
    if visible:
        first = visible.split(",")[0].strip()
        if first.isdigit():
            return int(first)
    return 0


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
    out = sample_gpu(index)
    out.update(sample_process())
    peak = torch_vram_peak_mb()
    if peak is not None:
        out["vram_peak_mb"] = peak
    return out
