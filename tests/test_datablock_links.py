"""Offline datablock-level link detail, against the linkproj fixtures.

scene.blend links Tree from libA; libA.blend links Rock from libB. Linking an
object pulls its mesh/material too, so we assert loosely on presence + attribution.
"""

import pathlib

import pytest

from core import datablock_links as dl

LINKPROJ = pathlib.Path(__file__).resolve().parent / "fixtures" / "linkproj"

pytestmark = pytest.mark.skipif(
    not (LINKPROJ / "scene.blend").is_file(),
    reason="linkproj fixtures not built",
)


def test_scene_links_tree_from_libA():
    links = dl.linked_datablocks(LINKPROJ / "scene.blend")
    # attributed to a library whose filename is libA.blend
    libA = [items for lib, items in links.items() if lib.lower().endswith("liba.blend")]
    assert libA, f"expected a libA library, got {list(links)}"
    assert ("Object", "Tree") in libA[0]


def test_datablocks_from_library_by_name():
    hits = dl.datablocks_from_library(LINKPROJ / "scene.blend", "libA.blend")
    assert ("Object", "Tree") in hits


def test_libB_is_leaf_has_no_linked_datablocks():
    # libB is a pure source library — it links nothing itself.
    assert dl.linked_datablocks(LINKPROJ / "libB.blend") == {}


def test_link_counts_nonempty_for_scene():
    counts = dl.link_counts(LINKPROJ / "scene.blend")
    assert counts and counts[0][1] >= 1
