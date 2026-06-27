"""Unit tests for core.collection_mirror -- the Flatten v2 "Make Copy"
collection-mirroring path math (bpy-free)."""

from core.collection_mirror import lowest_common_path, mirror_collection_paths, mirror_name

ROOT = "Scene Collection"


def test_mirror_name_appends_suffix():
    assert mirror_name("Collection.002") == "Collection.002_flattened"


def test_lowest_common_path_empty_input():
    assert lowest_common_path([]) == ()


def test_lowest_common_path_single_path_is_itself():
    p = (ROOT, "Collection.002")
    assert lowest_common_path([p]) == p


def test_lowest_common_path_disjoint_branches_collapses_to_root():
    """The worked example: Armature1 under Collection.002, Armature2 under
    Collection.004 -- nothing shared below Scene Collection itself."""
    a = (ROOT, "Collection.002")
    b = (ROOT, "Collection.004")
    assert lowest_common_path([a, b]) == (ROOT,)


def test_lowest_common_path_shared_deeper_collection():
    a = (ROOT, "Collection.002", "Collection.005")
    b = (ROOT, "Collection.002", "Collection.006")
    assert lowest_common_path([a, b]) == (ROOT, "Collection.002")


def test_mirror_collection_paths_worked_example():
    """Confirms the exact user-provided worked example: Armature1 in
    Scene Collection > Collection.002, Armature2 in Scene Collection >
    Collection.004 -- root mirror is the Scene Collection's own mirror
    (since that's the lowest common ancestor here), with two independent
    branches underneath, one per character's own collection."""
    a = (ROOT, "Collection.002")
    b = (ROOT, "Collection.004")
    ordered = mirror_collection_paths([a, b])
    assert ordered == [(ROOT,), a, b]


def test_mirror_collection_paths_shared_ancestor_deduped_not_duplicated():
    """Two characters sharing Collection.002 but in different
    sub-collections -- Collection.002's mirror must appear ONCE, not once
    per character."""
    a = (ROOT, "Collection.002", "Collection.005")
    b = (ROOT, "Collection.002", "Collection.006")
    ordered = mirror_collection_paths([a, b])
    assert ordered == [(ROOT, "Collection.002"), a, b]
    assert ordered.count((ROOT, "Collection.002")) == 1


def test_mirror_collection_paths_remote_character_is_root_only():
    """A remote-sourced character with no known local anchor is represented
    as just (ROOT,) -- it lands directly in the root mirror collection, no
    extra nested branch."""
    remote = (ROOT,)
    local = (ROOT, "Collection.002")
    ordered = mirror_collection_paths([remote, local])
    # Lowest common ancestor of (ROOT,) and (ROOT, "Collection.002") is (ROOT,).
    assert ordered == [(ROOT,), local]
    # The remote character's own leaf IS the root entry -- present, no extra path needed.
    assert remote in ordered


def test_mirror_collection_paths_every_objects_own_path_is_present():
    """Every object's own (possibly multi-level) path must be a real entry
    in the result, since that's how the caller finds its leaf mirror
    collection."""
    paths = [
        (ROOT, "Collection.002", "Collection.005"),
        (ROOT, "Collection.002", "Collection.006"),
        (ROOT,),
    ]
    ordered = mirror_collection_paths(paths)
    for p in paths:
        assert p in ordered


def test_mirror_collection_paths_parents_sort_before_children():
    """With only ONE object, its ancestor IS its own immediate parent -- no
    extra intermediate mirrors are created above it. Use two objects
    sharing a deeper ancestor so there's a real multi-level chain to check
    ordering on."""
    paths = [(ROOT, "Collection.002", "Collection.005"),
             (ROOT, "Collection.002", "Collection.006")]
    ordered = mirror_collection_paths(paths)
    assert ordered.index((ROOT, "Collection.002")) < ordered.index(
        (ROOT, "Collection.002", "Collection.005"))
    assert ordered.index((ROOT, "Collection.002")) < ordered.index(
        (ROOT, "Collection.002", "Collection.006"))
