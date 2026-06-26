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


def _drive(path: str) -> str:
    """Windows drive letter ("C:"), or "(no drive)" for a UNC/driveless path."""
    drive, _tail = os.path.splitdrive(path)
    return drive.upper() if drive else "(no drive)"


@dataclass
class LibFixPlan:
    renames: list[tuple[str, str, str]] = field(default_factory=list)  # (name, old, new)
    # resolved key -> [(library name, stored path)] -- the stored path is needed
    # so the "Use Selected Paths" UI (item 6, 2026-06-25) can show each member's
    # own form as a checkbox label, not just its name.
    duplicates: dict[str, list[tuple[str, str]]] = field(default_factory=dict)


def plan_library_fixes(libs: list[LibDesc], blend_dir: str) -> LibFixPlan:
    """Compute the safe path normalisations + the duplicate-block groups."""
    renames: list[tuple[str, str, str]] = []
    for lib in libs:
        if not lib.exists or not needs_fix(lib):
            continue  # missing -> relinker; already clean -> skip
        new = to_relative(lib.resolved, blend_dir)
        if new and new != lib.stored:
            renames.append((lib.name, lib.stored, new))

    groups: dict[str, list[tuple[str, str]]] = {}
    for lib in libs:
        groups.setdefault(_key(lib.resolved), []).append((lib.name, lib.stored))
    duplicates = {k: v for k, v in groups.items() if len(v) > 1}
    return LibFixPlan(renames=renames, duplicates=duplicates)


@dataclass
class AbsoluteLibrary:
    """One absolute-path library, for item 7's grouped checkbox UI.
    ``new`` is the relative path it would become, or "" when it can't be
    (different drive — there is no relative path across Windows drives)."""

    name: str
    stored: str
    new: str = ""


@dataclass
class AbsolutePathGroup:
    drive: str  # "C:", "D:", ... or "(no drive)" for a UNC path
    fixable: bool  # False = cross-drive from the current file — grouped, but un-fixable
    members: list[AbsoluteLibrary] = field(default_factory=list)


def plan_absolute_paths(libs: list[LibDesc], blend_dir: str) -> list[AbsolutePathGroup]:
    """Group every EXISTING absolute-stored library by drive (item 7,
    2026-06-25: "the absolute paths section should group by drive... I don't
    think a relative path is possible to other drives"). Same-drive-as-the-
    current-file groups are fixable; cross-drive groups are still reported
    (Path Normalization's plain ``renames`` list silently drops these today —
    a transparency gap, not just a missing action) but flagged un-fixable,
    fixable groups sort first."""
    groups: dict[str, AbsolutePathGroup] = {}
    for lib in libs:
        if not lib.exists or lib.stored.startswith("//"):
            continue  # missing -> relinker; already relative -> not an absolute-path issue
        new = to_relative(lib.resolved, blend_dir)
        drive = _drive(lib.resolved)
        g = groups.setdefault(drive, AbsolutePathGroup(drive=drive, fixable=new is not None))
        g.members.append(AbsoluteLibrary(name=lib.name, stored=lib.stored, new=new or ""))
    return sorted(groups.values(), key=lambda g: (not g.fixable, g.drive))


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


def build_broken_links_report(
    broken: list[tuple[str, str, str]], blend_name: str = "current file"
) -> Report:
    """Report the current file's broken/missing library links.

    ``broken`` is ``[(library name, stored path, auto-found candidate or "")]``.
    Always emits at least one finding: an analysis must produce a visible result
    even when it finds nothing, so a clean file shows "No broken library links
    found" rather than silently doing nothing (user rule, 2026-06-22). Mirrors
    the ✓ "clean" status row :func:`build_libfix_report` produces."""
    report = Report(title=f"Broken Library Links: {blend_name}", feature="f7links")
    for name, stored, candidate in broken:
        if candidate:
            msg = f"{name}:  missing ({stored})  —  auto-match found: {candidate}"
        else:
            msg = f"{name}:  missing ({stored})  —  no match found (pick a file)"
        report.add(Finding(category="broken_link", message=msg, severity="error",
                           items=[name, stored], data={"name": name, "stored": stored}))
    if not broken:
        report.add(Finding(
            category="clean",
            message="✓ No broken library links found — every linked library resolves on disk",
            severity="info"))
    return report


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
    for _resolved, members in plan.duplicates.items():
        names = [name for name, _stored in members]
        report.add(Finding(category="duplicate_library",
                           message=f"{len(names)} libraries resolve to the same file: "
                                   f"{', '.join(names)}",
                           severity="warning", items=names,
                           data={"members": [list(m) for m in members]}))
    if not report.findings:
        report.add(Finding(category="clean",
                           message="✓ All library paths are clean — nothing to fix",
                           severity="info"))
    return report
