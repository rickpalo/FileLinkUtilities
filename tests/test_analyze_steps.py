"""Unit tests for core.analyze_steps (the Analyze-All sequence, bpy-free)."""

from core.analyze_steps import (
    DUPLICATE_STEP_KEYS,
    DUPLICATE_STEPS,
    FLATTEN_STEP_KEYS,
    FLATTEN_STEPS,
    STEPS,
    step_by_key,
)


def test_steps_have_unique_keys_and_opnames():
    keys = [s.key for s in STEPS]
    opnames = [s.opname for s in STEPS]
    assert len(keys) == len(set(keys))
    assert len(opnames) == len(set(opnames))


def test_steps_nonempty_and_well_formed():
    assert len(STEPS) == 15
    for step in STEPS:
        assert step.key and step.label and step.opname.startswith("filelink.")
        assert isinstance(step.kwargs, dict)


def test_profile_render_and_folder_pickers_excluded():
    opnames = {s.opname for s in STEPS}
    assert "filelink.profile_render" not in opnames
    assert "filelink.scan_folder" not in opnames
    assert "filelink.check_dependents" not in opnames
    assert "filelink.scan_missing_datablocks" not in opnames


def test_step_by_key_found_and_missing():
    step = step_by_key("find_broken_links")
    assert step is not None
    assert step.opname == "filelink.scan_broken_links"
    assert step_by_key("nonexistent") is None


def test_check_library_paths_step_is_report_only():
    """Group 11 #43, 2026-06-26: Path Normalization gained an Analyze trigger
    (it previously had none) -- must report-only, like every other check."""
    step = step_by_key("check_library_paths")
    assert step is not None
    assert step.opname == "filelink.normalize_library_paths"
    assert step.kwargs == {"apply": False}


def test_duplicate_steps_is_the_right_subset():
    """Item 3, 2026-06-25: "Find Duplicates" combines Materials/Geometry/
    Content/Data-blocks -- Resolution Variants stays out (a different kind
    of analysis, footprint not strict duplicates)."""
    assert {s.key for s in DUPLICATE_STEPS} == set(DUPLICATE_STEP_KEYS)
    assert len(DUPLICATE_STEPS) == 4
    assert "find_resolution_variants" not in DUPLICATE_STEP_KEYS
    # Every duplicate step is a real STEPS entry, same order as in STEPS.
    assert all(s in STEPS for s in DUPLICATE_STEPS)


def test_flatten_steps_is_the_right_subset():
    """2026-06-26 (docs/TODO.md #41): "Find Flattenable Link Chains" and
    "Find Flattenable Characters" merged into one "Find Flattenable Links"
    trigger -- same dispatcher pattern as Find Duplicates."""
    assert {s.key for s in FLATTEN_STEPS} == set(FLATTEN_STEP_KEYS)
    assert len(FLATTEN_STEPS) == 2
    assert all(s in STEPS for s in FLATTEN_STEPS)
    # Order matters: the grouping step needs the chain step's f7chain data
    # already stashed, so it must run second, not just be "in the set".
    assert [s.key for s in FLATTEN_STEPS] == [
        "find_flattenable_chains", "find_flattenable_characters"]
