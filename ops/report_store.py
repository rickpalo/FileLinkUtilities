"""Persistent per-feature report registry + the operators driving the report UI.

Each feature keeps its OWN report (JSON) + expanded-keys on the WindowManager, so
a Materials report survives a later Geometry scan; the Report panel has a selector
to switch between whichever reports exist. Plus operators for expand/collapse,
select-the-datablock (with the agreed non-intrusive behaviour), row labels (which
carry the full text as a tooltip), clear, and export.
"""

import json
import os

import bpy

from ..core.report import Report, default_export_filename
from ..core.tree import (
    all_keys,
    flatten_visible,
    nodes_from_json,
    nodes_to_json,
    report_to_tree,
    top_level_keys,
)
from .pickers import FilePickerMixin
from .progress import set_result

# (key, label) for each feature that produces a report. F5 resource is separate.
FEATURES = [
    ("f1", "Link Map"),
    ("f2", "Make Local"),
    ("f3", "Materials"),
    ("f4", "Orphans"),
    ("geo", "Geometry"),
    ("f7", "Dependencies"),
    ("f7chain", "Link Chain Analysis"),
    ("f7flatten", "Flatten Plan"),
    ("f7live", "Overrides"),
    ("f7rev", "Safe to Delete?"),
    ("f7links", "Broken Library Links"),
    ("f7fix", "Path Fixes"),
    ("f6tex", "Missing Textures"),
    ("f6dup", "Duplicate Textures"),
    ("f6res", "Resolution Variants"),
    ("f9", "Dry-Run Render Warnings"),
    ("matdiag", "Material Diagnostics"),
    ("matsearch", "Find Material Across Files"),
    ("deformcheck", "Armature Deformation Check"),
]


# Features whose stored JSON is a TreeNode list (not a flat Report). The F7
# dependency view needs arbitrary hierarchy (the file map), which Report can't hold.
TREE_FEATURES = {"f7"}

# Features with their OWN inline Analyze-button disclosure (ui.panels.
# _draw_report_detail), Group 12 Phase 4 — a fixed, small set (one per call
# site), each needing its OWN virtualized rows collection since several of
# these can be expanded SIMULTANEOUSLY in the same Analyze panel (unlike the
# Reports tab, which only ever shows one active feature at a time).
INLINE_DETAIL_FEATURES = ("f1", "f2", "f4", "f7", "f7chain", "f7flatten", "f7live", "f9", "matdiag",
                         "matsearch")


def data_prop(feature: str) -> str:
    return f"filelink_rep_{feature}"


def exp_prop(feature: str) -> str:
    return f"filelink_repx_{feature}"


def stash_report(context, report, feature: str, set_active: bool = True) -> None:
    """Persist a feature's report. Categories start COLLAPSED so a large report
    (hundreds of findings) doesn't draw as one giant column — the N-panel doesn't
    virtualize manual rows, which can leave rows blank. The user expands one
    category at a time.

    ``set_active=False`` for features (e.g. f6dup) whose report is only kept
    around for the inline Export button — the real UI for that feature lives
    elsewhere (the Duplicate Materials/Textures section), so stashing it must
    not steal the report selector away from whatever the user is looking at."""
    wm = context.window_manager
    setattr(wm, data_prop(feature), report.to_json())
    setattr(wm, exp_prop(feature), "")  # collapsed
    if set_active:
        wm.filelink_active_report = feature
    rebuild_report_rows(wm)


def stash_tree(context, nodes, feature: str) -> None:
    """Persist a feature whose data is a TreeNode tree (vs a flat Report). Opens
    the top-level sections (e.g. Summary / File map / Errors) by default."""
    wm = context.window_manager
    setattr(wm, data_prop(feature), nodes_to_json(nodes))
    setattr(wm, exp_prop(feature), "\n".join(top_level_keys(nodes)))
    wm.filelink_active_report = feature
    rebuild_report_rows(wm)


