"""F7 Phase 4b — Phase A (multi-hop link chains, modal/offline via BAT), Phase
B (per-character flatten plan, plain/live bpy), and Phase 4's Apply step (the
actual flatten-and-reapply mutation). Phase A/B stay read-only — see
core/linkchain.py; the Apply mutation lives at the bottom of this file (it has
to call live bpy override-creation APIs, so it can't be pure/bpy-free like the
rest of this module's logic).

Phase A reuses the same recursive scan as Check Link Chain (Scan
Dependencies), then reads the CURRENT file's own local Object blocks a second
time (cheap — it's the root file, already on disk) to census which ones are
Library Overrides carrying an adjusted transform. Phase B picks up from
there, live in the open session: scan every such character into a picker
list, then build a focused, generic property-replay plan for ONE chosen
character at a time. Apply (report-first, like every other mutating feature
in this codebase) takes that same plan and, after a backup, actually links
the ultimate library directly, creates one new override hierarchy, replays
every recorded property onto it, and remaps the old multi-hop object's users
onto it — never force-removing the old linked copy (mirrors Examine
Library's user_remap pattern)."""

from __future__ import annotations

import json
import pathlib

import bpy

from ..core import blendscan, depscan, linkchain
from ..core.report import Report
from .progress import ModalProgressMixin
from .report_store import data_prop, resolve_datablock, stash_report


class ASSETDOCTOR_OT_scan_link_chains(ModalProgressMixin, bpy.types.Operator):
    bl_idname = "assetdoctor.scan_link_chains"
    bl_label = "Find Flattenable Link Chains"
    bl_description = (
        "Find libraries this file reaches via an intermediate hop (not just "
        "directly), and census Library Overrides with an adjusted transform "
        "in EVERY file the scan visits (not just this one) that could be "
        "flattened once their source chain is confirmed. Read-only — does "
        "not mutate anything; reopens each file a second time, so this is "
        "slower than Check Link Chain alone"
    )

    _PROGRESS_BUDGET = 0.0  # same reasoning as Check Link Chain: repaint every file

    def invoke(self, context, event):
        if not blendscan.bat_available():
            self.report({"ERROR"}, "Blender Asset Tracer unavailable — cannot scan offline")
            return {"CANCELLED"}
        start = bpy.data.filepath
        if not start or not pathlib.Path(start).is_file():
            self.report({"ERROR"}, "Save the file first — the scan reads it from disk")
            return {"CANCELLED"}
        return super().invoke(context, event)

    def run_steps(self, context):
        start = bpy.data.filepath
        result = depscan.new_dep_scan()

        # Census EVERY file visited during the scan, not just the root (fixed
        # 2026-06-25, real user report) — the actual flatten candidates can
        # live several hops deep (this project's own real files: the Stage
        # file holds zero local overrides; the character-roster file linked
        # several hops in holds hundreds). Reads links AND objects in the
        # SAME BAT open per file (perf fix, 2026-06-25 user feedback — used
        # to open every file a SECOND time just for this, roughly doubling
        # its share of the scan; now one open does both).
        posing: list[linkchain.ObjectPosingInfo] = []

        def scan_and_classify(path):
            refs, objects = linkchain.scan_links_and_objects(path)
            posing.extend(objects)
            return refs

        yield from depscan.scan_recursive_steps(
            result, [pathlib.Path(start)], scan_file=scan_and_classify
        )
        root = depscan._canon(start)

        report = linkchain.build_chain_report(result.graph, root, posing)
        stash_report(context, report, "f7chain")
        routes = sum(1 for f in report.findings if f.category == "multihop_route")
        flattenable = sum(1 for f in report.findings if f.category == "posing_override")
        yield 1.0, f"Done: {routes} multi-hop route(s), {flattenable} flattenable"
        self.report({"INFO"}, f"Link chain analysis: {routes} multi-hop route(s), "
                              f"{flattenable} flattenable override(s)")


# --- Phase B: flatten plan (live bpy read, still read-only) -----------------
#
# Design settled 2026-06-25 (docs/TODO.md "question 3"): read the override's
# properties via live bpy (id.override_library.properties + path_resolve)
# instead of a custom BAT DNA path-walker — the eventual mutating Apply step
# has to call real bpy override-creation APIs anyway, so there's no benefit
# to keeping this read offline-only. Split into a scan (every candidate, cheap,
# cached) + a per-character build (one chosen row) per the user's explicit
# request (2026-06-25) to act on a single character at a time, not the whole
# file in one pass — both operators only read/cache/show; neither applies
# anything.

