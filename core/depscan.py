"""F7 Phase 1 — recursive single-file dependency scan + link issue classifier.

Starts at one (or more) ``.blend`` file, reads its library (``LI``) links offline
via BAT, resolves them, and recurses into each resolved ``.blend`` that exists,
building the dependency subtree for *that* file. Then classifies every link:

  intrinsic (per link):  missing · absolute · mixed-slash (backslashes)
  cross-file:            duplicate ref (same file -> one target via >1 stored path)
                         inconsistent path (one target reached via >1 stored form)
                         drive-remap candidate (missing absolute whose basename
                                                 resolves elsewhere under another root)

Reuses :mod:`core.blendscan` (``scan_file``/``LinkRef``) and :mod:`core.graph`
(``DepGraph``/``find_cycles``). bpy-free and unit-tested. The scan is exposed as a
**step-generator** (:func:`scan_recursive_steps`) so the modal operator can show
per-file status, advance under a time budget, and pause between files; the
synchronous :func:`scan_recursive` (used by tests and the EXEC path) just drains it.
"""

from __future__ import annotations

import ntpath
import pathlib
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Iterator

from .blendscan import LinkRef, scan_file as _bat_scan_file
from .graph import DepGraph
from .report import Finding, Report, SEVERITIES
from .tree import TreeNode, _CATEGORY_TITLES

# Link-issue category keys (also used as Report.Finding categories).
MISSING = "missing_link"
ABSOLUTE = "absolute_path"
MIXED_SLASH = "mixed_slash"
DUPLICATE_REF = "duplicate_ref"
INCONSISTENT_PATH = "inconsistent_path"
DRIVE_REMAP = "drive_remap"

ScanFileFn = Callable[[pathlib.Path], "list[LinkRef]"]


def _canon(path: str) -> str:
    """Graph identity for a path: absolute, separator-normalized, case preserved.
    Node ids and edge targets both go through this so the same file is one node
    regardless of whether the string came from ``resolve()`` or BAT's resolved
    path (which can differ in slash direction)."""
    try:
        return str(pathlib.Path(path).resolve())
    except OSError:
        return str(pathlib.Path(path))


def _key(path: str) -> str:
    """Canonical comparison key for a resolved path (case/sep-insensitive)."""
    return str(path).replace("\\", "/").rstrip("/").lower()


def _name(path: str) -> str:
    return ntpath.basename(path) or path


def has_backslash(stored: str) -> bool:
    """A stored Blender path containing ``\\`` is non-portable. The ``//`` prefix
    uses forward slashes, so any backslash is the (mixed-slash) problem."""
    return "\\" in stored


def link_issues(ref: LinkRef) -> set[str]:
    """Intrinsic issues for a single link, independent of the rest of the scan."""
    issues: set[str] = set()
    if not ref.exists:
        issues.add(MISSING)
    elif not ref.is_relative:
        issues.add(ABSOLUTE)
    if has_backslash(ref.stored_path):
        issues.add(MIXED_SLASH)
    return issues


@dataclass
class DepScan:
    """Outcome of a recursive dependency scan."""

    graph: DepGraph = field(default_factory=DepGraph)
    refs: dict[str, list[LinkRef]] = field(default_factory=dict)  # file key -> its links
    errors: dict[str, str] = field(default_factory=dict)  # file key -> read error
    order: list[str] = field(default_factory=list)  # visit order (file keys)
    roots: list[str] = field(default_factory=list)  # the start file keys
    sizes: dict[str, int] = field(default_factory=dict)  # file key -> bytes on disk


def new_dep_scan() -> DepScan:
    return DepScan()


