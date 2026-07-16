"""F7 Phase 2 — live current-file analysis: duplicate datablocks, library/override
census, and datablock dependency-loop detection.

Walks ``bpy.data`` (this needs a live session — it can't be done offline), extracts
plain data, and hands it to :mod:`core.datablock_graph` for the pure logic. Loop
detection is restricted to linked/override datablocks (where the resync loops that
spam ``lib.override.resync`` and bloat the file live) and capped so a giant file
can't hang the walk."""

from __future__ import annotations

import bpy

from ..core import datablock_graph as dg
from ..core.datablock_graph import LiveExtract
from ..core.missingdata import MissingBlock
from .progress import ModalProgressMixin
from .report_store import stash_report

# (label, bpy.data attribute) for the datablock types worth auditing.
_COLLECTIONS = [
    ("Material", "materials"), ("Mesh", "meshes"), ("Image", "images"),
    ("Object", "objects"), ("Node Group", "node_groups"), ("Armature", "armatures"),
    ("Action", "actions"), ("Texture", "textures"), ("Curve", "curves"),
    ("Light", "lights"), ("Collection", "collections"), ("World", "worlds"),
    ("Shape Key", "shape_keys"), ("Particle", "particles"),
]

# Above this many linked/override datablocks, skip loop detection (the user_map +
# cycle search would be too heavy); the duplicate/library census still runs.
_LOOP_NODE_CAP = 60000


def _node_id(idblock) -> str:
    return f"{type(idblock).__name__}/{idblock.name}"


def _iter_all_blocks():
    """Yield ``(bpy.data attribute, block)`` for EVERY ID datablock across all of
    ``bpy.data``'s collections — the shared generic walk this addon's per-feature
    scans are built on top of (Phase 2b consolidation, 2026-06-25: this used to be
    duplicated near-verbatim in ``ops.examine_library._iter_library_blocks``, same
    shape, different predicate). Non-ID collections are skipped on their first item."""
    for attr in dir(bpy.data):
        if attr.startswith("_"):
            continue
        coll = getattr(bpy.data, attr, None)
        if not isinstance(coll, bpy.types.bpy_prop_collection):
            continue
        for block in coll:
            if not isinstance(block, bpy.types.ID):
                break  # not a data-block collection (e.g. a settings list) — skip it
            yield attr, block


def _iter_missing_blocks():
    """Yield every ``is_missing`` (placeholder) ID across all of ``bpy.data``'s
    data-block collections. Walks generically so ANY linked type counts (not just
    the audited dup-census set).

    EXCLUDES ``bpy.data.libraries`` (user report 2026-07-15): a *missing Library*
    has ``is_missing = True`` too, so it used to appear in Datablock Reconnect as a
    "Library: foo.blend" row under "(source unknown)" — but a library isn't
    reconnectable via the datablock (``user_remap``) mechanism; it's fixed by Relink
    or Retarget in Broken Library Links. Listing it here was a dead end and made the
    3 broken libraries look like they belonged in two places at once."""
    for attr, block in _iter_all_blocks():
        if attr == "libraries":
            continue  # a missing Library is a Relink/Retarget job, not a reconnect
        if getattr(block, "is_missing", False):
            lib = getattr(block, "library", None)
            yield MissingBlock(
                kind=type(block).__name__,
                name=block.name,
                library=(lib.filepath if lib is not None else ""),
                collection=attr)


class FILELINK_OT_scan_all_missing(bpy.types.Operator):
    bl_idname = "filelink.scan_all_missing"
    bl_label = "Find All Missing"
    bl_description = (
        "Run all three Connect-phase checks at once: broken library LINKS (whole "
        ".blend files that can't be found), reconnectable DATA-BLOCKS (individual "
        "linked materials / objects that didn't resolve), and missing TEXTURES "
        "(image files that moved). Read-only; each list below fills in either way"
    )
    bl_options = {"REGISTER"}

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the file first")
            return {"CANCELLED"}
        bpy.ops.filelink.scan_broken_links()         # whole missing libraries
        bpy.ops.filelink.scan_reconnect_targets()    # individual placeholder ids
        bpy.ops.filelink.scan_broken_textures()      # missing image files (2026-07-14)
        if context.area:
            context.area.tag_redraw()
        self.report({"INFO"},
                    "Checked broken library links + reconnectable data-blocks + missing textures")
        return {"FINISHED"}


class FILELINK_OT_analyze_overrides(ModalProgressMixin, bpy.types.Operator):
    bl_idname = "filelink.analyze_overrides"
    bl_label = "Analyze Overrides"
    bl_description = (
        "Scan the CURRENT file: count linked/override datablocks per library and "
        "detect datablock dependency loops (the cause of lib.override.resync "
        "spam). Read-only"
    )

    def run_steps(self, context):
        extract = LiveExtract()
        from collections import Counter

        lib_counter: Counter = Counter()
        override_count = 0
        relevant: list = []  # linked/override id blocks (loop-graph nodes)

        n = len(_COLLECTIONS)
        for i, (label, attr) in enumerate(_COLLECTIONS):
            coll = getattr(bpy.data, attr, None)
            if coll is None:
                continue
            blocks = list(coll)
            extract.totals[label] = len(blocks)
            for b in blocks:
                lib = getattr(b, "library", None)
                ovr = getattr(b, "override_library", None)
                if lib is not None:
                    lib_counter[lib.name] += 1
                if ovr is not None:
                    override_count += 1
                if lib is not None or ovr is not None:
                    relevant.append(b)
                if attr == "shape_keys":
                    owner = getattr(b, "user", None)
                    if owner is not None and getattr(owner, "override_library", None) is not None:
                        extract.shape_key_risks.append((b.name, owner.name))
            yield (i + 1) / (n + 2), f"Scanning {label} ({len(blocks)})"

        extract.library_counts = sorted(lib_counter.items(), key=lambda kv: -kv[1])
        extract.override_count = override_count

        # Dependency loops among linked/override datablocks.
        yield n / (n + 2), "Detecting dependency loops…"
        if len(relevant) > _LOOP_NODE_CAP:
            extract.loops_skipped = f"{len(relevant)} linked/override datablocks (> {_LOOP_NODE_CAP})"
        elif relevant:
            try:
                ids = set(relevant)
                node = {b: _node_id(b) for b in relevant}
                umap = bpy.data.user_map(subset=relevant)
                edges = []
                for b in relevant:
                    for user in umap.get(b, ()):
                        if user in ids:  # edge user -> used (a dependency)
                            edges.append((node[user], node[b]))
                extract.loops = dg.find_datablock_loops(edges)
            except Exception as exc:  # never let a bpy quirk kill the report
                extract.loops_skipped = f"{type(exc).__name__}: {exc}"

        label = bpy.path.basename(bpy.data.filepath) or "current file"
        report = dg.build_live_report(extract, label)
        stash_report(context, report, "f7live")
        yield 1.0, f"Done: {len(extract.loops)} loop(s)"
        self.report({"INFO"}, f"Analyzed {label}: {len(extract.loops)} dependency loop(s)")
