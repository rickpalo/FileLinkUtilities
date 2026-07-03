"""Find Duplicate Data-blocks surfaces SKIPPED risky shape keys by name:

    blender --background --factory-startup --python tests/smoke_datablock_dup_skip.py

User feedback (2026-06-28, same session as the crash fix): silently dropping
a risky shape key into the generic "unverified" bucket isn't enough -- the
user needs to see WHICH shape key got skipped and WHY, so they can go
investigate the underlying file corruption. Builds a real Library Override
(via the normal link + override_create() round trip) whose shape key shares
a `.NNN` name family with a plain local one, runs the REAL
``assetdoctor.scan_datablock_dups`` operator, and checks the override one is
reported by name in ``wm.assetdoctor_datablock_skipped_text`` while the
plain local one is NOT (it still gets fingerprinted normally).
"""

import pathlib
import sys
import tempfile
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))
PKG = REPO_ROOT.name


def _mesh_with_shape_keys(bpy, name):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new(name, mesh)
    obj.shape_key_add(name="Basis")
    sk = obj.shape_key_add(name="Moved")
    sk.data[0].co = (5.0, 0.0, 0.0)
    return obj


def main():
    import bpy

    tmp = pathlib.Path(tempfile.mkdtemp())
    donor_path = tmp / "donor.blend"

    checks = []
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        obj = _mesh_with_shape_keys(bpy, "Char")
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
        override_key_name = override_mesh.shape_keys.name  # auto-named "Key" (first in this session)

        # A second, plain LOCAL mesh+shape-key -- Blender auto-suffixes its Key
        # to "Key.001" since "Key" is taken, forming a genuine .NNN family with
        # the override's shape key above (the precondition `_gather_steps`
        # needs to even consider fingerprinting either of them).
        local_obj = _mesh_with_shape_keys(bpy, "LocalChar")
        bpy.context.scene.collection.objects.link(local_obj)
        local_key_name = local_obj.data.shape_keys.name
        checks.append(("the two shape keys really share a .NNN family",
                       local_key_name != override_key_name
                       and local_key_name.split(".")[0] == override_key_name.split(".")[0]))

        addon = __import__(PKG)
        addon.register()
        try:
            bpy.ops.assetdoctor.scan_datablock_dups()
            wm = bpy.context.window_manager
            skipped_text = wm.assetdoctor_datablock_skipped_text
            checks.append(("override shape key named in the skipped text",
                           override_key_name in skipped_text))
            checks.append(("skipped reason mentions it's a Library Override",
                           "Override" in skipped_text))
            checks.append(("the plain local shape key is NOT in the skipped text",
                           local_key_name not in skipped_text))
        finally:
            addon.unregister()

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("DATABLOCK_DUP_SKIP_SMOKE_OK" if ok else "DATABLOCK_DUP_SKIP_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("DATABLOCK_DUP_SKIP_SMOKE_FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
