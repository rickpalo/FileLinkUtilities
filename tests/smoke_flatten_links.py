"""End-to-end "Find Flattenable Links" merge check in Blender:

    blender --background --factory-startup --python tests/smoke_flatten_links.py

Regression test for docs/TODO.md #41 (2026-06-26): "Find Flattenable Link
Chains" and "Find Flattenable Characters" merged into one trigger. The flat
per-object posing_override/posing_modifier rows for objects LOCAL to the
currently open file are hidden from the f7chain tree display (the grouped
picker below already shows them); rows for objects in OTHER files (reached
several hops deep, invisible to the live picker) are KEPT -- a follow-up fix
after the first version hid the whole category unconditionally and lost
visibility into remote-only results (real user report, live testing
PSM_Stage_v5.1.blend: 929 flattenable objects, zero local, nothing left to
inspect beyond a bare file-name list). The underlying stashed Report is
never touched either way -- remote_posing_files still reads the full thing.
Also covers the new ready-first/rig-first sort key used by the grouped
picker (ui.panels._flatten_group_sort_key), which is pure logic but lives in
a bpy-importing module, so it can only be exercised here.
"""

import glob
import pathlib
import sys
import tempfile
import traceback
from types import SimpleNamespace

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))
_bat = glob.glob(str(REPO_ROOT / "wheels" / "blender_asset_tracer-*.whl"))
if _bat:
    sys.path.insert(0, _bat[0])
PKG = REPO_ROOT.name


def _member(ready, is_rig, is_remote=False):
    return SimpleNamespace(ready=ready, is_rig=is_rig, is_remote=is_remote)


def _find(nodes, key):
    return next((n for n in nodes if n.key == key), None)


def _labels(node):
    return [c.label for c in node.children] if node else []


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()
    linkchain = __import__(f"{PKG}.core.linkchain", fromlist=["x"])
    Report = __import__(f"{PKG}.core.report", fromlist=["Report"]).Report
    store = __import__(f"{PKG}.ops.report_store", fromlist=["x"])
    panels = __import__(f"{PKG}.ui.panels", fromlist=["x"])

    checks = []
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        wm = bpy.context.window_manager

        # --- sort key: rig-tier beats readiness-tier beats alphabetical ----
        groups = {
            "Zeta": [_member(True, True), _member(True, True)],     # rig, all ready
            "Alpha": [_member(True, True), _member(False, True)],   # rig, partial
            "Beta": [_member(False, True), _member(False, True)],   # rig, blocked
            "Yelp": [_member(True, False)],                          # standalone, ready
            "Apple": [_member(False, False)],                        # standalone, blocked
        }
        order = sorted(groups, key=lambda r: panels._flatten_group_sort_key(r, groups[r]))
        checks.append(("sort: rigs before standalone, ready before blocked",
                       order == ["Zeta", "Alpha", "Beta", "Yelp", "Apple"]))

        # --- f7chain tree filter: LOCAL rows hidden, REMOTE rows kept ------
        tmp_root = pathlib.Path(tempfile.mkdtemp()) / "root.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(tmp_root))
        root = bpy.data.filepath

        g = linkchain.DepGraph()
        posing = [
            linkchain.ObjectPosingInfo(
                name="LocalChar", has_override=True, loc=(1.0, 0.0, 0.0),
                rot=(0.0, 0.0, 0.0), quat=(1.0, 0.0, 0.0, 0.0), size=(1.0, 1.0, 1.0),
                reference=linkchain.OverrideReference(name="LocalChar", kind="Object", library="//lib.blend"),
                source_file=root),
            linkchain.ObjectPosingInfo(
                name="LocalModChar", has_modifier=True,
                loc=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0),
                quat=(1.0, 0.0, 0.0, 0.0), size=(1.0, 1.0, 1.0),
                source_file=root),
            linkchain.ObjectPosingInfo(
                name="RemoteChar", has_override=True, loc=(2.0, 0.0, 0.0),
                rot=(0.0, 0.0, 0.0), quat=(1.0, 0.0, 0.0, 0.0), size=(1.0, 1.0, 1.0),
                reference=linkchain.OverrideReference(name="RemoteChar", kind="Object", library="//lib2.blend"),
                source_file="/proj/other.blend"),
        ]
        report = linkchain.build_chain_report(g, root, posing)
        store.stash_report(bpy.context, report, "f7chain")

        raw_categories = [f.category for f in report.findings]
        checks.append(("stashed report keeps all 3 posing findings (1 modifier + 2 override)",
                       raw_categories.count("posing_override") == 2
                       and raw_categories.count("posing_modifier") == 1))

        raw = getattr(wm, store.data_prop("f7chain"))
        reread = Report.from_json(raw)
        checks.append(("round-tripped WM data still has all 3",
                       len([f for f in reread.findings
                            if f.category in ("posing_override", "posing_modifier")]) == 3))

        _has_run, nodes = panels._feature_tree_nodes(wm, "f7chain")
        override_node = _find(nodes, "f7chain:posing_override")
        modifier_node = _find(nodes, "f7chain:posing_modifier")

        checks.append(("rendered tree's posing_override category survives (RemoteChar remains)",
                       override_node is not None))
        override_labels = " ".join(_labels(override_node))
        checks.append(("rendered posing_override hides the LOCAL row",
                       "LocalChar" not in override_labels))
        checks.append(("rendered posing_override keeps the REMOTE row",
                       "RemoteChar" in override_labels))
        checks.append(("rendered tree's posing_modifier category is gone (its only row was local)",
                       modifier_node is None))

        node_keys = {n.key for n in nodes}
        checks.append(("rendered f7chain tree keeps overview",
                       any(k.startswith("f7chain:overview") for k in node_keys)))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("FLATTEN_LINKS_SMOKE_OK" if ok else "FLATTEN_LINKS_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("FLATTEN_LINKS_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
