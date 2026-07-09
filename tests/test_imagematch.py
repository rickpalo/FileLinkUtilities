"""Unit tests for core.imagematch — fuzzy/synonym texture-rename matching.

Driven by the real renamed-texture cases the user hit (Woodplanks PBR set, Beard
variants) so the matcher provably handles them."""

from core import imagematch as im

# The on-disk Woodplanks set (vendor renamed; trailing _METALNESS workflow suffix).
WOODPLANKS_DISK = [
    "WoodplanksNaturalStained007_COL_2K_METALNESS.png",
    "WoodplanksNaturalStained007_AO_2K_METALNESS.png",
    "WoodplanksNaturalStained007_DISP16_2K_METALNESS.png",
    "WoodplanksNaturalStained007_METALNESS_2K_METALNESS.png",
    "WoodplanksNaturalStained007_NRM_2K_METALNESS.png",
    "WoodplanksNaturalStained007_ROUGHNESS_2K_METALNESS.png",
    "WoodplanksNaturalStained007_Preview1.png",
]


def test_woodplanks_renamed_channels_match_correctly():
    cases = {
        "WoodplanksNaturalStained007_2K_ao.png": "WoodplanksNaturalStained007_AO_2K_METALNESS.png",
        "WoodplanksNaturalStained007_2K_metallic.png": "WoodplanksNaturalStained007_METALNESS_2K_METALNESS.png",
        "WoodplanksNaturalStained007_2K_roughness.png": "WoodplanksNaturalStained007_ROUGHNESS_2K_METALNESS.png",
    }
    for wanted, expect in cases.items():
        m = im.best_match(wanted, WOODPLANKS_DISK)
        assert m is not None, wanted
        assert m.candidate == expect, f"{wanted} -> {m.candidate}, expected {expect}"
        assert m.confidence == "high"


def test_color_workflow_suffix_does_not_look_metallic():
    """COL_2K_METALNESS is the COLOR map (first channel token wins) — the trailing
    _METALNESS workflow suffix must not match it to a wanted metallic map."""
    m = im.best_match("WoodplanksNaturalStained007_2K_metallic.png", WOODPLANKS_DISK)
    assert m.candidate == "WoodplanksNaturalStained007_METALNESS_2K_METALNESS.png"
    # and the COLOR file is the match for a wanted color map
    mc = im.best_match("WoodplanksNaturalStained007_2K_col.png", WOODPLANKS_DISK)
    assert mc.candidate == "WoodplanksNaturalStained007_COL_2K_METALNESS.png"


def test_beard18_never_matches_beard19():
    """The trailing number is identity, not a strippable variant."""
    cands = ["Beard18_Transparency_2K_col.png", "Beard19_Transparency_2K_color.png"]
    m = im.best_match("Beard19_Transparency_2K_diffuse.png", cands)
    assert m is not None
    assert m.candidate == "Beard19_Transparency_2K_color.png"
    # Beard18 alone must be rejected outright (not just ranked lower)
    assert im.score_match("Beard19_Transparency_2K_diffuse.png",
                          "Beard18_Transparency_2K_col.png") is None


def test_numbered_variants_stay_distinct():
    assert im.score_match("Brows_Base1_2K_col.png", "Brows_Base12_2K_col.png") is None
    assert im.score_match("Brows_Base2_2K_col.png", "Brows_Base1_2K_col.png") is None
    # same number -> fine
    assert im.score_match("Brows_Base12_2K_col.png", "Brows_Base12_2K_color.png") is not None


def test_channel_synonyms():
    assert im.classify("x_DISP_2K.png").channel == "displacement"
    assert im.classify("x_DISPLACEMENT_2K.png").channel == "displacement"
    assert im.classify("x_AmbientOcclusion.png").channel == "ao"
    assert im.classify("x_AO.png").channel == "ao"
    for tok in ("COL", "COLOR", "COLOR1", "DIFFUSE", "Albedo", "BaseColor"):
        assert im.classify(f"mat_{tok}_2K.png").channel == "color", tok


