"""Examine Library's "two-pass" content verification for the MANUAL-pick
paths, end-to-end in Blender:

    blender --background --factory-startup --python tests/smoke_examine_content_verify.py

docs/TODO.md's 2026-07-09 "two-pass" design (unblocked by tests/probe_double_
link.py, 2026-07-14): Pick a Specific Item, Search a Folder, and the new bulk
"Search a Folder (all unresolved)" used to stage a manually-found candidate
and auto-select it for Apply on NAME MATCH ALONE -- exactly the trust
smoke_examine_library.py already proved wrong for the IN-MEMORY suggestion
path (an exact/same-generic-name match is not proof of identity). This test
proves the same content check (identical/differs/unverified, gated the same
way _populate_examine_rows gates an in-memory suggestion) now applies here
too, for both the per-row operators and the new bulk one -- and that a
manual dropdown swap to an unverified candidate can't silently ride along on
a stale "verified" auto-select (ui.panels._on_examine_target_changed).
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


def _plane_mesh(bpy, name, size):
    mesh = bpy.data.meshes.new(name)
    verts = [(-size, -size, 0), (size, -size, 0), (size, size, 0), (-size, size, 0)]
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    mesh.update()
    mesh.use_fake_user = True  # 0-user datablocks are silently dropped on save
    return mesh


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()
    examine = __import__(f"{PKG}.ops.examine_library", fromlist=["_populate_examine_rows"])

    checks = []
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = pathlib.Path(tmp_dir)
            candidates_dir = tmp / "candidates"
            candidates_dir.mkdir()
            # A SEPARATE folder/file for the per-row tests below: once the
            # bulk pass real-links candidates/walls.blend, that library is
            # legitimately "already loaded" for the rest of the session, and
            # every later Search a Folder correctly SKIPS it (crash-avoidance
            # -- see FILELINK_OT_examine_search_folder's docstring). Reusing
            # the same file for both phases would make the per-row phase
            # find nothing, for a reason that has nothing to do with what
            # it's testing.
            candidates_dir2 = tmp / "candidates2"
            candidates_dir2.mkdir()

            # The EXAMINED library: three meshes with deliberately odd names
            # (no in-memory local/other-library match, so _populate_examine_
            # rows leaves all three suggested_kind == "none" -- the manual-
            # pick fallback this whole test exercises).
            library_path = str(tmp / "library.blend")
            bpy.ops.wm.read_factory_settings(use_empty=True)
            _plane_mesh(bpy, "WallA", 1.0)
            _plane_mesh(bpy, "WallB", 2.0)
            _plane_mesh(bpy, "WallC", 3.0)
            bpy.ops.wm.save_as_mainfile(filepath=library_path)

            # candidates/walls.blend: WallA is genuinely IDENTICAL (size 1.0);
            # WallB is genuinely DIFFERENT (size 9.0 vs. the library's 2.0) --
            # same exact-name-is-not-proof-of-identity shape as smoke_examine_
            # library.py, just reached via a manual file pick instead of an
            # in-memory match. Both share one file so the bulk pass's
            # "group several rows onto one file load" path gets exercised too.
            bpy.ops.wm.read_factory_settings(use_empty=True)
            _plane_mesh(bpy, "WallA", 1.0)
            _plane_mesh(bpy, "WallB", 9.0)
            bpy.ops.wm.save_as_mainfile(filepath=str(candidates_dir / "walls.blend"))

            # candidates/fuzzy_source.blend: only a FUZZY-confidence name match
            # for "WallC" -- must be staged (visible for manual review) but
            # NEVER real-linked/content-verified/auto-selected, same rule as
            # the in-memory path's allow_fuzzy=False.
            bpy.ops.wm.read_factory_settings(use_empty=True)
            _plane_mesh(bpy, "WallC_v2", 3.0)
            bpy.ops.wm.save_as_mainfile(filepath=str(candidates_dir / "fuzzy_source.blend"))

            # candidates2/walls2.blend: the SAME WallA-identical/WallB-differs
            # shape, for the per-row operator tests below (a fresh, not-yet-
            # linked file, per the note above).
            bpy.ops.wm.read_factory_settings(use_empty=True)
            _plane_mesh(bpy, "WallA", 1.0)
            _plane_mesh(bpy, "WallB", 9.0)
            bpy.ops.wm.save_as_mainfile(filepath=str(candidates_dir2 / "walls2.blend"))

            # Fresh session: link all three from library.blend for real.
            bpy.ops.wm.read_factory_settings(use_empty=True)
            with bpy.data.libraries.load(library_path, link=True) as (data_from, data_to):
                data_to.meshes = list(data_from.meshes)
            for m in data_to.meshes:
                obj = bpy.data.objects.new(m.name, m)
                bpy.context.scene.collection.objects.link(obj)
            library = next(m.library for m in data_to.meshes if m is not None)

            def rows_by_name():
                examine._populate_examine_rows(bpy.context, library)
                return {r.name: r for r in bpy.context.window_manager.filelink_examine_rows}

            # --- Bulk operator: one folder walk resolves all three rows -----
            rows = rows_by_name()
            checks.append(("three rows populated, all unresolved",
                           len(rows) == 3 and all(r.suggested_kind == "none" for r in rows.values())))

            res = bpy.ops.filelink.examine_bulk_search_folder(
                "EXEC_DEFAULT", directory=str(candidates_dir))
            checks.append(("bulk search FINISHED", res == {"FINISHED"}))

            a, b, c = rows.get("WallA"), rows.get("WallB"), rows.get("WallC")
            if a is not None:
                checks.append(("bulk: WallA found in walls.blend",
                               a.source_blend.endswith("walls.blend")))
                checks.append(("bulk: WallA content identical", a.graph_match == "identical"))
                checks.append(("bulk: WallA auto-selected", a.selected is True))
            else:
                checks.append(("WallA row found (bulk)", False))
            if b is not None:
                checks.append(("bulk: WallB found in walls.blend",
                               b.source_blend.endswith("walls.blend")))
                checks.append(("bulk: WallB content differs", b.graph_match == "differs"))
                checks.append(("bulk: WallB NOT auto-selected", b.selected is False))
            else:
                checks.append(("WallB row found (bulk)", False))
            if c is not None:
                checks.append(("bulk: WallC found fuzzy match in fuzzy_source.blend",
                               c.source_blend.endswith("fuzzy_source.blend")))
                checks.append(("bulk: WallC never content-verified (fuzzy-only)",
                               c.graph_match == ""))
                checks.append(("bulk: WallC NOT auto-selected", c.selected is False))
            else:
                checks.append(("WallC row found (bulk)", False))

            # --- Per-row Search a Folder: same verification, one row at a time
            rows = rows_by_name()
            idx_a = next((i for i, r in enumerate(bpy.context.window_manager.filelink_examine_rows)
                         if r.name == "WallA"), None)
            res = bpy.ops.filelink.examine_search_folder(
                "EXEC_DEFAULT", index=idx_a, directory=str(candidates_dir2))
            checks.append(("per-row search_folder FINISHED", res == {"FINISHED"}))
            a2 = rows.get("WallA")
            checks.append(("per-row: WallA content identical",
                           a2 is not None and a2.graph_match == "identical"))
            checks.append(("per-row: WallA auto-selected",
                           a2 is not None and a2.selected is True))

            # Manually swap the dropdown to WallB (present in the same file,
            # never verified against THIS row) -- must reset the stale
            # "verified identical" state instead of silently keeping it
            # selected (ui.panels._on_examine_target_changed).
            if a2 is not None:
                a2.target = "WallB"
                checks.append(("target swap resets graph_match", a2.graph_match == ""))
                checks.append(("target swap resets selected", a2.selected is False))

            # --- Per-row Pick a Specific Item: manual file+item pick --------
            rows = rows_by_name()
            idx_b = next((i for i, r in enumerate(bpy.context.window_manager.filelink_examine_rows)
                         if r.name == "WallB"), None)
            res = bpy.ops.filelink.examine_pick_source(
                "EXEC_DEFAULT", index=idx_b, filepath=str(candidates_dir2 / "walls2.blend"))
            checks.append(("per-row pick_source FINISHED", res == {"FINISHED"}))
            b2 = rows.get("WallB")
            checks.append(("per-row: WallB content differs",
                           b2 is not None and b2.graph_match == "differs"))
            checks.append(("per-row: WallB NOT auto-selected",
                           b2 is not None and b2.selected is False))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("EXAMINE_CONTENT_VERIFY_SMOKE_OK" if ok else "EXAMINE_CONTENT_VERIFY_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("EXAMINE_CONTENT_VERIFY_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
