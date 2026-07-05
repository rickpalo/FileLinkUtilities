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


def test_build_chain_report_multihop_route_message_and_items():
    """docs/TODO.md #40 (a)/(b): the route message no longer repeats the
    root's own name (we're already scoped to the open file), and no longer
    inlines the whole chain as one string -- each hop is its own item instead,
    for the UI to render as one row per hop."""
    g = DepGraph()
    g.add_edge("root.blend", "mid.blend")
    g.add_edge("mid.blend", "leaf.blend")
    report = linkchain.build_chain_report(g, "root.blend", [])
    f = next(f for f in report.findings if f.category == "multihop_route")
    assert "root" not in f.message
    assert "leaf" in f.message
    assert " -> " not in f.message
    assert f.items == ["mid", "leaf"]


def test_build_chain_report_multihop_route_notes_also_linked_directly():
    g = DepGraph()
    g.add_edge("root.blend", "leaf.blend")
    g.add_edge("root.blend", "mid.blend")
    g.add_edge("mid.blend", "leaf.blend")
    report = linkchain.build_chain_report(g, "root.blend", [])
    f = next(f for f in report.findings if f.category == "multihop_route")
    assert "(also linked directly)" in f.message
    assert f.data["has_direct"] is True


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


def test_build_chain_report_tags_posing_source_file_when_set():
    """A character found several hops deep (not in root.blend) names its own
    file in the message -- the 2026-06-25 fix that censuses every visited
    file, not just root, so a character ISN'T mistaken for living in root."""
    g = DepGraph()
    g.add_edge("root.blend", "people1.blend")
    posing = [_info(name="Char1", has_override=True, loc=(1.0, 0.0, 0.0),
                    source_file="//libs/people1.blend")]
    report = linkchain.build_chain_report(g, "root.blend", posing)
    f = next(f for f in report.findings if f.category == "posing_override")
    assert "(in people1)" in f.message  # ".blend" dropped from display (item 5b)


def test_build_chain_report_no_file_tag_when_source_file_unset():
    g = DepGraph()
    posing = [_info(name="Char1", has_override=True, loc=(1.0, 0.0, 0.0))]
    report = linkchain.build_chain_report(g, "root.blend", posing)
    f = next(f for f in report.findings if f.category == "posing_override")
    assert "(in " not in f.message


def test_build_chain_report_posing_override_carries_source_file_in_data():
    """remote_posing_files (Phase B's "found, but elsewhere" fallback) reads
    this back out -- it must be structured data, not just message text."""
    g = DepGraph()
    posing = [_info(name="Char1", has_override=True, loc=(1.0, 0.0, 0.0),
                    source_file="//libs/people1.blend")]
    report = linkchain.build_chain_report(g, "root.blend", posing)
    f = next(f for f in report.findings if f.category == "posing_override")
    assert f.data["source_file"] == "//libs/people1.blend"


# --- remote_posing_files ------------------------------------------------------

def test_remote_posing_files_finds_characters_in_other_files():
    """The real motivating case: the currently open file (a Stage file) holds
    zero local overrides, but Find Flattenable Link Chains already found some
    several hops deep in People1.blend -- the live picker must be able to
    point the user there instead of just reporting "nothing found"."""
    g = DepGraph()
    g.add_edge("/proj/stage.blend", "/proj/people1.blend")
    posing = [_info(name="Char1", has_override=True, loc=(1.0, 0.0, 0.0),
                    source_file="/proj/people1.blend")]
    report = linkchain.build_chain_report(g, "/proj/stage.blend", posing)
    assert linkchain.remote_posing_files(report, "/proj/stage.blend") == ["people1"]


def test_remote_posing_files_excludes_the_current_file():
    g = DepGraph()
    posing = [_info(name="Char1", has_override=True, loc=(1.0, 0.0, 0.0),
                    source_file="/proj/stage.blend")]
    report = linkchain.build_chain_report(g, "/proj/stage.blend", posing)
    assert linkchain.remote_posing_files(report, "/proj/stage.blend") == []


def test_remote_posing_files_empty_when_no_posing_overrides():
    g = DepGraph()
    report = linkchain.build_chain_report(g, "/proj/stage.blend", [])
    assert linkchain.remote_posing_files(report, "/proj/stage.blend") == []


