"""Scan every materials/*.blend under a library root for asset-marking data-
quality issues, one Blender session for the whole scan (open_mainfile per
file, not a relaunch, to avoid paying addon-load startup cost hundreds of
times).

Flags three issue kinds:
  * multi_asset   -- more than one material in the file is asset-marked
                     (usually the real material plus staging-rig leftovers
                     like Floor/Left_Light/R_Light/T_Light) -- clutters the
                     Materials catalog in the Asset Browser with spurious
                     extra tiles.
  * no_asset      -- zero materials in the file are asset-marked -- the file
                     won't show up in the Asset Browser at all.
  * name_mismatch -- exactly one asset-marked material, but its name doesn't
                     match the file's own basename (informational only, not
                     necessarily wrong -- some are intentionally renamed).

Read-only: never modifies or saves any file.

Usage:
    blender -b --python tools/find_multi_asset_materials.py -- \\
        --library "D:\\BlenderLibraries\\LocalLibrary" \\
        [--studio "...\\MaterialDisplayStudio.blend"] \\
        [--csv "D:\\BlenderReorg_Audit\\multi_asset_materials.csv"]
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import sys

import bpy


def _parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--library", required=True)
    p.add_argument("--studio", default=None, help="Excluded from the scan if given")
    p.add_argument("--csv", default=None)
    return p.parse_args(argv)


def main():
    args = _parse_args()
    csv_path = args.csv or os.path.join(args.library, "multi_asset_materials.csv")

    files = glob.glob(os.path.join(args.library, "materials", "**", "*.blend"), recursive=True)
    if args.studio:
        studio_norm = os.path.normcase(os.path.abspath(args.studio))
        files = [f for f in files if os.path.normcase(os.path.abspath(f)) != studio_norm]
    files.sort()

    rows = []
    print(f"Scanning {len(files)} material files...")
    for i, path in enumerate(files, 1):
        try:
            bpy.ops.wm.open_mainfile(filepath=path)
        except Exception as exc:
            rows.append((path, "open_failed", str(exc)))
            continue

        marked = [m for m in bpy.data.materials if getattr(m, "asset_data", None) is not None]
        basename = os.path.splitext(os.path.basename(path))[0].strip().lower()

        if len(marked) == 0:
            rows.append((path, "no_asset", ""))
        elif len(marked) > 1:
            names = [m.name for m in marked]
            rows.append((path, "multi_asset", "; ".join(names)))
        else:
            name = marked[0].name
            if name.strip().lower() != basename:
                rows.append((path, "name_mismatch", name))

        if i % 50 == 0:
            print(f"  ...{i}/{len(files)}")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "issue", "detail"])
        w.writerows(rows)

    by_issue = {}
    for _, issue, _ in rows:
        by_issue[issue] = by_issue.get(issue, 0) + 1
    print(f"\nCSV written: {csv_path}")
    print(f"Scanned {len(files)} files, {len(rows)} flagged:")
    for issue, count in sorted(by_issue.items()):
        print(f"  {issue}: {count}")


main()
