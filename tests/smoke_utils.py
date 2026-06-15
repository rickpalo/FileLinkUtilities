"""End-to-end check for the UI plumbing added for the TODO batch:

    blender --background --factory-startup --python tests/smoke_utils.py

Verifies the Scene properties register, the Enable Debug Log toggle writes a
file, and each operator's tooltip description() returns a non-empty string for
its variants.
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


class _Props:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()
    checks = []
    try:
        sc = bpy.context.scene
        wm = bpy.context.window_manager
        checks.append(("scan_dir prop registered", hasattr(sc, "assetdoctor_scan_dir")))
        checks.append(("debug_log prop registered", hasattr(sc, "assetdoctor_debug_log")))
        checks.append(("op progress props registered",
                       hasattr(wm, "assetdoctor_op_active")
                       and hasattr(wm, "assetdoctor_op_progress")
                       and hasattr(wm, "assetdoctor_op_status")))

        # Toggle debug on (unsaved file -> temp dir) and confirm the file appears.
        sc.assetdoctor_debug_log = True
        log_path = pathlib.Path(bpy.app.tempdir) / "AssetDoctorDebugLog.txt"
        checks.append(("debug log file created", log_path.is_file()))
        sc.assetdoctor_debug_log = False

        # description() returns text for each variant.
        ml = __import__(f"{PKG}.ops.make_local", fromlist=["x"]).ASSETDOCTOR_OT_make_local
        md = __import__(f"{PKG}.ops.material_dedup", fromlist=["x"]).ASSETDOCTOR_OT_material_dedup
        orp = __import__(f"{PKG}.ops.orphans", fromlist=["x"]).ASSETDOCTOR_OT_scan_orphans
        d1 = ml.description(bpy.context, _Props(apply=True, mode="NEW_FILE"))
        d2 = ml.description(bpy.context, _Props(apply=True, mode="IN_PLACE"))
        d3 = ml.description(bpy.context, _Props(apply=False, mode="NEW_FILE"))
        d4 = md.description(bpy.context, _Props(apply=True))
        d5 = orp.description(bpy.context, _Props(purge_orphans=True))
        checks.append(("descriptions non-empty & distinct",
                       all(isinstance(d, str) and d for d in (d1, d2, d3, d4, d5))
                       and d1 != d2))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("UTILS_SMOKE_OK" if ok else "UTILS_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("UTILS_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
