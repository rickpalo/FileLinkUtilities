"""F7 Phase 4b / Phase A — multi-hop link-chain detection + per-object posing-
mechanism classification (read-only, no mutation).

Answers, for one already-scanned file: "which libraries does this file reach
via an intermediate hop (not just directly), and which locally-overridden
objects even have a transform worth preserving if that chain were collapsed."
Phase B (the actual flatten-and-reapply action) is a separate, later, mutating
step — this module only classifies.

Two independent layers, deliberately split so the decision logic is testable
without bpy/BAT:

1. Pure graph query over an existing :class:`core.depscan.DepGraph` —
   ``find_chains``/``multihop_routes``. No I/O.
2. Per-object posing-mechanism read (BAT, on-demand) + classify (pure).
   ``read_object_posing`` does the DNA read; ``classify_posing`` is the pure
   decision function, unit-tested directly with crafted
   :class:`ObjectPosingInfo` values (no override fixture exists yet to test
   the read side end-to-end — see the module docstring note below).

Override-reference attribution (closed 2026-06-25 via a real-file probe, see
docs/TODO.md): ``ov_block.get_pointer((b"reference",))`` resolves to the
overridden datablock as a generic ``ID`` placeholder — the EXACT same shape
:mod:`core.datablock_links` already reads for plain links (bare ``name`` +
``lib`` pointer, no embedded ``id`` prefix). This must be TWO separate
single-hop ``get_pointer`` calls (first resolve ``id.override_library``, THEN
call ``get_pointer`` again on that result for ``reference``) — chaining both
hops into one 3-element path silently returns the WRONG block (confirmed by
probing real production files: a 3-tuple path returned another
``IDOverrideLibrary`` struct with an empty name, not the actual reference;
BAT's ``get_pointer`` only dereferences the FINAL hop of a path, treating
earlier hops as plain embedded-struct offsets — fine for ``(id,
override_library)`` since ``id`` is embedded, not fine for a THIRD hop that
needs ANOTHER dereference). Confirmed against real overrides in
``ThePiazzaSanMarco - People1_v5.1.blend`` (not a synthetic fixture — no
override fixture exists for pytest, same caveat as the rest of this module).
"""

from __future__ import annotations

import pathlib
from dataclasses import asdict, dataclass

from .depscan import DepGraph
from .report import Finding, Report

OVERRIDE_WITH_TRANSFORM = "override_with_transform"
MODIFIER_DRIVEN = "modifier_driven"
UNCLASSIFIED = "unclassified"

_IDENTITY_LOC = (0.0, 0.0, 0.0)
_IDENTITY_ROT = (0.0, 0.0, 0.0)
_IDENTITY_QUAT = (1.0, 0.0, 0.0, 0.0)
_IDENTITY_SIZE = (1.0, 1.0, 1.0)
_EPS = 1e-6


# --- 1. pure graph chain-finder ---------------------------------------------

def find_chains(graph: DepGraph, source: str, target: str, max_depth: int = 12) -> list[list[str]]:
    """Every simple path ``source -> ... -> target`` (cycle-safe: a path never
    revisits a node, so it terminates even if ``graph`` has cycles elsewhere).
    Each path is a list of node keys including both endpoints, so a direct
    link is ``[source, target]`` (length 2) and a 2-hop chain is length 3."""
    paths: list[list[str]] = []

    def walk(node: str, path: list[str], visited: set[str]) -> None:
        if node == target and len(path) > 1:
            paths.append(list(path))
            return
        if len(path) - 1 >= max_depth:
            return
        for nxt in sorted(graph.targets_of(node)):
            if nxt in visited:
                continue
            walk(nxt, path + [nxt], visited | {nxt})

    walk(source, [source], {source})
    return paths


def multihop_routes(graph: DepGraph, source: str, max_depth: int = 12) -> dict[str, list[list[str]]]:
    """``{target: [paths]}`` for every file reachable from ``source`` that has
    at least one path of 2+ hops (a genuine multi-hop route — the precondition
    for "could this be flattened"). When a target is ALSO reachable directly,
    that direct path is kept alongside the longer one(s), so the caller can
    see the redundancy (the real motivating case: PSM_Stage links human_bundle
    both directly AND via People1)."""
    out: dict[str, list[list[str]]] = {}
    for target in graph.nodes:
        if target == source:
            continue
        paths = find_chains(graph, source, target, max_depth)
        if any(len(p) >= 3 for p in paths):
            out[target] = paths
    return out


