"""Tests for core.picker.flatten_picker_rows."""
import pytest
from core.picker import MemberData, PickerRow, flatten_picker_rows


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
