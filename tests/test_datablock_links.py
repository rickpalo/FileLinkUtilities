"""Offline datablock-level link detail, against the linkproj fixtures.

scene.blend links Tree from libA; libA.blend links Rock from libB. Linking an
object pulls its mesh/material too, so we assert loosely on presence + attribution.
"""

import pathlib

import pytest

from core import datablock_links as dl

LINKPROJ = pathlib.Path(__file__).resolve().parent / "fixtures" / "linkproj"

# Only the fixture-dependent tests below need this — basename() is a plain
# string function and shouldn't be skipped just because the BAT fixtures
# haven't been built.
_needs_fixtures = pytest.mark.skipif(
    not (LINKPROJ / "scene.blend").is_file(),
    reason="linkproj fixtures not built",
)


@_needs_fixtures
def test_scene_links_tree_from_libA():
    links = dl.linked_datablocks(LINKPROJ / "scene.blend")
    # attributed to a library whose filename is libA.blend
    libA = [items for lib, items in links.items() if lib.lower().endswith("liba.blend")]
    assert libA, f"expected a libA library, got {list(links)}"
    assert ("Object", "Tree") in libA[0]


@_needs_fixtures
def test_datablocks_from_library_by_name():
    hits = dl.datablocks_from_library(LINKPROJ / "scene.blend", "libA.blend")
    assert ("Object", "Tree") in hits


@_needs_fixtures
def test_libB_is_leaf_has_no_linked_datablocks():
    # libB is a pure source library — it links nothing itself.
    assert dl.linked_datablocks(LINKPROJ / "libB.blend") == {}


@_needs_fixtures
def test_link_counts_nonempty_for_scene():
    counts = dl.link_counts(LINKPROJ / "scene.blend")
    assert counts and counts[0][1] >= 1


# --- basename() (2026-07-04 follow-up: the "Fix at Source" blank-name bug) --

def test_basename_plain_relative_path():
    assert dl.basename("//materialMaster.blend") == "materialMaster.blend"


def test_basename_same_folder_relative_is_not_blank():
    # The exact regression: os.path.basename("//Name.blend") returns '' on
    # Windows because ntpath misreads Blender's leading "//" as a UNC root.
    assert dl.basename("//ThePiazzaSanMarco - People.blend") == "ThePiazzaSanMarco - People.blend"


def test_basename_multi_hop_relative_path():
    assert dl.basename("//..\\..\\..\\libraries\\human_bundle.blend") == "human_bundle.blend"


def test_basename_absolute_windows_path():
    assert dl.basename("D:\\BlenderLibraries\\foo\\bar.blend") == "bar.blend"


def test_basename_trailing_slash():
    assert dl.basename("//folder/") == "folder"
