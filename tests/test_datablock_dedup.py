"""Unit tests for core.datablock_dedup (generic .NNN merge planning, bpy-free).

Mirrors tests/test_imagededup.py — that module is now a thin wrapper over this
one, so these tests lock the SHARED algorithm directly (and with type-agnostic
names like Action/Material, not just images)."""

from core import datablock_dedup as dd
from core.datablock_dedup import MemberInfo


def test_identical_family_merges_into_base():
    members = [MemberInfo("Walk", "fpA", users=3),
               MemberInfo("Walk.001", "fpA", users=1),
               MemberInfo("Walk.002", "fpA", users=2)]
    plans, conflicts = dd.plan_merges(members)
    assert conflicts == []
    assert len(plans) == 1
    p = plans[0]
    assert p.base == "Walk"
    assert p.canonical == "Walk"
    assert p.redundant == ["Walk.001", "Walk.002"]


def test_canonical_falls_back_to_most_users_when_base_absent():
    members = [MemberInfo("Run.001", "fpW", users=1),
               MemberInfo("Run.002", "fpW", users=5)]
    plans, conflicts = dd.plan_merges(members)
    assert conflicts == []
    assert plans[0].canonical == "Run.002"
    assert plans[0].redundant == ["Run.001"]


def test_differing_content_not_merged_but_flagged():
    members = [MemberInfo("Pose", "fpX", users=1), MemberInfo("Pose.001", "fpY", users=1)]
    plans, conflicts = dd.plan_merges(members)
    assert plans == []
    assert len(conflicts) == 1
    assert conflicts[0].base == "Pose"
    assert "differing content" in conflicts[0].reason


def test_unverified_fingerprint_not_merged():
    members = [MemberInfo("Gone", "", users=1), MemberInfo("Gone.001", "", users=1)]
    plans, conflicts = dd.plan_merges(members)
    assert plans == []
    assert conflicts and "unverified" in conflicts[0].reason


def test_differing_content_and_unverified_both_reported():
    # A family that's BOTH split across 2 real content groups AND has a member
    # with no fingerprint at all -- the reason must say both, not just the
    # first one checked (regression: used to silently drop the unverified half).
    members = [MemberInfo("Pose", "fpX", users=1), MemberInfo("Pose.001", "fpY", users=1),
               MemberInfo("Pose.002", "", users=1)]
    plans, conflicts = dd.plan_merges(members)
    assert plans == []
    assert len(conflicts) == 1
    assert "differing content" in conflicts[0].reason
    assert "unverified" in conflicts[0].reason


def test_lone_numbered_copy_is_not_a_family():
    members = [MemberInfo("Solo.001", "fp", users=1)]
    plans, conflicts = dd.plan_merges(members)
    assert plans == [] and conflicts == []


def test_removable_count():
    members = [MemberInfo("A", "fp", users=1), MemberInfo("A.001", "fp", users=1),
               MemberInfo("A.002", "fp", users=1)]
    plans, _conflicts = dd.plan_merges(members)
    assert dd.removable_count(plans) == 2


def test_victims_for_keeper_follows_user_choice():
    members = ["Walk", "Walk.001", "Walk.002"]
    assert dd.victims_for_keeper(members, "Walk") == ["Walk.001", "Walk.002"]
    assert dd.victims_for_keeper(members, "Walk.001") == ["Walk", "Walk.002"]
