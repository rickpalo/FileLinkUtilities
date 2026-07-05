"""Idle-scan FEASIBILITY PROTOTYPE (Batch E).

Proves the OS-idle poll (``core.idle.seconds_since_input``) works from inside
Blender via a ``bpy.app.timers`` callback — without freezing the UI or
crashing on file load/reload. It does NOT trigger any scan; wiring a real
idle-triggered scan is separate, larger follow-up work (an offline BAT scan
blocks the main thread, so it would need to run chunked/modal like every other
heavy op here, and must never start while a render is running). See
``docs/TODO.md`` "BATCH E".

Gated behind ``FileLinkPreferences.idle_scan_enabled`` (default OFF). This
is the FIRST app timer File & Link Utilities registers, so ``unregister_idle_timer()``
must run on add-on unregister — nothing should survive a disable/reload.
"""

from __future__ import annotations

_TICK_SECONDS = 5.0


def _idle_tick():
    """One poll, rescheduled every ``_TICK_SECONDS``. Wrapped in a broad
    except — a prototype timer must never take Blender down with it, and a
    timer that raises is permanently dropped by Blender instead of retried."""
    import bpy

    from ..core.idle import is_idle, seconds_since_input
    from ..prefs import get_prefs

    try:
        prefs = get_prefs()
        wm = bpy.context.window_manager
        if prefs is None or wm is None or not prefs.idle_scan_enabled:
            return _TICK_SECONDS
        if getattr(wm, "filelink_op_active", False):
            return _TICK_SECONDS  # never fire while a modal scan/apply is running

        secs = seconds_since_input()
        wm.filelink_idle_seconds = secs if secs is not None else 0.0
        wm.filelink_idle_detected = is_idle(secs, prefs.idle_scan_threshold)
    except Exception:
        pass
    return _TICK_SECONDS


def register_idle_timer() -> None:
    import bpy

    if not bpy.app.timers.is_registered(_idle_tick):
        # persistent=True: this is an addon/preferences-level prototype, not
        # scene data, so it should survive File > New / Open, not just appends.
        bpy.app.timers.register(_idle_tick, first_interval=_TICK_SECONDS, persistent=True)


def unregister_idle_timer() -> None:
    import bpy

    if bpy.app.timers.is_registered(_idle_tick):
        bpy.app.timers.unregister(_idle_tick)


__all__ = ["register_idle_timer", "unregister_idle_timer"]
