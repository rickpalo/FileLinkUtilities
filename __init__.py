"""File & Link Utilities — Blender 5+ asset dependency & dedup addon.

Top-level registration. Keep this file thin: it only wires up the operator,
panel and preferences classes plus a couple of Scene properties. All real logic
lives in ``core`` (bpy-free, unit-testable) and ``ops`` (thin bpy operators that
call into ``core``).

bpy-dependent submodules are imported *lazily inside register()* so that simply
importing this package (e.g. during pytest collection, outside Blender) never
pulls in ``bpy``. See docs/ARCHITECTURE.md.
"""

# Populated by register(); used by unregister() to tear down in reverse order.
_REGISTERED: list = []
_load_post_handler = None  # the persistent load_post callback, for unregister


def _debug_update(self, context):
    """Scene 'Enable Debug Log' toggle callback."""
    import bpy

    from .log import set_debug_enabled

    set_debug_enabled(self.filelink_debug_log, bpy.data.filepath)


def _debug_log_on_load(_dummy):
    """On opening a file with the debug toggle on, start a FRESH log for it.

    The Scene-prop ``update`` callback doesn't fire on load, so without this an
    enabled toggle wouldn't reactivate after opening a file."""
    import bpy

    from .log import set_debug_enabled

    scene = bpy.context.scene
    if scene and getattr(scene, "filelink_debug_log", False):
        set_debug_enabled(False)  # detach any stale handler
        set_debug_enabled(True, bpy.data.filepath)  # fresh log for the opened file


