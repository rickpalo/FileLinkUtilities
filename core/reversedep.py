"""Batch 3 — reverse-dependency ("safe to delete?") check (bpy-free).

The folder scan (:func:`core.blendscan.map_folder`) gives a directed file→file
graph where an edge ``A → B`` means "A links a library from B". The normal scan
reads it top-down (what does A pull in?). This module reads it the OTHER way:
given a file you're about to delete, who links **to** it — directly or through a
chain — and would therefore break?

This is the inverse of the top-down scan and exists because of a real incident:
a 19 GB ``ThePiazzaSanMarco.blend`` was deleted as "an old version" while it was a
live dependency of two staged scenes. Run this first and the answer is a flat list
of the files that would go magenta.

bpy-free + unit-tested; the operator scans a folder offline (BAT) and feeds the
edge pairs + node list here.
"""

from __future__ import annotations

import ntpath

from .report import Finding, Report


def _key(path: str) -> str:
    """Case/separator-insensitive comparison key for a path string."""
    return str(path).replace("\\", "/").rstrip("/").lower()


def _name(path: str) -> str:
    return ntpath.basename(str(path).replace("\\", "/").rstrip("/")) or str(path)


def dependents(edge_pairs, nodes, target: str):
    """``(direct, indirect, canonical)`` for ``target`` within the scanned graph.

    ``edge_pairs`` is an iterable of ``(source, target)`` path strings ("source
    links target"); ``nodes`` is the set of all scanned file paths. Returns the
    files that link ``target`` **directly** (immediate predecessors) and the ones
    that reach it only **transitively** (sorted, original path strings), plus the
    canonical node string that matched ``target`` (``None`` if it wasn't scanned —
    so the caller can tell "nothing links it" from "it wasn't in the scan")."""
    tkey = _key(target)
    canon = next((n for n in nodes if _key(n) == tkey), None)
    if canon is None:
        return [], [], None

    rev: dict[str, set[str]] = {}  # node -> its direct linkers (predecessors)
    for src, dst in edge_pairs:
        if src != dst:
            rev.setdefault(dst, set()).add(src)

    direct = set(rev.get(canon, set()))
    # Reverse-reachability (BFS over the inverted graph), cycle-safe via `seen`.
    seen = {canon}
    queue = list(direct)
    ancestors: set[str] = set()
    while queue:
        n = queue.pop()
        if n in seen:
            continue
        seen.add(n)
        ancestors.add(n)
        for pred in rev.get(n, ()):
            if pred not in seen:
                queue.append(pred)
    indirect = ancestors - direct  # a direct linker is reported as direct, not both
    return sorted(direct), sorted(indirect), canon


def build_reverse_dep_report(target: str, direct, indirect, found: bool,
                             scanned: int = 0, file_label: str | None = None) -> Report:
    """Report who depends on ``target``. Three outcomes, all visible (never a silent
    pass): not-in-scan (warning — wrong folder), nothing-links-it (✓ safe), or a
    listing of the dependents that would break."""
    label = file_label or _name(target)
    report = Report(title=f"Safe to delete? {label}", feature="f7rev")

    if not found:
        report.add(Finding(
            category="clean",
            message=(f"'{label}' wasn't among the {scanned} scanned file(s) — point the "
                     "scan at the folder that holds the files which might link it"),
            severity="warning"))
        return report

    total = len(direct) + len(indirect)
    if total == 0:
        report.add(Finding(
            category="clean",
            message=f"✓ Nothing links to {label} — safe to delete "
                    f"(checked {scanned} file(s))",
            severity="info"))
        return report

    for s in direct:
        report.add(Finding(category="direct_dependent", message=_name(s),
                           severity="error", items=[s], data={"path": s}))
    for s in indirect:
        report.add(Finding(category="indirect_dependent", message=_name(s),
                           severity="warning", items=[s], data={"path": s}))

    tail = f", {len(indirect)} more transitively" if indirect else ""
    report.add(Finding(
        category="summary",
        message=f"{len(direct)} file(s) link {label} directly{tail} — deleting it "
                "will break them",
        severity="error",
        data={"direct": len(direct), "indirect": len(indirect)}))
    return report


__all__ = ["dependents", "build_reverse_dep_report"]
