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
