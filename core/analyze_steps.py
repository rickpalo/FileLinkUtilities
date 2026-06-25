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
    opname: str  # "assetdoctor.scan_x" -> bpy.ops.assetdoctor.scan_x(**kwargs)
    kwargs: dict


STEPS: tuple[AnalyzeStep, ...] = (
    AnalyzeStep("check_link_chain", "Check Link Chain", "assetdoctor.scan_dependencies", {}),
    AnalyzeStep("audit_file", "Audit This File", "assetdoctor.analyze_overrides", {}),
    AnalyzeStep("find_flattenable_chains", "Find Flattenable Link Chains",
                "assetdoctor.scan_link_chains", {}),
    AnalyzeStep("find_duplicate_datablocks", "Find Duplicate Data-blocks",
                "assetdoctor.scan_datablock_dups", {}),
    AnalyzeStep("find_broken_links", "Find Broken Links", "assetdoctor.scan_broken_links", {}),
    AnalyzeStep("find_reconnectable", "Find Reconnectable Data-blocks",
                "assetdoctor.scan_reconnect_targets", {}),
    AnalyzeStep("find_missing_textures", "Find Missing Textures",
                "assetdoctor.scan_broken_textures", {}),
    AnalyzeStep("find_duplicate_materials", "Find Duplicate Materials",
                "assetdoctor.material_dedup", {"apply": False}),
    AnalyzeStep("find_duplicate_geometry", "Find Duplicate Geometry",
                "assetdoctor.instance_geometry", {"apply": False}),
    AnalyzeStep("find_orphans", "Find Orphans", "assetdoctor.scan_orphans",
                {"purge_orphans": False}),
    AnalyzeStep("find_duplicate_content", "Find Duplicate Content",
                "assetdoctor.scan_content_dups", {}),
    AnalyzeStep("find_resolution_variants", "Find Resolution Variants",
                "assetdoctor.scan_res_variants", {}),
    AnalyzeStep("analyze_memory_disk", "Analyze Memory/Disk",
                "assetdoctor.analyze_resources", {}),
)


def step_by_key(key: str) -> AnalyzeStep | None:
    for step in STEPS:
        if step.key == key:
            return step
    return None


__all__ = ["AnalyzeStep", "STEPS", "step_by_key"]