def scan_recursive_steps(
    result: DepScan,
    starts: list[pathlib.Path],
    scan_file: ScanFileFn = _bat_scan_file,
    max_depth: int = 12,
) -> Iterator[tuple[float, str]]:
    """Fill ``result`` by BFS from ``starts``, yielding ``(fraction, status)``.

    Recurses only into resolved targets that *exist* and end in ``.blend``. The
    fraction is approximate (discovered frontier grows during the walk):
    ``processed / (processed + queued)``.
    """
    queue: deque[tuple[pathlib.Path, int]] = deque()
    visited: set[str] = set()  # normalized keys (case/sep-insensitive)
    for s in starts:
        s = pathlib.Path(s)
        result.roots.append(_canon(str(s)))
        queue.append((s, 0))

    processed = 0
    yield 0.0, f"Scanning {len(starts)} file(s)…"
    while queue:
        path, depth = queue.popleft()
        node = _canon(str(path))
        nk = _key(node)  # normalized key for dedup; node keeps original case
        if nk in visited:
            continue
        visited.add(nk)
        result.order.append(node)
        result.graph.add_node(node)
        try:  # disk size is ~free here (we already have the path); see _build_file_map
            result.sizes[node] = path.stat().st_size
        except OSError:
            pass

        processed += 1
        frac = processed / max(processed + len(queue), 1)
        sz = result.sizes.get(node)
        yield frac, (f"Reading {path.name}" + (f" ({_fmt_size(sz)})" if sz else "")
                     + f"…  ({processed} done, {len(queue)} queued)")

        if depth > max_depth:
            result.errors[node] = f"max recursion depth {max_depth} reached"
            continue
        try:
            file_refs = scan_file(path)
        except Exception as exc:  # unreadable/corrupt - record, keep going
            result.errors[node] = f"{type(exc).__name__}: {exc}"
            continue
        result.refs[node] = file_refs
        for ref in file_refs:
            target = ref.resolved_path or ref.stored_path
            result.graph.add_edge(node, _canon(target), ref.stored_path)
            if ref.exists and ref.resolved_path.lower().endswith(".blend"):
                if _key(ref.resolved_path) not in visited:
                    queue.append((pathlib.Path(ref.resolved_path), depth + 1))


def scan_recursive(
    starts: list[pathlib.Path],
    scan_file: ScanFileFn = _bat_scan_file,
    max_depth: int = 12,
) -> DepScan:
    """Synchronous convenience: drain :func:`scan_recursive_steps`."""
    result = new_dep_scan()
    for _ in scan_recursive_steps(result, starts, scan_file, max_depth):
        pass
    return result


def library_link_counts(scan: DepScan) -> list[tuple[str, int, bool]]:
    """(target key, times linked, exists-on-disk) sorted most-linked first."""
    indeg: dict[str, int] = {}
    for e in scan.graph.edges:
        indeg[e.target] = indeg.get(e.target, 0) + 1
    out = []
    for tgt, n in indeg.items():
        out.append((tgt, n, pathlib.Path(tgt).is_file()))
    out.sort(key=lambda t: (-t[1], _key(t[0])))
    return out


def duplicate_refs(scan: DepScan) -> dict[str, dict[str, list[str]]]:
    """Per file: resolved-target -> [distinct stored paths] when a file links the
    *same* resolved library via more than one stored path."""
    out: dict[str, dict[str, list[str]]] = {}
    for fkey, refs in scan.refs.items():
        by_target: dict[str, tuple[str, list[str]]] = {}  # normkey -> (real, forms)
        for ref in refs:
            real = ref.resolved_path or ref.stored_path
            _real, forms = by_target.setdefault(_key(real), (real, []))
            if ref.stored_path not in forms:
                forms.append(ref.stored_path)
        dups = {real: forms for real, forms in by_target.values() if len(forms) > 1}
        if dups:
            out[fkey] = dups
    return out


def inconsistent_paths(scan: DepScan) -> dict[str, list[str]]:
    """Across the whole subtree: resolved-target -> [distinct stored forms] when a
    single library is reached via more than one stored string (abs vs rel, slashes,
    different roots). These spawn duplicate library blocks in Blender."""
    groups: dict[str, tuple[str, list[str]]] = {}  # normkey -> (real, forms)
    for refs in scan.refs.values():
        for ref in refs:
            real = ref.resolved_path or ref.stored_path
            _real, forms = groups.setdefault(_key(real), (real, []))
            if ref.stored_path not in forms:
                forms.append(ref.stored_path)
    return {real: forms for real, forms in groups.values() if len(forms) > 1}


def drive_remap_candidates(scan: DepScan) -> list[tuple[str, str]]:
    """(missing stored path, an existing resolved path with the same basename).

    A missing *absolute* link whose basename matches a library that *does* resolve
    elsewhere in the subtree — i.e. the same file under a different drive/root, a
    prefix-remap candidate (e.g. ``D:\\…`` -> ``E:\\…``)."""
    existing_by_base: dict[str, str] = {}
    for refs in scan.refs.values():
        for ref in refs:
            if ref.exists and ref.resolved_path:
                existing_by_base.setdefault(ntpath.basename(ref.resolved_path).lower(),
                                            ref.resolved_path)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for refs in scan.refs.values():
        for ref in refs:
            if ref.exists or ref.is_relative:
                continue
            base = ntpath.basename(ref.stored_path).lower()
            match = existing_by_base.get(base)
            if match and ref.stored_path not in seen:
                seen.add(ref.stored_path)
                out.append((ref.stored_path, match))
    return out


