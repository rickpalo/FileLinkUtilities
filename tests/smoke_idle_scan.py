"""Idle-scan prototype registration check, in Blender:

    blender --background --factory-startup --python tests/smoke_idle_scan.py

Confirms register()/unregister() wire up the FIRST app timer this add-on has
ever used without raising, that toggling the (default-off) preference is
respected by one manual timer tick, and that unregister() removes the timer —
nothing should survive a disable/reload of the add-on.
"""

import pathlib
import sys
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))
PKG = REPO_ROOT.name


def main():
    import bpy

    addon = __import__(PKG)
    idle_scan = __import__(f"{PKG}.ops.idle_scan", fromlist=["_idle_tick"])

    checks = []
    try:
        addon.register()
        checks.append(("timer registered on add-on register",
                       bpy.app.timers.is_registered(idle_scan._idle_tick)))

        wm = bpy.context.window_manager
        prefs = bpy.context.preferences.addons[PKG].preferences

        # Disabled by default — a manual tick must not touch the idle flags.
        checks.append(("disabled by default", prefs.idle_scan_enabled is False))
        wm.assetdoctor_idle_detected = False
        idle_scan._idle_tick()
        checks.append(("tick is a no-op while disabled",
                       wm.assetdoctor_idle_detected is False))

        # Enabled — a manual tick should set seconds-since-input without raising
        # (the real OS value; we only check it ran and produced a number).
        prefs.idle_scan_enabled = True
        idle_scan._idle_tick()
        checks.append(("tick sets idle_seconds while enabled",
                       isinstance(wm.assetdoctor_idle_seconds, float)))

        # Must never fire while a modal op is "running".
        wm.assetdoctor_op_active = True
        wm.assetdoctor_idle_detected = False
        prefs.idle_scan_threshold = 0  # would otherwise always be "idle"
        idle_scan._idle_tick()
        checks.append(("tick skips while a modal op is active",
                       wm.assetdoctor_idle_detected is False))
        wm.assetdoctor_op_active = False

        addon.unregister()
        checks.append(("timer removed on add-on unregister",
                       not bpy.app.timers.is_registered(idle_scan._idle_tick)))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("IDLE_SCAN_SMOKE_OK" if ok else "IDLE_SCAN_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("IDLE_SCAN_SMOKE_FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
