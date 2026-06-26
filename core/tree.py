"""A reusable tree model for displaying reports (and later the F5 resource
hierarchy) in Blender's UI. bpy-free and unit-tested.

A `Report` (flat findings) converts to a 3-level tree: category → finding →
item. `flatten_visible` turns a tree + a set of expanded node keys into the
ordered, indented row list the panel draws (Blender has no native tree widget,
so we render a flattened list with indentation + expand toggles).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .report import SEVERITIES, Report

# Prettier titles for known finding categories; falls back to the raw category.
_CATEGORY_TITLES = {
    "broken_link": "Broken Library Links",
    "absolute_path": "Absolute paths",
    "circular_link": "Circular references",
    "unreadable_file": "Unreadable files",
    "linked_library": "Linked libraries",
    "orphan": "Orphans",
    "fake_only": "Fake-user only",
    "identical": "Identical datablocks",
    "duplicate_group": "Duplicate Materials",
    "instanceable": "Duplicate Geometry",
    "duplicate_material": "Duplicate Materials",
    "linked_victim": "Linked duplicates",
    "relink_missing": "Relink missing libraries",
    "normalize_path": "Normalize paths",
    "duplicate_library": "Duplicate library blocks",
    "relink_texture": "Relink missing textures",
    "found_texture": "Found textures",
    "unresolved_texture": "Still missing",
    "merge_lossless": "Merge duplicates (lossless)",
    "family_conflict": "Name family, content differs",
    "res_variant": "Multi-resolution variants (footprint)",
    "direct_dependent": "Linked directly by",
    "indirect_dependent": "Linked indirectly by",
    "overview": "Summary",
    "clean": "Status",
    "summary": "Summary",
    "override_loop": "Override dependency loops (cause resync spam / bloat)",
    "shape_key_override_risk": "Shape keys at risk (override-mesh write warnings)",
    "duplicate_family": "Duplicate data-blocks (.NNN copies — wasted memory)",
    "multihop_route": "Multi-hop link chains",
    "posing_override": "Flattenable overrides (Library Override + transform)",
    "posing_modifier": "Modifier-driven (not flattenable yet)",
    "flatten_plan": "Flatten plan (preview — applies nothing)",
    "flatten_warning": "Flatten plan — blocked / needs attention",
    "flatten_applied": "Flattened",
    "library_block": "Linked data-blocks per library",
    "missing_image": "Missing images (render-time)",
    "driver_error": "Driver errors",
    "render_error": "Render errors",
    "render_warning": "Render warnings",
}


@dataclass
class TreeNode:
    key: str  # unique, stable path key
    label: str
    severity: str = "info"
    children: list["TreeNode"] = field(default_factory=list)
    ref: dict | None = None  # optional {"type","name"} for click-to-select
    detail: str = ""  # optional right-aligned value column (e.g. sizes)
    icon: str = ""  # optional Blender icon id override (e.g. "FILE_BLEND")


@dataclass
class Row:
    indent: int
    key: str
    label: str
    severity: str
    has_children: bool
    expanded: bool
    ref: dict | None = None
    detail: str = ""
    icon: str = ""


def node_to_dict(n: TreeNode) -> dict:
    return {
        "key": n.key, "label": n.label, "severity": n.severity, "detail": n.detail,
        "ref": n.ref, "icon": n.icon, "children": [node_to_dict(c) for c in n.children],
    }


def node_from_dict(d: dict) -> TreeNode:
    return TreeNode(
        key=d["key"], label=d["label"], severity=d.get("severity", "info"),
        detail=d.get("detail", ""), ref=d.get("ref"), icon=d.get("icon", ""),
        children=[node_from_dict(c) for c in d.get("children", [])],
    )


def nodes_to_json(nodes: list[TreeNode]) -> str:
    return json.dumps([node_to_dict(n) for n in nodes])


def nodes_from_json(text: str) -> list[TreeNode]:
    return [node_from_dict(d) for d in json.loads(text)]


def _max_severity(sevs) -> str:
    present = set(sevs)
    for sev in reversed(SEVERITIES):
        if sev in present:
            return sev
    return "info"


def _parse_ref(item: str) -> dict | None:
    """Recognise a "Type/Name" datablock label (not a file path)."""
    if item.count("/") != 1:
        return None
    type_, name = item.split("/", 1)
    if not type_ or not name or "\\" in type_ or " " in type_ or "." in type_:
        return None
    return {"type": type_, "name": name}


# Categories rendered as a flat top-level row (the message IS the whole content,
# no items to drill into): "clean" (the all-clear status) and "overview" (a one-line
# headline a feature wants read without expanding — e.g. the missing-data-block count).
# "summary" is intentionally NOT here — it stays a collapsible "Summary" category by
# design (several tests assert that).
_FLAT_CATEGORIES = {"clean", "overview"}


def report_to_tree(report: Report) -> list[TreeNode]:
    """category → finding(message) → item leaves, with rolled-up severities.
    Exception: ``clean`` status findings are hoisted to a flat top-level row."""
    groups: dict[str, list] = {}
    for f in report.findings:
        groups.setdefault(f.category, []).append(f)

    # Overview (flat headline) first, then Summary, then the rest in original
    # order (user: summary on top; overview — when present — reads even higher,
    # since it's a single glance line rather than a collapsible category).
    ordered = ([c for c in groups if c == "overview"]
               + [c for c in groups if c == "summary"]
               + [c for c in groups if c not in ("overview", "summary")])

    nodes: list[TreeNode] = []
    for cat in ordered:
        findings = groups[cat]
        cat_key = f"{report.feature}:{cat}"
        # "clean"/status findings render as a DIRECT top-level row (no collapsible
        # wrapper), so an all-clear result shows on the summary line instead of
        # making the user expand a "Status" category to read it (user, 2026-06-22).
        if cat in _FLAT_CATEGORIES:
            for i, f in enumerate(findings):
                nodes.append(TreeNode(key=f"{cat_key}:{i}", label=f.message,
                                      severity=f.severity, detail=f.detail))
            continue
        # Category row detail: a feature-supplied override (e.g. F3's local/linked
        # breakdown) or, by default, the number of findings in the category.
        detail = report.category_details.get(cat) or str(len(findings))
        cat_node = TreeNode(
            key=cat_key,
            label=_CATEGORY_TITLES.get(cat, cat),
            severity=_max_severity(f.severity for f in findings),
            detail=detail,
        )
        for i, f in enumerate(findings):
            f_key = f"{cat_key}:{i}"
            f_node = TreeNode(key=f_key, label=f.message, severity=f.severity, detail=f.detail)
            for j, item in enumerate(f.items):
                f_node.children.append(
                    TreeNode(key=f"{f_key}:{j}", label=item, severity=f.severity,
                             ref=_parse_ref(item))
                )
            cat_node.children.append(f_node)
        nodes.append(cat_node)
    return nodes


def flatten_visible(nodes: list[TreeNode], expanded: set[str]) -> list[Row]:
    """DFS into ``expanded`` nodes only, producing ordered indented rows.

    Indentation is plain depth only (no ASCII tree-connector glyphs) — a
    file-explorer-style "│  ├─ " guide was tried and dropped (user feedback,
    2026-06-25: "garbage, don't want it"); every report renders the same
    plain icon + indent + label shape now, matching the Missing Textures
    section's house style."""
    rows: list[Row] = []

    def walk(node: TreeNode, depth: int) -> None:
        has = bool(node.children)
        is_exp = node.key in expanded
        rows.append(Row(depth, node.key, node.label, node.severity, has, is_exp,
                        node.ref, node.detail, node.icon))
        if has and is_exp:
            for child in node.children:
                walk(child, depth + 1)

    for n in nodes:
        walk(n, 0)
    return rows


def top_level_keys(nodes: list[TreeNode]) -> list[str]:
    """Keys of the root nodes (used to auto-expand categories on a fresh report)."""
    return [n.key for n in nodes]


def all_keys(nodes: list[TreeNode]) -> set[str]:
    """Every node key in the tree (used to fully expand for text export)."""
    keys: set[str] = set()

    def walk(node: TreeNode) -> None:
        keys.add(node.key)
        for c in node.children:
            walk(c)

    for n in nodes:
        walk(n)
    return keys
