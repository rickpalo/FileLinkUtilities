"""F7 Phase 4b / Phase A — multi-hop chain detection + posing classification.

Three layers, matching core/linkchain.py's own split: pure graph queries
(crafted DepGraph), pure posing classification (crafted ObjectPosingInfo, no
bpy/BAT), and a real-fixture check of the BAT read path (linkproj, skipped if
not built — same pattern as test_datablock_links.py)."""

import pathlib

import pytest

from core import linkchain
from core.depscan import DepGraph
from core.linkchain import (
    MODIFIER_DRIVEN, OVERRIDE_WITH_TRANSFORM, UNCLASSIFIED, ObjectPosingInfo,
    OverrideProperty, OverrideReference,
)

LINKPROJ = pathlib.Path(__file__).resolve().parent / "fixtures" / "linkproj"


# --- find_chains / multihop_routes ------------------------------------------

def test_find_chains_direct_only():
    g = DepGraph()
    g.add_edge("A", "B")
    paths = linkchain.find_chains(g, "A", "B")
    assert paths == [["A", "B"]]


def test_find_chains_multihop():
    g = DepGraph()
    g.add_edge("A", "B")
    g.add_edge("B", "C")
    paths = linkchain.find_chains(g, "A", "C")
    assert paths == [["A", "B", "C"]]


def test_find_chains_no_path():
    g = DepGraph()
    g.add_edge("A", "B")
    g.add_node("C")
    assert linkchain.find_chains(g, "A", "C") == []


def test_find_chains_is_cycle_safe():
    g = DepGraph()
    g.add_edge("A", "B")
    g.add_edge("B", "A")  # cycle back to the source
    g.add_edge("B", "C")
    paths = linkchain.find_chains(g, "A", "C")
    assert paths == [["A", "B", "C"]]  # terminates, doesn't loop forever


def test_find_chains_finds_both_direct_and_indirect():
    g = DepGraph()
    g.add_edge("A", "C")        # direct
    g.add_edge("A", "B")
    g.add_edge("B", "C")        # via B
    paths = {tuple(p) for p in linkchain.find_chains(g, "A", "C")}
    assert paths == {("A", "C"), ("A", "B", "C")}


def test_multihop_routes_real_motivating_case():
    """PSM_Stage links human_bundle BOTH directly AND via People1 (the real
    case that prompted Phase 4b) — multihop_routes must surface human_bundle
    with both paths, and must NOT surface a file only reached directly."""
    g = DepGraph()
    g.add_edge("PSM_Stage.blend", "human_bundle.blend")          # direct
    g.add_edge("PSM_Stage.blend", "People1.blend")
    g.add_edge("People1.blend", "human_bundle.blend")            # via People1
    g.add_edge("PSM_Stage.blend", "materialMaster.blend")        # direct only

    routes = linkchain.multihop_routes(g, "PSM_Stage.blend")
    assert "human_bundle.blend" in routes
    assert "materialMaster.blend" not in routes  # only ever reached directly
    found = {tuple(p) for p in routes["human_bundle.blend"]}
    assert ("PSM_Stage.blend", "human_bundle.blend") in found
    assert ("PSM_Stage.blend", "People1.blend", "human_bundle.blend") in found


def test_multihop_routes_excludes_source():
    g = DepGraph()
    g.add_edge("A", "B")
    assert "A" not in linkchain.multihop_routes(g, "A")


# --- classify_posing (pure) --------------------------------------------------

def _info(**kw) -> ObjectPosingInfo:
    base = dict(name="X", has_override=False, has_modifier=False,
                loc=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0),
                quat=(1.0, 0.0, 0.0, 0.0), size=(1.0, 1.0, 1.0))
    base.update(kw)
    return ObjectPosingInfo(**base)


def test_classify_override_with_adjusted_loc():
    info = _info(has_override=True, loc=(1.0, 2.0, 3.0))
    assert linkchain.classify_posing(info) == OVERRIDE_WITH_TRANSFORM


