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


def _drain(gen):
    """Run an iter_resolve generator to completion and return its StopIteration value."""
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        return stop.value


def test_iter_resolve_group_matches_sync_version(tmp_path):
    d = tmp_path / "beard"
    d.mkdir()
    (d / "a.png").write_bytes(b"x")
    (d / "b.png").write_bytes(b"x")
    members = [_img("a.png", str(tmp_path / "gone" / "a.png")),
               _img("b.png", str(tmp_path / "gone" / "b.png")),
               _img("c.png", str(tmp_path / "gone" / "c.png"))]
    assert _drain(imagefamily.iter_resolve_group_in_dir(members, str(d))) == \
        imagefamily.resolve_group_in_dir(members, str(d))


def test_iter_resolve_group_recursive_matches_sync(tmp_path):
    sub = tmp_path / "pack" / "tex"
    sub.mkdir(parents=True)
    (sub / "a.png").write_bytes(b"x")
    members = [_img("a.png", str(tmp_path / "gone" / "a.png"))]
    # Non-recursive finds nothing; recursive finds it — same as the sync function.
    assert _drain(imagefamily.iter_resolve_group_in_dir(members, str(tmp_path / "pack"))) == {}
    assert _drain(imagefamily.iter_resolve_group_in_dir(
        members, str(tmp_path / "pack"), recursive=True)) == \
        {"a.png": os.path.normpath(str(sub / "a.png"))}


def test_iter_resolve_group_yields_folder_progress(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.png").write_bytes(b"x")
    members = [_img("x.png", str(tmp_path / "gone" / "x.png"))]
    counts = list(imagefamily.iter_resolve_group_in_dir(
        members, str(tmp_path), recursive=True))
    # One yield per folder walked (root + "a"), monotonically increasing.
    assert counts == [1, 2]


# --- recursion-limit investigation (user, 2026-06-23): surface WHY a folder
# search skipped a member instead of just leaving it unmatched ---------------

def test_iter_resolve_group_reports_ambiguous_basename(tmp_path):
    s1 = tmp_path / "p" / "one"
    s2 = tmp_path / "p" / "two"
    s1.mkdir(parents=True)
    s2.mkdir(parents=True)
    (s1 / "a.png").write_bytes(b"x")
    (s2 / "a.png").write_bytes(b"x")
    members = [_img("a.png", str(tmp_path / "gone" / "a.png"))]
    ambiguous: dict = {}
    found = _drain(imagefamily.iter_resolve_group_in_dir(
        members, str(tmp_path / "p"), recursive=True, ambiguous=ambiguous))
    assert found == {}  # unchanged behaviour: still never guesses
    assert set(ambiguous) == {"a.png"}
    assert len(ambiguous["a.png"]) == 2


def test_iter_resolve_group_no_ambiguity_when_unique(tmp_path):
    d = tmp_path / "beard"
    d.mkdir()
    (d / "a.png").write_bytes(b"x")
    members = [_img("a.png", str(tmp_path / "gone" / "a.png"))]
    ambiguous: dict = {}
    found = _drain(imagefamily.iter_resolve_group_in_dir(
        members, str(d), ambiguous=ambiguous))
    assert found == {"a.png": os.path.normpath(str(d / "a.png"))}
    assert ambiguous == {}


def test_iter_resolve_group_reports_skipped_dirs(tmp_path, monkeypatch):
    from core import imagepaths

    bad = OSError("denied")
    bad.filename = str(tmp_path / "denied")

    def fake_walk(root, onerror=None):
        if onerror is not None:
            onerror(bad)
        yield (root, [], [])

    monkeypatch.setattr(imagepaths.os, "walk", fake_walk)
    members = [_img("a.png", str(tmp_path / "gone" / "a.png"))]
    skipped: list = []
    _drain(imagefamily.iter_resolve_group_in_dir(
        members, str(tmp_path), recursive=True, skipped_dirs=skipped))
    assert skipped == [str(tmp_path / "denied")]
