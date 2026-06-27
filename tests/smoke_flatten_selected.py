"""End-to-end "Flatten Selected" check in Blender (docs/TODO.md Group 11 #47):

    blender --background --factory-startup --python tests/smoke_flatten_selected.py

Two things confirmed by hand while building this (neither obvious going in):
(1) ``Object.library`` always attributes to a datablock's TRUE owning file,
even through several layers of indirection -- linking it via ANOTHER file's
collection never makes that other file its owner. (2) ``override_create()``
only succeeds on an object whose ``.library`` is a DIRECT dependency of the
CURRENT file; an object only reachable through another file's collection
can never be overridden directly. So building a REAL multi-file chain where
the override itself is also legitimately multi-hop is a much bigger
undertaking than it looks (this is also presumably WHY the real production
file has 0 local candidates -- PSM_Stage can't create one either).

That's a question about Blender's override system, already answered and not
what THIS test needs to re-prove -- the existing, real-production-validated
_flatten_rig mechanism already demonstrates multi-hop overrides work when
authored normally. This test instead isolates what's actually NEW here: a
real local override (built the simple, proven way -- direct link +
override_create, same as the very first probe this session) + a SYNTHETIC
f7chain report (core.linkchain.build_chain_report against a crafted
DepGraph, the same technique tests/test_linkchain.py already uses) that
classifies it as a multi-hop "ready" candidate. scan_flatten_candidates and
flatten_selected then run for real against that combination.
"""

import glob
import pathlib
import sys
import tempfile
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))
_bat = glob.glob(str(REPO_ROOT / "wheels" / "blender_asset_tracer-*.whl"))
if _bat:
    sys.path.insert(0, _bat[0])
