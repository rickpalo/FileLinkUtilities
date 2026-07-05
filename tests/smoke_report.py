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

        # Group 12 Phase 4's inline Analyze-button disclosures (docs/TODO.md
        # item 46c, 2026-07-04): toggling a node in one of these shares the
        # single "assetdoctor_detail_expanded" WM prop across every feature —
        # `focus_row` had no case for it (only the Reports tab/pickers did),
        # so the toggled row's own list never got re-pointed at, and the
        # inline template_list appeared to jump back to the top on every
        # interaction. Exercise the real operator + the real feature (matdiag).
        bpy.ops.assetdoctor.check_materials("EXEC_DEFAULT")
        mat_report = Report.from_json(getattr(wm, store.data_prop("matdiag")))
        mat_nodes = tree_mod.report_to_tree(mat_report)
        store.rebuild_inline_detail_rows(wm, "matdiag", mat_nodes, set())
        toggle_key = mat_nodes[0].key
        bpy.ops.assetdoctor.row_toggle(key=toggle_key, prop="assetdoctor_detail_expanded")
        store.rebuild_inline_detail_rows(
            wm, "matdiag", mat_nodes, store.get_expanded(wm, "assetdoctor_detail_expanded"))
        inline_rows = getattr(wm, store.inline_rows_prop("matdiag"))
        inline_idx = getattr(wm, store.inline_active_prop("matdiag"))
        checks.append(("inline-detail toggle focuses the toggled row",
                       0 <= inline_idx < len(inline_rows) and inline_rows[inline_idx].key == toggle_key))

        # Make Local's headline (docs/TODO.md item 46d, 2026-07-04): a report
        # whose only Finding is the "summary" category (no linked items, so
        # no per-library findings) already showed the real count line as its
        # headline, but didn't skip that node from the inline body -- so
        # expanding it just showed a redundant "Summary" row repeating the
        # exact same text underneath a pointless expand arrow. Exercise the
        # real headline function against a real F2 report.
        panels = __import__(f"{PKG}.ui.panels", fromlist=["x"])
        f2_mod = __import__(f"{PKG}.core.f2_makelocal", fromlist=["x"])
        empty_f2_report = f2_mod.build_makelocal_report([], all_names=[])
        f2_nodes = tree_mod.report_to_tree(empty_f2_report)
        f2_headline, f2_skip = panels._report_headline(f2_nodes, "f2", wm)
        checks.append(("Make Local headline shows the real count, not a generic fallback",
                       "linked datablock" in f2_headline and f2_headline != "✓ nothing found"))
        checks.append(("Make Local headline's node is skipped from the inline body",
                       f2_skip is f2_nodes[0]))

        # Find Flattenable Links' f7chain headline (docs/TODO.md item 46m,
        # 2026-07-04): the all-zero case adds BOTH an "overview" Finding (the
        # "0 multi-hop route(s) · ..." line, unconditional) AND a "clean"
        # Finding (core.linkchain.build_chain_report's own redundant
        # fallback, kept for its own test coverage) -- only the overview
        # node was ever skipped from the inline body, so expanding showed a
        # pointless second row repeating the same "nothing found" idea.
        linkchain_mod = __import__(f"{PKG}.core.linkchain", fromlist=["x"])
        empty_chain_report = linkchain_mod.build_chain_report(
            linkchain_mod.DepGraph(), "root.blend", [])
        chain_nodes = tree_mod.report_to_tree(empty_chain_report)
        chain_headline, chain_skip = panels._report_headline(chain_nodes, "f7chain", wm)
        checks.append(("f7chain all-zero report has both an overview and a clean node",
                       len(chain_nodes) == 2))
        checks.append(("f7chain headline skips BOTH nodes, leaving nothing to expand",
                       isinstance(chain_skip, list) and set(id(n) for n in chain_skip)
                       == set(id(n) for n in chain_nodes)))

        # Find Orphans' fake-user-only/identical sections (docs/TODO.md item
        # 46f, 2026-07-04): used to be hand-rolled box.row() loops; now share
        # ASSETDOCTOR_UL_tree via the SAME "f4" inline-rows collection every
        # other section uses. Two structurally-identical, unused, fake-user
        # materials are simultaneously "fake_only" AND clustered as
        # "identical" -- real material fixtures, real assetdoctor.scan_orphans.
        for nm in ("FakeDup1", "FakeDup2"):
            m = bpy.data.materials.new(nm)
            m.use_nodes = True
            m.use_fake_user = True
        bpy.ops.assetdoctor.scan_orphans("EXEC_DEFAULT", purge_orphans=False)
        f4_report = Report.from_json(getattr(wm, store.data_prop("f4")))
        f4_cats = {f.category for f in f4_report.findings}
        checks.append(("orphans scan produced fake_only + identical + summary",
                       {"fake_only", "identical", "summary"} <= f4_cats))
        f4_ro_findings = [f for f in f4_report.findings if f.category in ("fake_only", "identical")]
        f4_ro_report = Report(title=f4_report.title, feature=f4_report.feature, findings=f4_ro_findings)
        f4_ro_nodes = tree_mod.report_to_tree(f4_ro_report)
        checks.append(("orphans read-only sub-report excludes orphan/summary",
                       {n.key.split(":", 1)[1] for n in f4_ro_nodes} == {"fake_only", "identical"}))
        store.rebuild_inline_detail_rows(wm, "f4", f4_ro_nodes, set())
        f4_rows_collapsed = len(getattr(wm, store.inline_rows_prop("f4")))
        identical_key = next(n.key for n in f4_ro_nodes if n.key.split(":", 1)[1] == "identical")
        store.rebuild_inline_detail_rows(wm, "f4", f4_ro_nodes, {identical_key})
        f4_rows_expanded = len(getattr(wm, store.inline_rows_prop("f4")))
        checks.append(("expanding the identical-group category grows the row collection",
                       f4_rows_expanded > f4_rows_collapsed > 0))

        # Find Duplicates' collapsed sub-section (docs/TODO.md item 46j,
        # 2026-07-04): the 4 per-type buttons + the "Find All Duplicates"
        # sequencer trigger must all still be real, registered operators, and
        # the header's own live summary must reflect how many of the 4 have
        # actually run (not just a static label).
        for opname in ("scan_datablock_dups", "material_dedup", "instance_geometry",
                       "scan_content_dups", "find_duplicates"):
            checks.append((f"assetdoctor.{opname} is registered",
                           hasattr(bpy.ops.assetdoctor, opname)))
        # material_dedup already ran earlier (the "f3 persisted" check above)
        # -- reset all 4 flags for a clean, predictable baseline here.
        wm.assetdoctor_datablock_scanned = False
        wm.assetdoctor_mat_scanned = False
        wm.assetdoctor_dup_scanned = False
        setattr(wm, store.data_prop("geo"), "")
        checks.append(("duplicates summary is static before any scan",
                       panels._duplicates_overview_summary(wm) == "Find Duplicates"))
        bpy.ops.assetdoctor.scan_datablock_dups("EXEC_DEFAULT")
        checks.append(("duplicates summary counts scans once one has run",
                       panels._duplicates_overview_summary(wm) == "Find Duplicates — 1/4 scan(s) run"))

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