def test_channel_synonyms_from_real_library_naming():
    """Words actually found scanning the CC/HumGen/general texture libraries —
    not previously recognized, so they were dragging down stem similarity as
    stray stem tokens (see the "_png" pseudo-extension bug this mirrors)."""
    cases = {
        "x_REFL_2K.png": "specular",       # older CC/iClone "reflection" naming
        "x_HSpecMap.png": "specular",
        "x_DISP16_2K.png": "displacement",  # CC's 16-bit-map suffix
        "x_BUMP16_2K.png": "bump",
        "x_NRM16_2K.png": "normal",
        "x_MicroNMask.png": "normal",
        "x_CavityMap.png": "ao",
        "x_GradAO.png": "ao",
        "x_TransMap.png": "opacity",
        "x_SSSMap.png": "sss",
        "x_VertexColorMap.png": "vertexcolor",
        "x_WeightMap.png": "weight",
    }
    for name, expected in cases.items():
        assert im.classify(name).channel == expected, name


def test_orm_pack_is_its_own_channel_not_interchangeable():
    # An ORM (Occlusion/Roughness/Metallic) pack is a genuinely different image
    # from a standalone roughness map — must not stand in for one, or vice versa.
    assert im.classify("wood_2K_orm.png").channel == "orm"
    assert im.score_match("wood_2K_roughness.png", "wood_2K_orm.png") is None


def test_wrong_channel_is_disqualified():
    # a normal map can't stand in for a roughness map even with identical stem
    assert im.score_match("wood_2K_roughness.png", "wood_2K_normal.png") is None


def test_resolution_mismatch_flagged_not_blocked():
    m = im.score_match("wood_2K_ao.png", "wood_1K_ao.png")
    assert m is not None
    assert m.res_mismatch is True
    assert m.confidence != "high"  # res change lowers confidence


def test_transparency_is_a_stem_token_not_a_channel():
    parts = im.classify("Beard19_Transparency_2K_col.png")
    assert "transparency" in parts.stems
    assert parts.channel == "color"


def test_underscore_pseudo_extension_stripped_like_a_real_one():
    """Some FBX/vendor exports can't embed a literal '.' in a texture reference name
    and use "_png"/"_jpg" instead; Blender may then add its OWN real ".001" dedup
    suffix on top ("..._png.001"). Without stripping the pseudo-extension too, that
    lone "png" stem token (present in the wanted name but not the real file) drags
    an otherwise-perfect match down to "low"/"medium" instead of "high"."""
    wanted = "FabricVelvetEmbossed018_AO_1K_METALNESS_png.001"
    disk = "FabricVelvetEmbossed018_AO_1K_METALNESS.png"
    assert im.tokenize(wanted) == im.tokenize(disk)
    m = im.score_match(wanted, disk)
    assert m is not None
    assert m.confidence == "high"


def test_underscore_pseudo_extension_without_dedup_suffix():
    assert im.tokenize("CordRopeJute001_REFL_2K_png") == im.tokenize("CordRopeJute001_REFL_2K.png")


def test_dot_joined_double_extension_stripped_like_underscore_form():
    """Real bug found live, 2026-07-09 (FabricRope001): Blender's OWN ordinary
    dedup-on-collision naming appends ".NNN" to whatever datablock name was
    requested, even when that name already looks like it has a real extension
    baked in ("FabricRope001_AO_1K.jpg" + a collision -> "...1K.jpg.002"). The
    real-extension strip only removes the LAST ".NNN", leaving a redundant
    ".jpg" in the stem -- same failure shape as the underscore pseudo-extension
    case above, just dot-separated instead of underscore-separated."""
    wanted = "FabricRope001_AO_1K.jpg.002"
    disk = "FabricRope001_AO_1K.jpg"
    assert im.tokenize(wanted) == im.tokenize(disk)
    m = im.score_match(wanted, disk)
    assert m is not None
    assert m.confidence == "high"