def _coerce_override_value(value):
    """Reduce whatever ``ID.path_resolve()`` returns for one RNA path into a
    JSON-friendly shape for the report. ID/pointer properties (e.g. an
    Armature modifier's ``object``) resolve to another datablock — represent
    those as a "Type/Name" ref string (the same convention core.tree's
    click-to-select parser already understands) rather than trying to
    serialize a live bpy object. Vector/array properties (mathutils types,
    bpy_prop_array) are iterable — collapse to a plain tuple. Anything else
    that isn't already JSON-safe falls back to its string repr."""
    if isinstance(value, bpy.types.ID):
        return f"{type(value).__name__}/{value.name}"
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return tuple(value)
    except TypeError:
        return str(value)


def read_live_override_properties(obj) -> list[linkchain.OverrideProperty]:
    """Every (rna_path, current value) pair on a live Library Override
    object — the generic property-replay primitive Phase B is built around,
    covering bones/actions/drivers/parenting/materials/modifiers, not just
    the bare object transform Phase A already classifies on."""
    ov = getattr(obj, "override_library", None)
    if ov is None:
        return []
    out = []
    for prop in ov.properties:
        try:
            value = obj.path_resolve(prop.rna_path)
        except (ValueError, AttributeError):
            continue
        out.append(linkchain.OverrideProperty(
            rna_path=prop.rna_path, value=_coerce_override_value(value)))
    return out


def _resolve_rig(obj) -> str:
    """Walk from a posed part to the ARMATURE that drives it, so the picker
    can roll up body/eyes/clothes/etc. under one character (user feedback,
    2026-06-25: present everything in terms of the rig). Tries, in order: the
    object itself (it IS the rig), an Armature modifier's target, then the
    parent chain. "" when no rig can be found (a standalone prop override
    becomes its own one-member group, see the caller)."""
    if obj.type == "ARMATURE":
        return obj.name
    for mod in getattr(obj, "modifiers", ()):
        if mod.type == "ARMATURE" and mod.object is not None:
            return mod.object.name
    node = obj.parent
    seen = set()
    while node is not None and node.name not in seen:
        seen.add(node.name)
        if node.type == "ARMATURE":
            return node.name
        node = node.parent
    return ""


def _is_override_with_transform(obj) -> bool:
    """Live-bpy equivalent of core.linkchain.classify_posing's bucket check —
    this operator already has the object open, so there's no reason to
    re-read it from disk via BAT the way the offline census does."""
    if getattr(obj, "override_library", None) is None:
        return False
    return linkchain.transform_differs_from_identity(
        tuple(obj.location), tuple(obj.rotation_euler),
        tuple(obj.rotation_quaternion), tuple(obj.scale))


def _live_override_reference(obj) -> linkchain.OverrideReference | None:
    ref = obj.override_library.reference
    if ref is None:
        return None
    lib_path = ref.library.filepath if ref.library else ""
    return linkchain.OverrideReference(name=ref.name, kind=type(ref).__name__, library=lib_path)


