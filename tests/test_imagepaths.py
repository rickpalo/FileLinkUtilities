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


def test_build_image_report_sections():
    report = imagepaths.build_image_report(
        {"a.png": r"C:\t\a.png"}, [_img("b.png", r"C:\gone\b.png")], blend_name="scene.blend")
    cats = [f.category for f in report.findings]
    assert cats == ["relink_texture", "unresolved_texture"]


def test_build_image_report_clean():
    report = imagepaths.build_image_report({}, [])
    assert report.findings[0].category == "clean"


# --- Follow-up A: native find_missing_files before/after diff -----------------

def test_diff_found_classifies_found_and_still_missing():
    before = [_img("a.png", r"C:\gone\a.png"), _img("b.png", r"C:\gone\b.png", stored="//b.png")]
    after = {
        "a.png": _img("a.png", r"C:\found\a.png", exists=True),  # relocated by native search
        "b.png": _img("b.png", r"C:\gone\b.png"),                # still not found
    }
    result = imagepaths.diff_found(before, after)
    assert result.found == [("a.png", r"C:\found\a.png")]
    assert result.still_missing == [("b.png", "//b.png")]


def test_diff_found_missing_after_entry_counts_as_still_missing():
    # An image that vanished from bpy.data after the run (renamed/purged) isn't "found".
    before = [_img("c.png", r"C:\gone\c.png", stored="//c.png")]
    result = imagepaths.diff_found(before, {})
    assert result.found == []
    assert result.still_missing == [("c.png", "//c.png")]


def test_build_find_missing_report_sections():
    result = imagepaths.FindMissingResult(
        found=[("a.png", r"C:\found\a.png")], still_missing=[("b.png", "//b.png")])
    report = imagepaths.build_find_missing_report(result, blend_name="scene.blend")
    assert [f.category for f in report.findings] == ["found_texture", "unresolved_texture"]
    assert report.feature == "f6tex"


def test_build_find_missing_report_clean_when_empty():
    report = imagepaths.build_find_missing_report(
        imagepaths.FindMissingResult(found=[], still_missing=[]))
    assert report.findings[0].category == "clean"