# --- 2a. posing read (BAT) ---------------------------------------------------

@dataclass(frozen=True)
class OverrideReference:
    """What a Library Override overrides: the linked datablock it references,
    and that datablock's own source library (the chain-attribution target)."""

    name: str
    kind: str
    library: str  # stored path of the reference's library, "" if unresolved


# DNA ID-block 2-char name prefix -> friendly kind (mirrors core.datablock_links).
_PREFIX_KINDS = {
    "OB": "Object", "ME": "Mesh", "MA": "Material", "IM": "Image",
    "NT": "Node Group", "AR": "Armature", "AC": "Action", "CU": "Curve",
    "GR": "Collection", "TE": "Texture", "LA": "Light", "CA": "Camera",
    "WO": "World", "SC": "Scene", "KE": "Shape Key", "PA": "Particle",
}


def read_override_reference(ov_block) -> OverrideReference | None:
    """Given an already-resolved ``IDOverrideLibrary`` block (from
    ``id_block.get_pointer((b"id", b"override_library"))``), read what it
    overrides. TWO separate single-hop derefs — see module docstring for why
    chaining this into the caller's path tuple silently returns garbage."""
    ref = ov_block.get_pointer((b"reference",), default=None)
    if ref is None:
        return None
    raw_name = ref.get((b"name",), as_str=True, default="")
    kind = _PREFIX_KINDS.get(raw_name[:2], raw_name[:2] or "?")
    name = raw_name[2:] if raw_name else ""
    lib_path = ""
    try:
        lib_block = ref.get_pointer((b"lib",), default=None)
        if lib_block is not None:
            lib_path = lib_block.get((b"name",), as_str=True, default="")
    except Exception:
        pass
    return OverrideReference(name=name, kind=kind, library=lib_path)


@dataclass(frozen=True)
class ObjectPosingInfo:
    """Raw, unjudged signals read off one local Object block."""

    name: str
    has_override: bool = False
    has_modifier: bool = False
    loc: tuple[float, ...] | None = None
    rot: tuple[float, ...] | None = None
    quat: tuple[float, ...] | None = None
    size: tuple[float, ...] | None = None
    reference: OverrideReference | None = None


def read_object_posing(block) -> ObjectPosingInfo:
    """Read posing signals off one already-open Object (``OB``) BAT block.

    DNA paths confirmed against real production files (2026-06-24 + 2026-06-25
    sessions, see docs/TODO.md): ``(b"id", b"override_library")`` (a Library
    Override's data lives under the embedded ``id`` sub-struct, NOT directly
    on ``Object``) and ``(b"modifiers", b"first")`` (presence-only — this
    deliberately does NOT identify the modifier TYPE, just whether one
    exists, since Phase A only needs to bucket "has some modifier-driven
    motion" vs not)."""
    raw_name = block.get((b"id", b"name"), as_str=True, default="")
    name = raw_name[2:] if raw_name else ""
    ov_block = block.get_pointer((b"id", b"override_library"), default=None)
    has_override = ov_block is not None
    reference = read_override_reference(ov_block) if ov_block is not None else None
    has_modifier = block.get_pointer((b"modifiers", b"first"), default=None) is not None
    loc = tuple(block.get((b"loc",), default=[0.0, 0.0, 0.0]))
    rot = tuple(block.get((b"rot",), default=[0.0, 0.0, 0.0]))
    quat = tuple(block.get((b"quat",), default=[1.0, 0.0, 0.0, 0.0]))
    size = tuple(block.get((b"size",), default=[1.0, 1.0, 1.0]))
    return ObjectPosingInfo(name=name, has_override=has_override, has_modifier=has_modifier,
                            loc=loc, rot=rot, quat=quat, size=size, reference=reference)


def classify_objects(blend_path) -> list[ObjectPosingInfo]:
    """Read + return posing info for every LOCAL Object in ``blend_path``
    (on-demand, one whole-file BAT read — same cost profile as
    :func:`core.datablock_links.linked_datablocks`; call on the one file
    already on disk that the user is checking, not across a whole scan)."""
    from blender_asset_tracer import blendfile

    out: list[ObjectPosingInfo] = []
    bfile = blendfile.BlendFile(pathlib.Path(blend_path))
    try:
        for block in bfile.find_blocks_from_code(b"OB"):
            out.append(read_object_posing(block))
    finally:
        bfile.close()
    return out


