"""Unit tests for F7 Phase 1: core.depscan (recursive scan + issue classifier).

Two layers: the real linkproj fixture exercised through the recursive walk, and a
stubbed ``scan_file`` returning crafted LinkRefs so every classifier is checked
deterministically without large real files.
"""

import pathlib

import pytest

from core import depscan
from core.blendscan import LinkRef
from core.depscan import (
    ABSOLUTE, DRIVE_REMAP, DUPLICATE_REF, INCONSISTENT_PATH, MISSING, MIXED_SLASH,
)

LINKPROJ = pathlib.Path(__file__).resolve().parent / "fixtures" / "linkproj"


# --- intrinsic per-link classifier -----------------------------------------

def test_has_backslash():
    assert depscan.has_backslash("//..\\libA.blend") is True
    assert depscan.has_backslash("//libA.blend") is False


def test_link_issues_missing_beats_absolute():
    ref = LinkRef("D:/x.blend", "D:/x.blend", is_relative=False, exists=False)
    assert depscan.link_issues(ref) == {MISSING}  # missing takes precedence


def test_link_issues_absolute_and_mixed():
    ref = LinkRef("C:/a\\b.blend", "C:/a/b.blend", is_relative=False, exists=True)
    assert depscan.link_issues(ref) == {ABSOLUTE, MIXED_SLASH}


def test_link_issues_clean():
    ref = LinkRef("//b.blend", "C:/proj/b.blend", is_relative=True, exists=True)
    assert depscan.link_issues(ref) == set()


# --- crafted recursive scan via a stub -------------------------------------

def _stub(mapping):
    def scan_file(path):
        return mapping.get(depscan._key(str(pathlib.Path(path).resolve())), [])
    return scan_file


def _R(stored, resolved, rel, exists):
    return LinkRef(stored, resolved, is_relative=rel, exists=exists)


@pytest.fixture
def crafted():
    mapping = {
        depscan._key("C:/proj/scene.blend"): [
            _R("//libA.blend", "C:/proj/libA.blend", True, True),       # clean
            _R("C:/proj/libA.blend", "C:/proj/libA.blend", False, True),  # abs+dup+inconsistent
            _R("D:/old/human.blend", "D:/old/human.blend", False, False),  # missing+remap
        ],
        depscan._key("C:/proj/libA.blend"): [
            _R("//human.blend", "C:/proj/human.blend", True, True),     # existing remap target
            _R("//..\\scene.blend", "C:/proj/scene.blend", True, True),  # backslash + cycle
        ],
        depscan._key("C:/proj/human.blend"): [],  # leaf
    }
    return depscan.scan_recursive([pathlib.Path("C:/proj/scene.blend")],
                                  scan_file=_stub(mapping))


def test_recursion_visits_all_and_stops_on_cycle(crafted):
    names = {pathlib.Path(k).name for k in crafted.order}
    assert names == {"scene.blend", "libA.blend", "human.blend"}
    assert not crafted.errors


def _base(p):
    return pathlib.Path(p).name.lower()


def test_duplicate_refs(crafted):
    dups = depscan.duplicate_refs(crafted)
    scene = [k for k in dups if _base(k) == "scene.blend"][0]
    target, forms = next(iter(dups[scene].items()))
    assert _base(target) == "liba.blend"
    assert set(forms) == {"//libA.blend", "C:/proj/libA.blend"}


def test_inconsistent_paths(crafted):
    inc = depscan.inconsistent_paths(crafted)
    libA = [k for k in inc if _base(k) == "liba.blend"][0]
    assert set(inc[libA]) == {"//libA.blend", "C:/proj/libA.blend"}
    # the single-form targets are not flagged
    assert not any(_base(k) == "human.blend" for k in inc)


def test_drive_remap_candidates(crafted):
    cands = depscan.drive_remap_candidates(crafted)
    assert len(cands) == 1
    stored, match = cands[0]
    assert stored == "D:/old/human.blend"
    assert match.lower().endswith("human.blend")


def test_library_link_counts(crafted):
    counts = depscan.library_link_counts(crafted)
    top = counts[0]
    assert pathlib.Path(top[0]).name == "libA.blend"
    assert top[1] == 2  # linked twice from scene


def test_cycles_detected(crafted):
    cycles = crafted.graph.find_cycles()
    assert any(
        {pathlib.Path(n).name for n in c} >= {"scene.blend", "libA.blend"}
        for c in cycles
    )


def test_build_dependency_tree_structure(crafted):
    nodes = depscan.build_dependency_tree(crafted)
    keys = [n.key for n in nodes]
    assert keys[0] == "f7:summary"  # summary on top
    assert keys[1] == "f7:filemap"
    # then one node per non-empty severity tier
    assert "f7tier:will_break" in keys  # crafted has a missing link + a cycle
    assert all(k.startswith(("f7:summary", "f7:filemap", "f7tier:")) for k in keys)


def test_dependency_tree_file_map(crafted):
    nodes = depscan.build_dependency_tree(crafted)
    filemap = next(n for n in nodes if n.key == "f7:filemap")
    assert len(filemap.children) == 1  # one root (scene)
    scene = filemap.children[0]
    assert _base(scene.label.split()[0]) == "scene.blend"
    assert len(scene.children) == 3  # scene's three refs (libA, libA-abs, missing human)
    # a missing link is marked
    assert any("missing" in c.label for c in scene.children)