def test_classify_override_with_adjusted_rot():
    info = _info(has_override=True, rot=(0.0, 1.5, 0.0))
    assert linkchain.classify_posing(info) == OVERRIDE_WITH_TRANSFORM


def test_classify_override_with_adjusted_quat():
    info = _info(has_override=True, quat=(0.7, 0.7, 0.0, 0.0))
    assert linkchain.classify_posing(info) == OVERRIDE_WITH_TRANSFORM


def test_classify_override_with_adjusted_size():
    info = _info(has_override=True, size=(2.0, 1.0, 1.0))
    assert linkchain.classify_posing(info) == OVERRIDE_WITH_TRANSFORM


def test_classify_override_at_identity_is_unclassified():
    """An override with nothing to reapply isn't a flatten candidate -- it's a
    plain relink, not "override_with_transform"."""
    info = _info(has_override=True)
    assert linkchain.classify_posing(info) == UNCLASSIFIED


def test_classify_modifier_no_override():
    info = _info(has_modifier=True)
    assert linkchain.classify_posing(info) == MODIFIER_DRIVEN


def test_classify_neither_is_unclassified():
    info = _info()
    assert linkchain.classify_posing(info) == UNCLASSIFIED


def test_classify_override_takes_precedence_over_modifier():
    info = _info(has_override=True, has_modifier=True, loc=(5.0, 0.0, 0.0))
    assert linkchain.classify_posing(info) == OVERRIDE_WITH_TRANSFORM


# --- build_chain_report -------------------------------------------------------

def test_build_chain_report_overview_and_categories():
    g = DepGraph()
    g.add_edge("root.blend", "mid.blend")
    g.add_edge("mid.blend", "leaf.blend")
    posing = [_info(name="Char1", has_override=True, loc=(1.0, 0.0, 0.0)),
              _info(name="Prop1", has_modifier=True)]
    report = linkchain.build_chain_report(g, "root.blend", posing)
    cats = {f.category for f in report.findings}
    assert {"overview", "multihop_route", "posing_override", "posing_modifier"} <= cats
    overview = next(f for f in report.findings if f.category == "overview")
    assert "1 multi-hop route" in overview.message
    assert "1 flattenable" in overview.message


def test_build_chain_report_clean_when_nothing_found():
    g = DepGraph()
    g.add_edge("root.blend", "leaf.blend")  # direct only, no multi-hop
    report = linkchain.build_chain_report(g, "root.blend", [_info()])
    cats = {f.category for f in report.findings}
    assert "clean" in cats
    assert "multihop_route" not in cats


def test_build_chain_report_posing_items_are_selectable_refs():
    g = DepGraph()
    posing = [_info(name="Char1", has_override=True, loc=(1.0, 0.0, 0.0))]
    report = linkchain.build_chain_report(g, "root.blend", posing)
    f = next(f for f in report.findings if f.category == "posing_override")
    assert f.items == ["Object/Char1"]  # "Type/Name" -- core.tree._parse_ref recognises this


# --- read_override_reference (stubbed BAT blocks -- the real DNA paths were
# confirmed against actual production overrides via a one-off probe script,
# 2026-06-25, not a synthetic fixture; see docs/TODO.md and the module
# docstring) ------------------------------------------------------------------

class _StubBlock:
    """Minimal stand-in for a BAT BlendFileBlock: maps path-tuples to values."""

    def __init__(self, gets: dict = None, pointers: dict = None):
        self._gets = gets or {}
        self._pointers = pointers or {}

    def get(self, path, as_str=False, default=None):
        return self._gets.get(path, default)

    def get_pointer(self, path, default=None):
        return self._pointers.get(path, default)


def test_read_override_reference_resolves_name_kind_and_library():
    lib_block = _StubBlock(gets={(b"name",): "//libs/human_bundle.blend"})
    ref_block = _StubBlock(gets={(b"name",): "OBbonnet"},
                            pointers={(b"lib",): lib_block})
    ov_block = _StubBlock(pointers={(b"reference",): ref_block})
    ref = linkchain.read_override_reference(ov_block)
    assert ref == OverrideReference(name="bonnet", kind="Object",
                                    library="//libs/human_bundle.blend")


