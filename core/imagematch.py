"""Fuzzy / synonym matching for relinking RENAMED textures (F6 step 4 / B2).

Exact-basename relink (Layer 1 / B1) fails when a texture vendor changes the
naming convention: the .blend wants ``WoodplanksNaturalStained007_2K_ao.png`` but
the file on disk is ``WoodplanksNaturalStained007_AO_2K_METALNESS.png`` — the same
texture under a new name. This module scores a candidate filename against a wanted
one by breaking BOTH into tokens (split on ``_ . -`` and whitespace) and comparing:

  stem tokens   the material/asset identity (``WoodplanksNaturalStained007``).
                These must match — and a token that is the same word with a
                DIFFERENT trailing number is a hard CONFLICT, so ``Beard18`` never
                matches ``Beard19`` and ``Base1``/``Base2``/``Base12`` stay distinct
                (the numbers are identity, not a strippable variant).
  channel       the PBR map type, matched through a synonym table so
                ``AO == AmbientOcclusion``, ``DISP == DISPLACEMENT``,
                ``COL == COLOR == COLOR1 == DIFFUSE``, etc. A file's channel is its
                FIRST channel-token in order, so a trailing workflow suffix like
                ``…_2K_METALNESS`` on a COLOR map doesn't make it look metallic.
  resolution    ``1K``/``2K``/``4K``… — a mismatch is allowed but lowers confidence
                and is flagged (relinking 2K→1K changes the texture).

bpy-free and unit-tested. The operator feeds candidate filenames from a chosen
folder; :func:`best_match` returns the best staged target (with a confidence band)
for the user to review — it never applies anything itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# canonical channel -> alias tokens (all lowercase). Extend freely; unknown tokens
# are treated as stem (identity) tokens, which is the safe default.
_CHANNEL_ALIASES: dict[str, set[str]] = {
    "color": {"col", "color", "colour", "diffuse", "diff", "albedo", "basecolor",
              "base", "col1", "color1", "diffuse1", "diffuse2", "color2", "col2"},
    "normal": {"nrm", "normal", "nor", "norm", "normalgl", "normaldx", "nml", "nmap"},
    "roughness": {"rough", "roughness", "rgh", "roughness1"},
    "metallic": {"metal", "metallic", "metalness", "mtl", "metalness1", "metalic"},
    "ao": {"ao", "ambientocclusion", "ambient", "occlusion", "occ", "ambient_occlusion"},
    "displacement": {"disp", "displacement", "displace", "height", "heightmap"},
    "bump": {"bump", "bmp"},
    "gloss": {"gloss", "glossy", "glossiness", "gls"},
    "specular": {"spec", "specular", "specularity", "specularlevel"},
    "emission": {"emit", "emission", "emissive", "glow"},
    "opacity": {"opacity", "alpha", "mask", "transmission"},
    # NB: "transparency" is intentionally NOT an alias — in this asset set it is a
    # material/family name token (Beard19_Transparency), not a per-file channel.
}
_ALIAS_TO_CHANNEL = {alias: chan for chan, al in _CHANNEL_ALIASES.items() for alias in al}

# Resolution tokens: "1k".."16k", or a bare power-of-two-ish pixel size.
_RES_RE = re.compile(r"^\d{1,2}k$")
_RES_PIXELS = {"256", "512", "1024", "2048", "4096", "8192"}
_SPLIT_RE = re.compile(r"[^a-z0-9]+")
_WORDNUM_RE = re.compile(r"^([a-z][a-z]*?)(\d+)$")  # "beard19" -> ("beard","19")


def tokenize(name: str) -> list[str]:
    """Lowercase tokens of a filename, extension dropped, split on non-alphanumerics."""
    stem = name.rsplit(".", 1)[0] if "." in name else name
    # keep a real extension out, but a "Stained007" stays whole (split is on _.- only
    # for the dot — we already removed the trailing extension above).
    return [t for t in _SPLIT_RE.split(stem.lower()) if t]


def _is_resolution(token: str) -> bool:
    return bool(_RES_RE.match(token)) or token in _RES_PIXELS


@dataclass(frozen=True)
class NameParts:
    stems: frozenset[str]   # identity tokens
    channel: str | None     # canonical PBR channel (first channel token wins)
    res: str | None         # resolution token, normalized (e.g. "2k")
    tokens: tuple[str, ...]  # raw token order (for debugging)


def classify(name: str) -> NameParts:
    """Break a filename into (stem tokens, primary channel, resolution)."""
    stems: list[str] = []
    channel: str | None = None
    res: str | None = None
    toks = tokenize(name)
    for t in toks:
        if _is_resolution(t):
            res = res or t
        elif t in _ALIAS_TO_CHANNEL:
            channel = channel or _ALIAS_TO_CHANNEL[t]  # FIRST channel token wins
        else:
            stems.append(t)
    return NameParts(frozenset(stems), channel, res, tuple(toks))


def _numbered_conflict(a: frozenset[str], b: frozenset[str]) -> bool:
    """True if a stem word appears with the SAME letters but a DIFFERENT trailing
    number in each set (Beard18 vs Beard19, Base1 vs Base12) — different variants,
    so they must not match."""
    amap: dict[str, set[str]] = {}
    for t in a:
        m = _WORDNUM_RE.match(t)
        if m:
            amap.setdefault(m.group(1), set()).add(m.group(2))
    for t in b:
        m = _WORDNUM_RE.match(t)
        if m and m.group(1) in amap and m.group(2) not in amap[m.group(1)]:
            return True
    return False


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def name_affinity(name: str, other: str) -> float:
    """Token-overlap (Jaccard) between two filenames/datablock names, 0..1. Used to
    attribute a texture to the material whose NAME best matches it: among the
    materials that reference an image, the highest-affinity one wins, so a
    ``…_lightBlue_…`` texture groups under a lightBlue material rather than whichever
    material happened to be walked first."""
    return _jaccard(frozenset(tokenize(name)), frozenset(tokenize(other)))


@dataclass(frozen=True)
class Match:
    candidate: str
    score: float
    confidence: str       # "high" | "medium" | "low"
    res_mismatch: bool    # candidate resolves to a different resolution
    channel_ok: bool      # channels agree (or both absent)


_STEM_FLOOR = 0.5  # below this stem similarity, not a candidate


def score_match(wanted: str, candidate: str) -> Match | None:
    """Score ``candidate`` as a stand-in for the missing ``wanted`` file, or None if
    it is disqualified (numbered-variant conflict, wrong channel, or too dissimilar)."""
    w, c = classify(wanted), classify(candidate)
    if _numbered_conflict(w.stems, c.stems):
        return None  # Beard18 vs Beard19 etc.
    if w.channel and c.channel and w.channel != c.channel:
        return None  # a roughness map can't stand in for a normal map
    stem_sim = _jaccard(w.stems, c.stems)
    if stem_sim < _STEM_FLOOR:
        return None

    chan_match = bool(w.channel and c.channel and w.channel == c.channel)
    both_no_channel = not w.channel and not c.channel
    channel_ok = chan_match or both_no_channel

    score = 0.6 * stem_sim
    if chan_match:
        score += 0.3
    elif both_no_channel:
        score += 0.1
    res_mismatch = bool(w.res and c.res and w.res != c.res)
    if w.res and c.res and w.res == c.res:
        score += 0.1
    elif res_mismatch:
        score -= 0.15

    if stem_sim >= 0.999 and chan_match and not res_mismatch:
        confidence = "high"
    elif stem_sim >= 0.6 and channel_ok:
        confidence = "medium"
    else:
        confidence = "low"
    return Match(candidate, round(score, 4), confidence, res_mismatch, channel_ok)


def best_match(wanted: str, candidates: list[str]) -> Match | None:
    """The single best candidate filename for ``wanted`` (highest score), or None.
    ``candidates`` are basenames found in the search folder."""
    best: Match | None = None
    for cand in candidates:
        m = score_match(wanted, cand)
        if m is None:
            continue
        if best is None or m.score > best.score:
            best = m
    return best


_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def propose_matches(
    wanted: list[str], candidates: list[str], *, min_confidence: str = "low",
) -> dict[str, Match]:
    """``{wanted basename: best Match}`` for each wanted filename that has a
    qualifying fuzzy candidate at or above ``min_confidence``. Names with no
    candidate (or only below-floor ones) are omitted. The caller maps each
    ``Match.candidate`` basename back to a real path and stages it for review —
    nothing here applies anything. This is the fuzzy FALLBACK for the textures
    that exact-basename search (Layer 1 / B1) could not place."""
    floor = _CONFIDENCE_RANK.get(min_confidence, 0)
    out: dict[str, Match] = {}
    for w in wanted:
        m = best_match(w, candidates)
        if m is not None and _CONFIDENCE_RANK.get(m.confidence, 0) >= floor:
            out[w] = m
    return out


def propose_from_paths(
    wanted: list[str], candidate_paths: list[str], *, min_confidence: str = "low",
) -> dict[str, tuple[str, Match]]:
    """Like :func:`propose_matches`, but candidates are full file PATHS (from a folder
    walk, another .blend, or a source material's textures). Returns
    ``{wanted basename: (candidate path, Match)}`` — the chosen candidate basename is
    already resolved back to its real path so the caller can stage it directly. When
    several candidate paths share a basename, the first one wins."""
    import os

    name_to_path: dict[str, str] = {}
    for p in candidate_paths:
        base = os.path.basename(p.replace("\\", "/"))
        if base:
            name_to_path.setdefault(base, p)
    proposals = propose_matches(wanted, list(name_to_path), min_confidence=min_confidence)
    return {w: (name_to_path[m.candidate], m) for w, m in proposals.items()}
