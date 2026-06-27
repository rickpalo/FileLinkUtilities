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


def _is_shape_key_reciprocal(cycle: list[str]) -> bool:
    """A Mesh/Curve/Lattice <-> its own Key (shape keys) back-reference is
    INTRINSIC Blender plumbing, not a real override-resync-loop bug: the
    owner's ``shape_keys`` pointer and the Key's own (read-only) ``user``
    pointer mirror each other, so EVERY shape-keyed datablock forms exactly
    this reciprocal pair — it would otherwise swamp the loop count with
    non-actionable noise (real user report, 2026-06-25: "Mesh/CC_Base_
    Body.038 -> Key/Key.296 -> Mesh/CC_Base_Body.038", asking what kind of
    loop that even is). Only the bare 2-node pair is excluded — a LONGER
    loop that happens to pass through a Key (3+ distinct datablocks) is
    still a real structural problem and stays reported."""
    nodes = set(cycle)
    return len(nodes) == 2 and any(n.startswith("Key/") for n in nodes)


def find_datablock_loops(edges: list[tuple[str, str]]) -> list[list[str]]:
    """Cycles in the datablock dependency graph. ``edges`` are (user, used) node
    ids (e.g. ``"Object/Body"`` -> ``"Mesh/Body"``); a cycle is a dependency loop.

    Self-edges (``X -> X``) are dropped: an id appears in its own ``user_map`` via
    modifiers/drivers/constraints, but that is not a multi-datablock loop and would
    otherwise inflate the count with meaningless 1-cycles. The intrinsic Mesh<->Key
    reciprocal pair is dropped too — see :func:`_is_shape_key_reciprocal`."""
    g = DepGraph()
    for src, dst in edges:
        if src != dst:
            g.add_edge(src, dst)
    return [c for c in g.find_cycles() if not _is_shape_key_reciprocal(c)]


@dataclass
class LiveExtract:
    """Everything the bpy walk pulls out of the current file for Phase 2."""

    totals: dict[str, int] = field(default_factory=dict)          # type label -> count
    library_counts: list[tuple[str, int]] = field(default_factory=list)  # (lib name, #blocks)
    override_count: int = 0
    loops: list[list[str]] = field(default_factory=list)          # datablock cycles
    loops_skipped: str = ""  # reason, if loop detection was skipped (too large)
    # (shape key name, owning mesh name) for every Key whose owner is itself a
    # Library Override — Blender's writer can flag these "directly linked, but
    # not linkable" (the KEKey.NNN warnings), since a shape key can never be an
    # independent override on its own, only inherited via its owner.
    shape_key_risks: list[tuple[str, str]] = field(default_factory=list)


def build_live_report(extract: LiveExtract, file_label: str = "current file") -> Report:
    """Turn a :class:`LiveExtract` into the F7 live (overrides & duplicates) report.

    Deliberately does NOT report ``.NNN``-suffix duplicate families here
    (removed 2026-06-26, user request): the name-only heuristic across every
    datablock type (Mesh, Object, Collection, ...) overclaimed badly — Blender
    appends ``.NNN`` constantly for objects that diverge after linking (e.g. a
    cloth-sim bake), not just true duplicates. Images, the one type where
    ``.NNN`` families are commonly REAL duplicates, already have a dedicated
    content-hash-verified tool (Duplicate Textures); the rest are covered by
    "Find Duplicate Data-blocks" (`core.datablock_dedup`), which is the same
    name-only heuristic but at least scoped to a deliberate own button rather
    than bundled into this audit."""
    report = Report(title=f"Overrides: {file_label}", feature="f7live")

    # Headline counts as a flat top row, read at a glance without drilling into
    # each category (mirrors core.missingdata's "overview" row).
    n_loops = len(extract.loops)
    n_libs = len(extract.library_counts)
    severity = "error" if n_loops else "info"
    report.add(Finding(
        category="overview",
        message=(f"{n_loops} override loop(s) · "
                 f"{n_libs} librar{'y' if n_libs == 1 else 'ies'} · "
                 f"{extract.override_count} override(s)"),
        severity=severity,
        data={"loops": n_loops, "libraries": n_libs,
              "overrides": extract.override_count}))

    # Override dependency loops first — these are the crash/resync cause.
    for loop in extract.loops:
        report.add(Finding(category="override_loop",
                           message="Dependency loop: " + " → ".join(loop),
                           severity="error", items=list(loop)))
    if extract.loops_skipped:
        report.add(Finding(category="override_loop",
                           message=f"Loop detection skipped: {extract.loops_skipped}",
                           severity="warning"))

    # Shape keys sitting on override meshes — Blender can't write a shape key
    # as its own "directly linked" override (only its owner can be one), which
    # is the likely cause of the "KEKey.NNN ... not linkable, but flagged as
    # directly linked" write warnings on heavily-overridden files (Batch C #3's
    # KEKey half, real user report). A heuristic, not a literal interception of
    # Blender's write-time warning (no public API exposes that) — but it names
    # exactly the datablocks most likely responsible.
    for key_name, mesh_name in extract.shape_key_risks:
        report.add(Finding(
            category="shape_key_override_risk",
            message=(f"Shape key '{key_name}' sits on override mesh '{mesh_name}' — "
                     "likely cause of Blender's \"KEKey ... not linkable, but flagged "
                     "as directly linked\" write warnings for this file"),
            severity="warning", items=[f"Mesh/{mesh_name}"]))

    # Library blocks (how many datablocks come from each library).
    for lib, n in extract.library_counts:
        report.add(Finding(category="library_block",
                           message=f"{lib}: {n} linked datablock(s)",
                           severity="info", items=[lib], detail=f"{n}"))

    # No trailing "summary" Finding here (unlike most reports) — the flat
    # "overview" headline above already carries the same counts, just phrased
    # differently; a second summary row was redundant clutter (user, 2026-06-23).
    return report
