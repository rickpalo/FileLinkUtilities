"""Properties > Scene UI for File & Link Utilities.

Everything lives under one Scene panel (FILELINK_PT_scene_deps) now — the
old VIEW_3D N-panel (FILELINK_PT_main and its children, plus the standalone
Report/Resource panels) was retired in Batch 5 (2026-06-23) once every feature
had a home here; see docs/TODO.md "BATCH E" / "BATCH 5"."""

from .panels import (
    FILELINK_PG_tree_row,
    FILELINK_PG_analyze_step,
    FILELINK_PG_flatten_candidate,
    FILELINK_PG_picker_row,
    FILELINK_PG_broken_lib,
    FILELINK_PG_dup_family,
    FILELINK_PG_missing_block,
    FILELINK_PG_datablock_family,
    FILELINK_PG_material_family,
    FILELINK_PG_geo_family,
    FILELINK_PG_orphan_row,
    FILELINK_PG_examine_row,
    FILELINK_UL_tree,
    FILELINK_UL_broken_libs,
    FILELINK_UL_flatten_picker,
    FILELINK_UL_missing_tex_picker,
    FILELINK_UL_dup_tex_picker,
    FILELINK_UL_reconnect_picker,
    FILELINK_UL_examine_picker,
    FILELINK_PT_scene_deps,
    FILELINK_PT_current_file_data,
    FILELINK_PT_analyze,
    FILELINK_PT_analyze_external,
    FILELINK_PT_utilities,
)

# PropertyGroup + UIList first (panels' template_list draws them, and the WM
# CollectionProperty in register() needs the PropertyGroup to exist), then the
# parent Scene panel (must register BEFORE its bl_parent_id children below),
# then its collapsible children (bl_order: Current File Data=0, Analyze This
# File=1, Analyze External Files=2, Utilities=7 — the legacy Batch-5 panels 3-6
# were folded into Analyze/Utilities one by one and deleted, Results=8 last
# of all, deleted in the Group 11 panel-consolidation pass, 2026-06-26 — see
# each remaining class for its number).
REGISTER_CLASSES = (
    FILELINK_PG_tree_row,
    FILELINK_PG_analyze_step,
    FILELINK_PG_flatten_candidate,
    FILELINK_PG_picker_row,
    FILELINK_PG_broken_lib,
    FILELINK_PG_dup_family,
    FILELINK_PG_missing_block,
    FILELINK_PG_datablock_family,
    FILELINK_PG_material_family,
    FILELINK_PG_geo_family,
    FILELINK_PG_orphan_row,
    FILELINK_PG_examine_row,
    FILELINK_UL_tree,
    FILELINK_UL_broken_libs,
    FILELINK_UL_flatten_picker,
    FILELINK_UL_missing_tex_picker,
    FILELINK_UL_dup_tex_picker,
    FILELINK_UL_reconnect_picker,
    FILELINK_UL_examine_picker,
    FILELINK_PT_scene_deps,
    FILELINK_PT_current_file_data,
    FILELINK_PT_analyze,
    FILELINK_PT_analyze_external,
    FILELINK_PT_utilities,
)
