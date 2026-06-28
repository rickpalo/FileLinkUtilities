"""F2 analysis: report what is linked into a file, grouped by source library.
bpy-free; the ops layer gathers the linked datablocks and performs the actual
make-local (which must happen in a live Blender session).

linked item dict contract (from ops):
    { "type": "Object", "name": "Tree", "library": "//libA.blend",
      "indirect": bool }   # indirect = pulled in transitively (library.parent set)
"""

from __future__ import annotations

import ntpath

from .report import Finding, Report


def _libname(path: str) -> str:
    return ntpath.basename(path) or path


def find_rename_collisions(all_names: list[dict]) -> list[dict]:
    """Datablocks that will collide on name once everything currently linked
    becomes local (docs/TODO.md Group 6 #19, 2026-06-27) — the actual risk
    Make Local poses to another file that links one of these BY NAME, not
    "this file is shared" in general. Blender enforces name uniqueness only
    WITHIN one library (local counts as its own), so two items can share a
    bare name today only because they live in different libraries; once
    they're ALL local, every name after the first gets a ``.001``-style
    auto-suffix — which silently breaks a same-named link from elsewhere.

    ``all_names``: ``{"type", "name", "library"}`` for EVERY existing
    datablock, local included (local items pass ``library=""``).
    Returns one dict per colliding name: ``{"type", "name", "members"}`` —
    ``members`` are the distinguishing sources ("local" or a library path)."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for it in all_names:
        groups.setdefault((it["type"], it["name"]), []).append(it)
    collisions = []
    for (kind, name), members in sorted(groups.items()):
        if len(members) < 2:
            continue
        collisions.append({
            "type": kind, "name": name,
            "members": sorted(m["library"] or "local" for m in members),
        })
    return collisions


def build_makelocal_report(items: list[dict], all_names: list[dict] | None = None) -> Report:
    report = Report(title="Make local", feature="F2")

    by_lib: dict[str, list[dict]] = {}
    for it in items:
        by_lib.setdefault(it["library"], []).append(it)

    indirect_total = 0
    for lib in sorted(by_lib):
        members = sorted(by_lib[lib], key=lambda m: (m["type"], m["name"]))
        n_indirect = sum(1 for m in members if m.get("indirect"))
        indirect_total += n_indirect
        tag = f" ({n_indirect} indirect)" if n_indirect else ""
        report.add(Finding(
            category="linked_library",
            message=f"{len(members)} datablock(s) linked from {_libname(lib)}{tag}",
            severity="info",
            items=[f"{m['type']}/{m['name']}" for m in members],
            data={"library": lib, "indirect": n_indirect},
        ))

    collisions = find_rename_collisions(all_names) if all_names else []
    for c in collisions:
        report.add(Finding(
            category="rename_risk",
            message=f"{c['type']}/{c['name']} — shared by {len(c['members'])} sources "
                    f"({', '.join(c['members'])}); Make Local will rename all but one",
            severity="warning",
            items=[f"{c['type']}/{c['name']}"],
            data={"members": c["members"]},
        ))

    tail = f"; {len(collisions)} name collision(s) will be renamed" if collisions else ""
    report.add(Finding(
        category="summary",
        message=(
            f"{len(items)} linked datablock(s) from {len(by_lib)} librar(ies); "
            f"{indirect_total} indirect{tail}"
        ),
        severity="warning" if (items or collisions) else "info",
        data={"linked": len(items), "libraries": len(by_lib), "indirect": indirect_total,
              "collisions": len(collisions)},
    ))
    return report