def available_features(wm):
    return [(k, label) for k, label in FEATURES if getattr(wm, data_prop(k))]


def active_feature(wm) -> str:
    a = wm.filelink_active_report
    if a and getattr(wm, data_prop(a), ""):
        return a
    avail = available_features(wm)
    return avail[0][0] if avail else ""


def get_expanded(wm, prop: str) -> set[str]:
    raw = getattr(wm, prop)
    return set(raw.split("\n")) if raw else set()


def set_expanded(wm, keys: set[str], prop: str) -> None:
    setattr(wm, prop, "\n".join(sorted(keys)))


# --- UIList materialisation -------------------------------------------------
# The Report/Resource panels draw a UIList over a CollectionProperty of rows
# (virtualized + scrollable, so large reports no longer blank out). The JSON on
# the WindowManager stays the source of truth; these helpers re-flatten it into
# the collection whenever the shown report or its expansion changes.

RESOURCE_EXP_PROP = "filelink_resource_expanded"


def _fill_rows(coll, rows, prop: str) -> None:
    coll.clear()
    for r in rows:
        item = coll.add()
        item.name = r.label  # so the UIList's built-in search box filters on it
        item.indent = r.indent
        item.key = r.key
        item.label = r.label
        item.severity = r.severity
        item.has_children = r.has_children
        item.expanded = r.expanded
        item.detail = r.detail
        item.icon = r.icon
        item.prop = prop
        item.ram = r.ram
        item.vram = r.vram
        item.disk = r.disk
        if r.ref:
            item.ref_type = r.ref.get("type", "")
            item.ref_name = r.ref.get("name", "")
        if r.popup:
            item.popup_parent = r.popup.get("parent", "")
            item.popup_basename = r.popup.get("basename", "")


def rebuild_report_rows(wm) -> None:
    """Refill ``filelink_report_rows`` from the active feature's report JSON."""
    coll = wm.filelink_report_rows
    active = active_feature(wm)
    if not active:
        coll.clear()
        return
    raw = getattr(wm, data_prop(active), "")
    try:
        if active in TREE_FEATURES:
            nodes = nodes_from_json(raw)
        else:
            nodes = report_to_tree(Report.from_json(raw))
    except Exception:
        coll.clear()
        return
    rows = flatten_visible(nodes, get_expanded(wm, exp_prop(active)))
    _fill_rows(coll, rows, exp_prop(active))


def inline_rows_prop(feature: str) -> str:
    return f"filelink_inline_rows_{feature}"


def inline_active_prop(feature: str) -> str:
    return f"filelink_inline_active_{feature}"


def rebuild_inline_detail_rows(wm, feature: str, nodes: list, expanded: set[str]) -> None:
    """Refill one feature's OWN inline-disclosure rows collection (Group 12
    Phase 4) — the per-feature analogue of ``rebuild_report_rows``, needed
    because several features' inline disclosures can be open simultaneously
    in the Analyze panel. ``nodes`` is already headline-filtered (the node
    ``ui.panels._report_headline`` says is quoted verbatim already removed)
    by the caller — this function has no UI-layer knowledge of headlines.
    Refilled on every ``_draw_report_detail`` call (cheap: the SAME
    nodes+flatten work the old manual loop already redid every draw; the win
    here is `template_list` only instantiating on-screen rows, not a
    fill-avoidance trick — see that function's docstring)."""
    coll = getattr(wm, inline_rows_prop(feature), None)
    if coll is None:
        return
    rows = flatten_visible(nodes, expanded)
    _fill_rows(coll, rows, "filelink_detail_expanded")


def rebuild_resource_rows(wm) -> None:
    """Refill ``filelink_resource_rows`` from the resource tree JSON."""
    coll = wm.filelink_resource_rows
    raw = getattr(wm, "filelink_resource_tree", "")
    if not raw:
        coll.clear()
        return
    try:
        nodes = nodes_from_json(raw)
    except Exception:
        coll.clear()
        return
    rows = flatten_visible(nodes, get_expanded(wm, RESOURCE_EXP_PROP))
    _fill_rows(coll, rows, RESOURCE_EXP_PROP)


