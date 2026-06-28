"""F6 Layer 2/3 — lossless content-overlap merge of duplicate image datablocks.

The image analogue of F3 material dedup: the same image imported more than once
(under the same name — ``Leather``, ``Leather.001`` — or under a totally
different one across folders) wastes memory as content-identical datablocks.
This module groups LOCAL images by a **content fingerprint the operator
supplies** (dimensions + a file/packed hash) regardless of name; any group of
2+ identical-content datablocks is offered for LOSSLESS merge. This is the
SAFETY RULE: content identity is verified before any merge — name is never
trusted alone.

(History: an earlier, narrower ``.NNN``-name-family-only scan, "Find .NNN",
was removed 2026-06-24 — confirmed redundant, since this content-based scan
uses the identical fingerprint over a strict superset of images and so always
finds everything the narrower scan did, plus cross-name/cross-folder
duplicates it couldn't see at all.)

Resolution variants (``Leather_1k`` vs ``_2k``) have DIFFERENT content, so they
never land in a merge group here — they are step 4's lossy standardize, kept
separate by design so a 1k/2k pair is never collapsed by accident.
"""

from __future__ import annotations

from dataclasses import dataclass

from .datablock_dedup import FamilyConflict, MergePlan
from .datablock_dedup import removable_count as removable_count
from .datablock_dedup import victims_for_keeper as victims_for_keeper
from .datablock_graph import duplicate_families
from .report import Finding, Report


@dataclass
class ImgInfo:
    """A local image as the operator extracts it: a content ``fingerprint``
    (``""`` when it couldn't be verified — missing/unhashable) and its user count."""

    name: str
    fingerprint: str = ""
    users: int = 0


def plan_content_merges(images: list[ImgInfo]) -> list[MergePlan]:
    """Group images by CONTENT fingerprint regardless of name; any group of 2+
    identical-content datablocks is a LOSSLESS merge — crosses names and
    folders, so the same texture imported under different names across many
    CC4 folders collapses to one. Canonical = most-used, then shortest
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


def _fingerprint_dims(fingerprint: str) -> str:
    """The size/channel/depth portion of an image fingerprint, dropping the
    trailing content hash — ``"1024x1024:4:8:<sha1>"`` -> ``"1024x1024:4:8"``."""
    dims, _sep, _content_hash = fingerprint.rpartition(":")
    return dims


def find_image_conflicts(images: list[ImgInfo]) -> list[FamilyConflict]:
    """Same-``.NNN``-name-family images that did NOT end up in one content-
    merge group — informational only, never a merge trigger (a fingerprint
    match is still the only thing ``plan_content_merges`` ever merges on).
    Distinguishes WHY a family was kept separate: different dimensions
    (probably a resolution variant misnamed with a ``.NNN`` suffix instead of
    a resolution token, or just two unrelated images sharing a name) vs. the
    same dimensions but a different pixel hash (the genuinely suspicious case
    — looks like the same texture, isn't)."""
    by_name = {i.name: i for i in images}
    fams = duplicate_families([i.name for i in images])
    conflicts: list[FamilyConflict] = []
    for base in sorted(fams):
        group = [by_name[n] for n in fams[base]]
        fingerprints = {i.fingerprint for i in group if i.fingerprint}
        unverified = [i.name for i in group if not i.fingerprint]
        if len(fingerprints) <= 1 and not unverified:
            continue  # single clean fingerprint group (or nothing at all to report)
        bits = []
        if len(fingerprints) > 1:
            dims = {_fingerprint_dims(fp) for fp in fingerprints}
            bits.append("different dimensions — likely a resolution variant, not a real "
                        "duplicate" if len(dims) > 1
                        else "same dimensions, different content — worth a closer look")
        if unverified:
            bits.append(f"{len(unverified)} unverified (no fingerprint available) — not merged")
        conflicts.append(FamilyConflict(base=base, members=sorted(i.name for i in group),
                                        reason="; ".join(bits)))
    return conflicts


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
                           message="✓ No duplicate image datablocks",
                           severity="info"))
    else:
        report.add(Finding(category="summary",
                           message=f"{len(plans)} merge group(s); ~{purge} redundant "
                                   f"datablock(s) removable",
                           severity="info", data={"plans": len(plans), "purge": purge}))
    return report


__all__ = ["ImgInfo", "MergePlan", "FamilyConflict",
           "plan_content_merges", "removable_count", "victims_for_keeper",
           "build_dedup_report"]
