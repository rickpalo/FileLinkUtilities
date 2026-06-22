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

from dataclasses import dataclass, field

from .datablock_graph import duplicate_families
from .report import Finding, Report


@dataclass
class ImgInfo:
    """A local image as the operator extracts it: a content ``fingerprint``
    (``""`` when it couldn't be verified — missing/unhashable) and its user count."""

    name: str
    fingerprint: str = ""
    users: int = 0


@dataclass
class MergePlan:
    base: str                       # family base name (suffix stripped)
    canonical: str                  # the datablock to keep
    redundant: list[str] = field(default_factory=list)  # remap->canonical, then remove
    fingerprint: str = ""


@dataclass
class FamilyConflict:
    base: str
    members: list[str]
    reason: str  # why the family wasn't a single clean merge


def _pick_canonical(group: list[ImgInfo], base: str) -> str:
    """Prefer the un-suffixed original name (``Leather`` over ``Leather.001``);
    else the most-used datablock; ties broken lexicographically (deterministic)."""
    for m in group:
        if m.name == base:
            return base
    return sorted(group, key=lambda m: (-m.users, m.name))[0].name


def plan_dup_merges(images: list[ImgInfo]
                    ) -> tuple[list[MergePlan], list[FamilyConflict]]:
    """``(merge plans, conflicts)``. Within each ``.NNN`` family, group members by
    fingerprint; any fingerprint-group of 2+ is a lossless :class:`MergePlan`. A
    family with more than one distinct content (or unverifiable members) is also
    surfaced as a :class:`FamilyConflict` so the user sees what wasn't merged."""
    by_name = {i.name: i for i in images}
    fams = duplicate_families([i.name for i in images])
    plans: list[MergePlan] = []
    conflicts: list[FamilyConflict] = []
    for base in sorted(fams):
        members = [by_name[n] for n in fams[base]]
        groups: dict[str, list[ImgInfo]] = {}
        unverified: list[str] = []
        for m in members:
            if m.fingerprint:
                groups.setdefault(m.fingerprint, []).append(m)
            else:
                unverified.append(m.name)
        for fp, group in groups.items():
            if len(group) >= 2:
                canonical = _pick_canonical(group, base)
                redundant = sorted(m.name for m in group if m.name != canonical)
                plans.append(MergePlan(base=base, canonical=canonical,
                                       redundant=redundant, fingerprint=fp))
        if len(groups) > 1 or unverified:
            reason = ("differing content — identical copies merged, variants kept"
                      if len(groups) > 1
                      else "unverified copies (missing/unhashable) — not merged")
            conflicts.append(FamilyConflict(
                base=base, members=sorted(m.name for m in members), reason=reason))
    return plans, conflicts


def removable_count(plans: list[MergePlan]) -> int:
    """Total datablocks the plans would remove (sum of redundant members)."""
    return sum(len(p.redundant) for p in plans)


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
           "removable_count", "build_dedup_report"]
