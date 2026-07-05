"""Folder-search ambiguity/skip diagnostics, end-to-end in Blender:

    blender --background --factory-startup --python tests/smoke_folder_search_diagnostics.py

Reproduces the user-reported symptom (a drive-level "Search a Folder (Recursive)"
misses textures a narrower search finds) and checks the new diagnostic actually
explains it: a texture whose filename exists in TWO scanned subfolders gets no
target (unchanged behaviour — still never guesses) but its row's
``ambiguous_count`` is set so the UI can say WHY, while a uniquely-named texture
resolves normally with ``ambiguous_count == 0``.
"""

import pathlib
import sys
import tempfile
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))
PKG = REPO_ROOT.name


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()

    checks = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "one").mkdir()
            (root / "two").mkdir()
            (root / "one" / "dup.png").write_bytes(b"x")
            (root / "two" / "dup.png").write_bytes(b"x")  # same filename, 2 places
            (root / "one" / "uniq.png").write_bytes(b"x")

            wm = bpy.context.window_manager
            coll = wm.filelink_broken_imgs
            coll.clear()
            for name in ("dup.png", "uniq.png"):
                row = coll.add()
                row.name = name
                row.stored = f"//missing/{name}"

            res = bpy.ops.filelink.relink_folder_search(
                "EXEC_DEFAULT", directory=str(root), mode="EXACT_ALL", recursive=True)
            checks.append(("operator FINISHED", res == {"FINISHED"}))

            rows = {r.name: r for r in wm.filelink_broken_imgs}
            dup, uniq = rows.get("dup.png"), rows.get("uniq.png")
            checks.append(("dup row found", dup is not None))
            checks.append(("uniq row found", uniq is not None))
            if dup is not None:
                checks.append(("ambiguous dup has NO target (never guesses)", not dup.target))
                checks.append(("ambiguous_count reflects the 2 matches", dup.ambiguous_count == 2))
            if uniq is not None:
                checks.append(("unique texture got a target", bool(uniq.target)))
                checks.append(("unique texture has no ambiguity flagged",
                               uniq.ambiguous_count == 0))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("FOLDER_DIAG_SMOKE_OK" if ok else "FOLDER_DIAG_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("FOLDER_DIAG_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
