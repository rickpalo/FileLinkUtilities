"""Flatten picker-row flattener for virtualized group-checkbox UILists.

Converts nested {group_key: [MemberData]} groupings into a flat ordered list
of PickerRow specs — the visible-rows analogue of core.tree.flatten_visible,
for the Flattenable Overrides picker (and, in Phase 3, other group-checkbox
sections). bpy-free — testable with plain Python, no Blender import needed.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MemberData:
    """Plain-Python mirror of ASSETDOCTOR_PG_flatten_candidate's per-row data,
    extractable without bpy so the flatten helper stays testable."""
    name: str
    status: str
    ready: bool
    done: bool
    is_remote: bool
    is_rig: bool
    ref_index: int  # index into the real wm.assetdoctor_flatten_candidates collection


@dataclass
class PickerRow:
    """One row in the flat ordered list the UIList renders from."""
    kind: str                  # "outer" | "group" | "rollup" | "member"
    key: str = ""              # toggle/action key (group/outer rows)
    group_key: str = ""        # parent group key (member + nested-group rows)
    children_keys: str = ""    # newline-joined child rig keys (outer rows only)
    ref_index: int = -1        # index into real collection (member rows only)
    indent: int = 0
    label: str = ""
    icon: str = ""
    checkbox_state: str = "none"  # "none" | "checked" | "unchecked" | "done"
    is_expanded: bool = False


def _group_checkbox_state(key: str, members: list[MemberData], deselected: set[str]) -> str:
    if all(m.done for m in members):
        return "done"
    return "unchecked" if key in deselected else "checked"


def _member_icon(m: MemberData) -> str:
    if m.done:
        return "CHECKMARK"
    if m.is_remote:
        return "QUESTION"
    return "CHECKMARK" if m.ready else "ERROR"


def _group_label(key: str, members: list[MemberData]) -> str:
    label = key.split(" :: ", 1)[-1] if " :: " in key else key
    ready = sum(1 for m in members if m.ready)
    if all(m.done for m in members):
        return f"{label}  ({len(members)} part(s) flattened)"
    if members[0].is_remote:
        return f"{label}  ({len(members)} part(s), remote)"
    return f"{label}  ({ready}/{len(members)} part(s) ready)"


def _group_icon(members: list[MemberData]) -> str:
    if members[0].is_rig:
        return "ARMATURE_DATA"
    if members[0].is_remote:
        return "LINKED"
    return "OBJECT_DATA"


def flatten_picker_rows(
    groups: dict[str, list[MemberData]],
    order: list[str],
    outer_order: list[str],
    outer_children: dict[str, list[str]],
    expanded: set[str],
    deselected: set[str],
    rollups: dict[str, str] | None = None,
) -> list[PickerRow]:
    """Return the flat ordered list of visible rows given current expand/deselect state.

    ``groups``         — rig-key → list of MemberData, ALL groups (local + remote).
    ``order``          — local rig keys in the desired sort order.
    ``outer_order``    — outer group_parent keys in sort order.
    ``outer_children`` — outer key → [rig keys] for each remote group, in sort order.
    ``expanded``       — set of currently-expanded keys.
    ``deselected``     — set of rig keys whose group-checkbox is UNCHECKED.
    ``rollups``        — optional rig → pre-computed rollup text (from build_rig_rollup).
    """
    rows: list[PickerRow] = []
    rollups = rollups or {}

    # Local groups (flat, no outer header)
    for rig in order:
        members = groups[rig]
        is_exp = rig in expanded
        rows.append(PickerRow(
            kind="group",
            key=rig,
            indent=0,
            label=_group_label(rig, members),
            icon=_group_icon(members),
            checkbox_state=_group_checkbox_state(rig, members, deselected),
            is_expanded=is_exp,
        ))
        if is_exp:
            if rig in rollups:
                rows.append(PickerRow(kind="rollup", indent=2, label=rollups[rig]))
            for m in members:
                rows.append(PickerRow(
                    kind="member",
                    key=rig,
                    group_key=rig,
                    ref_index=m.ref_index,
                    indent=2,
                    label=f"{m.name}  —  {m.status}",
                    icon=_member_icon(m),
                ))

    # Remote outer groups (each expands to nested rig sub-groups)
    for group_parent in outer_order:
        children = outer_children.get(group_parent, [])
        total_members = sum(len(groups.get(rig, [])) for rig in children)
        all_checked = all(rig not in deselected for rig in children)
        is_exp = group_parent in expanded
        rows.append(PickerRow(
            kind="outer",
            key=group_parent,
            children_keys="\n".join(children),
            indent=0,
            label=(f"{group_parent}  ({total_members} part(s) "
                   f"across {len(children)} character(s))"),
            icon="LIBRARY_DATA_OVERRIDE",
            checkbox_state="checked" if all_checked else "unchecked",
            is_expanded=is_exp,
        ))
        if not is_exp:
            continue
        for rig in children:
            members = groups.get(rig, [])
            is_rig_exp = rig in expanded
            rows.append(PickerRow(
                kind="group",
                key=rig,
                group_key=group_parent,
                indent=1,
                label=_group_label(rig, members),
                icon=_group_icon(members),
                checkbox_state=_group_checkbox_state(rig, members, deselected),
                is_expanded=is_rig_exp,
            ))
            if is_rig_exp:
                if rig in rollups:
                    rows.append(PickerRow(kind="rollup", indent=3, label=rollups[rig]))
                for m in members:
                    rows.append(PickerRow(
                        kind="member",
                        key=rig,
                        group_key=group_parent,
                        ref_index=m.ref_index,
                        indent=3,
                        label=f"{m.name}  —  {m.status}",
                        icon=_member_icon(m),
                    ))

    return rows
