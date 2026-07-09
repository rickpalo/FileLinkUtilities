"""Tests for core.picker.flatten_picker_rows."""
import pytest
from core.picker import (MemberData, PickerRow, GroupSpec, MemberRef, CategorySpec,
                         flatten_picker_rows, flatten_group_member_rows,
                         flatten_category_group_member_rows)


def _m(name, *, ready=True, done=False, is_remote=False, is_rig=True, ref_index=0, status="ok"):
    return MemberData(name=name, status=status, ready=ready, done=done,
                      is_remote=is_remote, is_rig=is_rig, ref_index=ref_index)


# --- basic cases ---

def test_empty_input():
    rows = flatten_picker_rows({}, [], [], {}, set(), set())
    assert rows == []


def test_single_collapsed_group():
    groups = {"Rig_A": [_m("Body"), _m("Eyes")]}
    rows = flatten_picker_rows(groups, ["Rig_A"], [], {}, set(), set())
    assert len(rows) == 1
    r = rows[0]
    assert r.kind == "group"
    assert r.key == "Rig_A"
    assert r.is_expanded is False
    assert r.checkbox_state == "checked"
    assert "2/2" in r.label


def test_collapsed_group_hides_members():
    groups = {"Rig_A": [_m("Body"), _m("Eyes")]}
    rows = flatten_picker_rows(groups, ["Rig_A"], [], {}, set(), set())
    assert all(r.kind != "member" for r in rows)


# --- expand / collapse ---

def test_expanded_group_shows_members():
    groups = {"Rig_A": [_m("Body", ref_index=0), _m("Eyes", ref_index=1)]}
    rows = flatten_picker_rows(groups, ["Rig_A"], [], {}, {"Rig_A"}, set())
    kinds = [r.kind for r in rows]
    assert kinds == ["group", "member", "member"]
    assert rows[1].ref_index == 0
    assert rows[2].ref_index == 1


def test_rollup_inserted_before_members_when_expanded():
    groups = {"Rig_A": [_m("Body")]}
    rows = flatten_picker_rows(groups, ["Rig_A"], [], {}, {"Rig_A"}, set(),
                               rollups={"Rig_A": "loc, rot"})
    kinds = [r.kind for r in rows]
    assert kinds == ["group", "rollup", "member"]
    assert rows[1].label == "loc, rot"
    assert rows[1].icon == ""


def test_rollup_not_present_when_collapsed():
    groups = {"Rig_A": [_m("Body")]}
    rows = flatten_picker_rows(groups, ["Rig_A"], [], {}, set(), set(),
                               rollups={"Rig_A": "loc"})
    assert all(r.kind != "rollup" for r in rows)


# --- checkbox states ---

def test_deselected_group_state():
    groups = {"Rig_A": [_m("Body")]}
    rows = flatten_picker_rows(groups, ["Rig_A"], [], {}, set(), {"Rig_A"})
    assert rows[0].checkbox_state == "unchecked"


def test_done_group_state():
    groups = {"Rig_A": [_m("Body", done=True), _m("Eyes", done=True)]}
    rows = flatten_picker_rows(groups, ["Rig_A"], [], {}, set(), set())
    assert rows[0].checkbox_state == "done"
    assert "flattened" in rows[0].label


def test_partially_done_group_not_done_state():
    groups = {"Rig_A": [_m("Body", done=True), _m("Eyes", done=False)]}
    rows = flatten_picker_rows(groups, ["Rig_A"], [], {}, set(), set())
    assert rows[0].checkbox_state == "checked"


# --- member icons ---

def test_member_icon_ready():
    groups = {"R": [_m("Body", ready=True, done=False, is_remote=False)]}
    rows = flatten_picker_rows(groups, ["R"], [], {}, {"R"}, set())
    member = next(r for r in rows if r.kind == "member")
    assert member.icon == "CHECKMARK"


def test_member_icon_blocked():
    groups = {"R": [_m("Body", ready=False, done=False, is_remote=False)]}
    rows = flatten_picker_rows(groups, ["R"], [], {}, {"R"}, set())
    member = next(r for r in rows if r.kind == "member")
    assert member.icon == "ERROR"


def test_member_icon_remote():
    groups = {"R": [_m("Body", ready=False, done=False, is_remote=True)]}
    rows = flatten_picker_rows(groups, ["R"], [], {}, {"R"}, set())
    member = next(r for r in rows if r.kind == "member")
    assert member.icon == "QUESTION"


# --- outer groups (remote) ---

