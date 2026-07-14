"""Progressive-disclosure classifier smoke test:

    blender --background --factory-startup --python tests/smoke_progressive.py

Covers ui.panels._check_status (not_run/clean/findings from real WM counts) and
_gate (clean checks counted + hidden unless the phase tally is expanded). The
panel rendering itself needs a UI; this locks the decision logic that drives it.
"""

import glob
import pathlib
import sys
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))
_bat = glob.glob(str(REPO_ROOT / "wheels" / "blender_asset_tracer-*.whl"))
if _bat:
    sys.path.insert(0, _bat[0])
PKG = REPO_ROOT.name


def main():
    import bpy
    from importlib import import_module

    addon = __import__(PKG)
    addon.register()
    panels = import_module(f"{PKG}.ui.panels")

    checks = []
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        wm = bpy.context.window_manager
        st = panels._check_status

        # Reconnectable: not run -> clean (scanned, empty) -> findings (a row).
        checks.append(("reconnect not_run", st(wm, "find_reconnectable") == "not_run"))
        wm.filelink_missing_scanned = True
        checks.append(("reconnect clean", st(wm, "find_reconnectable") == "clean"))
        wm.filelink_missing_blocks.add()
        checks.append(("reconnect findings", st(wm, "find_reconnectable") == "findings"))

        # Deform: same ladder via its own flags.
        checks.append(("deform not_run", st(wm, "check_deform") == "not_run"))
        wm.filelink_deform_scanned = True
        checks.append(("deform clean", st(wm, "check_deform") == "clean"))
        wm.filelink_deform_rows.add()
        checks.append(("deform findings", st(wm, "check_deform") == "findings"))

        # Broken links: "has run" is the stashed f7links report string.
        checks.append(("broken not_run", st(wm, "find_broken_links") == "not_run"))
        wm.filelink_rep_f7links = "ran"
        checks.append(("broken clean", st(wm, "find_broken_links") == "clean"))
        wm.filelink_broken_libs.add()
        checks.append(("broken findings", st(wm, "find_broken_links") == "findings"))

        # Unknown / always-shown key.
        checks.append(("unknown key always findings", st(wm, "make_local") == "findings"))

        # _gate: a clean check counts and is hidden while collapsed, shown while expanded.
        wm.filelink_deform_rows.clear()  # deform back to clean
        counter = [0]
        drew_collapsed = panels._gate(wm, "check_deform", show_passed=False, counter=counter)
        checks.append(("clean gated: counted", counter[0] == 1))
        checks.append(("clean gated: hidden when collapsed", drew_collapsed is False))
        counter = [0]
        drew_expanded = panels._gate(wm, "check_deform", show_passed=True, counter=counter)
        checks.append(("clean gated: shown when expanded", drew_expanded is True and counter[0] == 1))
        # A findings check always draws and never counts toward "passed".
        wm.filelink_deform_rows.add()
        counter = [0]
        drew_findings = panels._gate(wm, "check_deform", show_passed=False, counter=counter)
        checks.append(("findings always drawn, not counted",
                       drew_findings is True and counter[0] == 0))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("PROGRESSIVE_SMOKE_OK" if ok else "PROGRESSIVE_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("PROGRESSIVE_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
