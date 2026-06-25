"""Batch 3 — the missing DATA-BLOCK record (bpy-free).

Blender marks a linked data-block whose source can't be resolved (the library
file is missing, or the block no longer exists in that library) with
``ID.is_missing``. These are placeholders: they keep the file loadable but render
as magenta / empty, and they're what other add-ons' timers trip over on the
crashing files (the "3 linked data-blocks missing" human_bundle case we didn't
surface before).

The operator walks ``bpy.data`` for ``is_missing`` blocks and feeds plain
:class:`MissingBlock` records to ``core.reconnect`` (Datablock Reconnect, the
only consumer now — the standalone read-only "Find Missing Data-blocks" report
that used to live here was deleted 2026-06-25: it scanned the exact same
``is_missing`` blocks Reconnect's "Find Reconnectable Data-blocks" already
shows, just without anything actionable, so it was a strict subset)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MissingBlock:
    """One unresolved (placeholder) data-block."""

    kind: str      # data-block type label, e.g. "Object", "Material", "Image"
    name: str      # the block's name
    library: str   # filepath of the library it should load from ("" if unknown)
    # The bpy.data collection attribute this block lives in (e.g. "materials") —
    # captured at scan time so a later RECONNECT (core.reconnect) knows exactly
    # which data_from/data_to attribute to read on a chosen source .blend, with no
    # guessing from ``kind`` (which is a Python class name, not always the same word).
    collection: str = ""


__all__ = ["MissingBlock"]