def build_dep_report(scan: DepScan) -> Report:
    """Turn a :class:`DepScan` into the F7 dependency report."""
    start_names = ", ".join(_name(k) for k in scan.roots) or "(file)"
    report = Report(title=f"Dependencies: {start_names}", feature="F7")

    for path, msg in sorted(scan.errors.items()):
        report.add(Finding(category="unreadable_file",
                           message=f"Could not read {_name(path)}: {msg}",
                           severity="error", items=[path]))

    # Intrinsic per-link issues.
    for fkey in scan.order:
        for ref in scan.refs.get(fkey, []):
            issues = link_issues(ref)
            if MISSING in issues:
                report.add(Finding(category=MISSING,
                                   message=f"{_name(fkey)} links missing library {ref.stored_path}",
                                   severity="error",
                                   items=[fkey, ref.resolved_path or ref.stored_path],
                                   data={"stored": ref.stored_path}))
            elif ABSOLUTE in issues:
                report.add(Finding(category=ABSOLUTE,
                                   message=f"{_name(fkey)} links {ref.stored_path} by absolute path",
                                   severity="warning",
                                   items=[fkey, ref.resolved_path],
                                   data={"stored": ref.stored_path}))
            if MIXED_SLASH in issues:
                report.add(Finding(category=MIXED_SLASH,
                                   message=f"{_name(fkey)} stores backslashes in {ref.stored_path}",
                                   severity="warning",
                                   items=[fkey],
                                   data={"stored": ref.stored_path}))

    # Same file -> one target via several stored paths.
    for fkey, dups in sorted(duplicate_refs(scan).items()):
        for tk, forms in dups.items():
            report.add(Finding(category=DUPLICATE_REF,
                               message=f"{_name(fkey)} links {_name(tk)} via "
                                       f"{len(forms)} different paths: {', '.join(forms)}",
                               severity="error", items=[fkey, tk],
                               data={"forms": forms}))

    # One target reached via several stored forms across the subtree.
    for tk, forms in sorted(inconsistent_paths(scan).items()):
        report.add(Finding(category=INCONSISTENT_PATH,
                           message=f"{_name(tk)} is linked via {len(forms)} different path "
                                   f"forms (spawns duplicate library blocks): {', '.join(forms)}",
                           severity="warning", items=[tk], detail=f"{len(forms)} forms",
                           data={"forms": forms}))

    # Drive/root remap candidates.
    for stored, match in drive_remap_candidates(scan):
        report.add(Finding(category=DRIVE_REMAP,
                           message=f"Missing {stored} — same name resolves at {match}",
                           severity="warning", items=[stored, match],
                           data={"stored": stored, "candidate": match}))

    # Circular library references.
    for cycle in scan.graph.find_cycles():
        report.add(Finding(category="circular_link",
                           message="Circular library reference: "
                                   + " -> ".join(_name(n) for n in cycle),
                           severity="error", items=list(cycle)))

    # Most-linked libraries (the diamond/dup census), info.
    counts = library_link_counts(scan)
    for tgt, n, exists in counts[:25]:
        if n < 2:
            continue
        report.add(Finding(category="most_linked",
                           message=f"{_name(tgt)} linked {n}×" + ("" if exists else " (MISSING)"),
                           severity="info" if exists else "warning",
                           items=[tgt], detail=f"{n}×"))

    g = scan.graph
    report.add(Finding(category="summary",
                       message=f"{len(g.nodes)} files in subtree, {len(g.edges)} link(s)",
                       severity="info",
                       data={"files": len(g.nodes), "links": len(g.edges)}))
    return report


