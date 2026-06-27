"""Throwaway probe (not a regression test): does linking an object that is
ITSELF a Library Override in its source file expose override_library /
overridden values to the file that links it?

Run: blender --background --factory-startup --python tests/probe_remote_override_link.py
"""
import pathlib
import sys
import tempfile


def main():
    import bpy

    tmp = pathlib.Path(tempfile.mkdtemp())
    source_path = tmp / "source.blend"
    donor_path = tmp / "donor.blend"

    # --- source.blend: a plain object, the "ultimate library" -----------------
    bpy.ops.wm.read_factory_settings(use_empty=True)
    src_obj = bpy.data.objects.new("TestObj", bpy.data.meshes.new("TestMesh"))
    bpy.context.scene.collection.objects.link(src_obj)
    bpy.ops.wm.save_as_mainfile(filepath=str(source_path))
    print(f"PROBE source saved: {source_path}")

    # --- donor.blend: links TestObj from source, overrides + moves it --------
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with bpy.data.libraries.load(str(source_path), link=True) as (data_from, data_to):
        data_to.objects = list(data_from.objects)
    linked = data_to.objects[0]
    bpy.context.scene.collection.objects.link(linked)
    bpy.context.view_layer.update()
    override = linked.override_create()
    override.location = (5.0, 5.0, 5.0)
    print(f"PROBE donor override props after edit: "
          f"{[p.rna_path for p in override.override_library.properties]}")
    # Sanity-check object: a TRULY plain local object, no override at all,
    # saved in the SAME file -- proves whether libraries.load's data_from
    # enumeration excludes overrides specifically, or something else is wrong.
    plain = bpy.data.objects.new("PlainObj", bpy.data.meshes.new("PlainMesh"))
    bpy.context.scene.collection.objects.link(plain)
    bpy.ops.wm.save_as_mainfile(filepath=str(donor_path))
    print(f"PROBE donor saved: {donor_path}, override name={override.name}, "
          f"loc={tuple(override.location)}, is_override={override.override_library is not None}")
    print(f"PROBE donor.blend's own bpy.data.objects: {[o.name for o in bpy.data.objects]}")

    # --- consumer: try to link BOTH from donor -------------------------------
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with bpy.data.libraries.load(str(donor_path), link=True) as (data_from, data_to):
        print(f"PROBE donor.blend's objects visible to libraries.load: {list(data_from.objects)}")
        data_to.objects = list(data_from.objects)
    for consumed in data_to.objects:
        if consumed is None:
            continue
        bpy.context.scene.collection.objects.link(consumed)
        bpy.context.view_layer.update()
        print(f"PROBE CONSUMED name={consumed.name} library={consumed.library} "
              f"override_library={consumed.override_library} location={tuple(consumed.location)}")

    print("PROBE DONE")


if __name__ == "__main__":
    main()
    sys.exit(0)