def rebuild_rows_for_prop(wm, prop: str) -> None:
    """Rebuild whichever virtualized collection a toggle on ``prop`` affects.

    Only two ``prop`` families are backed by a virtualized ``CollectionProperty``
    today: ``RESOURCE_EXP_PROP`` and any feature's own ``exp_prop`` (always
    ``"filelink_repx_<feature>"``, see ``exp_prop()``) for the Reports tab.
    ``FILELINK_OT_row_toggle`` (docs/TODO.md Group 12) is now the ONE toggle
    operator for every grouped section in the addon, not just these two, so an
    unconditional "anything else must be a report feature" ``else`` would be
    wrong — it would silently rebuild the Reports tab's rows (wasted work, and
    liable to clobber the wrong report) every time an unrelated section (e.g.
    Missing Textures) toggles a group. No-op for any other ``prop`` — those
    sections still draw manually and have nothing to rebuild (yet; see Group
    12's phased rollout for sections gaining their own virtualized collection)."""
    if prop == RESOURCE_EXP_PROP:
        rebuild_resource_rows(wm)
    elif prop.startswith("filelink_repx_"):
        rebuild_report_rows(wm)
    elif prop in ("filelink_flatten_expanded", "filelink_flatten_deselected"):
        from .linkchain import rebuild_flatten_picker_rows  # lazy — avoids circular import
        rebuild_flatten_picker_rows(wm)
    elif prop == "filelink_tex_expanded":
        # Shared with Possible Matches/Linked-missing's namespaced ("\x01"/"\x03")
        # keys, which still draw manually — a rebuild here is harmless for those
        # (Missing Textures' own picker rows just don't contain that key).
        from .image_relink import rebuild_missing_tex_picker_rows  # lazy — avoids circular import
        rebuild_missing_tex_picker_rows(wm)
    elif prop == "filelink_dup_expanded":
        from .image_dedup import rebuild_dup_tex_picker_rows  # lazy — avoids circular import
        rebuild_dup_tex_picker_rows(wm)
    elif prop == "filelink_missing_expanded":
        from .datablock_reconnect import rebuild_reconnect_picker_rows  # lazy — avoids circular import
        rebuild_reconnect_picker_rows(wm)
    elif prop == "filelink_examine_expanded":
        from .examine_library import rebuild_examine_picker_rows  # lazy — avoids circular import
        rebuild_examine_picker_rows(wm)


def _index_prop_for(prop: str) -> str:
    return "filelink_resource_index" if prop == RESOURCE_EXP_PROP else "filelink_report_index"


