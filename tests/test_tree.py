"""Unit tests for core.tree + Report JSON round-trip."""

from core.report import Finding, Report
from core.tree import all_keys, flatten_visible, report_to_tree, top_level_keys


def _report():
    r = Report(title="Orphans", feature="F4")
    r.add(Finding("orphan", "2 orphaned datablocks", severity="warning",
                  items=["Material/Wood", "Mesh/Cube"]))
    r.add(Finding("identical", "2 identical", severity="warning", items=["Material/A", "Material/B"]))
    r.add(Finding("summary", "scan done", severity="info"))
    return r


def test_report_json_roundtrip():
    r = _report()
    back = Report.from_json(r.to_json())
    assert back.to_dict() == r.to_dict()


def test_report_to_tree_structure():
    tree = report_to_tree(_report())
    # Summary hoisted to the top, then categories in first-seen order.
    assert [n.label for n in tree] == ["Summary", "Orphans", "Identical datablocks"]
    # category severity rolls up from its findings
    assert tree[0].severity == "info"  # summary
    assert tree[1].severity == "warning"  # orphans
    # finding -> item leaves
    orphan_finding = tree[1].children[0]
    assert [c.label for c in orphan_finding.children] == ["Material/Wood", "Mesh/Cube"]


def test_item_ref_parsing():
    tree = report_to_tree(_report())
    leaf = tree[1].children[0].children[0]  # Material/Wood (tree[0] is Summary)
    assert leaf.ref == {"type": "Material", "name": "Wood"}


def test_file_path_item_is_not_a_ref():
    r = Report(title="x", feature="F1")
    r.add(Finding("broken_link", "missing", severity="error",
                  items=["C:/proj/scene.blend"]))
    leaf = report_to_tree(r)[0].children[0].children[0]
    assert leaf.ref is None  # file paths must not be treated as Type/Name


def test_flatten_collapsed_shows_only_roots():
    tree = report_to_tree(_report())
    rows = flatten_visible(tree, expanded=set())
    assert all(r.indent == 0 for r in rows)
    assert len(rows) == 3
    # every category wraps at least one finding, so all roots have children
    assert all(r.has_children for r in rows)


def test_flatten_expand_category_then_finding():
    tree = report_to_tree(_report())
    cat_key = tree[1].key  # Orphans (tree[0] is Summary)
    rows = flatten_visible(tree, expanded={cat_key})
    labels = [r.label for r in rows]
    assert "2 orphaned datablocks" in labels  # finding now visible
    assert "Material/Wood" not in labels  # but items still hidden

    finding_key = tree[1].children[0].key
    rows2 = flatten_visible(tree, expanded={cat_key, finding_key})
    labels2 = [(r.indent, r.label) for r in rows2]
    assert (2, "Material/Wood") in labels2  # items at indent 2


def test_top_level_keys():
    tree = report_to_tree(_report())
    assert top_level_keys(tree) == [n.key for n in tree]


def test_category_detail_is_finding_count():
    r = Report(title="x", feature="F1")
    r.add(Finding("orphan", "a"))
    r.add(Finding("orphan", "b"))
    r.add(Finding("summary", "done", severity="info"))
    tree = report_to_tree(r)
    assert tree[0].detail == "1"  # summary finding, hoisted to the top
    assert tree[1].detail == "2"  # two orphan findings


def test_category_detail_override_and_finding_detail():
    r = Report(title="Materials", feature="F3")
    r.category_details["duplicate_material"] = "3 (2 Local & 1 Linked)"
    r.add(Finding("duplicate_material", "Local", severity="warning",
                  detail="2", items=["Material/A", "Material/B"]))
    r.add(Finding("duplicate_material", "Linked", severity="info",
                  detail="1", items=["Material/C"]))
    cat = report_to_tree(r)[0]
    assert cat.detail == "3 (2 Local & 1 Linked)"   # override, not the finding count (2)
    assert [(c.label, c.detail) for c in cat.children] == [("Local", "2"), ("Linked", "1")]


def test_all_keys_covers_every_node():
    tree = report_to_tree(_report())
    keys = all_keys(tree)
    # every row from a fully-expanded flatten is present in all_keys
    rows = flatten_visible(tree, keys)
    assert {r.key for r in rows} == keys
    # includes nested item leaves, not just roots
    assert len(keys) > len(top_level_keys(tree))
