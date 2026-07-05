"""End-to-end F5 Profile Render check in Blender:

    blender --background --factory-startup --python tests/smoke_profile.py

Adds a camera, renders the current frame via the operator, and verifies a real
peak-RAM figure was captured and stored on the WindowManager.
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
        cam_data = bpy.data.cameras.new("Cam")
        cam = bpy.data.objects.new("Cam", cam_data)
        bpy.context.scene.collection.objects.link(cam)
        bpy.context.scene.camera = cam
        # tiny render to keep it fast
        bpy.context.scene.render.resolution_x = 16
        bpy.context.scene.render.resolution_y = 16

        res = bpy.ops.filelink.profile_render("EXEC_DEFAULT")
        wm = bpy.context.window_manager
        checks.append(("FINISHED", res == {"FINISHED"}))
        checks.append(("profiled RAM stored", bool(wm.filelink_profiled_ram)))
        checks.append(("profiled RAM is a real figure",
                       wm.filelink_profiled_ram not in ("", "unavailable")))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}  ({wm.filelink_profiled_ram})")
        print("PROFILE_SMOKE_OK" if ok else "PROFILE_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("PROFILE_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
