"""Properties > Scene UI for AssetDoctor.

Everything lives under one Scene panel (ASSETDOCTOR_PT_scene_deps) now — the
old VIEW_3D N-panel (ASSETDOCTOR_PT_main and its children, plus the standalone
Report/Resource panels) was retired in Batch 5 (2026-06-23) once every feature
had a home here; see docs/TODO.md "BATCH E" / "BATCH 5"."""

from .panels import (
    ASSETDOCTOR_PG_tree_row,
    ASSETDOCTOR_PG_analyze_step,
    ASSETDOCTOR_PG_flatten_candidate,
    ASSETDOCTOR_PG_picker_row,
    ASSETDOCTOR_PG_broken_lib,
    ASSETDOCTOR_PG_dup_family,
    ASSETDOCTOR_PG_missing_block,
    ASSETDOCTOR_PG_datablock_family,
    ASSETDOCTOR_PG_material_family,
    ASSETDOCTOR_PG_geo_family,
    ASSETDOCTOR_PG_orphan_row,
    ASSETDOCTOR_PG_examine_row,
    ASSETDOCTOR_UL_tree,
    ASSETDOCTOR_UL_broken_libs,
    ASSETDOCTOR_UL_flatten_picker,
    ASSETDOCTOR_UL_missing_tex_picker,
    ASSETDOCTOR_UL_dup_tex_picker,
    ASSETDOCTOR_UL_reconnect_picker,
    ASSETDOCTOR_UL_examine_picker,
    ASSETDOCTOR_PT_scene_deps,
    ASSETDOCTOR_PT_current_file_data,
    ASSETDOCTOR_PT_analyze,
    ASSETDOCTOR_PT_analyze_external,
    ASSETDOCTOR_PT_utilities,
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
    ASSETDOCTOR_PG_tree_row,
    ASSETDOCTOR_PG_analyze_step,
    ASSETDOCTOR_PG_flatten_candidate,
    ASSETDOCTOR_PG_picker_row,
    ASSETDOCTOR_PG_broken_lib,
    ASSETDOCTOR_PG_dup_family,
    ASSETDOCTOR_PG_missing_block,
    ASSETDOCTOR_PG_datablock_family,
    ASSETDOCTOR_PG_material_family,
    ASSETDOCTOR_PG_geo_family,
    ASSETDOCTOR_PG_orphan_row,
    ASSETDOCTOR_PG_examine_row,
    ASSETDOCTOR_UL_tree,
    ASSETDOCTOR_UL_broken_libs,
    ASSETDOCTOR_UL_flatten_picker,
    ASSETDOCTOR_UL_missing_tex_picker,
    ASSETDOCTOR_UL_dup_tex_picker,
    ASSETDOCTOR_UL_reconnect_picker,
    ASSETDOCTOR_UL_examine_picker,
    ASSETDOCTOR_PT_scene_deps,
    ASSETDOCTOR_PT_current_file_data,
    ASSETDOCTOR_PT_analyze,
    ASSETDOCTOR_PT_analyze_external,
    ASSETDOCTOR_PT_utilities,
)
