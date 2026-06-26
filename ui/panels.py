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
    # The ARMATURE/rig this part rolls up under (own name when it IS the rig,
    # or when no rig could be resolved — see ops.linkchain._resolve_rig).
    rig: bpy.props.StringProperty()  # type: ignore[valid-type]


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
    # Generic free-form per-row tag, repurposed per list (items 6/7/11,
    # 2026-06-25): unused for Inconsistent/Duplicate Library Paths and
    # Absolute Paths (``group`` already carries their grouping key); for
    # Resolution Variant rows it holds the member's own resolution token
    # ("1k"/"2k"/...), needed by Select High/Low Resolution.
    tag: bpy.props.StringProperty()  # type: ignore[valid-type]


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


class ASSETDOCTOR_PG_material_family(bpy.types.PropertyGroup):
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


class _SceneFeaturePanel:
    """Shared bl_* attributes for the legacy-feature Scene sub-panels (Make
    Local, Duplicate Materials, Orphans, Geometry, Utilities) — migrated off
    the old VIEW_3D N-panel (Batch 5, 2026-06-23) so
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
    for row in wm.assetdoctor_analyze_steps:
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
    try:
        nodes = (nodes_from_json(raw) if feature in TREE_FEATURES
                 else report_to_tree(Report.from_json(raw)))
    except Exception:
        return False, []
    return True, nodes


def _report_headline(nodes, feature: str) -> tuple[str, object | None]:
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
            return summary.children[0].label, None
        return "✓ nothing found", None
    parts = [_fmt_count(n.label, n.detail) for n in cats[:4]]
    if len(cats) > 4:
        parts.append(f"+{len(cats) - 4} more")
    return " · ".join(parts), None


def _draw_report_detail(layout, wm, feature: str) -> None:
    """One Analyze button's report result: a single row carrying BOTH the
    one-line headline AND its own expand arrow — no separate "Details" row
    (item a, 2026-06-25). When expanded, every remaining category draws as
    its OWN collapsible row, collapsed by default (item c), via the inline-
    only ``assetdoctor_detail_expanded`` key set (independent of each
    feature's own ``exp_prop`` — the dedicated Reports tab pre-seeds THAT one
    expanded, which would defeat "starts collapsed" here). Plain depth
    indentation only, no tree-connector glyphs (item b). The one node the
    headline already quotes verbatim is left out of the body so it isn't
    shown twice (item e); when nothing remains beyond the headline, no arrow
    is drawn at all — there's nothing left to disclose (item f).

    All rows draw inside one ``column(align=True)`` (user feedback,
    2026-06-25 item 4: vertical spacing between rows was "inconsistent and
    too large") — a bare sequence of top-level ``layout.row()`` calls each
    carries Blender's normal inter-widget margin; an aligned column packs
    them tightly, matching the Missing Textures section's spacing."""
    from ..core.tree import flatten_visible

    has_run, nodes = _feature_tree_nodes(wm, feature)
    if not has_run:
        return
    col = layout.column(align=True)
    row = col.row(align=True)
    row.separator(factor=2.2)
    if not nodes:
        row.label(text="✓ nothing found")
        return

    headline, skip = _report_headline(nodes, feature)
    remaining = [n for n in nodes if n is not skip]
    if not remaining:
        row.label(text=headline)
        return

    expanded = set(filter(None, wm.assetdoctor_detail_expanded.split("\n")))
    root_key = f"{feature}:__inline_root__"
    is_open = root_key in expanded
    op = row.operator("assetdoctor.toggle_inline_detail", text="",
                       icon="TRIA_DOWN" if is_open else "TRIA_RIGHT", emboss=False)
    op.key = root_key
    row.label(text=headline)
    if not is_open:
        return

    for r in flatten_visible(remaining, expanded):
        drow = col.row(align=True)
        drow.separator(factor=2.8 + r.indent * 1.4)
        if r.has_children:
            top = drow.operator("assetdoctor.toggle_inline_detail", text="",
                                icon="TRIA_DOWN" if r.expanded else "TRIA_RIGHT", emboss=False)
            top.key = r.key
        else:
            drow.label(text="", icon="BLANK1")
        if r.icon:
            drow.label(text="", icon=r.icon)
        if r.ref:
            bop = drow.operator("assetdoctor.select_datablock", text=r.label,
                                 icon="NONE", emboss=False)
            bop.type, bop.name = r.ref["type"], r.ref["name"]
        else:
            drow.label(text=r.label)
        if r.detail:
            sub = drow.row()
            sub.alignment = "RIGHT"
            sub.label(text=r.detail)


def _missing_textures_headline(wm, narrow: bool) -> str:
    """The Missing Textures section's own header summary, factored out so the
    Analyze button can show the same line inline (Phase 3c)."""
    n_missing = len(wm.assetdoctor_broken_imgs)
    n_linked = len(wm.assetdoctor_linked_missing_imgs)
    scanned = wm.assetdoctor_tex_scanned
    found = max(wm.assetdoctor_tex_initial_missing - n_missing, 0)
    matched = sum(1 for it in wm.assetdoctor_broken_imgs if it.target)

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
    scanned = wm.assetdoctor_dup_scanned
    families = wm.assetdoctor_dup_families
    mats = len({row.material or "(no material)" for row in families})
    removable = wm.assetdoctor_dup_removable
    conflicts = wm.assetdoctor_dup_conflicts
    if not scanned:
        return ""
    if not len(families) and not conflicts:
        return "Duplicate Materials/Textures — none found"
    if narrow:
        return f"Duplicates — {mats} mat / {removable} tex"
    bits = [f"{mats} material(s)", f"{removable} texture(s) redundant"]
    if conflicts:
        bits.append(f"{conflicts} differing")
    return "Duplicate Materials/Textures — " + ", ".join(bits)


def _duplicates_has_run(wm) -> bool:
    """Item 3, 2026-06-25: "Find Duplicates" status icon — true once ANY of
    the 4 folded-in scans has data, regardless of which one was clicked."""
    return bool(wm.assetdoctor_datablock_scanned or wm.assetdoctor_mat_scanned
                or _feature_has_run(wm, "geo") or wm.assetdoctor_dup_scanned)


def _draw_duplicates_summary(layout, wm, narrow: bool) -> None:
    """Item 3, 2026-06-25: "Find Duplicates" replaces 4 separate buttons
    (Data-blocks/Materials/Geometry/Content), so its result needs all 4 of
    their headlines — none of the section boxes below show their own
    anymore (each used to rely on its now-removed individual Analyze row).
    Find Duplicate Geometry is the one exception: it's tree-based and
    already draws its own headline+arrow row via ``_draw_report_detail``
    (called separately), so it is deliberately NOT repeated here."""
    for bit in (_datablock_dups_headline(wm), _material_dups_headline(wm),
                _duplicate_textures_headline(wm, narrow)):
        if not bit:
            continue
        row = layout.row(align=True)
        row.separator(factor=2.2)
        row.label(text=bit)


def _datablock_dups_headline(wm) -> str:
    """The Duplicate Data-blocks section's own header summary, factored out
    so the Analyze button can show the same line inline."""
    families = wm.assetdoctor_datablock_families
    scanned = wm.assetdoctor_datablock_scanned
    removable = wm.assetdoctor_datablock_removable
    conflicts = wm.assetdoctor_datablock_conflicts
    if not scanned:
        return ""
    if not len(families) and not conflicts:
        return "Duplicate Data-blocks — none found"
    kinds = len({row.kind for row in families})
    bits = [f"{kinds} kind(s)", f"{removable} removable"]
    if conflicts:
        bits.append(f"{conflicts} differing/unverified")
    return "Duplicate Data-blocks — " + ", ".join(bits)


def _reconnect_headline(wm) -> str:
    """The Datablock Reconnect section's own header summary, factored out so
    the Analyze button can show the same line inline."""
    rows = wm.assetdoctor_missing_blocks
    scanned = wm.assetdoctor_missing_scanned
    if not scanned:
        return ""
    if not len(rows):
        return "Datablock Reconnect — none found"
    libs = len({r.library for r in rows})
    staged = sum(1 for r in rows if r.selected and r.target)
    return f"Datablock Reconnect — {len(rows)} missing, {libs} group(s), {staged} staged"


def _all_missing_summary(wm) -> str:
    """"Find All Missing" runs both the broken-library-link scan and the
    datablock-reconnect scan; combine their counts into one line."""
    if not wm.assetdoctor_missing_scanned:
        return ""
    broken = len(wm.assetdoctor_broken_libs)
    missing = len(wm.assetdoctor_missing_blocks)
    if not broken and not missing:
        return "✓ nothing missing"
    return f"{broken} broken link(s), {missing} missing data-block(s)"


def _flatten_candidates_summary(wm) -> str:
    """``assetdoctor_flatten_plans_json`` is non-empty (even if "{}") once a
    scan has run, so its presence — not the row count — is the "has this
    been run" signal (negative-output principle: say so when nothing was
    found, don't just look identical to never-run)."""
    if not wm.assetdoctor_flatten_plans_json:
        return ""
    rows = wm.assetdoctor_flatten_candidates
    if not len(rows):
        return wm.assetdoctor_flatten_remote_note or "✓ no flattenable characters found"
    rigs = len({r.rig for r in rows})
    ready = sum(1 for r in rows if r.ready)
    return f"{len(rows)} part(s) across {rigs} rig(s)/character(s) — {ready} ready, {len(rows) - ready} blocked"


def _resource_summary(wm) -> str:
    return wm.assetdoctor_resource_totals


def _profile_render_summary(wm) -> str:
    ram = wm.assetdoctor_profiled_ram
    return f"Real peak RAM: {ram}" if ram else ""


def _draw_resource_breakdown(layout, wm):
    """The by-type RAM/VRAM/disk breakdown, rolled up as a child directly below
    the Analyze Memory/Disk button's inline summary (replaces the standalone
    Resource Analyzer panel — same template_list + Export, just relocated so
    the detail lives right under the totals it explains)."""
    if not wm.assetdoctor_resource_tree:
        return
    col = layout.column(align=True)
    hint = col.row(align=True)
    hint.separator(factor=2.2)
    hint.label(text="RAM / VRAM estimated; disk accurate", icon="INFO")
    col.template_list(
        "ASSETDOCTOR_UL_tree", "resource",
        wm, "assetdoctor_resource_rows",
        wm, "assetdoctor_resource_index",
        rows=8, sort_lock=True,
    )
    erow = col.row(align=True)
    erow.separator(factor=2.2)
    erow.operator("assetdoctor.export_report", text="Export…", icon="EXPORT").source = "resource"


def _analyze_row(layout, wm, step_key, opname, text, icon, summary="", has_run=None):
    """One Analyze trigger button, full-width (Phase 3 feedback item 2a,
    2026-06-25: one per row so each gets a status icon AND a result line),
    with its inline result summary directly below when there's one to show.

    ``has_run`` drives the status icon (item 9, 2026-06-25) — defaults to
    "the summary text is non-empty" (true for every feature whose headline
    this draws directly); the tree-based features that now draw their own
    headline inside ``_draw_report_detail`` instead must pass it explicitly."""
    if has_run is None:
        has_run = bool(summary)
    row = layout.row(align=True)
    row.label(text="", icon=_analyze_step_status_icon(wm, step_key, has_run))
    op = row.operator(opname, text=text, icon=icon)
    if summary:
        srow = layout.row(align=True)
        srow.separator(factor=2.2)
        srow.label(text=summary)
    return op


def _draw_flatten_candidates(layout, wm):
    """Phase 4-B picker, grouped by ARMATURE/rig (user feedback, 2026-06-25:
    present everything in terms of the rig, with body/eyes/clothes rolled up
    underneath). Each rig's combined replay rollup (core.linkchain.
    build_rig_rollup) shows directly below its own row — no separate report
    tab needed to judge whether flattening one is worth it; the small
    FILE_TEXT button stashes the read-only preview (f7flatten report); the
    "Flatten (creates backup)" button (Phase 4 Apply, 2026-06-25) only
    appears once expanded — and only when at least one part is ready — so
    the real mutation isn't one click away from the collapsed list."""
    rows = wm.assetdoctor_flatten_candidates
    if not len(rows):
        return
    import json

    from ..core import linkchain

    cached = json.loads(wm.assetdoctor_flatten_plans_json or "{}")
    expanded = set(filter(None, wm.assetdoctor_flatten_expanded.split("\n")))

    groups: dict[str, list] = {}
    order: list[str] = []
    for row in rows:
        if row.rig not in groups:
            groups[row.rig] = []
            order.append(row.rig)
        groups[row.rig].append(row)

    box = layout.box().column(align=True)
    for rig in sorted(order, key=str.lower):
        members = groups[rig]
        plans = [linkchain.flatten_plan_from_dict(cached[m.name]) for m in members if m.name in cached]
        ready = sum(1 for m in members if m.ready)
        is_exp = rig in expanded
        crow = box.row(align=True)
        crow.operator("assetdoctor.flatten_category_toggle", text="",
                      icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False).key = rig
        crow.label(text=f"{rig}  ({ready}/{len(members)} part(s) ready)", icon="ARMATURE_DATA")
        crow.operator("assetdoctor.build_flatten_plan", text="", icon="FILE_TEXT").name = rig
        if not is_exp:
            continue
        rollup = box.row(align=True)
        rollup.separator(factor=2.0)
        rollup.label(text=linkchain.build_rig_rollup(plans), icon="INFO")
        if ready:
            arow = box.row(align=True)
            arow.separator(factor=2.0)
            aop = arow.operator("assetdoctor.build_flatten_plan",
                                text="Flatten (creates backup)", icon="CHECKMARK")
            aop.name = rig
            aop.apply = True
        for m in members:
            mrow = box.row(align=True)
            mrow.separator(factor=3.0)
            mrow.label(text=f"{m.name}  —  {m.status}",
                      icon="CHECKMARK" if m.ready else "QUESTION")


class ASSETDOCTOR_PT_analyze(_SceneFeaturePanel, bpy.types.Panel):
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
    bl_idname = "ASSETDOCTOR_PT_analyze"
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        narrow = bool(context.region) and context.region.width < 320

        layout.operator("assetdoctor.analyze_all", icon="PLAY")

        _analyze_row(layout, wm, "check_link_chain", "assetdoctor.scan_dependencies",
                     "Check Link Chain", "VIEWZOOM", has_run=_feature_has_run(wm, "f7"))
        _draw_report_detail(layout, wm, "f7")
        _analyze_row(layout, wm, "audit_file", "assetdoctor.analyze_overrides",
                     "Audit This File", "LIBRARY_DATA_OVERRIDE", has_run=_feature_has_run(wm, "f7live"))
        _draw_report_detail(layout, wm, "f7live")
        _analyze_row(layout, wm, "find_flattenable_chains", "assetdoctor.scan_link_chains",
                     "Find Flattenable Link Chains", "LINKED", has_run=_feature_has_run(wm, "f7chain"))
        _draw_report_detail(layout, wm, "f7chain")
        _analyze_row(layout, wm, "", "assetdoctor.scan_flatten_candidates",
                     "Find Flattenable Characters", "LIBRARY_DATA_OVERRIDE",
                     _flatten_candidates_summary(wm))
        _draw_flatten_candidates(layout, wm)

        _analyze_row(layout, wm, "find_broken_links", "assetdoctor.scan_broken_links",
                     "Find Broken Library Links", "LIBRARY_DATA_BROKEN",
                     has_run=_feature_has_run(wm, "f7links"))
        _draw_report_detail(layout, wm, "f7links")
        # Item 3, 2026-06-25 (user request): Find Duplicate Materials/Geometry/
        # Content folded into ONE "Find Duplicates" trigger alongside Find
        # Duplicate Data-blocks — one click runs all 4 scans; each one's own
        # report/list section (below) is unchanged, so the result reads as one
        # combined summary followed by what each individual button would have
        # shown. Resolution Variants stays its OWN separate button (a
        # different kind of analysis — multi-res footprint, not duplicates).
        _analyze_row(layout, wm, "find_duplicate_datablocks", "assetdoctor.find_duplicates",
                     "Find Duplicates", "LIBRARY_DATA_OVERRIDE",
                     has_run=_duplicates_has_run(wm))
        _draw_duplicates_summary(layout, wm, narrow)
        _draw_datablock_dups(layout, wm)
        _draw_material_dups(layout, wm)
        _draw_report_detail(layout, wm, "geo")

        _analyze_row(layout, wm, "find_reconnectable", "assetdoctor.scan_reconnect_targets",
                     "Find Reconnectable Data-blocks", "LIBRARY_DATA_OVERRIDE",
                     _reconnect_headline(wm))
        _analyze_row(layout, wm, "", "assetdoctor.scan_all_missing",
                     "Find All Missing", "VIEWZOOM", _all_missing_summary(wm))

        _analyze_row(layout, wm, "find_missing_textures", "assetdoctor.scan_broken_textures",
                     "Find Missing Textures", "IMAGE_DATA",
                     _missing_textures_headline(wm, narrow))

        _analyze_row(layout, wm, "find_resolution_variants", "assetdoctor.scan_res_variants",
                     "Find Resolution Variants", "FULLSCREEN_ENTER",
                     _res_variants_headline(wm))
        _draw_res_variants(layout, wm)

        _analyze_row(layout, wm, "find_orphans", "assetdoctor.scan_orphans",
                     "Find Orphans", "NONE", has_run=_feature_has_run(wm, "f4")).purge_orphans = False
        _draw_report_detail(layout, wm, "f4")

        # Footprint/impact analyses — a different KIND of analysis (not "is
        # something broken") — separated from the find-a-problem buttons above
        # (user request, 2026-06-25).
        layout.separator()
        _analyze_row(layout, wm, "analyze_memory_disk", "assetdoctor.analyze_resources",
                     "Analyze Memory/Disk", "VIEWZOOM", _resource_summary(wm))
        _draw_resource_breakdown(layout, wm)
        # "Make Local Impact" = the old Make Local panel's "Report (Dry Run)"
        # button, relocated here for now (user request, 2026-06-25) — it will
        # replace that panel once a Fix-it/Apply button joins it in Cleanup &
        # Fixes (Phase 3c), at which point the whole Make Local panel can go.
        _analyze_row(layout, wm, "", "assetdoctor.make_local",
                     "Make Local Impact", "LIBRARY_DATA_DIRECT",
                     has_run=_feature_has_run(wm, "f2")).apply = False
        _draw_report_detail(layout, wm, "f2")
        # Profile Render actually renders — too slow/disruptive for the Analyze
        # All sequencer (core.analyze_steps.STEPS deliberately excludes it);
        # manual only, no step status to show.
        _analyze_row(layout, wm, "", "assetdoctor.profile_render",
                     "Profile Render (Real RAM)", "RENDER_STILL", _profile_render_summary(wm))


class ASSETDOCTOR_PT_analyze_external(_SceneFeaturePanel, bpy.types.Panel):
    """Folder-wide link map (graphical) + reverse-dependency check both scan a
    FOLDER you pick, not the current file — different scope from "Analyze
    This File" above, so they live in their own section (user request,
    2026-06-25 item 2: split out of Analyze, titled "Analyze External
    Files"). Content unchanged from the old Analyze panel, just relocated."""

    bl_label = "Analyze External Files"
    bl_idname = "ASSETDOCTOR_PT_analyze_external"
    bl_order = 2

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager

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
    Geometry, Utilities) joined as native collapsible child panels in Batch 5
    (2026-06-23), and the N-panel itself was retired. The Resource Analyzer
    panel was folded into the Analyze panel's "Analyze Memory/Disk" row
    (its by-type breakdown rolled up directly below, like the Flatten
    Characters picker's rollup) and deleted as its own section."""

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
        # Reports" block — now its own ASSETDOCTOR_PT_results panel) is a real
        # bl_order'd child, so they all draw AFTER this, in order, every time —
        # user-reported regression (2026-06-25): the inline block used to render
        # here, ahead of every child panel including Current File Data/Analyze,
        # no matter what bl_order said, since bl_order only orders siblings
        # against each other, never against the parent's own draw() body.
        _draw_progress(layout, wm)

        if wm.assetdoctor_last_result:
            res = layout.row()
            if not wm.assetdoctor_last_result_ok:
                res.alert = True
            res.label(text=wm.assetdoctor_last_result,
                      icon="CHECKMARK" if wm.assetdoctor_last_result_ok else "ERROR")


def _draw_datablock_dups(layout, wm) -> None:
    """Batch C #3 — generic Duplicate Data-blocks: find .NNN families across
    Objects/Actions/Node Groups/etc. (Materials/Meshes/Images keep their own
    dedicated tools), group by KIND, pick a keeper per family, Merge Selected.
    Relocated directly under its Analyze button (user feedback, 2026-06-25:
    "fairly good, could go as-is under the button summary") — no longer drawn
    in the Results holding pen, and its own headline label is dropped since
    the Analyze row right above already shows it."""
    families = wm.assetdoctor_datablock_families
    scanned = wm.assetdoctor_datablock_scanned
    conflicts = wm.assetdoctor_datablock_conflicts

    box = layout.box().column(align=True)
    box.label(text="Objects, Actions, Node Groups, etc. — Materials/Meshes/Images "
              "have their own dedup tools.", icon="INFO")

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


def _res_variants_headline(wm) -> str:
    """Find Resolution Variants' own Analyze-row summary (item 11, 2026-06-25
    — replaces the generic tree disclosure now that this section has its own
    actionable checkbox+button UI, mirroring Find Duplicate Materials/
    Data-blocks)."""
    if not _feature_has_run(wm, "f6res"):
        return ""
    coll = wm.assetdoctor_res_variant_members
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
    is dropped — the Analyze row right above already shows it."""
    coll = wm.assetdoctor_res_variant_members
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
    box.label(text="Standardizing is LOSSY — the removed resolution's users "
              "switch to the kept one.", icon="INFO")
    brow = box.row(align=True)
    brow.operator("assetdoctor.res_variant_select", text="Select High Resolution").which = "HIGH"
    brow.operator("assetdoctor.res_variant_select", text="Select Low Resolution").which = "LOW"
    box.operator("assetdoctor.remove_excess_variants",
                 text="Remove Excess Variants (Backup)", icon="TRASH")

    expanded = set(filter(None, wm.assetdoctor_detail_expanded.split("\n")))
    for group_key in order:
        members = groups[group_key]
        ckey = f"resvar:{group_key}"
        is_exp = ckey in expanded
        kept = next((item.tag for _i, item in members if item.selected), "")
        crow = box.row(align=True)
        top = crow.operator("assetdoctor.toggle_inline_detail", text="",
                            icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False)
        top.key = ckey
        label = f"{group_key}  ({len(members)} resolutions)"
        if kept:
            label += f" — keeping {kept}"
        crow.label(text=label, icon="IMAGE_DATA")
        if not is_exp:
            continue
        for idx, item in members:
            frow = box.row(align=True)
            frow.separator(factor=2.0)
            sop = frow.operator("assetdoctor.res_variant_keep", text="",
                                icon="RADIOBUT_ON" if item.selected else "RADIOBUT_OFF",
                                emboss=False)
            sop.index = idx
            frow.label(text=f"{item.name}  [{item.tag}]")


def _material_dups_headline(wm) -> str:
    """The Find Duplicate Materials Analyze row's own summary (replaces the
    generic _report_feature_summary line — user feedback, 2026-06-25: the
    old report gave no way to act on what it found, this section does)."""
    if not wm.assetdoctor_mat_scanned:
        return ""
    groups = wm.assetdoctor_mat_families
    if not len(groups):
        return "✓ no duplicate materials found"
    removable = wm.assetdoctor_mat_removable
    linked = wm.assetdoctor_mat_linked
    bits = [f"{len(groups)} group(s)", f"{removable} material(s) remappable"]
    if linked:
        bits.append(f"{linked} linked (stay in library)")
    return ", ".join(bits)


def _draw_material_dups(layout, wm) -> None:
    """Reformatted Find Duplicate Materials — keeper-dropdown + Merge Selected,
    the same actionable shape as Duplicate Data-blocks/Textures (user
    feedback, 2026-06-25: "does not allow me to do anything with the
    information"). Flat list, no kind-grouping needed (every row is already
    one fingerprint-identical material group)."""
    groups = wm.assetdoctor_mat_families
    if not (wm.assetdoctor_mat_scanned and len(groups)):
        return
    box = layout.box().column(align=True)
    box.operator("assetdoctor.merge_material_selected",
                 text="Merge Selected (Backup)", icon="AREA_JOIN")
    for row in groups:
        frow = box.row(align=True)
        frow.prop(row, "selected", text="")
        label = row.name.split(" [", 1)[0]  # drop the "[library]" qualifier for display
        frow.label(text=f"{label}  (−{row.removable})", icon="MATERIAL")
        keep = frow.row()
        keep.alignment = "RIGHT"
        keep.label(text="keep", icon="PINNED")
        keep.prop(row, "keeper", text="")


class ASSETDOCTOR_PT_results(_SceneFeaturePanel, bpy.types.Panel):
    """Everything that used to draw inline in the parent panel's own body
    (Duplicate Data-blocks through the generic Reports selector) — moved here
    wholesale (v0.2.56, 2026-06-25 user report) so it actually renders BELOW
    Current File Data/Analyze/the legacy panels, instead of always ahead of
    them regardless of bl_order (see ASSETDOCTOR_PT_scene_deps.draw() for why).
    Placed last (highest bl_order) as a holding pen — NOT a Phase 3b/3c design;
    that 3-way split (Reporting & Recommendations / Cleanup & Fixes / Info &
    Utilities) still hasn't happened. Content/order inside is UNCHANGED from
    before the move."""

    bl_label = "Results"
    bl_idname = "ASSETDOCTOR_PT_results"
    bl_order = 8

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

        # Phase 3 path fixes are TWO independent jobs (user, 2026-06-21):
        #  (1) relink broken/missing library links — per-link + pick-a-file, so you
        #      can fix one specific link (e.g. a broken material library);
        #  (2) normalize the paths of libraries that already resolve.
        # Both Find triggers (Find Broken Library Links, the old Find Missing
        # Data-blocks — now folded into Find Reconnectable Data-blocks below)
        # moved to Analyze (Phase 3a); this box keeps the results list + Relink
        # Selected.
        links = layout.box().column(align=True)
        links.label(text="Broken Library Links & missing data-blocks", icon="LIBRARY_DATA_BROKEN")
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
        self._draw_duplicate_library_paths(context, norm, wm)
        self._draw_absolute_paths(context, norm, wm)

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
        scanned = wm.assetdoctor_tex_scanned
        narrow = bool(context.region) and context.region.width < 320

        tex = layout.box().column(align=True)
        # Header summary (the visible result — no separate report needed); the
        # Analyze panel's "Find Missing Textures" button shows the same line
        # inline (Phase 3c) via the same _missing_textures_headline helper.
        headline = _missing_textures_headline(wm, narrow)
        if headline:
            tex.label(text=headline, icon="IMAGE_DATA")
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

    def _draw_duplicate_library_paths(self, context, layout, wm):
        """Item 6, 2026-06-25: the duplicate-library-path groups Path
        normalization's "Check" finds — the SAME real file reached via 2+
        stored path forms (separate Library ID blocks in this file). Each
        form is its own radio-style checkbox row (only one enabled per
        group — Blender has no native radio-checkbox, so a toggle operator
        enforces it); a per-group "Use Selected Paths" button merges
        everything the OTHER form(s) provide onto the ticked one."""
        coll = wm.assetdoctor_dup_lib_members
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
        expanded = set(filter(None, wm.assetdoctor_detail_expanded.split("\n")))
        for group_key in order:
            members = groups[group_key]
            ckey = f"duplib:{group_key}"
            is_exp = ckey in expanded
            fname = os.path.basename(members[0][1].stored.rstrip("/\\")) or members[0][1].stored
            crow = layout.row(align=True)
            top = crow.operator("assetdoctor.toggle_inline_detail", text="",
                                icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False)
            top.key = ckey
            crow.label(text=f"{fname} — {len(members)} forms", icon="FILE_BLEND")
            mop = crow.operator("assetdoctor.merge_duplicate_libraries",
                                text="Use Selected Paths", icon="AREA_JOIN")
            mop.group = group_key
            if not is_exp:
                continue
            for idx, item in members:
                frow = layout.row(align=True)
                frow.separator(factor=2.0)
                sop = frow.operator("assetdoctor.dup_lib_select", text="",
                                    icon="RADIOBUT_ON" if item.selected else "RADIOBUT_OFF",
                                    emboss=False)
                sop.index = idx
                frow.label(text=item.stored, icon="FILE_BLEND" if item.selected else "NONE")

    def _draw_absolute_paths(self, context, layout, wm):
        """Item 7, 2026-06-25: absolute libraries grouped by drive. A
        same-drive group gets a free-multi-select checkbox per member (any
        subset can be converted) and ONE "Make Selected Relative" button on
        its own title line; a cross-drive group is shown read-only — there is
        no relative path between Windows drives, so nothing is selectable."""
        coll = wm.assetdoctor_abs_path_members
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
        expanded = set(filter(None, wm.assetdoctor_detail_expanded.split("\n")))
        for group_key in order:
            members = groups[group_key]
            fixable = members[0][1].target != ""
            ckey = f"abspath:{group_key}"
            is_exp = ckey in expanded
            crow = layout.row(align=True)
            top = crow.operator("assetdoctor.toggle_inline_detail", text="",
                                icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False)
            top.key = ckey
            label = f"{group_key} — {len(members)} librar{'y' if len(members) == 1 else 'ies'}"
            if fixable:
                crow.label(text=label, icon="CHECKMARK")
                crow.operator("assetdoctor.make_selected_relative",
                              text="Make Selected Relative", icon="FILE_REFRESH")
            else:
                crow.label(text=label + "  (different drive — can't be made relative)",
                          icon="ERROR")
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
        headline = _reconnect_headline(wm)
        if headline:
            box.label(text=headline, icon="LIBRARY_DATA_OVERRIDE")

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
            matched = sum(1 for m in members
                         if m.confidence not in ("none", "transitive", "external"))
            stuck = sum(1 for m in members if m.confidence == "transitive")
            external = sum(1 for m in members if m.confidence == "external")
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
            if external:
                bits.append(f"{external} fix at the source library")
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
        conflicts = wm.assetdoctor_dup_conflicts
        # Summary header (the visible result); the Analyze panel's "Find
        # Duplicate Content" button shows the same line inline (Phase 3c).
        headline = _duplicate_textures_headline(wm, narrow)
        if headline:
            dup.label(text=headline, icon="IMAGE_DATA")

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
