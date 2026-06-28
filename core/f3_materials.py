"""F3 analysis: cluster duplicate / multi-res materials and decide a canonical
survivor per white/black list. bpy-free; ops supplies material info dicts and
executes the resulting plan with ``user_remap`` + purge.

material info dict contract (from ops):
    { "id": "Wood [libA]",   # unique, human-readable key (name + library)
      "name": "Wood",        # the bare datablock name, matched against the lists
      "fingerprint": str | None,
      "linked": bool,
      "max_res": int }       # largest texture dimension, for the tie-break

Canonical selection order:
    1. a whitelisted member (always keep)        -> never a blacklisted one
    2. else any non-blacklisted member
    3. else (all blacklisted) keep the best available, with a note
    Within the chosen pool: prefer local over linked, then highest max_res,
    then name (stable).
"""

from __future__ import annotations

import fnmatch

from .cluster import group_identical
from .report import Finding, Report


def parse_name_list(text: str) -> list[str]:
    """Split a comma/semicolon/newline separated list of names/globs."""
    if not text:
        return []
    norm = text.replace(";", ",").replace("\n", ",")
    return [c.strip() for c in norm.split(",") if c.strip()]


def _matches(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def _rank_key(m: dict, prefer_linked: bool = False):
    # local before linked by default (False<True); flipped when the user
    # prefers linked (docs/TODO.md #21, 2026-06-27). Higher res first, then
    # stable by name either way.
    linked_first = (not m["linked"]) if prefer_linked else m["linked"]
    return (linked_first, -m.get("max_res", 0), m["name"])


def choose_canonical(members: list[dict], whitelist: list[str], blacklist: list[str],
                     prefer_linked: bool = False):
    """Pick the canonical member of a duplicate cluster. Returns (member, reason).
    ``prefer_linked`` only affects the LOCAL/LINKED tie-break — whitelist/
    blacklist still take precedence, same as before."""
    whitelisted = [m for m in members if _matches(m["name"], whitelist)]
    non_black = [m for m in members if not _matches(m["name"], blacklist)]

    if whitelisted:
        pool, reason = whitelisted, "whitelisted"
    elif non_black:
        pool, reason = non_black, None
    else:
        pool, reason = members, "all blacklisted — kept best available"

    best = sorted(pool, key=lambda m: _rank_key(m, prefer_linked))[0]
    if reason is None:
        reason = (
            f"highest resolution ({best['max_res']})" if best.get("max_res") else "first by name"
        )
    return best, reason


def build_dedup_plan(items: list[dict], whitelist=(), blacklist=(), prefer_linked: bool = False):
    """Return (Report, plan). plan is a list of
    {fingerprint, canonical: id, victims: [id], linked_victims: [id]}."""
    report = Report(title="Material duplicates", feature="F3")
    by_id = {it["id"]: it for it in items}
    clusters = group_identical(
        sorted((it["id"], it["fingerprint"]) for it in items if it["fingerprint"])
    )

    plan = []
    local_victims: list[str] = []   # duplicate materials that will be removed
    linked_victims: list[str] = []  # duplicate materials that stay in their library
    for fp, ids in sorted(clusters.items(), key=lambda kv: sorted(kv[1])[0]):
        members = [by_id[i] for i in sorted(ids)]
        canonical, reason = choose_canonical(members, list(whitelist), list(blacklist), prefer_linked)
        victims = [m for m in members if m["id"] != canonical["id"]]
        grp_linked = [v["id"] for v in victims if v["linked"]]
        plan.append({
            "fingerprint": fp,
            "canonical": canonical["id"],
            "victims": [v["id"] for v in victims],
            "linked_victims": grp_linked,
        })
        for v in victims:
            (linked_victims if v["linked"] else local_victims).append(v["id"])

    local_victims.sort()
    linked_victims.sort()
    n_local, n_linked = len(local_victims), len(linked_victims)
    total = n_local + n_linked

    # Headline on the category row: "XX (YY Local & ZZ Linked)".
    report.category_details["duplicate_material"] = (
        f"{total} ({n_local} Local & {n_linked} Linked)"
    )
    if total == 0:
        report.add(Finding(category="duplicate_material",
                           message="No duplicate materials found", severity="info"))
        return report, plan
    if local_victims:
        report.add(Finding(
            category="duplicate_material", message="Local", severity="warning",
            detail=str(n_local), items=local_victims,
            data={"kind": "local", "count": n_local},
        ))
    if linked_victims:
        report.add(Finding(
            category="duplicate_material",
            message="Linked (stay in their library; only local users are remapped)",
            severity="info", detail=str(n_linked), items=linked_victims,
            data={"kind": "linked", "count": n_linked},
        ))
    return report, plan
