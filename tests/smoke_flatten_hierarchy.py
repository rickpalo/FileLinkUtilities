"""End-to-end check for the 2026-06-27 remote-candidate hierarchy redesign
(docs/TODO.md): the picker used to group every remote character from one
donor file under a single "Remote: <file>" key (no per-character selection
possible) and only ever surfaced objects already classified
OVERRIDE_WITH_TRANSFORM at the offline-census stage (missing any character
posed purely via bones, e.g. the rig's own Armature whose object-transform
never moves). Both fixed by reading the raw per-file hierarchy census
(``assetdoctor_flatten_hierarchy_json``) + ``build_offline_rig_index``
instead of the already-filtered f7chain report findings.

    blender --background --factory-startup --python tests/smoke_flatten_hierarchy.py
"""

import glob
import json
import pathlib
import sys
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

    checks = []
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        wm = bpy.context.window_manager

        root = "/proj/root.blend"
        donor = "/proj/donor.blend"
        ref_lib = "//ultimate.blend"

        # Two characters in the SAME donor file: HeroRig (posed via bones
        # only -- object transform stays at identity, so the OLD
        # classification gate would have dropped it entirely) and
        # VillainRig (a normal object-transform override). Each rig has one
        # mesh child attached via parent_name. A standalone prop (no
        # resolvable rig) rounds out the donor file.
        posing = [
            linkchain.ObjectPosingInfo(
                name="HeroRig", obj_kind="Armature", has_override=True,
                reference=linkchain.OverrideReference(name="HeroRig", kind="Object", library=ref_lib),
                source_file=donor),
            linkchain.ObjectPosingInfo(
                name="HeroBody", obj_kind="Mesh", has_override=True, parent_name="HeroRig",
                reference=linkchain.OverrideReference(name="HeroBody", kind="Object", library=ref_lib),
                source_file=donor),
            linkchain.ObjectPosingInfo(
                name="VillainRig", obj_kind="Armature", has_override=True, loc=(3.0, 0.0, 0.0),
                reference=linkchain.OverrideReference(name="VillainRig", kind="Object", library=ref_lib),
                source_file=donor),
            linkchain.ObjectPosingInfo(
                name="LooseProp", obj_kind="Mesh", has_override=True,
                reference=linkchain.OverrideReference(name="LooseProp", kind="Object", library=ref_lib),
                source_file=donor),
        ]
        wm.assetdoctor_flatten_hierarchy_json = json.dumps(linkchain.posing_list_to_dict(posing))

        g = linkchain.DepGraph()
        g.add_edge(root, "/proj/intermediate.blend")
        g.add_edge("/proj/intermediate.blend", ref_lib)
        report = linkchain.build_chain_report(g, root, [])
        store.stash_report(bpy.context, report, "f7chain")

        res = bpy.ops.assetdoctor.scan_flatten_candidates("EXEC_DEFAULT")
        checks.append(("scan_flatten_candidates FINISHED", res == {"FINISHED"}))

        rows = {r.name: r for r in wm.assetdoctor_flatten_candidates}
        print(f"PROBE rows: {[(n, r.group_parent, r.rig) for n, r in rows.items()]}")

        checks.append(("HeroRig (bone-only-posed Armature) IS a candidate -- "
                       "the old transform-only gate would have dropped it",
                       "HeroRig" in rows))
        checks.append(("HeroBody and HeroRig share one rig group",
                       "HeroRig" in rows and "HeroBody" in rows
                       and rows["HeroRig"].rig == rows["HeroBody"].rig))
        checks.append(("VillainRig got a DIFFERENT rig group than HeroRig -- "
                       "the actual user-reported bug (one donor file, one shared checkbox)",
                       "VillainRig" in rows and rows["VillainRig"].rig != rows["HeroRig"].rig))
        checks.append(("LooseProp (no resolvable rig) falls back to a standalone-by-type group",
                       "LooseProp" in rows and "standalone" in rows["LooseProp"].rig))
        checks.append(("all donor-file rows share one outer group_parent",
                       len({r.group_parent for r in rows.values()}) == 1
                       and next(iter(rows.values())).group_parent.startswith("Remote:")))
        checks.append(("every row is marked remote", all(r.is_remote for r in rows.values())))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("FLATTEN_HIERARCHY_SMOKE_OK" if ok else "FLATTEN_HIERARCHY_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("FLATTEN_HIERARCHY_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
