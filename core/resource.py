"""Memory/disk estimation for the F5 Resource Analyzer. bpy-free; ops supplies
plain dicts extracted from datablocks.

All RAM/VRAM figures are **estimates** (Blender exposes no exact per-datablock
byte counts) and are labeled as such in the UI. Disk figures are accurate where
a file/packed size is available.

Model (documented, deliberately simple — good for ranking the heavy hitters):
  * Images:  RAM ≈ width*height*(depth_bits/8)  [depth is Blender's bits-per-pixel,
             so 8-bit RGBA=32, 32-bit float RGBA=128]. VRAM ≈ RAM * 4/3 (mipmaps).
  * Meshes:  RAM from element counts via per-element constants below.
             VRAM ≈ loops * GPU vertex stride (pos+normal+uv ~ 32 B).
"""

from __future__ import annotations

import sys

# Rough per-element mesh RAM constants (bytes). Approximate by design.
_MESH_VERT_B = 40
_MESH_EDGE_B = 16
_MESH_LOOP_B = 24
_MESH_POLY_B = 16
_MESH_GPU_STRIDE = 32  # per-loop GPU vertex (position + normal + one UV)
_MIPMAP_FACTOR = 4 / 3


def image_estimate(info: dict) -> dict:
    """info: {width, height, depth(bits/px)}. Returns {ram, vram} bytes."""
    px = max(0, info.get("width", 0)) * max(0, info.get("height", 0))
    ram = px * (info.get("depth", 0) // 8)
    return {"ram": ram, "vram": int(ram * _MIPMAP_FACTOR)}


def mesh_estimate(info: dict) -> dict:
    """info: {verts, edges, loops, polys}. Returns {ram, vram} bytes."""
    ram = (
        info.get("verts", 0) * _MESH_VERT_B
        + info.get("edges", 0) * _MESH_EDGE_B
        + info.get("loops", 0) * _MESH_LOOP_B
        + info.get("polys", 0) * _MESH_POLY_B
    )
    return {"ram": ram, "vram": info.get("loops", 0) * _MESH_GPU_STRIDE}


def peak_process_ram_bytes() -> int:
    """Best-effort REAL peak resident memory of this process, in bytes (0 if
    unknown). Used by F5 'Profile Render' to report actual peak RAM after a
    render, complementing the estimates. OS-level; no bpy."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class _PMC(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD
            ]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

            counters = _PMC()
            counters.cb = ctypes.sizeof(_PMC)
            handle = kernel32.GetCurrentProcess()
            if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return int(counters.PeakWorkingSetSize)
        except Exception:
            return 0
        return 0
    try:
        import resource as _res

        maxrss = _res.getrusage(_res.RUSAGE_SELF).ru_maxrss
        # Linux reports KB, macOS reports bytes.
        return int(maxrss * (1024 if sys.platform.startswith("linux") else 1))
    except Exception:
        return 0


def human_bytes(n: int) -> str:
    """Human-readable size, e.g. 1536 -> '1.5 KB'."""
    n = float(max(0, n))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