def test_outer_group_collapsed():
    groups = {"f1 :: Rig_A": [_m("Body", is_remote=True, is_rig=True)]}
    outer_children = {"Remote: f1": ["f1 :: Rig_A"]}
    rows = flatten_picker_rows(groups, [], ["Remote: f1"], outer_children,
                               set(), set())
    assert len(rows) == 1
    assert rows[0].kind == "outer"
    assert rows[0].is_expanded is False
    assert "f1 :: Rig_A" in rows[0].children_keys


def test_outer_group_expanded_shows_nested_group():
    groups = {"f1 :: Rig_A": [_m("Body", is_remote=True, is_rig=True)]}
    outer_children = {"Remote: f1": ["f1 :: Rig_A"]}
    rows = flatten_picker_rows(groups, [], ["Remote: f1"], outer_children,
                               {"Remote: f1"}, set())
    kinds = [r.kind for r in rows]
    assert kinds == ["outer", "group"]
    assert rows[1].indent == 1
    assert rows[1].group_key == "Remote: f1"


def test_nested_group_expanded_shows_members():
    groups = {"f1 :: Rig_A": [_m("Body", is_remote=True, ref_index=5)]}
    outer_children = {"Remote: f1": ["f1 :: Rig_A"]}
    rows = flatten_picker_rows(groups, [], ["Remote: f1"], outer_children,
                               {"Remote: f1", "f1 :: Rig_A"}, set())
    kinds = [r.kind for r in rows]
    assert kinds == ["outer", "group", "member"]
    assert rows[2].ref_index == 5
    assert rows[2].indent == 3


def test_outer_checkbox_unchecked_when_any_child_deselected():
    groups = {
        "f1 :: Rig_A": [_m("Body", is_remote=True)],
        "f1 :: Rig_B": [_m("Eyes", is_remote=True)],
    }
    outer_children = {"Remote: f1": ["f1 :: Rig_A", "f1 :: Rig_B"]}
    rows = flatten_picker_rows(groups, [], ["Remote: f1"], outer_children,
                               set(), {"f1 :: Rig_A"})
    assert rows[0].kind == "outer"
    assert rows[0].checkbox_state == "unchecked"


def test_outer_checkbox_checked_when_all_children_selected():
    groups = {
        "f1 :: Rig_A": [_m("Body", is_remote=True)],
        "f1 :: Rig_B": [_m("Eyes", is_remote=True)],
    }
    outer_children = {"Remote: f1": ["f1 :: Rig_A", "f1 :: Rig_B"]}
    rows = flatten_picker_rows(groups, [], ["Remote: f1"], outer_children,
                               set(), set())
    assert rows[0].checkbox_state == "checked"


# --- order and indent ---

def test_order_is_respected():
    groups = {
        "Rig_B": [_m("Body_B")],
        "Rig_A": [_m("Body_A")],
    }
    rows = flatten_picker_rows(groups, ["Rig_B", "Rig_A"], [], {}, set(), set())
    assert rows[0].key == "Rig_B"
    assert rows[1].key == "Rig_A"


def test_local_groups_have_indent_zero():
    groups = {"Rig_A": [_m("Body")]}
    rows = flatten_picker_rows(groups, ["Rig_A"], [], {}, set(), set())
    assert rows[0].indent == 0


def test_member_indent_in_local_group():
    groups = {"Rig_A": [_m("Body")]}
    rows = flatten_picker_rows(groups, ["Rig_A"], [], {}, {"Rig_A"}, set())
    member = next(r for r in rows if r.kind == "member")
    assert member.indent == 2


def test_member_indent_in_nested_remote_group():
    groups = {"f1 :: Rig_A": [_m("Body", is_remote=True, ref_index=0)]}
    outer_children = {"Remote: f1": ["f1 :: Rig_A"]}
    rows = flatten_picker_rows(groups, [], ["Remote: f1"], outer_children,
                               {"Remote: f1", "f1 :: Rig_A"}, set())
    member = next(r for r in rows if r.kind == "member")
    assert member.indent == 3


# --- flatten_group_member_rows (Group 12 Phase 3, single-level shape) ---

def test_group_member_empty_input():
    assert flatten_group_member_rows([], set(), "filelink_broken_imgs") == []


def test_group_member_collapsed_hides_members():
    g = GroupSpec(key="Wood", label="Wood  (1)", icon="MATERIAL",
                 members=[MemberRef(ref_index=0)])
    rows = flatten_group_member_rows([g], set(), "filelink_broken_imgs")
    assert len(rows) == 1
    assert rows[0].kind == "group"
    assert rows[0].is_expanded is False


