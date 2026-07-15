"""Open-in-new-Blender operator smoke test:

    blender --background --factory-startup --python tests/smoke_open_external.py

Confirms FILELINK_OT_open_blend_external registers and REFUSES a non-existent /
empty path (so a bad "fix at source" link can't spawn a broken Blender). The
happy path actually launches a GUI Blender, so it isn't exercised headless —
Blender surfaces an operator ERROR report to a direct bpy.ops caller as a
RuntimeError, which is how the rejection is detected here.
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


def _rejects(filepath) -> bool:
    import bpy
    try:
        bpy.ops.filelink.open_blend_external(filepath=filepath)
    except RuntimeError:
        return True   # ERROR report -> rejected, no launch
    return False


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()
    checks = []
    try:
        checks.append(("operator registered",
                       hasattr(bpy.types, "FILELINK_OT_open_blend_external")))
        checks.append(("non-existent path rejected",
                       _rejects("E:/no/such/file_zzz_qwerty.blend")))
        checks.append(("empty path rejected", _rejects("")))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("OPEN_EXTERNAL_SMOKE_OK" if ok else "OPEN_EXTERNAL_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("OPEN_EXTERNAL_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
