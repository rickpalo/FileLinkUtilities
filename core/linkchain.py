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

from . import blendscan
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
    """Raw, unjudged signals read off one local Object block.

    ``source_file`` (added when the census was extended to every file in a
    multi-hop chain, not just the root — see ``classify_objects``) names which
    .blend this object is LOCAL to. Defaults to "" for any pre-existing caller
    that only ever read one already-known file and didn't need to say so."""

    name: str
    has_override: bool = False
    has_modifier: bool = False
    loc: tuple[float, ...] | None = None
    rot: tuple[float, ...] | None = None
    quat: tuple[float, ...] | None = None
    size: tuple[float, ...] | None = None
    reference: OverrideReference | None = None
    source_file: str = ""


def read_object_posing(block, source_file: str = "") -> ObjectPosingInfo:
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
                            loc=loc, rot=rot, quat=quat, size=size, reference=reference,
                            source_file=source_file)


def classify_objects(blend_path) -> list[ObjectPosingInfo]:
    """Read + return posing info for every LOCAL Object in ``blend_path``
    (on-demand, one whole-file BAT read — same cost profile as
    :func:`core.datablock_links.linked_datablocks`). Each result's
    ``source_file`` is stamped with ``blend_path`` so a caller censusing
    several files (see ``ops.linkchain``'s chain-wide census) can tell them
    apart."""
    from blender_asset_tracer import blendfile

    out: list[ObjectPosingInfo] = []
    bfile = blendfile.BlendFile(pathlib.Path(blend_path))
    try:
        for block in bfile.find_blocks_from_code(b"OB"):
            out.append(read_object_posing(block, source_file=str(blend_path)))
    finally:
        bfile.close()
    return out


def scan_links_and_objects(
    blend_path,
) -> tuple[list[blendscan.LinkRef], list[ObjectPosingInfo]]:
    """``blendscan.scan_file`` (LI blocks) + :func:`classify_objects` (OB
    blocks), but sharing ONE ``BlendFile`` open instead of two (perf fix,
    2026-06-25 user feedback: Find Flattenable Link Chains used to open every
    file in the chain TWICE, paying BAT's block-table-index cost — the
    dominant per-file cost on a multi-GB file, see docs/TODO.md — once for
    each pass, for no reason once both reads land in the same function). An
    object-read failure is swallowed (posing info for that file is just
    empty) rather than propagated, matching the old call site's behaviour —
    a file with flaky OB blocks but readable LI blocks should still let the
    chain walk continue through it; a link-read failure still propagates,
    same as plain ``scan_file``, so depscan's own per-file error handling is
    unchanged."""
    from blender_asset_tracer import blendfile

    path = pathlib.Path(blend_path)
    bfile = blendfile.BlendFile(path)
    try:
        refs: list[blendscan.LinkRef] = []
        for block in bfile.find_blocks_from_code(b"LI"):
            stored = block.get(b"name", as_str=True, default="")
            if not stored:
                continue
            resolved, is_rel = blendscan.resolve_blend_relative(stored, path)
            refs.append(blendscan.LinkRef(
                stored_path=stored, resolved_path=resolved, is_relative=is_rel,
                exists=pathlib.Path(resolved).is_file() if resolved else False))
        try:
            objects = [read_object_posing(block, source_file=str(blend_path))
                       for block in bfile.find_blocks_from_code(b"OB")]
        except Exception:
            objects = []
        return refs, objects
    finally:
        bfile.close()


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

def _strip_blend_ext(name: str) -> str:
    """Drop a trailing ``.blend`` (user feedback, 2026-06-25 item 5b: "leave
    the file extension off all the reports... it can be assumed" — every
    file this report names is a .blend, so the extension carries no
    information, only width)."""
    return name[:-6] if name.lower().endswith(".blend") else name


def _name(path: str) -> str:
    import ntpath
    return _strip_blend_ext(ntpath.basename(path) or path)


def _display_name(path: str) -> str:
    """Filename of a Blender-stored path (``//``-relative or absolute) without
    ntpath's misreading of the ``//`` prefix as a UNC root — see
    core.datablock_links for the same caveat. Used wherever a path comes from
    a BAT-read DNA field rather than a plain filesystem path (those go
    through ``_name`` instead)."""
    return _strip_blend_ext(path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1])


def _basename(path: str) -> str:
    return _display_name(path).lower()


