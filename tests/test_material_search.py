"""docs/TODO.md #22 — Find Material Across Files.

The matcher itself is pure/synthetic; find_materials against real fixtures
mirrors tests/test_blendscan.py's pattern (real BAT-backed reads against the
committed linkproj fixtures, skipped if they haven't been built).
"""

import pathlib

import pytest

from core import material_search

LINKPROJ = pathlib.Path(__file__).resolve().parent / "fixtures" / "linkproj"

pytestmark = pytest.mark.skipif(
    not (LINKPROJ / "scene.blend").is_file(),
    reason="linkproj fixtures not built (run tests/fixtures/build_linkproj.py in Blender)",
)


# --- make_matcher (pure, no fixtures needed) ---------------------------------

def test_matcher_plain_text_is_substring():
    m = material_search.make_matcher("bark")
    assert m("Bark_2k")
    assert m("OldBark")
    assert not m("Stone")


def test_matcher_wildcard_is_glob():
    m = material_search.make_matcher("Bark_*")
    assert m("Bark_2k")
    assert not m("OldBark")  # glob is a full-name match, not substring


def test_matcher_is_case_insensitive():
    assert material_search.make_matcher("BARK")("bark_2k")
    assert material_search.make_matcher("bark_*")("BARK_2K")


def test_matcher_question_mark_glob():
    m = material_search.make_matcher("Bark_?k")
    assert m("Bark_2k")
    assert not m("Bark_20k")


# --- find_materials (real BAT reads against committed fixtures) -------------

def test_find_materials_substring_match():
    assert material_search.find_materials(LINKPROJ / "libA.blend", "bark") == ["Bark_2k"]


def test_find_materials_glob_match():
    assert material_search.find_materials(LINKPROJ / "libA.blend", "Bark_*") == ["Bark_2k"]


def test_find_materials_no_match_returns_empty():
    assert material_search.find_materials(LINKPROJ / "libA.blend", "Stone") == []


def test_find_materials_different_file_different_material():
    assert material_search.find_materials(LINKPROJ / "libB.blend", "Stone") == ["Stone"]


def test_find_materials_scene_has_no_materials():
    assert material_search.find_materials(LINKPROJ / "scene.blend", "*") == []


# --- score_material_name / material_name_confidence (pure, no fixtures needed) ----

def test_score_material_name_exact_match_is_one():
    assert material_search.score_material_name("Bark_2k", "Bark_2k") == 1.0


def test_score_material_name_short_alias_inside_long_vendor_name():
    # The real Poliigon case: a shortened in-scene alias for a long, delimiter-
    # free vendor compound name. Contained -> a low-but-real score, not None.
    long_name = "FabricFloralDuckeggJacquard001"
    score = material_search.score_material_name("DuckEgg", long_name)
    assert score is not None
    assert score == len("duckegg") / len("fabricfloralduckeggjacquard001")
    assert score < 0.5  # a generic short alias should rank low, not "medium"+


def test_score_material_name_is_bidirectional():
    long_name = "FabricFloralDuckeggJacquard001"
    # long name as "wanted", short alias as "candidate" -> same score either way.
    a = material_search.score_material_name("DuckEgg", long_name)
    b = material_search.score_material_name(long_name, "DuckEgg")
    assert a == b


def test_score_material_name_no_containment_is_none():
    assert material_search.score_material_name("Bark_2k", "Stone") is None


def test_score_material_name_ignores_separators_and_case():
    assert material_search.score_material_name("Duck_Egg", "DUCKEGG_001") is not None


def test_material_name_confidence_bands():
    assert material_search.material_name_confidence(1.0) == "high"
    assert material_search.material_name_confidence(0.9) == "high"
    assert material_search.material_name_confidence(0.6) == "medium"
    assert material_search.material_name_confidence(0.5) == "medium"
    assert material_search.material_name_confidence(0.2) == "low"


# --- best_material_match (pure: list_material_names monkeypatched, no real
# .blend files needed — mirrors the "one material per file" library this was
# built for, which the committed bundle-style linkproj fixtures don't model) --

def test_best_material_match_confirms_by_internal_name_not_just_filename(monkeypatch):
    fake_contents = {
        pathlib.Path("FabricFloralDuckeggJacquard001.blend"): ["FabricFloralDuckeggJacquard001"],
        pathlib.Path("Stone.blend"): ["Stone"],
    }
    monkeypatch.setattr(material_search, "list_material_names",
                        lambda p: fake_contents[pathlib.Path(p)])

    best = material_search.best_material_match("DuckEgg", list(fake_contents))
    assert best is not None
    f, name, score = best
    assert f == pathlib.Path("FabricFloralDuckeggJacquard001.blend")
    assert name == "FabricFloralDuckeggJacquard001"
    assert 0 < score < 0.5


def test_best_material_match_no_filename_lead_returns_none(monkeypatch):
    # Neither candidate filename contains/is-contained-by "wanted" -> nothing to
    # shortlist, so list_material_names is never even called (no I/O wasted).
    monkeypatch.setattr(material_search, "list_material_names",
                        lambda p: (_ for _ in ()).throw(AssertionError("should not open this file")))
    best = material_search.best_material_match("DuckEgg", [pathlib.Path("libA.blend")])
    assert best is None


def test_best_material_match_skips_unreadable_shortlisted_file(monkeypatch):
    def _boom(p):
        if pathlib.Path(p) == pathlib.Path("DuckEgg_corrupt.blend"):
            raise OSError("corrupt file")
        return ["DuckEgg"]

    monkeypatch.setattr(material_search, "list_material_names", _boom)
    best = material_search.best_material_match(
        "DuckEgg", [pathlib.Path("DuckEgg_corrupt.blend"), pathlib.Path("DuckEgg_ok.blend")])
    assert best is not None
    assert best[0] == pathlib.Path("DuckEgg_ok.blend")


def test_best_material_match_picks_best_scoring_candidate(monkeypatch):
    fake_contents = {
        pathlib.Path("DuckEgg.blend"): ["DuckEgg"],  # exact match, score 1.0
        pathlib.Path("DuckEggFabricVariant.blend"): ["DuckEggFabricVariant"],  # weaker
    }
    monkeypatch.setattr(material_search, "list_material_names",
                        lambda p: fake_contents[pathlib.Path(p)])
    best = material_search.best_material_match("DuckEgg", list(fake_contents))
    assert best is not None
    assert best[0] == pathlib.Path("DuckEgg.blend")
    assert best[2] == 1.0