def test_dependency_tree_file_map_icons(crafted):
    """File Map nodes (#6) carry a per-node icon: a clean in-tree relative link
    is "FILE_BLEND", a link resolved via an absolute path reads as "external"
    (FILE_FOLDER), and a missing link reads as broken — missing wins over
    absolute, same precedence as ``link_issues``."""
    nodes = depscan.build_dependency_tree(crafted)
    filemap = next(n for n in nodes if n.key == "f7:filemap")
    assert filemap.icon == "FILE_FOLDER"
    scene = filemap.children[0]
    assert scene.icon == depscan.ICON_BLEND  # root file, no ref yet

    clean = next(c for c in scene.children if "[" not in c.label)
    assert clean.icon == depscan.ICON_BLEND
    external = next(c for c in scene.children
                     if "absolute" in c.label and "missing" not in c.label)
    assert external.icon == depscan.ICON_EXTERNAL
    missing = next(c for c in scene.children if "missing" in c.label)
    assert missing.icon == depscan.ICON_MISSING


def test_dependency_tree_circular_node_keeps_blend_icon(crafted):
    nodes = depscan.build_dependency_tree(crafted)
    filemap = next(n for n in nodes if n.key == "f7:filemap")

    def find_circular(node):
        if "↻ circular" in node.label:
            return node
        for c in node.children:
            found = find_circular(c)
            if found:
                return found
        return None

    circ = find_circular(filemap)
    assert circ is not None
    assert circ.icon == depscan.ICON_BLEND


def test_dependency_tree_marks_circular(crafted):
    nodes = depscan.build_dependency_tree(crafted)

    def labels(node):
        out = [node.label]
        for c in node.children:
            out += labels(c)
        return out

    all_labels = [l for n in nodes for l in labels(n)]
    assert any("↻ circular" in l for l in all_labels)


def test_dependency_tree_severity_tiers(crafted):
    nodes = depscan.build_dependency_tree(crafted)
    tiers = {n.key: n for n in nodes if n.key.startswith("f7tier:")}
    # crafted: cycle + missing -> will_break; inconsistent/dup/remap -> may_break;
    # absolute/backslash -> portability; most_linked -> info
    assert {"f7tier:will_break", "f7tier:may_break", "f7tier:portability",
            "f7tier:info"} <= set(tiers)
    assert all(t.detail.isdigit() and int(t.detail) >= 1 for t in tiers.values())
    # will_break holds circular + missing categories
    wb_cats = {c.label for c in tiers["f7tier:will_break"].children}
    assert any("Circular" in c for c in wb_cats)
    assert any("Missing" in c for c in wb_cats)


def test_report_to_tree_summary_first():
    from core.report import Finding, Report
    from core.tree import report_to_tree
    r = Report(title="t", feature="x")
    r.add(Finding(category="absolute_path", message="a"))
    r.add(Finding(category="summary", message="s"))
    tree = report_to_tree(r)
    assert tree[0].label == "Summary"  # summary hoisted to the top


def test_build_dep_report_categories(crafted):
    report = depscan.build_dep_report(crafted)
    cats = {f.category for f in report.findings}
    assert {MISSING, ABSOLUTE, MIXED_SLASH, DUPLICATE_REF, INCONSISTENT_PATH,
            DRIVE_REMAP, "circular_link", "summary"} <= cats
    assert report.feature == "F7"
    assert sum(1 for f in report.findings if f.category == MISSING) == 1


def test_steps_yield_progress_and_status():
    mapping = {depscan._key("C:/proj/a.blend"): []}
    result = depscan.new_dep_scan()
    steps = list(depscan.scan_recursive_steps(
        result, [pathlib.Path("C:/proj/a.blend")], scan_file=_stub(mapping)))
    assert steps[0][1].startswith("Scanning")
    fracs = [f for f, _ in steps]
    assert fracs[-1] == pytest.approx(1.0)
    assert all(0.0 <= f <= 1.0 for f in fracs)


# --- real fixture (scene -> libA -> libB) ----------------------------------

pytestmark = pytest.mark.skipif(
    not (LINKPROJ / "scene.blend").is_file(),
    reason="linkproj fixtures not built",
)


def test_recursive_scan_real_fixture_transitive():
    scan = depscan.scan_recursive([LINKPROJ / "scene.blend"])
    names = {pathlib.Path(k).name for k in scan.graph.nodes}
    assert names == {"scene.blend", "libA.blend", "libB.blend"}
    assert not scan.errors


def test_real_fixture_captures_sizes_in_file_map():
    scan = depscan.scan_recursive([LINKPROJ / "scene.blend"])
    assert all(n in scan.sizes and scan.sizes[n] > 0 for n in scan.order)
    nodes = depscan.build_dependency_tree(scan)
    filemap = next(n for n in nodes if n.key == "f7:filemap")
    root = filemap.children[0]
    assert root.detail.endswith(("B", "KB", "MB", "GB"))  # size shown on the file


def test_real_fixture_report_is_clean():
    scan = depscan.scan_recursive([LINKPROJ / "scene.blend"])
    report = depscan.build_dep_report(scan)
    cats = {f.category for f in report.findings}
    assert MISSING not in cats
    assert "circular_link" not in cats
    assert ABSOLUTE not in cats
