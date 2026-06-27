"""End-to-end remote-harvest subprocess check (docs/TODO.md Group 11 #47):

    blender --background --factory-startup --python tests/smoke_remote_harvest.py

Builds a real local override in a throwaway "donor" file, then drives
``ops.linkchain._harvest_remote`` for real -- a SEPARATE background Blender
process opens the donor file and reads its override back out, exactly the
mechanism Flatten Selected uses for a remote-sourced character. This is the
one piece of the whole Flatten v2 pipeline that can't be covered by
smoke_flatten_selected.py's synthetic-report approach, since it genuinely
needs a second real Blender process round-trip.
"""

import glob
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


def main():
    import bpy

    tmp = pathlib.Path(tempfile.mkdtemp())
    ultimate_path = tmp / "ultimate.blend"
    donor_path = tmp / "donor.blend"

    checks = []
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        obj = bpy.data.objects.new("Char", bpy.data.meshes.new("CharMesh"))
        bpy.context.scene.collection.objects.link(obj)
        bpy.ops.wm.save_as_mainfile(filepath=str(ultimate_path))

        bpy.ops.wm.read_factory_settings(use_empty=True)
        with bpy.data.libraries.load(str(ultimate_path), link=True) as (data_from, data_to):
            data_to.objects = list(data_from.objects)
        coll = bpy.data.collections.new("CharColl")
        bpy.context.scene.collection.children.link(coll)
        coll.objects.link(data_to.objects[0])
        bpy.context.view_layer.update()

        override = bpy.data.objects["Char"].override_create()
        if override is None:
            print("SMOKE_FAIL: override_create() failed during setup")
            return 1
        override.location = (3.0, 4.0, 5.0)
        override.override_library.properties.add("location")
        coll.objects.link(override)
        bpy.ops.wm.save_as_mainfile(filepath=str(donor_path))

        addon = __import__(PKG)
        addon.register()
        ops_linkchain = __import__(f"{PKG}.ops.linkchain", fromlist=["x"])
        try:
            gen = ops_linkchain._harvest_remote(str(donor_path), ["Char", "NoSuchObject"])
            result = None
            progress_steps = 0
            try:
                while True:
                    frac, msg = next(gen)
                    progress_steps += 1
            except StopIteration as stop:
                result = stop.value
        finally:
            addon.unregister()

        checks.append(("at least one progress step was yielded", progress_steps >= 1))
        checks.append(("result dict returned", isinstance(result, dict)))
        checks.append(("Char found", result.get("Char") is not None and result["Char"].found))
        if result.get("Char") is not None and result["Char"].found:
            hr = result["Char"]
            checks.append(("Char's reference resolved",
                           hr.reference is not None and hr.reference.name == "Char"))
            print(f"PROBE hr.reference.library = {hr.reference.library!r}")
            checks.append(("Char's reference library is ultimate.blend",
                           hr.reference is not None
                           and "ultimate.blend" in hr.reference.library))
            loc_prop = next((p for p in hr.properties if p.rna_path == "location"), None)
            checks.append(("location property harvested with the right value",
                           loc_prop is not None and tuple(loc_prop.value) == (3.0, 4.0, 5.0)))
        checks.append(("NoSuchObject correctly reported as not found",
                       result.get("NoSuchObject") is not None
                       and not result["NoSuchObject"].found))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("REMOTE_HARVEST_SMOKE_OK" if ok else "REMOTE_HARVEST_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("REMOTE_HARVEST_SMOKE_FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
