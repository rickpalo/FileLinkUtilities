"""Tier 2 material-name escalation, end-to-end in Blender:

    blender --background --factory-startup --python tests/smoke_material_tier.py

Reproduces the real reorg scenario: a missing texture whose loose file is
GONE (moved into a per-material .blend under a different folder) but whose
MATERIAL exists, under a shortened alias, in another .blend nearby. Checks
that "Suggest Matches (fuzzy)" (mode=FUZZY) escalates past Tier 1 (which has
nothing to find) to Tier 2 (core.material_search + core.blendscan) and stages
the image harvested from that other .blend as the proposal.
"""

import pathlib
import sys
import tempfile
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))
PKG = REPO_ROOT.name

MATERIAL_NAME = "FabricFloralDuckeggJacquard001"
ALIAS = "DuckEgg"  # the shortened in-scene name Tier 2 must still resolve


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()

    checks = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            search_root = root / "search"  # what Tier 1 walks — the "Materials" folder
            texture_root = root / "elsewhere"  # NOT under search_root
            (search_root / "Materials").mkdir(parents=True)
            texture_root.mkdir()

            # The real on-disk texture the missing row secretly wants — lives
            # OUTSIDE the folder tree being searched (a different drive/library
            # in the real case), so Tier 1's loose-file walk can never find it
            # directly; only Tier 2, via the .blend's own harvested path, can.
            tex_path = texture_root / f"{MATERIAL_NAME}_AO.jpg"
            tex_path.write_bytes(b"fake-jpg")

            # A material .blend (Tier 2's actual target), referencing that
            # image externally (not packed) — same shape as a real asset file.
            mat = bpy.data.materials.new(MATERIAL_NAME)
            mat.use_nodes = True
            img = bpy.data.images.new("ao_img", 4, 4)
            img.filepath = str(tex_path)
            img.source = 'FILE'
            tex_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
            tex_node.image = img

            other_blend = search_root / "Materials" / f"{ALIAS}.blend"
            bpy.data.libraries.write(str(other_blend), {mat, img}, path_remap='ABSOLUTE')
            bpy.data.materials.remove(mat)
            bpy.data.images.remove(img)

            # The current file's missing-texture row: wants a file that does
            # NOT exist anywhere as a loose file under search_root, but belongs
            # to a material named with the shortened alias.
            wm = bpy.context.window_manager
            coll = wm.filelink_broken_imgs
            coll.clear()
            row = coll.add()
            row.name = f"{MATERIAL_NAME}_AmbientOcclusion_2K.jpg"
            row.stored = f"//missing/{MATERIAL_NAME}_AmbientOcclusion_2K.jpg"
            row.material = ALIAS

            res = bpy.ops.filelink.relink_folder_search(
                "EXEC_DEFAULT", directory=str(search_root), mode="FUZZY", recursive=True)
            checks.append(("operator FINISHED", res == {"FINISHED"}))

            row = wm.filelink_broken_imgs[0]
            checks.append(("Tier 2 staged a proposal", bool(row.proposal)))
            checks.append(("proposal points at the harvested image",
                           pathlib.Path(row.proposal) == tex_path))
            checks.append(("confidence is low (generic short alias)",
                           row.proposal_confidence == "low"))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("MATERIAL_TIER_SMOKE_OK" if ok else "MATERIAL_TIER_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("MATERIAL_TIER_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
