"""Unit tests for core.analyze_steps (the Analyze-All sequence, bpy-free)."""

from core.analyze_steps import DUPLICATE_STEP_KEYS, DUPLICATE_STEPS, STEPS, step_by_key


def test_steps_have_unique_keys_and_opnames():
    keys = [s.key for s in STEPS]
    opnames = [s.opname for s in STEPS]
    assert len(keys) == len(set(keys))
    assert len(opnames) == len(set(opnames))


def test_steps_nonempty_and_well_formed():
    assert len(STEPS) == 13
    for step in STEPS:
        assert step.key and step.label and step.opname.startswith("assetdoctor.")
        assert isinstance(step.kwargs, dict)


def test_profile_render_and_folder_pickers_excluded():
    opnames = {s.opname for s in STEPS}
    assert "assetdoctor.profile_render" not in opnames
    assert "assetdoctor.scan_folder" not in opnames
    assert "assetdoctor.check_dependents" not in opnames
    assert "assetdoctor.scan_missing_datablocks" not in opnames


def test_step_by_key_found_and_missing():
    step = step_by_key("find_broken_links")
    assert step is not None
    assert step.opname == "assetdoctor.scan_broken_links"
    assert step_by_key("nonexistent") is None


def test_duplicate_steps_is_the_right_subset():
    """Item 3, 2026-06-25: "Find Duplicates" combines Materials/Geometry/
    Content/Data-blocks -- Resolution Variants stays out (a different kind
    of analysis, footprint not strict duplicates)."""
    assert {s.key for s in DUPLICATE_STEPS} == set(DUPLICATE_STEP_KEYS)
    assert len(DUPLICATE_STEPS) == 4
    assert "find_resolution_variants" not in DUPLICATE_STEP_KEYS
    # Every duplicate step is a real STEPS entry, same order as in STEPS.
    assert all(s in STEPS for s in DUPLICATE_STEPS)
