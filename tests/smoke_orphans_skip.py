"""Find Orphans surfaces SKIPPED risky meshes by name:

    blender --background --factory-startup --python tests/smoke_orphans_skip.py

2026-07-04 follow-up to the v0.2.94 shape-key crash fix: the SAME disease
class (a native access violation reading geometry/node-tree/image data off a
missing placeholder or Library Override datablock) crashed ops.orphans's
mesh-fingerprint step too, which had NO risk filtering at all (unlike shape
keys). Builds a real Library Override mesh (via the normal link +
override_create() round trip), runs the REAL ``filelink.scan_orphans``
operator, and checks the override mesh is reported by name in
``wm.filelink_orphan_skipped_text`` while a plain local mesh is NOT (it
still gets fingerprinted normally).
"""

import pathlib
import sys
import tempfile
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))
PKG = REPO_ROOT.name


def _mesh_object(bpy, name):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    return bpy.data.objects.new(name, mesh)


def main():
    import bpy

    tmp = pathlib.Path(tempfile.mkdtemp())
    donor_path = tmp / "donor.blend"

    checks = []
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        obj = _mesh_object(bpy, "Char")
        bpy.context.scene.collection.objects.link(obj)
        bpy.ops.wm.save_as_mainfile(filepath=str(donor_path))

        bpy.ops.wm.read_factory_settings(use_empty=True)
        with bpy.data.libraries.load(str(donor_path), link=True) as (data_from, data_to):
            data_to.objects = list(data_from.objects)
        coll = bpy.data.collections.new("Coll")
        bpy.context.scene.collection.children.link(coll)
        coll.objects.link(data_to.objects[0])
        bpy.context.view_layer.update()

        linked_obj = bpy.data.objects["Char"]
        override_obj = linked_obj.override_create()
        override_mesh = override_obj.data.override_create()
        bpy.context.view_layer.update()
        override_mesh_name = override_mesh.name

        # A second, plain LOCAL mesh — should still be fingerprinted normally.
        local_obj = _mesh_object(bpy, "LocalChar")
        bpy.context.scene.collection.objects.link(local_obj)
        local_mesh_name = local_obj.data.name

        addon = __import__(PKG)
        addon.register()
        try:
            bpy.ops.filelink.scan_orphans()
            wm = bpy.context.window_manager
            skipped_text = wm.filelink_orphan_skipped_text
            checks.append(("override mesh named in the skipped text",
                           override_mesh_name in skipped_text))
            checks.append(("skipped reason mentions it's a Library Override",
                           "Override" in skipped_text))
            checks.append(("the plain local mesh is NOT in the skipped text",
                           local_mesh_name not in skipped_text))
        finally:
            addon.unregister()

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("ORPHANS_SKIP_SMOKE_OK" if ok else "ORPHANS_SKIP_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("ORPHANS_SKIP_SMOKE_FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
