"""Generic ``.NNN`` name-family duplicate-merge planning (bpy-free).

Any Blender ID type can accumulate duplicate-named copies from repeated linking
or re-importing — ``Leather``/``Leather.001`` for images, but just as often
``Walk.001``/``Walk.002`` for Actions, or ``Body.553`` for meshes. The planning
logic is identical regardless of type: group a name-family's members by a
caller-supplied content fingerprint, and offer a lossless merge for any
fingerprint-identical 2+ subset. This is the SAME safety rule every per-type
dedup in this addon already follows (name similarity finds candidates; content
identity gates the merge) — extracted here once so it isn't reimplemented per
type. ``core.imagededup`` is a thin, image-flavored front end over this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .datablock_graph import duplicate_families


@dataclass
class MemberInfo:
    """A name-family member as the caller extracts it: a content ``fingerprint``
    (``""`` when it couldn't be verified) and its user count."""

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


def _pick_canonical(group: list[MemberInfo], base: str) -> str:
    """Prefer the un-suffixed original name over the most-used datablock; ties
    broken lexicographically (deterministic)."""
    for m in group:
        if m.name == base:
            return base
    return sorted(group, key=lambda m: (-m.users, m.name))[0].name


def plan_merges(members: list[MemberInfo]) -> tuple[list[MergePlan], list[FamilyConflict]]:
    """``(merge plans, conflicts)``. Within each ``.NNN`` family, group members by
    fingerprint; any fingerprint-group of 2+ is a lossless :class:`MergePlan`. A
    family with more than one distinct content (or unverifiable members) is also
    surfaced as a :class:`FamilyConflict` so the caller can show what wasn't merged."""
    by_name = {m.name: m for m in members}
    fams = duplicate_families([m.name for m in members])
    plans: list[MergePlan] = []
    conflicts: list[FamilyConflict] = []
    for base in sorted(fams):
        group_members = [by_name[n] for n in fams[base]]
        groups: dict[str, list[MemberInfo]] = {}
        unverified: list[str] = []
        for m in group_members:
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
            bits = []
            if len(groups) > 1:
                bits.append("differing content — identical copies merged, variants kept")
            if unverified:
                bits.append(f"{len(unverified)} unverified (no fingerprint available) — not merged")
            conflicts.append(FamilyConflict(
                base=base, members=sorted(m.name for m in group_members),
                reason="; ".join(bits)))
    return plans, conflicts


def removable_count(plans: list[MergePlan]) -> int:
    """Total datablocks the plans would remove (sum of redundant members)."""
    return sum(len(p.redundant) for p in plans)


def victims_for_keeper(members: list[str], keeper: str) -> list[str]:
    """Members to remap+remove when ``keeper`` is the chosen survivor — i.e. every
    member except the keeper. Lets the UI override the auto-picked canonical: the
    user points the dropdown at any family member and merge follows that choice."""
    return [m for m in members if m != keeper]


__all__ = ["MemberInfo", "MergePlan", "FamilyConflict", "plan_merges",
           "removable_count", "victims_for_keeper"]
