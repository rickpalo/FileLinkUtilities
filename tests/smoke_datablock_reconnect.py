"""Datablock Reconnect vs a same-named LOCAL decoy, end-to-end:

    blender --background --factory-startup --python tests/smoke_datablock_reconnect.py

Regression test for a real bug found 2026-06-28 against the user's production
human_bundle.blend: ``ASSETDOCTOR_OT_reconnect_selected`` looked up each
placeholder via a bare ``target_coll.get(row.name)``, which is ambiguous
whenever a LOCAL data-block happens to share the exact same name as the
linked-but-missing placeholder (this project's real files routinely have
both, e.g. a local ``.NNN`` duplicate family colliding with a renamed-at-
source linked material) -- Blender's plain-name ``.get()`` silently returned
the local (non-missing) one, so every such row reported "no longer a missing
placeholder, skipped" even though the real placeholder was untouched and
still resolvable. Fixed via the ``(name, library)`` tuple form of ``.get()``.

Builds the exact collision via a real save/reopen round-trip (the only way
to legitimately produce an ``is_missing`` placeholder): a source .blend whose
material gets renamed after a file already links it under the old name, then
a LOCAL material is added under that same now-stale name before reconnecting.
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
    source_path = tmp / "source.blend"
    main_path = tmp / "main.blend"

    checks = []
    try:
        # source.blend starts out with the STALE (suffixed) name. Needs a fake
        # user or Blender drops the otherwise-unused material on save.
        bpy.ops.wm.read_factory_settings(use_empty=True)
        seed = bpy.data.materials.new("RealMat.026")
        seed.use_fake_user = True
        bpy.ops.wm.save_as_mainfile(filepath=str(source_path))

        # main.blend links it (while it still resolves) and assigns it to a
        # real mesh slot -- a real (non-fake) user, so the link itself
        # survives main.blend's own save the way production files do.
        bpy.ops.wm.read_factory_settings(use_empty=True)
        with bpy.data.libraries.load(str(source_path), link=True) as (data_from, data_to):
            data_to.materials = list(data_from.materials)
        linked = data_to.materials[0]
        mesh = bpy.data.meshes.new("HolderMesh")
        mesh.materials.append(linked)
        holder = bpy.data.objects.new("Holder", mesh)
        bpy.context.scene.collection.objects.link(holder)
        bpy.ops.wm.save_as_mainfile(filepath=str(main_path))

        # Source renames it -- the "renamed at source" case the suggester targets.
        bpy.ops.wm.open_mainfile(filepath=str(source_path))
        bpy.data.materials["RealMat.026"].name = "RealMat"
        bpy.ops.wm.save_mainfile()

        # Reopening main.blend now leaves a real is_missing placeholder still
        # named "RealMat.026". Add a LOCAL material under the exact same name --
        # the real-world collision this bug depends on.
        bpy.ops.wm.open_mainfile(filepath=str(main_path))
        placeholder = bpy.data.materials.get("RealMat.026")
        checks.append(("placeholder is_missing after reopen",
                       placeholder is not None and placeholder.is_missing))
        decoy = bpy.data.materials.new("RealMat.026")
        checks.append(("decoy got the exact colliding name (not auto-suffixed)",
                       decoy.name == "RealMat.026" and decoy.library is None))

        addon = __import__(PKG)
        addon.register()
        try:
            bpy.ops.assetdoctor.scan_reconnect_targets()
            wm = bpy.context.window_manager
            coll = wm.assetdoctor_missing_blocks
            checks.append(("exactly one missing row found", len(coll) == 1))
            row = coll[0] if len(coll) else None
            checks.append(("row auto-suggested 'RealMat' (numbered/renamed match)",
                           row is not None and row.target == "RealMat"
                           and row.confidence == "numbered" and row.selected))

            bpy.ops.assetdoctor.reconnect_selected()
            checks.append(("result message reports success, not skipped",
                           wm.assetdoctor_last_result_ok
                           and "Reconnected 1" in wm.assetdoctor_last_result
                           and "skipped" not in wm.assetdoctor_last_result))
            checks.append(("missing list now empty", len(wm.assetdoctor_missing_blocks) == 0))

            same_name = [m for m in bpy.data.materials if m.name == "RealMat.026"]
            checks.append(("only the decoy is left named RealMat.026 (placeholder removed)",
                           len(same_name) == 1 and same_name[0].library is None
                           and not same_name[0].is_missing))
            checks.append(("holder mesh's material slot now points at the real RealMat",
                           bpy.data.meshes["HolderMesh"].materials[0] is not None
                           and bpy.data.meshes["HolderMesh"].materials[0].name == "RealMat"))
        finally:
            addon.unregister()

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("DATABLOCK_RECONNECT_SMOKE_OK" if ok else "DATABLOCK_RECONNECT_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("DATABLOCK_RECONNECT_SMOKE_FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
