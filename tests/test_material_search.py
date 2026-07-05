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
