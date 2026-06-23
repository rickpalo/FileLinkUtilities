"""Unit tests for Batch 3: core.missingdata (missing data-block report)."""

from core import missingdata
from core.missingdata import MissingBlock


def _b(kind, name, library=""):
    return MissingBlock(kind=kind, name=name, library=library)


def test_group_by_library_clusters():
    blocks = [_b("Object", "Tree", "//libA.blend"),
              _b("Material", "Bark", "//libA.blend"),
              _b("Image", "Leaf", "//libB.blend")]
    groups = missingdata.group_by_library(blocks)
    assert set(groups) == {"//libA.blend", "//libB.blend"}
    assert {m.name for m in groups["//libA.blend"]} == {"Tree", "Bark"}


def test_report_clean_when_none():
    report = missingdata.build_missing_datablocks_report([])
    assert report.feature == "f7miss"
    assert [f.category for f in report.findings] == ["clean"]
    assert report.max_severity == "info"


def test_report_groups_by_library_and_summarizes():
    blocks = [_b("Object", "Tree", "//libA.blend"),
              _b("Material", "Bark", "//libA.blend"),
              _b("Image", "Leaf", "//libB.blend")]
    report = missingdata.build_missing_datablocks_report(blocks, "scene.blend")
    cats = [f.category for f in report.findings]
    # Headline overview first, then the two library groups (most-missing first).
    assert cats == ["overview", "missing_datablock", "missing_datablock"]
    assert report.findings[0].message == "2 file(s) with 3 missing data-block(s)"
    assert report.findings[0].data == {"missing": 3, "libraries": 2}
    assert report.findings[1].message.startswith("//libA.blend")  # 2 beats 1
    assert report.findings[1].detail == "2"
    assert report.findings[1].items == ["Material: Bark", "Object: Tree"]
    assert report.max_severity == "error"


def test_report_unknown_library_labeled():
    report = missingdata.build_missing_datablocks_report([_b("Mesh", "Body", "")])
    # findings[0] is the overview headline; the library group follows.
    assert report.findings[1].message.startswith("(unknown library)")