def register() -> None:
    import bpy

    from . import prefs
    from .ops import REGISTER_CLASSES as op_classes
    from .ui import REGISTER_CLASSES as ui_classes

    # Order matters: preferences first, then operators, then panels.
    classes = (prefs.FileLinkPreferences, *op_classes, *ui_classes)
    for cls in classes:
        bpy.utils.register_class(cls)
        _REGISTERED.append(cls)

    bpy.types.Scene.filelink_scan_dir = bpy.props.StringProperty(
        name="Project Folder",
        description="Folder to recursively scan for .blend link relationships",
        subtype="DIR_PATH",
        default="",
    )
    bpy.types.Scene.filelink_dep_target = bpy.props.StringProperty(
        name="File to check",
        description="The .blend you're considering deleting — the reverse-dependency "
        "check scans the Project Folder above and lists who links TO this file",
        subtype="FILE_PATH",
        default="",
    )
    bpy.types.Scene.filelink_material_search_pattern = bpy.props.StringProperty(
        name="Material Name",
        description="Material name to search for under the Project Folder above — plain text "
        "matches as a substring, or use wildcards (* ? [ ]) for a glob match",
        default="",
    )
    bpy.types.Scene.filelink_debug_log = bpy.props.BoolProperty(
        name="Enable Debug Log",
        description="Write FileLinkDebugLog.txt next to the .blend (or Blender's temp folder "
        "if unsaved) capturing detailed activity, to help diagnose issues. A fresh log starts "
        "each time it's enabled or a file is opened",
        default=False,
        update=_debug_update,
    )

    global _load_post_handler
    from bpy.app.handlers import persistent

    _load_post_handler = persistent(_debug_log_on_load)
    bpy.app.handlers.load_post.append(_load_post_handler)

    # Live progress for any modal operation (folder scan, make-local, …) shown as
    # one shared progress bar at the top of the panel. See ops.progress.
    bpy.types.WindowManager.filelink_op_active = bpy.props.BoolProperty(default=False)
    bpy.types.WindowManager.filelink_op_progress = bpy.props.FloatProperty(
        default=0.0, min=0.0, max=1.0
    )
    bpy.types.WindowManager.filelink_op_status = bpy.props.StringProperty(default="")
    # Pause flag for the running modal op (held between steps; ESC still cancels).
    bpy.types.WindowManager.filelink_op_paused = bpy.props.BoolProperty(default=False)
    # Cancel flag, set by the panel's Cancel button; the modal stops at the next step.
    bpy.types.WindowManager.filelink_op_cancel = bpy.props.BoolProperty(default=False)
    # Sticky last-result line: unlike the transient self.report() toast (gone once
    # you move the mouse) or the progress bar (hidden once the op finishes), this
    # STAYS in the panel until the next action overwrites it — user feedback
    # (2026-06-24): Reconnect Selected gave no in-panel confirmation of what
    # happened. See ops.progress.set_result.
    bpy.types.WindowManager.filelink_last_result = bpy.props.StringProperty(default="")
    bpy.types.WindowManager.filelink_last_result_ok = bpy.props.BoolProperty(default=True)
    # Persistent click-to-select outcome per datablock (JSON dict, "Type/Name" ->
    # "found"/"no_user"/"unresolved"), docs/TODO.md Group 10 #37 (2026-07-04) — lets
    # a row show a STICKY outcome icon instead of relying on a one-shot toast.
    bpy.types.WindowManager.filelink_select_outcomes = bpy.props.StringProperty(default="")

    # Persistent per-feature reports: data JSON + expanded keys per feature, plus
    # the currently-shown feature key. See ops/report_store.FEATURES.
    from .ops.report_store import FEATURES

    for key, _label in FEATURES:
        setattr(bpy.types.WindowManager, f"filelink_rep_{key}",
                bpy.props.StringProperty(default=""))
        setattr(bpy.types.WindowManager, f"filelink_repx_{key}",
                bpy.props.StringProperty(default=""))
    bpy.types.WindowManager.filelink_active_report = bpy.props.StringProperty(default="")

    # F5 resource tree (JSON) + its expanded node keys.
    bpy.types.WindowManager.filelink_resource_tree = bpy.props.StringProperty(default="")
    bpy.types.WindowManager.filelink_resource_expanded = bpy.props.StringProperty(default="")
    # Estimated RAM/VRAM/disk totals from the last Analyze Memory/Disk run
    # (human-readable string), persisted so the Analyze button's inline
    # summary survives after the operator-report popup fades.
    bpy.types.WindowManager.filelink_resource_totals = bpy.props.StringProperty(default="")
    # Real peak RAM from the last Profile Render (human-readable string).
    bpy.types.WindowManager.filelink_profiled_ram = bpy.props.StringProperty(default="")
    # docs/TODO.md #15 (2026-06-27): the last scan's raw per-datablock items
    # (JSON), cached so clicking a column header can cheaply re-sort/re-group
    # without re-walking bpy.data; the chosen sort column persists too.
    bpy.types.WindowManager.filelink_resource_items_json = bpy.props.StringProperty(default="")
    bpy.types.WindowManager.filelink_resource_sort = bpy.props.EnumProperty(
        items=[("ram", "RAM", ""), ("vram", "VRAM", ""), ("disk", "Disk", "")], default="ram")

    # Materialised, flattened tree rows that the Report/Resource UILists draw
    # (virtualized + scrollable — fixes blank rows on large reports). Rebuilt by
    # ops.report_store from the JSON above whenever a report or its expansion
    # changes. WM-scoped (ephemeral), matching the report JSON's lifetime.
    from .ui.panels import (FILELINK_PG_analyze_step, FILELINK_PG_broken_lib,
                            FILELINK_PG_datablock_family, FILELINK_PG_deform_row,
                            FILELINK_PG_dup_family,
                            FILELINK_PG_examine_row, FILELINK_PG_flatten_candidate,
                            FILELINK_PG_geo_family, FILELINK_PG_makelocal_row,
                            FILELINK_PG_material_family,
                            FILELINK_PG_missing_block, FILELINK_PG_orphan_row,
                            FILELINK_PG_picker_row, FILELINK_PG_tree_row)

    bpy.types.WindowManager.filelink_report_rows = bpy.props.CollectionProperty(
        type=FILELINK_PG_tree_row)
    bpy.types.WindowManager.filelink_report_index = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.filelink_resource_rows = bpy.props.CollectionProperty(
        type=FILELINK_PG_tree_row)
    bpy.types.WindowManager.filelink_resource_index = bpy.props.IntProperty(default=0)

    # Check Armature Deformation (Group 16, 2026-07-09): one selectable row per
    # flagged object. See ops.deform_check.
    bpy.types.WindowManager.filelink_deform_rows = bpy.props.CollectionProperty(
        type=FILELINK_PG_deform_row)
    bpy.types.WindowManager.filelink_deform_index = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.filelink_deform_scanned = bpy.props.BoolProperty(default=False)

    # Group 12 Phase 4: one small virtualized rows collection PER inline-detail
    # feature (ops.report_store.INLINE_DETAIL_FEATURES) — several of these can
    # be expanded simultaneously in the Analyze panel, unlike the Reports tab's
    # single active-feature collection above.
    from .ops.report_store import INLINE_DETAIL_FEATURES

    for _feature in INLINE_DETAIL_FEATURES:
        setattr(bpy.types.WindowManager, f"filelink_inline_rows_{_feature}",
                bpy.props.CollectionProperty(type=FILELINK_PG_tree_row))
        setattr(bpy.types.WindowManager, f"filelink_inline_active_{_feature}",
                bpy.props.IntProperty(default=0))

    # F7 per-link relink list: the current file's broken/missing library links,
    # each with a relink target + a per-row checkbox. See ops.relink.
    bpy.types.WindowManager.filelink_broken_libs = bpy.props.CollectionProperty(
        type=FILELINK_PG_broken_lib)
    bpy.types.WindowManager.filelink_broken_index = bpy.props.IntProperty(default=0)
    # F6 per-texture relink list: the current file's missing image textures (same
    # row shape, reusing FILELINK_PG_broken_lib). See ops.image_relink.
    bpy.types.WindowManager.filelink_broken_imgs = bpy.props.CollectionProperty(
        type=FILELINK_PG_broken_lib)
    bpy.types.WindowManager.filelink_broken_imgs_index = bpy.props.IntProperty(default=0)
    # Group 12 Phase 3: virtualized picker rows for Missing Textures (rebuilt by
    # ops.image_relink.rebuild_missing_tex_picker_rows after scan/pick/accept/relink).
    bpy.types.WindowManager.filelink_missingtex_picker_rows = bpy.props.CollectionProperty(
        type=FILELINK_PG_picker_row)
    bpy.types.WindowManager.filelink_missingtex_picker_active = bpy.props.IntProperty(default=0)
    # F6 read-only companion list: missing textures whose Image is LINKED (owned by
    # another library) — can't be relinked from here, but the user asked for them
    # to be visible (a render-time dry run found far more missing images than this
    # scan counted, because linked images were silently excluded). See
    # ops.image_relink._gather_linked_missing_images.
    bpy.types.WindowManager.filelink_linked_missing_imgs = bpy.props.CollectionProperty(
        type=FILELINK_PG_broken_lib)
    # Items 6/7/11, 2026-06-25: three more actionable lists, all reusing the
    # same generic row shape. See ops.relink (items 6/7) / ops.image_dedup
    # (item 11). None use a template_list, so no "active index" prop needed.
    bpy.types.WindowManager.filelink_dup_lib_members = bpy.props.CollectionProperty(
        type=FILELINK_PG_broken_lib)  # item 6: duplicate-library-path groups
    bpy.types.WindowManager.filelink_abs_path_members = bpy.props.CollectionProperty(
        type=FILELINK_PG_broken_lib)  # item 7: absolute-path rows grouped by drive
    bpy.types.WindowManager.filelink_res_variant_members = bpy.props.CollectionProperty(
        type=FILELINK_PG_broken_lib)  # item 11: resolution-variant rows grouped by texture set
    # F6 B1: how the missing-texture categories group (by original folder or by
    # the material that uses each texture).
    bpy.types.WindowManager.filelink_tex_group_by = bpy.props.EnumProperty(
        name="Group by",
        items=[("DIR", "Folder", "Group by each texture's original folder"),
               ("MATERIAL", "Material", "Group by the material that uses each texture "
                "(use when the original folder is gone)")],
        default="MATERIAL")
    # Missing-texture section state: whether a scan has run (drives the header
    # summary), the count at scan time (so "found" = initial − still-missing), and
    # the expanded category keys (newline-joined) for the collapsible list.
    bpy.types.WindowManager.filelink_tex_scanned = bpy.props.BoolProperty(default=False)
    bpy.types.WindowManager.filelink_tex_initial_missing = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.filelink_tex_expanded = bpy.props.StringProperty(default="")
    # B4 — eyedropper source: pick a material whose (on-disk) textures become the
    # candidate corpus for proposing matches to the still-unplaced missing textures.
    bpy.types.WindowManager.filelink_tex_source_material = bpy.props.PointerProperty(
        type=bpy.types.Material,
        name="Source material",
        description="A material whose existing textures are offered as substitutes for "
        "the missing ones (matched by name) — staged as Possible Matches, never applied")

    # F6 Layer 2 — redesigned Duplicate Materials/Textures list: one row per content-
    # identical .NNN family (with a keeper dropdown), grouped by material; plus the
    # scan state + summary counts that drive the inline header (no separate report).
    bpy.types.WindowManager.filelink_dup_families = bpy.props.CollectionProperty(
        type=FILELINK_PG_dup_family)
    bpy.types.WindowManager.filelink_dup_index = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.filelink_dup_scanned = bpy.props.BoolProperty(default=False)
    bpy.types.WindowManager.filelink_dup_expanded = bpy.props.StringProperty(default="")
    bpy.types.WindowManager.filelink_dup_removable = bpy.props.IntProperty(default=0)
    # 2026-07-14: redundant members that are LINKED (scan now includes linked
    # images) — reported, never merged; tracked apart from filelink_dup_removable
    # so that count stays an honest "what Merge Selected will actually remove".
    bpy.types.WindowManager.filelink_dup_linked = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.filelink_dup_conflicts = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.filelink_dup_conflicts_text = bpy.props.StringProperty(default="")
    # Group 12 Phase 3 item 2: virtualized picker rows for Duplicate Textures
    # (rebuilt by ops.image_dedup.rebuild_dup_tex_picker_rows after scan/merge/
    # toggle, and by material_override's own update callback).
    bpy.types.WindowManager.filelink_duptex_picker_rows = bpy.props.CollectionProperty(
        type=FILELINK_PG_picker_row)
    bpy.types.WindowManager.filelink_duptex_picker_active = bpy.props.IntProperty(default=0)

    # Batch 3 reverse-dep check: a small verdict the panel colors without having
    # to re-parse the stashed f7rev report JSON on every redraw. "" = not run yet.
    bpy.types.WindowManager.filelink_dep_verdict = bpy.props.StringProperty(default="")
    bpy.types.WindowManager.filelink_dep_verdict_text = bpy.props.StringProperty(default="")

    # Batch C #2: missing-data-block RECONNECT list. Rows group by their broken/
    # renamed source library; ops.datablock_reconnect fills/enumerates/applies it.
    bpy.types.WindowManager.filelink_missing_blocks = bpy.props.CollectionProperty(
        type=FILELINK_PG_missing_block)
    bpy.types.WindowManager.filelink_missing_index = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.filelink_missing_scanned = bpy.props.BoolProperty(default=False)
    bpy.types.WindowManager.filelink_missing_expanded = bpy.props.StringProperty(default="")
    # Group 12 Phase 3 item 3: virtualized picker rows for Datablock Reconnect
    # (rebuilt by ops.datablock_reconnect.rebuild_reconnect_picker_rows after
    # scan/pick-source/reconnect-selected).
    bpy.types.WindowManager.filelink_reconnect_picker_rows = bpy.props.CollectionProperty(
        type=FILELINK_PG_picker_row)
    bpy.types.WindowManager.filelink_reconnect_picker_active = bpy.props.IntProperty(default=0)

    # Batch C #3: generic Duplicate Data-blocks list (any type, via ID.user_remap).
    bpy.types.WindowManager.filelink_datablock_families = bpy.props.CollectionProperty(
        type=FILELINK_PG_datablock_family)
    bpy.types.WindowManager.filelink_datablock_index = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.filelink_datablock_scanned = bpy.props.BoolProperty(default=False)
    bpy.types.WindowManager.filelink_datablock_removable = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.filelink_datablock_conflicts = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.filelink_datablock_conflicts_text = bpy.props.StringProperty(default="")
    bpy.types.WindowManager.filelink_datablock_skipped_text = bpy.props.StringProperty(default="")
    bpy.types.WindowManager.filelink_datablock_expanded = bpy.props.StringProperty(default="")

    # F3 reformat (user feedback, 2026-06-25): Find Duplicate Materials gets the
    # same keeper-dropdown/Merge Selected shape as the other dedup tools instead
    # of a single blind "Dedup & Remap (Apply)" button.
    bpy.types.WindowManager.filelink_mat_families = bpy.props.CollectionProperty(
        type=FILELINK_PG_material_family)
    bpy.types.WindowManager.filelink_mat_index = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.filelink_mat_scanned = bpy.props.BoolProperty(default=False)
    bpy.types.WindowManager.filelink_mat_removable = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.filelink_mat_linked = bpy.props.IntProperty(default=0)
    # Find Duplicates display unification (docs/TODO.md #16, 2026-06-27): same-
    # name-family materials that didn't merge cleanly, kept separate.
    bpy.types.WindowManager.filelink_mat_conflicts = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.filelink_mat_conflicts_text = bpy.props.StringProperty(default="")

    # Group 11 #44 (2026-06-26): Find Duplicate Geometry gets the same
    # selective checkbox/Instance-Selected shape as the other dedup tools,
    # instead of the old blunt "Instance & Merge (Apply everything)" button.
    bpy.types.WindowManager.filelink_geo_families = bpy.props.CollectionProperty(
        type=FILELINK_PG_geo_family)
    bpy.types.WindowManager.filelink_geo_index = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.filelink_geo_scanned = bpy.props.BoolProperty(default=False)
    bpy.types.WindowManager.filelink_geo_removable = bpy.props.IntProperty(default=0)
    # docs/TODO.md #21 (2026-06-27): linked victims that stay in their library
    # (only their local users get repointed) -- tracked separately from
    # filelink_geo_removable, mirroring core.f3_materials' linked accounting.
    bpy.types.WindowManager.filelink_geo_linked = bpy.props.IntProperty(default=0)
    # Find Duplicates display unification (docs/TODO.md #16, 2026-06-27): same-
    # name-family meshes that didn't merge cleanly, kept separate.
    bpy.types.WindowManager.filelink_geo_conflicts = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.filelink_geo_conflicts_text = bpy.props.StringProperty(default="")

    # Group 11 #45 (2026-06-26): Find Orphans gets a checkbox/Purge-Selected
    # shape for TRUE orphans (no keeper — purge is binary). Fake-user-only and
    # identical-cluster findings stay read-only, drawn straight from the f4
    # report (deliberate, existing design — see ops.orphans).
    bpy.types.WindowManager.filelink_orphan_rows = bpy.props.CollectionProperty(
        type=FILELINK_PG_orphan_row)
    bpy.types.WindowManager.filelink_orphan_index = bpy.props.IntProperty(default=0)
    # 2026-07-04: datablocks skipped during fingerprinting because reading them
    # risked a native crash (missing placeholder / Library Override) — see
    # ops.orphans._gather_steps / extract.datablock_risk_reason.
    bpy.types.WindowManager.filelink_orphan_skipped_text = bpy.props.StringProperty(default="")

    # docs/TODO.md #22: Make Local gets the same actionable checkbox shape as
    # Materials/Geometry/Orphans, one row per LINKED DATABLOCK (flat, not
    # grouped by library — see FILELINK_PG_makelocal_row's docstring).
    bpy.types.WindowManager.filelink_makelocal_rows = bpy.props.CollectionProperty(
        type=FILELINK_PG_makelocal_row)
    bpy.types.WindowManager.filelink_makelocal_active = bpy.props.IntProperty(default=0)

    # docs/TODO.md #22 — Find Material Across Files: unreadable/corrupt files
    # hit during the folder walk, same "skipped, unsafe to read" convention
    # as ops.orphans.
    bpy.types.WindowManager.filelink_matsearch_skipped_text = bpy.props.StringProperty(default="")

    # Examine Library: retarget AWAY from a chosen (working) library.
    bpy.types.WindowManager.filelink_examine_library_pick = bpy.props.StringProperty(
        name="Library", description="The library to examine (prop_search over bpy.data.libraries)")
    bpy.types.WindowManager.filelink_examine_library = bpy.props.StringProperty(default="")
    bpy.types.WindowManager.filelink_examine_rows = bpy.props.CollectionProperty(
        type=FILELINK_PG_examine_row)
    bpy.types.WindowManager.filelink_examine_index = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.filelink_examine_scanned = bpy.props.BoolProperty(default=False)
    bpy.types.WindowManager.filelink_examine_expanded = bpy.props.StringProperty(default="")
    # Persistent post-apply result (docs/TODO.md, 2026-07-09): Apply Selected
    # clears filelink_examine_rows on success, which used to also wipe every
    # trace of what just happened from the panel -- the one-shot toast was the
    # only feedback, and a user who missed it (or scrolled away) had no way to
    # tell whether anything actually got remapped. Survives the rows-clear;
    # replaced by the next Examine or Apply Selected call.
    bpy.types.WindowManager.filelink_examine_apply_summary = bpy.props.StringProperty(default="")
    # Group 12 Phase 3 item 4: virtualized picker rows for Examine Library
    # (rebuilt by ops.examine_library.rebuild_examine_picker_rows after
    # Examine/Apply Selected).
    bpy.types.WindowManager.filelink_examine_picker_rows = bpy.props.CollectionProperty(
        type=FILELINK_PG_picker_row)
    bpy.types.WindowManager.filelink_examine_picker_active = bpy.props.IntProperty(default=0)

    # Phase 3a — Analyze section's "Analyze All" sequencer: per-step status
    # (pending/running/done/error), rebuilt by ops.analyze_all at the start of
    # each run so the panel can show a per-step icon while it works.
    bpy.types.WindowManager.filelink_analyze_steps = bpy.props.CollectionProperty(
        type=FILELINK_PG_analyze_step)
    bpy.types.WindowManager.filelink_analyze_index = bpy.props.IntProperty(default=0)

    # F7 Phase 4-B: the character picker for Build Flatten Plan. Scanning caches
    # every candidate's full plan as JSON (filelink_flatten_plans_json) so
    # picking one row later doesn't require rescanning the whole file. See
    # ops.linkchain.
    bpy.types.WindowManager.filelink_flatten_candidates = bpy.props.CollectionProperty(
        type=FILELINK_PG_flatten_candidate)
    bpy.types.WindowManager.filelink_flatten_index = bpy.props.IntProperty(default=0)
    # Group 12 Phase 2: virtualized picker rows (rebuilt by ops.linkchain.
    # rebuild_flatten_picker_rows after every scan/toggle/evaluate/flatten).
    bpy.types.WindowManager.filelink_flatten_picker_rows = bpy.props.CollectionProperty(
        type=FILELINK_PG_picker_row)
    bpy.types.WindowManager.filelink_flatten_picker_active = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.filelink_flatten_plans_json = bpy.props.StringProperty(default="")
    # Full per-file object hierarchy census (core.linkchain.posing_list_to_dict),
    # cached by Find Flattenable Link Chains so the picker can resolve each
    # remote character's rig (parent/Armature-modifier/Hook-modifier/Child-Of-
    # constraint relationships) without re-scanning every file -- 2026-06-27
    # redesign, docs/TODO.md.
    bpy.types.WindowManager.filelink_flatten_hierarchy_json = bpy.props.StringProperty(default="")
    # Which rig/character groups are expanded in the picker (newline-joined
    # rig names), mirroring every other collapsible-group list in this addon.
    bpy.types.WindowManager.filelink_flatten_expanded = bpy.props.StringProperty(default="")
    # Set when a scan finds zero LOCAL candidates but Find Flattenable Link
    # Chains already found some elsewhere in the chain — "" otherwise.
    bpy.types.WindowManager.filelink_flatten_remote_note = bpy.props.StringProperty(default="")

    # Flatten v2 (docs/TODO.md Group 11 #47). Per-group selection is tracked
    # as DESELECTED keys (newline-joined) -- absence means selected, so every
    # group starts checked by default without needing to pre-populate a set.
    bpy.types.WindowManager.filelink_flatten_deselected = bpy.props.StringProperty(default="")
    # The single shared Make Local / Make Copy toggle pair on the
    # "Flattenable overrides" subgroup's own title line (not per-character).
    bpy.types.WindowManager.filelink_flatten_make_local = bpy.props.BoolProperty(default=False)
    bpy.types.WindowManager.filelink_flatten_make_copy = bpy.props.BoolProperty(default=True)
    # Persistent outcome counts so the subgroup title AND the top overview
    # line can both show "AA of YY flattenable" after every Flatten Selected
    # run, per the standing summary-propagation rule -- not just a one-shot
    # operator message.
    bpy.types.WindowManager.filelink_flatten_done = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.filelink_flatten_failed = bpy.props.IntProperty(default=0)

    # Per-node expand state for the Analyze panel's inline report disclosure
    # (item a/c, 2026-06-25) — deliberately separate from each feature's own
    # exp_prop (the dedicated Reports tab pre-seeds THAT one expanded; this
    # one always starts empty/collapsed). One flat newline-joined key set
    # shared across every feature's inline view (node keys already embed
    # their own report's feature tag, so no collisions).
    bpy.types.WindowManager.filelink_detail_expanded = bpy.props.StringProperty(default="")

    # Batch E — idle-scan feasibility prototype (gated off by default in prefs).
    bpy.types.WindowManager.filelink_idle_seconds = bpy.props.FloatProperty(default=0.0)
    bpy.types.WindowManager.filelink_idle_detected = bpy.props.BoolProperty(default=False)
    from .ops.idle_scan import register_idle_timer

    register_idle_timer()


