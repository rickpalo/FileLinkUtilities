"""Unit tests for F6 step 2: core.imagefamily (group missing textures + folder-resolve)."""

import os

from core import imagefamily
from core.imagepaths import ImgDesc


def _img(name, resolved, stored="//x.png"):
    return ImgDesc(name=name, stored=stored, resolved=os.path.normpath(resolved), exists=False)


def test_group_by_directory_groups_same_folder():
    a = _img("a.png", r"E:/chars/beard/a.png")
    b = _img("b.png", r"E:/chars/beard/b.png")
    c = _img("c.png", r"E:/chars/brows/c.png")
    groups = imagefamily.group_by_directory([a, b, c])
    assert set(groups) == {"E:/chars/beard", "E:/chars/brows"}
    assert [m.name for m in groups["E:/chars/beard"]] == ["a.png", "b.png"]


def test_group_by_directory_handles_backslashes():
    a = _img("a.png", r"E:\chars\beard\a.png")
    groups = imagefamily.group_by_directory([a])
    assert list(groups) == ["E:/chars/beard"]


def test_group_by_key_material_fallback():
    a = _img("a.png", r"E:/x/a.png")
    b = _img("b.png", r"E:/y/b.png")
    mat = {"a.png": "Beard", "b.png": "Beard"}
    groups = imagefamily.group_by_key([a, b], lambda i: mat.get(i.name, ""))
    assert list(groups) == ["Beard"]
    assert {m.name for m in groups["Beard"]} == {"a.png", "b.png"}


def test_group_by_key_empty_key_bucketed():
    a = _img("a.png", r"E:/x/a.png")
    groups = imagefamily.group_by_key([a], lambda i: "")
    assert list(groups) == [""]


def test_resolve_group_in_dir_finds_by_basename(tmp_path):
    d = tmp_path / "beard"
    d.mkdir()
    (d / "a.png").write_bytes(b"x")
    (d / "b.png").write_bytes(b"x")
    members = [_img("a.png", str(tmp_path / "gone" / "a.png")),
               _img("b.png", str(tmp_path / "gone" / "b.png")),
               _img("c.png", str(tmp_path / "gone" / "c.png"))]  # not in dir
    found = imagefamily.resolve_group_in_dir(members, str(d))
    assert found == {"a.png": os.path.normpath(str(d / "a.png")),
                     "b.png": os.path.normpath(str(d / "b.png"))}


def test_resolve_group_in_dir_recursive_into_subfolder(tmp_path):
    sub = tmp_path / "pack" / "tex"
    sub.mkdir(parents=True)
    (sub / "a.png").write_bytes(b"x")
    members = [_img("a.png", str(tmp_path / "gone" / "a.png"))]
    assert imagefamily.resolve_group_in_dir(members, str(tmp_path / "pack")) == {}  # not at top level
    assert imagefamily.resolve_group_in_dir(
        members, str(tmp_path / "pack"), recursive=True
    ) == {"a.png": os.path.normpath(str(sub / "a.png"))}


def test_resolve_group_in_dir_ambiguous_recursive_skipped(tmp_path):
    s1 = tmp_path / "p" / "one"
    s2 = tmp_path / "p" / "two"
    s1.mkdir(parents=True)
    s2.mkdir(parents=True)
    (s1 / "a.png").write_bytes(b"x")
    (s2 / "a.png").write_bytes(b"x")
    members = [_img("a.png", str(tmp_path / "gone" / "a.png"))]
    assert imagefamily.resolve_group_in_dir(members, str(tmp_path / "p"), recursive=True) == {}
