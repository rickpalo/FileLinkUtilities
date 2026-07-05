"""End-to-end F5 Resource Analyzer check in Blender:

    blender --background --factory-startup --python tests/smoke_resource.py

Builds an image + a mesh, runs the analyzer, and verifies the resource tree is
stored on the WindowManager with correct type grouping and non-zero totals.
The panel draw is interactive-only; this covers the data pipeline.
"""

import glob
import pathlib
import sys
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
    nodes_from_json = __import__(f"{PKG}.core.tree", fromlist=["nodes_from_json"]).nodes_from_json

    checks = []
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.data.images.new("wood", 1024, 1024)  # ~4 MB RAM estimate
        me = bpy.data.meshes.new("Grid")
        me.from_pydata([(i, 0, 0) for i in range(50)], [], [])
        me.update()

        res = bpy.ops.filelink.analyze_resources("EXEC_DEFAULT")
        wm = bpy.context.window_manager
        checks.append(("FINISHED", res == {"FINISHED"}))
        checks.append(("resource tree stored", bool(wm.filelink_resource_tree)))

        nodes = nodes_from_json(wm.filelink_resource_tree)
        labels = [n.label for n in nodes]
        checks.append(("has Image + Mesh type nodes",
                       any(l.startswith("Image") for l in labels)
                       and any(l.startswith("Mesh") for l in labels)))

        image_node = next(n for n in nodes if n.label.startswith("Image"))
        wood = next((c for c in image_node.children if c.label == "wood"), None)
        checks.append(("image datablock listed with ref + real RAM column",
                       wood is not None and wood.ref == {"type": "Image", "name": "wood"}
                       and wood.ram))
        checks.append(("auto-expanded type keys",
                       set(wm.filelink_resource_expanded.split("\n")) >= {n.key for n in nodes}))

        # docs/TODO.md #15 (2026-06-27): clicking a column header re-sorts the
        # type groups cheaply (cached items, no re-scan) instead of always RAM.
        checks.append(("items cached for cheap re-sort", bool(wm.filelink_resource_items_json)))
        res_sort = bpy.ops.filelink.resource_sort_by("EXEC_DEFAULT", metric="VRAM")
        checks.append(("sort-by-VRAM FINISHED", res_sort == {"FINISHED"}))
        checks.append(("sort preference persisted", wm.filelink_resource_sort == "vram"))
        nodes_after = nodes_from_json(wm.filelink_resource_tree)
        checks.append(("re-sorted without losing type nodes",
                       {n.label for n in nodes_after} == set(labels)))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("RESOURCE_SMOKE_OK" if ok else "RESOURCE_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("RESOURCE_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
