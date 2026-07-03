"""extract_shape_key's override-guard, end-to-end:

    blender --background --factory-startup --python tests/smoke_extract_shape_key.py

Regression test for the 2026-06-28 Find Duplicates crash on human_bundle.blend
(EXCEPTION_ACCESS_VIOLATION inside extract_shape_key, via a real production
crash log) — a shape key whose owning Mesh is a Library Override is the
documented "KEKey... not linkable, flagged as directly linked" disease
(ops.datablock_inspect already flags this combination as `shape_key_risks`
without ever reading `kb.data` on it). The native access violation can't be
reproduced safely or caught with try/except, so this test instead proves the
GUARD fires for exactly that combination (using a REAL Library Override built
via the normal link + override_create() round trip, not a mock), while a
plain local mesh+shape-key still gets a real fingerprint.
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
        bpy.context.view_layer.update()
        # override_create() on the OBJECT does NOT cascade to its owned Mesh
        # (confirmed via probe) -- the mesh itself needs its OWN override.
        override_mesh = override_obj.data.override_create()
        checks.append(("mesh override_create() succeeded", override_mesh is not None))
        bpy.context.view_layer.update()

        addon = __import__(PKG)
        addon.register()
        extract = __import__(f"{PKG}.ops.extract", fromlist=["extract_shape_key"])
        try:
            # Sanity: a plain LOCAL mesh+shape-key still gets a real fingerprint.
            local_obj = _mesh_with_shape_keys(bpy, "LocalChar")
            bpy.context.scene.collection.objects.link(local_obj)
            local_result = extract.extract_shape_key(local_obj.data.shape_keys)
            checks.append(("plain local shape key still fingerprints normally",
                           bool(local_result.get("blocks")) and len(local_result["blocks"]) == 2))

            checks.append(("override mesh really has override_library set (real override, not a mock)",
                           getattr(override_mesh, "override_library", None) is not None))
            checks.append(("override mesh kept its shape keys (real risky case, not an empty one)",
                           override_mesh.shape_keys is not None
                           and len(override_mesh.shape_keys.key_blocks) == 2))
            risky_result = extract.extract_shape_key(override_mesh.shape_keys)
            checks.append(("override-owned shape key returns {} (guard fires, no deep read)",
                           risky_result == {}))
        finally:
            addon.unregister()

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("EXTRACT_SHAPE_KEY_SMOKE_OK" if ok else "EXTRACT_SHAPE_KEY_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("EXTRACT_SHAPE_KEY_SMOKE_FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