def focus_row(wm, prop: str, key: str) -> None:
    """Point the list's active index at the row identified by ``key`` (after a
    rebuild) so Blender's ``template_list`` scrolls to keep it visible. Without
    this, expanding/collapsing a row deep in a long report re-filled the whole
    collection from scratch with no active-index change, so the list appeared to
    jump back to the top instead of staying where you clicked (user, 2026-06-23).
    No-op for a ``prop`` that isn't one of the two virtualized collections today
    (every other grouped section still draws manually) — same guard as
    ``rebuild_rows_for_prop``, see there for why a blanket "else" would be wrong
    now that one shared toggle op (below) serves every section."""
    if prop == RESOURCE_EXP_PROP or prop.startswith("filelink_repx_"):
        coll = wm.filelink_resource_rows if prop == RESOURCE_EXP_PROP else wm.filelink_report_rows
        for i, item in enumerate(coll):
            if item.key == key and item.prop == prop:
                setattr(wm, _index_prop_for(prop), i)
                return
    elif prop in ("filelink_flatten_expanded", "filelink_flatten_deselected"):
        for i, item in enumerate(wm.filelink_flatten_picker_rows):
            if item.key == key:
                wm.filelink_flatten_picker_active = i
                return
    elif prop == "filelink_tex_expanded":
        for i, item in enumerate(wm.filelink_missingtex_picker_rows):
            if item.key == key:
                wm.filelink_missingtex_picker_active = i
                return
    elif prop == "filelink_dup_expanded":
        for i, item in enumerate(wm.filelink_duptex_picker_rows):
            if item.key == key:
                wm.filelink_duptex_picker_active = i
                return
    elif prop == "filelink_missing_expanded":
        for i, item in enumerate(wm.filelink_reconnect_picker_rows):
            if item.key == key:
                wm.filelink_reconnect_picker_active = i
                return
    elif prop == "filelink_examine_expanded":
        for i, item in enumerate(wm.filelink_examine_picker_rows):
            if item.key == key:
                wm.filelink_examine_picker_active = i
                return
    elif prop == "filelink_detail_expanded":
        # Group 12 Phase 4's inline Analyze-button disclosures (docs/TODO.md
        # item 46c, 2026-07-04 live-verify: clicking a row deep in Check
        # Materials' list jumped back to the top) — omitted when Phase 4 added
        # this shared prop, same disease this function was originally written
        # to fix for the other collections above. A toggled node's OWN row
        # survives the toggle unchanged (only ITS CHILDREN appear/disappear),
        # so it's safe to search the not-yet-rebuilt collection here (the real
        # rebuild happens lazily on the next `_draw_report_detail` draw, per
        # that function's own docstring).
        feature = key.split(":", 1)[0]
        coll = getattr(wm, inline_rows_prop(feature), None)
        if coll is None:
            return
        for i, item in enumerate(coll):
            if item.key == key:
                setattr(wm, inline_active_prop(feature), i)
                return


class FILELINK_OT_row_toggle(bpy.types.Operator):
    """The one generic expand/collapse (and, via a differently-named ``prop``,
    select/deselect — see ``ops.linkchain``'s Flatten-candidate groups) toggle
    for every grouped results section in the addon (docs/TODO.md Group 12,
    2026-06-27). Replaces 8 near-identical operator classes that each
    hand-rolled the same "toggle ``key`` in/out of a newline-joined WM
    string-set named ``prop``" logic — one per section, plus this one's own
    two predecessors (``report_toggle``/``toggle_inline_detail``).

    ``prop`` defaults to ``filelink_detail_expanded``, the one shared
    bucket used by every inline Analyze-button disclosure (a node's own key
    already embeds its report's feature tag, so two features' keys never
    collide there); every other section passes its own dedicated ``prop``
    explicitly. ``rebuild_rows_for_prop``/``focus_row`` are no-ops for any
    ``prop`` that isn't (yet) backed by a virtualized row collection — see
    those functions — so this is a pure behavior-preserving merge for the
    ~11 sections still drawn manually; only the Reports tab/Resource Usage
    case (the two ``prop`` families ``report_toggle`` used to serve) gets the
    rebuild+refocus treatment today. Redraws BOTH the area and its region
    (``FILELINK_OT_flatten_category_toggle`` added the region redraw
    2026-06-27 as a defensive fix for a reported "drill-down arrows stop
    responding" issue; adopted here for every section, not just Flatten's)."""

    bl_idname = "filelink.row_toggle"
    bl_label = "Expand/Collapse"
    # Explicit and short (docs/TODO.md item 46k, 2026-07-04 live-verify) — an
    # operator with no `bl_description` falls back to its class docstring as
    # the tooltip, and that docstring is implementation detail for developers
    # reading this file, not a useful hover hint for the user clicking a
    # triangle.
    bl_description = "Expand or collapse this row"
    bl_options = {"INTERNAL"}

    key: bpy.props.StringProperty()  # type: ignore[valid-type]
    prop: bpy.props.StringProperty(default="filelink_detail_expanded")  # type: ignore[valid-type]

    def execute(self, context):
        wm = context.window_manager
        keys = get_expanded(wm, self.prop)
        keys.discard(self.key) if self.key in keys else keys.add(self.key)
        set_expanded(wm, keys, self.prop)
        rebuild_rows_for_prop(wm, self.prop)
        focus_row(wm, self.prop, self.key)
        if context.area:
            context.area.tag_redraw()
        if context.region:
            context.region.tag_redraw()
        return {"FINISHED"}


