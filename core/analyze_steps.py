"""Phase 3a — the ordered list of "look for problems in the CURRENT file" checks
that the Analyze section's "Analyze All" button steps through (bpy-free, just
data + tests, so the running order is reviewable without Blender).

Each step names a real operator id (``ops.analyze_all`` dispatches it via
``getattr(bpy.ops, category)`` + ``getattr(..., name)``, never imports the ops
module here, keeping this file bpy-free per the project's architecture rule)
plus the keyword args that put it in report-only mode where it has one.

Deliberately NOT included: Project Link Map / Safe to Delete (need a
user-supplied path first, not a one-click current-file scan) and Profile
Render (an actual render to measure peak RAM — too slow/disruptive to fire
unattended in a sequencer; stays a manual-only button in the Analyze panel).
"Find Missing Data-blocks" was folded into "Find Reconnectable Data-blocks"
(same underlying scan; the Reconnect list is a strict superset) rather than
listed separately — see docs/TODO.md 2026-06-25.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalyzeStep:
    key: str
    label: str
    opname: str  # "filelink.scan_x" -> bpy.ops.filelink.scan_x(**kwargs)
    kwargs: dict


STEPS: tuple[AnalyzeStep, ...] = (
    AnalyzeStep("check_link_chain", "Check Link Chain", "filelink.scan_dependencies", {}),
    AnalyzeStep("audit_file", "Audit This File", "filelink.analyze_overrides", {}),
    AnalyzeStep("find_flattenable_chains", "Find Flattenable Link Chains",
                "filelink.scan_link_chains", {}),
    AnalyzeStep("find_flattenable_characters", "Group Flattenable Characters",
                "filelink.scan_flatten_candidates", {}),
    AnalyzeStep("find_duplicate_datablocks", "Find Duplicate Data-blocks",
                "filelink.scan_datablock_dups", {}),
    AnalyzeStep("find_broken_links", "Find Broken Library Links", "filelink.scan_broken_links", {}),
    AnalyzeStep("find_reconnectable", "Find Reconnectable Data-blocks",
                "filelink.scan_reconnect_targets", {}),
    AnalyzeStep("check_library_paths", "Check Library Paths",
                "filelink.normalize_library_paths", {"apply": False}),
    AnalyzeStep("find_missing_textures", "Find Missing Textures",
                "filelink.scan_broken_textures", {}),
    AnalyzeStep("find_duplicate_materials", "Find Duplicate Materials",
                "filelink.material_dedup", {"apply": False}),
    AnalyzeStep("find_duplicate_geometry", "Find Duplicate Geometry",
                "filelink.instance_geometry", {"apply": False}),
    AnalyzeStep("find_orphans", "Find Orphans", "filelink.scan_orphans",
                {"purge_orphans": False}),
    AnalyzeStep("find_duplicate_content", "Find Duplicate Content",
                "filelink.scan_content_dups", {}),
    AnalyzeStep("find_resolution_variants", "Find Resolution Variants",
                "filelink.scan_res_variants", {}),
    AnalyzeStep("analyze_memory_disk", "Analyze Memory/Disk",
                "filelink.analyze_resources", {}),
)


def step_by_key(key: str) -> AnalyzeStep | None:
    for step in STEPS:
        if step.key == key:
            return step
    return None


# Item 3, 2026-06-25: "Find Duplicates" combines the duplicate-detection scans
# (Find Duplicate Materials/Geometry/Content folded into Find Duplicate
# Data-blocks) into one trigger — same dispatcher, just this subset of STEPS.
# Resolution Variants is its OWN scan (different — multi-res footprint, not
# strictly "duplicates") and stays out, per the user's own scoping.
DUPLICATE_STEP_KEYS = (
    "find_duplicate_datablocks", "find_duplicate_materials",
    "find_duplicate_geometry", "find_duplicate_content",
)
DUPLICATE_STEPS: tuple[AnalyzeStep, ...] = tuple(
    s for s in STEPS if s.key in DUPLICATE_STEP_KEYS
)


# 2026-06-26: "Find Flattenable Link Chains" and "Find Flattenable Characters"
# merged into one "Find Flattenable Links" trigger (docs/TODO.md #41) — the
# second step always needs the first step's f7chain data, so they always ran
# back-to-back anyway; this just removes the manual two-click requirement.
FLATTEN_STEP_KEYS = ("find_flattenable_chains", "find_flattenable_characters")
FLATTEN_STEPS: tuple[AnalyzeStep, ...] = tuple(
    s for s in STEPS if s.key in FLATTEN_STEP_KEYS
)


# docs/TODO.md #22 — Automated Cleanup, redesigned to a Scan -> Review ->
# Apply Selected flow. Deliberately a SEPARATE, small step list rather than a
# STEPS subset (unlike DUPLICATE_STEPS/FLATTEN_STEPS above): Make Local's
# scan is intentionally excluded from the main "Analyze All" run (it's a
# footprint/impact measurement, not a "look for problems" check — see this
# module's own docstring), but it IS one of the 4 cleanup functions, so it
# needs its own entry here.
CLEANUP_SCAN_STEPS: tuple[AnalyzeStep, ...] = (
    AnalyzeStep("cleanup_make_local", "Make Local", "filelink.make_local", {"apply": False}),
    AnalyzeStep("cleanup_materials", "Duplicate Materials", "filelink.material_dedup",
                {"apply": False}),
    AnalyzeStep("cleanup_geometry", "Duplicate Geometry", "filelink.instance_geometry",
                {"apply": False}),
    AnalyzeStep("cleanup_orphans", "Orphans", "filelink.scan_orphans", {"purge_orphans": False}),
)

# The ticked-selection apply counterpart to each CLEANUP_SCAN_STEPS entry —
# same ``key``s (so a single include-toggle filter works for both scan and
# apply), different (real, already-existing except Make Local's) operator.
CLEANUP_APPLY_STEPS: tuple[AnalyzeStep, ...] = (
    AnalyzeStep("cleanup_make_local", "Make Local", "filelink.make_local_selected", {}),
    AnalyzeStep("cleanup_materials", "Duplicate Materials", "filelink.merge_material_selected",
                {}),
    AnalyzeStep("cleanup_geometry", "Duplicate Geometry", "filelink.instance_geometry_selected",
                {}),
    AnalyzeStep("cleanup_orphans", "Orphans", "filelink.purge_orphans_selected", {}),
)


__all__ = ["AnalyzeStep", "STEPS", "step_by_key", "DUPLICATE_STEP_KEYS", "DUPLICATE_STEPS",
           "FLATTEN_STEP_KEYS", "FLATTEN_STEPS", "CLEANUP_SCAN_STEPS", "CLEANUP_APPLY_STEPS"]
