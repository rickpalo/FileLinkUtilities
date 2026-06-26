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
    # File map (root + link hierarchy collapsed into one headline row, item 4,
    # 2026-06-25) is on top -- the separate flat "Summary" row is gone, folded
    # into that same headline (item e's redundancy rule).
    assert keys[0] == "f7:filemap"
    # then one node per non-empty severity tier
    assert "f7tier:will_break" in keys  # crafted has a missing link + a cycle
    assert all(k.startswith(("f7:filemap", "f7tier:")) for k in keys)


def test_dependency_tree_file_map(crafted):
    """The File map row IS the root file now (item 4: a wrapper holding
    exactly one child collapses into that child) -- its label carries the
    root name + a library count/size rollup, and its children are directly
    the root's own links (no intermediate "scene" wrapper node anymore)."""
    nodes = depscan.build_dependency_tree(crafted)
    filemap = next(n for n in nodes if n.key == "f7:filemap")
    assert filemap.label.startswith("scene")  # ".blend" dropped from display (item 5b)
    assert "File map" in filemap.label
    assert "2 libraries" in filemap.label  # libA + human, scene itself excluded
    assert len(filemap.children) == 3  # scene's three refs (libA, libA-abs, missing human)
    # a missing link is marked
    assert any("missing" in c.label for c in filemap.children)


def test_dependency_tree_error_items_are_selectable_library_refs(crafted):
    """Item 5a, 2026-06-25: clicking a library named in an Errors category
    should reveal it in the Outliner -- the item leaf needs a "Library" ref
    (resolution needs the real filename WITH its extension, even though the
    displayed label drops it per item 5b)."""
    nodes = depscan.build_dependency_tree(crafted)
    missing_tier = next(n for n in nodes if n.key == "f7tier:will_break")
    missing_cat = next(c for c in missing_tier.children if c.key == "f7err:missing_link")
    finding = missing_cat.children[0]
    item = next(c for c in finding.children if c.label == "human")
    assert item.ref == {"type": "Library", "name": "human.blend"}  # extension kept for resolution


def test_dependency_tree_file_map_icons(crafted):
    """File Map nodes (#6) carry a per-node icon: a clean in-tree relative link
    is "FILE_BLEND", a link resolved via an absolute path reads as "external"
    (FILE_FOLDER), and a missing link reads as broken — missing wins over
    absolute, same precedence as ``link_issues``. The merged headline row
    itself (item 4) always shows the Blender icon, not a folder (item 4b —
    the folder icon was never about asset libraries, it marks an absolute/
    external link, which never applies to the root file itself)."""
    nodes = depscan.build_dependency_tree(crafted)
    filemap = next(n for n in nodes if n.key == "f7:filemap")
    assert filemap.icon == depscan.ICON_BLEND  # the root file's own icon, no ref yet

    clean = next(c for c in filemap.children if "[" not in c.label)
    assert clean.icon == depscan.ICON_BLEND
    external = next(c for c in filemap.children
                     if "absolute" in c.label and "missing" not in c.label)
    assert external.icon == depscan.ICON_EXTERNAL
    missing = next(c for c in filemap.children if "missing" in c.label)
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


def test_inconsistent_path_finding_items_list_every_form(crafted):
    """Item 6, 2026-06-25: "I open the first example and only see one form" --
    ``items`` used to be just [target], so the tree never showed the OTHER
    stored form(s) the message text already named."""
    report = depscan.build_dep_report(crafted)
    finding = next(f for f in report.findings if f.category == INCONSISTENT_PATH)
    assert set(finding.items) == set(finding.data["forms"])
    assert len(finding.items) >= 2


def test_duplicate_ref_finding_items_list_every_form(crafted):
    report = depscan.build_dep_report(crafted)
    finding = next(f for f in report.findings if f.category == DUPLICATE_REF)
    assert set(finding.data["forms"]) <= set(finding.items)


def test_steps_yield_progress_and_status():
    mapping = {depscan._key("C:/proj/a.blend"): []}
    result = depscan.new_dep_scan()
    steps = list(depscan.scan_recursive_steps(
        result, [pathlib.Path("C:/proj/a.blend")], scan_file=_stub(mapping)))
    assert steps[0][1].startswith("Scanning")
    fracs = [f for f, _ in steps]
    assert fracs[-1] == pytest.approx(1.0)
    assert all(0.0 <= f <= 1.0 for f in fracs)


# --- depth/provenance (consolidated TODO Group 1, item 1) -------------------

