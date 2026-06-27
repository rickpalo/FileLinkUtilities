"""Unit tests for F7 Phase 2 core: core.datablock_graph."""

from core import datablock_graph as dg
from core.datablock_graph import LiveExtract


def test_strip_dup_suffix():
    assert dg.strip_dup_suffix("MECC_Base_Body.008") == "MECC_Base_Body"
    assert dg.strip_dup_suffix("KEKey.553") == "KEKey"
    assert dg.strip_dup_suffix("Body") == "Body"
    assert dg.strip_dup_suffix("Mat.2") == "Mat.2"  # single digit: not a dup suffix


def test_duplicate_families():
    names = ["Body", "Body.001", "Body.002", "Hair", "Stone.010"]
    fams = dg.duplicate_families(names)
    assert fams == {"Body": ["Body", "Body.001", "Body.002"]}  # Hair unique, Stone.010 alone


def test_duplicate_families_copies_without_base():
    # The original may be gone; the numbered copies still form a family.
    fams = dg.duplicate_families(["KEKey.551", "KEKey.552", "KEKey.553"])
    assert fams == {"KEKey": ["KEKey.551", "KEKey.552", "KEKey.553"]}


def test_find_datablock_loops():
    edges = [("Object/Body", "Mesh/Body"), ("Mesh/Body", "Key/KEKey"),
             ("Key/KEKey", "Object/Body")]  # cycle
    loops = dg.find_datablock_loops(edges)
    assert any({"Object/Body", "Mesh/Body", "Key/KEKey"} <= set(c) for c in loops)


def test_find_datablock_loops_acyclic():
    edges = [("a", "b"), ("b", "c")]
    assert dg.find_datablock_loops(edges) == []


def test_find_datablock_loops_ignores_self_edges():
    # an id that is its own user (modifier/driver/constraint) is not a real loop
    assert dg.find_datablock_loops([("Object/Rig", "Object/Rig")]) == []
    # but a genuine 2-datablock loop is still reported
    assert dg.find_datablock_loops([("a", "b"), ("b", "a")])


def test_find_datablock_loops_excludes_shape_key_reciprocal_pair():
    """A Mesh<->its own Key (shape_keys / Key.user mirror each other) is
    intrinsic Blender plumbing -- not a real override-resync-loop bug (real
    user report, 2026-06-25: "what type of a key is that, to help understand
    the loop")."""
    edges = [("Mesh/CC_Base_Body.038", "Key/Key.296"),
             ("Key/Key.296", "Mesh/CC_Base_Body.038")]
    assert dg.find_datablock_loops(edges) == []


def test_build_live_report():
    extract = LiveExtract(
        totals={"Material": 10},
        library_counts=[("human_bundle.blend", 42)],
        override_count=5,
        loops=[["Object/Body", "Mesh/Body", "Object/Body"]],
    )
    report = dg.build_live_report(extract, "test.blend")
    assert report.feature == "f7live"
    cats = {f.category for f in report.findings}
    assert {"overview", "override_loop", "library_block"} <= cats
    assert "summary" not in cats  # redundant with "overview" — dropped (user, 2026-06-23)
    assert "duplicate_family" not in cats  # removed 2026-06-26 — see Find Duplicate Data-blocks
    overview = [f for f in report.findings if f.category == "overview"][0]
    assert "1 override loop(s)" in overview.message
    assert "1 library" in overview.message
    assert "5 override(s)" in overview.message


def test_build_live_report_shape_key_risks():
    extract = LiveExtract(shape_key_risks=[("KEKey.553", "CC_Base_Body.038")])
    report = dg.build_live_report(extract, "test.blend")
    risks = [f for f in report.findings if f.category == "shape_key_override_risk"]
    assert len(risks) == 1
    assert "KEKey.553" in risks[0].message
    assert "CC_Base_Body.038" in risks[0].message
    assert risks[0].items == ["Mesh/CC_Base_Body.038"]


def test_build_live_report_no_shape_key_risks_by_default():
    report = dg.build_live_report(LiveExtract())
    assert not any(f.category == "shape_key_override_risk" for f in report.findings)


def test_build_live_report_loops_skipped():
    extract = LiveExtract(loops_skipped="graph too large (250000 nodes)")
    report = dg.build_live_report(extract)
    warn = [f for f in report.findings
            if f.category == "override_loop" and f.severity == "warning"]
    assert warn and "skipped" in warn[0].message.lower()