def test_dot_joined_pseudo_extension_stem_has_no_stray_extension_token():
    """Directly checks the stray "jpg" stem token is gone, not just that the two
    tokenizations happen to match (test_dot_joined_double_extension_stripped_like_
    underscore_form above could pass even if BOTH sides kept a stray "jpg")."""
    assert "jpg" not in im.tokenize("FabricRope001_AO_1K.jpg.002")


# --- catalog ID (Poliigon-style 4+ digit vendor SKU) weighting, 2026-07-09 ---

def test_catalog_id_extracted_and_kept_in_stems_too():
    """Not pulled out of stems (unlike channel/res) -- it should still help
    ordinary Jaccard overlap AS WELL AS the dedicated bonus/conflict check."""
    parts = im.classify("Poliigon_MetalSteelBrushed_7174_1K_Normal.jpg")
    assert parts.catalog_id == "7174"
    assert "7174" in parts.stems


def test_three_digit_number_is_not_a_catalog_id():
    """Distinguish from ordinary per-item counters (VAR1/.001/etc) -- Poliigon's
    own IDs observed in this library are consistently 4 digits."""
    parts = im.classify("Something_001.png")
    assert parts.catalog_id is None


def test_resolution_pixel_count_not_misread_as_catalog_id():
    """'1024'/'2048'/etc are claimed by _is_resolution first in the classify()
    loop -- must never leak through as a catalog_id too."""
    parts = im.classify("Wood_1024_col.png")
    assert parts.res == "1024"
    assert parts.catalog_id is None


def test_shared_catalog_id_rescues_a_weak_name_match():
    """Real user request: a shared 4+ digit vendor SKU should be a PRIMARY match
    signal, strong enough to rescue a pair whose descriptive words differ too
    much to pass the ordinary stem floor on their own."""
    wanted = "Poliigon_MetalSteelBrushed_7174_1K_Normal.jpg"
    candidate = "MetalSteel_7174_NRM_1K.jpg"  # heavily abbreviated vendor name
    assert im.tokenize(wanted) != im.tokenize(candidate)  # genuinely weak by name alone
    m = im.score_match(wanted, candidate)
    assert m is not None
    assert m.confidence == "high"


def test_mismatched_catalog_id_disqualifies_even_with_identical_words():
    """Two different vendor SKUs must never be treated as the same texture, even
    when every OTHER word matches exactly -- the ID is the authoritative part."""
    wanted = "Poliigon_MetalSteelBrushed_7174_1K_Normal.jpg"
    candidate = "Poliigon_MetalSteelBrushed_9999_1K_Normal.jpg"
    assert im.score_match(wanted, candidate) is None


def test_mismatched_catalog_id_disqualifies_even_when_channel_and_res_agree():
    """Channel/res agreement alone must not paper over a genuine SKU conflict."""
    m = im.score_match("Poliigon_Foo_1111_2K_ao.jpg", "Poliigon_Bar_2222_2K_ao.jpg")
    assert m is None


def test_catalog_match_does_not_override_channel_conflict():
    """A shared SKU is identity evidence, not a license to ignore a hard physical
    fact like "a normal map can't stand in for a roughness map"."""
    wanted = "Poliigon_Foo_7174_2K_Normal.jpg"
    candidate = "Poliigon_Foo_7174_2K_Roughness.jpg"
    assert im.score_match(wanted, candidate) is None


def test_no_candidates_returns_none():
    assert im.best_match("wood_2K_ao.png", []) is None
    assert im.best_match("wood_2K_ao.png", ["totally_different_thing.png"]) is None


