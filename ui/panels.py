"""The AssetDoctor N-panel (3D viewport sidebar > AssetDoctor).

Each feature exposes a read-only/report action and, where relevant, an explicit
Apply action so the report-first → apply workflow is reachable without the F9
redo panel. Detailed findings print to the system console
(Window > Toggle System Console on Windows) and, when enabled in Utilities, to
debugLog.txt. Button tooltips come from each operator's ``description()``.
"""

import os
import pathlib

import bpy

DOC_URL = "https://github.com/rickpalo/AssetDoctor/tree/main/docs"

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


class ASSETDOCTOR_PG_tree_row(bpy.types.PropertyGroup):
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
    guide: bpy.props.StringProperty()  # precomputed "│  ├─ "-style indent-guide prefix  # type: ignore[valid-type]
    ref_type: bpy.props.StringProperty()  # type: ignore[valid-type]
    ref_name: bpy.props.StringProperty()  # type: ignore[valid-type]
    prop: bpy.props.StringProperty()  # expanded-keys WM prop this row belongs to


class ASSETDOCTOR_UL_tree(bpy.types.UIList):
    """Virtualized, scrollable tree for the Report and Resource panels: indent +
    expand toggle + tooltip-bearing label + right-aligned detail. Shared by both."""

    bl_idname = "ASSETDOCTOR_UL_tree"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.label)
            return
        row = layout.row(align=True)
        # Indent guide: a "│  ├─ "-style connector (precomputed in core.tree) reads
        # clearer than blank space, especially in deep trees like the F7 File Map.
        if item.guide:
            row.label(text=item.guide, icon="NONE")
        if item.has_children:
            tri = "TRIA_DOWN" if item.expanded else "TRIA_RIGHT"
            op = row.operator("assetdoctor.report_toggle", text="", icon=tri, emboss=False)
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
        op = row.operator("assetdoctor.row_label", text=display,
                          icon="NONE", emboss=False)
        op.text = full
        op.key = item.key
        op.prop = item.prop
        op.has_children = item.has_children
        if item.ref_type:
            op.ref_type = item.ref_type
            op.ref_name = item.ref_name
        if item.detail:
            sub = row.row()
            sub.alignment = "RIGHT"
            sub.label(text=item.detail)


class ASSETDOCTOR_PG_analyze_step(bpy.types.PropertyGroup):
    """One step of the Analyze section's "Analyze All" sequence (Phase 3a) — a
    thin progress mirror of ``core.analyze_steps.STEPS``, rebuilt and updated by
    ``ops.analyze_all`` as it runs so the panel can show a per-step icon."""

    # `name` (built-in) unused; key/label are explicit for clarity at the call site.
    key: bpy.props.StringProperty()  # type: ignore[valid-type]
    label: bpy.props.StringProperty()  # type: ignore[valid-type]
    status: bpy.props.StringProperty(default="pending")  # pending|running|done|error  # type: ignore[valid-type]


class ASSETDOCTOR_PG_flatten_candidate(bpy.types.PropertyGroup):
    """One Library Override with an adjusted transform (Phase 4-B), for the
    character picker. ``ops.linkchain.scan_flatten_candidates`` fills the
    collection AND caches each row's full plan (as JSON, on the WM) so picking
    ONE row and building its plan doesn't require rescanning every character —
    the user explicitly wants to act on a single chosen character, not the
    whole file at once."""

    # `name` (built-in) holds the Object's name.
    ready: bpy.props.BoolProperty()  # type: ignore[valid-type]
    status: bpy.props.StringProperty()  # one-line summary or blocking reason  # type: ignore[valid-type]


class ASSETDOCTOR_PG_broken_lib(bpy.types.PropertyGroup):
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


class ASSETDOCTOR_PG_dup_family(bpy.types.PropertyGroup):
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
    material_override: bpy.props.PointerProperty(type=bpy.types.Material)  # type: ignore[valid-type]
    removable: bpy.props.IntProperty()  # type: ignore[valid-type]


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


class ASSETDOCTOR_PG_missing_block(bpy.types.PropertyGroup):
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


class ASSETDOCTOR_PG_datablock_family(bpy.types.PropertyGroup):
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
    """Append the node-graph comparison (Material rows only) to an Examine
    Library suggestion line: "identical" keeps the plain checkmark, "differs"
    warns that the same-named substitute looks different, anything else (not a
    Material, or comparison failed) leaves the base text untouched."""
    if graph_match == "identical":
        return f"{base} (identical)", "CHECKMARK"
    if graph_match == "differs":
        return f"{base} (graph differs)", "ERROR"
    return base, "CHECKMARK"


class ASSETDOCTOR_PG_examine_row(bpy.types.PropertyGroup):
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
    graph_match: bpy.props.StringProperty()  # "identical" | "differs" | "" — Material rows only  # type: ignore[valid-type]
    use_suggested: bpy.props.BoolProperty(default=False)  # type: ignore[valid-type]
    make_local: bpy.props.BoolProperty(
        default=False, name="",
        description="Sever the link and keep using THIS copy locally")  # type: ignore[valid-type]
    source_blend: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore[valid-type]
    candidates: bpy.props.StringProperty()  # newline-joined names from source_blend  # type: ignore[valid-type]
    target: bpy.props.EnumProperty(
        name="Relink to", items=_examine_target_items)  # type: ignore[valid-type]
    selected: bpy.props.BoolProperty(
        default=False, name="",
        description="Include this data-block when you Apply Selected")  # type: ignore[valid-type]


class ASSETDOCTOR_UL_broken_libs(bpy.types.UIList):
    """Per-link relink list: checkbox + broken library name + its target file (or
    a 'pick a file' hint) + a file-picker button. Lets the user fix one specific
    broken link without running a bulk pass."""

    bl_idname = "ASSETDOCTOR_UL_broken_libs"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.name)
            return
        row = layout.row(align=True)
        row.prop(item, "selected", text="")
        row.label(text=item.name, icon="LIBRARY_DATA_BROKEN")
        target = row.row()
        target.alignment = "RIGHT"
        if item.target:
            target.label(text=os.path.basename(item.target) or item.target,
                         icon="CHECKMARK" if item.has_candidate else "QUESTION")
        else:
            target.label(text="no match — pick a file", icon="QUESTION")
        row.operator("assetdoctor.relink_pick_file", text="", icon="FILEBROWSER").index = index


class ASSETDOCTOR_UL_flatten_candidates(bpy.types.UIList):
    """Phase 4-B character picker: one row per override-with-transform Object,
    its ready/blocked status, and a per-row "Build Plan" button — the user
    builds a flatten plan for ONE chosen character at a time, not the whole
    file in one pass."""

    bl_idname = "ASSETDOCTOR_UL_flatten_candidates"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.name)
            return
        row = layout.row(align=True)
        row.label(text=item.name, icon="CHECKMARK" if item.ready else "QUESTION")
        status = row.row()
        status.alignment = "RIGHT"
        status.label(text=item.status)
        row.operator("assetdoctor.build_flatten_plan", text="Build Plan").name = item.name


