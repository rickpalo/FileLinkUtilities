"""End-to-end F1 operator check, run by Blender:

    blender --background --factory-startup --python tests/smoke_f1.py

Registers the addon, runs filelink.scan_folder over the linkproj fixtures,
and asserts the JSON/CSV/DOT exports were written. Adds the BAT wheel to
sys.path to mirror what Blender does for an installed extension.
"""

import glob
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))  # so `import <foldername>` works
_bat = glob.glob(str(REPO_ROOT / "wheels" / "blender_asset_tracer-*.whl"))
if _bat:
    sys.path.insert(0, _bat[0])

PKG = REPO_ROOT.name
LINKPROJ = REPO_ROOT / "tests" / "fixtures" / "linkproj"


def main() -> int:
    import bpy

    addon = __import__(PKG)
    addon.register()
    try:
        res = bpy.ops.filelink.scan_folder("EXEC_DEFAULT", directory=str(LINKPROJ))
        assert res == {"FINISHED"}, res
        out = LINKPROJ / ".filelink"
        jsons = list(out.glob("linkmap_*.json"))
        csvs = list(out.glob("linkmap_*.csv"))
        dots = list(out.glob("linkmap_*.dot"))
        assert jsons and csvs and dots, f"missing exports in {out}"
        print("F1_SMOKE_OK", jsons[-1].name)
        # Clean up generated reports so the fixture dir stays pristine.
        for f in jsons + csvs + dots:
            os.remove(f)
        try:
            out.rmdir()
        except OSError:
            pass
        return 0
    except Exception:
        import traceback

        traceback.print_exc()
        print("F1_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
