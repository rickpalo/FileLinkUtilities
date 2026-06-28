"""Unit tests for F6 Layer 2/3: core.imagededup (content-overlap lossless merge plan).

(History: the narrower ".NNN"-name-family-only scan and its `plan_dup_merges`
function were removed 2026-06-24 — confirmed redundant with the content-based
scan here, which uses the identical fingerprint over a strict superset of
images, so its tests were removed too. See core/imagededup.py's docstring.)
"""

from core import imagededup
from core.imagededup import ImgInfo


def test_removable_count_and_report_sections():
    imgs = [ImgInfo("A", "fp", users=1), ImgInfo("A.001", "fp", users=1),
            ImgInfo("A.002", "fp", users=1)]
    plans = imagededup.plan_content_merges(imgs)
    assert imagededup.removable_count(plans) == 2
    report = imagededup.build_dedup_report(plans, [], "scene.blend")
    cats = [f.category for f in report.findings]
    assert cats == ["merge_lossless", "summary"]
    assert report.feature == "f6dup"


def test_report_clean_when_no_plans():
    report = imagededup.build_dedup_report([], [])
    assert report.findings[0].category == "clean"


def test_content_merge_crosses_names_and_folders():
    # Same content under three different names (the CC4 cross-folder case) -> one
    # lossless merge; canonical = most-used, then shortest name.
    imgs = [ImgInfo("Brick_CC3_Base.png", "fpA", users=1),
            ImgInfo("Brick_HD_Aaron.png", "fpA", users=4),
            ImgInfo("Brick_fullyClothed.png", "fpA", users=2),
            ImgInfo("Unrelated.png", "fpB", users=9)]
    plans = imagededup.plan_content_merges(imgs)
    assert len(plans) == 1
    assert plans[0].canonical == "Brick_HD_Aaron.png"  # most users
    assert plans[0].redundant == ["Brick_CC3_Base.png", "Brick_fullyClothed.png"]


def test_content_merge_skips_singletons_and_unhashable():
    imgs = [ImgInfo("A.png", "fp1", users=1), ImgInfo("B.png", "fp2", users=1),
            ImgInfo("Gone.png", "", users=1)]
    assert imagededup.plan_content_merges(imgs) == []


def test_content_merge_canonical_shortest_name_on_user_tie():
    imgs = [ImgInfo("Texture_long_name.png", "fp", users=2),
            ImgInfo("Tex.png", "fp", users=2)]
    plans = imagededup.plan_content_merges(imgs)
    assert plans[0].canonical == "Tex.png"  # tie on users -> shortest name


def test_victims_for_keeper_follows_user_choice():
    members = ["Leather", "Leather.001", "Leather.002"]
    # default keeper = the canonical
    assert imagededup.victims_for_keeper(members, "Leather") == ["Leather.001", "Leather.002"]
    # user overrides the keeper -> everything else is a victim, incl. the old canonical
    assert imagededup.victims_for_keeper(members, "Leather.001") == ["Leather", "Leather.002"]


def test_find_image_conflicts_ignores_clean_families():
    # A single clean fingerprint group (handled by plan_content_merges) and a
    # lone, non-suffixed image -- neither is a name-family conflict.
    imgs = [ImgInfo("A", "1024x1024:4:8:fp", users=1),
            ImgInfo("A.001", "1024x1024:4:8:fp", users=1),
            ImgInfo("Solo", "512x512:4:8:fp2", users=1)]
    assert imagededup.find_image_conflicts(imgs) == []


def test_find_image_conflicts_different_dimensions():
    imgs = [ImgInfo("Wood", "1024x1024:4:8:fpA", users=1),
            ImgInfo("Wood.001", "2048x2048:4:8:fpB", users=1)]
    conflicts = imagededup.find_image_conflicts(imgs)
    assert len(conflicts) == 1
    assert conflicts[0].base == "Wood"
    assert "different dimensions" in conflicts[0].reason


def test_find_image_conflicts_same_dimensions_different_hash():
    imgs = [ImgInfo("Wood", "1024x1024:4:8:fpA", users=1),
            ImgInfo("Wood.001", "1024x1024:4:8:fpB", users=1)]
    conflicts = imagededup.find_image_conflicts(imgs)
    assert len(conflicts) == 1
    assert "same dimensions, different content" in conflicts[0].reason


def test_find_image_conflicts_unverified_member():
    imgs = [ImgInfo("Wood", "1024x1024:4:8:fpA", users=1),
            ImgInfo("Wood.001", "", users=1)]
    conflicts = imagededup.find_image_conflicts(imgs)
    assert len(conflicts) == 1
    assert "unverified" in conflicts[0].reason
    assert "dimensions" not in conflicts[0].reason


def test_find_image_conflicts_dims_and_unverified_both_reported():
    imgs = [ImgInfo("Wood", "1024x1024:4:8:fpA", users=1),
            ImgInfo("Wood.001", "2048x2048:4:8:fpB", users=1),
            ImgInfo("Wood.002", "", users=1)]
    conflicts = imagededup.find_image_conflicts(imgs)
    assert len(conflicts) == 1
    assert "different dimensions" in conflicts[0].reason
    assert "unverified" in conflicts[0].reason
