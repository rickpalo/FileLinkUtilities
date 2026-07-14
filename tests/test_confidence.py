"""Unit tests for core.confidence (the shared tier ladder, bpy-free)."""

from core.confidence import rank, selected_by_tier, tier_counts


def test_rank_maps_both_vocabularies():
    # reconnect terms and texture terms land on the same ladder
    assert rank("exact") == rank("high") == 3
    assert rank("numbered") == 3
    assert rank("fuzzy") == rank("medium") == 2
    assert rank("low") == 1
    assert rank("none") == rank("") == 0
    assert rank("bogus") == 0  # unknown never auto-picks


def test_selected_by_tier_thresholds():
    assert selected_by_tier("exact", "HIGH")
    assert not selected_by_tier("fuzzy", "HIGH")
    assert selected_by_tier("fuzzy", "MED")
    assert not selected_by_tier("low", "MED")
    assert selected_by_tier("low", "ALL")
    assert not selected_by_tier("none", "ALL")  # no candidate is never selected
    for term in ("exact", "fuzzy", "low", "none"):
        assert not selected_by_tier(term, "NONE")  # NONE clears everything


def test_tier_counts():
    confs = ["exact", "numbered", "fuzzy", "low", "none"]
    counts = tier_counts(confs)
    assert counts["HIGH"] == 2   # exact + numbered
    assert counts["MED"] == 3    # + fuzzy
    assert counts["ALL"] == 4    # + low (none excluded)
    assert counts["NONE"] == 0
