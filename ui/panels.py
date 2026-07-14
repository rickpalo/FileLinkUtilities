"""The File & Link Utilities N-panel (3D viewport sidebar > File & Link Utilities).

Each feature exposes a read-only/report action and, where relevant, an explicit
Apply action so the report-first → apply workflow is reachable without the F9
redo panel. Detailed findings print to the system console
(Window > Toggle System Console on Windows) and, when enabled in Utilities, to
debugLog.txt. Button tooltips come from each operator's ``description()``.
"""

import os
import pathlib

import bpy

DOC_URL = "https://github.com/rickpalo/FileLinkUtilities/tree/main/docs"

_ADDON_VERSION = None


def _addon_version() -> str:
    """Addon version read once from the manifest (single source of truth)."""
    global _ADDON_VERSION
    if _ADDON_VERSION is None:
        try:
            import tomllib

            manifest = pathlib.Path(__file__).resolve().parent.parent / "blender_manifest.toml"
            _ADDON_VERSION = tomllib.loads(manifest.read_text(encoding="utf-8")).get("version", "?")
        except Exception:
            _ADDON_VERSION = "?"
    return _ADDON_VERSION

# Severity -> Blender icon for tree rows ("info" shows no icon to reduce noise).
_SEVERITY_ICON = {"info": "NONE", "warning": "ERROR", "error": "CANCEL"}

# Analyze-All per-step status -> icon (Phase 3a).
_ANALYZE_STEP_ICON = {
    "pending": "RADIOBUT_OFF", "running": "TIME", "done": "CHECKMARK", "error": "ERROR",
}


class FILELINK_PG_tree_row(bpy.types.PropertyGroup):
    """One flattened, indented tree row, materialised so a ``UIList`` can draw it.

    The Report/Resource trees used to be drawn as manual rows, but the N-panel
    doesn't virtualize those, so a large expansion left rows blank past a point.
    A ``UIList`` virtualizes (only visible rows are realised) and scrolls, fixing
    that for any size. ``ops.report_store`` rebuilds the collection from
    ``core.tree.flatten_visible`` whenever the report or its expansion changes."""

    indent: bpy.props.IntProperty()  # type: ignore[valid-type]
    key: bpy.props.StringProperty()  # type: ignore[valid-type]
    label: bpy.props.StringProperty()  # type: ignore[valid-type]
    severity: bpy.props.StringProperty(default="info")  # type: ignore[valid-type]
    has_children: bpy.props.BoolProperty()  # type: ignore[valid-type]
    expanded: bpy.props.BoolProperty()  # type: ignore[valid-type]
    detail: bpy.props.StringProperty()  # type: ignore[valid-type]
    icon: bpy.props.StringProperty()  # optional per-node icon override (e.g. File Map)  # type: ignore[valid-type]
    ref_type: bpy.props.StringProperty()  # type: ignore[valid-type]
    ref_name: bpy.props.StringProperty()  # type: ignore[valid-type]
    popup_parent: bpy.props.StringProperty()  # type: ignore[valid-type]
    popup_basename: bpy.props.StringProperty()  # type: ignore[valid-type]
    prop: bpy.props.StringProperty()  # expanded-keys WM prop this row belongs to
    # Resource Usage's 3 real columns (docs/TODO.md #15) -- empty for every
    # other tree, which keeps using `detail` instead (see draw_item below).
    ram: bpy.props.StringProperty()  # type: ignore[valid-type]
    vram: bpy.props.StringProperty()  # type: ignore[valid-type]
    disk: bpy.props.StringProperty()  # type: ignore[valid-type]


# Fixed width (UI units) for each RAM/VRAM/disk column (docs/TODO.md #15,
# 2026-06-27) -- shared by the Resource Usage header and
# FILELINK_UL_tree.draw_item's resource-row branch so values actually
# line up under their header instead of drifting with content length.
_RESOURCE_COL_WIDTH = 4.4


def _resource_columns(row):
    """3 fixed-width, right-aligned sub-layouts for RAM/VRAM/disk."""
    cols = []
    for _ in range(3):
        col = row.row()
        col.alignment = "RIGHT"
        col.ui_units_x = _RESOURCE_COL_WIDTH
        cols.append(col)
    return cols


class FILELINK_UL_tree(bpy.types.UIList):
    """Virtualized, scrollable tree for the Report and Resource panels: indent +
    expand toggle + tooltip-bearing label + right-aligned detail. Shared by both.
    A row with ``ram``/``vram``/``disk`` set (only Resource rows) draws those as
    3 real aligned columns instead of the generic single ``detail`` column."""

    bl_idname = "FILELINK_UL_tree"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.label)
            return
        row = layout.row(align=True)
        # Plain depth indentation (no ASCII tree-connector glyphs — tried and
        # dropped per user feedback, 2026-06-25: "this Fake Explorer style is
        # garbage"). Every report's tree now indents the same plain way. One
        # unit-factor separator PER LEVEL, not a single separator scaled by
        # item.indent — a single large-factor separator inside an align=True
        # row visibly breaks (both width and row height grow non-linearly past
        # ~3 levels deep, real user report 2026-06-26 on a 4-level File Map).
        for _ in range(item.indent):
            row.separator(factor=1.4)
        if item.has_children:
            tri = "TRIA_DOWN" if item.expanded else "TRIA_RIGHT"
            op = row.operator("filelink.row_toggle", text="", icon=tri, emboss=False)
            op.key = item.key
            op.prop = item.prop
        else:
            row.label(text="", icon="BLANK1")
        # Per-node icon override (e.g. the File Map's blend/missing/external-folder
        # icons) — most rows don't set one, keeping today's icon-free look.
        if item.icon:
            row.label(text="", icon=item.icon)
        # Label as a tooltip-bearing button: tooltip shows the full text (full path,
        # full message + size) even when the narrow panel truncates the display.
        # No severity icon — they added clutter without clear value (user, 2026-06-16).
        full = item.label + (f"   [{item.detail}]" if item.detail else "")
        # Width-aware status lines: a top-level info row (e.g. the "✓ … clean"
        # status) drops its " — …" explanatory tail on a narrow panel, so the gist
        # stays readable without sideways scrolling; the tooltip keeps the full text.
        display = item.label
        region = context.region
        if (item.indent == 0 and not item.has_children and item.severity == "info"
                and " — " in item.label and region and region.width < 320):
            display = item.label.split(" — ", 1)[0]
        op = row.operator("filelink.row_label", text=display,
                          icon="NONE", emboss=False)
        op.text = full
        op.key = item.key
        op.prop = item.prop
        op.has_children = item.has_children
        if item.ref_type:
            op.ref_type = item.ref_type
            op.ref_name = item.ref_name
            # Sticky click-to-select outcome icon (docs/TODO.md Group 10 #37,
            # 2026-07-04) — shows the LAST result for this specific datablock
            # (found-and-selected / no live user / unresolved) so it stays
            # visible after you've scrolled past the one-shot status message.
            from ..ops.report_store import SELECT_OUTCOME_ICON, get_select_outcome

            outcome = get_select_outcome(context.window_manager, item.ref_type, item.ref_name)
            if outcome:
                row.label(text="", icon=SELECT_OUTCOME_ICON.get(outcome, "NONE"))
        if item.popup_parent:
            op.popup_parent = item.popup_parent
            op.popup_basename = item.popup_basename
        if item.ram or item.vram or item.disk:
            for col, val in zip(_resource_columns(row), (item.ram, item.vram, item.disk)):
                col.label(text=val)
        elif item.key == "matdiag:empty_slot" and item.detail:
            # User request, 2026-07-14: a direct fix action right on Check
            # Materials' "Empty material slots" category row — the only
            # category here with a genuinely safe bulk-delete (an empty slot
            # has no content to lose), unlike shader-type/node-link which stay
            # informational-only by the user's own earlier design call.
            sub = row.row(align=True)
            sub.alignment = "RIGHT"
            sub.label(text=item.detail)
            sub.operator("filelink.delete_empty_material_slots",
                        text="Delete Empty Material Slots")
        elif item.detail:
            sub = row.row()
            sub.alignment = "RIGHT"
            sub.label(text=item.detail)


class FILELINK_PG_analyze_step(bpy.types.PropertyGroup):
    """One step of the Analyze section's "Analyze All" sequence (Phase 3a) — a
    thin progress mirror of ``core.analyze_steps.STEPS``, rebuilt and updated by
    ``ops.analyze_all`` as it runs so the panel can show a per-step icon."""

    # `name` (built-in) unused; key/label are explicit for clarity at the call site.
    key: bpy.props.StringProperty()  # type: ignore[valid-type]
    label: bpy.props.StringProperty()  # type: ignore[valid-type]
    status: bpy.props.StringProperty(default="pending")  # pending|running|done|error  # type: ignore[valid-type]


class FILELINK_PG_flatten_candidate(bpy.types.PropertyGroup):
    """One Library Override with an adjusted transform (Phase 4-B), for the
    character picker. ``ops.linkchain.scan_flatten_candidates`` fills the
    collection AND caches each row's full plan (as JSON, on the WM) so picking
    ONE row and building its plan doesn't require rescanning every character —
    the user explicitly wants to act on a single chosen character, not the
    whole file at once."""

    # `name` (built-in) holds the Object's name.
    ready: bpy.props.BoolProperty()  # type: ignore[valid-type]
    # True once Flatten Selected has actually applied this part (not just
    # evaluated it as ready) -- 2026-06-27 user feedback: a fully-done GROUP
    # (every member's `done`) swaps its checkbox for a plain checkmark in
    # the picker instead of moving to a separate "Successfully Flattened"
    # subgroup, the lower-effort of the two options offered.
    done: bpy.props.BoolProperty()  # type: ignore[valid-type]
    status: bpy.props.StringProperty()  # one-line summary or blocking reason  # type: ignore[valid-type]
    # The ARMATURE/rig this part rolls up under (own name when it IS the rig,
    # or when no rig could be resolved — see ops.linkchain._resolve_rig).
    rig: bpy.props.StringProperty()  # type: ignore[valid-type]
    # True when `rig` came from a real armature relationship (self/modifier/
    # parent chain); False when no rig could be found and `rig` fell back to
    # the object's own name (a standalone override, not a multi-part
    # character) — 2026-06-26, lets the picker visually tell the two apart.
    is_rig: bpy.props.BoolProperty()  # type: ignore[valid-type]
    # Flatten v2 (2026-06-27, docs/TODO.md Group 11 #47): True when this row
    # came from the OFFLINE census (core.linkchain.drop_local_posing_findings'
    # remote half), not a live bpy.data.objects read -- it has no live
    # override to inspect yet, so `ready`/`status` are placeholders until
    # Flatten Selected actually harvests it (core.remote_harvest).
    is_remote: bpy.props.BoolProperty()  # type: ignore[valid-type]
    # The .blend this override's data physically lives in -- "" for local
    # rows (this file IS the source). Used to batch remote harvests one
    # subprocess open per donor file, never per character.
    source_file: bpy.props.StringProperty()  # type: ignore[valid-type]
    # Outer grouping key, ABOVE `rig` (2026-06-27, docs/TODO.md): "" for local
    # rows (no outer level, drawn flat as before); "Remote: <file>" for
    # remote rows, so the picker can offer one "select all in this donor
    # file" toggle while still letting individual characters (the inner
    # `rig` groups) be picked separately -- the old design grouped every
    # character in one donor file under a single key, making that
    # impossible.
    group_parent: bpy.props.StringProperty()  # type: ignore[valid-type]


class FILELINK_PG_picker_row(bpy.types.PropertyGroup):
    """One row in the flat virtualized picker list (Group 12 Phase 2).

    ``kind`` selects the row shape in ``FILELINK_UL_flatten_picker.draw_item``:
    - "outer"  — remote donor-file header (select-all checkbox + triangle + label)
    - "group"  — one rig/character group (done-checkmark OR checkbox + triangle + label)
    - "rollup" — the combined property summary under an expanded group (INFO icon + text)
    - "member" — one individual flatten candidate; ``ref_index`` points into the
                 real ``wm.filelink_flatten_candidates`` collection so edits land
                 on live data with no sync step.
    Also reused (Group 12 Phase 3) by ``FILELINK_UL_target_picker`` for
    single-level "checkbox + label + target widget + picker button" sections
    (Missing Textures first): "group"/"member" only there, and ``ref_prop``
    names WHICH WM collection ``ref_index`` points into (member rows only) —
    ``draw_item`` reads/writes that real row directly, same live-data
    approach, generalized since different sections use different collections.
    ``checkbox_state`` is pre-computed at rebuild time so ``draw_item`` never has
    to parse the full newline-joined deselected/done string-sets on every redraw."""

    kind: bpy.props.StringProperty()           # type: ignore[valid-type]
    key: bpy.props.StringProperty()            # toggle/action key  # type: ignore[valid-type]
    group_key: bpy.props.StringProperty()      # parent group (member + nested-group rows)  # type: ignore[valid-type]
    children_keys: bpy.props.StringProperty()  # newline-joined child rig keys (outer rows)  # type: ignore[valid-type]
    ref_prop: bpy.props.StringProperty()       # WM collection name ref_index points into (member rows only)  # type: ignore[valid-type]
    ref_index: bpy.props.IntProperty(default=-1)  # index into real candidates collection  # type: ignore[valid-type]
    indent: bpy.props.IntProperty(default=0)   # type: ignore[valid-type]
    label: bpy.props.StringProperty()          # type: ignore[valid-type]
    icon: bpy.props.StringProperty()           # type: ignore[valid-type]
    checkbox_state: bpy.props.StringProperty()  # "none"|"checked"|"unchecked"|"done"  # type: ignore[valid-type]
    has_action: bpy.props.BoolProperty()       # group rows only: show the header's action button  # type: ignore[valid-type]
    is_expanded: bpy.props.BoolProperty()      # type: ignore[valid-type]


class FILELINK_PG_broken_lib(bpy.types.PropertyGroup):
    """One broken/missing library link, for the per-link relink list (F7).

    ``ops.relink._populate_broken_links`` fills the collection from the current
    file's missing libraries; ``target`` is the auto-found same-name candidate (or
    a file the user picked). ``selected`` is the per-row checkbox so the user
    relinks only the links they choose — e.g. one broken material library."""

    # `name` (PropertyGroup built-in) holds the library datablock name.
    stored: bpy.props.StringProperty()  # type: ignore[valid-type]
    target: bpy.props.StringProperty()  # type: ignore[valid-type]
    has_candidate: bpy.props.BoolProperty()  # type: ignore[valid-type]
    selected: bpy.props.BoolProperty(
        default=False, name="",
        description="Include this link when you Relink Selected")  # type: ignore[valid-type]
    # F6 B1 grouping (images only): original containing directory + a representative
    # material, so the user can point a whole group at one folder.
    group: bpy.props.StringProperty()  # type: ignore[valid-type]
    material: bpy.props.StringProperty()  # type: ignore[valid-type]
    # F6 step 4 "Possible Matches": a FUZZY-proposed file for a texture that exact
    # search couldn't place (vendor-renamed channels, etc.). Staged separately from
    # ``target`` — the user reviews + Accepts, which copies ``proposal`` into
    # ``target``. ``proposal_confidence`` is "high"/"medium"/"low";
    # ``proposal_res_mismatch`` flags a different resolution (lossy — lower trust).
    proposal: bpy.props.StringProperty()  # type: ignore[valid-type]
    proposal_confidence: bpy.props.StringProperty()  # type: ignore[valid-type]
    proposal_res_mismatch: bpy.props.BoolProperty()  # type: ignore[valid-type]
    # Set by the recursive folder-search worker (ops.image_relink._run_exact) when
    # this row has NO target: how many files elsewhere in the scanned tree share its
    # filename (2+ = the row was skipped as ambiguous, not because nothing matched —
    # this is what made a drive-level search miss textures a narrower one found).
    ambiguous_count: bpy.props.IntProperty(default=0)  # type: ignore[valid-type]
    # Linked-missing-texture rows ONLY (ops.image_relink._gather_linked_missing_
    # images, a separate read-only list): the source LIBRARY this image belongs
    # to — these can't be relinked from here (the library file owns that path),
    # this just says where to go fix it. Empty for every other row/list that
    # reuses this PropertyGroup.
    library: bpy.props.StringProperty()  # type: ignore[valid-type]
    # Generic free-form per-row tag, repurposed per list (items 6/7/11,
    # 2026-06-25): unused for Inconsistent/Duplicate Library Paths and
    # Absolute Paths (``group`` already carries their grouping key); for
    # Resolution Variant rows it holds the member's own resolution token
    # ("1k"/"2k"/...), needed by Select High/Low Resolution. For Missing
    # Textures rows (2026-07-09) it holds the row's CATEGORY —
    # "material"/"world"/"other" — one level above ``material``'s own
    # grouping-within-category key; see ``ops.image_relink.
    # rebuild_missing_tex_picker_rows``.
    tag: bpy.props.StringProperty()  # type: ignore[valid-type]


class FILELINK_PG_deform_row(bpy.types.PropertyGroup):
    """One flagged object from Check Armature Deformation (ops.deform_check,
    2026-07-09) — detection/review only, no fix action yet, so this row is
    purely informational plus a ``selected`` checkbox for a later fix pass to
    read. ``vertex_ids`` is a comma-joined string (a real fix will need to
    re-resolve these against live bpy data anyway, e.g. to inspect vertex-group
    weights, so this is just enough to say WHICH vertices without re-scanning)."""

    # `name` (PropertyGroup built-in) holds the object name.
    mesh_name: bpy.props.StringProperty()  # type: ignore[valid-type]
    armature_name: bpy.props.StringProperty()  # type: ignore[valid-type]
    vertex_count: bpy.props.IntProperty()  # type: ignore[valid-type]
    worst_ratio: bpy.props.FloatProperty()  # type: ignore[valid-type]
    vertex_ids: bpy.props.StringProperty()  # type: ignore[valid-type]
    # False when the object or its mesh is LINKED from another .blend — the
    # vertex-group weight data a fix would need to edit isn't local to this
    # file, so a fix has to happen at the source file instead (same "fix at
    # source" distinction this addon already makes for linked missing textures).
    is_locally_fixable: bpy.props.BoolProperty(default=True)  # type: ignore[valid-type]
    selected: bpy.props.BoolProperty(
        default=False, name="",
        description="Mark this object for a future fix pass")  # type: ignore[valid-type]