def test_read_override_reference_no_reference_pointer():
    ov_block = _StubBlock()
    assert linkchain.read_override_reference(ov_block) is None


def test_read_override_reference_no_library():
    ref_block = _StubBlock(gets={(b"name",): "GRchild_older"})
    ov_block = _StubBlock(pointers={(b"reference",): ref_block})
    ref = linkchain.read_override_reference(ov_block)
    assert ref == OverrideReference(name="child_older", kind="Collection", library="")


# --- build_chain_report cross-referencing (override <-> multihop chain) -----

def test_build_chain_report_attributes_override_to_its_chain():
    g = DepGraph()
    g.add_edge("root.blend", "human_bundle.blend")
    g.add_edge("root.blend", "people1.blend")
    g.add_edge("people1.blend", "human_bundle.blend")
    ref = OverrideReference(name="bonnet", kind="Object", library="//libs/human_bundle.blend")
    posing = [_info(name="Char1", has_override=True, loc=(1.0, 0.0, 0.0), reference=ref)]
    report = linkchain.build_chain_report(g, "root.blend", posing)
    f = next(f for f in report.findings if f.category == "posing_override")
    assert "overrides Object/bonnet from human_bundle.blend" in f.message
    assert "reached via" in f.message


def test_build_chain_report_override_linked_directly_no_chain():
    g = DepGraph()
    g.add_edge("root.blend", "human_bundle.blend")  # direct only, no multi-hop
    ref = OverrideReference(name="bonnet", kind="Object", library="//libs/human_bundle.blend")
    posing = [_info(name="Char1", has_override=True, loc=(1.0, 0.0, 0.0), reference=ref)]
    report = linkchain.build_chain_report(g, "root.blend", posing)
    f = next(f for f in report.findings if f.category == "posing_override")
    assert "linked directly, no multi-hop chain to flatten" in f.message


# --- transform_differs_from_identity -----------------------------------------

def test_transform_differs_from_identity_true_on_loc():
    assert linkchain.transform_differs_from_identity(
        (1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), (1.0, 1.0, 1.0))


def test_transform_differs_from_identity_false_at_identity():
    assert not linkchain.transform_differs_from_identity(
        (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), (1.0, 1.0, 1.0))


# --- build_flatten_plan (Phase B) ---------------------------------------------

def _prop(path="location", value=(1.0, 2.0, 3.0)) -> OverrideProperty:
    return OverrideProperty(rna_path=path, value=value)


def test_build_flatten_plan_matches_route():
    routes = {"human_bundle.blend": [["root.blend", "human_bundle.blend"],
                                      ["root.blend", "people1.blend", "human_bundle.blend"]]}
    ref = OverrideReference(name="bonnet", kind="Object", library="//libs/human_bundle.blend")
    plan = linkchain.build_flatten_plan("Char1", ref, [_prop()], routes)
    assert plan.ultimate_library == "human_bundle.blend"
    assert plan.route == ["root.blend", "people1.blend", "human_bundle.blend"]
    assert plan.warnings == []


def test_build_flatten_plan_linked_directly_no_chain():
    ref = OverrideReference(name="bonnet", kind="Object", library="//libs/human_bundle.blend")
    plan = linkchain.build_flatten_plan("Char1", ref, [_prop()], {})
    assert plan.route is None
    assert plan.ultimate_library == ref.library
    assert "no multi-hop chain to flatten" in plan.warnings[0]


def test_build_flatten_plan_no_reference():
    plan = linkchain.build_flatten_plan("Char1", None, [_prop()], {})
    assert plan.route is None
    assert plan.ultimate_library is None
    assert "could not be determined" in plan.warnings[0]


