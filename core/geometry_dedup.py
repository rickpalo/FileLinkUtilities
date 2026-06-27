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


def choose_canonical(members: list[dict]) -> dict:
    """Keep the most-shared local datablock (so existing instances are preserved)."""
    return sorted(members, key=lambda m: (m["linked"], -m.get("users", 0), m["name"]))[0]


def removable_count(plan: list[dict]) -> int:
    """Total mesh datablocks the plan would remove (sum of victims per group)."""
    return sum(len(group["victims"]) for group in plan)


def build_instance_plan(items: list[dict]):
    """Return (Report, plan). plan entries: {kind, canonical: id, victims: [id]}."""
    report = Report(title="Instanceable duplicate geometry", feature="F5")
    by_id = {it["id"]: it for it in items}
    labeled = sorted(
        (it["id"], f"{it['kind']}|{it['fingerprint']}")
        for it in items
        if it.get("fingerprint") and not it["linked"]
    )
    clusters = group_identical(labeled)

    plan = []
    freed = 0
    for _key, ids in sorted(clusters.items(), key=lambda kv: sorted(kv[1])[0]):
        members = [by_id[i] for i in sorted(ids)]
        canonical = choose_canonical(members)
        victims = [m for m in members if m["id"] != canonical["id"]]
        freed += len(victims)
        kind = canonical["kind"]
        total_users = sum(m.get("users", 0) for m in members)
        plan.append({
            "kind": kind,
            "canonical": canonical["id"],
            "victims": [v["id"] for v in victims],
        })
        report.add(Finding(
            category="instanceable",
            message=(
                f"{len(members)} identical {kind} datablocks ({total_users} object use(s)) → "
                f"instance onto '{canonical['id']}', frees {len(victims)} datablock(s)"
            ),
            severity="warning",
            items=[canonical["id"]] + [v["id"] for v in victims],
            data={"canonical": canonical["id"], "victims": [v["id"] for v in victims], "kind": kind},
        ))

    report.add(Finding(
        category="summary",
        message=f"{len(clusters)} duplicate-geometry group(s); {freed} datablock(s) can be instanced away",
        severity="warning" if clusters else "info",
        data={"groups": len(clusters), "freed": freed},
    ))
    return report, plan
