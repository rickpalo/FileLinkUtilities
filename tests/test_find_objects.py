"""Tests for tools/find_objects.py.

The module lives in tools/ (a standalone utility, not the importable package), so
it is loaded by file path. conftest already puts the BAT wheel on sys.path, which
the module reuses. Mesh detection is exercised against the committed linkproj
fixtures: libB defines mesh "Rock", libA defines mesh "Tree".
"""

import importlib.util
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
LINKPROJ = REPO_ROOT / "tests" / "fixtures" / "linkproj"


def _load_module():
    path = REPO_ROOT / "tools" / "find_objects.py"
    spec = importlib.util.spec_from_file_location("find_objects", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fb = _load_module()
fb._ensure_bat_importable()

bat_missing = not __import__("importlib").util.find_spec("blender_asset_tracer")
needs_bat = pytest.mark.skipif(bat_missing, reason="BAT wheel not importable")


@needs_bat
def test_finds_mesh_by_keyword_case_insensitive():
    # "Rock" lives in libB; match case-insensitively, with the OB prefix stripped.
    hits = fb.find_mesh_objects(LINKPROJ / "libB.blend", "rock")
    assert hits == ["Rock"]


@needs_bat
def test_no_match_returns_empty():
    assert fb.find_mesh_objects(LINKPROJ / "libB.blend", "billboard") == []


@needs_bat
def test_object_name_has_no_ob_prefix_leak():
    # Regression: the 2-char "OB" id prefix must be stripped from reported names.
    hits = fb.find_mesh_objects(LINKPROJ / "libA.blend", "tree")
    assert hits == ["Tree"]
    assert not any(n.startswith("OB") for n in hits)


def test_iter_newest_first_orders_by_mtime(tmp_path):
    import os
    import time

    old = tmp_path / "old.blend"
    new = tmp_path / "new.blend"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    # Force a clear ordering regardless of write timing.
    os.utime(old, (time.time() - 100, time.time() - 100))
    os.utime(new, (time.time(), time.time()))
    ordered = fb.iter_blend_files_newest_first(tmp_path)
    assert [p.name for p in ordered] == ["new.blend", "old.blend"]


def test_iter_skips_ignored_dirs(tmp_path):
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "packed.blend").write_bytes(b"x")
    keep = tmp_path / "keep.blend"
    keep.write_bytes(b"x")
    names = [p.name for p in fb.iter_blend_files_newest_first(tmp_path)]
    assert names == ["keep.blend"]


def test_zstd_error_is_detected():
    # The fail-loud path keys off the zstandard hint in BAT's OSError message.
    err = OSError("File is compressed with ZStandard, install the `zstandard` module")
    assert fb._is_zstd_error(err) is True
    assert fb._is_zstd_error(OSError("truncated header")) is False


# --- generic search (wildcards + type filter) ---------------------------------
@needs_bat
def test_find_objects_wildcard_match():
    assert fb.find_objects(LINKPROJ / "libA.blend", "tr*", "mesh") == ["Tree"]
    assert fb.find_objects(LINKPROJ / "libA.blend", "*ee", "mesh") == ["Tree"]
    assert fb.find_objects(LINKPROJ / "libA.blend", "x*", "mesh") == []


@needs_bat
def test_find_objects_any_type_vs_wrong_type():
    # "Rock" is a mesh; it matches with any-type or mesh, but not as a camera.
    assert fb.find_objects(LINKPROJ / "libB.blend", "rock", None) == ["Rock"]
    assert fb.find_objects(LINKPROJ / "libB.blend", "rock", "mesh") == ["Rock"]
    assert fb.find_objects(LINKPROJ / "libB.blend", "rock", "camera") == []


def test_type_code_for():
    assert fb.type_code_for("mesh") == 1
    assert fb.type_code_for("CAMERA") == 11
    assert fb.type_code_for("light") == fb.type_code_for("lamp") == 10
    assert fb.type_code_for(None) is None
    assert fb.type_code_for("any") is None
    with pytest.raises(ValueError):
        fb.type_code_for("notatype")


def test_parser_parses_args():
    p = fb.build_parser()
    ns = p.parse_args(["dir", "tree", "--type", "mesh", "--first"])
    assert (ns.directory, ns.phrase, ns.obj_type, ns.first) == ("dir", "tree", "mesh", True)
    ns2 = p.parse_args(["dir", "*cam*", "--type=camera"])
    assert (ns2.obj_type, ns2.first) == ("camera", False)


def test_parser_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        fb.build_parser().parse_args(["--help"])
    assert exc.value.code == 0


def test_parser_rejects_unknown_type_and_missing_phrase():
    with pytest.raises(SystemExit):
        fb.build_parser().parse_args(["dir", "x", "--type", "bogus"])  # not an object type
    with pytest.raises(SystemExit):
        fb.build_parser().parse_args(["dir"])  # phrase is required


def test_type_is_case_insensitive():
    import argparse

    assert fb._object_type_arg("MESH") == "mesh"
    assert fb._object_type_arg("Camera") == "camera"
    assert fb._object_type_arg("Any") == "any"
    # the parser normalises case too
    ns = fb.build_parser().parse_args(["dir", "x", "--type", "Mesh"])
    assert ns.obj_type == "mesh"
    # non-object terms (action / NLA / material) are rejected with a clear message
    for bad in ("action", "NLA", "material"):
        with pytest.raises(argparse.ArgumentTypeError) as exc:
            fb._object_type_arg(bad)
        assert "not a Blender object type" in str(exc.value)