class _SceneFeaturePanel:
    """Shared bl_* attributes for the legacy-feature Scene sub-panels (Make
    Local, Duplicate Materials, Orphans, Geometry, Resource Analyzer,
    Utilities) — migrated off the old VIEW_3D N-panel (Batch 5, 2026-06-23) so
    everything lives under Properties > Scene > AssetDoctor. Each is a child of
    ASSETDOCTOR_PT_scene_deps, which gives it a native collapse triangle and
    remembers its open/closed state per-file, same as the N-panel did."""
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "ASSETDOCTOR_PT_scene_deps"


class ASSETDOCTOR_PT_current_file_data(_SceneFeaturePanel, bpy.types.Panel):
    """Phase 3a (2026-06-25) — the first of the 5 named top-level sections: the
    instant, no-scan "what is this file" summary. Content unchanged from before
    the split (just promoted to its own collapsible native sub-panel, per the
    user's "all 5 sections must be collapsible" requirement) — expanding this
    with face/vert/texture-size counts is its own deferred design question."""

    bl_label = "Current File Data"
    bl_idname = "ASSETDOCTOR_PT_current_file_data"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        fname = bpy.path.basename(bpy.data.filepath) or "(unsaved)"
        layout.label(text=fname, icon="FILE_BLEND")  # version lives in the panel header
        total, missing, absolute = _libraries_at_a_glance()
        bits = [f"{total} linked librar{'y' if total == 1 else 'ies'}"]
        if missing:
            bits.append(f"{missing} missing")
        if absolute:
            bits.append(f"{absolute} absolute")
        layout.label(text="   ·   ".join(bits), icon="LIBRARY_DATA_DIRECT")

        # Scan Dependencies / Check Link Chain reads the .blend FROM DISK (offline
        # BAT), so it reflects the last SAVED state — unsaved relinks/fixes won't
        # show until you save. Warn when the file is dirty so a stale "missing
        # link" isn't confusing.
        if bpy.data.filepath and bpy.data.is_dirty:
            warn = layout.row()
            warn.alert = True
            warn.label(text="Unsaved changes — save before Check Link Chain (it reads "
                       "from disk)", icon="ERROR")


class ASSETDOCTOR_PT_analyze(_SceneFeaturePanel, bpy.types.Panel):
    """Phase 3a (2026-06-25) — the second named section: every "look for
    problems in the CURRENT file" trigger, in one place, plus an Analyze All
    sequencer (``ops.analyze_all``) that runs them in order. Each button here
    fills the SAME WM state its box used to fill directly — relocating the
    trigger doesn't change what runs; the populated list/report still draws in
    its existing box below (Cleanup & Fixes isn't designed yet, per the user's
    explicit ask to rough this section in first and see what's left)."""

    bl_label = "Analyze"
    bl_idname = "ASSETDOCTOR_PT_analyze"
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager

        layout.operator("assetdoctor.analyze_all", icon="PLAY")
        steps = wm.assetdoctor_analyze_steps
        if len(steps):
            col = layout.column(align=True)
            for row in steps:
                col.label(text=row.label, icon=_ANALYZE_STEP_ICON.get(row.status, "BLANK1"))
            layout.separator()

        row = layout.row(align=True)
        row.operator("assetdoctor.scan_dependencies", text="Check Link Chain", icon="VIEWZOOM")
        row.operator("assetdoctor.analyze_overrides", text="Audit This File",
                     icon="LIBRARY_DATA_OVERRIDE")
        layout.operator("assetdoctor.scan_link_chains", text="Find Flattenable Link Chains",
                        icon="LINKED")
        layout.operator("assetdoctor.scan_flatten_candidates", text="Find Flattenable Characters",
                        icon="LIBRARY_DATA_OVERRIDE")
        if len(wm.assetdoctor_flatten_candidates):
            layout.template_list(
                "ASSETDOCTOR_UL_flatten_candidates", "flattencandidates",
                wm, "assetdoctor_flatten_candidates",
                wm, "assetdoctor_flatten_index", rows=4)

        layout.operator("assetdoctor.scan_datablock_dups", text="Find Duplicate Data-blocks",
                        icon="LIBRARY_DATA_OVERRIDE")

        row = layout.row(align=True)
        row.operator("assetdoctor.scan_broken_links", text="Find Broken Links",
                     icon="LIBRARY_DATA_BROKEN")
        row.operator("assetdoctor.scan_reconnect_targets", text="Find Reconnectable Data-blocks",
                     icon="LIBRARY_DATA_OVERRIDE")
        layout.operator("assetdoctor.scan_all_missing", text="Find All Missing", icon="VIEWZOOM")

        layout.operator("assetdoctor.scan_broken_textures", text="Find Missing Textures",
                        icon="IMAGE_DATA")

        row = layout.row(align=True)
        row.operator("assetdoctor.material_dedup", text="Find Duplicate Materials").apply = False
        row.operator("assetdoctor.instance_geometry", text="Find Duplicate Geometry").apply = False

        layout.operator("assetdoctor.scan_orphans", text="Find Orphans").purge_orphans = False

        row = layout.row(align=True)
        row.operator("assetdoctor.scan_content_dups", text="Find Duplicate Content",
                     icon="ZOOM_ALL")
        row.operator("assetdoctor.scan_res_variants", text="Find Resolution Variants",
                     icon="FULLSCREEN_ENTER")

        row = layout.row(align=True)
        row.operator("assetdoctor.analyze_resources", text="Analyze Memory/Disk", icon="VIEWZOOM")
        # Profile Render actually renders — too slow/disruptive for the Analyze All
        # sequencer (core.analyze_steps.STEPS deliberately excludes it); manual only.
        row.operator("assetdoctor.profile_render", text="Profile Render (Real RAM)",
                     icon="RENDER_STILL")

        # Folder-wide link map (graphical) + reverse-dependency check both scan a
        # FOLDER you pick, not the current file — different scope from everything
        # above, so the user asked for these at the BOTTOM of this section.
        layout.separator()
        pmap = layout.box().column(align=True)
        pmap.label(text="Map a Folder (folder → graph)", icon="NODETREE")
        pmap.prop(context.scene, "assetdoctor_scan_dir", text="")
        pmap.operator("assetdoctor.scan_folder", text="Map Folder → Open Graph",
                      icon="VIEWZOOM").directory = context.scene.assetdoctor_scan_dir

        rev = layout.box().column(align=True)
        rev.label(text="Safe to delete? (who links this file)", icon="TRASH")
        rev.prop(context.scene, "assetdoctor_dep_target", text="")
        rev.operator("assetdoctor.check_dependents", text="Check What Links This",
                     icon="VIEWZOOM")
        verdict = wm.assetdoctor_dep_verdict
        if verdict == "unsafe":
            vrow = rev.row()
            vrow.alert = True
            vrow.label(text=wm.assetdoctor_dep_verdict_text, icon="ERROR")
        elif verdict == "safe":
            rev.label(text=wm.assetdoctor_dep_verdict_text, icon="CHECKMARK")
        elif verdict == "not_scanned":
            vrow = rev.row()
            vrow.alert = True
            vrow.label(text=wm.assetdoctor_dep_verdict_text, icon="ERROR")


