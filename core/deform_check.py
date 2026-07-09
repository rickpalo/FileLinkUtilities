"""Detect armature-deformation vertex explosions (bpy-free scoring; the ops
layer extracts rest/deformed edge-length data and hands it here).

Real bug found live, 2026-07-09 (`ThePiazzaSanMarco - People.blend`,
`Canaletto_XX_blackHairBrownCloak`'s `shirt.003`): a mesh vertex weighted to a
non-deform bone (in this case Reallusion/CC facial rig CTRL_ bones, likely
picked up by an indiscriminate weight-TRANSFER from the body mesh when the
garment was fitted) gets pinned to that bone's pose-space position instead of
following the body — the vertex's REST-pose position is perfectly normal, so
this is invisible to any purely-rest-pose geometry check; it only shows up
once the Armature modifier actually deforms the mesh. Confirmed live: rest
edges normal, deformed edges up to ~84,000x their rest length on the same
mesh, while the median ratio across the whole mesh stayed ~1.57x (i.e. a
handful of vertices are catastrophically wrong while the mesh as a whole
deforms completely normally).

Detection only for now (user's explicit call, 2026-07-09) — this module never
mutates anything; it just flags candidates for a human (or a later fix pass)
to review.
"""

from __future__ import annotations

from dataclasses import dataclass

from .report import Finding, Report

# Well above anything seen on a healthy mesh in practice (the worst edge on a
# normal, unbroken cloth mesh checked this session topped out around 5-6x) and
# far below a genuinely exploded vertex (tens of thousands x, observed live) —
# a wide margin on both sides, so this isn't a knife-edge threshold pick.
DEFAULT_RATIO_THRESHOLD = 20.0


@dataclass(frozen=True)
class DeformIssue:
    """One flagged vertex: its worst (highest-ratio) deformed/rest edge."""

    vertex_id: int
    ratio: float
    rest_length: float
    deformed_length: float


def find_deform_outliers(
    edges: list[tuple[int, int]],
    rest_lengths: list[float],
    deformed_lengths: list[float],
    ratio_threshold: float = DEFAULT_RATIO_THRESHOLD,
) -> list[DeformIssue]:
    """One :class:`DeformIssue` per VERTEX that is an endpoint of at least one
    edge whose ``deformed_length / rest_length`` ratio exceeds
    ``ratio_threshold`` — keeps the vertex's single worst edge. ``edges``,
    ``rest_lengths`` and ``deformed_lengths`` are parallel sequences (same
    length and order, one entry per mesh edge) so this stays bpy-free and
    trivially testable with synthetic data. Sorted worst-first."""
    best: dict[int, DeformIssue] = {}
    for (v1, v2), rest_len, deformed_len in zip(edges, rest_lengths, deformed_lengths):
        if rest_len <= 1e-9:
            continue
        ratio = deformed_len / rest_len
        if ratio < ratio_threshold:
            continue
        for vid in (v1, v2):
            cur = best.get(vid)
            if cur is None or ratio > cur.ratio:
                best[vid] = DeformIssue(vid, ratio, rest_len, deformed_len)
    return sorted(best.values(), key=lambda d: -d.ratio)


@dataclass(frozen=True)
class ObjectDeformSummary:
    """One mesh object's flagged vertices, plus enough context to act on it
    later (object/armature names — the actual fix, when built, will need to
    inspect the target armature's bones again, which needs live bpy data this
    module deliberately doesn't touch)."""

    object_name: str
    mesh_name: str
    armature_name: str
    issues: tuple[DeformIssue, ...]
    # Whether the vertex-group weight data a fix would need to edit is local to
    # THIS file (False if the object or its mesh is linked from another .blend
    # — Blender can't modify linked datablocks in place, so a fix would have to
    # happen at the source file instead, same "fix at source" distinction this
    # addon already makes for linked missing textures). Detection works
    # identically either way; this only matters once a fix exists.
    is_locally_fixable: bool = True

    @property
    def worst_ratio(self) -> float:
        return self.issues[0].ratio if self.issues else 0.0

    @property
    def count(self) -> int:
        return len(self.issues)


def build_deform_check_report(summaries: list[ObjectDeformSummary]) -> Report:
    """One Finding per flagged object, worst-ratio-first, for the shared
    Report/headline machinery (Analyze row summary, Reports tab) — the
    per-vertex detail and the actual selection checkboxes live in the ops
    layer's own picker-row collection, not in this report (same split as
    Missing Textures: a Report for the headline, a separate live
    CollectionProperty for interactive selection)."""
    ordered = sorted(summaries, key=lambda s: -s.worst_ratio)
    findings = [
        Finding(
            category="deform_outlier",
            severity="warning",
            message=(f"{s.object_name}: {s.count} vertex(es) flagged, worst edge "
                     f"{s.worst_ratio:.1f}x its rest length (armature "
                     f"'{s.armature_name}')"
                     + ("" if s.is_locally_fixable else " — LINKED, fix at source")),
            items=[f"Object/{s.object_name}"],
            detail=f"{s.worst_ratio:.0f}x",
        )
        for s in ordered
    ]
    if not findings:
        findings = [Finding(category="clean", severity="info",
                            message="✓ no armature-deformation outliers found")]
    return Report(title="Armature Deformation Check", feature="DEFORMCHECK", findings=findings)


__all__ = ["DeformIssue", "ObjectDeformSummary", "find_deform_outliers",
           "build_deform_check_report", "DEFAULT_RATIO_THRESHOLD"]
