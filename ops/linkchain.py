"""F7 Phase 4b — Phase A (multi-hop link chains, modal/offline via BAT) and
Phase B (per-character flatten plan, plain/live bpy). Read-only throughout —
no mutation anywhere in this file, see core/linkchain.py.

Phase A reuses the same recursive scan as Check Link Chain (Scan
Dependencies), then reads the CURRENT file's own local Object blocks a second
time (cheap — it's the root file, already on disk) to census which ones are
Library Overrides carrying an adjusted transform. Phase B picks up from
there, live in the open session: scan every such character into a picker
list, then build a focused, generic property-replay plan for ONE chosen
character at a time."""

from __future__ import annotations

import json
import pathlib

import bpy

from ..core import blendscan, depscan, linkchain
from ..core.report import Report
from .progress import ModalProgressMixin
from .report_store import data_prop, stash_report


class ASSETDOCTOR_OT_scan_link_chains(ModalProgressMixin, bpy.types.Operator):
    bl_idname = "assetdoctor.scan_link_chains"
    bl_label = "Find Flattenable Link Chains"
    bl_description = (
        "Find libraries this file reaches via an intermediate hop (not just "
        "directly), and census local Library Overrides with an adjusted "
        "transform that could be flattened once their source chain is "
        "confirmed. Read-only — does not mutate anything"
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
        yield from depscan.scan_recursive_steps(
            result, [pathlib.Path(start)], scan_file=blendscan.scan_file
        )
        root = depscan._canon(start)
        yield 0.95, "Classifying local objects…"
        posing = linkchain.classify_objects(start)
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
            reference = _live_override_reference(obj)
            properties = read_live_override_properties(obj)
            plan = linkchain.build_flatten_plan(obj.name, reference, properties, routes)
            cached[obj.name] = linkchain.flatten_plan_to_dict(plan)

            row = coll.add()
            row.name = obj.name
            row.ready = bool(plan.route and plan.properties)
            row.status = "; ".join(plan.warnings) if plan.warnings else (
                f"{len(plan.properties)} propert{'y' if len(plan.properties) == 1 else 'ies'}"
                + (f", via {len(plan.route) - 1} hop(s)" if plan.route else ""))

        wm.assetdoctor_flatten_plans_json = json.dumps(cached)
        wm.assetdoctor_flatten_index = 0
        self.report({"INFO"}, f"Found {len(coll)} override character(s) with an adjusted transform")
        return {"FINISHED"}


class ASSETDOCTOR_OT_build_flatten_plan(bpy.types.Operator):
    bl_idname = "assetdoctor.build_flatten_plan"
    bl_label = "Build Flatten Plan (preview)"
    bl_description = (
        "Build the read-only flatten plan for ONE character (run Find "
        "Flattenable Characters first) — relink target + every overridden "
        "property it would replay. Applies nothing"
    )

    # Which cached candidate to build; "" = whichever row is active in the list.
    name: bpy.props.StringProperty()  # type: ignore[valid-type]

    def execute(self, context):
        wm = context.window_manager
        target = self.name
        coll = wm.assetdoctor_flatten_candidates
        if not target:
            if not len(coll):
                self.report({"ERROR"}, "Run Find Flattenable Characters first")
                return {"CANCELLED"}
            target = coll[wm.assetdoctor_flatten_index].name

        cached = json.loads(wm.assetdoctor_flatten_plans_json or "{}")
        if target not in cached:
            self.report({"ERROR"}, f"No cached plan for '{target}' — re-run Find Flattenable Characters")
            return {"CANCELLED"}
        plan = linkchain.flatten_plan_from_dict(cached[target])

        report = linkchain.build_flatten_plan_report([plan])
        stash_report(context, report, "f7flatten")
        verdict = "ready" if (plan.route and plan.properties) else "blocked — see warnings"
        self.report({"INFO"}, f"Flatten plan for {target}: {verdict}")
        return {"FINISHED"}
