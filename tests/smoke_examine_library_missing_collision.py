"""Examine Library must never suggest remapping onto ANOTHER missing placeholder:

    blender --background --factory-startup --python tests/smoke_examine_library_missing_collision.py

Real bug found live, 2026-07-09 (PSM_Stage_v5.2, two libraries both unreadable
on disk -- human_bundle.blend and Asset_bundle.blend). Both broken libraries
can each hold a same-BASE-name missing block purely by coincidence of
Blender's own ".NNN" dedup-suffix numbering (e.g. one wants "Widget.001", an
unrelated other wants "Widget.002" -- suggest_reconnect's "numbered" tier
strips both to base "Widget" and calls it a match). Remapping one placeholder
onto another placeholder doesn't fix anything and silently "succeeds", which
is how a user's staged Apply Selected can report success yet leave the
data-block count completely unchanged after a reload.

Builds two source .blends, links one object from each into a third (main)
file, saves, deletes BOTH source files from disk, then reopens the main file
-- Blender marks both linked objects as missing placeholders. Runs the real
Examine Library populate step against library A and asserts it does NOT
suggest library B's (also-missing) same-base-name object.
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
            source_a = str(pathlib.Path(tmp) / "sourceA.blend")
            source_b = str(pathlib.Path(tmp) / "sourceB.blend")
            main_path = str(pathlib.Path(tmp) / "main.blend")

            bpy.ops.wm.read_factory_settings(use_empty=True)
            obj_a = bpy.data.objects.new("Widget.001", None)
            bpy.context.scene.collection.objects.link(obj_a)
            bpy.ops.wm.save_as_mainfile(filepath=source_a)

            bpy.ops.wm.read_factory_settings(use_empty=True)
            obj_b = bpy.data.objects.new("Widget.002", None)
            bpy.context.scene.collection.objects.link(obj_b)
            bpy.ops.wm.save_as_mainfile(filepath=source_b)

            bpy.ops.wm.read_factory_settings(use_empty=True)
            with bpy.data.libraries.load(source_a, link=True) as (data_from, data_to):
                data_to.objects = list(data_from.objects)
            for o in data_to.objects:
                bpy.context.scene.collection.objects.link(o)
            with bpy.data.libraries.load(source_b, link=True) as (data_from, data_to):
                data_to.objects = list(data_from.objects)
            for o in data_to.objects:
                bpy.context.scene.collection.objects.link(o)
            bpy.ops.wm.save_as_mainfile(filepath=main_path)

            # Both source libraries now become unreadable -- reopening main.blend
            # marks their linked objects as missing placeholders (same shape as
            # the real "Unable to open ... No such file or directory" case).
            os.remove(source_a)
            os.remove(source_b)
            bpy.ops.wm.open_mainfile(filepath=main_path)

            lib_a = bpy.data.libraries.get("sourceA.blend")
            checks.append(("library A present", lib_a is not None))
            widget_a = bpy.data.objects.get("Widget.001")
            widget_b = bpy.data.objects.get("Widget.002")
            checks.append(("Widget.001 is a missing placeholder",
                           widget_a is not None and widget_a.is_missing))
            checks.append(("Widget.002 is a missing placeholder",
                           widget_b is not None and widget_b.is_missing))

            if lib_a is not None:
                n = examine._populate_examine_rows(bpy.context, lib_a)
                checks.append(("one row populated", n == 1))
                rows = list(bpy.context.window_manager.filelink_examine_rows)
                row = rows[0] if rows else None
                checks.append(("row is Widget.001", row is not None and row.name == "Widget.001"))
                if row is not None:
                    checks.append(("NOT suggested onto another missing placeholder",
                                   row.suggested_kind == "none"))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("EXAMINE_MISSING_COLLISION_SMOKE_OK" if ok else "EXAMINE_MISSING_COLLISION_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("EXAMINE_MISSING_COLLISION_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
