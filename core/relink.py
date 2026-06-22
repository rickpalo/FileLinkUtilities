"""F7 Phase 3a — current-file library path hygiene (bpy-free core).

Given the current file's linked libraries, plan **safe, reversible** fixes:
  - absolute path -> ``//``-relative (only when same-drive AND the target exists;
    cross-drive D:↔E: paths are left alone — that's the relinker's job),
  - backslashes -> forward slashes,
and report **duplicate library blocks** (two libraries resolving to the same file
via inconsistent stored paths — the bloat source). Normalising paths is low-risk
and undoable from the backup; merging duplicate blocks is deferred (riskier).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .report import Finding, Report


@dataclass
class LibDesc:
    """A current-file linked library, as the operator extracts it from bpy.data."""

    name: str
    stored: str  # library.filepath as stored ("//…" or absolute)
    resolved: str  # absolute, resolved path
    exists: bool


def has_backslash(stored: str) -> bool:
    return "\\" in stored


def to_relative(target_abs: str, blend_dir: str) -> str | None:
    """A ``//``-relative, forward-slash path from ``blend_dir`` to ``target_abs``.
    Returns None when they are on different drives (can't be relativised)."""
    try:
        rel = os.path.relpath(target_abs, blend_dir)
    except ValueError:
        return None  # different drives (Windows)
    return "//" + rel.replace("\\", "/")


def needs_fix(lib: LibDesc) -> bool:
    """Absolute, or stored with backslashes — both are portability/consistency hits."""
    return (not lib.stored.startswith("//")) or has_backslash(lib.stored)


def relink_stored_path(target_abs: str, blend_dir: str) -> str:
    """The path to store in ``library.filepath`` when relinking to ``target_abs``.

    Same-drive targets become ``//``-relative (portable); a cross-drive target
    keeps its absolute path (can't be relativised on Windows). This is the single
    place the relink operators turn a chosen target file into a stored path."""
    return to_relative(target_abs, blend_dir) or target_abs


def _key(p: str) -> str:
    return p.replace("\\", "/").rstrip("/").lower()


@dataclass
class LibFixPlan:
    renames: list[tuple[str, str, str]] = field(default_factory=list)  # (name, old, new)
    duplicates: dict[str, list[str]] = field(default_factory=dict)  # resolved key -> names


def plan_library_fixes(libs: list[LibDesc], blend_dir: str) -> LibFixPlan:
    """Compute the safe path normalisations + the duplicate-block groups."""
    renames: list[tuple[str, str, str]] = []
    for lib in libs:
        if not lib.exists or not needs_fix(lib):
            continue  # missing -> relinker; already clean -> skip
        new = to_relative(lib.resolved, blend_dir)
        if new and new != lib.stored:
            renames.append((lib.name, lib.stored, new))

    groups: dict[str, list[str]] = {}
    for lib in libs:
        groups.setdefault(_key(lib.resolved), []).append(lib.name)
    duplicates = {k: v for k, v in groups.items() if len(v) > 1}
    return LibFixPlan(renames=renames, duplicates=duplicates)


def find_relink_candidates(
    missing: list[LibDesc], search_dirs: list[str]
) -> dict[str, str]:
    """For each MISSING library, a unique same-filename ``.blend`` found in
    ``search_dirs`` (the folders of the file's resolvable libraries + its own
    folder). Returns ``{library name: candidate absolute path}``. Ambiguous (>1
    match) or unfound libraries are omitted — we only auto-propose unambiguous
    relinks; the rest are left for a manual/relinker pass."""
    index: dict[str, list[str]] = {}
    seen_dirs: set[str] = set()
    for d in search_dirs:
        key = d.replace("\\", "/").rstrip("/").lower()
        if key in seen_dirs:
            continue
        seen_dirs.add(key)
        try:
            for entry in os.scandir(d):
                if entry.is_file() and entry.name.lower().endswith(".blend"):
                    index.setdefault(entry.name.lower(), []).append(
                        os.path.normpath(entry.path))
        except OSError:
            continue
    out: dict[str, str] = {}
    for lib in missing:
        base = os.path.basename((lib.resolved or lib.stored).replace("\\", "/")).lower()
        matches = index.get(base, [])
        if len(matches) == 1:
            out[lib.name] = matches[0]
    return out


def build_libfix_report(plan: LibFixPlan, relinks: dict[str, str] | None = None,
                        blend_name: str = "current file") -> Report:
    # No standalone "Summary" row — the section headers (with counts) say it all
    # (user, 2026-06-16). The category becomes the self-describing top line.
    report = Report(title=f"Library paths: {blend_name}", feature="f7fix")
    for name, new in (relinks or {}).items():
        report.add(Finding(category="relink_missing",
                           message=f"{name}:  missing  →  {new}",
                           severity="error", items=[name, new],
                           data={"name": name, "new": new}))
    for name, old, new in plan.renames:
        report.add(Finding(category="normalize_path",
                           message=f"{name}:  {old}  →  {new}",
                           severity="warning", items=[old, new],
                           data={"name": name, "new": new}))
    for _resolved, names in plan.duplicates.items():
        report.add(Finding(category="duplicate_library",
                           message=f"{len(names)} libraries resolve to the same file: "
                                   f"{', '.join(names)}",
                           severity="warning", items=names))
    if not report.findings:
        report.add(Finding(category="clean",
                           message="✓ All library paths are clean — nothing to fix",
                           severity="info"))
    return report