class FILELINK_OT_row_label(bpy.types.Operator):
    """A tree row's label as a button: its tooltip is the full text (so long
    paths/messages are readable in the narrow panel), and clicking it does the
    row's natural action (expand/collapse a parent, or select a leaf's datablock)."""

    bl_idname = "filelink.row_label"
    bl_label = "Row"
    bl_options = {"INTERNAL"}

    text: bpy.props.StringProperty()  # full text -> shown as tooltip
    key: bpy.props.StringProperty()
    prop: bpy.props.StringProperty()
    has_children: bpy.props.BoolProperty()
    ref_type: bpy.props.StringProperty()
    ref_name: bpy.props.StringProperty()
    popup_parent: bpy.props.StringProperty()
    popup_basename: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        return properties.text or "—"

    def execute(self, context):
        if self.has_children and self.prop:
            wm = context.window_manager
            keys = get_expanded(wm, self.prop)
            keys.discard(self.key) if self.key in keys else keys.add(self.key)
            set_expanded(wm, keys, self.prop)
            rebuild_rows_for_prop(wm, self.prop)
            focus_row(wm, self.prop, self.key)
            if context.area:
                context.area.tag_redraw()
        elif self.popup_parent:
            bpy.ops.filelink.show_linked_from(
                "INVOKE_DEFAULT", parent=self.popup_parent, basename=self.popup_basename)
        elif self.ref_type:
            bpy.ops.filelink.select_datablock(type=self.ref_type, name=self.ref_name)
        return {"FINISHED"}


def _reveal_in_outliner(context, filter_name: str = "") -> None:
    """Best-effort: frame + expand the active object's hierarchy in an open
    Outliner, the same as typing its name there. ``outliner.show_active`` needs
    an Outliner area/region in the override context, which this panel's own
    Properties-editor context doesn't have — find one if the user has it open.

    ``outliner.show_active`` only ever reveals the ACTIVE OBJECT — Blender has
    no public API to scroll-to/highlight an arbitrary non-object ID (a
    Material, an Image) directly, in ANY display mode, including Blend File /
    Orphan Data (user-confirmed 2026-06-24: setting the active material slot
    alone did not focus the material there). ``filter_name``, when given, is
    set as the Outliner's own name filter (``SpaceOutliner.filter_text`` — the
    same search box the header's magnifying-glass icon opens) on every open
    Outliner, narrowing its rows to matches regardless of display mode. This
    DOES mutate persistent Outliner UI state (the filter stays set until
    cleared/replaced) — the deliberate, only-available alternative once
    ``show_active`` alone is confirmed insufficient for a non-object target."""
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "OUTLINER":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region is None:
                continue
            try:
                with context.temp_override(window=window, area=area, region=region):
                    bpy.ops.outliner.show_active()
            except Exception:
                pass
            if filter_name:
                try:
                    area.spaces[0].filter_text = filter_name
                except Exception:
                    pass
            return


def resolve_datablock(type_name: str, name: str):
    """Find the ID datablock matching a "Type/Name" ref (generic walk over every
    ``bpy.data`` collection) — shared by click-to-select here and Phase 4's
    flatten-apply (resolving an overridden pointer property's coerced
    "Type/Name" string back to a real datablock)."""
    for prop in bpy.data.bl_rna.properties:
        if prop.type != "COLLECTION":
            continue
        coll = getattr(bpy.data, prop.identifier, None)
        if coll is None:
            continue
        try:
            cand = coll.get(name)
        except (TypeError, AttributeError):
            continue
        if cand is not None and type(cand).__name__ == type_name:
            return cand
    return None


