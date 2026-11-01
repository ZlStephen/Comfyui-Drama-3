"""Refuse to enter the R2T2 native CUDA backend when it cannot run here.

The shipped r2t2-runtime/backends/ggml-cuda.dll is a CUDA 12.8 build whose
kernels cover sm_120 only (Blackwell). On an sm_89 device (RTX 4090) the
llama.cpp CUDA backend fails with

    CUDA error: no kernel image is available for execution on the device
      current device: 0, in function ggml_cuda_kernel_can_use_pdl
      cudaFuncGetAttributes(&attr, kernel)

and then calls abort(). That is a C-level abort: it kills the whole ComfyUI
process with "Fatal Python error: Aborted", and no Python-level try/except
can catch it. The only reliable guard is to check BEFORE the first native
call.

The check is deliberately conservative:
  * an unknown device architecture  -> allowed (the guard stays silent)
  * an unreadable / arch-less binary -> allowed (the guard stays silent)
  * a known device architecture that the binary provably does not cover
    -> refuse, with a message naming the alternatives
Set DRAMA_R2T2_ALLOW_UNSUPPORTED_ARCH=1 to bypass it.
"""
from __future__ import annotations

import ctypes
import os
import re
from pathlib import Path

# CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MAJOR / _MINOR
_ATTR_CC_MAJOR = 75
_ATTR_CC_MINOR = 76

_ARCH_RE = re.compile(rb"sm_(\d{2,3})[a-z]?\b")


def backend_archs(dll: Path) -> set[int]:
    """Compute capabilities the CUDA backend carries kernels for."""
    try:
        data = dll.read_bytes()
    except OSError:
        return set()
    return {int(m) for m in _ARCH_RE.findall(data)}


def device_arch() -> tuple[int, int] | None:
    """(major, minor) of the active CUDA device, or None if unknown."""
    try:
        import torch

        if torch.cuda.is_available():
            major, minor = torch.cuda.get_device_capability(0)
            return int(major), int(minor)
    except Exception:
        pass
    try:  # driver API, independent of torch
        cuda = ctypes.CDLL("nvcuda.dll")
        if cuda.cuInit(0) != 0:
            return None
        dev = ctypes.c_int()
        if cuda.cuDeviceGet(ctypes.byref(dev), 0) != 0:
            return None
        major = ctypes.c_int()
        minor = ctypes.c_int()
        if cuda.cuDeviceGetAttribute(ctypes.byref(major), _ATTR_CC_MAJOR, dev) != 0:
            return None
        if cuda.cuDeviceGetAttribute(ctypes.byref(minor), _ATTR_CC_MINOR, dev) != 0:
            return None
        return major.value, minor.value
    except Exception:
        return None


def check(runtime_dir: Path) -> str | None:
    """Return a refusal message, or None when the backend may be used."""
    if os.environ.get("DRAMA_R2T2_ALLOW_UNSUPPORTED_ARCH", "").strip() not in ("", "0", "false", "False"):
        return None
    dll = Path(runtime_dir) / "backends" / "ggml-cuda.dll"
    if not dll.is_file():
        return None
    archs = backend_archs(dll)
    if not archs:
        return None  # cannot prove anything - stay silent
    dev = device_arch()
    if dev is None:
        return None
    cap = dev[0] * 10 + dev[1]
    if cap in archs:
        return None
    have = ", ".join(f"sm_{a}" for a in sorted(archs))
    return (
        f"Confucius R2T2 native CUDA backend cannot run on this GPU.\n"
        f"  device      : compute capability {dev[0]}.{dev[1]} (sm_{cap})\n"
        f"  backend     : {dll.name} carries kernels for {have} only\n"
        f"  reason      : llama.cpp aborts the process with\n"
        f"                'CUDA error: no kernel image is available for execution on the device'\n"
        f"                which is a C-level abort that kills ComfyUI itself.\n"
        f"  use instead : T8DramaTranscribe (Qwen3-ASR) for transcription, and\n"
        f"                T8DramaAlign (Qwen3 forced aligner) for word timings.\n"
        f"  override    : set DRAMA_R2T2_ALLOW_UNSUPPORTED_ARCH=1 to try anyway."
    )