def test_remote_posing_files_dedupes_and_sorts():
    g = DepGraph()
    posing = [_info(name="Char1", has_override=True, loc=(1.0, 0.0, 0.0),
                    source_file="/proj/people1.blend"),
              _info(name="Char2", has_override=True, loc=(1.0, 0.0, 0.0),
                    source_file="/proj/people1.blend"),
              _info(name="Char3", has_override=True, loc=(1.0, 0.0, 0.0),
                    source_file="/proj/another.blend")]
    report = linkchain.build_chain_report(g, "/proj/stage.blend", posing)
    assert linkchain.remote_posing_files(report, "/proj/stage.blend") == [
        "another", "people1"]


# --- drop_local_posing_findings -----------------------------------------------

def test_drop_local_posing_findings_drops_only_the_current_files_rows():
    """docs/TODO.md #41 follow-up: the live picker only ever sees objects
    local to the open file, so local posing_override/posing_modifier rows are
    pure duplication -- but a remote one (several hops deep) has no other
    home and must survive."""
    g = DepGraph()
    posing = [_info(name="LocalChar", has_override=True, loc=(1.0, 0.0, 0.0),
                    source_file="/proj/stage.blend"),
              _info(name="RemoteChar", has_override=True, loc=(1.0, 0.0, 0.0),
                    source_file="/proj/people1.blend")]
    report = linkchain.build_chain_report(g, "/proj/stage.blend", posing)
    filtered = linkchain.drop_local_posing_findings(report, "/proj/stage.blend")
    names = [f.message for f in filtered.findings if f.category == "posing_override"]
    assert not any("LocalChar" in m for m in names)
    assert any("RemoteChar" in m for m in names)


def test_drop_local_posing_findings_drops_local_modifier_rows_too():
    g = DepGraph()
    posing = [_info(name="LocalChar", has_modifier=True, source_file="/proj/stage.blend")]
    report = linkchain.build_chain_report(g, "/proj/stage.blend", posing)
    filtered = linkchain.drop_local_posing_findings(report, "/proj/stage.blend")
    assert not any(f.category == "posing_modifier" for f in filtered.findings)


def test_drop_local_posing_findings_keeps_everything_else_untouched():
    """multihop_route/overview findings, and the original report object
    itself, must be unaffected -- this only ever filters the two posing
    categories on a COPY."""
    g = DepGraph()
    g.add_edge("/proj/stage.blend", "/proj/people1.blend")
    posing = [_info(name="LocalChar", has_override=True, loc=(1.0, 0.0, 0.0),
                    source_file="/proj/stage.blend")]
    report = linkchain.build_chain_report(g, "/proj/stage.blend", posing)
    before = len(report.findings)
    filtered = linkchain.drop_local_posing_findings(report, "/proj/stage.blend")
    assert len(report.findings) == before  # original untouched
    assert any(f.category == "overview" for f in filtered.findings)


def test_drop_local_posing_findings_keeps_rows_with_no_source_file():
    """An unset source_file is ambiguous, not provably local -- fail toward
    keeping it visible rather than silently hiding it."""
    g = DepGraph()
    posing = [_info(name="Char1", has_override=True, loc=(1.0, 0.0, 0.0))]  # source_file=""
    report = linkchain.build_chain_report(g, "/proj/stage.blend", posing)
    filtered = linkchain.drop_local_posing_findings(report, "/proj/stage.blend")
    assert any(f.category == "posing_override" for f in filtered.findings)


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


# --- read_attach_target (stubbed BAT blocks -- DNA paths confirmed 2026-06-27
# via a synthetic-fixture probe, not production data; see docs/TODO.md and the
# function's own docstring) ----------------------------------------------------

def _ob_block(name: str) -> _StubBlock:
    return _StubBlock(gets={(b"id", b"name"): f"OB{name}"})


def _modifier_block(mtype, target=None, subtarget="", nxt=None) -> _StubBlock:
    pointers = {(b"modifier", b"next"): nxt}
    if target is not None:
        pointers[(b"object",)] = target
    return _StubBlock(gets={(b"modifier", b"type"): mtype, (b"subtarget",): subtarget},
                      pointers=pointers)


