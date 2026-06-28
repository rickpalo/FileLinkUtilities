"""Unit tests for core.f3_materials (bpy-free)."""

from core.f3_materials import build_dedup_plan, choose_canonical, parse_name_list


def test_parse_name_list():
    assert parse_name_list("") == []
    assert parse_name_list("a, b ;c\nd") == ["a", "b", "c", "d"]
    assert parse_name_list("wood*, metal") == ["wood*", "metal"]


def _m(id_, name, linked=False, max_res=0):
    return {"id": id_, "name": name, "linked": linked, "max_res": max_res, "fingerprint": "H"}


def test_canonical_prefers_highest_resolution():
    members = [_m("Wood1K", "Wood", max_res=1024), _m("Wood2K", "Wood", max_res=2048)]
    best, reason = choose_canonical(members, [], [])
    assert best["id"] == "Wood2K"
    assert "resolution" in reason


def test_canonical_local_over_linked_at_equal_res():
    members = [_m("WoodLib", "Wood", linked=True, max_res=2048),
               _m("WoodLocal", "Wood", linked=False, max_res=2048)]
    best, _ = choose_canonical(members, [], [])
    assert best["id"] == "WoodLocal"


def test_canonical_prefers_linked_when_requested():
    # docs/TODO.md #21, 2026-06-27: an explicit preference can flip the tie-break.
    members = [_m("WoodLib", "Wood", linked=True, max_res=2048),
               _m("WoodLocal", "Wood", linked=False, max_res=2048)]
    best, _ = choose_canonical(members, [], [], prefer_linked=True)
    assert best["id"] == "WoodLib"


def test_prefer_linked_loses_to_whitelist():
    # whitelist/blacklist still take precedence over the local/linked preference.
    members = [_m("WoodLib", "WoodLib", linked=True, max_res=2048),
               _m("WoodLocal", "WoodLocal", linked=False, max_res=2048)]
    best, reason = choose_canonical(members, ["WoodLocal"], [], prefer_linked=True)
    assert best["id"] == "WoodLocal"
    assert reason == "whitelisted"


def test_whitelist_wins_over_resolution():
    members = [_m("WoodHi", "WoodHi", max_res=4096), _m("WoodMaster", "WoodMaster", max_res=512)]
    best, reason = choose_canonical(members, ["WoodMaster"], [])
    assert best["id"] == "WoodMaster"
    assert reason == "whitelisted"


def test_blacklisted_never_canonical():
    members = [_m("WoodBad", "WoodBad", max_res=4096), _m("WoodGood", "WoodGood", max_res=512)]
    best, _ = choose_canonical(members, [], ["WoodBad"])
    assert best["id"] == "WoodGood"


def test_all_blacklisted_keeps_best_with_note():
    members = [_m("A", "A", max_res=512), _m("B", "B", max_res=2048)]
    best, reason = choose_canonical(members, [], ["A", "B"])
    assert best["id"] == "B"  # highest res among the forced pool
    assert "blacklisted" in reason


def test_glob_patterns_match():
    members = [_m("wood_master", "wood_master", max_res=256), _m("wood_2k", "wood_2k", max_res=2048)]
    best, _ = choose_canonical(members, ["wood_master*"], [])
    assert best["id"] == "wood_master"


def test_build_plan_groups_and_report():
    items = [
        _m("WoodA", "WoodA", max_res=1024),
        _m("WoodB", "WoodB", max_res=2048),
        {"id": "Stone", "name": "Stone", "linked": False, "max_res": 0, "fingerprint": "OTHER"},
    ]
    report, plan = build_dedup_plan(items)
    assert len(plan) == 1
    group = plan[0]
    assert group["canonical"] == "WoodB"  # higher res
    assert group["victims"] == ["WoodA"]
    # No Summary finding anymore; the headline lives on the category row.
    assert not any(f.category == "summary" for f in report.findings)
    assert report.category_details["duplicate_material"] == "1 (1 Local & 0 Linked)"
    local = next(f for f in report.findings if f.message == "Local")
    assert local.items == ["WoodA"] and local.detail == "1"


def test_build_plan_splits_local_and_linked_victims():
    items = [
        _m("WoodLocal", "Wood", linked=False, max_res=2048),   # canonical (local preferred)
        _m("WoodLib", "Wood", linked=True, max_res=2048),      # linked victim
        _m("WoodLocal2", "Wood", linked=False, max_res=2048),  # local victim
    ]
    report, plan = build_dedup_plan(items)
    assert plan[0]["canonical"] == "WoodLocal"
    assert plan[0]["linked_victims"] == ["WoodLib"]
    assert report.category_details["duplicate_material"] == "2 (1 Local & 1 Linked)"
    local = next(f for f in report.findings if f.message == "Local")
    linked = next(f for f in report.findings if f.message.startswith("Linked"))
    assert local.items == ["WoodLocal2"]
    assert linked.items == ["WoodLib"]


def test_build_plan_no_duplicates_reports_none():
    items = [_m("A", "A"), {"id": "B", "name": "B", "linked": False, "max_res": 0,
                            "fingerprint": "ZZZ"}]
    items[0]["fingerprint"] = "AAA"
    report, plan = build_dedup_plan(items)
    assert plan == []
    assert report.category_details["duplicate_material"] == "0 (0 Local & 0 Linked)"
    assert any(f.message == "No duplicate materials found" for f in report.findings)


def test_no_duplicates_empty_plan():
    items = [_m("A", "A"), {"id": "B", "name": "B", "linked": False, "max_res": 0,
                            "fingerprint": "ZZZ"}]
    # distinct fingerprints
    items[0]["fingerprint"] = "AAA"
    report, plan = build_dedup_plan(items)
    assert plan == []
