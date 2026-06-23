"""F6 Layer 2 — resolution-variant detection (footprint pillar, REPORT-ONLY/LOSSY).

A texture present at several resolutions (``Wood_1k`` vs ``Wood_2k``) is NOT a
duplicate: the files differ, and "combining" them = standardizing to one chosen
resolution, which CHANGES the render. So this is footprint analysis, not a lossless
merge — report-only for now. It surfaces which textures exist at more than one
resolution so the user can decide whether to downscale (a later, opt-in apply).

Grouping reuses :func:`core.imagematch.classify` to split a name into stems +
channel + resolution: two images with the SAME stems and channel but DIFFERENT
resolution tokens are variants of one texture. ``.NNN`` suffixes are stripped first
(those are the lossless-merge job, not a resolution difference).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .datablock_graph import strip_dup_suffix
from .imagematch import classify
from .report import Finding, Report


@dataclass
class ResVariant:
    """One texture that exists at multiple resolutions: a display ``key`` (its
    stems + channel) and the members as ``(name, resolution token)`` pairs."""

    key: str
    members: list[tuple[str, str]] = field(default_factory=list)


def plan_res_variants(names: list[str]) -> list[ResVariant]:
    """Texture sets present at 2+ distinct resolutions. Groups by (stems, channel)
    ignoring the resolution token and any ``.NNN`` suffix; a group with more than one
    resolution is a variant set. Names without a resolution token are skipped."""
    groups: dict[tuple, dict[str, list[str]]] = {}
    for n in names:
        p = classify(strip_dup_suffix(n))
        if p.res is None:
            continue  # no resolution token -> can't be a resolution variant
        groups.setdefault((p.stems, p.channel), {}).setdefault(p.res, []).append(n)
    out: list[ResVariant] = []
    for (stems, channel), by_res in groups.items():
        if len(by_res) < 2:
            continue  # single resolution -> not a variant set
        members = [(n, res) for res in sorted(by_res) for n in sorted(by_res[res])]
        disp = " ".join(sorted(stems)) + (f" [{channel}]" if channel else "")
        out.append(ResVariant(key=disp.strip() or "(unnamed)", members=members))
    return sorted(out, key=lambda v: v.key.lower())


def build_res_report(variants: list[ResVariant], blend_name: str = "current file") -> Report:
    """Report the multi-resolution texture sets (info); empty -> a ✓ clean finding."""
    report = Report(title=f"Resolution variants: {blend_name}", feature="f6res")
    if not variants:
        report.add(Finding(category="clean",
                           message="✓ No multi-resolution texture variants found",
                           severity="info"))
        return report
    for v in variants:
        res_list = sorted({r for _n, r in v.members})
        report.add(Finding(category="res_variant",
                           message=f"{v.key}: {', '.join(res_list)}",
                           severity="info", items=[n for n, _r in v.members],
                           detail=f"{len(res_list)} res"))
    report.add(Finding(category="summary",
                       message=f"{len(variants)} texture(s) exist at multiple resolutions — "
                               "standardizing is lossy (footprint, opt-in)",
                       severity="info"))
    return report


__all__ = ["ResVariant", "plan_res_variants", "build_res_report"]
