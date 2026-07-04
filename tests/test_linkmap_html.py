"""Unit tests for core.linkmap_html — folder link-map → interactive HTML."""

import json

from core.blendscan import LinkRef, ScanResult
from core.graph import DepGraph
from core import linkmap_html as lh


def _ref(stored, resolved, exists, is_rel=True):
    return LinkRef(stored_path=stored, resolved_path=resolved,
                   is_relative=is_rel, exists=exists)


def _scan(root="/proj"):
    """A small project under /proj:
        scene.blend  -> chars.blend (in folder)        [intermediate target]
        scene.blend  -> /libs/materialMaster.blend     [external, exists, outside]
        chars.blend  -> /proj/missing.blend            [missing]
        lonely.blend                                   [isolated, scanned]
    """
    g = DepGraph()
    refs = {
        f"{root}/scene.blend": [
            _ref("//chars.blend", f"{root}/chars.blend", True),
            _ref("//../libs/materialMaster.blend", "/libs/materialMaster.blend", True, is_rel=True),
        ],
        f"{root}/chars.blend": [
            _ref("//missing.blend", f"{root}/missing.blend", False),
        ],
        f"{root}/lonely.blend": [],
    }
    for fkey, rs in refs.items():
        g.add_node(fkey)
        for r in rs:
            g.add_edge(fkey, r.resolved_path or r.stored_path)
    return ScanResult(graph=g, refs=refs, errors={})


def test_classification():
    scan = _scan()
    kinds = lh.classify_nodes(scan, "/proj")
    assert kinds["/proj/scene.blend"] == lh.ROOT          # nothing links it
    assert kinds["/proj/chars.blend"] == lh.INTERMEDIATE  # linked AND links
    assert kinds["/proj/lonely.blend"] == lh.ISOLATED
    assert kinds["/libs/materialMaster.blend"] == lh.EXTERNAL  # exists, outside root
    assert kinds["/proj/missing.blend"] == lh.MISSING


def test_external_takes_precedence_over_leaf():
    """A library that exists but lives outside the folder is EXTERNAL, even though
    it links nothing (which would otherwise read as a leaf)."""
    scan = _scan()
    kinds = lh.classify_nodes(scan, "/proj")
    assert kinds["/libs/materialMaster.blend"] == lh.EXTERNAL


def test_aggregate_edges_counts_duplicate_refs():
    g = DepGraph()
    g.add_node("a.blend")
    g.add_edge("a.blend", "b.blend")
    g.add_edge("a.blend", "b.blend")  # same target via two stored paths
    scan = ScanResult(graph=g, refs={}, errors={})
    agg = lh.aggregate_edges(scan)
    assert agg == [("a.blend", "b.blend", 2)]


def test_aggregate_edges_drops_self_edges():
    g = DepGraph()
    g.add_edge("a.blend", "a.blend")
    scan = ScanResult(graph=g, refs={}, errors={})
    assert lh.aggregate_edges(scan) == []


def test_cycle_edges_marked():
    g = DepGraph()
    g.add_edge("a.blend", "b.blend")
    g.add_edge("b.blend", "a.blend")
    scan = ScanResult(graph=g, refs={}, errors={})
    pairs = lh.cycle_edges(scan)
    assert ("a.blend", "b.blend") in pairs
    assert ("b.blend", "a.blend") in pairs


def test_build_graph_data_summary():
    data = lh.build_graph_data(_scan(), "/proj")
    s = data["summary"]
    assert s["files"] == 5  # scene, chars, lonely, materialMaster, missing
    assert s["roots"] == 1
    assert s["external"] == 1
    assert s["missing"] == 1
    assert s["isolated"] == 1
    assert s["cycles"] == 0
    # every node carries a kind + a hierarchical depth; every edge a count + cycle flag
    assert all("kind" in n and "depth" in n for n in data["nodes"])
    assert all("count" in e and "cycle" in e for e in data["edges"])


def test_assign_depths_layers_from_root():
    # scene -> chars -> missing ; lonely isolated ; materialMaster external leaf.
    # Depth is measured FROM THE ROOT (reverted 2026-07-04, Group 9 #30, back to
    # this ORIGINAL direction): the top-level scene that pulls everything in
    # sits at the top (0); pure assets (link nothing) sink to the bottom.
    data = lh.build_graph_data(_scan(), "/proj")
    depth = {n["id"]: n["depth"] for n in data["nodes"]}
    assert depth["/proj/scene.blend"] == 0          # root -> top
    assert depth["/proj/chars.blend"] == 1          # links missing
    assert depth["/proj/missing.blend"] == 2        # links nothing -> bottom
    assert depth["/libs/materialMaster.blend"] == 2  # external leaf -> bottom
    assert depth["/proj/lonely.blend"] == 2         # isolated -> bottom layer


def test_assign_depths_cycle_terminates():
    # A 2-cycle with no external root must not loop forever; both get finite depths.
    edges = [("a", "b", 1), ("b", "a", 1)]
    depths = lh.assign_depths(["a", "b"], edges)
    assert set(depths) == {"a", "b"}
    assert all(isinstance(d, int) and d >= 0 for d in depths.values())


def test_html_has_layout_controls():
    html = lh.build_link_map_html(_scan(), "/proj")
    for marker in ('id="zin"', 'id="zout"', 'id="zfit"', 'id="tree"', "function setTree"):
        assert marker in html


def test_build_html_is_self_contained_and_embeds_data():
    html = lh.build_link_map_html(_scan(), "/proj", title="My Map")
    assert html.startswith("<!DOCTYPE html>")
    assert "My Map" in html
    assert "const DATA =" in html
    # No external resources — fully offline.
    assert "http://" not in html and "https://" not in html
    assert "<script src" not in html
    # The embedded payload is valid JSON with our nodes.
    start = html.index("const DATA =") + len("const DATA =")
    end = html.index(";\n", start)
    payload = html[start:end].strip().replace("<\\/", "</")
    data = json.loads(payload)
    assert data["summary"]["files"] == 5


def test_unreadable_files_count_as_present():
    """A file found by the walk but unreadable still exists on disk — it must not be
    classified as a missing link."""
    g = DepGraph()
    g.add_node("/proj/corrupt.blend")
    g.add_edge("/proj/scene.blend", "/proj/corrupt.blend")
    scan = ScanResult(graph=g, refs={"/proj/scene.blend": []},
                      errors={"/proj/corrupt.blend": "BlendFileError: bad"})
    kinds = lh.classify_nodes(scan, "/proj")
    assert kinds["/proj/corrupt.blend"] != lh.MISSING
