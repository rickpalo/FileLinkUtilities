"""docs/TODO.md #21 (2026-06-27): Geometry dedup now clusters local+linked
meshes (previously local-only) -- verifies, via a REAL linked mesh (not just
the synthetic dicts core/test_geometry_dedup.py already covers), that the
default "prefer local" behavior clusters them but never touches/removes the
linked one; only the linked mesh's LOCAL users get repointed.

    blender --background --factory-startup --python tests/smoke_geo_linked.py

Note: this can't exercise the geometry_keep_preference="LINKED" prefs flip --
every smoke test in this project calls register() manually, which never
populates bpy.context.preferences.addons[pkg] (confirmed: smoke_idle_scan.py
fails on exactly this for an unrelated, pre-existing reason), so
ops.get_prefs() always returns None / the LOCAL default here. The flip is
covered where it belongs instead: core/test_geometry_dedup.py (prefs-free).
"""

import glob
import os
import pathlib
import sys
import tempfile
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))
_bat = glob.glob(str(REPO_ROOT / "wheels" / "blender_asset_tracer-*.whl"))
if _bat:
    sys.path.insert(0, _bat[0])
PKG = REPO_ROOT.name

TRI = ([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()

    checks = []
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        donor_path = os.path.join(tempfile.mkdtemp(), "donor.blend")

        me = bpy.data.meshes.new("Shared")
        me.from_pydata(*TRI)
        me.update()
        bpy.context.scene.collection.objects.link(bpy.data.objects.new("DonorObj", me))
        bpy.ops.wm.save_as_mainfile(filepath=donor_path)

        bpy.ops.wm.read_factory_settings(use_empty=True)
        local_me = bpy.data.meshes.new("Shared")
        local_me.from_pydata(*TRI)
        local_me.update()
        local_obj = bpy.data.objects.new("LocalObj", local_me)
        bpy.context.scene.collection.objects.link(local_obj)

        with bpy.data.libraries.load(donor_path, link=True) as (data_from, data_to):
            data_to.meshes = list(data_from.meshes)
        linked_me = next(m for m in data_to.meshes if m is not None)
        linked_obj = bpy.data.objects.new("LinkedUserObj", linked_me)
        bpy.context.scene.collection.objects.link(linked_obj)

        checks.append(("starts with 2 distinct 'Shared' meshes (local + linked)",
                       local_me != linked_me and local_me.name == "Shared"
                       and linked_me.name == "Shared" and linked_me.library is not None))

        res = bpy.ops.filelink.instance_geometry("EXEC_DEFAULT", apply=True)
        checks.append(("apply FINISHED", res == {"FINISHED"}))
        checks.append(("local mesh chosen as canonical (local preferred by default)",
                       local_obj.data == local_me))
        checks.append(("linked object's user remapped ONTO the local canonical",
                       linked_obj.data == local_me))
        checks.append(("the LINKED mesh datablock itself still exists (never removed)",
                       linked_me.name in bpy.data.meshes))
        checks.append(("...and is still actually linked, not silently localized",
                       linked_me.library is not None))
        checks.append(("nothing crashed re-scanning afterward",
                       bpy.ops.filelink.instance_geometry("EXEC_DEFAULT", apply=False)
                       == {"FINISHED"}))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("GEO_LINKED_SMOKE_OK" if ok else "GEO_LINKED_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("GEO_LINKED_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
