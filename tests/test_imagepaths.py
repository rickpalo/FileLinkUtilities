"""Unit tests for F6 Layer 1: core.imagepaths (missing-texture relinker)."""

import os

from core import imagepaths
from core.imagepaths import ImgDesc


def _img(name, resolved, exists=False, stored="//x.png"):
    return ImgDesc(name=name, stored=stored, resolved=resolved, exists=exists)


def test_dedup_path_collapses_immediate_repeat():
    # The real bug: a doubled folder segment.
    assert imagepaths.dedup_path(
        r"E:\BlenderSync\BlenderSync\SynologyDrive\a.png"
    ) == "E:/BlenderSync/SynologyDrive/a.png"


def test_dedup_path_keeps_non_consecutive_repeat():
    # a appears twice but not back-to-back — not an error, keep it.
    assert imagepaths.dedup_path(r"E:\a\b\a\c.png") == "E:/a/b/a/c.png"


def test_dedup_path_noop_when_clean():
    assert imagepaths.dedup_path("E:/x/y/z.png") == "E:/x/y/z.png"


def test_apply_prefix_remap_cross_drive():
    assert imagepaths.apply_prefix_remap(r"D:\lib\a.png", "D:\\", "E:\\") == "E:/lib/a.png"


def test_apply_prefix_remap_case_insensitive():
    assert imagepaths.apply_prefix_remap(
        "e:/BlenderSync/BlenderSync/t.png", "E:/BlenderSync/BlenderSync/", "E:/BlenderSync/"
    ) == "E:/BlenderSync/t.png"


def test_apply_prefix_remap_noop_when_not_prefix():
    assert imagepaths.apply_prefix_remap("E:/x/a.png", "D:/", "F:/") == "E:/x/a.png"


def test_find_target_via_dedup(tmp_path):
    real = tmp_path / "BlenderSync" / "tex" / "a.png"
    real.parent.mkdir(parents=True)
    real.write_bytes(b"x")
    doubled = str(tmp_path / "BlenderSync" / "BlenderSync" / "tex" / "a.png")
    img = _img("a.png", os.path.normpath(doubled))
    assert imagepaths.find_image_target(img, []) == os.path.normpath(str(real))


def test_find_target_via_folder_search(tmp_path):
    d = tmp_path / "textures"
    d.mkdir()
    f = d / "b.png"
    f.write_bytes(b"x")
    img = _img("b.png", os.path.normpath(str(tmp_path / "gone" / "b.png")))
    assert imagepaths.find_image_target(img, [str(d)]) == os.path.normpath(str(f))


def test_find_target_ambiguous_folder_match_skipped(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "c.png").write_bytes(b"x")
    (b / "c.png").write_bytes(b"x")
    img = _img("c.png", os.path.normpath(str(tmp_path / "gone" / "c.png")))
    assert imagepaths.find_image_target(img, [str(a), str(b)]) is None  # 2 matches → skip


def test_find_target_prefix_remap(tmp_path):
    real = tmp_path / "E_drive" / "lib" / "d.png"
    real.parent.mkdir(parents=True)
    real.write_bytes(b"x")
    missing = os.path.normpath(str(tmp_path / "D_drive" / "lib" / "d.png"))
    img = _img("d.png", missing)
    remaps = [(str(tmp_path / "D_drive"), str(tmp_path / "E_drive"))]
    assert imagepaths.find_image_target(img, [], remaps) == os.path.normpath(str(real))


def test_find_relink_targets_mixed(tmp_path):
    real = tmp_path / "BlenderSync" / "t" / "ok.png"
    real.parent.mkdir(parents=True)
    real.write_bytes(b"x")
    found = _img("ok.png", os.path.normpath(str(tmp_path / "BlenderSync" / "BlenderSync" / "t" / "ok.png")))
    gone = _img("gone.png", os.path.normpath(str(tmp_path / "nope" / "gone.png")))
    targets = imagepaths.find_relink_targets([found, gone], [])
    assert targets == {"ok.png": os.path.normpath(str(real))}


def test_iter_walk_dirs_non_recursive_yields_root_only(tmp_path):
    (tmp_path / "sub").mkdir()
    assert list(imagepaths.iter_walk_dirs(str(tmp_path), recursive=False)) == [str(tmp_path)]


def test_iter_walk_dirs_recursive_descends(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b").mkdir()
    got = set(imagepaths.iter_walk_dirs(str(tmp_path), recursive=True))
    assert got == {str(tmp_path), str(tmp_path / "a"), str(tmp_path / "a" / "b")}


def test_scan_dir_into_indexes_files_and_skips_seen(tmp_path):
    (tmp_path / "A.PNG").write_bytes(b"x")
    index, seen = {}, set()
    imagepaths._scan_dir_into(index, seen, str(tmp_path))
    assert index == {"a.png": [os.path.normpath(str(tmp_path / "A.PNG"))]}
    # A second scan of the same dir (case/trailing-slash insensitive) is a no-op.
    imagepaths._scan_dir_into(index, seen, str(tmp_path) + os.sep)
    assert index["a.png"] == [os.path.normpath(str(tmp_path / "A.PNG"))]


def test_scan_dir_into_matches_index_dirs(tmp_path):
    # The incremental primitive must build exactly what _index_dirs builds.
    (tmp_path / "a.png").write_bytes(b"x")
    (tmp_path / "b.png").write_bytes(b"x")
    index, seen = {}, set()
    imagepaths._scan_dir_into(index, seen, str(tmp_path))
    assert index == imagepaths._index_dirs([str(tmp_path)])


# --- recursion-limit investigation (user, 2026-06-23): why a drive-level search
# misses files a narrower one finds -----------------------------------------

def test_ambiguous_matches_flags_multi_hit_basenames():
    index = {"a.png": ["/x/a.png", "/y/a.png"], "b.png": ["/x/b.png"]}
    assert imagepaths.ambiguous_matches(index, ["a.png", "b.png", "c.png"]) == \
        {"a.png": ["/x/a.png", "/y/a.png"]}


def test_ambiguous_matches_case_insensitive_lookup():
    index = {"a.png": ["/x/a.png", "/y/a.png"]}
    assert imagepaths.ambiguous_matches(index, ["A.PNG"]) == {"A.PNG": ["/x/a.png", "/y/a.png"]}


def test_iter_walk_dirs_records_skipped_via_onerror(monkeypatch, tmp_path):
    # os.walk's onerror is the only hook that fires for a subdirectory it could not
    # list at all — simulate that without depending on real OS permission behavior.
    bad = OSError("denied")
    bad.filename = str(tmp_path / "denied")

    def fake_walk(root, onerror=None):
        if onerror is not None:
            onerror(bad)
        yield (root, [], [])

    monkeypatch.setattr(imagepaths.os, "walk", fake_walk)
    skipped: list[str] = []
    list(imagepaths.iter_walk_dirs(str(tmp_path), recursive=True, skipped=skipped))
    assert skipped == [str(tmp_path / "denied")]


def test_iter_walk_dirs_skipped_none_is_a_noop(monkeypatch, tmp_path):
    # Existing callers that don't pass `skipped` must keep working unchanged.
    bad = OSError("denied")

    def fake_walk(root, onerror=None):
        if onerror is not None:
            onerror(bad)
        yield (root, [], [])

    monkeypatch.setattr(imagepaths.os, "walk", fake_walk)
    assert list(imagepaths.iter_walk_dirs(str(tmp_path), recursive=True)) == [str(tmp_path)]
