"""Shared confidence ranking, so a "select by tier" control (Select High /
High+Med / All / None) means the same thing across every list whose scanner
grades its rows — the reconnect list (``exact``/``numbered``/``fuzzy``/
``none``), the texture fuzzy matcher (``high``/``medium``/``low``), and any
future one. Each scanner keeps its own vocabulary; this maps them onto one
three-tier ladder. bpy-free (pure data + tests), per the project's core rule.
"""

from __future__ import annotations

from collections.abc import Iterable

# vocabulary term -> rank. 3 = confident/near-exact, 2 = plausible fuzzy,
# 1 = weak, 0 = no candidate at all. Unknown terms rank 0 (never auto-picked).
RANK: dict[str, int] = {
    "exact": 3, "numbered": 3, "high": 3,
    "fuzzy": 2, "medium": 2, "med": 2,
    "low": 1,
    "none": 0, "": 0,
}

# UI tier -> the minimum rank a row must meet to be selected. "NONE" clears
# everything (no rank reaches 99), so the four buttons span deselect-all
# through select-all.
TIER_MIN_RANK: dict[str, int] = {"HIGH": 3, "MED": 2, "ALL": 1, "NONE": 99}

# Fixed button order for the toolbar (identifier, label).
TIERS: tuple[tuple[str, str], ...] = (
    ("HIGH", "High"), ("MED", "High + Med"), ("ALL", "All"), ("NONE", "None"),
)


def rank(confidence: str) -> int:
    return RANK.get(confidence, 0)


def selected_by_tier(confidence: str, tier: str) -> bool:
    """Whether a row of the given confidence should be ticked for ``tier``."""
    return rank(confidence) >= TIER_MIN_RANK.get(tier, 99)


def tier_counts(confidences: Iterable[str]) -> dict[str, int]:
    """How many of ``confidences`` each tier would select — for button counts
    and tests. ``NONE`` is always 0 (it deselects)."""
    ranks = [rank(c) for c in confidences]
    return {tier: sum(1 for r in ranks if r >= TIER_MIN_RANK[tier]) for tier, _ in TIERS}
