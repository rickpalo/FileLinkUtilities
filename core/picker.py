"""Flatten picker-row flatteners for virtualized results-section UILists.

Converts a section's live grouping into a flat ordered list of PickerRow specs
— the visible-rows analogue of core.tree.flatten_visible. Two shapes so far
(Group 12): flatten_picker_rows (two-level, group-level checkbox — Flattenable
Overrides, Phase 2) and flatten_group_member_rows (single-level, member rows
each drawing their own widgets — Missing Textures, Duplicate Textures, and
later Reconnect/Examine Library, Phase 3; the group's label/icon/alert/
has_action are pre-computed by the caller, since that's genuinely different
per section, while the flatten/expand shell is shared). bpy-free — testable
with plain Python, no Blender import needed.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MemberData:
    """Plain-Python mirror of FILELINK_PG_flatten_candidate's per-row data,
    extractable without bpy so the flatten helper stays testable."""
    name: str
    status: str
    ready: bool
    done: bool
    is_remote: bool
    is_rig: bool
    ref_index: int  # index into the real wm.filelink_flatten_candidates collection


@dataclass
class PickerRow:
    """One row in the flat ordered list the UIList renders from."""
    kind: str                  # "outer" | "group" | "rollup" | "member"
    key: str = ""              # toggle/action key (group/outer rows)
    group_key: str = ""        # parent group key (member + nested-group rows)
    children_keys: str = ""    # newline-joined child rig keys (outer rows only)
    ref_prop: str = ""         # WM collection name ref_index points into (member rows only)
    ref_index: int = -1        # index into real collection (member rows only)
    indent: int = 0
    label: str = ""
    icon: str = ""
    checkbox_state: str = "none"  # "none" | "checked" | "unchecked" | "done"
    has_action: bool = False   # group rows only: show the header's action button
    has_action2: bool = False  # group rows only: show a SECOND header action (section-defined)
    alert: bool = False        # group rows only: show the header's label in alert/red styling
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


@dataclass
class MemberRef:
    """A single-level-shape member row's live-data pointer — nothing else.
    The member row itself is drawn straight from the real PropertyGroup item
    (checkbox, label, target/keeper widgets — all section-specific), so this
    flatten layer only needs to know WHERE it lives; identical live-data
    approach to FILELINK_UL_broken_libs's flat case."""
    ref_index: int


@dataclass
class GroupSpec:
    """One single-level section's fully-formed group row. Label/icon/alert/
    has_action are computed by the CALLER (each section's grouping semantics —
    "matched" counts for Missing Textures, "mismatch" counts for Duplicate
    Textures, etc. — are section-specific and deliberately kept out of this
    bpy-free shell, same "shell vs flexibility" split as ``_draw_group_header``).
    ``groups`` passed to ``flatten_group_member_rows`` must already be in the
    desired display order."""
    key: str            # raw grouping key (toggle/expand identity)
    label: str          # full display text, count suffix included
    icon: str
    members: list[MemberRef]
    has_action: bool = False  # show the header's action button
    has_action2: bool = False  # show a SECOND header action (meaning is section-defined)
    alert: bool = False       # show the header's label in Blender's alert/red styling
    info: str = ""      # optional one-line status shown right under an expanded group
    info_icon: str = "INFO"  # icon for the info line (e.g. an error/question state)


@dataclass
class CategorySpec:
    """One top-level, collapsible-by-default category wrapping several
    single-level groups (Missing Textures' "Missing Material/World/Other
    Textures" split, 2026-07-09) — one level ABOVE :class:`GroupSpec`. Reuses
    the "outer" ``PickerRow.kind`` the Flattenable Overrides picker already
    established for a collapsible top row, so the UIList only needs one more
    ``kind`` branch, not a new row vocabulary. ``key`` should be namespaced
    (distinct from any real group/material key) so it can't collide in the
    shared expanded-set string; ``groups``' own ``key``s are NOT touched here —
    they stay the raw grouping identity (e.g. a material name) some group-level
    actions (``point_group_at_folder``) look up directly."""
    key: str
    label: str          # full display text, count suffix included (the "summary")
    icon: str
    groups: list[GroupSpec]


def flatten_category_group_member_rows(
    categories: list[CategorySpec],
    expanded: set[str],
    ref_prop: str,
) -> list[PickerRow]:
    """3-level version of :func:`flatten_group_member_rows`: category (indent 0,
    collapsed unless its key is in ``expanded`` — same "absent = collapsed"
    default every other section already uses, so a fresh scan starts every
    category collapsed with no extra state to seed) -> group (indent 1) ->
    member (indent 2)."""
    rows: list[PickerRow] = []
    for cat in categories:
        is_exp = cat.key in expanded
        rows.append(PickerRow(
            kind="outer",
            key=cat.key,
            indent=0,
            label=cat.label,
            icon=cat.icon,
            is_expanded=is_exp,
        ))
        if not is_exp:
            continue
        for g in cat.groups:
            is_gexp = g.key in expanded
            rows.append(PickerRow(
                kind="group",
                key=g.key,
                group_key=cat.key,
                indent=1,
                label=g.label,
                icon=g.icon,
                has_action=g.has_action,
                alert=g.alert,
                is_expanded=is_gexp,
            ))
            if is_gexp and g.info:
                rows.append(PickerRow(kind="rollup", group_key=g.key, indent=3,
                                      label=g.info, icon=g.info_icon))
            if not is_gexp:
                continue
            for m in g.members:
                rows.append(PickerRow(
                    kind="member",
                    key=g.key,
                    group_key=g.key,
                    ref_prop=ref_prop,
                    ref_index=m.ref_index,
                    indent=2,
                ))
    return rows


def flatten_group_member_rows(
    groups: list[GroupSpec],
    expanded: set[str],
    ref_prop: str,
) -> list[PickerRow]:
    """Return the flat ordered list of visible rows for a single-level
    group->member section (Group 12 Phase 3 — Missing Textures, Duplicate
    Textures, Datablock Reconnect, and later Examine Library all share this
    shell) given current expand state. ``ref_prop`` is the WM collection name
    every member row's ``ref_index`` points into."""
    rows: list[PickerRow] = []
    for g in groups:
        is_exp = g.key in expanded
        rows.append(PickerRow(
            kind="group",
            key=g.key,
            indent=0,
            label=g.label,
            icon=g.icon,
            has_action=g.has_action,
            has_action2=g.has_action2,
            alert=g.alert,
            is_expanded=is_exp,
        ))
        if is_exp and g.info:
            rows.append(PickerRow(kind="rollup", group_key=g.key, indent=2,
                                  label=g.info, icon=g.info_icon))
        if not is_exp:
            continue
        for m in g.members:
            rows.append(PickerRow(
                kind="member",
                key=g.key,
                group_key=g.key,
                ref_prop=ref_prop,
                ref_index=m.ref_index,
                indent=2,
            ))

    return rows