def test_group_member_expanded_shows_members_with_ref_prop():
    g = GroupSpec(key="Wood", label="Wood  (2)", icon="MATERIAL",
                 members=[MemberRef(ref_index=3), MemberRef(ref_index=7)])
    rows = flatten_group_member_rows([g], {"Wood"}, "filelink_broken_imgs")
    kinds = [r.kind for r in rows]
    assert kinds == ["group", "member", "member"]
    assert rows[1].ref_index == 3 and rows[1].ref_prop == "filelink_broken_imgs"
    assert rows[2].ref_index == 7 and rows[2].group_key == "Wood"


def test_group_member_label_icon_passed_through():
    g = GroupSpec(key="Wood", label="Wood  (2 of 2 matched)", icon="CHECKMARK",
                 members=[MemberRef(ref_index=0)])
    rows = flatten_group_member_rows([g], set(), "x")
    assert rows[0].label == "Wood  (2 of 2 matched)"
    assert rows[0].icon == "CHECKMARK"


def test_group_member_has_action_propagated():
    g = GroupSpec(key="Wood", label="Wood", icon="MATERIAL",
                 members=[MemberRef(ref_index=0)], has_action=True)
    rows = flatten_group_member_rows([g], set(), "x")
    assert rows[0].has_action is True


def test_group_member_has_action_defaults_false():
    g = GroupSpec(key="\x02", label="(no material)  (1)", icon="MATERIAL",
                 members=[MemberRef(ref_index=0)])
    rows = flatten_group_member_rows([g], set(), "x")
    assert rows[0].has_action is False


def test_group_member_alert_propagated():
    g = GroupSpec(key="Wood", label="Wood  (⚠1 mismatch)", icon="ERROR",
                 members=[MemberRef(ref_index=0)], alert=True)
    rows = flatten_group_member_rows([g], set(), "x")
    assert rows[0].alert is True


def test_group_member_alert_defaults_false():
    g = GroupSpec(key="Wood", label="Wood", icon="MATERIAL",
                 members=[MemberRef(ref_index=0)])
    rows = flatten_group_member_rows([g], set(), "x")
    assert rows[0].alert is False


def test_group_member_order_is_respected():
    a = GroupSpec(key="B", label="B", icon="MATERIAL", members=[MemberRef(ref_index=0)])
    b = GroupSpec(key="A", label="A", icon="MATERIAL", members=[MemberRef(ref_index=1)])
    rows = flatten_group_member_rows([a, b], set(), "x")
    assert [r.key for r in rows] == ["B", "A"]


def test_group_member_info_rollup_shown_when_expanded():
    g = GroupSpec(key="Wood", label="Wood", icon="MATERIAL",
                 members=[MemberRef(ref_index=0)], info="no source picked yet")
    rows = flatten_group_member_rows([g], {"Wood"}, "x")
    kinds = [r.kind for r in rows]
    assert kinds == ["group", "rollup", "member"]
    assert rows[1].label == "no source picked yet"
    assert rows[1].group_key == "Wood"
    assert rows[1].icon == "INFO"


def test_group_member_info_rollup_custom_icon():
    g = GroupSpec(key="Wood", label="Wood", icon="MATERIAL",
                 members=[MemberRef(ref_index=0)], info="library not found",
                 info_icon="ERROR")
    rows = flatten_group_member_rows([g], {"Wood"}, "x")
    rollup = next(r for r in rows if r.kind == "rollup")
    assert rollup.icon == "ERROR"


def test_group_member_info_rollup_hidden_when_collapsed():
    g = GroupSpec(key="Wood", label="Wood", icon="MATERIAL",
                 members=[MemberRef(ref_index=0)], info="no source picked yet")
    rows = flatten_group_member_rows([g], set(), "x")
    assert all(r.kind != "rollup" for r in rows)


def test_group_member_no_rollup_when_info_empty():
    g = GroupSpec(key="Wood", label="Wood", icon="MATERIAL",
                 members=[MemberRef(ref_index=0)])
    rows = flatten_group_member_rows([g], {"Wood"}, "x")
    assert all(r.kind != "rollup" for r in rows)


# --- flatten_category_group_member_rows (Missing Textures Material/World/Other
# category split, 2026-07-09, 3-level shape) ---

def test_category_empty_input():
    assert flatten_category_group_member_rows([], set(), "filelink_broken_imgs") == []


def test_category_collapsed_by_default_hides_everything_below():
    g = GroupSpec(key="Wood", label="Wood  (1)", icon="MATERIAL",
                 members=[MemberRef(ref_index=0)])
    cat = CategorySpec(key="\x03material", label="Missing Material Textures — 1",
                       icon="MATERIAL", groups=[g])
    rows = flatten_category_group_member_rows([cat], set(), "x")
    assert len(rows) == 1
    assert rows[0].kind == "outer"
    assert rows[0].is_expanded is False


