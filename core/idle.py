"""Feasibility prototype for an idle-triggered scan (Batch E).

Blender has no native "the user went idle" event, so this polls the OS
directly. Windows-only for now (``GetLastInputInfo`` via ``ctypes``) — the only
platform this add-on is developed/tested on; other platforms report ``None``
(treated as "unknown", never as idle).

This module is intentionally tiny and decision-only: it doesn't touch ``bpy``,
run any scan, or know what "idle" should trigger. See ``ops.idle_scan`` for the
one app-timer that polls it, and ``docs/TODO.md`` "BATCH E" for why actually
wiring a real idle-triggered scan is separate follow-up work — an offline BAT
scan blocks the main thread, so it would need to run chunked/modal like every
other heavy op here, and must never start while a render is running.
"""

from __future__ import annotations

import sys


def seconds_since_input() -> float | None:
    """Seconds since the last system-wide keyboard/mouse input, or ``None`` if
    unavailable (non-Windows, or the OS call failed). Callers must treat
    ``None`` as "unknown" — never as "idle"."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        class _LastInputInfo(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        info = _LastInputInfo()
        info.cbSize = ctypes.sizeof(_LastInputInfo)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):  # type: ignore[attr-defined]
            return None
        millis = ctypes.windll.kernel32.GetTickCount() - info.dwTime  # type: ignore[attr-defined]
        # GetTickCount wraps every ~49.7 days; clamp instead of reporting a
        # bogus negative idle time across that wrap.
        return max(0.0, millis / 1000.0)
    except Exception:
        return None


def is_idle(seconds_since: float | None, threshold: float) -> bool:
    """True once ``seconds_since`` is known and has reached ``threshold``."""
    return seconds_since is not None and seconds_since >= threshold


__all__ = ["seconds_since_input", "is_idle"]
