"""Find identical-but-separate object data (meshes, …) used by different objects
and plan to collapse them onto one shared datablock — i.e. turn wasteful Shift-D
copies into instances. bpy-free; the ops layer fingerprints the data and applies
the plan with `ID.user_remap` + purge.

This is the geometry analogue of F3 (material dedup) and the engine behind the
"objects duplicated but could be instanced" requirement. Kind-agnostic, so other
data types (curves, …) only need a fingerprint + gather.

item dict contract (from ops):
    { "id": "Cube.001",  # unique, human-readable key (name + library)
      "name": "Cube.001",
      "kind": "Mesh",
      "fingerprint": str | None,
      "linked": bool,
      "users": int }      # how many objects use this datablock
"""

from __future__ import annotations

from .cluster import group_identical
from .report import Finding, Report


def choose_canonical(members: list[dict], prefer_linked: bool = False) -> dict:
    """Keep the most-shared LOCAL datablock by default (preserves existing
    instances). ``prefer_linked=True`` (docs/TODO.md #21, 2026-06-27) keeps an
    already-linked-in copy instead — repoints local users onto the shared
    library datablock, reducing local footprint; the linked datablock itself
    is never removed either way (only local IDs can be)."""
    def key(m):
        linked_first = (not m["linked"]) if prefer_linked else m["linked"]
        return (linked_first, -m.get("users", 0), m["name"])
    return sorted(members, key=key)[0]


def removable_count(plan: list[dict]) -> int:
    """Total mesh datablocks the plan would actually REMOVE — local victims
    only; a linked victim stays in its library (only its local users are
    repointed), same accounting as core.f3_materials."""
    return sum(len(group["victims"]) - len(group.get("linked_victims", [])) for group in plan)


def build_instance_plan(items: list[dict], prefer_linked: bool = False):
    """Return (Report, plan). plan entries: {kind, canonical: id, victims: [id],
    linked_victims: [id]}. Clusters by content fingerprint regardless of
    local/linked (docs/TODO.md #21, 2026-06-27 — previously local-only): a
    linked victim's LOCAL users still get repointed onto the canonical, but
    the linked datablock itself is never touched/removed."""
    report = Report(title="Instanceable duplicate geometry", feature="F5")
    by_id = {it["id"]: it for it in items}
    labeled = sorted(
        (it["id"], f"{it['kind']}|{it['fingerprint']}")
        for it in items
        if it.get("fingerprint")
    )
    clusters = group_identical(labeled)

    plan = []
    local_freed = 0
    for _key, ids in sorted(clusters.items(), key=lambda kv: sorted(kv[1])[0]):
        members = [by_id[i] for i in sorted(ids)]
        canonical = choose_canonical(members, prefer_linked)
        victims = [m for m in members if m["id"] != canonical["id"]]
        linked_victims = [v["id"] for v in victims if v["linked"]]
        local_count = len(victims) - len(linked_victims)
        local_freed += local_count
        kind = canonical["kind"]
        total_users = sum(m.get("users", 0) for m in members)
        plan.append({
            "kind": kind,
            "canonical": canonical["id"],
            "victims": [v["id"] for v in victims],
            "linked_victims": linked_victims,
        })
        tail = f", frees {local_count} local datablock(s)"
        if linked_victims:
            tail += f" ({len(linked_victims)} linked stay in library)"
        report.add(Finding(
            category="instanceable",
            message=(
                f"{len(members)} identical {kind} datablocks ({total_users} object use(s)) → "
                f"instance onto '{canonical['id']}'{tail}"
            ),
            severity="warning",
            items=[canonical["id"]] + [v["id"] for v in victims],
            data={"canonical": canonical["id"], "victims": [v["id"] for v in victims], "kind": kind},
        ))

    report.add(Finding(
        category="summary",
        message=f"{len(clusters)} duplicate-geometry group(s); "
                f"{local_freed} datablock(s) can be instanced away",
        severity="warning" if clusters else "info",
        data={"groups": len(clusters), "freed": local_freed},
    ))
    return report, plan