class FILELINK_UL_deform_rows(bpy.types.UIList):
    """Check Armature Deformation's results list: checkbox + object name +
    worst-edge ratio + affected-vertex count. Flat, no grouping — in practice
    this list should stay short (a healthy file has zero rows), unlike Missing
    Textures' potentially-thousands-of-rows case that needed real grouping."""

    bl_idname = "FILELINK_UL_deform_rows"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.name)
            return
        row = layout.row(align=True)
        row.prop(item, "selected", text="")
        row.label(text=item.name, icon="ERROR")
        if not item.is_locally_fixable:
            lrow = row.row()
            lrow.alignment = "RIGHT"
            lrow.label(text="linked — fix at source", icon="LIBRARY_DATA_BROKEN")
        detail = row.row()
        detail.alignment = "RIGHT"
        detail.label(text=f"{item.vertex_count} vert(s), worst {item.worst_ratio:.0f}x  "
                          f"(armature: {item.armature_name})")


# Keeps a strong reference to each row's keeper-enum items list. Dynamic
# EnumProperty item callbacks MUST NOT let the returned strings be garbage-collected
# (a well-known Blender crash) — caching the list here pins them for the row's life.
_KEEPER_ITEMS_CACHE: dict[str, list] = {}


def _keeper_enum_items(self, context):
    """Items for a duplicate family's keeper dropdown = its member datablock names
    (canonical first). Built from the row's newline-joined ``members`` string."""
    names = [n for n in self.members.split("\n") if n]
    items = [(n, n, "Keep this datablock; merge the others into it", i)
             for i, n in enumerate(names)]
    _KEEPER_ITEMS_CACHE[self.members] = items  # pin against GC
    return items or [("", "", "")]


def _dup_override_updated(self, context) -> None:
    """``material_override``'s ``update`` callback (Group 12 Phase 3, item 2):
    unlike every other per-row edit in this section (``selected``/``keeper``),
    picking a different material here changes which GROUP the family belongs
    under (and the group's mismatch flag/count) — a plain ``row.prop()`` edit
    with no operator to hang a rebuild off, so the virtualized picker rows
    would otherwise show the family under its OLD group until the next scan."""
    from ..ops.image_dedup import rebuild_dup_tex_picker_rows

    rebuild_dup_tex_picker_rows(context.window_manager)
    if context.area:
        context.area.tag_redraw()


class FILELINK_PG_dup_family(bpy.types.PropertyGroup):
    """One content-identical ``.NNN`` duplicate family, for the redesigned Duplicate
    Materials/Textures list. ``members`` (newline-joined, canonical first) feeds the
    ``keeper`` dropdown so the user can pick which datablock survives; ``selected``
    is the per-family include checkbox for Merge Selected."""

    # `name` (built-in) = the family base name.
    members: bpy.props.StringProperty()  # type: ignore[valid-type]
    keeper: bpy.props.EnumProperty(
        name="Keep", description="Which datablock to keep; the rest merge into it",
        items=_keeper_enum_items)  # type: ignore[valid-type]
    selected: bpy.props.BoolProperty(
        default=True, name="",
        description="Include this family when you Merge Selected")  # type: ignore[valid-type]
    material: bpy.props.StringProperty()  # type: ignore[valid-type]
    # Eyedropper override: when the auto-attributed material looks wrong (its name
    # doesn't match the texture's), point this at the correct material to re-group
    # the family under it. Organizational only — it does NOT rewire node trees.
    material_override: bpy.props.PointerProperty(
        type=bpy.types.Material, update=_dup_override_updated)  # type: ignore[valid-type]
    removable: bpy.props.IntProperty()  # type: ignore[valid-type]
    # Redundant members that are LINKED (2026-07-14) — reported, never merged;
    # kept separate from `removable` so that number stays an honest count of
    # what Merge Selected will actually remove.
    linked_count: bpy.props.IntProperty()  # type: ignore[valid-type]


# Keeps a strong reference to each row's reconnect-target enum items list, the
# same GC-pin trick as _KEEPER_ITEMS_CACHE — dynamic EnumProperty item callbacks
# must not let the returned strings be garbage-collected.
_RECONNECT_ITEMS_CACHE: dict[str, list] = {}


def _reconnect_target_items(self, context):
    """Items for a missing block's reconnect-target dropdown = the names available
    in its chosen source .blend (``ops.datablock_reconnect._enumerate_group`` fills
    ``candidates``, already ranked so the suggested name is first — Blender shows a
    fresh dynamic enum's first item by default, so that's how the suggestion
    becomes the default selection without an explicit (fragile) assignment)."""
    names = [n for n in self.candidates.split("\n") if n]
    if not names:
        # Covers both "no source picked yet" AND "a source IS remembered for this
        # group but candidates weren't re-peeked" (the crash-safety change in
        # ops.datablock_reconnect._populate_missing_blocks) — same fix either way:
        # click the group's folder icon to (re-)pick the source.
        return [("", "(pick/re-pick the source .blend)", "")]
    items = [(n, n, "Reconnect to this datablock", i) for i, n in enumerate(names)]
    _RECONNECT_ITEMS_CACHE[self.candidates] = items  # pin against GC
    return items


class FILELINK_PG_missing_block(bpy.types.PropertyGroup):
    """One missing (placeholder) data-block staged for RECONNECT (Batch C). Rows
    group by ``library`` in the panel — one source-.blend pick applies to the whole
    group, since a broken/renamed library's blocks usually all need the same fix.
    ``ops.datablock_reconnect`` fills/enumerates/applies this list."""

    # `name` (built-in) = the missing block's own name.
    kind: bpy.props.StringProperty()  # type: ignore[valid-type]
    collection: bpy.props.StringProperty()  # bpy.data attribute, e.g. "materials"  # type: ignore[valid-type]
    library: bpy.props.StringProperty()  # original source library path (group key)  # type: ignore[valid-type]
    source_blend: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore[valid-type]
    candidates: bpy.props.StringProperty()  # newline-joined names, ranked (best first)  # type: ignore[valid-type]
    confidence: bpy.props.StringProperty(default="none")  # type: ignore[valid-type]
    target: bpy.props.EnumProperty(
        name="Reconnect to", items=_reconnect_target_items)  # type: ignore[valid-type]
    selected: bpy.props.BoolProperty(
        default=False, name="",
        description="Include this data-block when you Reconnect Selected")  # type: ignore[valid-type]
    # Whether THIS GROUP's own stored library path resolves on disk (computed at
    # scan time, ops.datablock_reconnect._populate_missing_blocks) — distinguishes
    # "library not found on this machine, pick a source manually" from "library
    # found, just doesn't have this exact name" (user report 2026-06-24: the
    # Reconnect list didn't differentiate the two, so a hopeless group looked
    # identical to a fixable one).
    library_found: bpy.props.BoolProperty(default=False)  # type: ignore[valid-type]


# Same GC-pin trick as _KEEPER_ITEMS_CACHE, separate cache for this list's rows.
_GENERIC_KEEPER_CACHE: dict[str, list] = {}


def _generic_keeper_items(self, context):
    """Items for a generic duplicate family's keeper dropdown = its member
    datablock names (canonical first, like the image-dedup keeper)."""
    names = [n for n in self.members.split("\n") if n]
    items = [(n, n, "Keep this datablock; merge the others into it", i)
             for i, n in enumerate(names)]
    _GENERIC_KEEPER_CACHE[self.members] = items  # pin against GC
    return items or [("", "", "")]


# Same GC-pin trick as _KEEPER_ITEMS_CACHE, separate cache for this list's rows.
_MATERIAL_KEEPER_CACHE: dict[str, list] = {}


def _material_keeper_items(self, context):
    """Items for a duplicate-material group's keeper dropdown = its member
    ids (canonical first — see ops.material_dedup._material_id for the
    "Name [library]" disambiguation a local + linked same-named pair needs)."""
    names = [n for n in self.members.split("\n") if n]
    items = [(n, n, "Keep this material; merge the others into it", i)
             for i, n in enumerate(names)]
    _MATERIAL_KEEPER_CACHE[self.members] = items  # pin against GC
    return items or [("", "", "")]


class FILELINK_PG_material_family(bpy.types.PropertyGroup):
    """One content-identical duplicate-material group for the reformatted
    Find Duplicate Materials list (user feedback, 2026-06-25: the old report
    gave no way to act on what it found). Unlike the .NNN name-family tools,
    members come from build_dedup_plan's FINGERPRINT clusters directly — two
    differently-named materials can land in the same group."""

    # `name` (built-in) = the canonical member's id (ops.material_dedup._material_id).
    members: bpy.props.StringProperty()  # newline-joined ids, canonical first  # type: ignore[valid-type]
    keeper: bpy.props.EnumProperty(
        name="Keep", description="Which material to keep; the rest merge into it",
        items=_material_keeper_items)  # type: ignore[valid-type]
    selected: bpy.props.BoolProperty(
        default=True, name="",
        description="Include this group when you Merge Selected")  # type: ignore[valid-type]
    removable: bpy.props.IntProperty()  # type: ignore[valid-type]


class FILELINK_PG_geo_family(bpy.types.PropertyGroup):
    """One duplicate-geometry instancing group for the Find Duplicates section
    (Group 11 #44, 2026-06-26) — mirrors :class:`FILELINK_PG_material_family`'s
    shape but no keeper dropdown: instancing always keeps the canonical mesh
    ``core.geometry_dedup.choose_canonical`` already picked (most-shared
    local), no ambiguity to override."""

    # `name` (built-in) = the canonical mesh's id (core.geometry_dedup format).
    kind: bpy.props.StringProperty()  # always "Mesh" today; kept for future kinds  # type: ignore[valid-type]
    victims: bpy.props.StringProperty()  # newline-joined victim ids  # type: ignore[valid-type]
    selected: bpy.props.BoolProperty(
        default=True, name="",
        description="Include this group when you Instance Selected")  # type: ignore[valid-type]
    removable: bpy.props.IntProperty()  # type: ignore[valid-type]


class FILELINK_PG_orphan_row(bpy.types.PropertyGroup):
    """One TRUE orphan (users==0) datablock for the Find Orphans section
    (Group 11 #45, 2026-06-26) — checkbox-only, no keeper: purging is binary,
    no "which one survives" decision like the dedup tools. Fake-user-only and
    identical-cluster findings stay read-only/informational (deliberate,
    existing design — see ``ops.orphans``'s module docstring: clearing fake
    users or merging identical datablocks "reflects intent, not just
    cleanup")."""

    # `name` (built-in) = "Type/Name" ref (core.tree._parse_ref format).
    selected: bpy.props.BoolProperty(
        default=True, name="",
        description="Include this datablock when you Purge Selected")  # type: ignore[valid-type]


class FILELINK_PG_makelocal_row(bpy.types.PropertyGroup):
    """One linked datablock for Make Local's per-item picker (docs/TODO.md
    #22) — flat (unlike the grouped-by-library report), since a real project
    can have thousands of linked datablocks and Blender's own UIList filter
    box already handles narrowing a big flat list; no group/member
    virtualization layer needed the way Missing/Duplicate Textures required
    (their underlying data is a genuine tree, this isn't)."""

    # `name` (built-in) = ops.make_local._row_key (unique "Type/Name [library]").
    item_type: bpy.props.StringProperty()  # type: ignore[valid-type]
    item_name: bpy.props.StringProperty()  # type: ignore[valid-type]
    library: bpy.props.StringProperty()  # type: ignore[valid-type]
    indirect: bpy.props.BoolProperty(default=False)  # type: ignore[valid-type]
    selected: bpy.props.BoolProperty(
        default=True, name="",
        description="Include this datablock when you Make Local Selected")  # type: ignore[valid-type]


class FILELINK_PG_datablock_family(bpy.types.PropertyGroup):
    """One content-identical ``.NNN`` duplicate family for the generic Duplicate
    Data-blocks list (Batch C #3) — any datablock type ``ops.datablock_dup``
    fingerprints, grouped by ``kind`` in the panel (no material attribution; that
    concept is texture-specific)."""

    # `name` (built-in) = "{bpy.data attribute}:{family base name}".
    kind: bpy.props.StringProperty()  # display label, e.g. "Action"  # type: ignore[valid-type]
    collection: bpy.props.StringProperty()  # bpy.data attribute, e.g. "actions"  # type: ignore[valid-type]
    members: bpy.props.StringProperty()  # newline-joined, canonical first  # type: ignore[valid-type]
    keeper: bpy.props.EnumProperty(
        name="Keep", description="Which datablock to keep; the rest merge into it",
        items=_generic_keeper_items)  # type: ignore[valid-type]
    selected: bpy.props.BoolProperty(
        default=True, name="",
        description="Include this family when you Merge Selected")  # type: ignore[valid-type]
    removable: bpy.props.IntProperty()  # type: ignore[valid-type]


# Same GC-pin trick as _RECONNECT_ITEMS_CACHE, separate cache for this list.
_EXAMINE_ITEMS_CACHE: dict[str, list] = {}


def _examine_target_items(self, context):
    """Items for an Examine Library row's manual-pick dropdown = the names found
    in the .blend the user picked via Pick a Specific Item (ranked, closest-name
    first; the user is free to pick ANY of them, e.g. a Sphere for a Cube)."""
    names = [n for n in self.candidates.split("\n") if n]
    if not names:
        return [("", "(pick a .blend first)", "")]
    items = [(n, n, "Relink to this datablock", i) for i, n in enumerate(names)]
    _EXAMINE_ITEMS_CACHE[self.candidates] = items  # pin against GC
    return items


def _graph_match_suffix(base: str, graph_match: str) -> tuple[str, str]:
    """Append the node-graph/mesh comparison (Material, Mesh, and NodeTree rows)
    to an Examine Library suggestion line: "identical" keeps the plain
    checkmark, "differs" warns that the same-named substitute is actually
    different content, "unverified" warns the content couldn't be safely
    checked at all (a missing placeholder or Library Override on either side —
    see ``ops.examine_library._content_graph_match``) — both "differs" and
    "unverified" are NOT auto-applied (2026-07-09). "" (unsupported kind) is
    the only case that leaves the base text untouched, unchanged behavior."""
    if graph_match == "identical":
        return f"{base} (identical)", "CHECKMARK"
    if graph_match == "differs":
        return f"{base} (graph differs)", "ERROR"
    if graph_match == "unverified":
        return f"{base} (unverified — needs manual check)", "QUESTION"
    return base, "CHECKMARK"


def _manual_pick_graph_icon(row) -> str:
    """Compact icon (no label — the ``target`` dropdown already eats
    horizontal row space, per docs/TODO.md's 2026-07-09 "two-pass" design
    note) for a manual-pick Examine Library row's content-verification state.
    ``""`` means draw nothing extra: either an unsupported kind (Object,
    Image, Action, ... — old name-only trust, unchanged) or nothing has been
    picked yet."""
    if row.graph_match == "identical":
        return "CHECKMARK"
    if row.graph_match == "differs":
        return "ERROR"
    if row.graph_match == "unverified":
        return "QUESTION"
    if row.source_blend and row.collection in {"meshes", "materials", "node_groups"}:
        return "QUESTION"  # fuzzy-only top match — never verified, needs manual review
    return ""


def _on_examine_target_changed(self, context):
    """The user manually swapped the manual-pick dropdown to a candidate pass
    2 never checked (``ops.examine_library._verify_candidates`` only verifies
    the ranked TOP candidate) — ``graph_match``/``selected`` were computed
    against the PREVIOUS target, so they're stale for this new one. Reset
    both so a swap can't silently ride along on a stale "verified" auto-
    select; the row's own checkbox is still right there for the user to
    re-tick after reviewing the new pick."""
    self.graph_match = ""
    self.selected = False


class FILELINK_PG_examine_row(bpy.types.PropertyGroup):
    """One datablock the EXAMINED library currently provides (Examine Library —
    distinct from the missing-data-block reconnect list: these links are NOT
    broken, the user just wants to stop depending on this library for them).

    ``ops.examine_library`` fills/applies this list. Per row: accept the
    in-memory suggestion (``use_suggested``), tick Make Local, or manually pick a
    specific source + item (``source_blend``/``target``) — mutually exclusive,
    checked in that priority order on Apply."""

    # `name` (built-in) = the datablock's own name.
    kind: bpy.props.StringProperty()  # type: ignore[valid-type]
    collection: bpy.props.StringProperty()  # bpy.data attribute  # type: ignore[valid-type]
    suggested_kind: bpy.props.StringProperty(default="none")  # "local" | "library" | "none"  # type: ignore[valid-type]
    suggested_name: bpy.props.StringProperty()  # type: ignore[valid-type]
    suggested_library: bpy.props.StringProperty()  # filepath, when suggested_kind == "library"  # type: ignore[valid-type]
    graph_match: bpy.props.StringProperty()  # "identical"|"differs"|"unverified"|"" — Material/Mesh/NodeTree rows  # type: ignore[valid-type]
    use_suggested: bpy.props.BoolProperty(default=False)  # type: ignore[valid-type]
    make_local: bpy.props.BoolProperty(
        default=False, name="",
        description="Sever the link and keep using THIS copy locally")  # type: ignore[valid-type]
    source_blend: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore[valid-type]
    candidates: bpy.props.StringProperty()  # newline-joined names from source_blend  # type: ignore[valid-type]
    target: bpy.props.EnumProperty(
        name="Relink to", items=_examine_target_items,
        update=_on_examine_target_changed)  # type: ignore[valid-type]
    selected: bpy.props.BoolProperty(
        default=False, name="",
        description="Include this data-block when you Apply Selected")  # type: ignore[valid-type]


class FILELINK_UL_broken_libs(bpy.types.UIList):
    """Per-link relink list: checkbox + broken library name + its target file (or
    a 'pick a file' hint) + a file-picker button. Lets the user fix one specific
    broken link without running a bulk pass."""

    bl_idname = "FILELINK_UL_broken_libs"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.name)
            return
        row = layout.row(align=True)
        row.prop(item, "selected", text="")
        row.label(text=item.name, icon="LIBRARY_DATA_BROKEN")
        # "indirect" (docs/TODO.md Group 1 item 5, 2026-07-04): this library
        # isn't linked by the current file directly, only by ANOTHER linked
        # library — not visible in this file's own Outliner, so callers used
        # to be confused why it showed up here at all. Only the surprising
        # case gets a visible flag; "direct" is the expected default, no noise.
        if item.tag == "indirect":
            ind = row.row()
            ind.alignment = "RIGHT"
            ind.label(text="indirect", icon="INFO")
        target = row.row()
        target.alignment = "RIGHT"
        if item.target:
            target.label(text=os.path.basename(item.target) or item.target,
                         icon="CHECKMARK" if item.has_candidate else "QUESTION")
        else:
            target.label(text="no match — pick a file", icon="QUESTION")
        row.operator("filelink.relink_pick_file", text="", icon="FILEBROWSER").index = index


