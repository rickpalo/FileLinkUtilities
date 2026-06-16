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


class ASSETDOCTOR_OT_analyze_overrides(ModalProgressMixin, bpy.types.Operator):
    bl_idname = "assetdoctor.analyze_overrides"
    bl_label = "Analyze Overrides & Duplicates"
    bl_description = (
        "Scan the CURRENT file for duplicate datablocks (the .NNN families that "
        "bloat memory), count linked/override datablocks per library, and detect "
        "datablock dependency loops (the cause of lib.override.resync spam). "
        "Read-only"
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
            fams = dg.duplicate_families([b.name for b in blocks])
            if fams:
                extract.duplicates[label] = fams
            for b in blocks:
                lib = getattr(b, "library", None)
                ovr = getattr(b, "override_library", None)
                if lib is not None:
                    lib_counter[lib.name] += 1
                if ovr is not None:
                    override_count += 1
                if lib is not None or ovr is not None:
                    relevant.append(b)
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
        yield 1.0, (f"Done: {len(extract.loops)} loop(s), "
                    f"~{dg.wasted_copies(extract.duplicates)} duplicate(s)")
        self.report({"INFO"}, f"Analyzed {label}: {len(extract.loops)} dependency loop(s)")
