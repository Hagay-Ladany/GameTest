"""
Hardware profile helpers.

Detects the active GPU and builds the hardware_profile dict that is
embedded in every AI request metadata log. Falls back gracefully when
PyTorch / CUDA are not available (e.g. CI environments).
"""
from __future__ import annotations

TARGET_GPU_NAME = "RTX 5070 Ti"


def get_hardware_profile(batch_mode: bool = True) -> dict:
    """
    Return a hardware_profile dict describing the current inference device.

    Example output::

        {
            "gpu": "NVIDIA GeForce RTX 5070 Ti",
            "vram_total_gb": 16.0,
            "batch_mode": true,
            "cuda_available": true,
            "device_index": 0
        }
    """
    profile: dict = {
        "gpu": TARGET_GPU_NAME,
        "vram_total_gb": None,
        "batch_mode": batch_mode,
        "cuda_available": False,
        "device_index": 0,
    }

    try:
        import torch  # optional dependency – not required at import time

        if torch.cuda.is_available():
            dev = torch.cuda.current_device()
            props = torch.cuda.get_device_properties(dev)
            profile["gpu"] = props.name
            profile["vram_total_gb"] = round(props.total_memory / 1024**3, 2)
            profile["cuda_available"] = True
            profile["device_index"] = dev
    except ImportError:
        pass  # torch not installed; use defaults

    return profile
