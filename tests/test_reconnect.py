"""Unit tests for Batch C: core.reconnect (datablock reconnect suggestions)."""

from core import reconnect
from core.missingdata import MissingBlock


def test_suggest_reconnect_exact_match_wins():
    s = reconnect.suggest_reconnect("Body", ["Body", "Body.001"])
    assert s.target == "Body"
    assert s.confidence == "exact"


def test_suggest_reconnect_numbered_no_unsuffixed_base():
    # Source only has a numbered copy (the renamed-at-source case from the TODO
    # example); exact name absent, so the .NNN copy is the best fallback.
    s = reconnect.suggest_reconnect("GeometricStichDesign",
                                    ["GeometricStichDesign.002", "Unrelated"])
    assert s.target == "GeometricStichDesign.002"
    assert s.confidence == "numbered"


def test_suggest_reconnect_numbered_prefers_unsuffixed_base():
    s = reconnect.suggest_reconnect("Leather.001", ["Leather", "Leather.003"])
    assert s.target == "Leather"
    assert s.confidence == "numbered"


def test_suggest_reconnect_fuzzy_token_affinity():
    s = reconnect.suggest_reconnect("old_wood_floor", ["new_wood_floor"])
    assert s.target == "new_wood_floor"
    assert s.confidence == "fuzzy"


def test_suggest_reconnect_none_below_floor():
    s = reconnect.suggest_reconnect("Xyz123Unique", ["TotallyDifferentThing"])
    assert s.target == ""
    assert s.confidence == "none"


def test_suggest_reconnect_allow_fuzzy_false_stops_at_numbered():
    # Numbered tier still applies even with fuzzy disabled.
    s = reconnect.suggest_reconnect("Leather.001", ["Leather"], allow_fuzzy=False)
    assert s == reconnect.Suggestion("Leather", "numbered")
    # But a fuzzy-only case (no exact/numbered) now returns none instead of guessing.
    s2 = reconnect.suggest_reconnect("old_wood_floor", ["new_wood_floor"], allow_fuzzy=False)
    assert s2 == reconnect.Suggestion("", "none")


def test_suggest_reconnect_no_candidates():
    s = reconnect.suggest_reconnect("Body", [])
    assert s == reconnect.Suggestion("", "none")


def test_ranked_candidates_orders_suggestion_first():
    ranked = reconnect.ranked_candidates("Body", ["Body.003", "Aaa", "Body"])
    assert ranked == ["Body", "Aaa", "Body.003"]


def test_ranked_candidates_falls_back_to_sorted_when_no_suggestion():
    ranked = reconnect.ranked_candidates("Xyz123Unique", ["Beta", "Alpha"])
    assert ranked == ["Alpha", "Beta"]


def test_plan_reconnects_keys_by_each_blocks_own_collection():
    blocks = [
        MissingBlock(kind="Material", name="Wood", library="//lib.blend", collection="materials"),
        MissingBlock(kind="Object", name="Tree", library="//lib.blend", collection="objects"),
    ]
    plans = reconnect.plan_reconnects(
        blocks, {"materials": ["Wood"], "objects": ["Shrub"]})
    by_name = {p.block.name: p.suggestion for p in plans}
    assert by_name["Wood"] == reconnect.Suggestion("Wood", "exact")
    assert by_name["Tree"] == reconnect.Suggestion("", "none")


def test_plan_reconnects_missing_collection_yields_no_candidates():
    blocks = [MissingBlock(kind="Image", name="Leaf", library="", collection="images")]
    plans = reconnect.plan_reconnects(blocks, {})
    assert plans[0].suggestion == reconnect.Suggestion("", "none")


def test_find_sibling_library_matches_by_basename():
    # Same file, linked via a stale absolute path vs a resolving relative one.
    missing = "D:\\Old\\materialMaster.blend"
    resolving = ["E:\\BlenderSync\\SynologyDrive\\libraries\\materialMaster.blend"]
    assert reconnect.find_sibling_library(missing, resolving) == resolving[0]


def test_find_sibling_library_case_and_slash_insensitive():
    missing = "//../../materialMaster.BLEND"
    resolving = ["E:/lib/MaterialMaster.blend"]
    assert reconnect.find_sibling_library(missing, resolving) == resolving[0]


def test_find_sibling_library_no_match_returns_empty():
    assert reconnect.find_sibling_library("//gone.blend", ["E:/lib/other.blend"]) == ""


def test_find_sibling_library_ambiguous_never_guesses():
    missing = "//gone/materialMaster.blend"
    resolving = ["E:/a/materialMaster.blend", "E:/b/materialMaster.blend"]
    assert reconnect.find_sibling_library(missing, resolving) == ""


def test_find_sibling_library_empty_inputs():
    assert reconnect.find_sibling_library("", ["E:/lib/x.blend"]) == ""
    assert reconnect.find_sibling_library("//x.blend", []) == ""