class ASSETDOCTOR_OT_scan_flatten_candidates(bpy.types.Operator):
    """Find every override-with-transform character and cache a plan for each
    (cheap — no disk I/O, just RNA reads), so the user can pick ONE row in the
    list and build/show a focused plan for just that character — they
    explicitly don't want to be forced to act on every character in the file
    at once, now or once Apply exists."""

    bl_idname = "assetdoctor.scan_flatten_candidates"
    bl_label = "Find Flattenable Characters"
    bl_description = (
        "List every Library Override in this file with an adjusted transform "
        "so you can pick ONE to build a flatten plan for (run Find Flattenable "
        "Link Chains first). Read-only"
    )

    def execute(self, context):
        wm = context.window_manager
        raw = getattr(wm, data_prop("f7chain"), "")
        if not raw:
            self.report({"ERROR"}, "Run Find Flattenable Link Chains first")
            return {"CANCELLED"}
        routes = linkchain.routes_from_report(Report.from_json(raw))

        coll = wm.assetdoctor_flatten_candidates
        coll.clear()
        cached = {}
        for obj in bpy.data.objects:
            if not _is_override_with_transform(obj):
                continue
            properties = read_live_override_properties(obj)
            if not properties:
                # An override shell with nothing actually overridden (this
                # project's well-documented .NNN duplicate-override bloat) —
                # not flattenable, and showing it as a candidate just buried
                # the real characters (user feedback, 2026-06-25).
                continue
            reference = _live_override_reference(obj)
            plan = linkchain.build_flatten_plan(obj.name, reference, properties, routes)
            cached[obj.name] = linkchain.flatten_plan_to_dict(plan)

            row = coll.add()
            row.name = obj.name
            row.rig = _resolve_rig(obj) or obj.name
            row.ready = bool(plan.route and plan.properties)
            status = linkchain.summarize_properties(plan.properties)
            if plan.route:
                status += f" (via {len(plan.route) - 1} hop(s))"
            row.status = "; ".join(plan.warnings) if plan.warnings else status

        wm.assetdoctor_flatten_plans_json = json.dumps(cached)
        wm.assetdoctor_flatten_index = 0
        rigs = len({r.rig for r in coll})
        self.report({"INFO"}, f"Found {len(coll)} override part(s) across {rigs} rig(s)/character(s)")
        return {"FINISHED"}


# --- Phase 4 Apply: the actual flatten-and-reapply mutation ----------------
#
# Confirmed against Blender's official Python API docs before writing this
# (no synthetic override fixture exists to test against, the same caveat
# core/linkchain.py's module docstring already notes — see docs/TODO.md for
# the live-verify checklist): bpy.types.ID.override_create(remap_local_usages),
# bpy.types.ID.override_hierarchy_create(scene, view_layer, reference,
# do_fully_editable) -> new root override, bpy.types.IDOverrideLibrary.
# hierarchy_root (every override created by ONE hierarchy_create call shares
# this back-pointer to the root it returned), IDOverrideLibraryProperties.add
# (rna_path), and ID.user_remap(new_id).
#
# ONE hierarchy_create call per rig (not per member) — the API is explicitly
# designed to create overrides for a WHOLE linked hierarchy from a single root
# call; calling it once per member would each independently re-walk and
# duplicate the same hierarchy. Deliberately requires the rig/armature's OWN
# override to be one of the ready plans (the anchor hierarchy_create relinks
# from) — a rig whose children are individually overridden but whose armature
# itself isn't a flattenable override is NOT supported yet (same "stop and
# scope the next increment" pattern as the rest of this project's history;
# no real case has surfaced one yet to design against).

_KIND_TO_COLLECTION = {
    "Object": "objects", "Mesh": "meshes", "Material": "materials", "Image": "images",
    "Node Group": "node_groups", "Armature": "armatures", "Action": "actions",
    "Curve": "curves", "Collection": "collections", "Texture": "textures",
    "Light": "lights", "Camera": "cameras", "World": "worlds", "Scene": "scenes",
    "Shape Key": "shape_keys", "Particle": "particles",
}


def _resolve_library(path: str):
    """An already-loaded Library whose resolved filepath matches ``path``, if
    any — reused instead of creating a SECOND Library datablock for a path
    that's already loaded under a differently-spelled link (this project's
    own well-documented duplicate-library-block disease)."""
    try:
        target = pathlib.Path(bpy.path.abspath(path)).resolve()
    except OSError:
        return None
    for lib in bpy.data.libraries:
        try:
            if pathlib.Path(bpy.path.abspath(lib.filepath)).resolve() == target:
                return lib
        except OSError:
            continue
    return None


def _link_direct(library_path: str, kind: str, name: str):
    """Link ONE named datablock of ``kind`` directly from ``library_path``,
    reusing an already-loaded Library for the same resolved path if one
    exists. Returns the linked/found ID, or ``None`` if ``kind`` isn't a
    top-level bpy.data collection or the name isn't found there."""
    attr = _KIND_TO_COLLECTION.get(kind)
    if attr is None:
        return None
    existing = _resolve_library(library_path)
    if existing is not None:
        for item in getattr(bpy.data, attr):
            if item.library == existing and item.name == name:
                return item
    found = False
    with bpy.data.libraries.load(library_path, link=True) as (data_from, data_to):
        if name in getattr(data_from, attr):
            setattr(data_to, attr, [name])
            found = True
    if not found:
        return None
    linked = getattr(data_to, attr)
    return linked[0] if linked else None


