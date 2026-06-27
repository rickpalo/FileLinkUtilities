"""End-to-end Analyze All / Find Duplicates check in Blender:

    blender --background --factory-startup --python tests/smoke_analyze_all.py

Regression test for docs/TODO.md Group 10 #34: ``ASSETDOCTOR_OT_find_duplicates``
used to subclass the already-registered ``ASSETDOCTOR_OT_analyze_all`` operator
directly, which corrupts Blender's RNA python-class binding for the FIRST-
registered one once the second is ALSO registered — ``analyze_all`` kept
returning {'FINISHED'} while silently running zero of its own steps. Calling
via 'EXEC_DEFAULT' bypasses invoke()/the modal event loop (drains the same
generator synchronously), so this is exercisable headless even though the
operator is normally driven modally from the UI.
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

    addon = __import__(PKG)
    addon.register()

    checks = []
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        wm = bpy.context.window_manager

        res = bpy.ops.assetdoctor.analyze_all("EXEC_DEFAULT")
        rows = list(wm.assetdoctor_analyze_steps)
        checks.append(("analyze_all FINISHED", res == {"FINISHED"}))
        checks.append(("analyze_all ran all 15 steps", len(rows) == 15))
        checks.append(("analyze_all stashed a result", bool(wm.assetdoctor_last_result)))

        res2 = bpy.ops.assetdoctor.find_duplicates("EXEC_DEFAULT")
        rows2 = list(wm.assetdoctor_analyze_steps)
        checks.append(("find_duplicates FINISHED", res2 == {"FINISHED"}))
        checks.append(("find_duplicates ran its 4 steps", len(rows2) == 4))

        # 2026-06-26: a THIRD operator built on the same _AnalyzeSequencerMixin
        # ("Find Flattenable Link Chains" + "Find Flattenable Characters"
        # merged into one trigger, docs/TODO.md #41) -- same RNA-corruption
        # regression class as analyze_all/find_duplicates, now with one more
        # registered class sharing the mixin.
        res2b = bpy.ops.assetdoctor.find_flattenable_links("EXEC_DEFAULT")
        rows2b = list(wm.assetdoctor_analyze_steps)
        checks.append(("find_flattenable_links FINISHED", res2b == {"FINISHED"}))
        checks.append(("find_flattenable_links ran its 2 steps", len(rows2b) == 2))

        # Re-run analyze_all AFTER both other sequencers have also been called
        # once — this is the exact corrupted-RNA-binding scenario: every
        # operator registered AND every one has been invoked at least once.
        res3 = bpy.ops.assetdoctor.analyze_all("EXEC_DEFAULT")
        rows3 = list(wm.assetdoctor_analyze_steps)
        checks.append(("analyze_all still works after the others ran",
                       res3 == {"FINISHED"} and len(rows3) == 15))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("ANALYZE_ALL_SMOKE_OK" if ok else "ANALYZE_ALL_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("ANALYZE_ALL_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