class ASSETDOCTOR_PT_make_local(_SceneFeaturePanel, bpy.types.Panel):
    bl_label = "Make Local"
    bl_idname = "ASSETDOCTOR_PT_make_local"
    bl_order = 2

    def draw(self, context):
        layout = self.layout
        layout.operator("assetdoctor.make_local", text="Report (Dry Run)").apply = False
        row = layout.row(align=True)
        op = row.operator("assetdoctor.make_local", text="→ New File")
        op.apply = True
        op.mode = "NEW_FILE"
        op = row.operator("assetdoctor.make_local", text="→ In Place")
        op.apply = True
        op.mode = "IN_PLACE"


class ASSETDOCTOR_PT_materials(_SceneFeaturePanel, bpy.types.Panel):
    bl_label = "Duplicate Materials"
    bl_idname = "ASSETDOCTOR_PT_materials"
    bl_order = 3

    def draw(self, context):
        # Its "Find Duplicate Materials" report trigger now lives in the Analyze
        # sub-panel (Phase 3a, 2026-06-25); this panel keeps the Apply action.
        layout = self.layout
        layout.operator("assetdoctor.material_dedup", text="Dedup & Remap (Apply)").apply = True


class ASSETDOCTOR_PT_orphans(_SceneFeaturePanel, bpy.types.Panel):
    bl_label = "Orphans & Fake Users"
    bl_idname = "ASSETDOCTOR_PT_orphans"
    bl_order = 4

    def draw(self, context):
        # Its "Find Orphans" report trigger now lives in the Analyze sub-panel
        # (Phase 3a, 2026-06-25); this panel keeps the Apply action.
        layout = self.layout
        layout.operator("assetdoctor.scan_orphans", text="Scan + Purge Orphans").purge_orphans = True


class ASSETDOCTOR_PT_geometry(_SceneFeaturePanel, bpy.types.Panel):
    bl_label = "Duplicate Geometry"
    bl_idname = "ASSETDOCTOR_PT_geometry"
    bl_order = 5

    def draw(self, context):
        # Its "Find Duplicate Geometry" report trigger now lives in the Analyze
        # sub-panel (Phase 3a, 2026-06-25); this panel keeps the Apply action.
        layout = self.layout
        layout.operator("assetdoctor.instance_geometry", text="Instance & Merge (Apply)").apply = True


class ASSETDOCTOR_PT_resource_tools(_SceneFeaturePanel, bpy.types.Panel):
    bl_label = "Resource Analyzer"
    bl_idname = "ASSETDOCTOR_PT_resource_tools"
    bl_order = 6

    def draw(self, context):
        # Its "Analyze Memory/Disk" + "Profile Render" triggers now live in the
        # Analyze sub-panel (Phase 3a, 2026-06-25); this panel keeps the results.
        layout = self.layout
        wm = context.window_manager

        # Folded in from the old standalone "Resource Usage" N-panel (Batch 5) —
        # it was only ever a second view onto this same scan/profile result.
        if not wm.assetdoctor_resource_tree:
            return
        layout.separator()
        layout.label(text="RAM / VRAM estimated; disk accurate", icon="INFO")
        if wm.assetdoctor_profiled_ram:
            layout.label(text=f"Profiled real peak RAM: {wm.assetdoctor_profiled_ram}",
                         icon="RENDER_STILL")
        layout.operator("assetdoctor.export_report", text="Export…", icon="EXPORT").source = "resource"
        layout.template_list(
            "ASSETDOCTOR_UL_tree", "resource",
            wm, "assetdoctor_resource_rows",
            wm, "assetdoctor_resource_index",
            rows=12, sort_lock=True,
        )


class ASSETDOCTOR_PT_utilities(_SceneFeaturePanel, bpy.types.Panel):
    bl_label = "Utilities"
    bl_idname = "ASSETDOCTOR_PT_utilities"
    bl_order = 7
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        from ..prefs import get_prefs

        layout = self.layout
        layout.prop(context.scene, "assetdoctor_debug_log")
        layout.operator("assetdoctor.open_preferences",
                        text="Lists & Backups: Add-on Preferences…", icon="PREFERENCES")

        prefs = get_prefs(context)
        if prefs is not None and prefs.idle_scan_enabled:
            wm = context.window_manager
            secs = getattr(wm, "assetdoctor_idle_seconds", 0.0)
            detected = getattr(wm, "assetdoctor_idle_detected", False)
            layout.separator()
            layout.label(text=f"Idle-scan prototype — {secs:.0f}s since input"
                        + (" (idle)" if detected else ""), icon="TIME")


def _libraries_at_a_glance():
    """Instant linked-library health from ``bpy.data`` (in memory, no scan):
    (total, missing, absolute) over ``bpy.data.libraries``."""
    total = missing = absolute = 0
    for lib in bpy.data.libraries:
        fp = lib.filepath
        if not fp:
            continue
        total += 1
        if not fp.startswith("//"):
            absolute += 1
        try:
            if not pathlib.Path(bpy.path.abspath(fp)).is_file():
                missing += 1
        except Exception:
            missing += 1
    return total, missing, absolute


def _draw_progress(layout, wm):
    """Shared progress bar + Pause/Resume + ESC hint, drawn while a modal runs."""
    if not getattr(wm, "assetdoctor_op_active", False):
        return False
    col = layout.column()
    col.progress(
        factor=wm.assetdoctor_op_progress,
        type="BAR",
        text=wm.assetdoctor_op_status or "Working…",
    )
    row = col.row(align=True)
    paused = getattr(wm, "assetdoctor_op_paused", False)
    row.operator("assetdoctor.toggle_pause",
                 text="Resume" if paused else "Pause",
                 icon="PLAY" if paused else "PAUSE")
    row.operator("assetdoctor.request_cancel", text="Cancel (or ESC)", icon="X")
    return True