@pytest.fixture
def chain():
    """scene -> libA -> libB, three real hops, libB has its own missing link."""
    mapping = {
        depscan._key("C:/proj/scene.blend"): [
            _R("//libA.blend", "C:/proj/libA.blend", True, True),
        ],
        depscan._key("C:/proj/libA.blend"): [
            _R("//libB.blend", "C:/proj/libB.blend", True, True),
        ],
        depscan._key("C:/proj/libB.blend"): [
            _R("//gone.blend", "C:/proj/gone.blend", True, False),
        ],
    }
    return depscan.scan_recursive([pathlib.Path("C:/proj/scene.blend")],
                                  scan_file=_stub(mapping))


def test_depths_and_parents_recorded(chain):
    scene = next(k for k in chain.order if _base(k) == "scene.blend")
    libA = next(k for k in chain.order if _base(k) == "liba.blend")
    libB = next(k for k in chain.order if _base(k) == "libb.blend")
    assert chain.depths[scene] == 0
    assert chain.depths[libA] == 1
    assert chain.depths[libB] == 2
    assert chain.parents[libA] == scene
    assert chain.parents[libB] == libA
    assert scene not in chain.parents  # roots have no parent


def test_provenance_direct_vs_indirect(chain):
    scene = next(k for k in chain.order if _base(k) == "scene.blend")
    libA = next(k for k in chain.order if _base(k) == "liba.blend")
    libB = next(k for k in chain.order if _base(k) == "libb.blend")
    assert depscan._provenance(chain, scene) == "direct"
    assert depscan._provenance(chain, libA) == "indirect (1 hop via scene)"
    assert depscan._provenance(chain, libB) == "indirect (2 hops via libA)"


def test_missing_finding_labels_direct_at_root(crafted):
    report = depscan.build_dep_report(crafted)
    finding = next(f for f in report.findings if f.category == MISSING)
    assert "(direct)" in finding.message


def test_missing_finding_labels_indirect_deep_in_chain(chain):
    # A live placeholder for the missing link, so it stays MISSING (not downgraded
    # to stale by item 4's check) -- this test is purely about the depth label.
    report = depscan.build_dep_report(
        chain, linked_datablocks_fn=lambda fkey: {"//gone.blend": [("Object", "y")]})
    finding = next(f for f in report.findings if f.category == MISSING)
    assert "indirect (2 hops via libA)" in finding.message


def test_file_map_direct_row_has_no_popup(chain):
    """A depth-1 row (directly linked by the open/root file) IS a real
    bpy.data.libraries entry -- no on-demand lookup needed for it."""
    nodes = depscan.build_dependency_tree(
        chain, linked_datablocks_fn=lambda fkey: {"//gone.blend": [("Object", "y")]})
    filemap = next(n for n in nodes if n.key == "f7:filemap")
    libA_row = filemap.children[0]
    assert _base(libA_row.label.split("   ")[0]) == "liba"
    assert libA_row.popup is None


def test_file_map_indirect_row_gets_popup(chain):
    """Item 2, 2026-06-26: a depth-2+ row (a library only reachable through
    another library) isn't a real bpy.data.libraries entry on the open file,
    so it carries {"parent","basename"} for a "show what's linked from here"
    popup instead of a click-to-select ref."""
    nodes = depscan.build_dependency_tree(
        chain, linked_datablocks_fn=lambda fkey: {"//gone.blend": [("Object", "y")]})
    filemap = next(n for n in nodes if n.key == "f7:filemap")
    libA_row = filemap.children[0]
    libB_row = libA_row.children[0]
    assert libB_row.popup is not None
    assert _base(libB_row.popup["parent"]) == "liba.blend"
    assert libB_row.popup["basename"].lower() == "libb.blend"


def test_file_map_missing_target_has_no_popup(chain):
    """A missing/never-visited target has no recorded depth at all -- must not
    be mistaken for a real depth-0 root and treated as "direct"/clickable."""
    nodes = depscan.build_dependency_tree(
        chain, linked_datablocks_fn=lambda fkey: {"//gone.blend": [("Object", "y")]})
    filemap = next(n for n in nodes if n.key == "f7:filemap")
    libB_row = filemap.children[0].children[0]
    missing_row = libB_row.children[0]
    assert "missing" in missing_row.label
    assert missing_row.popup is None


