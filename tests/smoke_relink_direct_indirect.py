"""Find Broken Links distinguishes DIRECT vs INDIRECT libraries:

    blender --background --factory-startup --python tests/smoke_relink_direct_indirect.py

docs/TODO.md Group 1 item 5 (2026-07-04) — `bpy.data.libraries` includes
libraries the current file links directly AND libraries only reachable
transitively through another linked library (the historical "Piazza
SanMarco.blend not in Libraries" confusion). Builds a real 3-file chain
(root -> libA -> libB, where root only ever references something IN libA,
and libB is only reachable via libA's own data) and checks
`ops.relink._gather_libs()` tags libA "direct" and libB "indirect".
"""

import pathlib
import sys
import tempfile
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))
PKG = REPO_ROOT.name


def main():
    import bpy

    tmp = pathlib.Path(tempfile.mkdtemp())
    libB_path = tmp / "libB.blend"
    libA_path = tmp / "libA.blend"

    checks = []
    try:
        # libB: one plain mesh object.
        bpy.ops.wm.read_factory_settings(use_empty=True)
        mesh_b = bpy.data.meshes.new("MeshB")
        mesh_b.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
        obj_b = bpy.data.objects.new("MeshB", mesh_b)
        bpy.context.scene.collection.objects.link(obj_b)
        bpy.ops.wm.save_as_mainfile(filepath=str(libB_path))

        # libA: links MeshB, has its own LOCAL object ObjA parented to it (so
        # libB is only reachable through libA's OWN data, never root's).
        bpy.ops.wm.read_factory_settings(use_empty=True)
        with bpy.data.libraries.load(str(libB_path), link=True) as (data_from, data_to):
            data_to.objects = list(data_from.objects)
        linked_meshb = bpy.data.objects["MeshB"]
        bpy.context.scene.collection.objects.link(linked_meshb)
        mesh_a = bpy.data.meshes.new("MeshA")
        mesh_a.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
        obj_a = bpy.data.objects.new("ObjA", mesh_a)
        obj_a.parent = linked_meshb  # the ONLY reference to libB's content
        bpy.context.scene.collection.objects.link(obj_a)
        bpy.ops.wm.save_as_mainfile(filepath=str(libA_path))

        # root: links ObjA (from libA) into its OWN local collection — this is
        # the only local reference anywhere, and it points at libA, not libB.
        bpy.ops.wm.read_factory_settings(use_empty=True)
        with bpy.data.libraries.load(str(libA_path), link=True) as (data_from, data_to):
            data_to.objects = [n for n in data_from.objects if n == "ObjA"]
        bpy.context.scene.collection.objects.link(data_to.objects[0])
        bpy.context.view_layer.update()

        lib_names = sorted(lib.name for lib in bpy.data.libraries)
        checks.append(("root's bpy.data.libraries includes BOTH libA and libB",
                       len(lib_names) == 2))

        addon = __import__(PKG)
        addon.register()
        try:
            import importlib
            relink_mod = importlib.import_module(f"{PKG}.ops.relink")
            libs = relink_mod._gather_libs()
            by_name = {pathlib.Path(lib.stored).name: lib for lib in libs}
            checks.append(("libA.blend present in _gather_libs()", "libA.blend" in by_name))
            checks.append(("libB.blend present in _gather_libs()", "libB.blend" in by_name))
            if "libA.blend" in by_name:
                checks.append(("libA.blend tagged DIRECT", by_name["libA.blend"].is_direct is True))
            if "libB.blend" in by_name:
                checks.append(("libB.blend tagged INDIRECT", by_name["libB.blend"].is_direct is False))
        finally:
            addon.unregister()

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("RELINK_DIRECT_INDIRECT_SMOKE_OK" if ok else "RELINK_DIRECT_INDIRECT_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("RELINK_DIRECT_INDIRECT_SMOKE_FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