class FILELINK_UL_flatten_picker(bpy.types.UIList):
    """Virtualized picker for the Flattenable Overrides section (Group 12 Phase 2).

    Renders from ``wm.filelink_flatten_picker_rows`` (rebuilt by
    ``ops.linkchain.rebuild_flatten_picker_rows`` after scan/toggle/evaluate/flatten).
    Four row shapes handled in ``draw_item`` via ``item.kind``; all state (expanded,
    deselected, done) is pre-baked into the row at rebuild time so this draw path
    stays pure read-only — no per-redraw string-set parsing."""

    bl_idname = "FILELINK_UL_flatten_picker"

    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname, index):
        if self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.label or "—")
            return

        row = layout.row(align=True)
        if item.indent:
            row.separator(factor=float(item.indent) * 1.5)

        if item.kind == "outer":
            gop = row.operator("filelink.flatten_group_select_all", text="",
                               icon=("CHECKBOX_HLT" if item.checkbox_state == "checked"
                                     else "CHECKBOX_DEHLT"),
                               emboss=False)
            gop.keys = item.children_keys
            tog = row.operator("filelink.row_toggle", text="",
                               icon="TRIA_DOWN" if item.is_expanded else "TRIA_RIGHT",
                               emboss=False)
            tog.key, tog.prop = item.key, "filelink_flatten_expanded"
            row.label(text=item.label, icon=item.icon)

        elif item.kind == "group":
            if item.checkbox_state == "done":
                row.label(text="", icon="CHECKMARK")
            else:
                cop = row.operator("filelink.row_toggle", text="",
                                   icon=("CHECKBOX_HLT" if item.checkbox_state == "checked"
                                         else "CHECKBOX_DEHLT"),
                                   emboss=False)
                cop.key, cop.prop = item.key, "filelink_flatten_deselected"
            tog = row.operator("filelink.row_toggle", text="",
                               icon="TRIA_DOWN" if item.is_expanded else "TRIA_RIGHT",
                               emboss=False)
            tog.key, tog.prop = item.key, "filelink_flatten_expanded"
            row.label(text=item.label, icon=item.icon)

        elif item.kind == "rollup":
            row.label(text=item.label, icon="INFO")

        elif item.kind == "member":
            row.label(text=item.label, icon=item.icon)


class FILELINK_UL_missing_tex_picker(bpy.types.UIList):
    """Virtualized picker for the Missing Textures section (Group 12 Phase 3,
    first single-level "checkbox + label + target widget + picker button"
    section). Renders from ``wm.filelink_missingtex_picker_rows`` (rebuilt
    by ``ops.image_relink.rebuild_missing_tex_picker_rows`` after every scan/
    toggle/pick/accept/relink). Group rows draw the pre-baked triangle+icon+
    label+count (and an optional "point at folder" action button); member
    rows read/write the REAL ``wm.filelink_broken_imgs`` row directly via
    ``item.ref_prop``/``item.ref_index`` — same live-data approach as
    ``FILELINK_UL_broken_libs`` — so ticking a checkbox or picking a file
    needs no rebuild, only a target/membership change does."""

    bl_idname = "FILELINK_UL_missing_tex_picker"

    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname, index):
        if self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.label or "—")
            return

        row = layout.row(align=True)
        if item.indent:
            row.separator(factor=float(item.indent) * 1.5)

        if item.kind == "outer":
            # The Material/World/Other Textures category header (2026-07-09) --
            # a pure collapsible label + summary, no per-category bulk action
            # (the section-wide Search Folder/Suggest Matches buttons above
            # already cover all three; see rebuild_missing_tex_picker_rows for
            # why a folder action stays MATERIAL-group-only).
            tog = row.operator("filelink.row_toggle", text="",
                               icon="TRIA_DOWN" if item.is_expanded else "TRIA_RIGHT",
                               emboss=False)
            tog.key, tog.prop = item.key, "filelink_tex_expanded"
            row.label(text=item.label, icon=item.icon)
            return

        if item.kind == "group":
            tog = row.operator("filelink.row_toggle", text="",
                               icon="TRIA_DOWN" if item.is_expanded else "TRIA_RIGHT",
                               emboss=False)
            tog.key, tog.prop = item.key, "filelink_tex_expanded"
            row.label(text=item.label, icon=item.icon)
            if item.has_action:
                fop = row.operator("filelink.point_group_at_folder", text="",
                                   icon="FILE_FOLDER")
                fop.group_key, fop.by = item.key, "MATERIAL"
            return

        # kind == "member": draw straight from the real row, nothing copied here.
        coll = getattr(context.window_manager, item.ref_prop, None)
        if coll is None or not (0 <= item.ref_index < len(coll)):
            return
        real = coll[item.ref_index]
        row.prop(real, "selected", text="")
        row.label(text=real.name, icon="IMAGE_DATA")
        tgt = row.row()
        tgt.alignment = "RIGHT"
        if real.target:
            tgt.label(text=os.path.basename(real.target) or real.target, icon="CHECKMARK")
        elif real.ambiguous_count > 1:
            tgt.label(text=f"{real.ambiguous_count} found elsewhere — pick one", icon="ERROR")
        else:
            tgt.label(text="no match", icon="QUESTION")
        row.operator("filelink.relink_pick_texture", text="",
                    icon="FILEBROWSER").index = item.ref_index


class FILELINK_UL_dup_tex_picker(bpy.types.UIList):
    """Virtualized picker for the Duplicate Textures section (Group 12 Phase 3,
    item 2) — the "keeper dropdown" member shape, a DIFFERENT row family from
    Missing Textures' target+picker shape (every member row carries a keeper
    ``EnumProperty`` + a conditional material-override eyedropper instead of a
    file-picker button). Renders from ``wm.filelink_duptex_picker_rows``
    (rebuilt by ``ops.image_dedup.rebuild_dup_tex_picker_rows`` after scan/
    merge/toggle, AND by ``material_override``'s own ``update`` callback since
    that field can change a family's group with no operator involved). Member
    rows read/write the REAL ``wm.filelink_dup_families`` row directly, same
    live-data approach as ``FILELINK_UL_missing_tex_picker``."""

    bl_idname = "FILELINK_UL_dup_tex_picker"

    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname, index):
        if self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.label or "—")
            return

        row = layout.row(align=True)
        if item.indent:
            row.separator(factor=float(item.indent) * 1.5)

        if item.kind == "group":
            tog = row.operator("filelink.row_toggle", text="",
                               icon="TRIA_DOWN" if item.is_expanded else "TRIA_RIGHT",
                               emboss=False)
            tog.key, tog.prop = item.key, "filelink_dup_expanded"
            lab = row.row()
            lab.alert = item.alert
            lab.label(text=item.label, icon=item.icon)
            if item.has_action:
                kop = row.operator("filelink.dup_material_keeper", text="",
                                   icon="DOWNARROW_HLT")
                kop.material = item.key
            return

        # kind == "member": draw straight from the real row, nothing copied here.
        from ..ops.image_dedup import is_mismatch

        coll = getattr(context.window_manager, item.ref_prop, None)
        if coll is None or not (0 <= item.ref_index < len(coll)):
            return
        real = coll[item.ref_index]
        row.prop(real, "selected", text="")
        bad = is_mismatch(real)
        name = row.row()
        name.alert = bad
        linked_suffix = f", +{real.linked_count} linked" if real.linked_count else ""
        name.label(text=f"{real.name}  ({real.removable}{linked_suffix})",
                  icon="ERROR" if bad else "IMAGE_DATA")
        # Alternate material picker (eyedropper): re-home a mis-attributed family
        # under the correct material. Shown when it looks wrong (or was already
        # overridden). Organizational only — doesn't rewire nodes.
        if bad or real.material_override:
            row.prop(real, "material_override", text="")
        keep = row.row()
        keep.alignment = "RIGHT"
        keep.label(text="keep", icon="PINNED")
        keep.prop(real, "keeper", text="")


class FILELINK_UL_makelocal_picker(bpy.types.UIList):
    """Virtualized picker for Make Local's per-item selection (docs/TODO.md
    #22) — draws straight off ``wm.filelink_makelocal_rows`` (a real, flat
    CollectionProperty; template_list virtualizes it natively, no extra
    group/member indirection layer needed the way the tree-shaped pickers
    elsewhere in this file require)."""

    bl_idname = "FILELINK_UL_makelocal_picker"

    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname, index):
        if self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.item_name or "—")
            return

        row = layout.row(align=True)
        row.prop(item, "selected", text="")
        row.label(text=f"{item.item_type}/{item.item_name}",
                  icon="LIBRARY_DATA_INDIRECT" if item.indirect else "LIBRARY_DATA_DIRECT")
        lib = row.row()
        lib.alignment = "RIGHT"
        lib.label(text=os.path.basename(item.library) or item.library)


class FILELINK_UL_reconnect_picker(bpy.types.UIList):
    """Virtualized picker for the Datablock Reconnect section (Group 12 Phase
    3, item 3) — a THIRD member-row family (checkbox + label + a confidence
    icon/label + a "Reconnect to" ``EnumProperty`` dropdown, no file-picker or
    keeper). Renders from ``wm.filelink_reconnect_picker_rows`` (rebuilt by
    ``ops.datablock_reconnect.rebuild_reconnect_picker_rows`` after scan/pick-
    source/reconnect-selected). Group rows always carry the "Pick Source
    .blend" action button; the source-status line (which .blend is picked, or
    why not) draws as a "rollup" row — the same INFO-line shape Flattenable
    Overrides already uses, generalized (Group 12 Phase 3's ``GroupSpec.info``)
    so this section didn't need its own kind. Member rows read/write the REAL
    ``wm.filelink_missing_blocks`` row directly, same live-data approach as
    ``FILELINK_UL_missing_tex_picker``."""

    bl_idname = "FILELINK_UL_reconnect_picker"

    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname, index):
        if self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.label or "—")
            return

        row = layout.row(align=True)
        if item.indent:
            row.separator(factor=float(item.indent) * 1.5)

        if item.kind == "group":
            tog = row.operator("filelink.row_toggle", text="",
                               icon="TRIA_DOWN" if item.is_expanded else "TRIA_RIGHT",
                               emboss=False)
            tog.key, tog.prop = item.key, "filelink_missing_expanded"
            row.label(text=item.label, icon=item.icon)
            if item.has_action:
                pop = row.operator("filelink.reconnect_pick_source", text="",
                                   icon="FILEBROWSER")
                pop.library = item.key
            return

        if item.kind == "rollup":
            row.label(text=item.label, icon=item.icon or "INFO")
            return

        # kind == "member": draw straight from the real row, nothing copied here.
        coll = getattr(context.window_manager, item.ref_prop, None)
        if coll is None or not (0 <= item.ref_index < len(coll)):
            return
        real = coll[item.ref_index]
        row.prop(real, "selected", text="")
        row.label(text=f"{real.kind}: {real.name}", icon="LIBRARY_DATA_BROKEN")
        conf_icon, conf_label = _RECONNECT_CONF.get(real.confidence, ("BLANK1", ""))
        if conf_label:
            cf = row.row()
            cf.alignment = "RIGHT"
            cf.label(text=conf_label, icon=conf_icon)
        row.prop(real, "target", text="")


class FILELINK_UL_examine_picker(bpy.types.UIList):
    """Virtualized picker for the Examine Library section (Group 12 Phase 3,
    item 4 — the last single-level section) — a FOURTH member-row family:
    checkbox + label + a conditional middle status (Make Local / in-memory
    suggestion / manual target dropdown / "no in-memory match") + a Make
    Local checkbox + two per-row file-pick buttons. The simplest rebuild story
    of the four: grouping is fixed at scan time (by ``kind``) and no group
    header text depends on per-row state, so ``ops.examine_library.
    rebuild_examine_picker_rows`` only runs after Examine/Apply Selected —
    every per-row edit here (``selected``/``make_local``/``target``, or a
    fresh ``source_blend`` from Pick a Specific Item/Search a Folder) draws
    live off the real ``wm.filelink_examine_rows`` row, same as the other
    three pickers."""

    bl_idname = "FILELINK_UL_examine_picker"

    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname, index):
        if self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.label or "—")
            return

        row = layout.row(align=True)
        if item.indent:
            row.separator(factor=float(item.indent) * 1.5)

        if item.kind == "group":
            tog = row.operator("filelink.row_toggle", text="",
                               icon="TRIA_DOWN" if item.is_expanded else "TRIA_RIGHT",
                               emboss=False)
            tog.key, tog.prop = item.key, "filelink_examine_expanded"
            row.label(text=item.label, icon=item.icon)
            return

        # kind == "member": draw straight from the real row, nothing copied here.
        coll = getattr(context.window_manager, item.ref_prop, None)
        if coll is None or not (0 <= item.ref_index < len(coll)):
            return
        real = coll[item.ref_index]
        row.prop(real, "selected", text="")
        row.label(text=real.name, icon="LIBRARY_DATA_DIRECT")
        if real.make_local:
            pass  # the Make Local checkbox below already says it all
        elif real.suggested_kind == "local":
            # NOTE: not gated on `use_suggested` — a "(graph differs)" row has
            # use_suggested=False (Apply Selected won't auto-touch it, see
            # ops.examine_library._populate_examine_rows) but the suggestion
            # and WHY it was rejected still need to be visible for manual
            # review, not silently replaced by the "no in-memory match" line.
            s = row.row()
            s.alignment = "RIGHT"
            text, sicon = _graph_match_suffix(f"local: {real.suggested_name}", real.graph_match)
            s.label(text=text, icon=sicon)
        elif real.suggested_kind == "library":
            from ..core.datablock_links import basename as _lib_basename

            s = row.row()
            s.alignment = "RIGHT"
            base = f"{_lib_basename(real.suggested_library)}: {real.suggested_name}"
            text, sicon = _graph_match_suffix(base, real.graph_match)
            s.label(text=text, icon=sicon)
        elif real.source_blend:
            row.prop(real, "target", text="")
            icon = _manual_pick_graph_icon(real)
            if icon:
                row.label(text="", icon=icon)
        else:
            s = row.row()
            s.alignment = "RIGHT"
            s.label(text="no in-memory match", icon="QUESTION")
        row.prop(real, "make_local", text="", icon="FILE_TICK")
        row.operator("filelink.examine_pick_source", text="",
                    icon="FILEBROWSER").index = item.ref_index
        row.operator("filelink.examine_search_folder", text="",
                    icon="VIEWZOOM").index = item.ref_index


class _SceneFeaturePanel:
    """Shared bl_* attributes for the legacy-feature Scene sub-panels (Make
    Local, Duplicate Materials, Orphans, Geometry, Utilities) — migrated off
    the old VIEW_3D N-panel (Batch 5, 2026-06-23) so
    everything lives under Properties > Scene > File & Link Utilities. Each is a child of
    FILELINK_PT_scene_deps, which gives it a native collapse triangle and
    remembers its open/closed state per-file, same as the N-panel did."""
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "FILELINK_PT_scene_deps"


class FILELINK_PT_current_file_data(_SceneFeaturePanel, bpy.types.Panel):
    """The Health dashboard (v0.3.x, project_flow_redesign) — was the instant
    "what is this file" summary; now an adaptive metrics readout that shows
    ``baseline → now`` deltas as the addon works through issues. Size-on-disk
    and linked libraries show instantly; render RAM/VRAM appear once profiled/
    scanned; duplicate-material/mesh and issue counts appear once their own
    scan surfaces a non-zero value. Baseline is "since you opened the file"
    (reset by the load_post handler); see ``ops.metrics``."""

    bl_label = "Current File Data"
    bl_idname = "FILELINK_PT_current_file_data"
    bl_order = 0

    # status -> the fixed-color icon that stands in for coloured text (Blender
    # panels can't colour label text; only red via alert). COLORSET_*_VEC are
    # baked-colour dots, theme-independent. "neutral" gets a blank spacer so
    # every value column still lines up.
    _STATUS_DOT = {"good": "COLORSET_03_VEC", "attention": "COLORSET_01_VEC",
                   "neutral": "BLANK1"}

    def draw(self, context):
        from ..ops import metrics

        layout = self.layout
        wm = context.window_manager
        fname = bpy.path.basename(bpy.data.filepath) or "(unsaved)"
        layout.label(text=fname, icon="FILE_BLEND")  # version lives in the panel header

        _t, miss, absol = metrics.library_stats()
        # Two columns when there's room; one when the Properties editor is
        # narrow (delta strings like "8.6 → 6.9 GB (−1.7)" need the width).
        wide = bool(context.region) and context.region.width >= 400
        grid = layout.grid_flow(row_major=True, columns=2 if wide else 1,
                                even_columns=True, align=False)
        for key, label, unit, base, cur in metrics.rows(wm):
            st = metrics.status(key, base, cur, missing=miss)
            cell = grid.row(align=True)
            cell.label(text="", icon=self._STATUS_DOT[st])
            cell.label(text=label)
            val = cell.row()
            val.alignment = "RIGHT"
            val.alert = st == "attention"  # the one native text colour: red
            detail = ""
            if key == "linked_libs":
                extra = ([f"{miss} missing"] if miss else []) + \
                        ([f"{absol} absolute"] if absol else [])
                detail = f"  ({', '.join(extra)})" if extra else ""
            if cur is None:
                val.label(text="—")
            elif base is None or base == cur:
                val.label(text=metrics.fmt(unit, cur) + detail)
            else:
                tail = "  ✓" if cur == 0 else f"  ({metrics.delta_str(unit, base, cur)})"
                val.label(text=f"{metrics.fmt(unit, base)} → {metrics.fmt(unit, cur)}{tail}")

        # Scan Dependencies / Check Link Chain reads the .blend FROM DISK (offline
        # BAT), so it reflects the last SAVED state — unsaved relinks/fixes won't
        # show until you save. Warn when the file is dirty so a stale "missing
        # link" isn't confusing.
        if bpy.data.filepath and bpy.data.is_dirty:
            warn = layout.row()
            warn.alert = True
            warn.label(text="Unsaved changes — save before Check Link Chain (it reads "
                       "from disk)", icon="ERROR")


