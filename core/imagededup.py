"""F6 Layer 2 (step 3) — lossless merge of ``.NNN`` duplicate image datablocks.

The image analogue of F3 material dedup: when the same image is loaded more than
once Blender makes ``Leather``, ``Leather.001``, … — content-identical datablocks
that waste memory. This module groups local images into ``.NNN`` name-families
(reusing :func:`core.datablock_graph.duplicate_families`) and, WITHIN a family,
partitions by a **content fingerprint the operator supplies** (dimensions + a
file/packed hash). Only a fingerprint-identical subset (2+ members) is offered for
LOSSLESS merge; members of the same name-family that differ in content — or that
couldn't be hashed — are reported, never merged. This is the SAFETY RULE: name
similarity finds candidates; content identity is verified before any merge.

Resolution variants (``Leather_1k`` vs ``_2k``) have DIFFERENT names, so they do
not land in a ``.NNN`` family here — they are step 4's lossy standardize, kept
separate by design so a 1k/2k pair is never collapsed by accident.
"""

from __future__ import annotations

from dataclasses import dataclass

from .datablock_dedup import FamilyConflict, MemberInfo, MergePlan
from .datablock_dedup import plan_merges as _plan_merges
from .datablock_dedup import removable_count as removable_count
from .datablock_dedup import victims_for_keeper as victims_for_keeper
from .report import Finding, Report


@dataclass
class ImgInfo:
    """A local image as the operator extracts it: a content ``fingerprint``
    (``""`` when it couldn't be verified — missing/unhashable) and its user count."""

    name: str
    fingerprint: str = ""
    users: int = 0


def plan_dup_merges(images: list[ImgInfo]
                    ) -> tuple[list[MergePlan], list[FamilyConflict]]:
    """``(merge plans, conflicts)``. Within each ``.NNN`` family, group members by
    fingerprint; any fingerprint-group of 2+ is a lossless :class:`MergePlan`. A
    family with more than one distinct content (or unverifiable members) is also
    surfaced as a :class:`FamilyConflict` so the user sees what wasn't merged.

    Thin image-flavored wrapper over :func:`core.datablock_dedup.plan_merges` (the
    grouping logic isn't image-specific — every type's dedup tool shares it)."""
    return _plan_merges([MemberInfo(i.name, i.fingerprint, i.users) for i in images])


def plan_content_merges(images: list[ImgInfo]) -> list[MergePlan]:
    """F6 Layer 3 — group images by CONTENT fingerprint regardless of name; any
    group of 2+ identical-content datablocks is a LOSSLESS merge. Unlike
    :func:`plan_dup_merges` (which only looks WITHIN a ``.NNN`` name-family) this
    crosses names and folders, so the same texture imported under different names
    across many CC4 folders collapses to one. Canonical = most-used, then shortest
    name, then lexical (deterministic). Images with no fingerprint are skipped."""
    by_fp: dict[str, list[ImgInfo]] = {}
    for i in images:
        if i.fingerprint:
            by_fp.setdefault(i.fingerprint, []).append(i)
    plans: list[MergePlan] = []
    for fp, group in by_fp.items():
        if len(group) < 2:
            continue
        canonical = sorted(group, key=lambda m: (-m.users, len(m.name), m.name))[0].name
        redundant = sorted(m.name for m in group if m.name != canonical)
        plans.append(MergePlan(base=canonical, canonical=canonical,
                               redundant=redundant, fingerprint=fp))
    return sorted(plans, key=lambda p: p.canonical)


def build_dedup_report(plans: list[MergePlan], conflicts: list[FamilyConflict],
                       blend_name: str = "current file") -> Report:
    """Report the lossless-merge plan (info) then any conflicts (warning)."""
    report = Report(title=f"Duplicate textures: {blend_name}", feature="f6dup")
    for p in plans:
        report.add(Finding(category="merge_lossless",
                           message=f"{p.base}: keep {p.canonical}, "
                                   f"merge {len(p.redundant)} copy(ies)",
                           severity="info", items=[p.canonical, *p.redundant],
                           detail=f"-{len(p.redundant)}",
                           data={"canonical": p.canonical, "redundant": p.redundant}))
    for c in conflicts:
        report.add(Finding(category="family_conflict",
                           message=f"{c.base}: {c.reason}",
                           severity="warning", items=c.members))
    purge = removable_count(plans)
    if not plans and not conflicts:
        report.add(Finding(category="clean",
                           message="✓ No duplicate (.NNN) image datablocks",
                           severity="info"))
    else:
        report.add(Finding(category="summary",
                           message=f"{len(plans)} merge group(s); ~{purge} redundant "
                                   f"datablock(s) removable",
                           severity="info", data={"plans": len(plans), "purge": purge}))
    return report


__all__ = ["ImgInfo", "MergePlan", "FamilyConflict", "plan_dup_merges",
           "plan_content_merges", "removable_count", "victims_for_keeper",
           "build_dedup_report"]
