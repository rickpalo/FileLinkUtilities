"""bpy operators for File & Link Utilities (the only code allowed to import bpy besides ui/prefs).

Each operator is thin: gather bpy data -> hand to filelink.core -> show a
report -> on explicit Apply, mutate (after an auto-backup). The operators below
are scaffold stubs that register cleanly; feature logic arrives per-milestone.
"""

from .scan_folder import FILELINK_OT_scan_folder
from .dep_scan import FILELINK_OT_scan_dependencies
from .linkchain import (
    FILELINK_OT_evaluate_selected,
    FILELINK_OT_flatten_group_select_all,
    FILELINK_OT_flatten_selected,
    FILELINK_OT_scan_flatten_candidates,
    FILELINK_OT_scan_link_chains,
)
from .reversedep import FILELINK_OT_check_dependents
from .datablock_inspect import (
    FILELINK_OT_analyze_overrides,
    FILELINK_OT_scan_all_missing,
)
from .analyze_all import (
    FILELINK_OT_analyze_all,
    FILELINK_OT_find_duplicates,
    FILELINK_OT_find_flattenable_links,
)
from .select_tier import FILELINK_OT_select_by_confidence
from .relink import (
    FILELINK_OT_dup_lib_select,
    FILELINK_OT_make_selected_relative,
    FILELINK_OT_merge_duplicate_libraries,
    FILELINK_OT_normalize_library_paths,
    FILELINK_OT_relink_pick_file,
    FILELINK_OT_relink_selected,
    FILELINK_OT_scan_broken_links,
)
from .datablock_reconnect import (
    FILELINK_OT_scan_reconnect_targets,
    FILELINK_OT_reconnect_pick_source,
    FILELINK_OT_reconnect_selected,
)
from .datablock_dup import (
    FILELINK_OT_scan_datablock_dups,
    FILELINK_OT_merge_datablock_selected,
)
from .examine_library import (
    FILELINK_OT_examine_library,
    FILELINK_OT_examine_pick_source,
    FILELINK_OT_examine_search_folder,
    FILELINK_OT_examine_bulk_pick_folder,
    FILELINK_OT_examine_bulk_search_folder,
    FILELINK_OT_examine_apply_selected,
)
from .material_search import FILELINK_OT_search_material
from .image_relink import (
    FILELINK_OT_scan_broken_textures,
    FILELINK_OT_relink_folder_search,
    FILELINK_OT_search_textures_folder,
    FILELINK_OT_suggest_fuzzy_matches,
    FILELINK_OT_suggest_from_material,
    FILELINK_OT_suggest_from_blend,
    FILELINK_OT_accept_match,
    FILELINK_OT_accept_material_matches,
    FILELINK_OT_accept_all_matches,
    FILELINK_OT_point_group_at_folder,
    FILELINK_OT_relink_pick_texture,
    FILELINK_OT_relink_textures_selected,
)
from .image_dedup import (
    FILELINK_OT_scan_content_dups,
    FILELINK_OT_merge_dup_selected,
    FILELINK_OT_dup_material_keeper,
    FILELINK_OT_scan_res_variants,
    FILELINK_OT_res_variant_keep,
    FILELINK_OT_res_variant_select,
    FILELINK_OT_remove_excess_variants,
)
from .progress import FILELINK_OT_toggle_pause, FILELINK_OT_request_cancel
from .make_local import FILELINK_OT_make_local, FILELINK_OT_make_local_selected
from .material_dedup import FILELINK_OT_material_dedup, FILELINK_OT_merge_material_selected
from .material_diagnostics import (
    FILELINK_OT_check_materials,
    FILELINK_OT_delete_empty_material_slots,
)
from .deform_check import FILELINK_OT_scan_deform_issues
from .orphans import FILELINK_OT_purge_orphans_selected, FILELINK_OT_scan_orphans
from .instance_dedup import (
    FILELINK_OT_instance_geometry, FILELINK_OT_instance_geometry_selected,
)
from .resource import (
    FILELINK_OT_analyze_resources,
    FILELINK_OT_profile_render,
    FILELINK_OT_resource_sort_by,
)
from .dryrun_render import FILELINK_OT_dryrun_render
from .open_preferences import FILELINK_OT_open_preferences
from .report_store import (
    FILELINK_OT_export_report,
    FILELINK_OT_row_label,
    FILELINK_OT_row_toggle,
    FILELINK_OT_select_datablock,
    FILELINK_OT_show_linked_from,
)

