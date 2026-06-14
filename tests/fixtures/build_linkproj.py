"""Generate a small linked .blend project used by F1 tests.

Run with Blender (committed output so pytest stays bpy-free):

    blender --background --factory-startup --python tests/fixtures/build_linkproj.py

Produces tests/fixtures/linkproj/:
    libB.blend   - leaf library: object "Rock", material "Stone"
    libA.blend   - links "Rock" from libB  (so libA -> libB, an indirect chain)
                   + own object "Tree", material "Bark_2k"
    scene.blend  - links "Tree" from libA  (so scene -> libA -> libB)

Links are stored relative (relative_remap) so the fixtures are location-
independent. Deterministic: same names every run.
"""

import os
import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "linkproj")
os.makedirs(OUT, exist_ok=True)

LIBA = os.path.join(OUT, "libA.blend")
LIBB = os.path.join(OUT, "libB.blend")
SCENE = os.path.join(OUT, "scene.blend")


def _reset_empty():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _new_object(name, mat_name):
    mesh = bpy.data.meshes.new(name + "Mesh")
    # one tri so the mesh is non-trivial
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    obj.data.materials.append(mat)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _link_object(blendpath, obj_name):
    with bpy.data.libraries.load(blendpath, link=True) as (src, dst):
        assert obj_name in src.objects, f"{obj_name} not in {blendpath}: {list(src.objects)}"
        dst.objects = [obj_name]
    for obj in dst.objects:
        if obj is not None:
            bpy.context.scene.collection.objects.link(obj)


def _save(path):
    bpy.ops.wm.save_as_mainfile(filepath=path, relative_remap=True, compress=False)


def main():
    # libB - leaf: object Rock + material Stone + a fake-user action (for the
    # find_datablocks "action" search test; fake user keeps it without an animated user).
    _reset_empty()
    _new_object("Rock", "Stone")
    bpy.data.actions.new("WalkCycle").use_fake_user = True
    _save(LIBB)

    # libA - own Tree + link Rock from libB
    _reset_empty()
    _new_object("Tree", "Bark_2k")
    _link_object(LIBB, "Rock")
    _save(LIBA)

    # scene - link Tree from libA
    _reset_empty()
    _link_object(LIBA, "Tree")
    _save(SCENE)

    print("FIXTURES_BUILT", OUT)
    for f in (LIBB, LIBA, SCENE):
        print("  ", os.path.basename(f), os.path.getsize(f), "bytes")


if __name__ == "__main__":
    main()
