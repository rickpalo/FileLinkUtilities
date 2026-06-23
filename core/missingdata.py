"""Batch 3 — missing DATA-BLOCKS report (bpy-free).

Blender marks a linked data-block whose source can't be resolved (the library
file is missing, or the block no longer exists in that library) with
``ID.is_missing``. These are placeholders: they keep the file loadable but render
as magenta / empty, and they're what other add-ons' timers trip over on the
crashing files (the "3 linked data-blocks missing" human_bundle case we didn't
surface before).

The operator walks ``bpy.data`` for ``is_missing`` blocks and feeds plain
:class:`MissingBlock` records here; this module owns the pure grouping + report
build so it's unit-testable without Blender.
"""

from __future__ import annotations

from dataclasses import dataclass

from .report import Finding, Report


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


def group_by_library(blocks: list[MissingBlock]) -> dict[str, list[MissingBlock]]:
    """``{library filepath: [missing blocks]}`` — missing blocks cluster by the
    library that failed to resolve, so the user fixes one broken library at a time."""
    out: dict[str, list[MissingBlock]] = {}
    for b in blocks:
        out.setdefault(b.library, []).append(b)
    return out


def build_missing_datablocks_report(blocks: list[MissingBlock],
                                    file_label: str = "current file") -> Report:
    """Report the file's missing data-blocks, grouped by their source library
    (worst-populated first). Always emits a row — a ✓ status when none are missing
    (negative output is a visible result, not a silent pass)."""
    report = Report(title=f"Missing data-blocks: {file_label}", feature="f7miss")
    if not blocks:
        report.add(Finding(category="clean",
                           message="✓ No missing data-blocks — all linked data resolved",
                           severity="info"))
        return report

    by_lib = group_by_library(blocks)
    libs = len(by_lib)

    # Headline first, as a flat top row (no drilling needed to read the totals).
    report.add(Finding(category="overview",
                       message=f"{libs} file(s) with {len(blocks)} missing data-block(s)",
                       severity="error",
                       data={"missing": len(blocks), "libraries": libs}))

    # Most-missing library first; ties broken by path for stable output.
    for lib in sorted(by_lib, key=lambda p: (-len(by_lib[p]), p.lower())):
        members = sorted(by_lib[lib], key=lambda b: (b.kind, b.name))
        libname = lib or "(unknown library)"
        report.add(Finding(category="missing_datablock",
                           message=f"{libname} — {len(members)} missing data-block(s)",
                           severity="error",
                           items=[f"{b.kind}: {b.name}" for b in members],
                           detail=f"{len(members)}",
                           data={"library": lib}))
    return report


__all__ = ["MissingBlock", "group_by_library", "build_missing_datablocks_report"]