def _analyze_step_status_icon(wm, step_key: str, has_run: bool) -> str:
    """Per-button status icon (Phase 3 item 5, 2026-06-25: "to the LEFT of each
    Analyze button, a small progress/status indicator" — replaces the old
    separate vertical step-status list).

    Fixed 2026-06-25 (user report: "the status icons... have gone missing...
    they should ALWAYS be visible, so the user knows which button(s) he has
    already used") — this used to look up ONLY the Analyze-All run's own
    per-step collection, which stays empty until Analyze All is clicked at
    least once, so every individually-clicked button showed a permanent blank
    icon. Now: the Analyze-All collection still wins while a step is actually
    ``running`` or just ``error``-ed (transient, only meaningful during/right
    after a run); otherwise fall back to ``has_run`` — whether this check's
    OWN data shows it has ever been run, individually or not."""
    for row in wm.filelink_analyze_steps:
        if row.key == step_key and row.status in ("running", "error"):
            return _ANALYZE_STEP_ICON[row.status]
    return "CHECKMARK" if has_run else "RADIOBUT_OFF"


def _fmt_count(label: str, detail: str) -> str:
    """``"Circular references (3)"`` for a plain count, ``"Duplicate
    Materials: 0 (0 Local & 0 Linked)"`` for a feature's own richer detail
    string (parens would double up)."""
    return f"{label} ({detail})" if detail.lstrip("-").isdigit() else f"{label}: {detail}"


def _f7_dependency_summary(nodes) -> str:
    """Check Link Chain's own rollup (Phase 3c, 2026-06-25): every severity
    tier's CATEGORY children (Circular references / Missing libraries / ...),
    skipping the File map node and the tier wrappers themselves — the issue
    counts are what answers "is this file safe," not the file/link totals
    the File map row carries."""
    parts = []
    for node in nodes:
        if node.key == "f7:filemap":
            continue
        for child in node.children:
            if child.detail:
                parts.append(_fmt_count(child.label, child.detail))
    if not parts:
        return "✓ no dependency issues found"
    text = " · ".join(parts[:5])
    if len(parts) > 5:
        text += f" · +{len(parts) - 5} more"
    return text


def _feature_has_run(wm, feature: str) -> bool:
    """Cheap "has this stashed report/tree feature ever run" check (no JSON
    parse needed) — drives the Analyze button's status icon (item 9,
    2026-06-25) for the features whose headline ``_draw_report_detail`` draws
    on its own, so ``_analyze_row`` can't infer it from a summary string."""
    from ..ops.report_store import data_prop

    return bool(getattr(wm, data_prop(feature), ""))


# feature -> (last raw JSON string seen, its parsed (has_run, nodes) result).
# _draw_report_detail calls _feature_tree_nodes UNCONDITIONALLY on every panel
# redraw (by design -- see its own docstring), which was fine while reports
# stayed small. Real crash, 2026-07-09: Check Materials on a file with heavy
# near-duplicate materials (1410 findings) meant every single redraw did a
# full JSON parse + tree rebuild of a ~1400-node report, not just on toggle
# or after a new scan. A stashed report only ever changes when a scan re-runs
# (report_store writes a brand new raw string then), so a plain string-equality
# check against the last-seen raw is a safe, exact cache key -- no risk of
# showing stale data after a real rescan, just skips redundant reparses of the
# SAME data across redraws in between.
_tree_nodes_cache: dict[str, tuple[str, tuple[bool, list]]] = {}


def _feature_tree_nodes(wm, feature: str) -> tuple[bool, list]:
    """``(has_run, nodes)`` for a stashed report/tree feature. ``has_run``
    distinguishes "never scanned" (hide the rollup entirely) from "scanned,
    found nothing" (negative-output: show a flat ✓ line) — both
    :func:`_report_headline` and :func:`_draw_report_detail` need that same
    distinction, so it's factored out once rather than duplicating the
    raw-fetch/parse dance."""
    from ..core.report import Report
    from ..core.tree import nodes_from_json, report_to_tree
    from ..ops.report_store import TREE_FEATURES, data_prop

    raw = getattr(wm, data_prop(feature), "")
    if not raw:
        return False, []
    cached = _tree_nodes_cache.get(feature)
    if cached is not None and cached[0] == raw:
        return cached[1]
    try:
        if feature == "f7chain":
            # The LOCAL half of posing_override/posing_modifier duplicates the
            # grouped-by-character picker drawn right below by
            # _draw_flatten_candidates (the two used to be separate buttons —
            # merged into "Find Flattenable Links" 2026-06-26, docs/TODO.md
            # #41) -- drop just those rows. REMOTE findings (an object several
            # hops deep, in a file the live picker can never see -- it only
            # reads bpy.data.objects of whichever file is open) have no other
            # home and are kept; the underlying stashed Report is untouched
            # either way (remote_posing_files still reads the full original).
            import bpy

            from ..core.linkchain import drop_local_posing_findings

            report = drop_local_posing_findings(Report.from_json(raw), bpy.data.filepath)
            nodes = report_to_tree(report)
        else:
            nodes = (nodes_from_json(raw) if feature in TREE_FEATURES
                     else report_to_tree(Report.from_json(raw)))
    except Exception:
        return False, []
    result = (True, nodes)
    _tree_nodes_cache[feature] = (raw, result)
    return result


def _f7chain_headline(wm, nodes) -> tuple[str, list]:
    """f7chain's flat overview line, with the flattenable count made LIVE
    (docs/TODO.md Group 11 #47, the standing summary-propagation rule) —
    "AA of YY flattenable" instead of the static YY baked in at scan time,
    where AA is however many are still pending after any Flatten Selected
    run. Substitutes the known exact substring `core.linkchain.
    build_chain_report` writes rather than a generic parse -- this module
    authors both sides of that string, so an exact match is reliable.

    Skips BOTH the overview node AND the trailing "clean" node (docs/TODO.md
    item 46m, 2026-07-04) when nothing was found — `core.linkchain.
    build_chain_report` still adds a "No multi-hop link chains or flattenable
    overrides found" Finding for that case (kept for its own test coverage),
    but the overview line above already spells out the same zero counts, so
    showing it again in the inline body just earns a pointless expand arrow."""
    first = nodes[0]
    label = first.label
    from ..core.report import Report
    from ..ops.report_store import data_prop

    try:
        report = Report.from_json(getattr(wm, data_prop("f7chain"), ""))
        overview = next((f for f in report.findings if f.category == "overview"), None)
        total = overview.data.get("flattenable_total") if overview else None
    except Exception:
        total = None
    if total is not None:
        remaining = max(0, total - wm.filelink_flatten_done - wm.filelink_flatten_failed)
        old = f"{total} flattenable (override+transform)"
        new = f"{remaining} of {total} flattenable (override+transform)"
        label = label.replace(old, new, 1)
    skip = [first]
    clean = next((n for n in nodes if n.key.startswith("f7chain:clean")), None)
    if clean is not None:
        skip.append(clean)
    return label, skip


def _report_headline(nodes, feature: str, wm) -> tuple[str, object | None]:
    """``(headline_text, node_to_skip)`` for a stashed report/tree feature's
    top-level nodes. ``node_to_skip`` is the exact node whose own ``.label``
    the headline already quotes verbatim (a flat clean/overview row) — the
    inline disclosure below must leave it out of its body, or the same line
    shows twice (user feedback, 2026-06-25 item e). ``None`` when the
    headline is a derived rollup that doesn't correspond to any one node
    (Check Link Chain's tier-count line), or there's nothing to deduplicate.

    A flat clean/overview headline (when a feature already writes one, e.g.
    "12 override loop(s) · ...") IS the one-liner; otherwise join the
    top-level issue categories' own counts, falling back to the report's own
    Summary sentence when there's nothing to break down (e.g. "0 orphan, 0
    fake-only, 0 identical group(s)")."""
    if feature == "f7":
        return _f7_dependency_summary(nodes), None
    if feature == "f7chain":
        return _f7chain_headline(wm, nodes)
    # Node keys are "<report.feature>:<category>[:i]" — report.feature's own
    # casing doesn't always match the lowercase key this panel stashes/looks
    # features up under (e.g. geometry_dedup's Report uses "F5" while this is
    # called with "geo"; f4_orphans/f2_makelocal/f3_materials use "F4"/"F2"/
    # "F3"). Derive the real prefix from the data instead of assuming it
    # equals `feature`, or the "exclude Summary" check below silently never
    # matches and a bare "Summary (N)" leaks into the rollup.
    tail = nodes[0].key.split(":", 1)[0] + ":"
    first = nodes[0]
    if not first.children and (first.key.startswith(tail + "overview")
                                or first.key.startswith(tail + "clean")):
        return first.label, first
    summary_key = f"{tail}summary"
    cats = [n for n in nodes if n.detail and n.key != summary_key]
    if not cats:
        summary = next((n for n in nodes if n.key == summary_key), None)
        if summary and summary.children:
            # docs/TODO.md item 46d, 2026-07-04: when the ONLY node is the
            # "Summary" category wrapper (e.g. Make Local's own single count
            # line, nothing else found), `skip=summary` so the inline body
            # doesn't ALSO show a redundant "Summary" row repeating the exact
            # same text underneath a pointless expand arrow — same standard
            # every other single-line clean/overview headline already follows.
            # Previously `skip=None` here, the one place that didn't.
            return summary.children[0].label, summary
        if summary:
            return summary.label, summary
        return "✓ nothing found", None
    parts = [_fmt_count(n.label, n.detail) for n in cats[:4]]
    if len(cats) > 4:
        parts.append(f"+{len(cats) - 4} more")
    return " · ".join(parts), None


def _draw_report_detail(layout, wm, feature: str) -> None:
    """One Analyze button's report result: a single row carrying BOTH the
    one-line headline AND its own expand arrow — no separate "Details" row
    (item a, 2026-06-25). When expanded, every remaining category draws via
    the SAME ``FILELINK_UL_tree``/``FILELINK_PG_tree_row`` machinery the
    Reports tab uses (Group 12 Phase 4, 2026-07-03) — closes the third
    independent manual tree-renderer this project had accumulated, and its own
    "blank rows on a deeply-expanded tree" exposure along with it. Collapsed
    by default via the inline-only ``filelink_detail_expanded`` key set
    (independent of each feature's own ``exp_prop`` — the dedicated Reports
    tab pre-seeds THAT one expanded, which would defeat "starts collapsed"
    here). The one node the headline already quotes verbatim is left out of
    the body so it isn't shown twice (item e); when nothing remains beyond the
    headline, no arrow is drawn at all — there's nothing left to disclose
    (item f).

    Each of the ~7 features calling this gets its OWN small rows collection
    (``ops.report_store.inline_rows_prop``), since several can be expanded
    SIMULTANEOUSLY in the same Analyze panel — unlike the Reports tab, which
    only ever shows one active feature. Refilled UNCONDITIONALLY on every
    draw (cheap: the exact same nodes-fetch + ``flatten_visible`` work the old
    manual loop already redid every draw, just filling a small
    ``CollectionProperty`` instead of instantiating N ``layout.row()``
    widgets) — this sidesteps needing a rebuild-on-toggle hook for a prop
    that's shared, namespaced-by-feature-prefix, across all 7 features; every
    toggle already triggers a redraw, and the next draw call reads current
    state fresh regardless of which row anywhere caused it."""
    from ..ops import report_store

    has_run, nodes = _feature_tree_nodes(wm, feature)
    if not has_run:
        return
    col = layout.column(align=True)
    row = col.row(align=True)
    row.separator(factor=2.2)
    if not nodes:
        row.label(text="✓ nothing found")
        return

    headline, skip = _report_headline(nodes, feature, wm)
    # `skip` is usually one node; f7chain's own headline (item 46m) can name
    # several (the overview line AND a now-redundant trailing "clean" node).
    skip_nodes = skip if isinstance(skip, list) else ([] if skip is None else [skip])
    remaining = [n for n in nodes if not any(n is s for s in skip_nodes)]
    if not remaining:
        row.label(text=headline)
        return

    expanded = set(filter(None, wm.filelink_detail_expanded.split("\n")))
    root_key = f"{feature}:__inline_root__"
    is_open = root_key in expanded
    op = row.operator("filelink.row_toggle", text="",
                       icon="TRIA_DOWN" if is_open else "TRIA_RIGHT", emboss=False)
    op.key = root_key
    row.label(text=headline)
    if not is_open:
        return

    report_store.rebuild_inline_detail_rows(wm, feature, remaining, expanded)
    rows_prop = report_store.inline_rows_prop(feature)
    n = len(getattr(wm, rows_prop))
    if n:
        col.template_list(
            "FILELINK_UL_tree", f"inline_{feature}",
            wm, rows_prop,
            wm, report_store.inline_active_prop(feature),
            rows=min(12, max(3, n)),
        )


def _missing_textures_headline(wm, narrow: bool) -> str:
    """The Missing Textures section's own header summary, factored out so the
    Analyze button can show the same line inline (Phase 3c)."""
    n_missing = len(wm.filelink_broken_imgs)
    n_linked = len(wm.filelink_linked_missing_imgs)
    scanned = wm.filelink_tex_scanned
    found = max(wm.filelink_tex_initial_missing - n_missing, 0)
    matched = sum(1 for it in wm.filelink_broken_imgs if it.target)

    title = "Missing Materials/Textures"
    linked_bit = f"{n_linked} linked" if n_linked else ""
    if not scanned:
        return ""
    if n_missing == 0:
        head = f"{title} — none missing locally" if n_linked else f"{title} — none missing"
        if found:
            head += f" ({found} relinked)"
        if linked_bit:
            head += f", {linked_bit}"
        return head
    if narrow:
        head = f"Missing — {n_missing}✗"
        if matched:
            head += f" {matched}⇒"
        if found:
            head += f" {found}✓"
        if linked_bit:
            head += f" {linked_bit}"
        return head
    bits = [f"{n_missing} missing"]
    if matched:
        bits.append(f"{matched} matched")
    if found:
        bits.append(f"{found} relinked")
    if linked_bit:
        bits.append(linked_bit)
    return f"{title} — " + ", ".join(bits)


def _duplicate_textures_headline(wm, narrow: bool) -> str:
    """The Duplicate Materials/Textures section's own header summary,
    factored out so the Analyze button can show the same line inline."""
    scanned = wm.filelink_dup_scanned
    families = wm.filelink_dup_families
    mats = len({row.material or "(no material)" for row in families})
    removable = wm.filelink_dup_removable
    linked = wm.filelink_dup_linked
    conflicts = wm.filelink_dup_conflicts
    if not scanned:
        return ""
    if not len(families) and not conflicts:
        return "Image Content — ✓ none found"
    if narrow:
        return f"Image Content — {mats} mat / {removable} tex"
    bits = [f"{mats} material(s)", f"{removable} texture(s) redundant"]
    if linked:
        bits.append(f"{linked} linked (stay in library)")
    if conflicts:
        bits.append(f"{conflicts} kept separate")
    return "Image Content — " + ", ".join(bits)


def _duplicates_has_run(wm) -> bool:
    """Item 3, 2026-06-25: "Find Duplicates" status icon — true once ANY of
    the 4 folded-in scans has data, regardless of which one was clicked."""
    return bool(wm.filelink_datablock_scanned or wm.filelink_mat_scanned
                or _feature_has_run(wm, "geo") or wm.filelink_dup_scanned)


def _duplicates_scanned_count(wm) -> int:
    return sum([bool(wm.filelink_datablock_scanned), bool(wm.filelink_mat_scanned),
                _feature_has_run(wm, "geo"), bool(wm.filelink_dup_scanned)])


def _duplicates_overview_summary(wm) -> str:
    """"Find Duplicates" collapsed-header summary (docs/TODO.md item 46j,
    2026-07-04) — how many of the 4 folded-in scans have run, not each one's
    own removable-count breakdown (each keeps its OWN live headline, visible
    once this section is expanded)."""
    if not _duplicates_has_run(wm):
        return "Find Duplicates"
    return f"Find Duplicates — {_duplicates_scanned_count(wm)}/4 scan(s) run"


def _duplicates_status_icon(wm) -> str:
    """Tri-state status icon for the "Find Duplicates" header (user report,
    2026-07-14: this section was the only collapsible group missing the
    not-run/done icon its Analyze-row siblings all show) — RADIOBUT_OFF (none
    of the 4 sub-scans have run), CHECKMARK (all 4 have), or RADIOBUT_ON as
    the "some but not all" middle state (a 2-state icon can't represent a
    group of independently-runnable sub-scans)."""
    scanned = _duplicates_scanned_count(wm)
    if scanned <= 0:
        return "RADIOBUT_OFF"
    if scanned >= 4:
        return "CHECKMARK"
    return "RADIOBUT_ON"


