"""Batch C — datablock RECONNECT (bpy-free suggestion logic).

A missing data-block (see :mod:`core.missingdata`) is a placeholder: its source
library either can't be found, or no longer holds a block of that name (renamed or
removed at the source — e.g. the link wants ``GeometricStichDesign`` but
``materialMaster.blend`` now has ``GeometricStichDesign.001``). Reconnecting means
pointing the placeholder at a REAL datablock — in the same library (re-pointed at
an upgraded file) or a different one entirely — then merging the placeholder's
users onto it.

This module only decides WHICH name to suggest, given the names available in a
chosen source .blend's matching collection (read via a peek-only
``bpy.data.libraries.load``, which needs bpy and so lives in ``ops.datablock_
reconnect``, not here). The actual link + ``user_remap`` is bpy-only and lives
there too.

Confidence ladder (mirrors the texture fuzzy-matcher's, but for datablock identity
rather than filenames): an EXACT name match beats a same-base ``.NNN`` match (the
renamed-at-source case) beats a fuzzy token-affinity guess.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .datablock_graph import strip_dup_suffix
from .imagematch import name_affinity
from .missingdata import MissingBlock

# Below this token-affinity, a candidate isn't worth suggesting at all — the same
# floor the texture matcher uses to decide "is this plausibly the same thing,
# renamed".
FUZZY_FLOOR = 0.5


@dataclass(frozen=True)
class Suggestion:
    """The best candidate name for a missing block, or none."""

    target: str       # candidate name, "" if nothing qualifies
    confidence: str    # "exact" | "numbered" | "fuzzy" | "none"


def suggest_reconnect(wanted: str, candidates: list[str], *, allow_fuzzy: bool = True) -> Suggestion:
    """Best candidate in ``candidates`` (names available in the chosen source
    .blend's matching collection) to reconnect a missing block named ``wanted``.

    ``allow_fuzzy=False`` stops after the exact/numbered tiers — used for
    in-memory suggestions (Examine Library), where guessing wrong would silently
    repoint a link at an unrelated existing datablock; a manual file+item pick is
    the deliberate fallback there instead of a fuzzy guess."""
    if not candidates:
        return Suggestion("", "none")
    pool = set(candidates)
    if wanted in pool:
        return Suggestion(wanted, "exact")

    base = strip_dup_suffix(wanted)
    same_base = sorted(c for c in candidates if strip_dup_suffix(c) == base)
    if same_base:
        # Prefer the un-suffixed base name if it's present, else the first copy.
        return Suggestion(base if base in pool else same_base[0], "numbered")

    if not allow_fuzzy:
        return Suggestion("", "none")

    best_name, best_score = "", 0.0
    for c in candidates:
        score = name_affinity(wanted, c)
        if score > best_score:
            best_name, best_score = c, score
    if best_score >= FUZZY_FLOOR:
        return Suggestion(best_name, "fuzzy")
    return Suggestion("", "none")


def ranked_candidates(wanted: str, candidates: list[str]) -> list[str]:
    """``candidates`` reordered so the suggested name (if any) comes first.

    Used to default a dynamic-enum dropdown's selection (Blender shows a fresh
    dynamic EnumProperty's FIRST item by default) without explicitly assigning its
    value — the duplicate-texture keeper dropdown found explicit dynamic-enum
    assignment fragile; ordering is the safe way to default a selection."""
    suggestion = suggest_reconnect(wanted, candidates)
    if not suggestion.target:
        return sorted(candidates)
    rest = sorted(c for c in candidates if c != suggestion.target)
    return [suggestion.target, *rest]


def find_sibling_library(missing_path: str, resolving_paths: list[str]) -> str:
    """``missing_path`` is a library's stored path that doesn't resolve on this
    machine. If exactly one path in ``resolving_paths`` (other libraries
    already loaded and confirmed to resolve) shares its basename, return it —
    the SAME file, linked via a different/stale path string. Real, documented
    disease on this project's own files: the same library gets linked many
    times under different path strings (absolute vs ``//``-relative, forward
    vs back slash, or a since-moved folder) — Blender treats each as a
    separate ``Library`` datablock, so a missing block recorded under a STALE
    duplicate path string would otherwise never auto-match even though the
    same file resolves fine elsewhere in the very same session.

    Returns ``""`` when there's no match or more than one — never guess when
    ambiguous (mirrors ``core.imagepaths.find_image_target``'s rule)."""
    basename = os.path.basename(missing_path.replace("\\", "/")).lower()
    if not basename:
        return ""
    matches = {p for p in resolving_paths
              if os.path.basename(p.replace("\\", "/")).lower() == basename}
    return next(iter(matches)) if len(matches) == 1 else ""


@dataclass(frozen=True)
class ReconnectPlan:
    """One missing block paired with its best suggestion."""

    block: MissingBlock
    suggestion: Suggestion


def plan_reconnects(
    blocks: list[MissingBlock], candidates_by_collection: dict[str, list[str]],
) -> list[ReconnectPlan]:
    """One :class:`ReconnectPlan` per missing block, suggesting the best name found
    in ``candidates_by_collection`` (``{bpy.data attribute: [names available in the
    chosen source .blend]}``), keyed by each block's own ``collection``."""
    return [
        ReconnectPlan(b, suggest_reconnect(b.name, candidates_by_collection.get(b.collection, [])))
        for b in blocks
    ]


__all__ = [
    "Suggestion", "suggest_reconnect", "ranked_candidates", "find_sibling_library",
    "ReconnectPlan", "plan_reconnects", "FUZZY_FLOOR",
]
