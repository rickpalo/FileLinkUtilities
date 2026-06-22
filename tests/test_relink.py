"""Unit tests for F7 Phase 3a: core.relink (library path hygiene)."""

import os

from core import relink
from core.relink import LibDesc


def _lib(name, stored, resolved, exists=True):
    return LibDesc(name=name, stored=stored, resolved=resolved, exists=exists)


def test_needs_fix():
    assert relink.needs_fix(_lib("a", "//a.blend", "X")) is False
    assert relink.needs_fix(_lib("a", "C:/x/a.blend", "X")) is True  # absolute
    assert relink.needs_fix(_lib("a", "//..\\a.blend", "X")) is True  # backslash


def test_to_relative_same_drive():
    new = relink.to_relative(r"C:\proj\libs\a.blend", r"C:\proj\scene")
    assert new == "//../libs/a.blend"


def test_to_relative_cross_drive_returns_none():
    if os.name != "nt":
        return  # cross-drive semantics are Windows-only
    assert relink.to_relative(r"D:\libs\a.blend", r"C:\proj") is None


def test_relink_stored_path_same_drive_is_relative():
    assert relink.relink_stored_path(
        r"C:\proj\libs\mat.blend", r"C:\proj\scene") == "//../libs/mat.blend"


def test_relink_stored_path_cross_drive_keeps_absolute():
    if os.name != "nt":
        return  # cross-drive semantics are Windows-only
    assert relink.relink_stored_path(
        r"D:\libs\mat.blend", r"C:\proj") == r"D:\libs\mat.blend"


def test_plan_normalizes_absolute_same_drive():
    libs = [_lib("a.blend", r"C:\proj\libs\a.blend", r"C:\proj\libs\a.blend")]
    plan = relink.plan_library_fixes(libs, r"C:\proj\scene")
    assert plan.renames == [("a.blend", r"C:\proj\libs\a.blend", "//../libs/a.blend")]


def test_plan_skips_missing_and_clean():
    libs = [
        _lib("ok", "//ok.blend", r"C:\proj\ok.blend"),  # already relative+clean
        _lib("gone", r"C:\proj\gone.blend", r"C:\proj\gone.blend", exists=False),  # missing
    ]
    assert relink.plan_library_fixes(libs, r"C:\proj").renames == []


def test_plan_detects_duplicates():
    libs = [
        _lib("matA", "//materialMaster.blend", r"C:\proj\materialMaster.blend"),
        _lib("matB", r"C:\proj\materialMaster.blend", r"C:\proj\materialMaster.blend"),
    ]
    plan = relink.plan_library_fixes(libs, r"C:\proj")
    assert list(plan.duplicates.values()) == [["matA", "matB"]]


def test_find_relink_candidates_unique_match(tmp_path):
    libs_dir = tmp_path / "libs"
    libs_dir.mkdir()
    (libs_dir / "human_bundle.blend").write_bytes(b"x")
    missing = [_lib("human_bundle.blend", "//gone/human_bundle.blend",
                    str(tmp_path / "gone" / "human_bundle.blend"), exists=False)]
    found = relink.find_relink_candidates(missing, [str(libs_dir)])
    assert found == {"human_bundle.blend": str((libs_dir / "human_bundle.blend"))}


def test_find_relink_candidates_ambiguous_skipped(tmp_path):
    a = tmp_path / "a"; b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "lib.blend").write_bytes(b"x")
    (b / "lib.blend").write_bytes(b"x")
    missing = [_lib("lib.blend", "//x/lib.blend", str(tmp_path / "x" / "lib.blend"),
                    exists=False)]
    assert relink.find_relink_candidates(missing, [str(a), str(b)]) == {}  # 2 matches


def test_relink_section_in_report():
    report = relink.build_libfix_report(relink.LibFixPlan(),
                                        relinks={"lib.blend": r"C:\found\lib.blend"})
    assert report.findings[0].category == "relink_missing"
    assert report.findings[0].severity == "error"


def test_build_libfix_report_no_summary_row():
    libs = [_lib("a.blend", r"C:\proj\libs\a.blend", r"C:\proj\libs\a.blend")]
    plan = relink.plan_library_fixes(libs, r"C:\proj\scene")
    report = relink.build_libfix_report(plan, blend_name="scene.blend")
    assert report.feature == "f7fix"
    # no redundant Summary row; normalize_path is the self-describing top line
    assert all(f.category != "summary" for f in report.findings)
    assert report.findings[0].category == "normalize_path"