def test_read_attach_target_finds_armature_modifier():
    rig = _ob_block("Rig")
    mod = _modifier_block(linkchain._MOD_TYPE_ARMATURE, target=rig)
    block = _StubBlock(pointers={(b"modifiers", b"first"): mod})
    assert linkchain.read_attach_target(block) == ("Rig", "")


def test_read_attach_target_finds_hook_modifier_with_subtarget():
    rig = _ob_block("Rig")
    mod = _modifier_block(linkchain._MOD_TYPE_HOOK, target=rig, subtarget="Bone")
    block = _StubBlock(pointers={(b"modifiers", b"first"): mod})
    assert linkchain.read_attach_target(block) == ("Rig", "Bone")


def test_read_attach_target_skips_unrelated_modifier_types():
    rig = _ob_block("Rig")
    subsurf = _modifier_block(99, target=rig)  # not Armature/Hook
    block = _StubBlock(pointers={(b"modifiers", b"first"): subsurf})
    assert linkchain.read_attach_target(block) == ("", "")


def test_read_attach_target_walks_modifier_linked_list():
    rig = _ob_block("Rig")
    second = _modifier_block(linkchain._MOD_TYPE_ARMATURE, target=rig)
    first = _modifier_block(99, nxt=second)  # an irrelevant modifier comes first
    block = _StubBlock(pointers={(b"modifiers", b"first"): first})
    assert linkchain.read_attach_target(block) == ("Rig", "")


def test_read_attach_target_finds_child_of_constraint():
    rig = _ob_block("Rig")
    data = _StubBlock(gets={(b"subtarget",): "Bone"}, pointers={(b"tar",): rig})
    con = _StubBlock(gets={(b"type",): linkchain._CONSTRAINT_TYPE_CHILD_OF},
                      pointers={(b"data",): data})
    block = _StubBlock(pointers={(b"constraints", b"first"): con})
    assert linkchain.read_attach_target(block) == ("Rig", "Bone")


def test_read_attach_target_skips_unrelated_constraint_types():
    con = _StubBlock(gets={(b"type",): 7})  # not Child Of
    block = _StubBlock(pointers={(b"constraints", b"first"): con})
    assert linkchain.read_attach_target(block) == ("", "")


def test_read_attach_target_none_when_no_modifiers_or_constraints():
    block = _StubBlock()
    assert linkchain.read_attach_target(block) == ("", "")


def _ob_placeholder_block(name: str) -> _StubBlock:
    """A generic ``ID`` placeholder block (bare ``name``, no ``id`` wrapper)
    -- what a plain link nobody individually overrode looks like, the same
    shape ``read_override_reference`` already documents for
    ``override_library.reference``."""
    return _StubBlock(gets={(b"name",): f"OB{name}"})


def test_read_attach_target_finds_armature_modifier_via_bare_link_placeholder():
    """A shared rig template nobody locally overrode has no real OB block --
    only a generic ID placeholder (bare `name`, no `id` wrapper). The
    attach-target walk must still resolve its name (2026-06-27 fix, real
    production data -- this is why most characters in a donor file with a
    shared, never-locally-overridden rig fell back to an unresolved
    "standalone" group)."""
    rig = _ob_placeholder_block("Rig")
    mod = _modifier_block(linkchain._MOD_TYPE_ARMATURE, target=rig)
    block = _StubBlock(pointers={(b"modifiers", b"first"): mod})
    assert linkchain.read_attach_target(block) == ("Rig", "")


# --- read_object_posing hierarchy fields (stubbed BAT blocks) -----------------

def test_read_object_posing_detects_mesh_kind_parent_and_attach_target():
    rig_target = _ob_block("Rig")
    mesh_data = _StubBlock(gets={(b"id", b"name"): "MEBonnetData"})
    mod = _modifier_block(linkchain._MOD_TYPE_ARMATURE, target=rig_target)
    parent_block = _ob_block("Hat")
    block = _StubBlock(
        gets={(b"id", b"name"): "OBBonnet",
              (b"loc",): [0.0, 0.0, 0.0], (b"rot",): [0.0, 0.0, 0.0],
              (b"quat",): [1.0, 0.0, 0.0, 0.0], (b"size",): [1.0, 1.0, 1.0]},
        pointers={(b"data",): mesh_data, (b"parent",): parent_block,
                  (b"modifiers", b"first"): mod})
    info = linkchain.read_object_posing(block, source_file="char.blend")
    assert info.obj_kind == "Mesh"
    assert info.parent_name == "Hat"
    assert info.attach_target == "Rig"
    assert info.attach_subtarget == ""
    assert info.source_file == "char.blend"


