"""Examine Library folder-wide search, end-to-end in Blender:

    blender --background --factory-startup --python tests/smoke_examine_folder_search.py

docs/TODO.md #20 (2026-06-27): "Search a Folder" should find a name match
across several .blend files without the user already knowing which one holds
it, prefer an exact match in one file over a fuzzy one in another, and skip
any file that's already linked into the current session (crash-avoidance,
see ops.examine_library.FILELINK_OT_examine_search_folder's docstring).
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


def _mesh_obj(bpy, name):
    me = bpy.data.meshes.new(name + "_mesh")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()

    checks = []
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = pathlib.Path(tmp_dir)

            # Donor file the current session WILL link from (so it's already
            # loaded -- must be SKIPPED by the folder search).
            already_linked_path = tmp / "already_linked.blend"
            bpy.ops.wm.read_factory_settings(use_empty=True)
            _mesh_obj(bpy, "Body")
            bpy.ops.wm.save_as_mainfile(filepath=str(already_linked_path))

            # A folder of OTHER files: one with only a fuzzy-ish near match,
            # one with the real exact match -- search order is alphabetical
            # (core.blendscan.iter_blend_files sorts), so "a_fuzzy" is seen
            # before "b_exact"; the exact one must still win.
            bpy.ops.wm.read_factory_settings(use_empty=True)
            _mesh_obj(bpy, "Body_old")
            bpy.ops.wm.save_as_mainfile(filepath=str(tmp / "a_fuzzy.blend"))

            bpy.ops.wm.read_factory_settings(use_empty=True)
            _mesh_obj(bpy, "Body")
            bpy.ops.wm.save_as_mainfile(filepath=str(tmp / "b_exact.blend"))

            # Fresh session: link Body from already_linked.blend (so it's a
            # real Examine Library candidate AND a session-loaded library to
            # be skipped), then Examine it.
            bpy.ops.wm.read_factory_settings(use_empty=True)
            with bpy.data.libraries.load(str(already_linked_path), link=True) as (df, dt):
                dt.objects = list(df.objects)
            linked_obj = next(o for o in dt.objects if o is not None)
            bpy.context.scene.collection.objects.link(linked_obj)

            examine = __import__(f"{PKG}.ops.examine_library", fromlist=["x"])
            library = linked_obj.library
            n = examine._populate_examine_rows(bpy.context, library)
            checks.append(("two rows populated (Object + its Mesh data)", n == 2))

            wm = bpy.context.window_manager
            idx, row = next(((i, r) for i, r in enumerate(wm.filelink_examine_rows)
                             if r.kind == "Object"), (None, None))
            checks.append(("Object row is for Body", row is not None and row.name == "Body"))

            # Both a_fuzzy.blend AND the genuinely-already-loaded
            # already_linked.blend (also in `tmp`, both with an exact-name
            # match) must lose to b_exact.blend -- the fuzzy one on
            # confidence, the already-loaded one because it's skipped
            # entirely (crash-avoidance) despite being an earlier
            # alphabetical/equal-confidence tiebreak candidate.
            res = bpy.ops.filelink.examine_search_folder(
                "EXEC_DEFAULT", index=idx, directory=str(tmp))
            checks.append(("search FINISHED", res == {"FINISHED"}))
            checks.append(("found the EXACT match's file, not the fuzzy or "
                           "already-loaded one", os.path.basename(row.source_blend)
                           == "b_exact.blend"))
            checks.append(("candidates populated with the exact name first",
                           row.candidates.split("\n")[0] == "Body"))
            checks.append(("row staged for apply", row.selected is True))

            # A folder with NOTHING relevant -> CANCELLED, no false match.
            empty_dir = tempfile.mkdtemp()
            row.source_blend = ""
            row.candidates = ""
            res2 = bpy.ops.filelink.examine_search_folder(
                "EXEC_DEFAULT", index=idx, directory=empty_dir)
            checks.append(("empty folder: CANCELLED (nothing found)", res2 == {"CANCELLED"}))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("EXAMINE_FOLDER_SMOKE_OK" if ok else "EXAMINE_FOLDER_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("EXAMINE_FOLDER_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
