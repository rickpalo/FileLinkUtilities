"""Unit tests for core.f2_makelocal (bpy-free)."""

from core.f2_makelocal import build_makelocal_report, find_rename_collisions


def _it(type_, name, library, indirect=False):
    return {"type": type_, "name": name, "library": library, "indirect": indirect}


def _n(type_, name, library=""):
    return {"type": type_, "name": name, "library": library}


def test_empty_is_info_summary():
    report = build_makelocal_report([])
    summary = next(f for f in report.findings if f.category == "summary")
    assert summary.severity == "info"
    assert summary.data == {"linked": 0, "libraries": 0, "indirect": 0, "collisions": 0}


def test_groups_by_library_and_counts_indirect():
    items = [
        _it("Object", "Tree", "//libA.blend"),
        _it("Mesh", "TreeMesh", "//libA.blend"),
        _it("Object", "Rock", "//libB.blend", indirect=True),
    ]
    report = build_makelocal_report(items)
    libs = [f for f in report.findings if f.category == "linked_library"]
    assert len(libs) == 2
    summary = next(f for f in report.findings if f.category == "summary")
    assert summary.data == {"linked": 3, "libraries": 2, "indirect": 1, "collisions": 0}
    assert summary.severity == "warning"  # there is linked data to act on


def test_library_finding_lists_members():
    items = [_it("Object", "Tree", "//libA.blend"), _it("Material", "Bark", "//libA.blend")]
    report = build_makelocal_report(items)
    f = next(f for f in report.findings if f.category == "linked_library")
    assert set(f.items) == {"Object/Tree", "Material/Bark"}
    assert f.data["library"] == "//libA.blend"


def test_no_collision_when_each_name_unique():
    names = [_n("Object", "Tree", "//libA.blend"), _n("Object", "Rock", "//libB.blend")]
    assert find_rename_collisions(names) == []


def test_collision_between_local_and_linked():
    names = [_n("Object", "Character"), _n("Object", "Character", "//libA.blend")]
    collisions = find_rename_collisions(names)
    assert len(collisions) == 1
    assert collisions[0]["type"] == "Object"
    assert collisions[0]["name"] == "Character"
    assert collisions[0]["members"] == ["//libA.blend", "local"]


def test_collision_between_two_different_libraries_no_local():
    names = [_n("Object", "Tree", "//libA.blend"), _n("Object", "Tree", "//libB.blend")]
    collisions = find_rename_collisions(names)
    assert len(collisions) == 1
    assert collisions[0]["members"] == ["//libA.blend", "//libB.blend"]


def test_collision_ignores_different_types_with_same_name():
    names = [_n("Object", "Shared", "//libA.blend"), _n("Material", "Shared", "//libB.blend")]
    assert find_rename_collisions(names) == []


def test_build_report_includes_collisions():
    items = [_it("Object", "Character", "//libA.blend")]
    all_names = [_n("Object", "Character"), _n("Object", "Character", "//libA.blend")]
    report = build_makelocal_report(items, all_names)
    risks = [f for f in report.findings if f.category == "rename_risk"]
    assert len(risks) == 1
    assert "Character" in risks[0].message
    summary = next(f for f in report.findings if f.category == "summary")
    assert summary.data["collisions"] == 1
    assert "collision" in summary.message
