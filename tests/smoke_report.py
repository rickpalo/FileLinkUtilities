"""End-to-end report-system v2 check in Blender:

    blender --background --factory-startup --python tests/smoke_report.py

Covers persistence (two scans both kept), switching/clearing the "active"
feature (the underlying `report_store` mechanism `stash_report` and every
scan operator still relies on internally, even though the generic Reports
selector UI that used to expose it directly was deleted — Group 11 #46,
2026-06-26 — so this calls `active_feature`/`rebuild_report_rows` etc.
directly instead of through the now-removed `report_select`/`report_clear`
operators), expand toggle on the active feature, select-the-datablock, and
export to a file.
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
    Report = __import__(f"{PKG}.core.report", fromlist=["Report"]).Report
    tree_mod = __import__(f"{PKG}.core.tree", fromlist=["x"])
    store = __import__(f"{PKG}.ops.report_store", fromlist=["x"])

    checks = []
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        for nm in ("OrphanMat", "WoodA", "WoodB"):
            bpy.data.materials.new(nm).use_nodes = True
        obj = bpy.data.objects.new("Cube", bpy.data.meshes.new("CubeMesh"))
        obj.data.materials.append(bpy.data.materials["WoodA"])
        bpy.context.scene.collection.objects.link(obj)
        wm = bpy.context.window_manager

        bpy.ops.assetdoctor.scan_orphans("EXEC_DEFAULT", purge_orphans=False)   # f4
        bpy.ops.assetdoctor.material_dedup("EXEC_DEFAULT", apply=False)         # f3

        checks.append(("f4 persisted", bool(getattr(wm, "assetdoctor_rep_f4"))))
        checks.append(("f3 persisted (after f4)", bool(getattr(wm, "assetdoctor_rep_f3"))))
        checks.append(("active is last run (f3)", store.active_feature(wm) == "f3"))
        checks.append(("both selectable", {k for k, _ in store.available_features(wm)} >= {"f3", "f4"}))

        def expected_rows(feature):
            rep = Report.from_json(getattr(wm, store.data_prop(feature)))
            exp = store.get_expanded(wm, store.exp_prop(feature))
            return len(tree_mod.flatten_visible(tree_mod.report_to_tree(rep), exp))

        # Regression (blank report rows): the UIList collection is materialised
        # for the active report and tracks the active feature + its expansion.
        checks.append(("rows materialised for active (f3)",
                       len(wm.assetdoctor_report_rows) == expected_rows("f3") > 0))

        wm.assetdoctor_active_report = "f4"
        store.rebuild_report_rows(wm)
        checks.append(("switching active feature rebuilds rows", store.active_feature(wm) == "f4"))
        checks.append(("rows rebuilt on selector switch",
                       len(wm.assetdoctor_report_rows) == expected_rows("f4")))

        rep = Report.from_json(getattr(wm, "assetdoctor_rep_f4"))
        first = tree_mod.report_to_tree(rep)[0].key
        rows_collapsed = len(wm.assetdoctor_report_rows)
        before = first in store.get_expanded(wm, store.exp_prop("f4"))
        bpy.ops.assetdoctor.row_toggle(key=first, prop=store.exp_prop("f4"))
        after = first in store.get_expanded(wm, store.exp_prop("f4"))
        checks.append(("toggle flips active feature's expand", before != after))
        checks.append(("expanding a category grows the row collection",
                       len(wm.assetdoctor_report_rows) == expected_rows("f4") > rows_collapsed))

        out = os.path.join(tempfile.mkdtemp(), "rep.txt")
        bpy.ops.assetdoctor.export_report("EXEC_DEFAULT", source="report", filepath=out)
        checks.append(("export wrote a file", os.path.isfile(out) and os.path.getsize(out) > 0))

        bpy.ops.object.select_all(action="DESELECT")
        r = bpy.ops.assetdoctor.select_datablock(type="Material", name="WoodA")
        checks.append(("select material picks object", r == {"FINISHED"} and obj.select_get()))

        # Clears active (f4) -- the same logic the deleted report_clear operator had.
        active = store.active_feature(wm)
        setattr(wm, store.data_prop(active), "")
        setattr(wm, store.exp_prop(active), "")
        remaining = store.available_features(wm)
        wm.assetdoctor_active_report = remaining[0][0] if remaining else ""
        store.rebuild_report_rows(wm)
        checks.append(("clear removes active but keeps the other",
                       not getattr(wm, "assetdoctor_rep_f4") and bool(getattr(wm, "assetdoctor_rep_f3"))))
        checks.append(("rows rebuilt to remaining report after clear",
                       store.active_feature(wm) == "f3"
                       and len(wm.assetdoctor_report_rows) == expected_rows("f3")))

        # Resource UIList shares the same materialisation path.
        rnodes = [tree_mod.TreeNode(key="g", label="Group",
                                    children=[tree_mod.TreeNode(key="g:0", label="img.png")])]
        wm.assetdoctor_resource_tree = tree_mod.nodes_to_json(rnodes)
        wm.assetdoctor_resource_expanded = "g"
        store.rebuild_resource_rows(wm)
        checks.append(("resource rows materialised (parent + child)",
                       len(wm.assetdoctor_resource_rows) == 2))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("REPORT_SMOKE_OK" if ok else "REPORT_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("REPORT_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
