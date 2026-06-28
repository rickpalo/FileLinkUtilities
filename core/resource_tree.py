"""Build the F5 'by datablock type' resource tree. bpy-free.

Input: per-datablock estimate dicts from the ops layer:
    { "type": "Image", "name": "wood", "ram": int, "vram": int, "disk": int,
      "users": int }
Output: TreeNodes (type → datablock), each datablock counted ONCE, sorted
biggest-first by RAM, with rolled-up per-type totals and a grand total.
"""

from __future__ import annotations

from .resource import human_bytes
from .tree import TreeNode


SORT_KEYS = ("ram", "vram", "disk")


def build_resource_tree(items: list[dict], sort_by: str = "ram") -> tuple[list[TreeNode], dict]:
    """Return (type nodes sorted by total ``sort_by`` desc, grand totals dict).

    RAM/VRAM/disk are kept as separate ``TreeNode.ram``/``vram``/``disk``
    text columns (docs/TODO.md #15, 2026-06-27 — real aligned columns
    instead of one combined ``detail`` string). ``sort_by`` only reorders
    the top-level type groups (the rows actually visible before anything is
    expanded) — each group's own children stay RAM-sorted, unchanged."""
    if sort_by not in SORT_KEYS:
        sort_by = "ram"
    by_type: dict[str, list[dict]] = {}
    for it in items:
        by_type.setdefault(it["type"], []).append(it)

    typed_nodes: list[tuple[int, TreeNode]] = []
    g_ram = g_vram = g_disk = 0
    for type_name, members in by_type.items():
        t_ram = sum(m.get("ram", 0) for m in members)
        t_vram = sum(m.get("vram", 0) for m in members)
        t_disk = sum(m.get("disk", 0) for m in members)
        g_ram += t_ram
        g_vram += t_vram
        g_disk += t_disk
        totals_by_key = {"ram": t_ram, "vram": t_vram, "disk": t_disk}

        type_node = TreeNode(
            key=f"type:{type_name}",
            label=f"{type_name} ({len(members)})",
            ram=human_bytes(t_ram), vram=human_bytes(t_vram),
            disk=human_bytes(t_disk) if t_disk else "",
        )
        for m in sorted(members, key=lambda d: d.get("ram", 0), reverse=True):
            users = m.get("users", 0)
            disk = m.get("disk", 0)
            type_node.children.append(TreeNode(
                key=f"type:{type_name}:{m['name']}",
                label=f"{m['name']}  ({users}u)" if users else m["name"],
                ram=human_bytes(m.get("ram", 0)), vram=human_bytes(m.get("vram", 0)),
                disk=human_bytes(disk) if disk else "",
                ref={"type": type_name, "name": m["name"]},
            ))
        typed_nodes.append((totals_by_key[sort_by], type_node))

    typed_nodes.sort(key=lambda pair: pair[0], reverse=True)
    nodes = [node for _key, node in typed_nodes]
    totals = {"ram": g_ram, "vram": g_vram, "disk": g_disk}
    return nodes, totals
