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
import os
import pathlib
import subprocess
import tempfile
import time

import bpy

from ..core import blendscan, collection_mirror, depscan, linkchain, remote_harvest
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
        "slower than Check Link Chain alone. Usually run via 'Find "
        "Flattenable Links', which also groups the result by character"
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


def _display_file_name(path: str) -> str:
    """Filename without extension, robust to Blender's "//"-relative prefix
    (ntpath/pathlib can misread it as a UNC root) -- same caveat as
    core.linkchain._display_name/core.datablock_links, duplicated here since
    those are private to their own modules."""
    name = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return name[:-6] if name.lower().endswith(".blend") else name


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
        "so you can pick ONE to build a flatten plan for (needs Find "
        "Flattenable Link Chains' data already stashed — usually run "
        "together via 'Find Flattenable Links'). Read-only"
    )

    def execute(self, context):
        wm = context.window_manager
        raw = getattr(wm, data_prop("f7chain"), "")
        if not raw:
            self.report({"ERROR"}, "Run Find Flattenable Link Chains first")
            return {"CANCELLED"}
        chain_report = Report.from_json(raw)
        routes = linkchain.routes_from_report(chain_report)

        coll = wm.assetdoctor_flatten_candidates
        coll.clear()
        cached = {}
        local_names: set[str] = set()
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

            resolved_rig = _resolve_rig(obj)
            row = coll.add()
            row.name = obj.name
            # 2026-06-27 (docs/TODO.md Group 11 #47): a standalone override
            # (no rig found) groups by object TYPE instead of becoming its
            # own 1-member group named after itself.
            row.rig = resolved_rig or f"{obj.type.title()} (standalone)"
            row.is_rig = bool(resolved_rig)
            row.is_remote = False
            row.ready = bool(plan.route and plan.properties)
            status = linkchain.summarize_properties(plan.properties)
            if plan.route:
                status += f" (via {len(plan.route) - 1} hop(s))"
            row.status = "; ".join(plan.warnings) if plan.warnings else status
            local_names.add(obj.name)

        wm.assetdoctor_flatten_plans_json = json.dumps(cached)
        wm.assetdoctor_flatten_index = 0

        # 2026-06-27 (docs/TODO.md Group 11 #47): the picker now ALSO surfaces
        # REMOTE candidates (an override several hops deep, in a file this
        # session never opened) instead of only ever showing local ones —
        # the real motivating case (PSM_Stage_v5.1: 929 flattenable, 0 local)
        # had nothing actionable here before this. `drop_local_posing_
        # findings` already isolates exactly the remote half of the census;
        # `ready`/`status` are placeholders until Flatten Selected actually
        # harvests each one (core.remote_harvest), since that requires
        # opening the donor file in a subprocess, too slow to do here just to
        # populate a list.
        remote_report = linkchain.drop_local_posing_findings(chain_report, bpy.data.filepath)
        remote_count = 0
        for f in remote_report.findings:
            if f.category != "posing_override" or not f.items:
                continue
            name = f.items[0].split("/", 1)[-1]
            if name in local_names:
                continue
            source_file = f.data.get("source_file", "")
            row = coll.add()
            row.name = name
            row.rig = f"Remote: {_display_file_name(source_file)}" if source_file else "Remote: unknown file"
            row.is_rig = False
            row.is_remote = True
            row.source_file = source_file
            row.ready = False
            row.status = "remote — not yet checked (run Flatten Selected to find out)"
            local_names.add(name)
            remote_count += 1

        # This picker used to see ONLY overrides LOCAL to the currently open
        # file — a character several hops deep (e.g. People1.blend, linked
        # under a Stage file that itself holds zero local overrides) was
        # invisible to it even though Find Flattenable Link Chains already
        # found it. Remote rows above close that gap directly now; this note
        # stays as a fallback for the (now rarer) case where there's truly
        # NOTHING in the census at all to show, local or remote.
        remote_files = [] if len(coll) else linkchain.remote_posing_files(chain_report, bpy.data.filepath)
        wm.assetdoctor_flatten_remote_note = (
            f"Found in {', '.join(remote_files)} but nothing could be listed — "
            "re-run Find Flattenable Links") if remote_files else ""

        if not len(coll):
            if remote_files:
                self.report({"WARNING"}, f"No candidates — found in {', '.join(remote_files)} but nothing listed")
            else:
                self.report({"INFO"}, "No flattenable overrides found")
        else:
            rigs = len({r.rig for r in coll})
            self.report({"INFO"}, f"Found {len(coll)} override part(s) across {rigs} group(s) "
                                   f"({remote_count} remote)")
        return {"FINISHED"}