def test_best_match_skips_a_candidate_that_raises_instead_of_aborting(monkeypatch):
    """Real production bug, 2026-07-09: a TypeError deep in score_match (root
    cause never reproduced) took down an entire modal folder search, losing
    every match already staged. One bad (wanted, candidate) pair must not cost
    the rest of the batch -- best_match should skip it and keep scoring."""
    real_score_match = im.score_match

    def flaky_score_match(wanted, candidate):
        if candidate == "poison.png":
            raise TypeError("simulated unreproduced live failure")
        return real_score_match(wanted, candidate)

    monkeypatch.setattr(im, "score_match", flaky_score_match)
    candidates = ["poison.png", "WoodplanksNaturalStained007_AO_2K_METALNESS.png"]
    m = im.best_match("WoodplanksNaturalStained007_2K_ao.png", candidates)
    assert m is not None
    assert m.candidate == "WoodplanksNaturalStained007_AO_2K_METALNESS.png"


def test_propose_matches_only_returns_placeable_wanted():
    wanted = [
        "WoodplanksNaturalStained007_2K_ao.png",
        "WoodplanksNaturalStained007_2K_roughness.png",
        "SomethingElseEntirely_2K_col.png",  # nothing in the folder matches it
    ]
    out = im.propose_matches(wanted, WOODPLANKS_DISK)
    assert set(out) == {
        "WoodplanksNaturalStained007_2K_ao.png",
        "WoodplanksNaturalStained007_2K_roughness.png",
    }
    assert out["WoodplanksNaturalStained007_2K_ao.png"].candidate == \
        "WoodplanksNaturalStained007_AO_2K_METALNESS.png"


def test_name_affinity_picks_matching_variant_material():
    # The real FabricWool bug: a lightBlue texture must prefer the lightBlue material
    # over the brown one, not whichever was found first.
    img = "FabricWool001_2K_lightBlue_metallic.png"
    a = im.name_affinity(img, "FabricWool001_2K_lightBlue")
    b = im.name_affinity(img, "FabricWool001_2K_brown")
    c = im.name_affinity(img, "FabricFloralLaceWhite001_1k")
    assert a > b > c
    assert max(["FabricWool001_2K_brown", "FabricWool001_2K_lightBlue",
                "FabricFloralLaceWhite001_1k"],
               key=lambda m: im.name_affinity(img, m)) == "FabricWool001_2K_lightBlue"


def test_propose_matches_confidence_floor():
    # a res-mismatch candidate is medium/low confidence; the high floor drops it
    wanted = ["wood_2K_ao.png"]
    cands = ["wood_1K_ao.png"]
    assert "wood_2K_ao.png" in im.propose_matches(wanted, cands, min_confidence="low")
    assert im.propose_matches(wanted, cands, min_confidence="high") == {}


def test_propose_from_paths_resolves_to_real_path():
    wanted = ["Beard_COLOR.png"]
    paths = ["E:/lib/textures/Beard_COLOR.png", "E:/lib/textures/Beard_NORMAL.png"]
    out = im.propose_from_paths(wanted, paths)
    assert "Beard_COLOR.png" in out
    path, match = out["Beard_COLOR.png"]
    assert path == "E:/lib/textures/Beard_COLOR.png"
    assert match.candidate == "Beard_COLOR.png"


def test_propose_from_paths_first_path_wins_on_duplicate_basename():
    wanted = ["wood_COL.png"]
    paths = [r"A\wood_COL.png", "B/wood_COL.png"]
    path, _m = im.propose_from_paths(wanted, paths)["wood_COL.png"]
    assert path == r"A\wood_COL.png"


def test_propose_from_paths_respects_confidence_floor():
    wanted = ["wood_2K_ao.png"]
    paths = ["/lib/wood_1K_ao.png"]  # resolution mismatch -> not high confidence
    assert im.propose_from_paths(wanted, paths, min_confidence="high") == {}
    assert "wood_2K_ao.png" in im.propose_from_paths(wanted, paths, min_confidence="low")