def test_category_expanded_shows_group_but_not_members():
    g = GroupSpec(key="Wood", label="Wood  (1)", icon="MATERIAL",
                 members=[MemberRef(ref_index=0)])
    cat = CategorySpec(key="\x03material", label="Missing Material Textures — 1",
                       icon="MATERIAL", groups=[g])
    rows = flatten_category_group_member_rows([cat], {"\x03material"}, "x")
    kinds = [r.kind for r in rows]
    assert kinds == ["outer", "group"]
    assert rows[1].key == "Wood"
    assert rows[1].group_key == "\x03material"
    assert rows[1].indent == 1


def test_category_and_group_both_expanded_shows_members():
    g = GroupSpec(key="Wood", label="Wood  (1)", icon="MATERIAL",
                 members=[MemberRef(ref_index=9)])
    cat = CategorySpec(key="\x03material", label="Missing Material Textures — 1",
                       icon="MATERIAL", groups=[g])
    rows = flatten_category_group_member_rows(
        [cat], {"\x03material", "Wood"}, "filelink_broken_imgs")
    kinds = [r.kind for r in rows]
    assert kinds == ["outer", "group", "member"]
    assert rows[2].ref_index == 9
    assert rows[2].ref_prop == "filelink_broken_imgs"
    assert rows[2].group_key == "Wood"
    assert rows[2].indent == 2


def test_category_group_collapsed_hides_its_members_even_if_category_expanded():
    g = GroupSpec(key="Wood", label="Wood  (1)", icon="MATERIAL",
                 members=[MemberRef(ref_index=0)])
    cat = CategorySpec(key="\x03material", label="Missing Material Textures — 1",
                       icon="MATERIAL", groups=[g])
    rows = flatten_category_group_member_rows([cat], {"\x03material"}, "x")
    assert all(r.kind != "member" for r in rows)


def test_category_group_has_action_and_alert_propagated():
    g = GroupSpec(key="Wood", label="Wood", icon="MATERIAL",
                 members=[MemberRef(ref_index=0)], has_action=True, alert=True)
    cat = CategorySpec(key="\x03material", label="Missing Material Textures",
                       icon="MATERIAL", groups=[g])
    rows = flatten_category_group_member_rows([cat], {"\x03material"}, "x")
    group_row = next(r for r in rows if r.kind == "group")
    assert group_row.has_action is True
    assert group_row.alert is True


def test_category_group_info_rollup_shown_when_both_expanded():
    g = GroupSpec(key="Wood", label="Wood", icon="MATERIAL",
                 members=[MemberRef(ref_index=0)], info="no source picked yet")
    cat = CategorySpec(key="\x03material", label="Missing Material Textures",
                       icon="MATERIAL", groups=[g])
    rows = flatten_category_group_member_rows([cat], {"\x03material", "Wood"}, "x")
    kinds = [r.kind for r in rows]
    assert kinds == ["outer", "group", "rollup", "member"]


def test_category_order_is_respected():
    cat_a = CategorySpec(key="\x03material", label="A", icon="MATERIAL", groups=[])
    cat_b = CategorySpec(key="\x03world", label="B", icon="WORLD", groups=[])
    # Empty-groups categories still emit their own header row (the caller is
    # responsible for omitting a category with nothing in it, same contract
    # as GroupSpec with no members) -- order here just checks header ordering.
    rows = flatten_category_group_member_rows([cat_a, cat_b], set(), "x")
    assert [r.key for r in rows] == ["\x03material", "\x03world"]


def test_two_categories_independently_expanded():
    g1 = GroupSpec(key="Wood", label="Wood  (1)", icon="MATERIAL",
                   members=[MemberRef(ref_index=0)])
    g2 = GroupSpec(key="Sky", label="Sky  (1)", icon="WORLD",
                   members=[MemberRef(ref_index=1)])
    cat_material = CategorySpec(key="\x03material", label="Missing Material Textures — 1",
                                icon="MATERIAL", groups=[g1])
    cat_world = CategorySpec(key="\x03world", label="Missing World Textures — 1",
                             icon="WORLD", groups=[g2])
    # Only the World category is expanded -- Material's group must stay hidden.
    rows = flatten_category_group_member_rows(
        [cat_material, cat_world], {"\x03world", "Sky"}, "x")
    assert [r.kind for r in rows] == ["outer", "outer", "group", "member"]
    assert rows[2].key == "Sky"
