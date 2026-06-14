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
    "broken_link": "Broken links",
    "absolute_path": "Absolute paths",
    "circular_link": "Circular references",
    "unreadable_file": "Unreadable files",
    "linked_library": "Linked libraries",
    "orphan": "Orphans",
    "fake_only": "Fake-user only",
    "identical": "Identical datablocks",
    "duplicate_group": "Duplicate Materials",
    "linked_victim": "Linked duplicates",
    "summary": "Summary",
}


@dataclass
class TreeNode:
    key: str  # unique, stable path key
    label: str
    severity: str = "info"
    children: list["TreeNode"] = field(default_factory=list)
    ref: dict | None = None  # optional {"type","name"} for click-to-select
    detail: str = ""  # optional right-aligned value column (e.g. sizes)


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


def node_to_dict(n: TreeNode) -> dict:
    return {
        "key": n.key, "label": n.label, "severity": n.severity, "detail": n.detail,
        "ref": n.ref, "children": [node_to_dict(c) for c in n.children],
    }


def node_from_dict(d: dict) -> TreeNode:
    return TreeNode(
        key=d["key"], label=d["label"], severity=d.get("severity", "info"),
        detail=d.get("detail", ""), ref=d.get("ref"),
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


def report_to_tree(report: Report) -> list[TreeNode]:
    """category → finding(message) → item leaves, with rolled-up severities."""
    groups: dict[str, list] = {}
    for f in report.findings:
        groups.setdefault(f.category, []).append(f)

    nodes: list[TreeNode] = []
    for cat, findings in groups.items():
        cat_key = f"{report.feature}:{cat}"
        cat_node = TreeNode(
            key=cat_key,
            label=_CATEGORY_TITLES.get(cat, cat),
            severity=_max_severity(f.severity for f in findings),
            detail=str(len(findings)),  # count shown on the (collapsed) category row
        )
        for i, f in enumerate(findings):
            f_key = f"{cat_key}:{i}"
            f_node = TreeNode(key=f_key, label=f.message, severity=f.severity)
            for j, item in enumerate(f.items):
                f_node.children.append(
                    TreeNode(key=f"{f_key}:{j}", label=item, severity=f.severity,
                             ref=_parse_ref(item))
                )
            cat_node.children.append(f_node)
        nodes.append(cat_node)
    return nodes


def flatten_visible(nodes: list[TreeNode], expanded: set[str]) -> list[Row]:
    """DFS into ``expanded`` nodes only, producing ordered indented rows."""
    rows: list[Row] = []

    def walk(node: TreeNode, depth: int) -> None:
        has = bool(node.children)
        is_exp = node.key in expanded
        rows.append(Row(depth, node.key, node.label, node.severity, has, is_exp,
                        node.ref, node.detail))
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