# --- 2b. posing classify (pure) ---------------------------------------------

def _differs(v: tuple[float, ...] | None, identity: tuple[float, ...]) -> bool:
    return v is not None and any(abs(a - b) > _EPS for a, b in zip(v, identity))


def _has_adjusted_transform(info: ObjectPosingInfo) -> bool:
    return transform_differs_from_identity(info.loc, info.rot, info.quat, info.size)


def transform_differs_from_identity(
    loc: tuple[float, ...] | None,
    rot: tuple[float, ...] | None,
    quat: tuple[float, ...] | None,
    size: tuple[float, ...] | None,
) -> bool:
    """Public wrapper around the same epsilon-based identity check
    ``classify_posing`` uses internally. Reused by ``ops/linkchain.py``'s
    live-bpy equivalent check (Phase B) so both the offline-BAT census and the
    live-session read agree on what counts as "adjusted"."""
    return (_differs(loc, _IDENTITY_LOC) or _differs(rot, _IDENTITY_ROT)
            or _differs(quat, _IDENTITY_QUAT) or _differs(size, _IDENTITY_SIZE))


def classify_posing(info: ObjectPosingInfo) -> str:
    """Bucket one object's posing mechanism. An override that carries no
    transform adjustment (still at identity loc/rot/quat/size) is deliberately
    NOT ``override_with_transform`` — there's nothing to reapply, so it's left
    ``unclassified`` (a candidate for a plain relink, not a flatten-and-
    reapply). Override takes precedence over a coexisting modifier: an
    override IS the mechanically-tractable case Phase B targets, regardless of
    whether the object also happens to carry an unrelated modifier."""
    if info.has_override and _has_adjusted_transform(info):
        return OVERRIDE_WITH_TRANSFORM
    if info.has_modifier and not info.has_override:
        return MODIFIER_DRIVEN
    return UNCLASSIFIED


# --- report -------------------------------------------------------------------

def _name(path: str) -> str:
    import ntpath
    return ntpath.basename(path) or path


def _display_name(path: str) -> str:
    """Filename of a Blender-stored path (``//``-relative or absolute) without
    ntpath's misreading of the ``//`` prefix as a UNC root — see
    core.datablock_links for the same caveat. Used wherever a path comes from
    a BAT-read DNA field rather than a plain filesystem path (those go
    through ``_name`` instead)."""
    return path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def _basename(path: str) -> str:
    return _display_name(path).lower()


def build_chain_report(graph: DepGraph, root: str, posing: list[ObjectPosingInfo]) -> Report:
    """Combine the multi-hop routes from ``root`` with a posing-mechanism
    census of ``root``'s own local objects into one Phase-4-A report. The two
    findings are NOT yet cross-referenced (see module docstring) — this is a
    "here's what exists" census, not yet "here's exactly what to flatten"."""
    report = Report(title=f"Link Chain Analysis: {_name(root)}", feature="f7chain")

    routes = multihop_routes(graph, root)
    by_mechanism = {OVERRIDE_WITH_TRANSFORM: 0, MODIFIER_DRIVEN: 0, UNCLASSIFIED: 0}
    classified = [(info, classify_posing(info)) for info in posing]
    for _info, mech in classified:
        by_mechanism[mech] += 1

    report.add(Finding(
        category="overview",
        message=(f"{len(routes)} multi-hop route(s) · "
                  f"{by_mechanism[OVERRIDE_WITH_TRANSFORM]} flattenable (override+transform) · "
                  f"{by_mechanism[MODIFIER_DRIVEN]} modifier-driven (not flattenable yet) · "
                  f"{by_mechanism[UNCLASSIFIED]} other local object(s)"),
        severity="info",
    ))

    for target, paths in sorted(routes.items()):
        longest = max(paths, key=len)
        chain_str = " -> ".join(_name(n) for n in longest)
        has_direct = any(len(p) == 2 for p in paths)
        msg = f"{_name(root)} reaches {_name(target)} via {len(longest) - 1} hops: {chain_str}"
        if has_direct:
            msg += " (also linked directly)"
        report.add(Finding(category="multihop_route", message=msg,
                           severity="warning", items=[root, target],
                           data={"paths": paths}))

    route_basenames = {_basename(target): target for target in routes}
    for info, mech in classified:
        if mech == OVERRIDE_WITH_TRANSFORM:
            msg = (f"Object/{info.name} is a Library Override with an adjusted transform "
                   "— a flatten candidate")
            ref = info.reference
            if ref and ref.library:
                ref_base = _basename(ref.library)
                msg += f", overrides {ref.kind}/{ref.name} from {_display_name(ref.library)}"
                if ref_base in route_basenames:
                    target = route_basenames[ref_base]
                    longest = max(routes[target], key=len)
                    msg += f" (reached via {len(longest) - 1} hops — see Multi-hop link chains)"
                else:
                    msg += " (linked directly, no multi-hop chain to flatten)"
            else:
                msg += " — its source chain could not be determined"
            report.add(Finding(
                category="posing_override", message=msg, severity="info",
                items=[f"Object/{info.name}"]))
        elif mech == MODIFIER_DRIVEN:
            report.add(Finding(
                category="posing_modifier",
                message=f"Object/{info.name} is posed via a modifier, not an override "
                         "— not flattenable by the override mechanism (Phase C, deferred)",
                severity="info", items=[f"Object/{info.name}"]))

    if not routes and by_mechanism[OVERRIDE_WITH_TRANSFORM] == 0:
        report.add(Finding(category="clean",
                           message="No multi-hop link chains or flattenable overrides found",
                           severity="info"))

    return report