def build_chain_report(graph: DepGraph, root: str, posing: list[ObjectPosingInfo]) -> Report:
    """Combine the multi-hop routes from ``root`` with a posing-mechanism
    census into one Phase-4-A report. ``posing`` may span EVERY file visited
    during the chain scan, not just ``root`` (2026-06-25 fix — the real
    characters live several hops deep, e.g. in ``People1.blend``, not in a
    Stage file that itself holds zero overrides; censusing only ``root`` found
    nothing to test). Each ``ObjectPosingInfo.source_file`` (when set) is
    named in its Finding so it's clear which file an object lives in when
    several files are mixed together."""
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
        # 2026-06-27 (docs/TODO.md Group 11 #47, standing summary-propagation
        # rule): the structured total, so the UI can turn the static
        # "{N} flattenable" into a LIVE "{remaining} of {N} flattenable"
        # after Flatten Selected runs, without re-parsing the message text.
        data={"flattenable_total": by_mechanism[OVERRIDE_WITH_TRANSFORM]},
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
        file_tag = f" (in {_display_name(info.source_file)})" if info.source_file else ""
        if mech == OVERRIDE_WITH_TRANSFORM:
            msg = (f"Object/{info.name}{file_tag} is a Library Override with an adjusted "
                   "transform — a flatten candidate")
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
                items=[f"Object/{info.name}"], data={"source_file": info.source_file}))
        elif mech == MODIFIER_DRIVEN:
            report.add(Finding(
                category="posing_modifier",
                message=f"Object/{info.name}{file_tag} is posed via a modifier, not an "
                         "override — not flattenable by the override mechanism (Phase C, "
                         "deferred)",
                severity="info", items=[f"Object/{info.name}"],
                data={"source_file": info.source_file}))

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


def drop_local_posing_findings(report: Report, current_file: str) -> Report:
    """A copy of ``report`` with ``posing_override``/``posing_modifier`` findings
    for objects LOCAL to ``current_file`` removed; findings for objects in
    OTHER files (reached several hops deep) are kept as-is.

    2026-06-26 (docs/TODO.md #41 follow-up): the live picker
    (``ops.linkchain.scan_flatten_candidates`` / ``ui.panels._draw_flatten_
    candidates``) already shows every LOCAL override-with-transform object
    grouped by character, so repeating them in this report's flat per-object
    list is pure duplication -- the UI hides those rows. But an object
    several hops deep, in a file the live picker can never see (it only
    reads ``bpy.data.objects`` of whichever file is currently open), has NO
    other home -- hiding those too left a real visibility gap (929+
    flattenable objects with nothing to inspect beyond a bare list of
    filenames from :func:`remote_posing_files`). Keeping remote findings here
    closes that gap without reintroducing the duplication for local ones."""
    current = _basename(current_file) if current_file else ""

    def _is_local(f: Finding) -> bool:
        if f.category not in ("posing_override", "posing_modifier"):
            return False
        src = f.data.get("source_file", "")
        return bool(src) and _basename(src) == current

    kept = [f for f in report.findings if not _is_local(f)]
    return Report(title=report.title, feature=report.feature, findings=kept,
                  category_details=dict(report.category_details))


def remote_posing_files(report: Report, current_file: str) -> list[str]:
    """Distinct file(s), other than ``current_file``, where ``build_chain_report``
    already found an ``override_with_transform`` character.

    Phase B's live picker (``ops.linkchain.scan_flatten_candidates``) can only
    see overrides local to whichever .blend is open right now — a multi-hop
    character several files deep (e.g. People1.blend, several hops below a
    Stage file that holds zero local overrides) is invisible to it even
    though Phase A's offline census (this report) already found it. Used to
    turn a misleading "nothing found" into "found, but open THIS file"."""
    current = _basename(current_file) if current_file else ""
    files: set[str] = set()
    for f in report.findings:
        if f.category != "posing_override":
            continue
        src = f.data.get("source_file", "")
        if src and _basename(src) != current:
            files.add(_display_name(src))
    return sorted(files)


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
        msg += f" — {summarize_properties(plan.properties)}"
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


# --- Phase 4 Apply (mutating — the real flatten/reapply step) ---------------
#
# Pure result type + report renderer only; the actual mutation (link direct,
# bpy.types.ID.override_hierarchy_create, IDOverrideLibraryProperties.add +
# value replay, ID.user_remap) has to call live bpy and lives in
# ops/linkchain.py, same split as the rest of this module.

@dataclass(frozen=True)
class FlattenApplyResult:
    """One member object's outcome after an Apply attempt."""

    object_name: str
    ok: bool
    message: str
    properties_applied: int = 0
    properties_failed: int = 0


