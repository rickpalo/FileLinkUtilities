"""Unit tests for core.geometry_dedup."""

from core.geometry_dedup import build_instance_plan, choose_canonical, removable_count


def _it(id_, fp, users=1, linked=False, kind="Mesh"):
    return {"id": id_, "name": id_, "kind": kind, "fingerprint": fp,
            "linked": linked, "users": users}


def test_canonical_keeps_most_used_local():
    members = [_it("A", "H", users=1), _it("B", "H", users=3)]
    assert choose_canonical(members)["id"] == "B"


def test_canonical_prefers_local_over_linked():
    members = [_it("Lib", "H", users=9, linked=True), _it("Local", "H", users=1)]
    assert choose_canonical(members)["id"] == "Local"


def test_canonical_prefers_linked_when_requested():
    # docs/TODO.md #21, 2026-06-27: an explicit preference can flip the tie-break.
    members = [_it("Lib", "H", users=9, linked=True), _it("Local", "H", users=1)]
    assert choose_canonical(members, prefer_linked=True)["id"] == "Lib"


def test_plan_groups_identical_meshes():
    items = [_it("Cube", "H", users=1), _it("Cube.001", "H", users=1), _it("Sphere", "S")]
    report, plan = build_instance_plan(items)
    assert len(plan) == 1
    g = plan[0]
    assert g["canonical"] in {"Cube", "Cube.001"}
    assert len(g["victims"]) == 1
    summary = next(f for f in report.findings if f.category == "summary")
    assert summary.data == {"groups": 1, "freed": 1}


def test_local_and_linked_cluster_but_linked_never_removed():
    # docs/TODO.md #21, 2026-06-27: linked meshes are now real candidates (a
    # local mesh's users can be repointed onto an already-linked-in copy,
    # reducing footprint) -- but the linked datablock itself is tracked
    # separately and never counted as removable.
    items = [_it("Local", "H"), _it("FromLib", "H", linked=True)]
    report, plan = build_instance_plan(items)
    assert len(plan) == 1
    assert plan[0]["canonical"] == "Local"  # local preferred by default
    assert plan[0]["victims"] == ["FromLib"]
    assert plan[0]["linked_victims"] == ["FromLib"]
    assert removable_count(plan) == 0  # nothing local actually freed
    summary = next(f for f in report.findings if f.category == "summary")
    assert summary.data == {"groups": 1, "freed": 0}


def test_prefer_linked_repoints_onto_library_copy():
    items = [_it("Local", "H"), _it("FromLib", "H", linked=True)]
    _report, plan = build_instance_plan(items, prefer_linked=True)
    assert plan[0]["canonical"] == "FromLib"
    assert plan[0]["victims"] == ["Local"]
    assert plan[0]["linked_victims"] == []
    assert removable_count(plan) == 1  # the local copy is now removable


def test_no_fingerprint_excluded():
    items = [_it("A", None), _it("B", None)]
    _, plan = build_instance_plan(items)
    assert plan == []


def test_different_kinds_do_not_merge():
    items = [_it("M", "H", kind="Mesh"), _it("C", "H", kind="Curve")]
    _, plan = build_instance_plan(items)
    assert plan == []


def test_removable_count():
    """Group 11 #44, 2026-06-26: drives the selective-apply UI's headline."""
    plan = [{"kind": "Mesh", "canonical": "A", "victims": ["B", "C"]},
            {"kind": "Mesh", "canonical": "D", "victims": ["E"]}]
    assert removable_count(plan) == 3


def test_removable_count_empty_plan():
    assert removable_count([]) == 0