def _set_override_value(root, rna_path: str, value) -> None:
    """Reverse ``_coerce_override_value``'s JSON-friendly encoding and write
    ``value`` onto ``root`` at ``rna_path``. Generic — splits the path into
    its container + final attribute and ``setattr``s; raises on anything it
    can't resolve (the caller counts that as one failed property, not a
    fatal error — the generic-replay design's accepted tradeoff: some
    property shapes may fail visibly rather than getting hand-coded)."""
    if isinstance(value, str) and "/" in value:
        kind, _, name = value.partition("/")
        resolved = resolve_datablock(kind, name)
        if resolved is not None:
            value = resolved
    elif isinstance(value, list):
        value = tuple(value)

    if "." not in rna_path:
        setattr(root, rna_path, value)
        return
    container_path, _, attr = rna_path.rpartition(".")
    container = root.path_resolve(container_path)
    setattr(container, attr, value)


def _flatten_rig(context, rig_plan, members: list) -> list:
    """Apply one rig/character's flatten plan for real. ``members`` is every
    READY plan in the group (``rig_plan`` included). Returns one
    :class:`core.linkchain.FlattenApplyResult` per member."""
    from ..log import get_logger

    log = get_logger()
    old_root = bpy.data.objects.get(rig_plan.object_name)
    if old_root is None or old_root.override_library is None:
        return [linkchain.FlattenApplyResult(
            p.object_name, False, "no longer a live override — re-run Find Flattenable Characters")
            for p in members]

    direct = _link_direct(rig_plan.ultimate_library, rig_plan.reference.kind, rig_plan.reference.name)
    if direct is None:
        msg = (f"'{rig_plan.reference.name}' not found directly in "
               f"{pathlib.Path(rig_plan.ultimate_library).name} — skipped")
        return [linkchain.FlattenApplyResult(p.object_name, False, msg) for p in members]

    try:
        new_root = direct.override_hierarchy_create(context.scene, context.view_layer, reference=old_root)
    except RuntimeError as exc:
        log.warning("F7 flatten apply: override_hierarchy_create failed for %s: %s",
                    rig_plan.object_name, exc)
        new_root = None
    if new_root is None:
        msg = "Blender declined to create the override hierarchy — see debug log"
        return [linkchain.FlattenApplyResult(p.object_name, False, msg) for p in members]

    # hierarchy_create only returns the ROOT — find every sibling override it
    # created alongside it (same hierarchy_root) so each member's OWN
    # properties land on its own counterpart, not all on the root.
    by_ref_name = {}
    for obj in bpy.data.objects:
        ov = getattr(obj, "override_library", None)
        if ov is None or (obj is not new_root and ov.hierarchy_root != new_root):
            continue
        if ov.reference is not None:
            by_ref_name[ov.reference.name] = obj

    results = []
    for plan in members:
        old_obj = bpy.data.objects.get(plan.object_name)
        new_obj = new_root if plan.object_name == rig_plan.object_name else (
            by_ref_name.get(plan.reference.name) if plan.reference else None)
        if old_obj is None or new_obj is None:
            results.append(linkchain.FlattenApplyResult(
                plan.object_name, False,
                "no matching part found in the new override hierarchy — skipped"))
            continue
        applied = failed = 0
        for prop in plan.properties:
            try:
                new_obj.override_library.properties.add(prop.rna_path)
                _set_override_value(new_obj, prop.rna_path, prop.value)
                applied += 1
            except Exception as exc:
                failed += 1
                log.warning("F7 flatten apply: %s on %s failed: %s",
                           prop.rna_path, plan.object_name, exc)
        old_obj.user_remap(new_obj)
        lib_name = pathlib.Path(rig_plan.ultimate_library).name
        msg = f"flattened via direct link to {lib_name} — {applied} propert{'y' if applied == 1 else 'ies'} replayed"
        if failed:
            msg += f", {failed} failed (see debug log)"
        results.append(linkchain.FlattenApplyResult(
            plan.object_name, True, msg, properties_applied=applied, properties_failed=failed))

    context.view_layer.update()
    return results


