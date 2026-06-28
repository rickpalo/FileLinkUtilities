"""End-to-end "Evaluate Selected" check in Blender (docs/TODO.md, 2026-06-27
user request): the preview-after-harvest checkpoint that doesn't apply
anything, distinct from "Flatten Selected". Reuses
tests/smoke_flatten_selected.py's exact local-override setup (a direct
link + override_create(), same proven pattern) since this test's whole
point is to confirm Evaluate Selected builds a real, ready plan WITHOUT
mutating the scene -- not to re-prove the override-creation mechanics.

    blender --background --factory-startup --python tests/smoke_evaluate_selected.py
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

    addon = __import__(PKG)
    addon.register()
    linkchain = __import__(f"{PKG}.core.linkchain", fromlist=["x"])
    store = __import__(f"{PKG}.ops.report_store", fromlist=["x"])

    tmp = pathlib.Path(tempfile.mkdtemp())
    ultimate_path = tmp / "ultimate.blend"
    root_path = tmp / "root.blend"

    checks = []
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        obj1 = bpy.data.objects.new("Char", bpy.data.meshes.new("CharMesh"))
        bpy.context.scene.collection.objects.link(obj1)
        bpy.ops.wm.save_as_mainfile(filepath=str(ultimate_path))

        bpy.ops.wm.read_factory_settings(use_empty=True)
        with bpy.data.libraries.load(str(ultimate_path), link=True) as (data_from, data_to):
            data_to.objects = list(data_from.objects)
        char_coll = bpy.data.collections.new("CharColl")
        bpy.context.scene.collection.children.link(char_coll)
        for linked_obj in data_to.objects:
            char_coll.objects.link(linked_obj)
        bpy.context.view_layer.update()

        ov = bpy.data.objects["Char"].override_create()
        checks.append(("override_create() succeeded on a direct link", ov is not None))
        ov.location = (5.0, 5.0, 5.0)
        ov.override_library.properties.add("location")
        char_coll.objects.link(ov)
        bpy.ops.wm.save_as_mainfile(filepath=str(root_path))

        bpy.ops.wm.open_mainfile(filepath=str(root_path))
        wm = bpy.context.window_manager
        char_in_root = next((o for o in bpy.data.objects if o.override_library is not None), None)
        ref_lib = char_in_root.override_library.reference.library.filepath

        g = linkchain.DepGraph()
        g.add_edge(str(root_path), "/proj/fake_intermediate.blend")
        g.add_edge("/proj/fake_intermediate.blend", ref_lib)
        posing = [linkchain.ObjectPosingInfo(
            name="Char", has_override=True, loc=(5.0, 5.0, 5.0),
            rot=(0.0, 0.0, 0.0), quat=(1.0, 0.0, 0.0, 0.0), size=(1.0, 1.0, 1.0))]
        report = linkchain.build_chain_report(g, str(root_path), posing)
        store.stash_report(bpy.context, report, "f7chain")

        bpy.ops.assetdoctor.scan_flatten_candidates("EXEC_DEFAULT")
        before_objects = set(bpy.data.objects.keys())

        res = bpy.ops.assetdoctor.evaluate_selected("EXEC_DEFAULT")
        checks.append(("evaluate_selected FINISHED", res == {"FINISHED"}))

        after_objects = set(bpy.data.objects.keys())
        checks.append(("no new objects were created -- nothing applied",
                       after_objects == before_objects))
        old_char = bpy.data.objects.get("Char")
        checks.append(("original Char untouched (still an override, not hidden)",
                       old_char is not None and old_char.override_library is not None
                       and not old_char.hide_viewport))

        rows = {r.name: r for r in wm.assetdoctor_flatten_candidates}
        checks.append(("Char marked ready after evaluation", rows.get("Char") is not None
                       and rows["Char"].ready))

        cached = __import__("json").loads(wm.assetdoctor_flatten_plans_json or "{}")
        checks.append(("Char's plan was cached for a later Flatten Selected", "Char" in cached))

        raw = getattr(wm, store.data_prop("f7flatten"), "")
        checks.append(("f7flatten preview report was stashed", bool(raw)))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("EVALUATE_SELECTED_SMOKE_OK" if ok else "EVALUATE_SELECTED_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("EVALUATE_SELECTED_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