# --- Phase B: flatten plan (read-only — no mutation, no Apply step yet) -----
#
# Design settled 2026-06-25 (see docs/TODO.md, "question 3"): the SOURCE
# override's properties are read via LIVE bpy (``id.override_library.
# properties`` + ``id.path_resolve(rna_path)``), not a from-scratch BAT DNA
# path-walker — Phase B's eventual mutating Apply step has to call real bpy
# override-creation APIs anyway, so there is no offline-only path to keep
# pure here. ``ops/linkchain.py`` does the live read and hands this module
# plain (rna_path, value) pairs; everything below stays bpy-free and tested
# with crafted inputs, same split as the rest of this file.

@dataclass(frozen=True)
class OverrideProperty:
    """One RNA path + its current live value, read off a Library Override.
    ``value`` is already coerced to a JSON-friendly shape (str/int/float/bool/
    tuple) by the bpy-side reader — this module never touches bpy/mathutils
    types directly."""

    rna_path: str
    value: object


@dataclass(frozen=True)
class FlattenPlan:
    """Read-only recipe for flattening one ``override_with_transform``
    character: link directly from ``ultimate_library`` instead of through
    ``route``, then replay every entry in ``properties`` onto the new
    override. Nothing here mutates anything; a later Apply step (not built
    yet — needs this plan reviewed/live-tested first, per the plan's own
    phased-caution rule) would be the thing that actually consumes it."""

    object_name: str
    reference: OverrideReference | None
    ultimate_library: str | None  # the library path to link directly from
    route: list[str] | None  # the multi-hop chain it currently routes through, if any
    properties: list[OverrideProperty]
    warnings: list[str]


def build_flatten_plan(
    object_name: str,
    reference: OverrideReference | None,
    properties: list[OverrideProperty],
    routes: dict[str, list[list[str]]],
) -> FlattenPlan:
    """Pure: cross-reference one character's override reference + its live
    property list against the multi-hop ``routes`` already found for this
    file (the same dict :func:`build_chain_report` consumes, reconstructable
    from a stashed f7chain report via :func:`routes_from_report`)."""
    warnings: list[str] = []
    route: list[str] | None = None
    ultimate_library: str | None = None

    if reference is None or not reference.library:
        warnings.append("override's source chain could not be determined")
    else:
        ref_base = _basename(reference.library)
        route_basenames = {_basename(target): target for target in routes}
        if ref_base in route_basenames:
            target = route_basenames[ref_base]
            route = max(routes[target], key=len)
            ultimate_library = target
        else:
            ultimate_library = reference.library
            warnings.append("linked directly, no multi-hop chain to flatten — nothing to collapse")

    if not properties:
        warnings.append("no override properties found to replay")

    return FlattenPlan(object_name=object_name, reference=reference,
                       ultimate_library=ultimate_library, route=route,
                       properties=list(properties), warnings=warnings)