def test_read_object_posing_detects_armature_kind():
    arm_data = _StubBlock(gets={(b"id", b"name"): "ARRigData"})
    block = _StubBlock(
        gets={(b"id", b"name"): "OBRig",
              (b"loc",): [0.0, 0.0, 0.0], (b"rot",): [0.0, 0.0, 0.0],
              (b"quat",): [1.0, 0.0, 0.0, 0.0], (b"size",): [1.0, 1.0, 1.0]},
        pointers={(b"data",): arm_data})
    info = linkchain.read_object_posing(block)
    assert info.obj_kind == "Armature"
    assert info.parent_name == ""
    assert info.attach_target == ""


def test_read_object_posing_detects_kind_via_bare_link_placeholder_data():
    """The object's own data (e.g. shared mesh data nobody individually
    overrode) can also be a bare-link placeholder -- obj_kind must still
    resolve (2026-06-27 fix; previously fell back to "" -> a generic
    "Object (standalone)" group instead of the real type)."""
    mesh_data_placeholder = _StubBlock(gets={(b"name",): "MEBonnetData"})
    block = _StubBlock(
        gets={(b"id", b"name"): "OBBonnet",
              (b"loc",): [0.0, 0.0, 0.0], (b"rot",): [0.0, 0.0, 0.0],
              (b"quat",): [1.0, 0.0, 0.0, 0.0], (b"size",): [1.0, 1.0, 1.0]},
        pointers={(b"data",): mesh_data_placeholder})
    info = linkchain.read_object_posing(block)
    assert info.obj_kind == "Mesh"


def test_read_object_posing_resolves_parent_via_bare_link_placeholder():
    parent_placeholder = _ob_placeholder_block("Rig")
    block = _StubBlock(
        gets={(b"id", b"name"): "OBBonnet",
              (b"loc",): [0.0, 0.0, 0.0], (b"rot",): [0.0, 0.0, 0.0],
              (b"quat",): [1.0, 0.0, 0.0, 0.0], (b"size",): [1.0, 1.0, 1.0]},
        pointers={(b"parent",): parent_placeholder})
    info = linkchain.read_object_posing(block)
    assert info.parent_name == "Rig"


# --- build_offline_rig_index (pure) -------------------------------------------

def _hier(name, obj_kind="Mesh", parent_name="", attach_target="", source_file="a.blend"):
    return ObjectPosingInfo(name=name, obj_kind=obj_kind, parent_name=parent_name,
                            attach_target=attach_target, source_file=source_file)


def test_build_offline_rig_index_self_is_armature():
    posing = [_hier("Rig", obj_kind="Armature")]
    assert linkchain.build_offline_rig_index(posing) == {("a.blend", "Rig"): "Rig"}


def test_build_offline_rig_index_via_attach_target():
    posing = [_hier("Rig", obj_kind="Armature"), _hier("Bonnet", attach_target="Rig")]
    index = linkchain.build_offline_rig_index(posing)
    assert index[("a.blend", "Bonnet")] == "Rig"


def test_build_offline_rig_index_via_parent_chain():
    posing = [_hier("Rig", obj_kind="Armature"),
              _hier("Body", parent_name="Rig"),
              _hier("Sleeve", parent_name="Body")]
    index = linkchain.build_offline_rig_index(posing)
    assert index[("a.blend", "Sleeve")] == "Rig"
    assert index[("a.blend", "Body")] == "Rig"


def test_build_offline_rig_index_falls_back_to_parent_when_attach_target_is_not_an_armature():
    posing = [_hier("Rig", obj_kind="Armature"),
              _hier("Empty", obj_kind="Empty", parent_name="Rig"),
              _hier("Prop", attach_target="Empty", parent_name="Rig")]
    index = linkchain.build_offline_rig_index(posing)
    assert index[("a.blend", "Prop")] == "Rig"