def build_flatten_apply_report(rig: str, results: list[FlattenApplyResult]) -> Report:
    """Render Apply's outcome into the same ``f7flatten`` report slot the
    preview uses (report-first/apply-after pattern every other Apply feature
    in this codebase follows) — "here's what I actually did."""
    report = Report(title=f"Flatten Apply: {rig}", feature="f7flatten")
    ok = sum(1 for r in results if r.ok)

    if results:
        report.add(Finding(
            category="overview",
            message=f"{ok} of {len(results)} part(s) flattened for {rig}. Save to persist.",
            severity="info" if ok == len(results) else "warning",
        ))

    for r in results:
        msg = f"Object/{r.object_name}: {r.message}"
        report.add(Finding(
            category="flatten_applied" if r.ok else "flatten_warning",
            message=msg, severity="info" if r.ok else "warning",
            items=[f"Object/{r.object_name}"]))

    if not results:
        report.add(Finding(category="clean", message=f"Nothing to flatten for {rig}",
                           severity="info"))

    return report


# --- property rollup (2026-06-25 user feedback) -----------------------------
#
# A raw "replay N overridden properties" count wasn't useful for deciding
# whether flattening a character is worth it — the user wants to know WHAT
# kind of overrides are involved (posed bones, an assigned action, a
# reparent, ...). Pure/bpy-free so it's testable with crafted properties,
# same split as the rest of this module.

def _pose_bone_name(rna_path: str) -> str | None:
    """``pose.bones["Name"].location`` -> ``Name``; ``None`` for anything else."""
    if not rna_path.startswith("pose.bones["):
        return None
    end = rna_path.find("]", 11)
    if end == -1:
        return None
    return rna_path[12:end].strip("\"'")


def summarize_properties(properties: list[OverrideProperty]) -> str:
    """One human-readable line rolling up what a flatten plan would actually
    replay, grouped by what the override affects rather than a bare count."""
    bones: set[str] = set()
    has_action = False
    transform_n = 0
    material_n = 0
    modifier_n = 0
    parent_n = 0
    other_n = 0
    for p in properties:
        path = p.rna_path
        bone = _pose_bone_name(path)
        if bone is not None:
            bones.add(bone)
        elif path.startswith("animation_data."):
            has_action = True
        elif path in ("location", "rotation_euler", "rotation_quaternion", "scale"):
            transform_n += 1
        elif path.startswith("material_slots[") or path == "active_material":
            material_n += 1
        elif path.startswith("modifiers["):
            modifier_n += 1
        elif path == "parent":
            parent_n += 1
        else:
            other_n += 1

    bits = []
    if bones:
        bits.append(f"{len(bones)} bone(s) posed")
    if has_action:
        bits.append("animation override")
    if transform_n:
        bits.append(f"{transform_n} transform adjustment(s)")
    if material_n:
        bits.append(f"{material_n} material override(s)")
    if modifier_n:
        bits.append(f"{modifier_n} modifier override(s)")
    if parent_n:
        bits.append("reparented")
    if other_n:
        bits.append(f"{other_n} other propert{'y' if other_n == 1 else 'ies'}")
    return " · ".join(bits) if bits else "no override properties found to replay"


def build_rig_rollup(plans: list[FlattenPlan]) -> str:
    """Combine every member object's properties under one rig/character into
    a single rolled-up line (the picker shows this directly below the rig's
    row — no separate report tab needed to judge whether flattening it is
    worth it)."""
    if not plans:
        return "no data"
    all_props = [p for plan in plans for p in plan.properties]
    ready = sum(1 for p in plans if p.route and p.properties)
    return f"{ready}/{len(plans)} part(s) ready — {summarize_properties(all_props)}"


__all__ = [
    "OVERRIDE_WITH_TRANSFORM", "MODIFIER_DRIVEN", "UNCLASSIFIED",
    "ObjectPosingInfo", "OverrideReference", "OverrideProperty", "FlattenPlan",
    "find_chains", "multihop_routes", "read_object_posing", "read_override_reference",
    "classify_objects", "classify_posing", "transform_differs_from_identity",
    "build_chain_report", "build_flatten_plan", "routes_from_report", "remote_posing_files",
    "drop_local_posing_findings", "build_flatten_plan_report",
    "flatten_plan_to_dict", "flatten_plan_from_dict", "summarize_properties", "build_rig_rollup",
    "FlattenApplyResult", "build_flatten_apply_report",
]