def test_build_flatten_plan_no_properties_warns():
    ref = OverrideReference(name="bonnet", kind="Object", library="//libs/human_bundle.blend")
    plan = linkchain.build_flatten_plan("Char1", ref, [], {})
    assert "no override properties found to replay" in plan.warnings


# --- routes_from_report --------------------------------------------------------

def test_routes_from_report_round_trips_build_chain_report():
    g = DepGraph()
    g.add_edge("root.blend", "human_bundle.blend")
    g.add_edge("root.blend", "people1.blend")
    g.add_edge("people1.blend", "human_bundle.blend")
    report = linkchain.build_chain_report(g, "root.blend", [])
    routes = linkchain.routes_from_report(report)
    assert "human_bundle.blend" in routes
    found = {tuple(p) for p in routes["human_bundle.blend"]}
    assert ("root.blend", "human_bundle.blend") in found
    assert ("root.blend", "people1.blend", "human_bundle.blend") in found


# --- flatten_plan_to_dict / from_dict (cache round-trip) ----------------------

def test_flatten_plan_round_trips_through_dict():
    routes = {"human_bundle.blend": [["root.blend", "people1.blend", "human_bundle.blend"]]}
    ref = OverrideReference(name="bonnet", kind="Object", library="//libs/human_bundle.blend")
    plan = linkchain.build_flatten_plan("Char1", ref, [_prop()], routes)
    restored = linkchain.flatten_plan_from_dict(linkchain.flatten_plan_to_dict(plan))
    assert restored == plan


def test_flatten_plan_round_trips_with_no_reference_or_properties():
    plan = linkchain.build_flatten_plan("Char1", None, [], {})
    restored = linkchain.flatten_plan_from_dict(linkchain.flatten_plan_to_dict(plan))
    assert restored == plan


# --- build_flatten_plan_report -------------------------------------------------

def test_build_flatten_plan_report_overview_and_finding():
    routes = {"human_bundle.blend": [["root.blend", "people1.blend", "human_bundle.blend"]]}
    ref = OverrideReference(name="bonnet", kind="Object", library="//libs/human_bundle.blend")
    plan = linkchain.build_flatten_plan("Char1", ref, [_prop()], routes)
    report = linkchain.build_flatten_plan_report([plan])
    cats = {f.category for f in report.findings}
    assert {"overview", "flatten_plan"} <= cats
    overview = next(f for f in report.findings if f.category == "overview")
    assert "1 of 1" in overview.message
    finding = next(f for f in report.findings if f.category == "flatten_plan")
    assert finding.items == ["Object/Char1"]
    assert "human_bundle.blend" in finding.message


def test_build_flatten_plan_report_blocked_plan_gets_warning_finding():
    ref = OverrideReference(name="bonnet", kind="Object", library="//libs/human_bundle.blend")
    plan = linkchain.build_flatten_plan("Char1", ref, [], {})
    report = linkchain.build_flatten_plan_report([plan])
    warn = next(f for f in report.findings if f.category == "flatten_warning")
    assert "Char1" in warn.message


def test_build_flatten_plan_report_clean_when_empty():
    report = linkchain.build_flatten_plan_report([])
    cats = {f.category for f in report.findings}
    assert "clean" in cats


# --- real fixture: BAT read path ---------------------------------------------

pytestmark = pytest.mark.skipif(
    not (LINKPROJ / "libA.blend").is_file(),
    reason="linkproj fixtures not built",
)


def test_classify_objects_real_fixture_no_override_no_modifier():
    """libA.blend's local Tree object has neither an override nor a modifier
    -- confirms the DNA field paths resolve cleanly (no exception) even when
    both signals are absent, and round-trip through classify_posing."""
    infos = linkchain.classify_objects(LINKPROJ / "libA.blend")
    assert infos
    tree = next(i for i in infos if i.name == "Tree")
    assert tree.has_override is False
    assert tree.has_modifier is False
    assert tree.loc == (0.0, 0.0, 0.0)
    assert tree.size == (1.0, 1.0, 1.0)
    assert linkchain.classify_posing(tree) == UNCLASSIFIED