def test_build_offline_rig_index_no_rig_found():
    posing = [_hier("Lonely")]
    assert linkchain.build_offline_rig_index(posing) == {("a.blend", "Lonely"): ""}


def test_build_offline_rig_index_scoped_per_file_no_cross_file_collision():
    """Two unrelated donor files both happen to have an object named "Rig" --
    a name collision across files must never let one resolve against the
    other's hierarchy."""
    posing = [
        _hier("Rig", obj_kind="Armature", source_file="a.blend"),
        _hier("Bonnet", attach_target="Rig", source_file="a.blend"),
        _hier("Rig", obj_kind="Mesh", source_file="b.blend"),  # NOT an armature in b.blend
        _hier("Sword", attach_target="Rig", source_file="b.blend"),
    ]
    index = linkchain.build_offline_rig_index(posing)
    assert index[("a.blend", "Bonnet")] == "Rig"
    assert index[("b.blend", "Sword")] == ""  # b.blend's "Rig" isn't an armature


def test_build_offline_rig_index_is_cycle_safe():
    """A corrupted/cyclic parent chain must not infinite-loop."""
    posing = [_hier("A", parent_name="B"), _hier("B", parent_name="A")]
    index = linkchain.build_offline_rig_index(posing)
    assert index[("a.blend", "A")] == ""
    assert index[("a.blend", "B")] == ""


# --- posing_list_to_dict / from_dict (cache round-trip) -----------------------

def test_posing_list_round_trips_through_dict():
    posing = [linkchain.ObjectPosingInfo(
        name="Bonnet", has_override=True, loc=(1.0, 2.0, 3.0), rot=(0.0, 0.0, 0.0),
        quat=(1.0, 0.0, 0.0, 0.0), size=(1.0, 1.0, 1.0),
        reference=OverrideReference(name="bonnet", kind="Object", library="//lib.blend"),
        source_file="char.blend", obj_kind="Mesh", parent_name="Rig",
        attach_target="Rig", attach_subtarget="")]
    restored = linkchain.posing_list_from_dict(linkchain.posing_list_to_dict(posing))
    assert restored == posing


def test_posing_list_round_trips_with_no_reference():
    posing = [linkchain.ObjectPosingInfo(name="Plain", source_file="char.blend")]
    restored = linkchain.posing_list_from_dict(linkchain.posing_list_to_dict(posing))
    assert restored == posing


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
    assert "overrides Object/bonnet from human_bundle" in f.message  # ".blend" dropped (item 5b)
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


# --- is_direct_link_only (2026-06-27 user feedback) ---------------------------

def test_is_direct_link_only_true_when_no_route_exists():
    ref = OverrideReference(name="bonnet", kind="Object", library="//libs/human_bundle.blend")
    assert linkchain.is_direct_link_only(ref, {}) is True


def test_is_direct_link_only_false_when_route_exists():
    ref = OverrideReference(name="bonnet", kind="Object", library="//libs/human_bundle.blend")
    routes = {"human_bundle.blend": [["root.blend", "people1.blend", "human_bundle.blend"]]}
    assert linkchain.is_direct_link_only(ref, routes) is False


def test_is_direct_link_only_false_when_reference_unknown():
    """An undetermined reference is a different, worth-surfacing problem --
    must NOT be silently excluded the same way a confirmed direct link is."""
    assert linkchain.is_direct_link_only(None, {}) is False


def test_is_direct_link_only_false_when_reference_has_no_library():
    ref = OverrideReference(name="bonnet", kind="Object", library="")
    assert linkchain.is_direct_link_only(ref, {}) is False


# --- summarize_properties / build_rig_rollup (2026-06-25 user feedback) -------

def test_summarize_properties_counts_posed_bones_once_per_name():
    props = [
        _prop('pose.bones["Hand_L"].location', (1.0, 0.0, 0.0)),
        _prop('pose.bones["Hand_L"].rotation_quaternion', (1.0, 0.0, 0.0, 0.0)),
        _prop('pose.bones["Hand_R"].location', (0.0, 0.0, 0.0)),
    ]
    summary = linkchain.summarize_properties(props)
    assert "2 bone(s) posed" in summary


def test_summarize_properties_detects_animation_override():
    props = [_prop("animation_data.action", "Action/Walk")]
    assert "animation override" in linkchain.summarize_properties(props)