# Click-to-select outcome -> icon, for a STICKY per-row indicator (docs/TODO.md
# Group 10 #37, 2026-07-04) instead of relying solely on a one-shot status
# message that's easy to miss or misattribute once you've scrolled past it.
SELECT_OUTCOME_ICON = {
    "found": "CHECKMARK",
    "no_user": "QUESTION",
    "unresolved": "ERROR",
}


def _load_select_outcomes(wm) -> dict:
    raw = wm.filelink_select_outcomes
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _save_select_outcome(wm, type_: str, name: str, outcome: str) -> None:
    outcomes = _load_select_outcomes(wm)
    outcomes[f"{type_}/{name}"] = outcome
    wm.filelink_select_outcomes = json.dumps(outcomes)


def get_select_outcome(wm, type_: str, name: str) -> str:
    """Persistent last-known click-to-select outcome for one datablock —
    ``"found"``/``"no_user"``/``"unresolved"``, or ``""`` if it's never been
    clicked. Rows draw ``SELECT_OUTCOME_ICON[outcome]`` next to themselves
    when this is non-empty."""
    return _load_select_outcomes(wm).get(f"{type_}/{name}", "")


class FILELINK_OT_select_datablock(bpy.types.Operator):
    bl_idname = "filelink.select_datablock"
    bl_label = "Select"
    bl_description = "Select the object(s) this finding refers to (the Outliner follows the active object)"
    bl_options = {"INTERNAL"}

    type: bpy.props.StringProperty()  # type: ignore[valid-type]
    name: bpy.props.StringProperty()  # type: ignore[valid-type]

    def execute(self, context):
        wm = context.window_manager
        if self._resolve_target() is None:
            # The datablock itself couldn't be found at all (renamed/removed
            # since this report was generated) — distinct from "found, but no
            # live user" below (docs/TODO.md Group 10 #37's "unresolved" case).
            msg = (f"{self.type}/{self.name}: could not resolve this datablock — it "
                   "may have been renamed or removed since this report was generated")
            _save_select_outcome(wm, self.type, self.name, "unresolved")
            self.report({"WARNING"}, msg)
            set_result(context, msg, ok=False)
            if context.area:
                context.area.tag_redraw()
            return {"CANCELLED"}

        targets, materials = self._find_objects(context)
        if not targets:
            # Non-intrusive: don't open/rearrange editors; hint where to look.
            # STICKY (not just a self.report() toast, user feedback 2026-06-25
            # item e) — a transient toast is easy to miss and reads as "the
            # click did nothing" even though this IS the real answer (most
            # duplicate-family members are exactly this: dead weight with no
            # real user). Also covers the case where a real user exists but
            # its collection is excluded from the current view layer, which
            # "has no users in the scene" technically doesn't distinguish.
            # 2026-07-04: ALSO now recorded per-row (`_save_select_outcome`)
            # so the row itself keeps showing this outcome after you've
            # scrolled past the message, not just this one-shot toast.
            # Reworded (docs/TODO.md item 46l, 2026-07-04 live-verify: "is the
            # object not found in this view layer, or is the object itself
            # not found?") — this branch only runs once `_resolve_target()`
            # already succeeded above, so the datablock ITSELF definitely
            # still exists; make that explicit instead of leading with "no
            # user found," which reads the same as the unresolved case above.
            msg = (f"{self.type}/{self.name}: exists, but has no object instance in "
                   "the current view layer (it may be unused, or its collection is "
                   "excluded from this view layer) — check Outliner → Display Mode → "
                   "Blender File / Orphan Data")
            _save_select_outcome(wm, self.type, self.name, "no_user")
            self.report({"INFO"}, msg)
            set_result(context, msg, ok=False)
            if context.area:
                context.area.tag_redraw()
            return {"CANCELLED"}

        _save_select_outcome(wm, self.type, self.name, "found")
        for obj in context.view_layer.objects:
            obj.select_set(False)
        for obj in targets:
            obj.select_set(True)
        context.view_layer.objects.active = targets[0]

        # Highlight the connecting Material's slot on the active object — covers
        # both a direct Material click AND something deeper (e.g. an Image two
        # hops below the Material it's used in, user report 2026-06-24: clicking a
        # missing texture didn't highlight "the material from whence it came").
        # CONFIRMED (live test, 2026-06-24) that alone doesn't focus the material
        # in the Outliner — show_active is active-OBJECT-only — so for anything
        # that isn't a direct Object click, ALSO narrow the Outliner via its own
        # name filter (the connecting material's name, else the clicked target's
        # own name) so it's findable regardless of display mode.
        filter_name = ""
        if self.type != "Object":
            for i, slot in enumerate(targets[0].material_slots):
                if slot.material in materials:
                    targets[0].active_material_index = i
                    filter_name = slot.material.name
                    break
            if not filter_name:
                filter_name = self.name

        _reveal_in_outliner(context, filter_name)
        tail = f" — Outliner filtered to '{filter_name}'" if filter_name else ""
        self.report({"INFO"}, f"Selected {len(targets)} object(s) using {self.name}{tail}")
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}

    def _resolve_target(self):
        """Find the ID datablock matching this finding's type-name + name."""
        return resolve_datablock(self.type, self.name)

    def _find_objects(self, context):
        """Scene objects that use the datablock, directly or transitively, plus any
        Material(s) found ALONG THE WAY (so a Material slot can be highlighted on
        the resulting active object even when the click started from something
        deeper than a Material — e.g. an Image used by a Material used by an
        Object: ``(objects, materials)``.

        ``bpy.data.user_map()`` maps each id -> the set of ids that USE it, so we
        walk it forward from the target up to the using objects."""
        scene_objs = set(context.view_layer.objects)
        target = self._resolve_target()
        if target is None:
            return [], set()
        if isinstance(target, bpy.types.Object):
            return ([target] if target in scene_objs else []), set()
        materials = {target} if isinstance(target, bpy.types.Material) else set()

        user_map = bpy.data.user_map()
        found, seen, stack = [], set(), [target]
        while stack:
            cur = stack.pop()
            for user in user_map.get(cur, ()):
                if user in seen:
                    continue
                seen.add(user)
                if isinstance(user, bpy.types.Material):
                    materials.add(user)
                if isinstance(user, bpy.types.Object):
                    if user in scene_objs and user not in found:
                        found.append(user)
                else:
                    stack.append(user)
        return found, materials