def flatten_plan_to_dict(plan: FlattenPlan) -> dict:
    """JSON-friendly round-trip of a :class:`FlattenPlan` — the scan step
    (``ops.linkchain.scan_flatten_candidates``) computes every candidate's
    plan up front (cheap — no disk I/O) and caches it this way, so picking ONE
    character later doesn't require recomputing or re-reading anything."""
    return {
        "object_name": plan.object_name,
        "reference": asdict(plan.reference) if plan.reference else None,
        "ultimate_library": plan.ultimate_library,
        "route": plan.route,
        "properties": [asdict(p) for p in plan.properties],
        "warnings": list(plan.warnings),
    }


def flatten_plan_from_dict(d: dict) -> FlattenPlan:
    reference = OverrideReference(**d["reference"]) if d.get("reference") else None
    properties = [OverrideProperty(**p) for p in d.get("properties", [])]
    return FlattenPlan(object_name=d["object_name"], reference=reference,
                       ultimate_library=d.get("ultimate_library"), route=d.get("route"),
                       properties=properties, warnings=list(d.get("warnings", [])))


def routes_from_report(report: Report) -> dict[str, list[list[str]]]:
    """Reconstruct the ``routes`` dict :func:`build_flatten_plan` needs from
    an already-built f7chain :class:`Report` (its ``multihop_route`` findings
    carry ``items=[root, target]`` + ``data={"paths": paths}``) — reused
    instead of re-running the slow offline multi-file scan a second time."""
    routes: dict[str, list[list[str]]] = {}
    for finding in report.findings:
        if finding.category != "multihop_route" or len(finding.items) < 2:
            continue
        target = finding.items[1]
        paths = finding.data.get("paths") or []
        routes.setdefault(target, []).extend(paths)
    return routes


def build_flatten_plan_report(plans: list[FlattenPlan]) -> Report:
    """Render a list of :class:`FlattenPlan` into the user-visible preview
    report (feature ``f7flatten``) — "here's what I'd do," still nothing
    applied."""
    report = Report(title="Flatten Plan (preview — applies nothing)", feature="f7flatten")
    actionable = [p for p in plans if p.route and p.properties]

    if plans:
        report.add(Finding(
            category="overview",
            message=(f"{len(actionable)} of {len(plans)} override character(s) ready to "
                      f"flatten ({len(plans) - len(actionable)} blocked — see warnings)"),
            severity="info",
        ))

    for plan in plans:
        lib_name = _display_name(plan.ultimate_library) if plan.ultimate_library else "?"
        msg = f"Object/{plan.object_name}: relink directly from {lib_name}"
        if plan.route:
            chain_str = " -> ".join(_name(n) for n in plan.route)
            msg += f" (currently routed via {chain_str})"
        n = len(plan.properties)
        msg += f", replay {n} overridden propert{'y' if n == 1 else 'ies'}"
        report.add(Finding(
            category="flatten_plan", message=msg,
            severity="warning" if plan.warnings else "info",
            items=[f"Object/{plan.object_name}"],
            data={"ultimate_library": plan.ultimate_library,
                  "properties": [{"rna_path": p.rna_path, "value": p.value} for p in plan.properties]},
            detail=str(n)))
        for warning in plan.warnings:
            report.add(Finding(
                category="flatten_warning",
                message=f"Object/{plan.object_name}: {warning}",
                severity="warning", items=[f"Object/{plan.object_name}"]))

    if not plans:
        report.add(Finding(
            category="clean",
            message=("No override_with_transform characters found in this file — run "
                      "Find Flattenable Link Chains first if you expected some"),
            severity="info"))

    return report


__all__ = [
    "OVERRIDE_WITH_TRANSFORM", "MODIFIER_DRIVEN", "UNCLASSIFIED",
    "ObjectPosingInfo", "OverrideReference", "OverrideProperty", "FlattenPlan",
    "find_chains", "multihop_routes", "read_object_posing", "read_override_reference",
    "classify_objects", "classify_posing", "transform_differs_from_identity",
    "build_chain_report", "build_flatten_plan", "routes_from_report", "build_flatten_plan_report",
    "flatten_plan_to_dict", "flatten_plan_from_dict",
]