class ASSETDOCTOR_PT_scene_deps(bpy.types.Panel):
    """The whole add-on, in Properties > Scene (this is scene-data hygiene, not a
    3D/render activity). Started as the F7 Link & Dependency Doctor hub; the
    legacy VIEW_3D N-panel features (Make Local, Duplicate Materials, Orphans,
    Geometry, Resource Analyzer, Utilities) joined as native collapsible child
    panels in Batch 5 (2026-06-23), and the N-panel itself was retired."""

    bl_label = "AssetDoctor"
    bl_idname = "ASSETDOCTOR_PT_scene_deps"
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

    # f6tex (the old before/after Missing-Textures report) is gone — the Missing
    # Textures section now lists everything inline, so no separate report is
    # needed. f6dup is excluded from the Reports selector below — the Duplicate
    # Materials/Textures section already lists everything inline (with a keeper
    # dropdown), so its report is only kept around for the inline Export button,
    # and showing it as a selectable tab would just be a second, redundant route
    # to the same data (see the 2026-06-23 #9 fix this preserves).
    _SELECTOR_EXCLUDE = frozenset({"f6dup"})

    def draw(self, context):
        from ..core.report import Report
        from ..ops.report_store import (
            TREE_FEATURES, active_feature, available_features, data_prop, exp_prop,
        )

        layout = self.layout
        wm = context.window_manager

        # Progress bar + Pause/Cancel + the sticky result line are the only things
        # left directly in the top panel (Phase 3a, 2026-06-25) — they need to stay
        # visible no matter which collapsible section below is open/closed, so they
        # can't live inside one of the 5 named sections. Current File Data (file
        # name, dirty-warning, libraries-at-a-glance) and Analyze (Check Link
        # Chain/Audit This File/the Find-X buttons/Project Link Map/Safe to Delete)
        # are now their own native sub-panels, right below — see
        # ASSETDOCTOR_PT_current_file_data / ASSETDOCTOR_PT_analyze. Everything
        # else here is UNCHANGED on purpose: the user asked to see Current File
        # Data + Analyze roughed in first, then design Reporting & Recommendations
        # / Cleanup & Fixes / Info & Utilities once it's visible what's left.
        _draw_progress(layout, wm)

        # Sticky last-result line (user, 2026-06-24): a plain operator like Reconnect
        # Selected left NO in-panel trace of what happened — only a toast (gone once
        # you move the mouse) and the Info editor. This persists until overwritten by
        # the next action. Minimal v1 (one line); a bigger always-visible feedback
        # area (multi-line, beside Current File Data) is a separate Phase 3 design
        # question, not decided yet — see docs/TODO.md.
        if wm.assetdoctor_last_result:
            res = layout.row()
            if not wm.assetdoctor_last_result_ok:
                res.alert = True
            res.label(text=wm.assetdoctor_last_result,
                      icon="CHECKMARK" if wm.assetdoctor_last_result_ok else "ERROR")

        # Batch C #3: act on the duplicate_family findings Analyze's Overrides &
        # Dups report surfaces (Objects/Actions/Node Groups/etc. — Materials/Meshes/
        # Images already have their own dedicated dedup tools below/elsewhere). Its
        # own "Find Duplicates" trigger now lives in the Analyze sub-panel (Phase
        # 3a) — this box keeps the results list + Merge Selected.
        self._draw_datablock_dups(context, layout, wm)

        # Phase 3 path fixes are TWO independent jobs (user, 2026-06-21):
        #  (1) relink broken/missing library links — per-link + pick-a-file, so you
        #      can fix one specific link (e.g. a broken material library);
        #  (2) normalize the paths of libraries that already resolve.
        # Both Find triggers (Find Broken Links, the old Find Missing Data-blocks —
        # now folded into Find Reconnectable Data-blocks below) moved to Analyze
        # (Phase 3a); this box keeps the results list + Relink Selected.
        links = layout.box().column(align=True)
        links.label(text="Broken links & missing data-blocks", icon="LIBRARY_DATA_BROKEN")
        if len(wm.assetdoctor_broken_libs):
            links.template_list(
                "ASSETDOCTOR_UL_broken_libs", "brokenlibs",
                wm, "assetdoctor_broken_libs",
                wm, "assetdoctor_broken_index", rows=4)
            links.operator("assetdoctor.relink_selected",
                           text="Relink Selected (Creates Backup)", icon="FILE_REFRESH")

        # Batch C #2: reconnect missing data-blocks to a real datablock in a chosen
        # source .blend (separate from the broken-LIBRARY-link relinker above — a
        # missing data-block's library can resolve fine; the block itself was just
        # renamed/removed at the source).
        self._draw_reconnect(context, layout, wm)

        # Examine Library: proactively retarget AWAY from a chosen WORKING library
        # (e.g. a shared bundle causing circular references) — distinct from the
        # reconnect box above, which only triggers on BROKEN placeholders.
        self._draw_examine_library(context, layout, wm)

        norm = layout.box().column(align=True)
        norm.label(text="Path normalization", icon="FILE_REFRESH")
        nr = norm.row(align=True)
        nr.operator("assetdoctor.normalize_library_paths", text="Check").apply = False
        nr.operator("assetdoctor.normalize_library_paths",
                    text="Normalize (Creates Backup)", icon="CHECKMARK").apply = True

        # F6: missing image textures (the magenta). Everything lists inline here —
        # header summary, then collapsible material/folder categories with per-file
        # rows — so no separate report is needed. The three relink paths share one
        # "stage a target → Relink Selected applies" model:
        #   • Search a folder (recursive) — stage matches for ALL missing textures
        #   • category folder button      — stage matches for one group
        #   • per-file file button        — pick one file
        self._draw_missing_textures(context, layout, wm)

        # F6 Layer 2: merge content-identical .NNN duplicate image datablocks
        # (verified by dimensions + hash). Redesigned to mirror the Missing section:
        # collapsible material groups, a per-family keeper dropdown, inline summary.
        self._draw_duplicate_textures(context, layout, wm)

        # Batch D: catch render-TIME problems (missing textures, driver errors)
        # that no static scan above can see, by rendering one low-res frame in a
        # SEPARATE background Blender process — this session's UI/file is untouched.
        dry = layout.box().column(align=True)
        dry.label(text="Dry-run render (catches render-time warnings)", icon="RENDER_STILL")
        if bpy.data.filepath and bpy.data.is_dirty:
            drow = dry.row()
            drow.alert = True
            drow.label(text="Unsaved changes — save first (renders from disk)", icon="ERROR")
        dry.operator("assetdoctor.dryrun_render", text="Run Dry-Run Render",
                     icon="RENDER_STILL")

        # Every report that currently has data (ALL features, not just F7/F6/F9 —
        # this absorbed the old N-panel's standalone Report panel in Batch 5, so
        # F1/F2/F3/F4/Geometry dry-run reports need a home here too); a small
        # selector when more than one. The Reports area always gets its own header
        # so a lone report isn't mistaken for part of the section above it (user,
        # 2026-06-23).
        layout.separator()
        hrow = layout.row(align=True)
        hrow.label(text="Reports", icon="PRESET")
        hrow.operator("assetdoctor.report_clear", text="", icon="X", emboss=False)
        present = [(k, lbl) for k, lbl in available_features(wm) if k not in self._SELECTOR_EXCLUDE]
        if not present:
            layout.label(text="Run a scan or analysis to see results.", icon="INFO")
            return

        active = active_feature(wm)
        if active not in dict(present):
            active = present[0][0]
        selrow = layout.row(align=True)
        for key, lbl in present:
            selrow.operator("assetdoctor.report_select", text=lbl,
                            depress=(key == active)).feature = key
        selrow.operator("assetdoctor.export_report", text="", icon="EXPORT").source = "report"

        if active not in TREE_FEATURES:
            try:
                report = Report.from_json(getattr(wm, data_prop(active)))
            except Exception:
                layout.label(text="(could not read report)", icon="ERROR")
                return
            titlerow = layout.row(align=True)
            titlerow.label(text=report.title, icon="PRESET")
        else:
            titlerow = layout.row(align=True)
        # Expand/Collapse All — deep trees (e.g. the File Map) are tedious to open
        # one row at a time.
        titlerow.alignment = "RIGHT"
        ea = titlerow.operator("assetdoctor.report_expand_all", text="", icon="ZOOM_IN")
        ea.feature, ea.prop, ea.expand = active, exp_prop(active), True
        ca = titlerow.operator("assetdoctor.report_expand_all", text="", icon="ZOOM_OUT")
        ca.feature, ca.prop, ca.expand = active, exp_prop(active), False
        layout.template_list(
            "ASSETDOCTOR_UL_tree", "f7report",
            wm, "assetdoctor_report_rows",
            wm, "assetdoctor_report_index",
            rows=14, sort_lock=True,
        )

    def _draw_missing_textures(self, context, layout, wm):
        """The unified Missing Textures section: a header summary, then collapsible
        material/folder categories whose members are per-file rows. All three relink
        paths STAGE a target (folder-search / category-folder / per-file pick); the
        single Relink Selected then applies. Replaces the old flat list + report."""
        n_missing = len(wm.assetdoctor_broken_imgs)
        n_linked = len(wm.assetdoctor_linked_missing_imgs)
        scanned = wm.assetdoctor_tex_scanned
        found = max(wm.assetdoctor_tex_initial_missing - n_missing, 0)
        # "matched" = still-missing textures that already have a staged target file
        # (auto-found, group-pointed, picked, or an accepted proposal) ready to relink.
        matched = sum(1 for it in wm.assetdoctor_broken_imgs if it.target)
        narrow = bool(context.region) and context.region.width < 320

        tex = layout.box().column(align=True)
        # Header summary (the visible result — no separate report needed). Before a
        # scan: just the title; after: missing + how many are matched (staged) +
        # how many were already relinked, PLUS how many more are linked (can't be
        # fixed here, see _draw_linked_missing_textures) — user report 2026-06-24: a
        # render-time Dry-Run found 144 missing images while this count alone said 9,
        # because linked images were silently excluded; surface that gap right here
        # instead of only finding out via a render. Briefer on a narrow panel.
        title = "Missing Materials/Textures"
        linked_bit = f"{n_linked} linked" if n_linked else ""
        if not scanned:
            head = title
        elif n_missing == 0:
            head = f"{title} — none missing locally" if n_linked else f"{title} — none missing"
            if found:
                head += f" ({found} relinked)"
            if linked_bit:
                head += f", {linked_bit}"
        elif narrow:
            head = f"Missing — {n_missing}✗"
            if matched:
                head += f" {matched}⇒"
            if found:
                head += f" {found}✓"
            if linked_bit:
                head += f" {linked_bit}"
        else:
            bits = [f"{n_missing} missing"]
            if matched:
                bits.append(f"{matched} matched")
            if found:
                bits.append(f"{found} relinked")
            if linked_bit:
                bits.append(linked_bit)
            head = f"{title} — " + ", ".join(bits)
        tex.label(text=head, icon="IMAGE_DATA")
        # Its "Find Missing Textures" trigger now lives in the Analyze sub-panel
        # (Phase 3a, 2026-06-25); this box keeps everything else.
        if not scanned:
            return
        if not n_missing:
            self._draw_linked_missing_textures(context, tex, wm)
            return

        # Recursive staged search over ALL missing textures (between List and the list).
        # Exact-basename first; the fuzzy matcher is the FALLBACK for vendor-renamed
        # files (proposals land in the Possible Matches sub-section below).
        srow = tex.row(align=True)
        srow.operator("assetdoctor.search_textures_folder",
                      text="Search a Folder (Recursive)…", icon="FILEBROWSER")
        srow.operator("assetdoctor.suggest_fuzzy_matches",
                      text="Suggest Matches…", icon="ZOOM_SELECTED")
        # B4 eyedropper: borrow a WORKING material's existing textures as substitute
        # candidates for the missing ones (matched by name → staged as Possible
        # Matches). The picker is the standard material datablock field + eyedropper.
        tex.label(text="Substitute from a material's textures:", icon="EYEDROPPER")
        mrow = tex.row(align=True)
        mrow.prop(wm, "assetdoctor_tex_source_material", text="")
        mrow.operator("assetdoctor.suggest_from_material", text="Suggest",
                      icon="ZOOM_SELECTED")
        # …or borrow the texture files another .blend references (offline BAT harvest).
        tex.operator("assetdoctor.suggest_from_blend",
                     text="Substitute from Another .blend…", icon="FILE_BLEND")
        tex.separator()
        hrow = tex.row(align=True)
        hrow.label(text="Missing Textures", icon="IMAGE_DATA")
        hrow.operator("assetdoctor.relink_textures_selected", text="Relink Selected",
                      icon="FILE_REFRESH")

        # Group by MATERIAL only (the folder view was dropped — user, 2026-06-22).
        mode = "MATERIAL"
        expanded = set(filter(None, wm.assetdoctor_tex_expanded.split("\n")))
        # Sentinel for items with no folder/material (no group button). NOT "\x00" —
        # a real bug: Blender's StringProperty round-trips through a C string, which
        # truncates at the first NUL byte, so storing a lone "\x00" in
        # assetdoctor_tex_expanded silently came back empty and the "(no material)"
        # triangle could never stay expanded.
        UNGROUPED = "\x02"
        groups: dict[str, list] = {}
        order: list[str] = []
        for idx, item in enumerate(wm.assetdoctor_broken_imgs):
            raw = (item.group if mode == "DIR" else item.material) or UNGROUPED
            if raw not in groups:
                groups[raw] = []
                order.append(raw)
            groups[raw].append((idx, item))

        for raw in sorted(order):
            members = groups[raw]
            total = len(members)
            matched = sum(1 for _i, it in members if it.target)
            if raw == UNGROUPED:
                disp = "(no material)" if mode == "MATERIAL" else "(no folder)"
            else:
                disp = (os.path.basename(raw.rstrip("/")) or raw) if mode == "DIR" else raw
            is_exp = raw in expanded
            crow = tex.row(align=True)
            crow.operator("assetdoctor.tex_category_toggle", text="",
                          icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False).key = raw
            label = f"{disp}  ({matched} of {total} matched)" if matched else f"{disp}  ({total})"
            crow.label(text=label,
                       icon="CHECKMARK" if matched and matched == total else
                       ("FILE_FOLDER" if mode == "DIR" else "MATERIAL"))
            # Category-level "point at a folder" (stages targets for the whole group).
            if raw != UNGROUPED:
                cop = crow.operator("assetdoctor.point_group_at_folder", text="",
                                    icon="FILE_FOLDER")
                cop.group_key = raw
                cop.by = mode
            if not is_exp:
                continue
            # Individual files: checkbox + name + staged target + per-file file picker.
            for idx, item in members:
                frow = tex.row(align=True)
                frow.separator(factor=2.0)
                frow.prop(item, "selected", text="")
                frow.label(text=item.name, icon="IMAGE_DATA")
                tgt = frow.row()
                tgt.alignment = "RIGHT"
                if item.target:
                    tgt.label(text=os.path.basename(item.target) or item.target, icon="CHECKMARK")
                elif item.ambiguous_count > 1:
                    tgt.label(text=f"{item.ambiguous_count} found elsewhere — pick one",
                             icon="ERROR")
                else:
                    tgt.label(text="no match", icon="QUESTION")
                frow.operator("assetdoctor.relink_pick_texture", text="",
                              icon="FILEBROWSER").index = idx

        self._draw_possible_matches(context, tex, wm)
        self._draw_linked_missing_textures(context, tex, wm)

    def _draw_linked_missing_textures(self, context, tex, wm):
        """Read-only companion list: missing textures owned by a LINKED Image —
        can't be relinked here (the source library owns that file path), grouped
        by library so the user knows exactly which file to go fix. No checkboxes,
        no file pickers, no Relink button — purely visibility (see
        ops.image_relink._gather_linked_missing_images for why this exists)."""
        rows = list(wm.assetdoctor_linked_missing_imgs)
        if not rows:
            return
        tex.separator()
        tex.label(text=f"Linked — fix at the source library ({len(rows)})",
                 icon="LIBRARY_DATA_BROKEN")

        LM = "\x03"  # namespaced so these keys don't collide with the lists above
        expanded = set(filter(None, wm.assetdoctor_tex_expanded.split("\n")))
        groups: dict[str, list] = {}
        for item in rows:
            groups.setdefault(item.library or "(unknown library)", []).append(item)

        for lib in sorted(groups):
            members = groups[lib]
            ckey = LM + lib
            is_exp = ckey in expanded
            crow = tex.row(align=True)
            crow.operator("assetdoctor.tex_category_toggle", text="",
                          icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False).key = ckey
            crow.label(text=f"{os.path.basename(lib)}  ({len(members)})", icon="FILE_BLEND")
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
    _CONF = {"high": ("CHECKMARK", "high", 2),
             "medium": ("QUESTION", "med", 1),
             "low": ("DOT", "low", 0)}

    # Below this name-token overlap, a duplicate family's material looks mis-attributed
    # (e.g. a lightBlue texture under a brown material) → flag it + offer the eyedropper.
    _DUP_MISMATCH_AFFINITY = 0.5

    def _draw_possible_matches(self, context, tex, wm):
        """F6 step 4 — the FUZZY proposals (a vendor-renamed file the exact search
        couldn't place). A second list grouped by material, COLLAPSIBLE and collapsed
        by default (so a long Suggest-Matches result doesn't bury the panel), with
        materials ordered by their best confidence (high first). Accept one row, a
        whole material, or all; accepting moves the proposal into the Missing Textures
        list above (ticked)."""
        proposals = [(idx, item) for idx, item in enumerate(wm.assetdoctor_broken_imgs)
                     if item.proposal and not item.target]
        if not proposals:
            return

        tex.separator()
        hrow = tex.row(align=True)
        hrow.label(text=f"Possible Matches — {len(proposals)}", icon="ZOOM_SELECTED")
        hrow.operator("assetdoctor.accept_all_matches", text="Accept All", icon="CHECKMARK")
        tex.label(text="Name-similarity guesses — review before accepting.", icon="INFO")

        # Category keys are namespaced ("\x01" + material) so they don't collide with
        # the Missing list's material keys in the shared expanded-set.
        PM = "\x01"
        expanded = set(filter(None, wm.assetdoctor_tex_expanded.split("\n")))

        groups: dict[str, list] = {}
        for idx, item in proposals:
            groups.setdefault(item.material or "(no material)", []).append((idx, item))

        def conf_rank(it):
            return self._CONF.get(it.proposal_confidence, ("DOT", "?", 0))[2]

        def cat_rank(members):
            return max(conf_rank(it) for _i, it in members)

        # Materials ordered by best confidence (high→low), then name.
        for key in sorted(groups, key=lambda k: (-cat_rank(groups[k]), k.lower())):
            members = sorted(groups[key], key=lambda pair: -conf_rank(pair[1]))
            ckey = PM + key
            is_exp = ckey in expanded
            best_lbl = self._CONF.get(
                {2: "high", 1: "medium", 0: "low"}[cat_rank(members)], ("", "?", 0))[1]
            crow = tex.row(align=True)
            crow.operator("assetdoctor.tex_category_toggle", text="",
                          icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False).key = ckey
            crow.label(text=f"{key}  ({len(members)}, {best_lbl})", icon="MATERIAL")
            # Material-level accept (the whole rolled-up group) — CHECKMARK marks the
            # group action, distinct from the single-row IMPORT below.
            crow.operator("assetdoctor.accept_material_matches", text="",
                          icon="CHECKMARK").material = key
            if not is_exp:
                continue
            for idx, item in members:
                frow = tex.row(align=True)
                frow.separator(factor=2.0)
                frow.label(text=item.name, icon="IMAGE_DATA")
                prop = frow.row()
                prop.alignment = "RIGHT"
                icon, conf, _r = self._CONF.get(item.proposal_confidence, ("DOT", "?", 0))
                tag = f"{conf}, diff res" if item.proposal_res_mismatch else conf
                prop.label(text=f"{os.path.basename(item.proposal)}  ({tag})", icon=icon)
                frow.operator("assetdoctor.accept_match", text="",
                              icon="IMPORT").index = idx

    # Reconnect confidence -> (icon, short label). "none" shows neither — the row
    # just offers the source's full candidate list with no particular guess.
    # "transitive" is set by ops.datablock_reconnect.reconnect_selected AFTER an
    # apply attempt found the chosen candidate was itself unresolved further
    # upstream — distinct from "none" (never tried) so the user can tell "this
    # is genuinely stuck, the library itself doesn't have it either" from
    # "just hasn't been matched yet".
    _RECONNECT_CONF = {
        "exact": ("CHECKMARK", "exact"),
        "numbered": ("FILE_REFRESH", "renamed"),
        "fuzzy": ("QUESTION", "fuzzy"),
        "transitive": ("ERROR", "missing upstream too"),
        "none": ("BLANK1", ""),
    }

    def _draw_datablock_dups(self, context, layout, wm):
        """Batch C #3 — generic Duplicate Data-blocks: find .NNN families across
        Objects/Actions/Node Groups/etc. (Materials/Meshes/Images keep their own
        dedicated tools), group by KIND, pick a keeper per family, Merge Selected.
        Mirrors the Duplicate Materials/Textures section's shape."""
        families = wm.assetdoctor_datablock_families
        scanned = wm.assetdoctor_datablock_scanned
        removable = wm.assetdoctor_datablock_removable
        conflicts = wm.assetdoctor_datablock_conflicts

        box = layout.box().column(align=True)
        if not scanned:
            head = "Duplicate Data-blocks"
        elif not len(families) and not conflicts:
            head = "Duplicate Data-blocks — none found"
        else:
            kinds = len({row.kind for row in families})
            bits = [f"{kinds} kind(s)", f"{removable} removable"]
            if conflicts:
                bits.append(f"{conflicts} differing/unverified")
            head = "Duplicate Data-blocks — " + ", ".join(bits)
        box.label(text=head, icon="LIBRARY_DATA_OVERRIDE")
        box.label(text="Objects, Actions, Node Groups, etc. — Materials/Meshes/Images "
                  "have their own dedup tools.", icon="INFO")

        # Its "Find Duplicate Data-blocks" trigger now lives in the Analyze
        # sub-panel (Phase 3a, 2026-06-25); this box keeps the results list +
        # Merge Selected.
        if scanned and len(families):
            box.operator("assetdoctor.merge_datablock_selected",
                         text="Merge Selected (Backup)", icon="AREA_JOIN")
        if not (scanned and (len(families) or conflicts)):
            return

        expanded = set(filter(None, wm.assetdoctor_datablock_expanded.split("\n")))
        groups: dict[str, list] = {}
        for row in families:
            groups.setdefault(row.kind, []).append(row)

        for kind in sorted(groups, key=str.lower):
            members = groups[kind]
            removable_here = sum(r.removable for r in members)
            is_exp = kind in expanded
            crow = box.row(align=True)
            crow.operator("assetdoctor.datablock_category_toggle", text="",
                          icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False).key = kind
            crow.label(text=f"{kind}  ({len(members)} family, −{removable_here})",
                      icon="LIBRARY_DATA_OVERRIDE")
            if not is_exp:
                continue
            for row in members:
                frow = box.row(align=True)
                frow.separator(factor=2.0)
                frow.prop(row, "selected", text="")
                base = row.name.split(":", 1)[-1]
                frow.label(text=f"{base}  (−{row.removable})", icon="LIBRARY_DATA_OVERRIDE")
                keep = frow.row()
                keep.alignment = "RIGHT"
                keep.label(text="keep", icon="PINNED")
                keep.prop(row, "keeper", text="")

        conflict_lines = [ln for ln in wm.assetdoctor_datablock_conflicts_text.split("\n") if ln]
        if conflict_lines:
            ckey = "\x03conflicts"
            is_exp = ckey in expanded
            crow = box.row(align=True)
            crow.operator("assetdoctor.datablock_category_toggle", text="",
                          icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False).key = ckey
            crow.label(text=f"Different content / unverified — kept separate ({len(conflict_lines)})",
                      icon="QUESTION")
            if is_exp:
                for ln in conflict_lines:
                    r = box.row(align=True)
                    r.separator(factor=2.0)
                    r.label(text=ln, icon="DOT")

    def _draw_reconnect(self, context, layout, wm):
        """Batch C #2 — reconnect missing data-blocks. Rows group by their broken/
        renamed source LIBRARY (the natural unit — one library's blocks usually all
        need the same fix); a group-level file picker peeks a chosen source .blend
        (never loads it) and suggests the closest name per row (core.reconnect);
        Reconnect Selected links the ticked rows in and user_remaps the placeholders.
        Mirrors the Duplicate Materials/Textures section's grouped shape."""
        rows = wm.assetdoctor_missing_blocks
        scanned = wm.assetdoctor_missing_scanned

        box = layout.box().column(align=True)
        libs = len({r.library for r in rows})
        staged = sum(1 for r in rows if r.selected and r.target)
        if not scanned:
            head = "Datablock Reconnect"
        elif not len(rows):
            head = "Datablock Reconnect — none found"
        else:
            head = f"Datablock Reconnect — {len(rows)} missing, {libs} group(s), {staged} staged"
        box.label(text=head, icon="LIBRARY_DATA_OVERRIDE")

        # Its "Find Reconnectable Data-blocks" trigger now lives in the Analyze
        # sub-panel (Phase 3a, 2026-06-25 — also absorbed the old, redundant Find
        # Missing Data-blocks report, the exact same underlying scan); this box
        # keeps the results list + Reconnect Selected.
        if scanned and len(rows):
            box.operator("assetdoctor.reconnect_selected",
                         text="Reconnect Selected (Backup)", icon="LINKED")
        if not (scanned and len(rows)):
            return

        expanded = set(filter(None, wm.assetdoctor_missing_expanded.split("\n")))
        groups: dict[str, list] = {}
        order: list[str] = []
        for item in rows:
            if item.library not in groups:
                groups[item.library] = []
                order.append(item.library)
            groups[item.library].append(item)

        for library in sorted(order, key=lambda lib: (-len(groups[lib]), lib.lower())):
            members = groups[library]
            matched = sum(1 for m in members if m.confidence not in ("none", "transitive"))
            stuck = sum(1 for m in members if m.confidence == "transitive")
            lib_found = members[0].library_found
            has_source = bool(members[0].source_blend)
            is_exp = library in expanded
            crow = box.row(align=True)
            crow.operator("assetdoctor.reconnect_category_toggle", text="",
                          icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False).key = library
            disp = library or "(unknown library)"
            bits = []
            if matched:
                bits.append(f"{matched} suggested")
            if stuck:
                bits.append(f"{stuck} stuck (missing upstream too)")
            label = f"{disp}  ({', '.join(bits)})" if bits else f"{disp}  ({len(members)})"
            # ERROR icon when the group's OWN library can't be found anywhere in
            # this session AND no source has been picked yet — distinguishes
            # "genuinely needs a manual file pick" from the normal broken-link
            # icon (user report 2026-06-24: these looked identical before).
            crow.label(text=label,
                      icon="LIBRARY_DATA_BROKEN" if (lib_found or has_source) else "ERROR")
            pick = crow.operator("assetdoctor.reconnect_pick_source", text="",
                                 icon="FILEBROWSER")
            pick.library = library
            if not is_exp:
                continue
            source = members[0].source_blend
            srow = box.row(align=True)
            srow.separator(factor=2.0)
            if source:
                srow.label(text=os.path.basename(source), icon="FILE_BLEND")
            elif lib_found:
                srow.label(text="no source picked yet — click the folder icon above",
                          icon="QUESTION")
            else:
                srow.label(text="library not found anywhere in this session — pick a "
                          "source .blend manually", icon="ERROR")
            for item in members:
                frow = box.row(align=True)
                frow.separator(factor=2.0)
                frow.prop(item, "selected", text="")
                frow.label(text=f"{item.kind}: {item.name}", icon="LIBRARY_DATA_BROKEN")
                icon, conf_label = self._RECONNECT_CONF.get(item.confidence, ("BLANK1", ""))
                if conf_label:
                    cf = frow.row()
                    cf.alignment = "RIGHT"
                    cf.label(text=conf_label, icon=icon)
                frow.prop(item, "target", text="")

    def _draw_examine_library(self, context, layout, wm):
        """Examine Library: list everything the current file links from a chosen
        (working) library and offer to re-source it from memory first — local,
        then another already-loaded library — falling back to Make Local or a
        per-row manual file+item pick. Grouped by KIND, mirrors the Duplicate
        Data-blocks section's shape."""
        rows = wm.assetdoctor_examine_rows
        scanned = wm.assetdoctor_examine_scanned

        box = layout.box().column(align=True)
        box.label(text="Examine Library", icon="LIBRARY_DATA_DIRECT")
        box.label(text="Retarget everything a library provides to your local file or "
                  "another library (e.g. to break a circular reference).", icon="INFO")
        pick = box.row(align=True)
        pick.prop_search(wm, "assetdoctor_examine_library_pick", bpy.data, "libraries", text="")
        pick.operator("assetdoctor.examine_library", text="Examine", icon="VIEWZOOM")

        if scanned and len(rows):
            staged = sum(1 for r in rows if r.selected)
            suggested = sum(1 for r in rows if r.suggested_kind != "none")
            box.label(text=f"{len(rows)} data-block(s) from {wm.assetdoctor_examine_library} — "
                      f"{suggested} in-memory match(es), {staged} staged",
                      icon="LIBRARY_DATA_OVERRIDE")
            box.operator("assetdoctor.examine_apply_selected",
                         text="Apply Selected (Backup)", icon="LINKED")
        elif scanned:
            box.label(text="✓ Nothing currently links from that library", icon="CHECKMARK")
        if not (scanned and len(rows)):
            return

        expanded = set(filter(None, wm.assetdoctor_examine_expanded.split("\n")))
        groups: dict[str, list] = {}
        for idx, item in enumerate(rows):
            groups.setdefault(item.kind, []).append((idx, item))

        for kind in sorted(groups, key=str.lower):
            members = groups[kind]
            is_exp = kind in expanded
            crow = box.row(align=True)
            crow.operator("assetdoctor.examine_category_toggle", text="",
                          icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False).key = kind
            crow.label(text=f"{kind}  ({len(members)})", icon="LIBRARY_DATA_DIRECT")
            if not is_exp:
                continue
            for idx, item in members:
                frow = box.row(align=True)
                frow.separator(factor=2.0)
                frow.prop(item, "selected", text="")
                frow.label(text=item.name, icon="LIBRARY_DATA_DIRECT")
                if item.make_local:
                    pass  # the Make Local checkbox below already says it all
                elif item.use_suggested and item.suggested_kind == "local":
                    s = frow.row()
                    s.alignment = "RIGHT"
                    text, icon = _graph_match_suffix(f"local: {item.suggested_name}", item.graph_match)
                    s.label(text=text, icon=icon)
                elif item.use_suggested and item.suggested_kind == "library":
                    s = frow.row()
                    s.alignment = "RIGHT"
                    base = (f"{os.path.basename(item.suggested_library)}: "
                            f"{item.suggested_name}")
                    text, icon = _graph_match_suffix(base, item.graph_match)
                    s.label(text=text, icon=icon)
                elif item.source_blend:
                    frow.prop(item, "target", text="")
                else:
                    s = frow.row()
                    s.alignment = "RIGHT"
                    s.label(text="no in-memory match", icon="QUESTION")
                frow.prop(item, "make_local", text="", icon="FILE_TICK")
                frow.operator("assetdoctor.examine_pick_source", text="",
                              icon="FILEBROWSER").index = idx

    def _draw_duplicate_textures(self, context, layout, wm):
        """F6 Layer 2/3 — the redesigned Duplicate Materials/Textures section: an
        inline summary header, top Find/Merge/Export, then collapsible material
        groups whose rows are content-identical merge families, each with an
        include checkbox + a keeper dropdown (pick which datablock survives).
        Mirrors the Missing section; no separate report (it's still stashed for
        the Export button). (History: a separate fast/name-only "Find .NNN" scan
        was removed 2026-06-24 — confirmed redundant with Find Content Dups,
        which uses the identical fingerprint over a strict superset of images.)"""
        scanned = wm.assetdoctor_dup_scanned
        families = wm.assetdoctor_dup_families
        narrow = bool(context.region) and context.region.width < 320

        dup = layout.box().column(align=True)
        # Summary header (the visible result). Materials = distinct groups with a
        # merge; Textures redundant = total removable datablocks.
        mats = len({row.material or "(no material)" for row in families})
        removable = wm.assetdoctor_dup_removable
        conflicts = wm.assetdoctor_dup_conflicts
        if not scanned:
            head = "Duplicate Materials/Textures"
        elif not len(families) and not conflicts:
            head = "Duplicate Materials/Textures — none found"
        elif narrow:
            head = f"Duplicates — {mats} mat / {removable} tex"
        else:
            bits = [f"{mats} material(s)", f"{removable} texture(s) redundant"]
            if conflicts:
                bits.append(f"{conflicts} differing")
            head = "Duplicate Materials/Textures — " + ", ".join(bits)
        dup.label(text=head, icon="IMAGE_DATA")

        # Its "Find Duplicate Content" + "Find Resolution Variants" triggers now
        # live in the Analyze sub-panel (Phase 3a, 2026-06-25); this box keeps the
        # results list + Merge Selected/Export.
        if scanned and len(families):
            brow = dup.row(align=True)
            brow.operator("assetdoctor.merge_dup_selected",
                          text="Merge Selected (Backup)", icon="AREA_JOIN")
            brow.operator("assetdoctor.export_report", text="",
                          icon="EXPORT").feature = "f6dup"
        if not (scanned and (len(families) or conflicts)):
            return

        from ..core.imagematch import name_affinity

        def _eff_mat(row):
            return (row.material_override.name if row.material_override
                    else (row.material or "(no material)"))

        def _mismatch(row):
            # An "apparent mismatch" = the (effective) material's name barely overlaps
            # the texture's name, e.g. a lightBlue texture under a brown material.
            eff = _eff_mat(row)
            return eff != "(no material)" and name_affinity(row.name, eff) < self._DUP_MISMATCH_AFFINITY

        expanded = set(filter(None, wm.assetdoctor_dup_expanded.split("\n")))
        groups: dict[str, list] = {}
        for row in families:
            groups.setdefault(_eff_mat(row), []).append(row)

        for key in sorted(groups, key=str.lower):
            members = groups[key]
            removable_here = sum(r.removable for r in members)
            mism = [r for r in members if _mismatch(r)]
            is_exp = key in expanded
            crow = dup.row(align=True)
            crow.operator("assetdoctor.dup_category_toggle", text="",
                          icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False).key = key
            # Alert only the label (not the whole row) when some textures here don't
            # look like they belong to this material.
            lab = crow.row()
            lab.alert = bool(mism)
            suffix = f", ⚠{len(mism)} mismatch" if mism else ""
            lab.label(text=f"{key}  ({len(members)} family, −{removable_here}{suffix})",
                      icon="ERROR" if mism else "MATERIAL")
            # Master keeper for the whole material (sets every family's keeper by a
            # policy) — the material-level counterpart to the per-family dropdowns.
            crow.operator("assetdoctor.dup_material_keeper", text="",
                          icon="DOWNARROW_HLT").material = key
            if not is_exp:
                continue
            for row in members:
                bad = _mismatch(row)
                frow = dup.row(align=True)
                frow.separator(factor=2.0)
                frow.prop(row, "selected", text="")
                name = frow.row()
                name.alert = bad
                name.label(text=f"{row.name}  (−{row.removable})",
                           icon="ERROR" if bad else "IMAGE_DATA")
                # Alternate material picker (eyedropper): re-home a mis-attributed
                # family under the correct material. Shown when it looks wrong (or was
                # already overridden). Organizational only — doesn't rewire nodes.
                if bad or row.material_override:
                    frow.prop(row, "material_override", text="")
                keep = frow.row()
                keep.alignment = "RIGHT"
                keep.label(text="keep", icon="PINNED")
                keep.prop(row, "keeper", text="")

        # Families with differing content — shown (collapsible) but never merged.
        conflict_lines = [ln for ln in wm.assetdoctor_dup_conflicts_text.split("\n") if ln]
        if conflict_lines:
            ckey = "\x02conflicts"
            is_exp = ckey in expanded
            crow = dup.row(align=True)
            crow.operator("assetdoctor.dup_category_toggle", text="",
                          icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False).key = ckey
            crow.label(text=f"Different content — kept separate ({len(conflict_lines)})",
                       icon="QUESTION")
            if is_exp:
                for ln in conflict_lines:
                    r = dup.row(align=True)
                    r.separator(factor=2.0)
                    r.label(text=ln, icon="DOT")
