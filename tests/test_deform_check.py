"""Tests for core.deform_check (armature-deformation vertex-explosion detection)."""
from core.deform_check import (
    DeformIssue,
    ObjectDeformSummary,
    build_deform_check_report,
    find_deform_outliers,
)


def test_no_edges_no_issues():
    assert find_deform_outliers([], [], []) == []


def test_all_edges_below_threshold_no_issues():
    edges = [(0, 1), (1, 2), (2, 0)]
    rest = [0.01, 0.01, 0.012]
    deformed = [0.011, 0.009, 0.013]  # ~1x ratios, a perfectly healthy mesh
    assert find_deform_outliers(edges, rest, deformed) == []


def test_single_exploded_edge_flags_both_endpoints():
    edges = [(0, 1)]
    rest = [0.001]
    deformed = [50.0]  # ratio 50,000x -- unambiguous
    issues = find_deform_outliers(edges, rest, deformed)
    assert {i.vertex_id for i in issues} == {0, 1}
    assert issues[0].ratio == 50000.0


def test_threshold_is_respected():
    edges = [(0, 1)]
    rest = [1.0]
    deformed = [10.0]  # ratio 10x
    assert find_deform_outliers(edges, rest, deformed, ratio_threshold=20.0) == []
    assert find_deform_outliers(edges, rest, deformed, ratio_threshold=5.0) != []


def test_zero_rest_length_edge_is_skipped_not_a_divide_by_zero():
    edges = [(0, 1)]
    rest = [0.0]
    deformed = [5.0]
    assert find_deform_outliers(edges, rest, deformed) == []


def test_vertex_keeps_its_single_worst_edge():
    """v1 touches two flagged edges -- the report should keep the WORSE one,
    not the first one encountered or an average."""
    edges = [(0, 1), (1, 2)]
    rest = [0.001, 0.001]
    deformed = [30.0, 90.0]  # ratios 30,000x and 90,000x
    issues = find_deform_outliers(edges, rest, deformed)
    v1_issue = next(i for i in issues if i.vertex_id == 1)
    assert v1_issue.ratio == 90000.0


def test_results_sorted_worst_first():
    edges = [(0, 1), (2, 3), (4, 5)]
    rest = [0.001, 0.001, 0.001]
    deformed = [10.0, 90.0, 50.0]
    issues = find_deform_outliers(edges, rest, deformed)
    ratios = [i.ratio for i in issues]
    assert ratios == sorted(ratios, reverse=True)


def test_healthy_mesh_with_normal_variance_not_flagged():
    """Mirrors the real shirt.003 data shape: most edges have a ratio close to
    1.0 (with ordinary variance up to a few x), only a tiny minority explode."""
    edges = [(i, i + 1) for i in range(20)]
    rest = [0.007 + 0.001 * (i % 3) for i in range(20)]
    deformed = [r * (1.0 + 0.3 * (i % 4)) for i, r in enumerate(rest)]  # up to ~1.9x
    assert find_deform_outliers(edges, rest, deformed) == []


# --- ObjectDeformSummary ---

def test_object_summary_worst_ratio_and_count():
    issues = (DeformIssue(1, 500.0, 0.001, 0.5), DeformIssue(2, 200.0, 0.001, 0.2))
    s = ObjectDeformSummary("shirt.003", "Circle.058", "CC3_Base_Plus_Rigify.026", issues)
    assert s.worst_ratio == 500.0
    assert s.count == 2


def test_object_summary_empty_issues():
    s = ObjectDeformSummary("clean_obj", "Mesh", "Armature", ())
    assert s.worst_ratio == 0.0
    assert s.count == 0


# --- build_deform_check_report ---

def test_report_empty_summaries_is_clean():
    report = build_deform_check_report([])
    assert len(report.findings) == 1
    assert report.findings[0].category == "clean"


def test_report_one_finding_per_object_worst_first():
    a = ObjectDeformSummary("obj_a", "mesh_a", "arm", (DeformIssue(1, 100.0, 0.001, 0.1),))
    b = ObjectDeformSummary("obj_b", "mesh_b", "arm", (DeformIssue(2, 9000.0, 0.001, 9.0),))
    report = build_deform_check_report([a, b])
    assert len(report.findings) == 2
    assert report.findings[0].message.startswith("obj_b")  # worse ratio listed first
    assert report.findings[0].severity == "warning"
    assert "Object/obj_b" in report.findings[0].items


def test_report_detail_shows_rounded_ratio():
    s = ObjectDeformSummary("obj", "mesh", "arm", (DeformIssue(1, 84324.63, 0.00092, 77.43),))
    report = build_deform_check_report([s])
    assert report.findings[0].detail == "84325x"


# --- is_locally_fixable (linked-character scope, 2026-07-09) ---

def test_summary_defaults_to_locally_fixable():
    s = ObjectDeformSummary("obj", "mesh", "arm", (DeformIssue(1, 100.0, 0.001, 0.1),))
    assert s.is_locally_fixable is True


def test_linked_object_flagged_in_report_message():
    s = ObjectDeformSummary("obj", "mesh", "arm", (DeformIssue(1, 100.0, 0.001, 0.1),),
                           is_locally_fixable=False)
    report = build_deform_check_report([s])
    assert "LINKED, fix at source" in report.findings[0].message


def test_local_object_report_message_has_no_linked_tag():
    s = ObjectDeformSummary("obj", "mesh", "arm", (DeformIssue(1, 100.0, 0.001, 0.1),))
    report = build_deform_check_report([s])
    assert "LINKED" not in report.findings[0].message