REGISTER_CLASSES = (
    FILELINK_OT_scan_folder,
    FILELINK_OT_scan_dependencies,
    FILELINK_OT_scan_link_chains,
    FILELINK_OT_scan_flatten_candidates,
    FILELINK_OT_flatten_group_select_all,
    FILELINK_OT_evaluate_selected,
    FILELINK_OT_flatten_selected,
    FILELINK_OT_check_dependents,
    FILELINK_OT_analyze_overrides,
    FILELINK_OT_analyze_all,
    FILELINK_OT_find_duplicates,
    FILELINK_OT_find_flattenable_links,
    FILELINK_OT_select_by_confidence,
    FILELINK_OT_scan_all_missing,
    FILELINK_OT_scan_broken_links,
    FILELINK_OT_relink_pick_file,
    FILELINK_OT_relink_selected,
    FILELINK_OT_normalize_library_paths,
    FILELINK_OT_dup_lib_select,
    FILELINK_OT_merge_duplicate_libraries,
    FILELINK_OT_make_selected_relative,
    FILELINK_OT_scan_reconnect_targets,
    FILELINK_OT_reconnect_pick_source,
    FILELINK_OT_reconnect_selected,
    FILELINK_OT_scan_datablock_dups,
    FILELINK_OT_merge_datablock_selected,
    FILELINK_OT_examine_library,
    FILELINK_OT_examine_pick_source,
    FILELINK_OT_examine_search_folder,
    FILELINK_OT_examine_bulk_pick_folder,
    FILELINK_OT_examine_bulk_search_folder,
    FILELINK_OT_examine_apply_selected,
    FILELINK_OT_search_material,
    FILELINK_OT_scan_broken_textures,
    FILELINK_OT_relink_folder_search,
    FILELINK_OT_search_textures_folder,
    FILELINK_OT_suggest_fuzzy_matches,
    FILELINK_OT_suggest_from_material,
    FILELINK_OT_suggest_from_blend,
    FILELINK_OT_accept_match,
    FILELINK_OT_accept_material_matches,
    FILELINK_OT_accept_all_matches,
    FILELINK_OT_point_group_at_folder,
    FILELINK_OT_relink_pick_texture,
    FILELINK_OT_relink_textures_selected,
    FILELINK_OT_scan_content_dups,
    FILELINK_OT_merge_dup_selected,
    FILELINK_OT_dup_material_keeper,
    FILELINK_OT_scan_res_variants,
    FILELINK_OT_res_variant_keep,
    FILELINK_OT_res_variant_select,
    FILELINK_OT_remove_excess_variants,
    FILELINK_OT_toggle_pause,
    FILELINK_OT_request_cancel,
    FILELINK_OT_make_local,
    FILELINK_OT_make_local_selected,
    FILELINK_OT_material_dedup,
    FILELINK_OT_merge_material_selected,
    FILELINK_OT_check_materials,
    FILELINK_OT_delete_empty_material_slots,
    FILELINK_OT_scan_deform_issues,
    FILELINK_OT_scan_orphans,
    FILELINK_OT_purge_orphans_selected,
    FILELINK_OT_instance_geometry,
    FILELINK_OT_instance_geometry_selected,
    FILELINK_OT_analyze_resources,
    FILELINK_OT_profile_render,
    FILELINK_OT_resource_sort_by,
    FILELINK_OT_dryrun_render,
    FILELINK_OT_open_preferences,
    FILELINK_OT_row_label,
    FILELINK_OT_row_toggle,
    FILELINK_OT_select_datablock,
    FILELINK_OT_show_linked_from,
    FILELINK_OT_export_report,
)
