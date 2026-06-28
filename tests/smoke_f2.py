"""End-to-end F2 check in Blender:

    blender --background --factory-startup --python tests/smoke_f2.py

Opens the scene.blend fixture (scene -> libA -> libB), runs F2 in both modes
against COPIES (fixtures stay pristine), and asserts:
  * NEW_FILE: a local copy is written whose .blend has zero library links
    (cross-checked with BAT), and the working session is reverted (still linked).
  * IN_PLACE: the session ends with no linked datablocks and no libraries.
"""

import glob
import pathlib
import shutil
import sys
import tempfile
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))
_bat = glob.glob(str(REPO_ROOT / "wheels" / "blender_asset_tracer-*.whl"))
if _bat:
    sys.path.insert(0, _bat[0])
PKG = REPO_ROOT.name
LINKPROJ = REPO_ROOT / "tests" / "fixtures" / "linkproj"


def _count_linked(bpy):
    n = 0
    for prop in bpy.data.bl_rna.properties:
        if prop.type != "COLLECTION":
            continue
        coll = getattr(bpy.data, prop.identifier, None)
        if not coll:
            continue
        first = next(iter(coll), None)
        if first is not None and hasattr(first, "library"):
            n += sum(1 for db in coll if db.library is not None)
    return n


def main():
    import bpy
    from blender_asset_tracer import blendfile

    addon = __import__(PKG)
    addon.register()
    checks = []
    try:
        # Work on a copy of the whole project so relative links resolve and the
        # fixtures are never modified.
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="ad_f2_"))
        proj = tmp / "proj"
        shutil.copytree(LINKPROJ, proj)
        scene = proj / "scene.blend"

        # ---- NEW_FILE mode ----
        bpy.ops.wm.open_mainfile(filepath=str(scene))
        linked_before = _count_linked(bpy)
        out = tmp / "scene_local.blend"
        res = bpy.ops.assetdoctor.make_local(
            "EXEC_DEFAULT", mode="NEW_FILE", apply=True, filepath=str(out)
        )
        checks.append(("NEW_FILE FINISHED", res == {"FINISHED"}))
        checks.append(("had linked data to start", linked_before > 0))
        checks.append(("local copy written", out.is_file()))
        if out.is_file():
            bf = blendfile.BlendFile(out)
            li = bf.find_blocks_from_code(b"LI")
            bf.close()
            checks.append(("local copy has zero library links", len(li) == 0))
        # session reverted -> still linked
        checks.append(("session reverted (still linked)", _count_linked(bpy) > 0))

        # ---- IN_PLACE mode ----
        bpy.ops.wm.open_mainfile(filepath=str(scene))
        res2 = bpy.ops.assetdoctor.make_local("EXEC_DEFAULT", mode="IN_PLACE", apply=True)
        checks.append(("IN_PLACE FINISHED", res2 == {"FINISHED"}))
        checks.append(("session has no linked datablocks", _count_linked(bpy) == 0))
        checks.append(("no libraries remain", len(bpy.data.libraries) == 0))

        # docs/TODO.md Group 6 #19 (2026-06-27): a LOCAL object sharing a name
        # with a linked one is a real rename-collision risk -- the dry-run
        # report must call it out by name, not just "this file is linked."
        bpy.ops.wm.open_mainfile(filepath=str(scene))
        make_local_mod = __import__(f"{PKG}.ops.make_local", fromlist=["_gather_linked"])
        linked_items = make_local_mod._gather_linked()
        collide_with = next(it for it in linked_items if it["type"] == "Object")
        bpy.data.objects.new(collide_with["name"], None)  # local, same type+name

        res3 = bpy.ops.assetdoctor.make_local("EXEC_DEFAULT", mode="IN_PLACE", apply=False)
        wm = bpy.context.window_manager
        checks.append(("dry-run FINISHED", res3 == {"FINISHED"}))
        f2_report = wm.assetdoctor_rep_f2
        checks.append(("rename collision reported", f"Object/{collide_with['name']}" in f2_report
                       and "rename_risk" in f2_report))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("F2_SMOKE_OK" if ok else "F2_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("F2_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
