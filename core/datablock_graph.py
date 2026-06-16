"""F7 Phase 2 core — datablock-level census + loop detection (bpy-free).

The operator extracts plain data from ``bpy.data`` (names per type, library of
each id, override flags, and a ``user_map`` restricted to linked/override ids)
and feeds it here. This module owns the pure logic — duplicate-family grouping
and dependency-loop detection (reusing :class:`core.graph.DepGraph`) — so it is
unit-testable without Blender.

Why this matters: a file like PSM_Stage_v5.1 accumulated hundreds of duplicate
datablocks (``KEKey.553``, ``MECC_Base_Body.008``) from repeated linking, and an
override **dependency loop** between a linked file and its library is what spams
``lib.override.resync … indirect usages too high`` and bloats/crashes the file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .graph import DepGraph
from .report import Finding, Report

# Blender's duplicate suffix is ``.NNN`` (``.001``…; longer on huge files, e.g.
# ``.553``). Matching 3+ digits avoids stripping legitimate names ending in a
# single digit (versions like "Mat.2"). Heuristic — documented, not perfect.
_DUP_SUFFIX = re.compile(r"\.\d{3,}$")


def strip_dup_suffix(name: str) -> str:
    """``"MECC_Base_Body.008"`` -> ``"MECC_Base_Body"`` (``"Body"`` unchanged)."""
    return _DUP_SUFFIX.sub("", name)


def duplicate_families(names: list[str]) -> dict[str, list[str]]:
    """Group names sharing a base (the original + its ``.NNN`` copies). Only
    families with the base name actually present **and** at least one numbered
    copy, or 2+ members, are returned — i.e. genuine duplicate sets."""
    fam: dict[str, list[str]] = {}
    for n in names:
        fam.setdefault(strip_dup_suffix(n), []).append(n)
    return {base: sorted(v) for base, v in fam.items() if len(v) > 1}


def find_datablock_loops(edges: list[tuple[str, str]]) -> list[list[str]]:
    """Cycles in the datablock dependency graph. ``edges`` are (user, used) node
    ids (e.g. ``"Object/Body"`` -> ``"Mesh/Body"``); a cycle is a dependency loop.

    Self-edges (``X -> X``) are dropped: an id appears in its own ``user_map`` via
    modifiers/drivers/constraints, but that is not a multi-datablock loop and would
    otherwise inflate the count with meaningless 1-cycles."""
    g = DepGraph()
    for src, dst in edges:
        if src != dst:
            g.add_edge(src, dst)
    return g.find_cycles()


@dataclass
class LiveExtract:
    """Everything the bpy walk pulls out of the current file for Phase 2."""

    totals: dict[str, int] = field(default_factory=dict)          # type label -> count
    duplicates: dict[str, dict[str, list[str]]] = field(default_factory=dict)  # type -> families
    library_counts: list[tuple[str, int]] = field(default_factory=list)  # (lib name, #blocks)
    override_count: int = 0
    loops: list[list[str]] = field(default_factory=list)          # datablock cycles
    loops_skipped: str = ""  # reason, if loop detection was skipped (too large)


def wasted_copies(duplicates: dict[str, dict[str, list[str]]]) -> int:
    """Total redundant datablocks across all families (members minus one each)."""
    return sum(len(members) - 1
               for fams in duplicates.values() for members in fams.values())


def build_live_report(extract: LiveExtract, file_label: str = "current file") -> Report:
    """Turn a :class:`LiveExtract` into the F7 live (overrides & duplicates) report."""
    report = Report(title=f"Overrides & duplicates: {file_label}", feature="f7live")

    # Override dependency loops first — these are the crash/resync cause.
    for loop in extract.loops:
        report.add(Finding(category="override_loop",
                           message="Dependency loop: " + " → ".join(loop),
                           severity="error", items=list(loop)))
    if extract.loops_skipped:
        report.add(Finding(category="override_loop",
                           message=f"Loop detection skipped: {extract.loops_skipped}",
                           severity="warning"))

    # Duplicate families (the .NNN bloat), worst first, grouped by type.
    waste = wasted_copies(extract.duplicates)
    for type_label in sorted(extract.duplicates):
        fams = extract.duplicates[type_label]
        for base in sorted(fams, key=lambda b: -len(fams[b])):
            members = fams[base]
            report.add(Finding(category="duplicate_family",
                               message=f"{type_label}: {base} ×{len(members)}",
                               severity="warning",
                               items=members, detail=f"{len(members)}",
                               data={"type": type_label, "base": base}))

    # Library blocks (how many datablocks come from each library).
    for lib, n in extract.library_counts:
        report.add(Finding(category="library_block",
                           message=f"{lib}: {n} linked datablock(s)",
                           severity="info", items=[lib], detail=f"{n}"))

    if extract.override_count:
        report.add(Finding(category="override_summary",
                           message=f"{extract.override_count} library override(s) in file",
                           severity="info"))

    report.add(Finding(category="summary",
                       message=f"{len(extract.loops)} loop(s); ~{waste} redundant "
                               f"duplicate datablock(s); {len(extract.library_counts)} "
                               f"linked library/-ies",
                       severity="info",
                       data={"loops": len(extract.loops), "wasted": waste}))
    return report
