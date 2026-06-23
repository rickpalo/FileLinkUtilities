"""Unit tests for Batch 3: core.reversedep (reverse-dependency 'safe to delete?')."""

from core import reversedep


# A small project:  scene -> chars -> body ;  promo -> chars ;  lonely (no links)
NODES = {"/p/scene.blend", "/p/chars.blend", "/p/body.blend", "/p/promo.blend",
         "/p/lonely.blend"}
EDGES = [("/p/scene.blend", "/p/chars.blend"),
         ("/p/chars.blend", "/p/body.blend"),
         ("/p/promo.blend", "/p/chars.blend")]


def test_direct_and_indirect_dependents():
    direct, indirect, canon = reversedep.dependents(EDGES, NODES, "/p/chars.blend")
    assert canon == "/p/chars.blend"
    assert direct == ["/p/promo.blend", "/p/scene.blend"]   # link chars directly
    assert indirect == []                                   # nothing else above them


def test_transitive_dependents_of_leaf():
    direct, indirect, _ = reversedep.dependents(EDGES, NODES, "/p/body.blend")
    assert direct == ["/p/chars.blend"]                     # chars links body directly
    assert indirect == ["/p/promo.blend", "/p/scene.blend"]  # reach body via chars


def test_no_dependents_is_safe():
    direct, indirect, canon = reversedep.dependents(EDGES, NODES, "/p/scene.blend")
    assert canon == "/p/scene.blend"
    assert direct == [] and indirect == []


def test_target_not_scanned_returns_none():
    direct, indirect, canon = reversedep.dependents(EDGES, NODES, "/p/elsewhere.blend")
    assert canon is None and direct == [] and indirect == []


def test_case_and_separator_insensitive_match():
    _d, _i, canon = reversedep.dependents(EDGES, NODES, r"\P\CHARS.BLEND")
    assert canon == "/p/chars.blend"


def test_cycle_does_not_hang():
    nodes = {"a", "b"}
    edges = [("a", "b"), ("b", "a")]
    direct, indirect, canon = reversedep.dependents(edges, nodes, "a")
    assert canon == "a"
    assert direct == ["b"] and indirect == []  # b links a directly; not double-counted


def test_report_safe_when_no_dependents():
    report = reversedep.build_reverse_dep_report("/p/scene.blend", [], [], found=True,
                                                 scanned=5)
    assert report.feature == "f7rev"
    assert [f.category for f in report.findings] == ["clean"]
    assert report.findings[0].message.startswith("✓")


def test_report_not_found_warns():
    report = reversedep.build_reverse_dep_report("/p/x.blend", [], [], found=False,
                                                 scanned=3)
    assert report.findings[0].category == "clean"
    assert report.findings[0].severity == "warning"


def test_report_lists_dependents_and_summary():
    report = reversedep.build_reverse_dep_report(
        "/p/body.blend", ["/p/chars.blend"], ["/p/scene.blend"], found=True, scanned=5)
    cats = [f.category for f in report.findings]
    assert cats == ["direct_dependent", "indirect_dependent", "summary"]
    assert report.findings[0].message == "chars.blend"
    assert report.findings[-1].data == {"direct": 1, "indirect": 1}
    assert report.max_severity == "error"