PKG = REPO_ROOT.name


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()
    linkchain = __import__(f"{PKG}.core.linkchain", fromlist=["x"])
    store = __import__(f"{PKG}.ops.report_store", fromlist=["x"])

    tmp = pathlib.Path(tempfile.mkdtemp())
    ultimate_path = tmp / "ultimate.blend"
    root_path = tmp / "root.blend"

    checks = []
    try:
        # --- ultimate.blend: the real source objects. Char2 is deliberately
        # --- a DIFFERENT object type (Empty, not Mesh) so it lands in its
        # --- OWN type-group -- group selection is per-GROUP, not per-member,
        # --- so this is what lets the Make Local check below flatten Char2
        # --- on its own, separately from Char. -------------------------------
        bpy.ops.wm.read_factory_settings(use_empty=True)
        obj1 = bpy.data.objects.new("Char", bpy.data.meshes.new("CharMesh"))
        bpy.context.scene.collection.objects.link(obj1)
        obj2 = bpy.data.objects.new("Char2", None)
        bpy.context.scene.collection.objects.link(obj2)
        bpy.ops.wm.save_as_mainfile(filepath=str(ultimate_path))

        # --- root.blend: links both DIRECTLY from ultimate.blend (its OWN
        # --- dependency -- override_create's real requirement, confirmed by
        # --- hand) and overrides both for real. Char2 is held back for the
        # --- Make Local check, done as a SECOND flatten run further down. ---
        bpy.ops.wm.read_factory_settings(use_empty=True)
        with bpy.data.libraries.load(str(ultimate_path), link=True) as (data_from, data_to):
            data_to.objects = list(data_from.objects)
        char_coll = bpy.data.collections.new("CharColl")
        bpy.context.scene.collection.children.link(char_coll)
        for linked_obj in data_to.objects:
            char_coll.objects.link(linked_obj)
        bpy.context.view_layer.update()

        overrides = {}
        for nm in ("Char", "Char2"):
            ov = bpy.data.objects[nm].override_create()
            checks.append((f"override_create() succeeded on a direct link ({nm})", ov is not None))
            if ov is None:
                continue
            ov.location = (5.0, 5.0, 5.0)
            ov.override_library.properties.add("location")  # script edits don't auto-track; force it
            char_coll.objects.link(ov)  # override_create() doesn't auto-link it anywhere -- with
            # zero users it'd be silently dropped as an orphan on save/reload (confirmed by hand).
            overrides[nm] = ov
        if len(overrides) != 2:
            ok = all(p for _, p in checks)
            for label, p in checks:
                print(f"  [{'OK' if p else 'FAIL'}] {label}")
            print("FLATTEN_SELECTED_SMOKE_FAIL (setup assumption was wrong)")
            return 1
        bpy.ops.wm.save_as_mainfile(filepath=str(root_path))

        # --- open root.blend FOR REAL (not via libraries.load) --------------
        bpy.ops.wm.open_mainfile(filepath=str(root_path))
        wm = bpy.context.window_manager
        print(f"PROBE all objects after reopen: "
              f"{[(o.name, o.library, o.override_library is not None) for o in bpy.data.objects]}")
        char_in_root = next((o for o in bpy.data.objects if o.override_library is not None), None)
        checks.append(("Char (the override) is local once root.blend is opened normally",
                       char_in_root is not None))
        if char_in_root is None:
            ok = all(p for _, p in checks)
            for label, p in checks:
                print(f"  [{'OK' if p else 'FAIL'}] {label}")
            print("FLATTEN_SELECTED_SMOKE_FAIL (override didn't survive save/reload)")
            return 1
        ref_lib = char_in_root.override_library.reference.library.filepath
        print(f"PROBE Char's real reference.library = {ref_lib}")

        # --- synthesize an f7chain report claiming a 2-hop route to
        # --- whatever file Char's REAL reference.library resolves to -- the
        # --- same crafted-DepGraph technique tests/test_linkchain.py uses,
        # --- standing in for a real multi-file BAT scan (a separate,
        # --- already-covered concern -- ops.linkchain.scan_link_chains).
        g = linkchain.DepGraph()
        g.add_edge(str(root_path), "/proj/fake_intermediate.blend")
        g.add_edge("/proj/fake_intermediate.blend", ref_lib)
        # Matching posing info for BOTH so the overview's "flattenable_total"
        # (the top headline's live "AA of YY" count) reflects what the LIVE
        # scan actually finds -- scan_flatten_candidates classifies from
        # real bpy.data.objects directly, never from this stashed report.
        posing = [linkchain.ObjectPosingInfo(
            name=nm, has_override=True, loc=(5.0, 5.0, 5.0),
            rot=(0.0, 0.0, 0.0), quat=(1.0, 0.0, 0.0, 0.0), size=(1.0, 1.0, 1.0))
            for nm in ("Char", "Char2")]
        report = linkchain.build_chain_report(g, str(root_path), posing)
        store.stash_report(bpy.context, report, "f7chain")

        try:
            res2 = bpy.ops.assetdoctor.scan_flatten_candidates("EXEC_DEFAULT")
            checks.append(("scan_flatten_candidates FINISHED", res2 == {"FINISHED"}))
            rows = list(wm.assetdoctor_flatten_candidates)
            print(f"PROBE candidate rows: "
                  f"{[(r.name, r.rig, r.is_remote, r.ready, r.status) for r in rows]}")
            checks.append(("Char found as a LOCAL candidate",
                           any(r.name == "Char" and not r.is_remote for r in rows)))
            checks.append(("Char is READY (synthetic multi-hop route resolved)",
                           any(r.name == "Char" and r.ready for r in rows)))
            checks.append(("Char2 (a different object TYPE) got its OWN group",
                           any(r.name == "Char2" and r.rig != "Mesh (standalone)" for r in rows)))

            # Only flatten Char's group this round -- Char2's group stays
            # deselected so the Make Local check below can flatten it alone.
            char2_group = next((r.rig for r in rows if r.name == "Char2"), "")
            wm.assetdoctor_flatten_deselected = char2_group
            before_done = wm.assetdoctor_flatten_done
            res3 = bpy.ops.assetdoctor.flatten_selected("EXEC_DEFAULT")
            checks.append(("flatten_selected FINISHED", res3 == {"FINISHED"}))
            checks.append(("outcome count advanced", wm.assetdoctor_flatten_done > before_done))
            checks.append(("Char2 untouched this round (its group was deselected)",
                           bpy.data.objects.get("Char2_flattened") is None))

            new_obj = bpy.data.objects.get("Char_flattened")
            checks.append(("renamed result object exists", new_obj is not None))
            checks.append(("result is itself an override",
                           new_obj is not None and new_obj.override_library is not None))
            if new_obj is not None:
                checks.append(("transform replayed (location matches the override)",
                               tuple(new_obj.location) == (5.0, 5.0, 5.0)))
                # A single object's own ancestor is its immediate parent
                # collection (CharColl), not the scene root -- the mirror is
                # CharColl_flattened, sibling of CharColl (see
                # _resolve_real_collection).
                mirror_coll = bpy.data.collections.get("CharColl_flattened")
                checks.append(("a mirror collection was created",
                               mirror_coll is not None and new_obj.name in mirror_coll.objects))

            old_char = bpy.data.objects.get("Char")
            checks.append(("original Char hidden, not deleted",
                           old_char is not None and old_char.hide_viewport))

            # --- Make Local: now flatten Char2's group WITH it enabled ------
            wm.assetdoctor_flatten_deselected = ""  # Char's group already done; harmless either way
            wm.assetdoctor_flatten_make_local = True
            bpy.ops.assetdoctor.scan_flatten_candidates("EXEC_DEFAULT")
            rows2 = list(wm.assetdoctor_flatten_candidates)
            char2_group2 = next((r.rig for r in rows2 if r.name == "Char2"), "")
            checks.append(("Char2 still a ready candidate on re-scan",
                           any(r.name == "Char2" and r.ready for r in rows2)))
            wm.assetdoctor_flatten_deselected = "\n".join(
                g for g in {r.rig for r in rows2} if g != char2_group2)
            res4 = bpy.ops.assetdoctor.flatten_selected("EXEC_DEFAULT")
            checks.append(("flatten_selected (Make Local) FINISHED", res4 == {"FINISHED"}))
            char2_new = bpy.data.objects.get("Char2_flattened")
            checks.append(("Char2_flattened exists", char2_new is not None))
            checks.append(("Make Local detached it from the override system",
                           char2_new is not None and char2_new.override_library is None))

            # --- top overview line goes live too (summary-propagation rule) -
            panels = __import__(f"{PKG}.ui.panels", fromlist=["x"])
            _has_run, nodes = panels._feature_tree_nodes(wm, "f7chain")
            headline, _skip = panels._report_headline(nodes, "f7chain", wm)
            print(f"PROBE f7chain headline: {headline!r}")
            checks.append(("top overview line shows 'AA of YY flattenable' live",
                           "of 2 flattenable" in headline))
        finally:
            addon.unregister()

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("FLATTEN_SELECTED_SMOKE_OK" if ok else "FLATTEN_SELECTED_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("FLATTEN_SELECTED_SMOKE_FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