def unregister() -> None:
    import bpy

    from .ops.idle_scan import unregister_idle_timer

    unregister_idle_timer()

    global _load_post_handler
    if _load_post_handler is not None and _load_post_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_post_handler)
    _load_post_handler = None

    for attr in ("filelink_scan_dir", "filelink_dep_target", "filelink_debug_log",
                "filelink_material_search_pattern"):
        if hasattr(bpy.types.Scene, attr):
            delattr(bpy.types.Scene, attr)
    from .ops.report_store import FEATURES, INLINE_DETAIL_FEATURES

    wm_attrs = ["filelink_op_active", "filelink_op_progress", "filelink_op_status",
                "filelink_op_paused", "filelink_op_cancel",
                "filelink_last_result", "filelink_last_result_ok",
                "filelink_select_outcomes",
                "filelink_active_report", "filelink_resource_tree",
                "filelink_resource_expanded", "filelink_resource_totals",
                "filelink_profiled_ram",
                "filelink_resource_items_json", "filelink_resource_sort",
                "filelink_report_rows", "filelink_report_index",
                "filelink_resource_rows", "filelink_resource_index",
                "filelink_deform_rows", "filelink_deform_index", "filelink_deform_scanned",
                "filelink_broken_libs", "filelink_broken_index",
                "filelink_broken_imgs", "filelink_broken_imgs_index",
                "filelink_missingtex_picker_rows", "filelink_missingtex_picker_active",
                "filelink_linked_missing_imgs",
                "filelink_dup_lib_members", "filelink_abs_path_members",
                "filelink_res_variant_members",
                "filelink_tex_group_by", "filelink_tex_scanned",
                "filelink_tex_initial_missing", "filelink_tex_expanded",
                "filelink_tex_source_material",
                "filelink_dup_families", "filelink_dup_index",
                "filelink_dup_scanned",
                "filelink_duptex_picker_rows", "filelink_duptex_picker_active",
                "filelink_dup_expanded",
                "filelink_dup_removable", "filelink_dup_linked", "filelink_dup_conflicts",
                "filelink_dup_conflicts_text",
                "filelink_dep_verdict", "filelink_dep_verdict_text",
                "filelink_missing_blocks", "filelink_missing_index",
                "filelink_missing_scanned", "filelink_missing_expanded",
                "filelink_reconnect_picker_rows", "filelink_reconnect_picker_active",
                "filelink_datablock_families", "filelink_datablock_index",
                "filelink_datablock_scanned", "filelink_datablock_removable",
                "filelink_datablock_conflicts", "filelink_datablock_conflicts_text",
                "filelink_datablock_skipped_text",
                "filelink_datablock_expanded",
                "filelink_mat_families", "filelink_mat_index",
                "filelink_mat_scanned", "filelink_mat_removable",
                "filelink_mat_linked",
                "filelink_mat_conflicts", "filelink_mat_conflicts_text",
                "filelink_geo_families", "filelink_geo_index",
                "filelink_geo_scanned", "filelink_geo_removable",
                "filelink_geo_linked",
                "filelink_geo_conflicts", "filelink_geo_conflicts_text",
                "filelink_orphan_rows", "filelink_orphan_index",
                "filelink_orphan_skipped_text",
                "filelink_makelocal_rows", "filelink_makelocal_active",
                "filelink_matsearch_skipped_text",
                "filelink_examine_library_pick", "filelink_examine_library",
                "filelink_examine_rows", "filelink_examine_index",
                "filelink_examine_scanned", "filelink_examine_expanded",
                "filelink_examine_apply_summary",
                "filelink_examine_picker_rows", "filelink_examine_picker_active",
                "filelink_analyze_steps", "filelink_analyze_index",
                "filelink_flatten_candidates", "filelink_flatten_index",
                "filelink_flatten_picker_rows", "filelink_flatten_picker_active",
                "filelink_flatten_plans_json", "filelink_flatten_hierarchy_json",
                "filelink_flatten_expanded",
                "filelink_flatten_remote_note", "filelink_flatten_deselected",
                "filelink_flatten_make_local", "filelink_flatten_make_copy",
                "filelink_flatten_done", "filelink_flatten_failed",
                "filelink_detail_expanded",
                "filelink_idle_seconds", "filelink_idle_detected"]
    for key, _label in FEATURES:
        wm_attrs += [f"filelink_rep_{key}", f"filelink_repx_{key}"]
    for feature in INLINE_DETAIL_FEATURES:
        wm_attrs += [f"filelink_inline_rows_{feature}", f"filelink_inline_active_{feature}"]
    for attr in wm_attrs:
        if hasattr(bpy.types.WindowManager, attr):
            delattr(bpy.types.WindowManager, attr)

    # Reverse order so dependents go before their dependencies.
    while _REGISTERED:
        bpy.utils.unregister_class(_REGISTERED.pop())