def _draw_duplicates(layout, wm, narrow: bool) -> None:
    """Find Duplicates — a collapsed-by-default sub-section (docs/TODO.md
    item 46j, 2026-07-04) wrapping the 4 scans this trigger used to run as
    one black box (Data-blocks/Materials/Geometry/Image Content). Expanding
    it reveals each scan's OWN button — so a crash-prone scanner (item 45)
    doesn't block running the other 3 — plus its own results area, unchanged
    internally: each ``_draw_*_dups`` already gates on its own ``*_scanned``
    flag and draws nothing until ITS OWN button has been clicked. "Find All
    Duplicates" (the header's own action button) still runs all 4 in
    sequence via the existing ``filelink.find_duplicates`` sequencer,
    waiting for each step's UI update before starting the next — unchanged,
    just relocated from its own top-level row into this header."""
    expanded = set(filter(None, wm.filelink_detail_expanded.split("\n")))
    key = "duplicates:all"
    is_open = key in expanded
    outer = layout.box().column(align=True)
    _draw_group_header(
        outer, key=key, prop="filelink_detail_expanded", is_exp=is_open,
        label=_duplicates_overview_summary(wm), icon="LIBRARY_DATA_OVERRIDE",
        status_icon=_duplicates_status_icon(wm),
        action=lambda r: r.operator("filelink.find_duplicates",
                                    text="Find All Duplicates", icon="PLAY"))
    if not is_open:
        return
    col = outer.column(align=True)

    def _child_button(opname: str, step_key: str, text: str, icon: str, has_run: bool):
        crow = col.row(align=True)
        crow.label(text="", icon=_analyze_step_status_icon(wm, step_key, has_run))
        crow.operator(opname, text=text, icon=icon)

    _child_button("filelink.scan_datablock_dups", "find_duplicate_datablocks",
                  "Find Duplicate Data-blocks", "LIBRARY_DATA_OVERRIDE",
                  bool(wm.filelink_datablock_scanned))
    _draw_datablock_dups(col, wm)
    col.separator()
    _child_button("filelink.material_dedup", "find_duplicate_materials",
                  "Find Duplicate Materials", "MATERIAL", bool(wm.filelink_mat_scanned))
    _draw_material_dups(col, wm)
    col.separator()
    _child_button("filelink.instance_geometry", "find_duplicate_geometry",
                  "Find Duplicate Geometry", "MESH_DATA", _feature_has_run(wm, "geo"))
    _draw_geo_dups(col, wm)
    col.separator()
    _child_button("filelink.scan_content_dups", "find_duplicate_content",
                  "Find Duplicate Textures", "IMAGE_DATA", bool(wm.filelink_dup_scanned))
    _draw_duplicate_textures(col, wm, narrow)
    # Resolution Variants folded into this group (2026-07-14,
    # project_flow_redesign) — it's redundant-material data too, so it belongs
    # in the Deduplicate phase rather than floating among unrelated checks. It
    # stays OUT of the "Find All Duplicates" sequencer in the header (a
    # different kind of analysis — multi-res footprint, not strict duplicates)
    # and keeps its own child button + results here.
    col.separator()
    _child_button("filelink.scan_res_variants", "find_resolution_variants",
                  "Find Resolution Variants", "FULLSCREEN_ENTER",
                  _feature_has_run(wm, "f6res"))
    _draw_res_variants(col, wm)


def _datablock_dups_headline(wm) -> str:
    """The Duplicate Data-blocks section's own header summary, factored out
    so the Analyze button can show the same line inline."""
    families = wm.filelink_datablock_families
    scanned = wm.filelink_datablock_scanned
    removable = wm.filelink_datablock_removable
    conflicts = wm.filelink_datablock_conflicts
    skipped = len([ln for ln in wm.filelink_datablock_skipped_text.split("\n") if ln])
    if not scanned:
        return ""
    if not len(families) and not conflicts and not skipped:
        return "Data-blocks — ✓ none found"
    kinds = len({row.kind for row in families})
    bits = [f"{kinds} kind(s)", f"{removable} removable"]
    if conflicts:
        bits.append(f"{conflicts} kept separate")
    if skipped:
        bits.append(f"{skipped} skipped")
    return "Data-blocks — " + ", ".join(bits)


def _reconnect_headline(wm) -> str:
    """The Datablock Reconnect section's own header summary, factored out so
    the Analyze button can show the same line inline."""
    rows = wm.filelink_missing_blocks
    scanned = wm.filelink_missing_scanned
    if not scanned:
        return ""
    if not len(rows):
        return "Datablock Reconnect — none found"
    libs = len({r.library for r in rows})
    staged = sum(1 for r in rows if r.selected and r.target)
    return f"Datablock Reconnect — {len(rows)} missing, {libs} group(s), {staged} staged"


def _all_missing_summary(wm) -> str:
    """"Find All Missing" runs the broken-library-link, datablock-reconnect AND
    missing-texture scans (2026-07-14 — textures used to be wrongly excluded
    from this meta-button); combine their counts into one line."""
    if not wm.filelink_missing_scanned:
        return ""
    broken = len(wm.filelink_broken_libs)
    missing = len(wm.filelink_missing_blocks)
    tex = len(wm.filelink_broken_imgs) if wm.filelink_tex_scanned else 0
    if not broken and not missing and not tex:
        return "✓ nothing missing"
    bits = [f"{broken} broken link(s)", f"{missing} missing data-block(s)"]
    if tex:
        bits.append(f"{tex} missing texture(s)")
    return ", ".join(bits)


def _broken_links_headline(wm) -> str:
    """Find Broken Library Links' own header summary, mirrors
    ``_reconnect_headline`` (Group 11 #43, 2026-06-26) so the Analyze button
    can show the same line inline instead of the generic tree disclosure
    (which would now just double-display the same rows a second way, since
    the interactive UIList below already shows everything actionable)."""
    if not _feature_has_run(wm, "f7links"):
        return ""
    coll = wm.filelink_broken_libs
    if not len(coll):
        return "Broken Library Links — none found"
    matched = sum(1 for item in coll if item.target)
    return f"Broken Library Links — {len(coll)} missing, {matched} matched"


def _path_normalization_headline(wm) -> str:
    """Path Normalization's own header summary, mirrors ``_reconnect_headline``
    (Group 11 #43, 2026-06-26). Counts renames from the f7fix report + the
    duplicate-library/absolute-path GROUPS from the interactive checkbox
    lists below (the actionable surface) — deliberately skips drawing the
    read-only f7fix tree itself, same reasoning as Broken Library Links."""
    from ..core.report import Report
    from ..ops.report_store import data_prop

    if not _feature_has_run(wm, "f7fix"):
        return ""
    try:
        report = Report.from_json(getattr(wm, data_prop("f7fix"), ""))
        renames = sum(1 for f in report.findings if f.category == "normalize_path")
    except Exception:
        renames = 0
    dup_groups = len({item.group for item in wm.filelink_dup_lib_members})
    abs_groups = len({item.group for item in wm.filelink_abs_path_members})
    if not renames and not dup_groups and not abs_groups:
        return "Path Normalization — ✓ clean"
    bits = []
    if renames:
        bits.append(f"{renames} path(s) to normalize")
    if dup_groups:
        bits.append(f"{dup_groups} duplicate-library group(s)")
    if abs_groups:
        bits.append(f"{abs_groups} absolute-path drive group(s)")
    return "Path Normalization — " + ", ".join(bits)


def _path_normalization_clean(wm) -> bool:
    """Whether the LAST Check Library Paths scan found nothing to normalize —
    docs/TODO.md item 46g, 2026-07-04: the "Normalize" action button used to
    stay visible even on a clean result, offering a no-op. Recomputes the
    same three counts as :func:`_path_normalization_headline` rather than
    string-matching its "✓ clean" text."""
    from ..core.report import Report
    from ..ops.report_store import data_prop

    if not _feature_has_run(wm, "f7fix"):
        return False
    try:
        report = Report.from_json(getattr(wm, data_prop("f7fix"), ""))
        renames = sum(1 for f in report.findings if f.category == "normalize_path")
    except Exception:
        renames = 0
    dup_groups = len({item.group for item in wm.filelink_dup_lib_members})
    abs_groups = len({item.group for item in wm.filelink_abs_path_members})
    return not renames and not dup_groups and not abs_groups


def _normalize_action_button(row) -> None:
    """The "Normalize" action for Path Normalization's Analyze row (Group 11
    #43) — a tiny named function rather than a lambda since it needs to set
    ``apply=True`` on the returned operator properties, which a single-
    expression lambda can't do."""
    row.operator("filelink.normalize_library_paths",
                 text="Normalize", icon="CHECKMARK").apply = True


def _flatten_candidates_summary(wm) -> str:
    """``filelink_flatten_plans_json`` is non-empty (even if "{}") once a
    scan has run, so its presence — not the row count — is the "has this
    been run" signal (negative-output principle: say so when nothing was
    found, don't just look identical to never-run)."""
    if not wm.filelink_flatten_plans_json:
        return ""
    rows = wm.filelink_flatten_candidates
    if not len(rows):
        return wm.filelink_flatten_remote_note or "✓ no flattenable characters found"
    rigs = len({r.rig for r in rows})
    ready = sum(1 for r in rows if r.ready)
    return f"{len(rows)} part(s) across {rigs} rig(s)/character(s) — {ready} ready, {len(rows) - ready} blocked"


def _resource_summary(wm) -> str:
    return wm.filelink_resource_totals


def _profile_render_summary(wm) -> str:
    ram = wm.filelink_profiled_ram
    return f"Real peak RAM: {ram}" if ram else ""


_RESOURCE_COL_LABELS = {"ram": "RAM", "vram": "VRAM", "disk": "Disk"}


def _draw_resource_breakdown(layout, wm):
    """The by-type RAM/VRAM/disk breakdown, rolled up as a child directly below
    the Analyze Memory/Disk button's inline summary (replaces the standalone
    Resource Analyzer panel — same template_list + Export, just relocated so
    the detail lives right under the totals it explains). Real aligned RAM/
    VRAM/disk columns + a clickable column-header sort (docs/TODO.md #15,
    2026-06-27) — each header button re-sorts the top-level type groups by
    that metric (cheap: reuses the last scan's cached items, no re-scan)."""
    if not wm.filelink_resource_tree:
        return
    col = layout.column(align=True)
    hint = col.row(align=True)
    hint.separator(factor=2.2)
    hint.label(text="RAM / VRAM estimated; disk accurate", icon="INFO")

    header = col.row(align=True)
    header.label(text="")  # flexible spacer matching each row's indent/triangle/label area
    sort_by = wm.filelink_resource_sort
    for sort_col, key in zip(_resource_columns(header), _RESOURCE_COL_LABELS):
        op = sort_col.operator("filelink.resource_sort_by", text=_RESOURCE_COL_LABELS[key],
                               depress=(sort_by == key))
        op.metric = key.upper()

    col.template_list(
        "FILELINK_UL_tree", "resource",
        wm, "filelink_resource_rows",
        wm, "filelink_resource_index",
        rows=8, sort_lock=True,
    )
    erow = col.row(align=True)
    erow.separator(factor=2.2)
    erow.operator("filelink.export_report", text="Export…", icon="EXPORT").source = "resource"


def _analyze_row(layout, wm, step_key, opname, text, icon, summary="", has_run=None,
                  draw_action=None):
    """One Analyze trigger button, full-width (Phase 3 feedback item 2a,
    2026-06-25: one per row so each gets a status icon AND a result line),
    with its inline result summary directly below when there's one to show.

    ``has_run`` drives the status icon (item 9, 2026-06-25) — defaults to
    "the summary text is non-empty" (true for every feature whose headline
    this draws directly); the tree-based features that now draw their own
    headline inside ``_draw_report_detail`` instead must pass it explicitly.

    ``draw_action``: optional ``callable(row)`` that draws ONE narrow extra
    operator on the right side of the summary row (e.g. "Reconnect Selected")
    instead of as its own full-width button in a box below (Group 11 #43,
    2026-06-26) — for sections whose fix action belongs right next to its
    result line, per the user's own screenshots."""
    if has_run is None:
        has_run = bool(summary)
    row = layout.row(align=True)
    row.label(text="", icon=_analyze_step_status_icon(wm, step_key, has_run))
    op = row.operator(opname, text=text, icon=icon)
    if summary:
        srow = layout.row(align=True)
        srow.separator(factor=2.2)
        srow.label(text=summary)
        if draw_action is not None:
            action_row = srow.row()
            action_row.scale_x = 0.7
            draw_action(action_row)
    return op


def _draw_deform_check(layout, wm) -> None:
    """Check Armature Deformation's results (Group 16, 2026-07-09) — a flat
    selectable list, one row per flagged object. Detection only: the
    ``selected`` checkboxes are read-and-write today but nothing consumes them
    yet — they're there for a later fix-pass operator to read, per the user's
    explicit "detection first" call, so this section deliberately has no
    Apply/Fix button."""
    if not wm.filelink_deform_scanned:
        return
    rows = wm.filelink_deform_rows
    box = layout.box().column(align=True)
    if not len(rows):
        box.label(text="✓ no armature-deformation outliers found", icon="CHECKMARK")
        return
    total_verts = sum(r.vertex_count for r in rows)
    box.label(text=f"{len(rows)} object(s), {total_verts} vertex(es) flagged", icon="ERROR")
    box.template_list(
        "FILELINK_UL_deform_rows", "",
        wm, "filelink_deform_rows",
        wm, "filelink_deform_index",
        rows=min(10, max(3, len(rows))),
    )


def _flattenable_overrides_summary(wm) -> str:
    """The "Flattenable overrides" subgroup's own live outcome line —
    docs/TODO.md Group 11 #47's standing summary-propagation rule: every
    action that changes the count updates this AND the top overview line
    (see _f7chain_headline) together, not just one of them."""
    rows = wm.filelink_flatten_candidates
    total = len(rows)
    done = wm.filelink_flatten_done
    failed = wm.filelink_flatten_failed
    return f"Flattenable overrides — {total} original, {done} flattened, {failed} failed"



def _draw_flatten_candidates(layout, wm):
    """Phase 4-B picker (Group 12 Phase 2 — now virtualized via UIList).

    The outer box + header + control row are still drawn manually (they're
    not part of the scrollable list); the per-group/per-member rows are
    rendered by ``FILELINK_UL_flatten_picker`` from the pre-built
    ``wm.filelink_flatten_picker_rows`` collection.  That collection is
    rebuilt by ``ops.linkchain.rebuild_flatten_picker_rows`` after every
    scan/toggle/evaluate/flatten — never on each redraw."""
    if not len(wm.filelink_flatten_candidates):
        return

    expanded = set(filter(None, wm.filelink_flatten_expanded.split("\n")))
    all_key = "__flattenable_overrides__"
    is_open = all_key in expanded

    outer = layout.box().column(align=True)
    hrow = outer.row(align=True)
    hop = hrow.operator("filelink.row_toggle", text="",
                        icon="TRIA_DOWN" if is_open else "TRIA_RIGHT", emboss=False)
    hop.key, hop.prop = all_key, "filelink_flatten_expanded"
    hrow.label(text=_flattenable_overrides_summary(wm))
    if not is_open:
        return

    crow = outer.row(align=True)
    crow.prop(wm, "filelink_flatten_make_local", text="Make Local")
    crow.prop(wm, "filelink_flatten_make_copy", text="Make Copy")
    crow.operator("filelink.evaluate_selected", text="Evaluate Selected", icon="VIEWZOOM")
    crow.operator("filelink.flatten_selected", text="Flatten Selected", icon="CHECKMARK")

    n = len(wm.filelink_flatten_picker_rows)
    if n:
        outer.template_list(
            "FILELINK_UL_flatten_picker", "",
            wm, "filelink_flatten_picker_rows",
            wm, "filelink_flatten_picker_active",
            rows=min(12, max(3, n)),
        )

    # The detailed per-property Flatten Plan preview/apply result — stashed by
    # "Evaluate Selected" / "Flatten Selected" into the f7flatten report slot.
    _draw_report_detail(layout, wm, "f7flatten")


def _draw_phase_header(layout, name: str, intent: str, icon: str) -> None:
    """A visual divider between the Analyze pipeline's phases (2026-07-14,
    project_flow_redesign) — a separator, then the phase name (with its icon)
    and a muted one-line intent, so the flat button stack reads as an ordered
    Connect → Restructure → Deduplicate → Purge → Measure sequence (fix what's
    broken before optimizing what's redundant) instead of an undifferentiated
    list. The intent line uses ``active = False`` for de-emphasis rather than
    ``enabled = False``, which would read as a disabled control."""
    layout.separator()
    col = layout.column(align=True)
    col.label(text=name, icon=icon)
    sub = col.row()
    sub.active = False
    sub.label(text=intent)


def _draw_advisory_note(layout, text: str, *, show: bool) -> None:
    """A short "detection-only — here's what to do" line under an advisory
    (no-auto-fix) check (2026-07-14) — shown once the check has run. Matches
    the Missing-Textures / Retarget-Library standard of telling the user what
    must happen by hand when the addon deliberately can't fix something
    itself, so an advisory check isn't a silent dead end."""
    if not show:
        return
    row = layout.row(align=True)
    row.separator(factor=2.2)
    row.active = False
    row.label(text=text, icon="INFO")