def test_circular_finding_labels_provenance(crafted):
    """The 2-cycle in `crafted` is scene <-> libA; scene is the root (depth 0),
    so the loop is reachable directly from the open file."""
    report = depscan.build_dep_report(crafted)
    finding = next(f for f in report.findings if f.category == "circular_link")
    assert "(direct)" in finding.message


# --- stale link-table entries (consolidated TODO Group 1, item 4) -----------

def test_missing_finding_downgraded_when_no_live_placeholder(crafted):
    """If nothing in the linking file's own ID blocks actually references the
    missing library, it's a vestigial LI table entry, not a real break."""
    report = depscan.build_dep_report(crafted, linked_datablocks_fn=lambda fkey: {})
    assert not any(f.category == MISSING for f in report.findings)
    stale = next(f for f in report.findings if f.category == depscan.STALE_LINK)
    assert "stale" in stale.message.lower()
    assert stale.severity == "info"


def test_missing_finding_kept_when_live_placeholder_exists(crafted):
    def fake_linked(fkey):
        return {"D:/old/human.blend": [("Object", "Foo")]}

    report = depscan.build_dep_report(crafted, linked_datablocks_fn=fake_linked)
    assert any(f.category == MISSING for f in report.findings)
    assert not any(f.category == depscan.STALE_LINK for f in report.findings)


def test_stale_check_unreadable_file_does_not_claim_stale(crafted):
    def boom(fkey):
        raise OSError("nope")

    report = depscan.build_dep_report(crafted, linked_datablocks_fn=boom)
    assert any(f.category == MISSING for f in report.findings)
    assert not any(f.category == depscan.STALE_LINK for f in report.findings)


# --- circular reference datablock nesting (consolidated TODO Group 1, item 3)

def test_circular_finding_nests_real_datablocks():
    """Item 3, 2026-06-26: a circular reference used to just repeat the same
    file names again under itself -- this nests the actual (kind, name) pairs
    crossing each direction of the loop, with real click-to-select refs."""
    mapping = {
        depscan._key("C:/proj/a.blend"): [_R("//b.blend", "C:/proj/b.blend", True, True)],
        depscan._key("C:/proj/b.blend"): [_R("//a.blend", "C:/proj/a.blend", True, True)],
    }
    scan = depscan.scan_recursive([pathlib.Path("C:/proj/a.blend")], scan_file=_stub(mapping))

    def fake_datablocks(linker, basename):
        if _base(linker) == "a.blend" and basename.lower() == "b.blend":
            return [("Object", "Tree")]
        if _base(linker) == "b.blend" and basename.lower() == "a.blend":
            return [("Material", "Wood")]
        return []

    nodes = depscan.build_dependency_tree(scan, datablocks_from_library_fn=fake_datablocks)
    tier = next(n for n in nodes if n.key == "f7tier:will_break")
    cat = next(c for c in tier.children if c.key == "f7err:circular_link")
    finding = cat.children[0]
    # Both directions of the loop are represented as their own pair node.
    assert any(c.label.startswith("a") and "b" in c.label for c in finding.children)
    assert any(c.label.startswith("b") and "a" in c.label for c in finding.children)
    a_to_b = next(c for c in finding.children if c.label.startswith("a"))
    assert a_to_b.children[0].label == "Object: Tree"
    assert a_to_b.children[0].ref == {"type": "Object", "name": "Tree"}
    b_to_a = next(c for c in finding.children if c.label.startswith("b"))
    assert b_to_a.children[0].label == "Material: Wood"


def test_circular_pair_node_maps_friendly_kind_to_bpy_class():
    """A friendly kind label that doesn't match the real bpy class name (Node
    Group/Shape Key/Particle) must still resolve to the real class for
    click-to-select, not the display label."""
    mapping = {
        depscan._key("C:/proj/a.blend"): [_R("//b.blend", "C:/proj/b.blend", True, True)],
        depscan._key("C:/proj/b.blend"): [_R("//a.blend", "C:/proj/a.blend", True, True)],
    }
    scan = depscan.scan_recursive([pathlib.Path("C:/proj/a.blend")], scan_file=_stub(mapping))
    nodes = depscan.build_dependency_tree(
        scan, datablocks_from_library_fn=lambda linker, basename: [("Node Group", "Shader")])
    tier = next(n for n in nodes if n.key == "f7tier:will_break")
    cat = next(c for c in tier.children if c.key == "f7err:circular_link")
    finding = cat.children[0]
    leaf = finding.children[0].children[0]
    assert leaf.ref == {"type": "NodeTree", "name": "Shader"}


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