class ASSETDOCTOR_OT_build_flatten_plan(bpy.types.Operator):
    bl_idname = "assetdoctor.build_flatten_plan"
    bl_label = "Build Flatten Plan (preview)"

    # The rig/character group to build (matches ASSETDOCTOR_PG_flatten_candidate.rig);
    # "" = whichever row is active in the picker.
    name: bpy.props.StringProperty()  # type: ignore[valid-type]
    apply: bpy.props.BoolProperty(
        name="Apply",
        description="Actually flatten: link the ultimate library directly, create a new "
        "override hierarchy, replay every recorded property onto it, and remap the old "
        "multi-hop object's users onto it. Takes a backup first. Leave off for a "
        "report-only preview",
        default=False,
    )  # type: ignore[valid-type]

    @classmethod
    def description(cls, context, properties):
        if properties.apply:
            return ("Flatten this rig/character for real: link directly from the ultimate "
                    "library, create a new override hierarchy, replay every recorded "
                    "property, and remap users onto it. Takes a backup first")
        return ("Build the read-only flatten plan for every part of ONE rig/character "
                "(run Find Flattenable Characters first) — relink target + every "
                "overridden property each part would replay. Applies nothing")

    def execute(self, context):
        wm = context.window_manager
        target = self.name
        coll = wm.assetdoctor_flatten_candidates
        if not target:
            if not len(coll):
                self.report({"ERROR"}, "Run Find Flattenable Characters first")
                return {"CANCELLED"}
            target = coll[wm.assetdoctor_flatten_index].rig

        cached = json.loads(wm.assetdoctor_flatten_plans_json or "{}")
        members = [row.name for row in coll if row.rig == target]
        if not members and target in cached:
            members = [target]
        if not members:
            self.report({"ERROR"}, f"No cached plan(s) for '{target}' — re-run Find Flattenable Characters")
            return {"CANCELLED"}
        plans = [linkchain.flatten_plan_from_dict(cached[m]) for m in members if m in cached]

        if not self.apply:
            report = linkchain.build_flatten_plan_report(plans)
            stash_report(context, report, "f7flatten")
            ready = sum(1 for p in plans if p.route and p.properties)
            self.report({"INFO"}, f"Flatten plan for {target}: {ready}/{len(plans)} part(s) ready")
            return {"FINISHED"}

        ready = [p for p in plans if p.route and p.properties]
        blocked = [p for p in plans if not (p.route and p.properties)]
        results = [linkchain.FlattenApplyResult(
            p.object_name, False, "; ".join(p.warnings) or "not ready — skipped")
            for p in blocked]

        if ready:
            from .safety import auto_backup
            auto_backup(context)
            rig_plan = next((p for p in ready if p.object_name == target), None)
            if rig_plan is None:
                results.extend(linkchain.FlattenApplyResult(
                    p.object_name, False,
                    "the rig/armature's own override isn't a ready flatten candidate — "
                    "flattening individually-overridden parts without it isn't supported yet")
                    for p in ready)
            else:
                results.extend(_flatten_rig(context, rig_plan, ready))

        report = linkchain.build_flatten_apply_report(target, results)
        stash_report(context, report, "f7flatten")
        ok = sum(1 for r in results if r.ok)
        level = "INFO" if ok == len(results) else "WARNING"
        self.report({level}, f"Flattened {ok}/{len(results)} part(s) of {target}. Save to persist.")
        return {"FINISHED"}


class ASSETDOCTOR_OT_flatten_category_toggle(bpy.types.Operator):
    """Expand/collapse one rig/character group in the Find Flattenable
    Characters picker."""

    bl_idname = "assetdoctor.flatten_category_toggle"
    bl_label = "Expand/Collapse Rig Group"
    bl_options = {"INTERNAL"}

    key: bpy.props.StringProperty()  # type: ignore[valid-type]

    def execute(self, context):
        wm = context.window_manager
        keys = set(filter(None, wm.assetdoctor_flatten_expanded.split("\n")))
        keys.discard(self.key) if self.key in keys else keys.add(self.key)
        wm.assetdoctor_flatten_expanded = "\n".join(sorted(keys))
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}
