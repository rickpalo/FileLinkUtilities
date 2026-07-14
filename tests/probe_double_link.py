"""Throwaway probe (not a regression test): does linking the SAME library
TWICE for real (``link=True`` with ``data_to`` actually assigned, not a
``_peek_names``-style dry read) in one Blender session crash, the way
re-PEEKING an already-linked library is documented to
(``ops/datablock_reconnect.py::_populate_missing_blocks``'s docstring,
2026-06-24 EXCEPTION_ACCESS_VIOLATION repro)?

This is docs/TODO.md's "first concrete step next session" for the two-pass
Examine Library content-verification design (2026-07-09 entry): pass 2 would
really-link a candidate file once to fingerprint it
(``ops.examine_library._content_graph_match``), and Apply Selected already
really-links from the same source independently later
(``FILELINK_OT_examine_apply_selected.execute``'s ``by_source`` grouping).
Nobody has confirmed the SECOND real load — not a peek — is safe.

Mirrors the actual shape as closely as possible: load Mesh/Material/NodeTree
(the three fingerprinted kinds) from one source file, read their content via
the real ``ops.extract`` + ``core.fingerprint`` functions (the same
vertex/node reads implicated in the documented crash class), then do it all
again from the SAME source path in the SAME session, and read content again.
If this script prints its final marker, the double-real-link shape survived.

Run: blender --background --factory-startup --python tests/probe_double_link.py
"""
import glob
import pathlib
import sys
import tempfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))
_bat = glob.glob(str(REPO_ROOT / "wheels" / "blender_asset_tracer-*.whl"))
if _bat:
    sys.path.insert(0, _bat[0])
PKG = REPO_ROOT.name


def _build_source(bpy, path):
    bpy.ops.wm.read_factory_settings(use_empty=True)

    mesh = bpy.data.meshes.new("TestMesh")
    verts = [(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)]
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    mesh.update()
    mesh.use_fake_user = True
    obj = bpy.data.objects.new("TestMesh", mesh)
    bpy.context.scene.collection.objects.link(obj)

    mat = bpy.data.materials.new("TestMat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (0.2, 0.6, 0.9, 1.0)
    mat.use_fake_user = True

    tree = bpy.data.node_groups.new("TestGroup", "ShaderNodeTree")
    tree.nodes.new("ShaderNodeMath")
    tree.use_fake_user = True

    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    print(f"PROBE source saved: {path}")


def _real_link(bpy, path, label):
    with bpy.data.libraries.load(str(path), link=True) as (data_from, data_to):
        data_to.meshes = [n for n in data_from.meshes if n == "TestMesh"]
        data_to.materials = [n for n in data_from.materials if n == "TestMat"]
        data_to.node_groups = [n for n in data_from.node_groups if n == "TestGroup"]
    mesh = data_to.meshes[0]
    mat = data_to.materials[0]
    tree = data_to.node_groups[0]
    print(f"PROBE {label} linked: mesh id={id(mesh)} name={mesh.name!r} "
          f"lib={mesh.library.filepath if mesh.library else None}; "
          f"mat id={id(mat)} name={mat.name!r}; "
          f"tree id={id(tree)} name={tree.name!r}")
    return mesh, mat, tree


def _fingerprint(extract_mesh, extract_material, extract_node_tree,
                  fingerprint_mesh, fingerprint_material, fingerprint_node_tree,
                  mesh, mat, tree, label):
    fp_mesh = fingerprint_mesh(extract_mesh(mesh))
    fp_mat = fingerprint_material(extract_material(mat))
    fp_tree = fingerprint_node_tree(extract_node_tree(tree))
    print(f"PROBE {label} fingerprints: mesh={fp_mesh} mat={fp_mat} tree={fp_tree}")
    return fp_mesh, fp_mat, fp_tree


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()
    extract = __import__(f"{PKG}.ops.extract", fromlist=[
        "extract_mesh", "extract_material", "extract_node_tree"])
    fingerprint = __import__(f"{PKG}.core.fingerprint", fromlist=[
        "fingerprint_mesh", "fingerprint_material", "fingerprint_node_tree"])

    try:
        with tempfile.TemporaryDirectory() as tmp:
            source_path = pathlib.Path(tmp) / "source.blend"
            _build_source(bpy, source_path)

            # Fresh consumer session -- everything from here on happens
            # WITHOUT a read_factory_settings reset, matching one continuous
            # Blender session doing pass-2-verify then Apply-Selected later.
            bpy.ops.wm.read_factory_settings(use_empty=True)

            mesh1, mat1, tree1 = _real_link(bpy, source_path, "PASS1 (verify)")
            fp1 = _fingerprint(
                extract.extract_mesh, extract.extract_material, extract.extract_node_tree,
                fingerprint.fingerprint_mesh, fingerprint.fingerprint_material,
                fingerprint.fingerprint_node_tree,
                mesh1, mat1, tree1, "PASS1")

            print("PROBE about to real-link the SAME source a SECOND time "
                  "in the SAME session...")
            mesh2, mat2, tree2 = _real_link(bpy, source_path, "PASS2 (apply)")
            print(f"PROBE identity: mesh2 is mesh1 = {mesh2 is mesh1}; "
                  f"mat2 is mat1 = {mat2 is mat1}; tree2 is tree1 = {tree2 is tree1}")

            fp2 = _fingerprint(
                extract.extract_mesh, extract.extract_material, extract.extract_node_tree,
                fingerprint.fingerprint_mesh, fingerprint.fingerprint_material,
                fingerprint.fingerprint_node_tree,
                mesh2, mat2, tree2, "PASS2")
            print(f"PROBE fingerprints match pass1==pass2: {fp1 == fp2}")

            print(f"PROBE bpy.data.meshes with name 'TestMesh': "
                  f"{[m.name for m in bpy.data.meshes if m.name.startswith('TestMesh')]}")
            print(f"PROBE bpy.data.libraries: {[lib.filepath for lib in bpy.data.libraries]}")

        print("PROBE_DOUBLE_LINK_SURVIVED")
        return 0
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