def test_summarize_properties_bare_transform_and_material_and_modifier():
    props = [
        _prop("location", (1.0, 2.0, 3.0)),
        _prop("scale", (1.0, 1.0, 1.0)),
        _prop("material_slots[0].material", "Material/Skin"),
        _prop('modifiers["Armature"].object', "Object/Rig"),
        _prop("parent", "Object/Rig"),
    ]
    summary = linkchain.summarize_properties(props)
    assert "2 transform adjustment(s)" in summary
    assert "1 material override(s)" in summary
    assert "1 modifier override(s)" in summary
    assert "reparented" in summary


def test_summarize_properties_empty_says_nothing_to_replay():
    assert linkchain.summarize_properties([]) == "no override properties found to replay"


def test_build_rig_rollup_combines_members_and_counts_ready():
    routes = {"human_bundle.blend": [["root.blend", "people1.blend", "human_bundle.blend"]]}
    ref = OverrideReference(name="bonnet", kind="Object", library="//libs/human_bundle.blend")
    ready_plan = linkchain.build_flatten_plan(
        "Body", ref, [_prop('pose.bones["Spine"].location')], routes)
    blocked_plan = linkchain.build_flatten_plan("Eyes", ref, [], routes)
    rollup = linkchain.build_rig_rollup([ready_plan, blocked_plan])
    assert rollup.startswith("1/2 part(s) ready")
    assert "1 bone(s) posed" in rollup


def test_build_rig_rollup_no_plans():
    assert linkchain.build_rig_rollup([]) == "no data"


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
    assert "human_bundle" in finding.message  # ".blend" dropped from display (item 5b)


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


# --- build_flatten_apply_report (Phase 4 Apply) ------------------------------

def test_build_flatten_apply_report_overview_counts_ok():
    results = [
        linkchain.FlattenApplyResult("Char1", True, "flattened — 3 properties replayed",
                                     properties_applied=3),
        linkchain.FlattenApplyResult("Char1_eyes", True, "flattened — 1 property replayed",
                                     properties_applied=1),
    ]
    report = linkchain.build_flatten_apply_report("Char1", results)
    overview = next(f for f in report.findings if f.category == "overview")
    assert "2 of 2" in overview.message
    assert overview.severity == "info"


def test_build_flatten_apply_report_partial_failure_is_warning():
    results = [
        linkchain.FlattenApplyResult("Char1", True, "flattened"),
        linkchain.FlattenApplyResult("Char1_eyes", False, "not ready — skipped"),
    ]
    report = linkchain.build_flatten_apply_report("Char1", results)
    overview = next(f for f in report.findings if f.category == "overview")
    assert "1 of 2" in overview.message
    assert overview.severity == "warning"
    warn = next(f for f in report.findings if f.category == "flatten_warning")
    assert warn.items == ["Object/Char1_eyes"]
    assert "not ready" in warn.message
    ok = next(f for f in report.findings if f.category == "flatten_applied")
    assert ok.items == ["Object/Char1"]


def test_build_flatten_apply_report_clean_when_empty():
    report = linkchain.build_flatten_apply_report("Char1", [])
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


def test_scan_links_and_objects_matches_separate_reads():
    """The merged one-open reader (perf fix, 2026-06-25: Find Flattenable Link
    Chains used to open every file twice) must return exactly what the two
    separate calls it replaces would have — same LinkRefs as
    blendscan.scan_file, same posing info as classify_objects."""
    from core import blendscan

    refs, objects = linkchain.scan_links_and_objects(LINKPROJ / "scene.blend")
    assert refs == blendscan.scan_file(LINKPROJ / "scene.blend")
    assert objects == linkchain.classify_objects(LINKPROJ / "scene.blend")


def test_scan_links_and_objects_no_links():
    """libB.blend (the chain's leaf) links nothing -- refs come back empty,
    objects still populated, same shape as the separate-call equivalents."""
    from core import blendscan

    refs, objects = linkchain.scan_links_and_objects(LINKPROJ / "libB.blend")
    assert refs == blendscan.scan_file(LINKPROJ / "libB.blend") == []
    assert objects == linkchain.classify_objects(LINKPROJ / "libB.blend")
    assert objects