# --- Phase 4 Apply: the actual flatten-and-reapply mutation ----------------
#
# Confirmed against Blender's official Python API docs (triple-verified
# 2026-06-26 against the official downloadable 5.1 reference, live RNA
# introspection of the installed binary, and a third independent mirror — see
# docs/TODO.md): bpy.types.ID.override_create(remap_local_usages) ->
# new local override (or the SAME id, see below), IDOverrideLibraryProperties.
# add(rna_path), and ID.user_remap(new_id).
#
# ONE override_create() call PER MEMBER, not a single override_hierarchy_
# create() call for the whole rig (that was the original design — changed
# 2026-06-26 after real production data, see docs/TODO.md's "Phase 4 Apply
# safety investigation"). hierarchy_create's one-call-builds-everything
# convenience came with a hidden cost: on a file where hundreds of characters
# share a handful of templates in one library, it can ADOPT an
# already-existing object that belongs to a DIFFERENT character (sharing the
# same ultimate reference) instead of creating a fresh one — silently
# corrupting that other character once properties get replayed onto it. Since
# we already enumerate every member + its own reference via the chain census,
# we don't need hierarchy_create's auto-discovery; doing it per member lets
# each one be verified independently (see ``_flatten_rig``'s freshness check)
# instead of trusting one opaque hierarchy-wide call. Members are fully
# independent now — one member failing (including the rig root itself) no
# longer blocks the others, since each has its own override_create() call and
# its own collection-linking/property-replay/remap (user explicitly asked for
# "duplicate where possible" over "block the whole rig on one bad part").

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
    :class:`core.linkchain.FlattenApplyResult` per member — independently;
    one member failing (including the rig root) does not block the others.

    Each member gets its OWN ``ID.override_create()`` call (see the module
    comment above for why this replaced a single ``override_hierarchy_
    create()`` call). The one real failure mode override_create() has on this
    project's files — converting an existing, still-shared plain link IN
    PLACE (when that reference has never been individually overridden by
    anyone in the file before) instead of creating an independent new object
    — is checked for via a before/after freshness check on the result, NOT a
    pre-check. A ``bpy.data.user_map``-based pre-check was tried and reverted
    (2026-06-26): in this file, EVERY heavily-shared template reference shows
    real users via user_map once the normal scan-then-apply flow has run
    (hundreds of OTHER characters' overrides legitimately point at the same
    reference — that's expected, not a danger sign), so a pre-check on "does
    anything else reference this" blocked every member, not just the unsafe
    one. The freshness check below — did override_create() actually allocate
    a NEW object this call — is the reliable signal; it doesn't care how many
    other things reference the SOURCE reference, only whether THIS call
    produced independent new data."""
    from ..log import get_logger

    log = get_logger()
    results = []
    for plan in members:
        old_obj = bpy.data.objects.get(plan.object_name)
        if old_obj is None or old_obj.override_library is None:
            results.append(linkchain.FlattenApplyResult(
                plan.object_name, False,
                "no longer a live override — re-run Find Flattenable Characters"))
            continue
        if plan.reference is None:
            results.append(linkchain.FlattenApplyResult(
                plan.object_name, False, "no reference recorded — skipped"))
            continue

        direct = _link_direct(rig_plan.ultimate_library, plan.reference.kind, plan.reference.name)
        if direct is None:
            msg = (f"'{plan.reference.name}' not found directly in "
                   f"{pathlib.Path(rig_plan.ultimate_library).name} — skipped")
            results.append(linkchain.FlattenApplyResult(plan.object_name, False, msg))
            continue

        attr = _KIND_TO_COLLECTION.get(plan.reference.kind, "objects")
        before_names = set(o.name for o in getattr(bpy.data, attr))
        try:
            new_obj = direct.override_create(remap_local_usages=False)
        except RuntimeError as exc:
            log.warning("F7 flatten apply: override_create failed for %s: %s",
                        plan.object_name, exc)
            new_obj = None
        if new_obj is None:
            results.append(linkchain.FlattenApplyResult(
                plan.object_name, False,
                "Blender declined to override this part — see debug log"))
            continue
        after_names = set(o.name for o in getattr(bpy.data, attr))
        if new_obj.name not in (after_names - before_names):
            # Belt-and-suspenders: the pre-check above should already have
            # caught this, but if override_create() still didn't create a
            # fresh object for some other reason, don't trust the result.
            results.append(linkchain.FlattenApplyResult(
                plan.object_name, False,
                "override_create() did not produce a fresh object for this "
                "part — skipped to avoid corrupting whatever it actually is"))
            continue

        if isinstance(new_obj, bpy.types.Object):
            for coll in old_obj.users_collection:
                try:
                    coll.objects.link(new_obj)
                except RuntimeError:
                    pass  # already linked

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


# --- Flatten v2 (docs/TODO.md Group 11 #47, 2026-06-27) ---------------------
#
# The shared "Flatten Selected" action: an arbitrary cross-group batch (any
# mix of rig groups, standalone-by-type groups, and remote-sourced groups),
# not one rig at a time like _flatten_rig above. Deliberately a SEPARATE
# function rather than a refactor of _flatten_rig — that one is validated
# against real production data ("Flattened 8/9 part(s)" on People1_v5.1.blend)
# and is left untouched; _flatten_member below duplicates its per-member body
# but uses each plan's OWN ultimate_library (not one shared across a rig) and
# adds the two genuinely new branches _flatten_rig never needed: a remote-
# sourced member (no local old_obj to remap from) and Make Copy placement
# (a mirrored collection instead of the old object's own collection
# membership) + the Make Local finishing step.

def _harvest_remote(blend_path: str, names: list[str]):
    """Open ``blend_path`` in a disposable background Blender process and
    read every named object's override reference + properties there — never
    touches the live session (confirmed via probe, 2026-06-27,
    ``tests/probe_remote_override_link.py``: there is no live-bpy way to do
    this, ``bpy.data.libraries.load`` never exposes an override object at
    all). Mirrors ``ops/dryrun_render.py``'s subprocess lifecycle exactly.
    Yields ``(fraction, message)`` progress tuples; the final yielded value
    via StopIteration.value is ``dict[str, HarvestResult]``."""
    script_path = out_path = None
    try:
        fd, script_path = tempfile.mkstemp(suffix=".py", prefix="assetdoctor_harvest_")
        fd_out, out_path = tempfile.mkstemp(suffix=".json", prefix="assetdoctor_harvest_out_")
        os.close(fd_out)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(remote_harvest.build_harvest_script(names, out_path))

        cmd = remote_harvest.build_harvest_command(bpy.app.binary_path, blend_path, script_path)
        popen_kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                                **popen_kwargs)
        start = time.monotonic()
        timeout = 1800  # matches Dry-Run Render's own bound — same multi-GB-file reality
        while proc.poll() is None:
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                proc.kill()
                return {n: remote_harvest.HarvestResult(n, False) for n in names}
            time.sleep(0.2)
            yield (min(0.9, elapsed / timeout), f"Reading {pathlib.Path(blend_path).name}…")

        if proc.returncode != 0:
            return {n: remote_harvest.HarvestResult(n, False) for n in names}
        with open(out_path, "r", encoding="utf-8") as fh:
            return remote_harvest.parse_harvest_output(fh.read())
    finally:
        for p in (script_path, out_path):
            if p:
                try:
                    os.remove(p)
                except OSError:
                    pass


def _find_collection_path(root, target_colls: set) -> tuple[str, ...] | None:
    """Names from ``root`` down to (and including) whichever of
    ``target_colls`` is reachable first, or ``None``."""
    def walk(coll, ancestors):
        here = ancestors + (coll.name,)
        if coll in target_colls:
            return here
        for child in coll.children:
            found = walk(child, here)
            if found is not None:
                return found
        return None
    return walk(root, ())


def _object_location_path(scene, obj) -> tuple[str, ...]:
    """This object's collection path from the scene's master collection down
    to its immediate parent collection — the anchor :func:`_realize_mirror_
    plan` mirrors. A remote-sourced member (no real local object at all) has
    no caller for this at all; it gets ``(scene.collection.name,)`` directly
    instead (the deliberate "no anchor found" scope decision, docs/TODO.md
    Group 11 #47 — composes for free with the lowest-common-ancestor math,
    since the LCA of a real path and the bare root is just the root)."""
    target_colls = set(obj.users_collection)
    if target_colls:
        found = _find_collection_path(scene.collection, target_colls)
        if found is not None:
            return found
    return (scene.collection.name,)


def _resolve_real_collection(scene, path: tuple[str, ...]):
    """The REAL ``bpy.types.Collection`` at ``path`` (names from the scene's
    root collection down), or the scene root itself for an empty path.
    ``mirror_collection_paths``'s FIRST entry is always the lowest common
    ANCESTOR -- with a single object, that ancestor can be arbitrarily deep
    (its own immediate parent collection), not necessarily the scene root
    (confirmed by hand, 2026-06-27: a naive "len(prefix)==1 -> scene root"
    check is wrong whenever there's only one object in the batch and its
    parent isn't the root) -- so the first entry's OWN parent always needs
    a real lookup, never an assumption."""
    coll = scene.collection
    for name in path[1:]:  # path[0] is always the scene root's own name
        found = coll.children.get(name)
        if found is None:
            break  # shouldn't happen; fail safe to whatever was resolved so far
        coll = found
    return coll


def _realize_mirror_plan(scene, paths: dict[str, tuple[str, ...]]) -> dict[str, "bpy.types.Collection"]:
    """Create (or reuse, across repeated Flatten Selected runs) the real
    Collections for the Make-Copy mirror tree, per ``core.collection_mirror``,
    and return ``{object_name: leaf Collection}`` for every entry in
    ``paths``. Only the FIRST entry's parent needs a real lookup (see
    :func:`_resolve_real_collection`) -- every later entry's parent was
    necessarily created earlier in this same loop (``mirror_collection_
    paths`` sorts parents before children)."""
    ordered = collection_mirror.mirror_collection_paths(list(paths.values()))
    created: dict[tuple[str, ...], "bpy.types.Collection"] = {}
    for i, prefix in enumerate(ordered):
        mirror_nm = collection_mirror.mirror_name(prefix[-1])
        parent = (_resolve_real_collection(scene, prefix[:-1]) if i == 0
                  else created[prefix[:-1]])
        coll = parent.children.get(mirror_nm)
        if coll is None:
            coll = bpy.data.collections.new(mirror_nm)
            parent.children.link(coll)
        created[prefix] = coll
    return {name: created[path] for name, path in paths.items()}


def _flatten_member(context, plan, mirror_collections: dict, make_local: bool):
    """One member's real flatten, for the cross-group "Flatten Selected"
    batch — see the module comment above for why this duplicates rather than
    reuses ``_flatten_rig``'s body. ``mirror_collections`` (always populated
    — Make Copy is the only path built so far, docs/TODO.md Group 11 #47)
    maps this member's name to its already-realized leaf mirror Collection."""
    from ..log import get_logger
    log = get_logger()

    if plan.reference is None:
        return linkchain.FlattenApplyResult(plan.object_name, False,
                                            "no reference recorded — skipped")

    direct = _link_direct(plan.ultimate_library, plan.reference.kind, plan.reference.name)
    if direct is None:
        msg = (f"'{plan.reference.name}' not found directly in "
               f"{pathlib.Path(plan.ultimate_library).name} — skipped")
        return linkchain.FlattenApplyResult(plan.object_name, False, msg)

    attr = _KIND_TO_COLLECTION.get(plan.reference.kind, "objects")
    before_names = set(o.name for o in getattr(bpy.data, attr))
    try:
        new_obj = direct.override_create(remap_local_usages=False)
    except RuntimeError as exc:
        log.warning("Flatten Selected: override_create failed for %s: %s", plan.object_name, exc)
        new_obj = None
    if new_obj is None:
        return linkchain.FlattenApplyResult(plan.object_name, False,
            "Blender declined to override this part — see debug log")
    after_names = set(o.name for o in getattr(bpy.data, attr))
    if new_obj.name not in (after_names - before_names):
        return linkchain.FlattenApplyResult(plan.object_name, False,
            "override_create() did not produce a fresh object for this part — "
            "skipped to avoid corrupting whatever it actually is")

    old_obj = bpy.data.objects.get(plan.object_name)
    is_local = old_obj is not None and old_obj.override_library is not None

    if isinstance(new_obj, bpy.types.Object):
        target_coll = mirror_collections.get(plan.object_name)
        if target_coll is not None:
            try:
                target_coll.objects.link(new_obj)
            except RuntimeError:
                pass
        new_obj.name = collection_mirror.mirror_name(plan.object_name)

    applied = failed = 0
    for prop in plan.properties:
        try:
            new_obj.override_library.properties.add(prop.rna_path)
            _set_override_value(new_obj, prop.rna_path, prop.value)
            applied += 1
        except Exception as exc:
            failed += 1
            log.warning("Flatten Selected: %s on %s failed: %s",
                       prop.rna_path, plan.object_name, exc)

    if is_local:
        old_obj.user_remap(new_obj)
        old_obj.hide_viewport = True
        old_obj.hide_render = True

    if make_local:
        try:
            new_obj.make_local()
        except Exception as exc:
            log.warning("Flatten Selected: make_local failed for %s: %s", plan.object_name, exc)

    lib_name = pathlib.Path(plan.ultimate_library).name
    msg = f"flattened via direct link to {lib_name} — {applied} propert{'y' if applied == 1 else 'ies'} replayed"
    if failed:
        msg += f", {failed} failed (see debug log)"
    return linkchain.FlattenApplyResult(
        plan.object_name, True, msg, properties_applied=applied, properties_failed=failed)


class ASSETDOCTOR_OT_flatten_selected(ModalProgressMixin, bpy.types.Operator):
    """The single shared action for every CHECKED group in the picker (any
    mix of rig/standalone-type/remote groups), using the one shared Make
    Local / Make Copy setting on the "Flattenable overrides" subgroup's own
    title line — not a per-character button. Remote-sourced members are
    harvested via a disposable background Blender process first (one open
    per donor file, batched); local members reuse today's live read."""

    bl_idname = "assetdoctor.flatten_selected"
    bl_label = "Flatten Selected"
    bl_description = (
        "Flatten every CHECKED character/group: link directly from the "
        "ultimate library, replay its recorded changes, and mirror it into a "
        "new collection structure with the original hidden (Make Copy). "
        "Remote-sourced characters are harvested via a disposable background "
        "Blender process first — can take a while for large donor files. "
        "Takes a backup first"
    )
    bl_options = {"REGISTER"}

    def invoke(self, context, event):
        wm = context.window_manager
        if not len(wm.assetdoctor_flatten_candidates):
            self.report({"ERROR"}, "Run Find Flattenable Links first")
            return {"CANCELLED"}
        return super().invoke(context, event)

    def run_steps(self, context):
        wm = context.window_manager
        rows = wm.assetdoctor_flatten_candidates
        deselected = set(filter(None, wm.assetdoctor_flatten_deselected.split("\n")))

        groups: dict[str, list] = {}
        for row in rows:
            groups.setdefault(row.rig, []).append(row)
        members = [m for rig, ms in groups.items() if rig not in deselected for m in ms]
        if not members:
            self.report({"WARNING"}, "Nothing selected")
            return

        if not wm.assetdoctor_flatten_make_copy:
            self.report({"INFO"},
                       "In-place (Make Copy off) isn't built yet — running as a copy instead")
        make_local = wm.assetdoctor_flatten_make_local

        yield (0.02, "Backing up…")
        from .safety import auto_backup
        auto_backup(context)

        chain_raw = getattr(wm, data_prop("f7chain"), "")
        chain_report = Report.from_json(chain_raw) if chain_raw else Report(title="", feature="f7chain")
        routes = linkchain.routes_from_report(chain_report)
        cached = json.loads(wm.assetdoctor_flatten_plans_json or "{}")

        # --- Harvest every remote member first, one subprocess open per ----
        # --- donor file, regardless of which group(s) it came from ---------
        remote_members = [m for m in members if m.is_remote]
        harvested: dict[str, remote_harvest.HarvestResult] = {}
        if remote_members:
            by_file = remote_harvest.group_by_source_file(
                [(m.name, m.source_file) for m in remote_members])
            for i, (source_file, names) in enumerate(by_file.items()):
                base = 0.05 + 0.45 * i / len(by_file)
                gen = _harvest_remote(source_file, names)
                result = None
                try:
                    while True:
                        frac, msg = next(gen)
                        yield (base + 0.45 * frac / len(by_file), msg)
                except StopIteration as stop:
                    result = stop.value
                harvested.update(result or {})

        # --- Build a FlattenPlan for every selected member ------------------
        plans: dict[str, object] = {}
        results = []
        for m in members:
            if m.is_remote:
                hr = harvested.get(m.name)
                if hr is None or not hr.found:
                    results.append(linkchain.FlattenApplyResult(
                        m.name, False, "not found in donor file (renamed/deleted since the scan?)"))
                    continue
                plan = linkchain.build_flatten_plan(m.name, hr.reference, list(hr.properties), routes)
            else:
                if m.name not in cached:
                    results.append(linkchain.FlattenApplyResult(
                        m.name, False, "no cached plan — re-run Find Flattenable Links"))
                    continue
                plan = linkchain.flatten_plan_from_dict(cached[m.name])
            if not (plan.route and plan.properties):
                results.append(linkchain.FlattenApplyResult(
                    m.name, False, "; ".join(plan.warnings) or "not ready — skipped"))
                continue
            plans[m.name] = plan

        # --- Make Copy: mirror placement for every flattenable member ------
        yield (0.55, "Planning collection placement…")
        scene = context.scene
        paths = {}
        for name, plan in plans.items():
            obj = bpy.data.objects.get(name)
            paths[name] = (_object_location_path(scene, obj) if obj is not None
                           else (scene.collection.name,))
        mirror_collections = _realize_mirror_plan(scene, paths) if paths else {}

        # --- Apply -----------------------------------------------------------
        total = len(plans) or 1
        for i, (name, plan) in enumerate(plans.items()):
            yield (0.6 + 0.4 * i / total, f"Flattening {name}…")
            try:
                result = _flatten_member(context, plan, mirror_collections, make_local)
            except Exception as exc:
                from ..log import get_logger
                get_logger().warning("Flatten Selected: %s crashed: %s", name, exc)
                result = linkchain.FlattenApplyResult(name, False, f"unexpected error: {exc}")
            results.append(result)

        context.view_layer.update()

        ok = sum(1 for r in results if r.ok)
        wm.assetdoctor_flatten_done += ok
        wm.assetdoctor_flatten_failed += (len(results) - ok)
        by_name = {r.object_name: r for r in results}
        for row in members:
            r = by_name.get(row.name)
            if r is not None:
                row.ready = r.ok
                row.status = r.message

        report = linkchain.build_flatten_apply_report("Selected", results)
        stash_report(context, report, "f7flatten")
        yield (1.0, "Done")
        level = "INFO" if ok == len(results) else "WARNING"
        self.report({level}, f"Flattened {ok}/{len(results)} part(s). Save to persist.")


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
    """Toggle membership of ``key`` in a newline-joined WM string-set property
    -- expand/collapse one rig/character group by default
    (``assetdoctor_flatten_expanded``), or select/deselect one
    (``assetdoctor_flatten_deselected``, 2026-06-27 docs/TODO.md Group 11
    #47 -- DESELECTED, not selected, so every group starts checked without
    needing to pre-populate the set with every group's name)."""

    bl_idname = "assetdoctor.flatten_category_toggle"
    bl_label = "Toggle Rig Group State"
    bl_options = {"INTERNAL"}

    key: bpy.props.StringProperty()  # type: ignore[valid-type]
    prop: bpy.props.StringProperty(default="assetdoctor_flatten_expanded")  # type: ignore[valid-type]

    def execute(self, context):
        wm = context.window_manager
        raw = getattr(wm, self.prop, "")
        keys = set(filter(None, raw.split("\n")))
        keys.discard(self.key) if self.key in keys else keys.add(self.key)
        setattr(wm, self.prop, "\n".join(sorted(keys)))
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}
