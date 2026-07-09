"""Examine Apply Selected must resolve the LINKED block, not a same-named LOCAL one:

    blender --background --factory-startup --python tests/smoke_examine_library_name_collision.py

Real bug found live, 2026-07-09 (PSM_Stage_v5.2, applying Examine Library
against human_bundle.blend reported "Made 0 local, remapped 0" for 46 rows
that had all just shown an in-memory match). Root cause: the per-row apply
loop looked the row's target block up by PLAIN NAME
(``target_coll.get(row.name)``), with no library disambiguation. In a file
this heavily merged, a local data-block can coincidentally share the exact
name of a linked one -- the plain-name lookup has no guarantee of returning
the specific linked block the row was populated from, so every row looked
"stale" (block.library == None) even though nothing had actually changed
since the scan.

Builds a source .blend with one object ("Widget"), links it into a main file
that ALSO has an unrelated local object also named "Widget" (Blender allows
this across libraries -- no forced rename), then runs the real Examine
Library populate + Apply Selected (with make_local ticked) against the
library and asserts the LINKED "Widget" was made local, not a no-op that
silently leaves the local "Widget" untouched.
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


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()
    examine = __import__(f"{PKG}.ops.examine_library", fromlist=["_populate_examine_rows"])

    checks = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            source = str(pathlib.Path(tmp) / "source.blend")
            main_path = str(pathlib.Path(tmp) / "main.blend")

            bpy.ops.wm.read_factory_settings(use_empty=True)
            src_obj = bpy.data.objects.new("Widget", None)
            bpy.context.scene.collection.objects.link(src_obj)
            bpy.ops.wm.save_as_mainfile(filepath=source)

            bpy.ops.wm.read_factory_settings(use_empty=True)
            # Unrelated LOCAL object with the exact same base name as the one
            # about to be linked in -- Blender allows this across libraries.
            local_obj = bpy.data.objects.new("Widget", None)
            bpy.context.scene.collection.objects.link(local_obj)
            with bpy.data.libraries.load(source, link=True) as (data_from, data_to):
                data_to.objects = list(data_from.objects)
            for o in data_to.objects:
                bpy.context.scene.collection.objects.link(o)
            bpy.ops.wm.save_as_mainfile(filepath=main_path)
            bpy.ops.wm.open_mainfile(filepath=main_path)

            library = bpy.data.libraries.get("source.blend")
            checks.append(("library present", library is not None))

            linked_obj = next(
                (o for o in bpy.data.objects if o.name == "Widget" and o.library is library),
                None,
            )
            checks.append(("linked Widget present", linked_obj is not None))
            checks.append(("a local Widget also exists",
                           any(o.name == "Widget" and o.library is None
                               for o in bpy.data.objects)))

            if library is not None:
                n = examine._populate_examine_rows(bpy.context, library)
                checks.append(("one row populated", n == 1))
                wm = bpy.context.window_manager
                rows = list(wm.filelink_examine_rows)
                row = rows[0] if rows else None
                if row is not None:
                    row.selected = True
                    row.make_local = True

                bpy.ops.filelink.examine_apply_selected()

                checks.append(("summary reports remapped/localized >0",
                               "Made 1 local" in wm.filelink_examine_apply_summary
                               or "remapped 1" in wm.filelink_examine_apply_summary))
                still_linked = any(o.name == "Widget" and o.library is library
                                   for o in bpy.data.objects)
                checks.append(("the linked Widget is no longer linked",
                               not still_linked))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("EXAMINE_NAME_COLLISION_SMOKE_OK" if ok else "EXAMINE_NAME_COLLISION_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("EXAMINE_NAME_COLLISION_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
