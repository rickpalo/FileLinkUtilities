"""Unit tests for core.resource_tree + tree (de)serialization."""

from core.resource_tree import build_resource_tree
from core.tree import flatten_visible, nodes_from_json, nodes_to_json


def _items():
    return [
        {"type": "Image", "name": "big", "ram": 16_000_000, "vram": 21_000_000,
         "disk": 4_000_000, "users": 2},
        {"type": "Image", "name": "small", "ram": 1_000_000, "vram": 1_300_000,
         "disk": 200_000, "users": 1},
        {"type": "Mesh", "name": "Cube", "ram": 5_000, "vram": 3_000, "disk": 0, "users": 3},
    ]


def test_grand_totals():
    _nodes, totals = build_resource_tree(_items())
    assert totals["ram"] == 16_000_000 + 1_000_000 + 5_000
    assert totals["vram"] == 21_000_000 + 1_300_000 + 3_000
    assert totals["disk"] == 4_000_000 + 200_000


def test_types_sorted_by_total_ram_desc():
    nodes, _ = build_resource_tree(_items())
    assert nodes[0].label.startswith("Image")  # images dominate RAM
    assert nodes[1].label.startswith("Mesh")


def test_children_sorted_biggest_first_and_have_refs():
    nodes, _ = build_resource_tree(_items())
    image_node = nodes[0]
    assert [c.label for c in image_node.children] == ["big  (2u)", "small  (1u)"]
    assert image_node.children[0].ref == {"type": "Image", "name": "big"}
    assert image_node.children[0].ram and image_node.children[0].vram
    assert image_node.children[0].disk  # 'big' has disk usage; 'Cube' (a mesh) has none


def test_disk_column_empty_when_zero():
    nodes, _ = build_resource_tree(_items())
    mesh_node = next(n for n in nodes if n.label.startswith("Mesh"))
    assert mesh_node.disk == ""
    assert mesh_node.children[0].disk == ""


def test_sort_by_vram_reorders_type_groups():
    items = [
        {"type": "Mesh", "name": "HeavyVram", "ram": 1, "vram": 50_000_000, "disk": 0, "users": 1},
        {"type": "Image", "name": "LightVram", "ram": 16_000_000, "vram": 1, "disk": 0, "users": 1},
    ]
    nodes, _ = build_resource_tree(items, sort_by="ram")
    assert nodes[0].label.startswith("Image")
    nodes, _ = build_resource_tree(items, sort_by="vram")
    assert nodes[0].label.startswith("Mesh")


def test_unknown_sort_by_falls_back_to_ram():
    nodes_default, _ = build_resource_tree(_items())
    nodes_bad, _ = build_resource_tree(_items(), sort_by="nonsense")
    assert [n.key for n in nodes_default] == [n.key for n in nodes_bad]


def test_each_datablock_counted_once():
    # 'big' image has 2 users but appears exactly once (no double counting).
    nodes, _ = build_resource_tree(_items())
    rows = flatten_visible(nodes, expanded={"type:Image"})
    big_rows = [r for r in rows if r.label.startswith("big")]
    assert len(big_rows) == 1


def test_tree_json_roundtrip_preserves_columns_and_ref():
    nodes, _ = build_resource_tree(_items())
    back = nodes_from_json(nodes_to_json(nodes))
    assert back[0].label == nodes[0].label
    assert back[0].ram == nodes[0].ram
    assert back[0].vram == nodes[0].vram
    assert back[0].disk == nodes[0].disk
    assert back[0].children[0].ref == nodes[0].children[0].ref