class FILELINK_PT_analyze(_SceneFeaturePanel, bpy.types.Panel):
    """Phase 3a (2026-06-25) — the second named section: every "look for
    problems in the CURRENT file" trigger, in one place, plus an Analyze All
    sequencer (``ops.analyze_all``) that runs them in order. Each button here
    fills the SAME WM state its box used to fill directly — relocating the
    trigger doesn't change what runs; the populated list/report still draws in
    its existing box below.

    Button layout (v0.2.59, 2026-06-25 user request — Phase 3 feedback items
    a/b/c/e/f): one full-width button per row (not paired) so each can carry
    its own inline result summary directly below it — the Phase 3c "per-
    button inline result" design, no longer just a placeholder. Analyze
    Memory/Disk, Make Local Impact, and Profile Render are split below a
    separator (they measure footprint/impact, not "is something broken").
    "Find All Duplicates" (a NEW grouping button over Materials/Resolution
    Variants/Geometry/Content) is still NOT built — needs real operator code,
    not just a layout change."""

    bl_label = "Analyze This File"
    bl_idname = "FILELINK_PT_analyze"
    bl_order = 1

    def draw(self, context):
        # Ordered as the 6-phase repair pipeline (2026-07-14,
        # project_flow_redesign) — the SAME sequence core.analyze_steps.STEPS
        # runs, so what the user reads top-to-bottom matches what "Analyze All"
        # fills in. Phase A (Understand) = Current File Data + the Analyze-All
        # button; B–F get a _draw_phase_header divider each.
        layout = self.layout
        wm = context.window_manager
        narrow = bool(context.region) and context.region.width < 320

        layout.operator("filelink.analyze_all", icon="PLAY")

        # ---- Phase B · Connect — resolve dangling references first ----
        _draw_phase_header(layout, "Connect", "Fix missing / broken references first",
                           "LIBRARY_DATA_BROKEN")
        _analyze_row(layout, wm, "check_link_chain", "filelink.scan_dependencies",
                     "Check Link Chain", "VIEWZOOM", has_run=_feature_has_run(wm, "f7"))
        _draw_report_detail(layout, wm, "f7")
        # The meta-button that fires all three missing-scans below at once —
        # now including Missing Textures (2026-07-14; it used to skip them).
        _analyze_row(layout, wm, "", "filelink.scan_all_missing",
                     "Find All Missing", "VIEWZOOM", _all_missing_summary(wm))
        _analyze_row(layout, wm, "find_broken_links", "filelink.scan_broken_links",
                     "Find Broken Library Links", "LIBRARY_DATA_BROKEN",
                     _broken_links_headline(wm),
                     draw_action=(lambda r: r.operator(
                         "filelink.relink_selected", text="Relink Selected", icon="FILE_REFRESH"))
                     if len(wm.filelink_broken_libs) else None)
        _draw_broken_links(layout, wm)
        _analyze_row(layout, wm, "find_reconnectable", "filelink.scan_reconnect_targets",
                     "Find Reconnectable Data-blocks", "LIBRARY_DATA_OVERRIDE",
                     _reconnect_headline(wm),
                     draw_action=(lambda r: r.operator(
                         "filelink.reconnect_selected", text="Reconnect Selected", icon="LINKED"))
                     if wm.filelink_missing_scanned and len(wm.filelink_missing_blocks) else None)
        _draw_reconnect(layout, wm)
        _analyze_row(layout, wm, "find_missing_textures", "filelink.scan_broken_textures",
                     "Find Missing Textures", "IMAGE_DATA",
                     _missing_textures_headline(wm, narrow))
        _draw_missing_textures(layout, wm, narrow)
        _analyze_row(layout, wm, "check_library_paths", "filelink.normalize_library_paths",
                     "Check Library Paths", "FILE_REFRESH",
                     _path_normalization_headline(wm),
                     draw_action=_normalize_action_button
                     if _feature_has_run(wm, "f7fix") and not _path_normalization_clean(wm)
                     else None).apply = False
        _draw_path_normalization(layout, wm)

        # ---- Phase C · Restructure — simplify the link graph ----
        _draw_phase_header(layout, "Restructure", "Simplify the link graph", "NODETREE")
        _analyze_row(layout, wm, "audit_file", "filelink.analyze_overrides",
                     "Audit This File", "LIBRARY_DATA_OVERRIDE", has_run=_feature_has_run(wm, "f7live"))
        _draw_report_detail(layout, wm, "f7live")
        # Merged 2026-06-26 (docs/TODO.md #41) -- "Find Flattenable Link
        # Chains" and "Find Flattenable Characters" were really one workflow
        # wearing two buttons; one click now runs both.
        _analyze_row(layout, wm, "find_flattenable_chains", "filelink.find_flattenable_links",
                     "Find Flattenable Links", "LIBRARY_DATA_OVERRIDE",
                     _flatten_candidates_summary(wm))
        _draw_report_detail(layout, wm, "f7chain")
        _draw_flatten_candidates(layout, wm)
        _analyze_row(layout, wm, "", "filelink.make_local",
                     "Make Local", "LIBRARY_DATA_DIRECT",
                     _makelocal_headline(wm), has_run=_feature_has_run(wm, "f2")).apply = False
        _draw_makelocal_picker(layout, wm)
        # Advisory (detection-only) checks — no safe bulk fix, so each gets a
        # "here's what to do by hand" line (2026-07-14) rather than being a
        # silent dead end.
        _analyze_row(layout, wm, "", "filelink.check_materials",
                     "Check Materials", "MATERIAL", has_run=_feature_has_run(wm, "matdiag"))
        _draw_advisory_note(layout, "Read-only — fix flagged shader/node issues by hand in "
                            "the Shading workspace; there's no safe bulk fix.",
                            show=_feature_has_run(wm, "matdiag"))
        _draw_report_detail(layout, wm, "matdiag")
        _analyze_row(layout, wm, "", "filelink.scan_deform_issues",
                     "Check Armature Deformation", "MOD_ARMATURE",
                     has_run=wm.filelink_deform_scanned)
        _draw_advisory_note(layout, "Detection only — reweight flagged vertices to a deform "
                            "bone in Weight Paint; the ticks are for a future fix pass.",
                            show=wm.filelink_deform_scanned and len(wm.filelink_deform_rows))
        _draw_deform_check(layout, wm)

        # ---- Phase D · Deduplicate — shrink redundancy ----
        _draw_phase_header(layout, "Deduplicate", "Shrink redundant data", "DUPLICATE")
        _draw_duplicates(layout, wm, narrow)

        # ---- Phase E · Purge — sweep leftovers once everything else is settled ----
        _draw_phase_header(layout, "Purge", "Remove unreferenced leftovers", "TRASH")
        _analyze_row(layout, wm, "find_orphans", "filelink.scan_orphans",
                     "Find Orphans", "NONE", _orphans_headline(wm)).purge_orphans = False
        _draw_orphans(layout, wm)

        # ---- Phase F · Measure — footprint payoff (not a problem check) ----
        _draw_phase_header(layout, "Measure", "Footprint after cleanup", "DISK_DRIVE")
        _analyze_row(layout, wm, "analyze_memory_disk", "filelink.analyze_resources",
                     "Analyze Memory/Disk", "VIEWZOOM", _resource_summary(wm))
        _draw_resource_breakdown(layout, wm)
        # Profile Render relocated to Utilities (Group 11 #42, 2026-06-26) — it
        # actually renders, more "one-off tool" than "is something broken."


class FILELINK_PT_analyze_external(_SceneFeaturePanel, bpy.types.Panel):
    """Folder-wide link map (graphical) + reverse-dependency check both scan a
    FOLDER you pick, not the current file — different scope from "Analyze
    This File" above, so they live in their own section (user request,
    2026-06-25 item 2: split out of Analyze, titled "Analyze External
    Files"). Content unchanged from the old Analyze panel, just relocated."""

    bl_label = "Analyze External Files"
    bl_idname = "FILELINK_PT_analyze_external"
    bl_order = 2

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager

        pmap = layout.box().column(align=True)
        pmap.label(text="Map a Folder (folder → graph)", icon="NODETREE")
        pmap.prop(context.scene, "filelink_scan_dir", text="")
        pmap.operator("filelink.scan_folder", text="Map Folder → Open Graph",
                      icon="VIEWZOOM").directory = context.scene.filelink_scan_dir
        # Group 11 #46, 2026-06-26: the scan ALSO stashes a flat f1 report
        # (legacy — its real surface is the HTML graph the button above opens)
        # — give it a home here rather than losing access entirely now that
        # the generic Reports selector is gone.
        _draw_report_detail(pmap, wm, "f1")

        rev = layout.box().column(align=True)
        rev.label(text="Safe to delete? (who links this file)", icon="TRASH")
        rev.prop(context.scene, "filelink_dep_target", text="")
        rev.operator("filelink.check_dependents", text="Check What Links This",
                     icon="VIEWZOOM")
        verdict = wm.filelink_dep_verdict
        if verdict == "unsafe":
            vrow = rev.row()
            vrow.alert = True
            vrow.label(text=wm.filelink_dep_verdict_text, icon="ERROR")
        elif verdict == "safe":
            rev.label(text=wm.filelink_dep_verdict_text, icon="CHECKMARK")
        elif verdict == "not_scanned":
            vrow = rev.row()
            vrow.alert = True
            vrow.label(text=wm.filelink_dep_verdict_text, icon="ERROR")


class FILELINK_PT_utilities(_SceneFeaturePanel, bpy.types.Panel):
    bl_label = "Utilities"
    bl_idname = "FILELINK_PT_utilities"
    bl_order = 7
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        from ..prefs import get_prefs

        layout = self.layout
        wm = context.window_manager
        layout.prop(context.scene, "filelink_debug_log")
        layout.operator("filelink.open_preferences",
                        text="Lists & Backups: Add-on Preferences…", icon="PREFERENCES")

        prefs = get_prefs(context)
        if prefs is not None and prefs.idle_scan_enabled:
            secs = getattr(wm, "filelink_idle_seconds", 0.0)
            detected = getattr(wm, "filelink_idle_detected", False)
            layout.separator()
            layout.label(text=f"Idle-scan prototype — {secs:.0f}s since input"
                        + (" (idle)" if detected else ""), icon="TIME")

        # Phase 3 panel consolidation (Group 11 #42, 2026-06-26) — one-off tools that
        # measure/probe rather than "is something broken," relocated here from the old
        # Results holding pen / Analyze panel.
        layout.separator()
        _analyze_row(layout, wm, "", "filelink.profile_render",
                     "Profile Render (Real RAM)", "RENDER_STILL", _profile_render_summary(wm))

        layout.separator()
        dry = layout.box().column(align=True)
        dry.label(text="Dry-run render (catches render-time warnings)", icon="RENDER_STILL")
        if bpy.data.filepath and bpy.data.is_dirty:
            drow = dry.row()
            drow.alert = True
            drow.label(text="Unsaved changes — save first (renders from disk)", icon="ERROR")
        dry.operator("filelink.dryrun_render", text="Run Dry-Run Render",
                     icon="RENDER_STILL")
        # Group 11 #46, 2026-06-26: the render-warnings result, previously only
        # reachable via the now-deleted generic Reports selector.
        _draw_report_detail(dry, wm, "f9")

        layout.separator()
        self._draw_examine_library(context, layout, wm)

        layout.separator()
        self._draw_material_search(context, layout, wm)

    def _draw_material_search(self, context, layout, wm):
        """docs/TODO.md #22 — Find Material Across Files: recursively search
        every .blend under the shared Project Folder (same ``scene.
        filelink_scan_dir`` "Map a Folder" already uses — no new duplicate
        directory picker) for a material name, offline via BAT. Results via
        the standard ``_draw_report_detail`` tree renderer — matches are
        expected far fewer than the total files scanned, so no dedicated
        virtualized picker is needed here."""
        scene = context.scene
        box = layout.box().column(align=True)
        box.label(text="Find Material Across Files", icon="MATERIAL")
        box.prop(scene, "filelink_scan_dir", text="Folder")
        box.prop(scene, "filelink_material_search_pattern", text="Material")
        box.operator("filelink.search_material", text="Search", icon="VIEWZOOM")
        _draw_report_detail(box, wm, "matsearch")
        skipped_lines = [ln for ln in wm.filelink_matsearch_skipped_text.split("\n") if ln]
        _draw_kept_separate(box, wm, "matsearch:skipped", skipped_lines,
                            label=f"Skipped — unreadable ({len(skipped_lines)})", icon="ERROR")

    def _draw_examine_library(self, context, layout, wm):
        """Examine Library: list everything the current file links from a chosen
        (working) library and offer to re-source it from memory first — local,
        then another already-loaded library — falling back to Make Local or a
        per-row manual file+item pick. Grouped by KIND, mirrors the Duplicate
        Data-blocks section's shape. Virtualized (Group 12 Phase 3 item 4,
        2026-07-03) via FILELINK_UL_examine_picker over
        wm.filelink_examine_picker_rows."""
        rows = wm.filelink_examine_rows
        scanned = wm.filelink_examine_scanned

        box = layout.box().column(align=True)
        box.label(text="Retarget Library", icon="LIBRARY_DATA_DIRECT")
        box.label(text="Retarget everything a library provides to your local file or "
                  "another library (e.g. to break a circular reference).", icon="INFO")
        pick = box.row(align=True)
        pick.prop_search(wm, "filelink_examine_library_pick", bpy.data, "libraries", text="")
        pick.operator("filelink.examine_library", text="Examine", icon="VIEWZOOM")

        # Persistent Apply Selected result (docs/TODO.md, 2026-07-09): Apply
        # Selected clears filelink_examine_rows on success, so the panel falls
        # straight back to this pre-scan look — without this, the one-shot
        # toast was the ONLY feedback a user had that anything happened at all.
        if wm.filelink_examine_apply_summary:
            box.label(text=wm.filelink_examine_apply_summary, icon="INFO")

        if scanned and len(rows):
            staged = sum(1 for r in rows if r.selected)
            suggested = sum(1 for r in rows if r.suggested_kind != "none")
            box.label(text=f"{len(rows)} data-block(s) from {wm.filelink_examine_library} — "
                      f"{suggested} in-memory match(es), {staged} staged",
                      icon="LIBRARY_DATA_OVERRIDE")
            if any(r.suggested_kind == "none" for r in rows):
                box.operator("filelink.examine_bulk_pick_folder",
                             text="Search a Folder (all unresolved)", icon="VIEWZOOM")
            box.operator("filelink.examine_apply_selected",
                         text="Apply Selected (Backup)", icon="LINKED")
        elif scanned:
            box.label(text="✓ Nothing currently links from that library", icon="CHECKMARK")
        if not (scanned and len(rows)):
            return

        n = len(wm.filelink_examine_picker_rows)
        if n:
            box.template_list(
                "FILELINK_UL_examine_picker", "",
                wm, "filelink_examine_picker_rows",
                wm, "filelink_examine_picker_active",
                rows=min(12, max(3, n)),
            )


def _draw_progress(layout, wm):
    """Shared progress bar + Pause/Resume + ESC hint, drawn while a modal runs."""
    if not getattr(wm, "filelink_op_active", False):
        return False
    col = layout.column()
    col.progress(
        factor=wm.filelink_op_progress,
        type="BAR",
        text=wm.filelink_op_status or "Working…",
    )
    row = col.row(align=True)
    paused = getattr(wm, "filelink_op_paused", False)
    row.operator("filelink.toggle_pause",
                 text="Resume" if paused else "Pause",
                 icon="PLAY" if paused else "PAUSE")
    row.operator("filelink.request_cancel", text="Cancel (or ESC)", icon="X")
    return True


class FILELINK_PT_scene_deps(bpy.types.Panel):
    """The whole add-on, in Properties > Scene (this is scene-data hygiene, not a
    3D/render activity). Started as the F7 Link & Dependency Doctor hub; the
    legacy VIEW_3D N-panel features (Make Local, Duplicate Materials, Orphans,
    Geometry, Utilities) joined as native collapsible child panels in Batch 5
    (2026-06-23), and the N-panel itself was retired. The Resource Analyzer
    panel was folded into the Analyze panel's "Analyze Memory/Disk" row
    (its by-type breakdown rolled up directly below, like the Flatten
    Characters picker's rollup) and deleted as its own section."""

    bl_label = "File & Link Utilities"
    bl_idname = "FILELINK_PT_scene_deps"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"

    def draw_header(self, context):
        # Title (bl_label) at left, then version, then the doc icon.
        # v0.2.39 tried layout.separator_spacer() here to push the icon to the
        # true far-right edge — REVERTED (live-Blender screenshot, 2026-06-24):
        # in this cramped header region it overlapped the icon onto the bl_label
        # text instead of pushing it right. Back to a plain right-aligned sub-row
        # (icon sits right after the version text, not edge-pinned) until a
        # working far-right approach is found and verified live.
        layout = self.layout
        layout.label(text=f"v{_addon_version()}", icon="LINKED")
        sub = layout.row()
        sub.alignment = "RIGHT"
        sub.operator("wm.url_open", text="", icon="HELP", emboss=False).url = DOC_URL

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager

        # Progress bar + Pause/Cancel + the sticky result line are the ONLY thing
        # drawn in the top (parent) panel's body (v0.2.56, 2026-06-25; placement
        # confirmed by the user: "should go as high in the UI as possible") — a
        # parent panel's own draw() always renders before any of its
        # bl_parent_id children, so this is the highest point achievable below
        # the panel's own draw_header() (title/version/help icon), and nothing
        # else lives here anymore: every section (Current File Data, Analyze,
        # the legacy Make Local/Materials/Orphans/Geometry/Utilities panels,
        # AND the former inline "Duplicate Data-blocks...
        # Reports" block — now its own FILELINK_PT_results panel) is a real
        # bl_order'd child, so they all draw AFTER this, in order, every time —
        # user-reported regression (2026-06-25): the inline block used to render
        # here, ahead of every child panel including Current File Data/Analyze,
        # no matter what bl_order said, since bl_order only orders siblings
        # against each other, never against the parent's own draw() body.
        _draw_progress(layout, wm)

        if wm.filelink_last_result:
            res = layout.row()
            if not wm.filelink_last_result_ok:
                res.alert = True
            res.label(text=wm.filelink_last_result,
                      icon="CHECKMARK" if wm.filelink_last_result_ok else "ERROR")


def _draw_group_header(layout, *, key: str, prop: str, is_exp: bool, label: str, icon: str,
                       action=None, alert: bool = False, indent_factor: float = 0.0,
                       status_icon: str = ""):
    """One collapsible group-header row: expand/collapse triangle + icon +
    label [+ an optional trailing action]. Extracted (docs/TODO.md Group 12
    Phase 1, 2026-06-27) from the ~10 sections that each hand-built the same
    "triangle + icon + counted label[ + action button]" row over their own
    grouped/collapsible list — every section still builds its OWN
    ``{group_key: [members]}`` dict, sort order, and label/icon text (the
    genuine per-section flexibility); only this shell is shared.

    ``action``, when given, is ``callable(row)`` drawing one more widget at
    the row's right — a folder/file picker, a master-keeper button, a "Use
    Selected" button — mirroring ``_analyze_row``'s own ``draw_action``
    parameter. ``alert`` puts JUST the label (not the whole row) into
    Blender's alert/red styling, for sections that flag a per-group problem
    (e.g. Duplicate Textures' material-mismatch warning).

    ``status_icon``, when given, draws a not-run/done (or, for a group with
    several independent sub-scans, a "some but not all" partial) indicator to
    the LEFT of the expand triangle — matching every Analyze-row section's own
    status icon (``_analyze_step_status_icon``). User report, 2026-07-14: "Find
    Duplicates" was the one collapsible-group section missing this, unlike its
    siblings (Check Link Chain, Audit This File, ...).

    Deliberately NOT used by Flatten v2's ``_draw_rig_group`` — that one's
    shape genuinely differs (a SECOND toggle for group-level select state,
    indent, a checkmark-when-done swap) and is the planned Phase 2 prototype
    for this initiative's virtualization layer, not worth reshaping twice."""
    row = layout.row(align=True)
    if indent_factor:
        row.separator(factor=indent_factor)
    if status_icon:
        row.label(text="", icon=status_icon)
    tog = row.operator("filelink.row_toggle", text="",
                       icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False)
    tog.key, tog.prop = key, prop
    lab = row.row()
    lab.alert = alert
    lab.label(text=label, icon=icon)
    if action is not None:
        action(row)
    return row


