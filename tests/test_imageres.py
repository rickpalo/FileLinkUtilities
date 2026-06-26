"""Unit tests for F6 Layer 2 resolution-variant detection (core.imageres)."""

from core import imageres


def test_two_resolutions_of_one_texture_is_a_variant():
    names = ["Wood_2K_col.png", "Wood_1K_col.png"]
    variants = imageres.plan_res_variants(names)
    assert len(variants) == 1
    res = sorted({r for _n, r in variants[0].members})
    assert res == ["1k", "2k"]


def test_single_resolution_is_not_a_variant():
    assert imageres.plan_res_variants(["Wood_2K_col.png", "Stone_2K_col.png"]) == []


def test_names_without_resolution_token_ignored():
    assert imageres.plan_res_variants(["Wood_col.png", "Wood_diffuse.png"]) == []


def test_nnn_suffix_does_not_split_a_variant_set():
    # Leather_2K + Leather_1K + a .001 lossless copy of the 2K -> still ONE variant
    # set keyed by stems+channel (the .001 is stripped before grouping).
    names = ["Leather_2K_col.png", "Leather_2K_col.png.001", "Leather_1K_col.png"]
    variants = imageres.plan_res_variants(names)
    assert len(variants) == 1
    assert sorted({r for _n, r in variants[0].members}) == ["1k", "2k"]


def test_different_channels_are_separate_sets():
    names = ["Wood_2K_col.png", "Wood_1K_col.png",
             "Wood_2K_nrm.png", "Wood_1K_nrm.png"]
    variants = imageres.plan_res_variants(names)
    assert len(variants) == 2  # one per channel


# --- res_value / highest_member / lowest_member (item 11, 2026-06-25) -------

def test_res_value_orders_k_tokens():
    assert imageres.res_value("1k") < imageres.res_value("2k") < imageres.res_value("4k")


def test_res_value_handles_pixel_tokens():
    assert imageres.res_value("2048") == 2048
    assert imageres.res_value("512") < imageres.res_value("2048")


def test_res_value_unrecognized_is_zero():
    assert imageres.res_value("huge") == 0


def test_highest_and_lowest_member():
    variants = imageres.plan_res_variants(
        ["Wood_1K_col.png", "Wood_2K_col.png", "Wood_4K_col.png"])
    v = variants[0]
    assert imageres.highest_member(v) == "Wood_4K_col.png"
    assert imageres.lowest_member(v) == "Wood_1K_col.png"


def test_report_clean_and_populated():
    assert imageres.build_res_report([]).findings[0].category == "clean"
    variants = imageres.plan_res_variants(["Wood_2K_col.png", "Wood_1K_col.png"])
    report = imageres.build_res_report(variants, "scene.blend")
    cats = [f.category for f in report.findings]
    assert cats == ["res_variant", "overview"]
    assert report.feature == "f6res"