# Prettier section titles for the dependency-tree "Errors" categories.
_F7_TITLES = {
    "missing_link": "Missing libraries",
    "absolute_path": "Absolute paths",
    "mixed_slash": "Backslash paths",
    "duplicate_ref": "Duplicate references (same file → one library)",
    "inconsistent_path": "Inconsistent paths (one library, many forms)",
    "drive_remap": "Drive-remap candidates",
    "circular_link": "Circular references",
    "most_linked": "Most-linked libraries",
    "unreadable_file": "Unreadable files",
}
# Severity tiers — how worried the user should be. Each lists the categories it
# owns, worst-first within the tier. This is how we convey severity now (named
# groups), instead of per-row icons.
_F7_TIERS = [
    ("will_break", "Will break / likely crash",
     ["circular_link", "missing_link", "unreadable_file"]),
    ("may_break", "May cause problems (bloat / instability)",
     ["inconsistent_path", "duplicate_ref", "drive_remap"]),
    ("portability", "Portability only (works on this machine)",
     ["absolute_path", "mixed_slash"]),
    ("info", "Informational (normal)",
     ["most_linked"]),
]


def _fmt_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _worst(severities) -> str:
    present = set(severities)
    for s in reversed(SEVERITIES):
        if s in present:
            return s
    return "info"


def _build_file_map(scan: DepScan) -> list[TreeNode]:
    """The dependency hierarchy as a tree of files: each file's children are the
    libraries it links, marked missing/absolute/backslash, cycle-safe (a file
    already on the current path is shown once as ``↻ circular`` and not recursed)."""
    counter = [0]

    def newkey() -> str:
        counter[0] += 1
        return f"fm:{counter[0]}"

    def build(node_key: str, ref: LinkRef | None, path: frozenset) -> TreeNode:
        name = _name(node_key)
        if node_key in path:
            return TreeNode(key=newkey(), label=f"{name}   ↻ circular", severity="error")
        markers: list[str] = []
        sev = "info"
        if ref is not None:
            if not ref.exists:
                markers.append("missing"); sev = "error"
            elif not ref.is_relative:
                markers.append("absolute"); sev = "warning"
            if has_backslash(ref.stored_path):
                markers.append("backslash")
                sev = sev if sev != "info" else "warning"
        label = name + (f"   [{', '.join(markers)}]" if markers else "")
        size = scan.sizes.get(node_key)
        node = TreeNode(key=newkey(), label=label, severity=sev,
                        detail=_fmt_size(size) if size else "")
        child_path = path | {node_key}
        for r in scan.refs.get(node_key, []):
            target = _canon(r.resolved_path or r.stored_path)
            node.children.append(build(target, r, child_path))
        return node

    return [build(root, None, frozenset()) for root in scan.roots]


def build_dependency_tree(scan: DepScan) -> list[TreeNode]:
    """The F7 Dependencies view: **Summary** (top) → **File map** (the hierarchy)
    → **Errors (N)** (the issue categories). Rendered directly as a TreeNode tree
    (the file map needs arbitrary depth, which the flat Report model can't hold)."""
    report = build_dep_report(scan)
    summary = next((f for f in report.findings if f.category == "summary"), None)

    groups: dict[str, list[Finding]] = {}
    for f in report.findings:
        if f.category == "summary":
            continue
        groups.setdefault(f.category, []).append(f)

    def cat_node(cat: str) -> TreeNode:
        findings = groups[cat]
        node = TreeNode(
            key=f"f7err:{cat}",
            label=_F7_TITLES.get(cat, _CATEGORY_TITLES.get(cat, cat)),
            severity=_worst(f.severity for f in findings), detail=str(len(findings)))
        for i, f in enumerate(findings):
            fn = TreeNode(key=f"f7err:{cat}:{i}", label=f.message,
                          severity=f.severity, detail=f.detail)
            for j, item in enumerate(f.items):
                fn.children.append(TreeNode(key=f"f7err:{cat}:{i}:{j}", label=item,
                                            severity=f.severity))
            node.children.append(fn)
        return node

    nodes: list[TreeNode] = []
    if summary:
        nodes.append(TreeNode(key="f7:summary", label=summary.message, severity="info"))
    nodes.append(TreeNode(key="f7:filemap", label="File map",
                          detail=str(len(scan.order)), children=_build_file_map(scan)))

    # One node per severity tier (skipping empty ones), worst tier first.
    for tier_key, tier_label, cats in _F7_TIERS:
        present = [c for c in cats if c in groups]
        if not present:
            continue
        children = [cat_node(c) for c in present]
        count = sum(len(groups[c]) for c in present)
        nodes.append(TreeNode(key=f"f7tier:{tier_key}", label=tier_label,
                              detail=str(count),
                              severity=_worst(n.severity for n in children),
                              children=children))
    return nodes
