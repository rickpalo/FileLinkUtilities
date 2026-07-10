"""Examine Library must not auto-apply a suggestion onto/from data it can't
verify — specifically, a MISSING placeholder is the LEAST trustworthy case
there is (its original content is gone), not a safe one to auto-remap by
name alone:

    blender --background --factory-startup --python tests/smoke_examine_library_missing_vs_local.py

Real bug found live, 2026-07-09, immediately after the Mesh/NodeTree content
check shipped (see tests/smoke_examine_library.py and CHANGELOG.md v0.2.118):
on the user's real `human_bundle.blend`/`Asset_bundle.blend`, a MISSING
placeholder Mesh in the library being examined (`Plane.070`, broken link)
landed on a real, non-missing LOCAL Mesh with the same generic name — content
verification correctly refused to read the missing placeholder's (nonexistent)
geometry, but the first cut of the fix then treated "couldn't verify" the
same as "safe, trust the name", auto-applying it anyway. That's backwards.

Builds a source .blend with a real "Plane.070" mesh, links it into a main
file, saves, deletes the source from disk, and reopens main.blend so Blender
marks the linked mesh a missing placeholder. Then adds a LOCAL "Plane.070"
mesh with genuinely different geometry (same shape as the real-world bug) and
runs the real Examine Library populate step, asserting the row is flagged
"unverified" and NOT staged for auto-apply.
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


def _plane(bpy, name, size):
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
        with tempfile.TemporaryDirectory() as tmp:
            source_path = str(pathlib.Path(tmp) / "source.blend")
            main_path = str(pathlib.Path(tmp) / "main.blend")

            bpy.ops.wm.read_factory_settings(use_empty=True)
            _plane(bpy, "Plane.070", 1.0)
            bpy.ops.wm.save_as_mainfile(filepath=source_path)

            bpy.ops.wm.read_factory_settings(use_empty=True)
            with bpy.data.libraries.load(source_path, link=True) as (data_from, data_to):
                data_to.meshes = list(data_from.meshes)
            # A linked datablock with no real user gets silently dropped from
            # main.blend's own save (same 0-user gotcha as source.blend's
            # helper needing use_fake_user) -- give it one via an Object in
            # the scene, same pattern as smoke_examine_library_missing_
            # collision.py's proven missing-placeholder setup.
            for m in data_to.meshes:
                obj = bpy.data.objects.new(m.name, m)
                bpy.context.scene.collection.objects.link(obj)
            bpy.ops.wm.save_as_mainfile(filepath=main_path)

            # source.blend becomes unreadable -- reopening main.blend marks its
            # linked "Plane.070" a missing placeholder (same shape as the real
            # "Unable to open ... No such file or directory" case).
            os.remove(source_path)
            bpy.ops.wm.open_mainfile(filepath=main_path)

            library = bpy.data.libraries.get("source.blend")
            checks.append(("library present", library is not None))
            missing = bpy.data.meshes.get("Plane.070")
            checks.append(("Plane.070 is a missing placeholder",
                           missing is not None and missing.is_missing))

            # A genuinely different LOCAL mesh, same generic name -- exactly
            # the real-world collision shape.
            _plane(bpy, "Plane.070", 5.0)
            checks.append(("two distinct Plane.070 meshes exist",
                           sum(1 for m in bpy.data.meshes if m.name == "Plane.070") == 2))

            if library is not None:
                n = examine._populate_examine_rows(bpy.context, library)
                checks.append(("one row populated", n == 1))
                rows = list(bpy.context.window_manager.filelink_examine_rows)
                row = rows[0] if rows else None
                checks.append(("row is Plane.070", row is not None and row.name == "Plane.070"))
                if row is not None:
                    checks.append(("suggested local", row.suggested_kind == "local"))
                    checks.append(("graph_match unverified", row.graph_match == "unverified"))
                    checks.append(("NOT auto-applied",
                                  not row.use_suggested and not row.selected))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("EXAMINE_MISSING_VS_LOCAL_SMOKE_OK" if ok else "EXAMINE_MISSING_VS_LOCAL_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("EXAMINE_MISSING_VS_LOCAL_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