def _draw_kept_separate(layout, wm, key: str, conflict_lines: list[str], *,
                        label: str | None = None, icon: str = "QUESTION") -> None:
    """Collapsible "kept separate" sub-list, shared by every Find Duplicates
    type section (docs/TODO.md #16, 2026-06-27): a name-family matched on
    naming but not content, so it was never merged/instanced/remapped —
    content identity alone still gates every actual apply, unchanged. Uses
    the one shared inline-detail toggle (``filelink.row_toggle``
    / ``filelink_detail_expanded``) like every other inline disclosure in
    this panel; ``key`` already embeds its own section tag so it can't
    collide with another section's. ``label``/``icon`` let a caller reuse this
    same collapsible-list widget for a differently-worded case (e.g. "skipped,
    unsafe to read" rather than "kept separate, content differs")."""
    if not conflict_lines:
        return
    expanded = set(filter(None, wm.filelink_detail_expanded.split("\n")))
    is_exp = key in expanded
    _draw_group_header(layout, key=key, prop="filelink_detail_expanded", is_exp=is_exp,
                       label=label or f"Kept separate — name matches, content differs ({len(conflict_lines)})",
                       icon=icon)
    if is_exp:
        for ln in conflict_lines:
            r = layout.row(align=True)
            r.separator(factor=2.0)
            r.label(text=ln, icon="DOT")


def _draw_datablock_dups(layout, wm) -> None:
    """Batch C #3 — generic Duplicate Data-blocks: find .NNN families across
    Objects/Actions/Node Groups/etc. (Materials/Meshes/Images keep their own
    dedicated tools, each its own section alongside this one), group by KIND,
    pick a keeper per family, Merge Selected. One section of the shared "Find
    Duplicates" results area (docs/TODO.md #16, 2026-06-27) — no longer its
    own standalone box, so every type reads the same way."""
    families = wm.filelink_datablock_families
    if not wm.filelink_datablock_scanned:
        return
    conflicts = wm.filelink_datablock_conflicts
    layout.label(text=_datablock_dups_headline(wm), icon="LIBRARY_DATA_OVERRIDE")
    has_skipped = bool(wm.filelink_datablock_skipped_text)
    if not (len(families) or conflicts or has_skipped):
        return
    if len(families):
        layout.operator("filelink.merge_datablock_selected",
                        text="Merge Selected (Backup)", icon="AREA_JOIN")

    expanded = set(filter(None, wm.filelink_datablock_expanded.split("\n")))
    groups: dict[str, list] = {}
    for row in families:
        groups.setdefault(row.kind, []).append(row)

    for kind in sorted(groups, key=str.lower):
        members = groups[kind]
        removable_here = sum(r.removable for r in members)
        is_exp = kind in expanded
        _draw_group_header(layout, key=kind, prop="filelink_datablock_expanded", is_exp=is_exp,
                           label=f"{kind}  ({len(members)} family, {removable_here})",
                           icon="LIBRARY_DATA_OVERRIDE")
        if not is_exp:
            continue
        for row in members:
            frow = layout.row(align=True)
            frow.separator(factor=2.0)
            frow.prop(row, "selected", text="")
            base = row.name.split(":", 1)[-1]
            frow.label(text=f"{base}  ({row.removable})", icon="LIBRARY_DATA_OVERRIDE")
            keep = frow.row()
            keep.alignment = "RIGHT"
            keep.label(text="keep", icon="PINNED")
            keep.prop(row, "keeper", text="")

    conflict_lines = [ln for ln in wm.filelink_datablock_conflicts_text.split("\n") if ln]
    _draw_kept_separate(layout, wm, "dupdb:conflicts", conflict_lines)

    skipped_lines = [ln for ln in wm.filelink_datablock_skipped_text.split("\n") if ln]
    _draw_kept_separate(layout, wm, "dupdb:skipped", skipped_lines,
                        label=f"Skipped — unsafe to read ({len(skipped_lines)})", icon="ERROR")


def _res_variants_headline(wm) -> str:
    """Find Resolution Variants' own Analyze-row summary (item 11, 2026-06-25
    — replaces the generic tree disclosure now that this section has its own
    actionable checkbox+button UI, mirroring Find Duplicate Materials/
    Data-blocks)."""
    if not _feature_has_run(wm, "f6res"):
        return ""
    coll = wm.filelink_res_variant_members
    groups = {item.group for item in coll}
    if not groups:
        return "✓ No multi-resolution texture variants found"
    kept = sum(1 for item in coll if item.selected)
    return f"{len(groups)} texture set(s) at multiple resolutions — {kept} chosen to keep so far"


def _draw_res_variants(layout, wm) -> None:
    """Item 11, 2026-06-25: the resolution-variant groups Find Resolution
    Variants finds, now actionable — a per-row "keep this one" checkbox
    (radio per group; no default, since picking which resolution to keep is
    a real decision, unlike items 6/7's safe normalizations) plus 3 buttons
    (Select High/Low Resolution, Remove Excess Variants). Its own headline
    is dropped — the Analyze row right above already shows it. The LOSSY
    warning (2026-07-03 follow-up) only shows when at least one group's
    current tick would actually discard a higher-resolution option — keeping
    every group's HIGHEST resolution isn't a quality loss (just wastes memory
    re-pointing lower-res users at a bigger file), so the warning would be
    misleading there."""
    coll = wm.filelink_res_variant_members
    if not len(coll):
        return

    groups: dict[str, list] = {}
    order: list[str] = []
    for i, item in enumerate(coll):
        if item.group not in groups:
            groups[item.group] = []
            order.append(item.group)
        groups[item.group].append((i, item))

    box = layout.box().column(align=True)
    from ..core import imageres

    loses_res = imageres.selection_loses_resolution(
        [[(item.tag, item.selected) for _i, item in members] for members in groups.values()])
    if loses_res:
        box.label(text="Standardizing is LOSSY — the removed resolution's users "
                  "switch to the kept one.", icon="INFO")
    brow = box.row(align=True)
    brow.operator("filelink.res_variant_select", text="Select High Resolution").which = "HIGH"
    brow.operator("filelink.res_variant_select", text="Select Low Resolution").which = "LOW"
    box.operator("filelink.remove_excess_variants",
                 text="Remove Excess Variants (Backup)", icon="TRASH")

    expanded = set(filter(None, wm.filelink_detail_expanded.split("\n")))
    for group_key in order:
        members = groups[group_key]
        ckey = f"resvar:{group_key}"
        is_exp = ckey in expanded
        kept = next((item.tag for _i, item in members if item.selected), "")
        label = f"{group_key}  ({len(members)} resolutions)"
        if kept:
            label += f" — keeping {kept}"
        _draw_group_header(box, key=ckey, prop="filelink_detail_expanded", is_exp=is_exp,
                           label=label, icon="IMAGE_DATA")
        if not is_exp:
            continue
        for idx, item in members:
            frow = box.row(align=True)
            frow.separator(factor=2.0)
            sop = frow.operator("filelink.res_variant_keep", text="",
                                icon="RADIOBUT_ON" if item.selected else "RADIOBUT_OFF",
                                emboss=False)
            sop.index = idx
            frow.label(text=f"{item.name}  [{item.tag}]")


def _material_dups_headline(wm) -> str:
    """The Find Duplicate Materials Analyze row's own summary (replaces the
    generic _report_feature_summary line — user feedback, 2026-06-25: the
    old report gave no way to act on what it found, this section does)."""
    if not wm.filelink_mat_scanned:
        return ""
    groups = wm.filelink_mat_families
    conflicts = wm.filelink_mat_conflicts
    if not len(groups) and not conflicts:
        return "Materials — ✓ none found"
    bits = []
    if len(groups):
        removable = wm.filelink_mat_removable
        linked = wm.filelink_mat_linked
        bits += [f"{len(groups)} group(s)", f"{removable} material(s) remappable"]
        if linked:
            bits.append(f"{linked} linked (stay in library)")
    if conflicts:
        bits.append(f"{conflicts} kept separate")
    return "Materials — " + ", ".join(bits)


def _draw_material_dups(layout, wm) -> None:
    """Reformatted Find Duplicate Materials — keeper-dropdown + Merge Selected,
    the same actionable shape as Duplicate Data-blocks/Textures (user
    feedback, 2026-06-25: "does not allow me to do anything with the
    information"). Flat list, no kind-grouping needed (every row is already
    one fingerprint-identical material group). One section of the shared
    "Find Duplicates" results area (docs/TODO.md #16, 2026-06-27).

    (Formerly took a ``key_suffix`` to namespace the collapse toggle for
    Automated Cleanup's own second copy of this list — that panel was removed
    in v0.3.0, so this now draws in exactly one place.)"""
    groups = wm.filelink_mat_families
    if not wm.filelink_mat_scanned:
        return
    conflicts = wm.filelink_mat_conflicts
    if not (len(groups) or conflicts):
        layout.label(text=_material_dups_headline(wm), icon="MATERIAL")
        return
    # Collapsible (user report, 2026-07-14: this summary row used to be a bare
    # label with no way to hide the group list below it, unlike every other
    # group-header row in this file).
    key = "matdups:groups"
    expanded = set(filter(None, wm.filelink_detail_expanded.split("\n")))
    is_exp = key in expanded
    _draw_group_header(layout, key=key, prop="filelink_detail_expanded", is_exp=is_exp,
                       label=_material_dups_headline(wm), icon="MATERIAL")
    if not is_exp:
        return
    if len(groups):
        layout.operator("filelink.merge_material_selected",
                        text="Merge Selected (Backup)", icon="AREA_JOIN")
        for row in groups:
            frow = layout.row(align=True)
            frow.prop(row, "selected", text="")
            label = row.name.split(" [", 1)[0]  # drop the "[library]" qualifier for display
            frow.label(text=f"{label}  ({row.removable})", icon="MATERIAL")
            keep = frow.row()
            keep.alignment = "RIGHT"
            keep.label(text="keep", icon="PINNED")
            keep.prop(row, "keeper", text="")

    conflict_lines = [ln for ln in wm.filelink_mat_conflicts_text.split("\n") if ln]
    _draw_kept_separate(layout, wm, "dupmat:conflicts", conflict_lines)


def _geo_dups_headline(wm) -> str:
    """The Find Duplicate Geometry Analyze row's own summary (Group 11 #44,
    2026-06-26) — replaces the generic tree disclosure now that this section
    has its own actionable checkbox UI, mirroring Find Duplicate Materials/
    Data-blocks."""
    if not wm.filelink_geo_scanned:
        return ""
    groups = wm.filelink_geo_families
    conflicts = wm.filelink_geo_conflicts
    if not len(groups) and not conflicts:
        return "Geometry — ✓ none found"
    bits = []
    if len(groups):
        bits += [f"{len(groups)} group(s)", f"{wm.filelink_geo_removable} mesh(es) instanceable"]
        if wm.filelink_geo_linked:
            bits.append(f"{wm.filelink_geo_linked} linked (stay in library)")
    if conflicts:
        bits.append(f"{conflicts} kept separate")
    return "Geometry — " + ", ".join(bits)


def _draw_geo_dups(layout, wm) -> None:
    """Find Duplicate Geometry — checkbox + Instance Selected (Group 11 #44,
    2026-06-26), replacing the old read-only tree report. No keeper dropdown
    needed (unlike Materials/Data-blocks/Images): instancing always keeps
    the canonical mesh ``core.geometry_dedup.choose_canonical`` already
    picked, no ambiguity to override. Flat list — every row is already one
    identical-mesh group (all "Mesh" today; ``kind`` is kept for future
    geometry types, same shape as Materials' flat list). One section of the
    shared "Find Duplicates" results area (docs/TODO.md #16, 2026-06-27)."""
    groups = wm.filelink_geo_families
    if not wm.filelink_geo_scanned:
        return
    conflicts = wm.filelink_geo_conflicts
    layout.label(text=_geo_dups_headline(wm), icon="MESH_DATA")
    if not (len(groups) or conflicts):
        return
    if len(groups):
        layout.operator("filelink.instance_geometry_selected",
                        text="Instance Selected (Backup)", icon="AREA_JOIN")
        for row in groups:
            frow = layout.row(align=True)
            frow.prop(row, "selected", text="")
            frow.label(text=f"{row.name}  ({row.removable})", icon="MESH_DATA")

    conflict_lines = [ln for ln in wm.filelink_geo_conflicts_text.split("\n") if ln]
    _draw_kept_separate(layout, wm, "dupgeo:conflicts", conflict_lines)


def _draw_duplicate_textures(layout, wm, narrow: bool) -> None:
    """F6 Layer 2/3 — the redesigned Image Content section: an inline summary
    header, top Find/Merge/Export, then collapsible material groups whose
    rows are content-identical merge families, each with an include checkbox
    + a keeper dropdown (pick which datablock survives). Mirrors the Missing
    section; no separate report (it's still stashed for the Export button).
    One section of the shared "Find Duplicates" results area (docs/TODO.md
    #16, 2026-06-27) — no longer its own standalone box. (History: a separate
    fast/name-only "Find .NNN" scan was removed 2026-06-24 — confirmed
    redundant with Find Content Dups, which uses the identical fingerprint
    over a strict superset of images.) The group/member list itself is
    virtualized (Group 12 Phase 3 item 2, 2026-07-03) via
    FILELINK_UL_dup_tex_picker over wm.filelink_duptex_picker_rows —
    the "keeper dropdown" row shape, mismatch/effective-material logic now
    lives in ops.image_dedup (shared with FILELINK_OT_dup_material_keeper)."""
    families = wm.filelink_dup_families
    if not wm.filelink_dup_scanned:
        return
    conflicts = wm.filelink_dup_conflicts
    layout.label(text=_duplicate_textures_headline(wm, narrow), icon="IMAGE_DATA")
    if not (len(families) or conflicts):
        return

    if len(families):
        brow = layout.row(align=True)
        brow.operator("filelink.merge_dup_selected",
                      text="Merge Selected (Backup)", icon="AREA_JOIN")
        brow.operator("filelink.export_report", text="",
                      icon="EXPORT").feature = "f6dup"

        n = len(wm.filelink_duptex_picker_rows)
        if n:
            layout.template_list(
                "FILELINK_UL_dup_tex_picker", "",
                wm, "filelink_duptex_picker_rows",
                wm, "filelink_duptex_picker_active",
                rows=min(12, max(3, n)),
            )

    conflict_lines = [ln for ln in wm.filelink_dup_conflicts_text.split("\n") if ln]
    _draw_kept_separate(layout, wm, "dupimg:conflicts", conflict_lines)


def _orphans_headline(wm) -> str:
    """Find Orphans' own Analyze-row summary (Group 11 #45, 2026-06-26) —
    replaces the generic tree disclosure now that orphans have their own
    actionable checkbox UI; fake-user-only/identical stay informational
    (deliberate — see ``ops.orphans``'s module docstring) but their counts
    still come from the same report's "summary" Finding."""
    from ..core.report import Report
    from ..ops.report_store import data_prop

    if not _feature_has_run(wm, "f4"):
        return ""
    try:
        report = Report.from_json(getattr(wm, data_prop("f4"), ""))
        summary = next(f for f in report.findings if f.category == "summary")
        d = summary.data
    except Exception:
        return ""
    if not d.get("orphans") and not d.get("fake_only") and not d.get("identical_groups"):
        return "✓ no orphans, fake users, or identical datablocks found"
    return (f"{d.get('orphans', 0)} orphan(s), {d.get('fake_only', 0)} fake-user-only, "
            f"{d.get('identical_groups', 0)} identical group(s)")


def _draw_orphans(layout, wm) -> None:
    """Find Orphans — checkbox + Purge Selected for TRUE orphans (Group 11
    #45, 2026-06-26), replacing the old read-only tree report. Fake-user-only
    and identical-cluster findings stay informational/read-only (deliberate,
    existing design — ``ops.orphans``'s module docstring: clearing fake users
    or merging identical datablocks "reflects intent, not just cleanup", so
    no checkbox/bulk-action for those here) — drawn via the SAME shared
    ``FILELINK_UL_tree`` machinery every other section uses (docs/TODO.md
    item 46f, 2026-07-04: these used to be hand-rolled ``box.row()`` loops,
    inconsistently indented and unvirtualized — a real production file with
    1000+ identical-datablock groups instantiated every single row regardless
    of scroll position). "orphan" (the checkbox list above) and "summary"
    (already the button's own headline) are deliberately excluded from this
    sub-report."""
    from ..core.report import Report
    from ..core.tree import report_to_tree
    from ..ops import report_store
    from ..ops.report_store import SELECT_OUTCOME_ICON, data_prop, get_select_outcome

    if not _feature_has_run(wm, "f4"):
        return
    try:
        report = Report.from_json(getattr(wm, data_prop("f4"), ""))
    except Exception:
        return

    rows = wm.filelink_orphan_rows
    ro_findings = [f for f in report.findings if f.category in ("fake_only", "identical")]
    skipped_lines = [ln for ln in wm.filelink_orphan_skipped_text.split("\n") if ln]
    if not (len(rows) or ro_findings or skipped_lines):
        return

    box = layout.box().column(align=True)
    if len(rows):
        box.operator("filelink.purge_orphans_selected",
                     text="Purge Selected (Backup)", icon="TRASH")
        for row in rows:
            type_name, _, name = row.name.partition("/")
            frow = box.row(align=True)
            frow.prop(row, "selected", text="")
            op = frow.operator("filelink.select_datablock", text=name,
                               icon="NONE", emboss=False)
            op.type, op.name = type_name, name
            outcome = get_select_outcome(wm, type_name, name)
            if outcome:
                frow.label(text="", icon=SELECT_OUTCOME_ICON.get(outcome, "NONE"))

    if ro_findings:
        ro_report = Report(title=report.title, feature=report.feature, findings=ro_findings)
        ro_nodes = report_to_tree(ro_report)
        expanded = set(filter(None, wm.filelink_detail_expanded.split("\n")))
        report_store.rebuild_inline_detail_rows(wm, "f4", ro_nodes, expanded)
        rows_prop = report_store.inline_rows_prop("f4")
        n = len(getattr(wm, rows_prop))
        if n:
            box.template_list(
                "FILELINK_UL_tree", "inline_f4",
                wm, rows_prop,
                wm, report_store.inline_active_prop("f4"),
                rows=min(12, max(3, n)),
            )

    _draw_kept_separate(box, wm, "orphans:skipped", skipped_lines,
                        label=f"Skipped — unsafe to read ({len(skipped_lines)})", icon="ERROR")


