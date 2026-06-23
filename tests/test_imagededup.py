"""Unit tests for F6 Layer 2 (step 3): core.imagededup (.NNN lossless merge plan)."""

from core import imagededup
from core.imagededup import ImgInfo


def test_identical_family_merges_into_base():
    imgs = [ImgInfo("Leather", "fpA", users=3),
            ImgInfo("Leather.001", "fpA", users=1),
            ImgInfo("Leather.002", "fpA", users=2)]
    plans, conflicts = imagededup.plan_dup_merges(imgs)
    assert conflicts == []
    assert len(plans) == 1
    p = plans[0]
    assert p.base == "Leather"
    assert p.canonical == "Leather"  # un-suffixed original preferred
    assert p.redundant == ["Leather.001", "Leather.002"]


def test_canonical_falls_back_to_most_users_when_base_absent():
    imgs = [ImgInfo("Wood.001", "fpW", users=1),
            ImgInfo("Wood.002", "fpW", users=5)]
    plans, conflicts = imagededup.plan_dup_merges(imgs)
    assert conflicts == []
    assert plans[0].canonical == "Wood.002"  # most users
    assert plans[0].redundant == ["Wood.001"]


def test_differing_content_not_merged_but_flagged():
    # Same .NNN family, different content -> NOT a merge; reported as a conflict.
    imgs = [ImgInfo("Skin", "fpX", users=1),
            ImgInfo("Skin.001", "fpY", users=1)]
    plans, conflicts = imagededup.plan_dup_merges(imgs)
    assert plans == []
    assert len(conflicts) == 1
    assert conflicts[0].base == "Skin"
    assert "differing content" in conflicts[0].reason


def test_partial_merge_of_mixed_family():
    # Two copies of content A + one of content B in one family: merge the A pair,
    # keep B, and flag that the family had mixed content.
    imgs = [ImgInfo("Metal", "fpA", users=2),
            ImgInfo("Metal.001", "fpA", users=1),
            ImgInfo("Metal.002", "fpB", users=1)]
    plans, conflicts = imagededup.plan_dup_merges(imgs)
    assert len(plans) == 1
    assert plans[0].canonical == "Metal"
    assert plans[0].redundant == ["Metal.001"]
    assert len(conflicts) == 1


def test_unverified_fingerprint_not_merged():
    imgs = [ImgInfo("Gone", "", users=1), ImgInfo("Gone.001", "", users=1)]
    plans, conflicts = imagededup.plan_dup_merges(imgs)
    assert plans == []
    assert conflicts and "unverified" in conflicts[0].reason


def test_lone_numbered_copy_is_not_a_family():
    # A single ".001" with no sibling base is not a duplicate set.
    imgs = [ImgInfo("Solo.001", "fp", users=1)]
    plans, conflicts = imagededup.plan_dup_merges(imgs)
    assert plans == [] and conflicts == []


def test_removable_count_and_report_sections():
    imgs = [ImgInfo("A", "fp", users=1), ImgInfo("A.001", "fp", users=1),
            ImgInfo("A.002", "fp", users=1)]
    plans, conflicts = imagededup.plan_dup_merges(imgs)
    assert imagededup.removable_count(plans) == 2
    report = imagededup.build_dedup_report(plans, conflicts, "scene.blend")
    cats = [f.category for f in report.findings]
    assert cats == ["merge_lossless", "summary"]
    assert report.feature == "f6dup"


def test_report_clean_when_no_families():
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
