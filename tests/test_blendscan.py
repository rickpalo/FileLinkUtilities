"""F1 tests against the committed linkproj fixtures (scene -> libA -> libB).

These exercise the real BAT-backed reader on real Blender 5.1 files, but run
under plain pytest (BAT wheel is put on sys.path by conftest).
"""

import pathlib

import pytest

from core import blendscan
from core.f1_linkmap import build_link_report

LINKPROJ = pathlib.Path(__file__).resolve().parent / "fixtures" / "linkproj"

pytestmark = pytest.mark.skipif(
    not (LINKPROJ / "scene.blend").is_file(),
    reason="linkproj fixtures not built (run tests/fixtures/build_linkproj.py in Blender)",
)


def test_scan_file_reads_direct_link():
    refs = blendscan.scan_file(LINKPROJ / "scene.blend")
    assert len(refs) == 1
    ref = refs[0]
    assert ref.stored_path == "//libA.blend"
    assert ref.is_relative is True
    assert ref.exists is True
    assert pathlib.Path(ref.resolved_path).name == "libA.blend"


def test_libB_is_a_leaf():
    assert blendscan.scan_file(LINKPROJ / "libB.blend") == []


def test_harvest_image_paths_runs_on_real_blend():
    # The link fixtures hold no images, so the result is empty — but this proves the
    # BAT IM-block path harvest runs against a real .blend without error (the texture
    # corpus for "Suggest from another .blend"). Matching itself is covered by
    # core.imagematch.propose_from_paths tests.
    out = blendscan.harvest_image_paths(LINKPROJ / "scene.blend")
    assert isinstance(out, list)
    assert all(isinstance(p, str) for p in out)


def test_resolve_blend_relative():
    base = LINKPROJ / "scene.blend"
    resolved, is_rel = blendscan.resolve_blend_relative("//libA.blend", base)
    assert is_rel is True
    assert pathlib.Path(resolved) == (LINKPROJ / "libA.blend").resolve()

    abs_in = str((LINKPROJ / "libA.blend").resolve())
    resolved2, is_rel2 = blendscan.resolve_blend_relative(abs_in, base)
    assert is_rel2 is False
    assert pathlib.Path(resolved2) == (LINKPROJ / "libA.blend").resolve()


def test_map_folder_builds_transitive_graph():
    scan = blendscan.map_folder(LINKPROJ)
    g = scan.graph
    # scene -> libA -> libB
    assert len(g.nodes) == 3
    assert len(g.edges) == 2
    names = {pathlib.Path(n).name for n in g.nodes}
    assert names == {"scene.blend", "libA.blend", "libB.blend"}
    # roots/leaves by basename
    roots = {pathlib.Path(n).name for n in g.roots()}
    leaves = {pathlib.Path(n).name for n in g.leaves()}
    assert roots == {"scene.blend"}
    assert leaves == {"libB.blend"}
    assert not scan.errors


def test_build_link_report_clean_project():
    report, scan = build_link_report(LINKPROJ)
    assert report.feature == "F1"
    cats = {f.category for f in report.findings}
    # A healthy relative-linked project: no broken links, no cycles, no abs paths.
    assert "broken_link" not in cats
    assert "circular_link" not in cats
    assert "absolute_path" not in cats
    summary = [f for f in report.findings if f.category == "summary"][0]
    assert summary.data["files"] == 3
    assert summary.data["links"] == 2


def test_report_detects_broken_link(tmp_path):
    # Copy only scene.blend + libA.blend; omit libB so libA's link is broken.
    import shutil

    proj = tmp_path / "proj"
    proj.mkdir()
    for name in ("scene.blend", "libA.blend"):
        shutil.copy(LINKPROJ / name, proj / name)

    report, scan = build_link_report(proj)
    broken = [f for f in report.findings if f.category == "broken_link"]
    assert len(broken) == 1
    assert "libB.blend" in broken[0].message


def test_incremental_scan_matches_map_folder():
    # The modal driver builds results via scan_into one file at a time; the
    # outcome must match the synchronous map_folder.
    files = list(blendscan.iter_blend_files(LINKPROJ))
    incremental = blendscan.new_scan_result()
    for f in files:
        blendscan.scan_into(incremental, f)
    full = blendscan.map_folder(LINKPROJ)
    assert incremental.graph.nodes == full.graph.nodes
    assert sorted(incremental.graph.edges, key=lambda e: (e.source, e.target)) == \
        sorted(full.graph.edges, key=lambda e: (e.source, e.target))
    assert incremental.errors == full.errors


def test_report_from_scan_matches_build_link_report():
    from core.f1_linkmap import build_link_report, report_from_scan

    report_a, scan = build_link_report(LINKPROJ)
    report_b = report_from_scan(scan, LINKPROJ)
    assert report_a.to_dict() == report_b.to_dict()


def test_bat_available_true_with_wheel_on_path():
    assert blendscan.bat_available() is True


def test_graph_to_dot_smoke():
    scan = blendscan.map_folder(LINKPROJ)
    dot = scan.graph.to_dot()
    assert dot.startswith("digraph deps {")
    assert "libA.blend" in dot
    assert "->" in dot