def _makelocal_headline(wm) -> str:
    """Make Local's own Analyze-row summary (docs/TODO.md #22), mirroring
    ``_orphans_headline`` now that Make Local has its own actionable
    checkbox picker instead of the old read-only tree report."""
    from ..core.report import Report
    from ..ops.report_store import data_prop

    if not _feature_has_run(wm, "f2"):
        return ""
    try:
        report = Report.from_json(getattr(wm, data_prop("f2"), ""))
        summary = next(f for f in report.findings if f.category == "summary")
        d = summary.data
    except Exception:
        return ""
    if not d.get("linked"):
        return "✓ nothing linked — already fully local"
    bits = [f"{d.get('linked', 0)} linked datablock(s)", f"{d.get('libraries', 0)} librar(ies)"]
    if d.get("indirect"):
        bits.append(f"{d['indirect']} indirect")
    if d.get("collisions"):
        bits.append(f"{d['collisions']} name collision(s)")
    return ", ".join(bits)


def _draw_makelocal_picker(layout, wm) -> None:
    """Make Local — checkbox + Make Local Selected (docs/TODO.md #22),
    replacing the old read-only tree report with the same actionable shape
    Materials/Geometry/Orphans already have. Rename-collision warnings (the
    one WARNING-severity finding this report can carry) stay visible below
    the picker via the same filtered-mini-report pattern ``_draw_orphans``
    uses for its own informational findings."""
    from ..core.report import Report
    from ..core.tree import report_to_tree
    from ..ops import report_store
    from ..ops.report_store import data_prop

    if not _feature_has_run(wm, "f2"):
        return
    try:
        report = Report.from_json(getattr(wm, data_prop("f2"), ""))
    except Exception:
        return

    rows = wm.filelink_makelocal_rows
    risk_findings = [f for f in report.findings if f.category == "rename_risk"]
    if not (len(rows) or risk_findings):
        return

    box = layout.box().column(align=True)
    if len(rows):
        box.operator("filelink.make_local_selected",
                     text="Make Local Selected (Backup)", icon="LIBRARY_DATA_DIRECT")
        n = len(rows)
        box.template_list(
            "FILELINK_UL_makelocal_picker", "",
            wm, "filelink_makelocal_rows",
            wm, "filelink_makelocal_active",
            rows=min(12, max(3, n)),
        )

    if risk_findings:
        risk_report = Report(title=report.title, feature=report.feature, findings=risk_findings)
        risk_nodes = report_to_tree(risk_report)
        expanded = set(filter(None, wm.filelink_detail_expanded.split("\n")))
        report_store.rebuild_inline_detail_rows(wm, "f2", risk_nodes, expanded)
        rows_prop = report_store.inline_rows_prop("f2")
        n = len(getattr(wm, rows_prop))
        if n:
            box.template_list(
                "FILELINK_UL_tree", "inline_f2",
                wm, rows_prop,
                wm, report_store.inline_active_prop("f2"),
                rows=min(12, max(3, n)),
            )


# Reconnect confidence -> (icon, short label). "none" shows neither — the row
# just offers the source's full candidate list with no particular guess.
# "transitive" is set by ops.datablock_reconnect.reconnect_selected AFTER an
# apply attempt found the chosen candidate was itself unresolved further
# upstream — distinct from "none" (never tried) so the user can tell "this
# is genuinely stuck, the library itself doesn't have it either" from
# "just hasn't been matched yet". "external" (2026-06-25, real-file
# diagnosis) is set when the remap call reports success but the
# placeholder still has real users — those users live inside data that is
# ITSELF linked from another library, so the pointer can't actually be
# rewritten from this file; the fix has to happen by opening that OTHER
# file directly. Distinct from "transitive" — there the SOURCE library
# doesn't have the data at all; here it does, the fix just can't be
# applied from here.
_RECONNECT_CONF = {
    "exact": ("CHECKMARK", "exact"),
    "numbered": ("FILE_REFRESH", "renamed"),
    "fuzzy": ("QUESTION", "fuzzy"),
    "transitive": ("ERROR", "missing upstream too"),
    "external": ("ERROR", "fix at the source library"),
    "none": ("BLANK1", ""),
}


def _draw_reconnect(layout, wm) -> None:
    """Batch C #2 — reconnect missing data-blocks' drill-down list. Rows group
    by their broken/renamed source LIBRARY (the natural unit — one library's
    blocks usually all need the same fix); a group-level file picker peeks a
    chosen source .blend (never loads it) and suggests the closest name per
    row (core.reconnect). Relocated under its Analyze row (Group 11 #43,
    2026-06-26) — Reconnect Selected now lives on that row's right side
    (``_normalize_action_button``-style, wired at the call site), so this
    just keeps the grouped list. Virtualized (Group 12 Phase 3 item 3,
    2026-07-03) via FILELINK_UL_reconnect_picker over
    wm.filelink_reconnect_picker_rows."""
    rows = wm.filelink_missing_blocks
    if not (wm.filelink_missing_scanned and len(rows)):
        return

    n = len(wm.filelink_reconnect_picker_rows)
    if not n:
        return
    box = layout.box().column(align=True)
    box.template_list(
        "FILELINK_UL_reconnect_picker", "",
        wm, "filelink_reconnect_picker_rows",
        wm, "filelink_reconnect_picker_active",
        rows=min(12, max(3, n)),
    )


def _draw_broken_links(layout, wm) -> None:
    """Find Broken Library Links' drill-down list. Relocated under its
    Analyze row (Group 11 #43, 2026-06-26) — Relink Selected now lives on
    that row's right side; this just keeps the UIList."""
    if not len(wm.filelink_broken_libs):
        return
    layout.template_list(
        "FILELINK_UL_broken_libs", "brokenlibs",
        wm, "filelink_broken_libs",
        wm, "filelink_broken_index", rows=4)


def _draw_duplicate_library_paths(layout, wm) -> None:
    """Item 6, 2026-06-25: the duplicate-library-path groups Path
    normalization's "Check" finds — the SAME real file reached via 2+
    stored path forms (separate Library ID blocks in this file). Each
    form is its own radio-style checkbox row (only one enabled per
    group — Blender has no native radio-checkbox, so a toggle operator
    enforces it); a per-group "Use Selected Paths" button merges
    everything the OTHER form(s) provide onto the ticked one."""
    coll = wm.filelink_dup_lib_members
    if not len(coll):
        return

    groups: dict[str, list] = {}
    order: list[str] = []
    for i, item in enumerate(coll):
        if item.group not in groups:
            groups[item.group] = []
            order.append(item.group)
        groups[item.group].append((i, item))

    layout.separator()
    hrow = layout.row(align=True)
    hrow.label(text=f"Duplicate library paths — {len(order)} group(s)",
              icon="LIBRARY_DATA_BROKEN")
    expanded = set(filter(None, wm.filelink_detail_expanded.split("\n")))
    for group_key in order:
        members = groups[group_key]
        ckey = f"duplib:{group_key}"
        is_exp = ckey in expanded
        fname = os.path.basename(members[0][1].stored.rstrip("/\\")) or members[0][1].stored

        def _use_selected_paths_action(row):
            row.operator("filelink.merge_duplicate_libraries", text="Use Selected Paths",
                        icon="AREA_JOIN").group = group_key

        _draw_group_header(layout, key=ckey, prop="filelink_detail_expanded", is_exp=is_exp,
                           label=f"{fname} — {len(members)} forms", icon="FILE_BLEND",
                           action=_use_selected_paths_action)
        if not is_exp:
            continue
        for idx, item in members:
            frow = layout.row(align=True)
            frow.separator(factor=2.0)
            sop = frow.operator("filelink.dup_lib_select", text="",
                                icon="RADIOBUT_ON" if item.selected else "RADIOBUT_OFF",
                                emboss=False)
            sop.index = idx
            frow.label(text=item.stored, icon="FILE_BLEND" if item.selected else "NONE")


def _draw_absolute_paths(layout, wm) -> None:
    """Item 7, 2026-06-25: absolute libraries grouped by drive. A
    same-drive group gets a free-multi-select checkbox per member (any
    subset can be converted) and ONE "Make Selected Relative" button on
    its own title line; a cross-drive group is shown read-only — there is
    no relative path between Windows drives, so nothing is selectable."""
    coll = wm.filelink_abs_path_members
    if not len(coll):
        return

    groups: dict[str, list] = {}
    order: list[str] = []
    for i, item in enumerate(coll):
        if item.group not in groups:
            groups[item.group] = []
            order.append(item.group)
        groups[item.group].append((i, item))

    layout.separator()
    layout.label(text=f"Absolute paths — {len(order)} drive(s)", icon="FILE_FOLDER")
    expanded = set(filter(None, wm.filelink_detail_expanded.split("\n")))
    for group_key in order:
        members = groups[group_key]
        fixable = members[0][1].target != ""
        ckey = f"abspath:{group_key}"
        is_exp = ckey in expanded
        label = f"{group_key} — {len(members)} librar{'y' if len(members) == 1 else 'ies'}"

        def _make_relative_action(row):
            row.operator("filelink.make_selected_relative",
                         text="Make Selected Relative", icon="FILE_REFRESH")

        if fixable:
            _draw_group_header(layout, key=ckey, prop="filelink_detail_expanded",
                               is_exp=is_exp, label=label, icon="CHECKMARK",
                               action=_make_relative_action)
        else:
            _draw_group_header(
                layout, key=ckey, prop="filelink_detail_expanded", is_exp=is_exp,
                label=label + "  (different drive — can't be made relative)", icon="ERROR")
        if not is_exp:
            continue
        for idx, item in members:
            frow = layout.row(align=True)
            frow.separator(factor=2.0)
            if fixable:
                frow.prop(item, "selected", text="")
            else:
                frow.label(text="", icon="BLANK1")
            frow.label(text=item.stored)


def _draw_path_normalization(layout, wm) -> None:
    """Path Normalization's interactive checkbox lists — duplicate library
    paths (radio-select which stored form to keep) + absolute paths (tick
    which to convert). Relocated under its Analyze row (Group 11 #43,
    2026-06-26) — Check/Normalize now live on that row; this just keeps the
    drill-down lists + their per-group action buttons."""
    if not _feature_has_run(wm, "f7fix"):
        return
    _draw_duplicate_library_paths(layout, wm)
    _draw_absolute_paths(layout, wm)


def _draw_missing_textures(layout, wm, narrow: bool) -> None:
    """The unified Missing Textures section: a header summary, then collapsible
    material categories whose members are per-file rows. All three relink
    paths STAGE a target (folder-search / category-folder / per-file pick); the
    single Relink Selected then applies. Relocated into Analyze (Group 11 #46,
    2026-06-26) — was the last section still stuck in the old Results holding
    pen, right after its own trigger via the existing _missing_textures_headline
    helper that already fed the Analyze row's summary. The category/member list
    itself is virtualized (Group 12 Phase 3, 2026-07-03) via
    FILELINK_UL_missing_tex_picker over wm.filelink_missingtex_picker_rows."""
    n_missing = len(wm.filelink_broken_imgs)
    scanned = wm.filelink_tex_scanned

    tex = layout.box().column(align=True)
    headline = _missing_textures_headline(wm, narrow)
    if headline:
        tex.label(text=headline, icon="IMAGE_DATA")
    if not scanned:
        return
    if not n_missing:
        _draw_linked_missing_textures(tex, wm)
        return

    # Recursive staged search over ALL missing textures (between List and the list).
    # Exact-basename first; the fuzzy matcher is the FALLBACK for vendor-renamed
    # files (proposals land in the Possible Matches sub-section below).
    srow = tex.row(align=True)
    srow.operator("filelink.search_textures_folder",
                  text="Search a Folder (Recursive)…", icon="FILEBROWSER")
    srow.operator("filelink.suggest_fuzzy_matches",
                  text="Suggest Matches…", icon="ZOOM_SELECTED")
    # B4 eyedropper: borrow a WORKING material's existing textures as substitute
    # candidates for the missing ones (matched by name → staged as Possible
    # Matches). The picker is the standard material datablock field + eyedropper.
    tex.label(text="Substitute from a material's textures:", icon="EYEDROPPER")
    mrow = tex.row(align=True)
    mrow.prop(wm, "filelink_tex_source_material", text="")
    mrow.operator("filelink.suggest_from_material", text="Suggest",
                  icon="ZOOM_SELECTED")
    # …or borrow the texture files another .blend references (offline BAT harvest).
    tex.operator("filelink.suggest_from_blend",
                 text="Substitute from Another .blend…", icon="FILE_BLEND")
    tex.separator()
    hrow = tex.row(align=True)
    hrow.label(text="Missing Textures", icon="IMAGE_DATA")
    hrow.operator("filelink.relink_textures_selected", text="Relink Selected",
                  icon="FILE_REFRESH")

    # Virtualized (Group 12 Phase 3): grouped by MATERIAL, rebuilt by
    # ops.image_relink.rebuild_missing_tex_picker_rows after every scan/pick/
    # accept/relink — never recomputed here on each redraw.
    n = len(wm.filelink_missingtex_picker_rows)
    if n:
        tex.template_list(
            "FILELINK_UL_missing_tex_picker", "",
            wm, "filelink_missingtex_picker_rows",
            wm, "filelink_missingtex_picker_active",
            rows=min(12, max(3, n)),
        )

    _draw_possible_matches(tex, wm)
    _draw_linked_missing_textures(tex, wm)


def _draw_linked_missing_textures(tex, wm) -> None:
    """Read-only companion list: missing textures owned by a LINKED Image —
    can't be relinked here (the source library owns that file path), grouped
    by library so the user knows exactly which file to go fix. No checkboxes,
    no file pickers, no Relink button — purely visibility (see
    ops.image_relink._gather_linked_missing_images for why this exists)."""
    rows = list(wm.filelink_linked_missing_imgs)
    if not rows:
        return
    tex.separator()
    tex.label(text=f"Linked — fix at the source library ({len(rows)})",
             icon="LIBRARY_DATA_BROKEN")

    from ..core.datablock_links import basename as _lib_basename

    LM = "\x03"  # namespaced so these keys don't collide with the lists above
    expanded = set(filter(None, wm.filelink_tex_expanded.split("\n")))
    groups: dict[str, list] = {}
    for item in rows:
        groups.setdefault(item.library or "(unknown library)", []).append(item)

    for lib in sorted(groups):
        members = groups[lib]
        ckey = LM + lib
        is_exp = ckey in expanded
        _draw_group_header(tex, key=ckey, prop="filelink_tex_expanded", is_exp=is_exp,
                           label=f"{_lib_basename(lib)}  ({len(members)})", icon="FILE_BLEND")
        if not is_exp:
            continue
        for item in members:
            frow = tex.row(align=True)
            frow.separator(factor=2.0)
            frow.label(text=item.name, icon="IMAGE_DATA")
            tail = frow.row()
            tail.alignment = "RIGHT"
            tail.label(text=item.material or "(no material)")


# Confidence band -> (icon, short label, rank). Higher rank sorts to the top.
_TEX_CONF = {"high": ("CHECKMARK", "high", 2),
             "medium": ("QUESTION", "med", 1),
             "low": ("DOT", "low", 0)}


def _draw_possible_matches(tex, wm) -> None:
    """F6 step 4 — the FUZZY proposals (a vendor-renamed file the exact search
    couldn't place). A second list grouped by material, COLLAPSIBLE and collapsed
    by default (so a long Suggest-Matches result doesn't bury the panel), with
    materials ordered by their best confidence (high first). Accept one row, a
    whole material, or all; accepting moves the proposal into the Missing Textures
    list above (ticked)."""
    proposals = [(idx, item) for idx, item in enumerate(wm.filelink_broken_imgs)
                 if item.proposal and not item.target]
    if not proposals:
        return

    tex.separator()
    hrow = tex.row(align=True)
    hrow.label(text=f"Possible Matches — {len(proposals)}", icon="ZOOM_SELECTED")
    arow = tex.row(align=True)
    arow.operator("filelink.accept_all_matches", text="Accept All",
                 icon="CHECKMARK").min_confidence = ""
    arow.operator("filelink.accept_all_matches", text="Accept High Matches",
                 icon="CHECKMARK").min_confidence = "high"
    arow.operator("filelink.accept_all_matches", text="Accept High/Med Matches",
                 icon="CHECKMARK").min_confidence = "medium"
    tex.label(text="Name-similarity guesses — review before accepting.", icon="INFO")

    # Category keys are namespaced ("\x01" + material) so they don't collide with
    # the Missing list's material keys in the shared expanded-set.
    PM = "\x01"
    expanded = set(filter(None, wm.filelink_tex_expanded.split("\n")))

    groups: dict[str, list] = {}
    for idx, item in proposals:
        groups.setdefault(item.material or "(no material)", []).append((idx, item))

    def conf_rank(it):
        return _TEX_CONF.get(it.proposal_confidence, ("DOT", "?", 0))[2]

    def cat_rank(members):
        return max(conf_rank(it) for _i, it in members)

    # Materials ordered by best confidence (high→low), then name.
    for key in sorted(groups, key=lambda k: (-cat_rank(groups[k]), k.lower())):
        members = sorted(groups[key], key=lambda pair: -conf_rank(pair[1]))
        ckey = PM + key
        is_exp = ckey in expanded
        best_lbl = _TEX_CONF.get(
            {2: "high", 1: "medium", 0: "low"}[cat_rank(members)], ("", "?", 0))[1]

        def _accept_material_action(row):
            # Material-level accept (the whole rolled-up group) — CHECKMARK marks the
            # group action, distinct from the single-row IMPORT below.
            row.operator("filelink.accept_material_matches", text="",
                        icon="CHECKMARK").material = key

        _draw_group_header(tex, key=ckey, prop="filelink_tex_expanded", is_exp=is_exp,
                           label=f"{key}  ({len(members)}, {best_lbl})", icon="MATERIAL",
                           action=_accept_material_action)
        if not is_exp:
            continue
        for idx, item in members:
            frow = tex.row(align=True)
            frow.separator(factor=2.0)
            frow.label(text=item.name, icon="IMAGE_DATA")
            prop = frow.row()
            prop.alignment = "RIGHT"
            icon, conf, _r = _TEX_CONF.get(item.proposal_confidence, ("DOT", "?", 0))
            tag = f"{conf}, diff res" if item.proposal_res_mismatch else conf
            prop.label(text=f"{os.path.basename(item.proposal)}  ({tag})", icon=icon)
            frow.operator("filelink.accept_match", text="",
                          icon="IMPORT").index = idx