class FILELINK_OT_show_linked_from(bpy.types.Operator):
    """"Show what's linked from here" for an INDIRECT File Map row (item 2,
    2026-06-26): the row's file was never directly linked into the open file
    (only a library-of-a-library), so it has no real ``bpy.data.libraries``
    entry for ``select_datablock`` to find. Reads the PARENT file offline
    instead (the already-built ``core.datablock_links.datablocks_from_library``)
    and lists exactly what it pulls from this row's file, in a transient popup
    -- each entry reuses ``select_datablock`` so a name that DOES happen to
    also be loaded locally is still clickable."""

    bl_idname = "filelink.show_linked_from"
    bl_label = "Show What's Linked From Here"
    bl_description = (
        "This library was never linked directly into the open file (only "
        "through another library), so it has no entry to select. Read the "
        "linking file and list what it actually pulls from here"
    )
    bl_options = {"INTERNAL"}

    parent: bpy.props.StringProperty()  # type: ignore[valid-type]
    basename: bpy.props.StringProperty()  # type: ignore[valid-type]

    def invoke(self, context, event):
        from ..core.datablock_links import datablocks_from_library

        # This is a real, BLOCKING disk read of the parent .blend (BAT block-
        # table scan) — up to ~1 min/file on this project's large production
        # files (see project memory) — with no other progress indication, so
        # a slow read was indistinguishable from "the click did nothing"
        # (docs/TODO.md Group 10 #39). A wait cursor is an OS-level cursor
        # swap, not dependent on a redraw, so it shows immediately even
        # though this whole call happens inside one blocking Python frame.
        context.window.cursor_modal_set("WAIT")
        try:
            self._items = datablocks_from_library(self.parent, self.basename)
        except Exception as exc:
            self.report({"ERROR"}, f"Could not read {os.path.basename(self.parent)}: {exc}")
            return {"CANCELLED"}
        finally:
            context.window.cursor_modal_restore()
        title = f"Linked from {self.basename} (via {os.path.basename(self.parent)})"
        context.window_manager.popup_menu(self._draw, title=title)
        return {"FINISHED"}

    def _draw(self, menu_self, context):
        from ..core.datablock_links import kind_ref

        layout = menu_self.layout
        if not self._items:
            layout.label(text="Nothing found")
            return
        for kind, name in self._items:
            ref = kind_ref(kind, name)
            op = layout.operator("filelink.select_datablock", text=f"{kind}: {name}")
            op.type, op.name = ref["type"], ref["name"]


def _tree_to_text(nodes, title: str) -> str:
    """Fully-expanded indented text dump of a tree (for export/print)."""
    lines = [title, "=" * len(title), ""]
    for r in flatten_visible(nodes, all_keys(nodes)):
        prefix = "  " * r.indent
        detail = f"   [{r.detail}]" if r.detail else ""
        lines.append(f"{prefix}{r.label}{detail}")
    return "\n".join(lines) + "\n"


class FILELINK_OT_export_report(FilePickerMixin, bpy.types.Operator):
    bl_idname = "filelink.export_report"
    bl_label = "Export Report"
    bl_description = "Save the report to a text file (for printing or sharing)"

    source: bpy.props.EnumProperty(
        items=[("report", "Report", ""), ("resource", "Resource", "")],
        default="report",
    )  # type: ignore[valid-type]
    # Optional: export THIS feature's report instead of the active one (so an inline
    # section Export button targets its own report regardless of the selector).
    feature: bpy.props.StringProperty(default="")  # type: ignore[valid-type]
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore[valid-type]

    def invoke(self, context, event):
        wm = context.window_manager
        if self.source == "resource":
            label = "Resource Usage"
        else:
            feature = self.feature or active_feature(wm)
            label = dict(FEATURES).get(feature, feature)
        self.filepath = default_export_filename(label)
        return super().invoke(context, event)

    def execute(self, context):
        wm = context.window_manager
        if self.source == "resource":
            raw = wm.filelink_resource_tree
            if not raw:
                self.report({"ERROR"}, "No resource analysis to export")
                return {"CANCELLED"}
            text = _tree_to_text(nodes_from_json(raw), "File & Link Utilities — Resource Usage (estimate)")
        else:
            feature = self.feature or active_feature(wm)
            raw = getattr(wm, data_prop(feature), "") if feature else ""
            if not raw:
                self.report({"ERROR"}, "No report to export")
                return {"CANCELLED"}
            if feature in TREE_FEATURES:
                text = _tree_to_text(nodes_from_json(raw), f"File & Link Utilities — {feature}")
            elif self.filepath.lower().endswith(".csv"):
                text = Report.from_json(raw).to_csv()
            else:
                report = Report.from_json(raw)
                text = _tree_to_text(report_to_tree(report), report.title)

        try:
            with open(bpy.path.abspath(self.filepath), "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            self.report({"ERROR"}, f"Could not write file: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported report to {self.filepath}")
        return {"FINISHED"}
