# Releasing & auto-updates

## For users — add the auto-updating repository in Blender

1. Edit → Preferences → **Get Extensions** → the dropdown (top-right) → **Repositories** →
   **＋ Add Remote Repository**.
2. URL: `https://rickpalo.github.io/FileLinkUtilities/index.json`
3. Tick **Check for Updates on Startup** (and **Enabled**).
4. Back in **Get Extensions**, search "File & Link Utilities" and **Install** it *from the repository*
   (if you previously installed the zip from disk, install the repo copy — same `id`, so
   it takes over; remove the disk one if both show).

Blender then offers updates automatically whenever a newer version is published here.
Installing from a local `.zip` (Install from Disk) never auto-updates — that's expected.

## For the maintainer — cutting a release

Repo: https://github.com/rickpalo/FileLinkUtilities  ·  Pages repo served from branch `gh-pages`.

1. **Bump** `version` in `blender_manifest.toml` (3rd digit per step; see CHANGELOG).
2. **Build** the zip:
   ```
   blender --command extension build --source-dir . --output-dir dist
   ```
3. **Commit, tag, push:**
   ```
   git add -A && git commit -m "…"
   git tag -a vX.Y.Z -m "File & Link Utilities vX.Y.Z — …"
   git push origin main vX.Y.Z
   ```
4. **GitHub Release** (with the zip asset):
   ```
   gh release create vX.Y.Z dist/file_link_utilities-X.Y.Z.zip --title "File & Link Utilities vX.Y.Z" --notes "…"
   ```
5. **Refresh the Pages repo index** (this is what drives auto-update). Publish a
   **single-version index** — only the *latest* zip in the repo dir before generating:
   ```
   # check out gh-pages into .pages, based on ORIGIN (the local ref lags behind)
   git worktree add -B gh-pages .pages origin/gh-pages
   Remove-Item .pages\file_link_utilities-*.zip  # drop the previous version's zip
   Copy-Item dist\file_link_utilities-X.Y.Z.zip .pages\  # only the new one
   blender --command extension server-generate --repo-dir .pages   # must say "found 1 packages"
   git -C .pages add -A
   git -C .pages commit -m "gh-pages: index vX.Y.Z"
   git -C .pages push origin gh-pages
   git worktree remove .pages --force
   ```
6. **Verify:** `https://rickpalo.github.io/FileLinkUtilities/index.json` shows the new `version`
   (and ONLY that version), and its zip returns HTTP 200.

Notes:
- **Single version only.** Do NOT leave older zips in the repo dir. `server-generate` would emit
  one index entry per zip with the *same* `blender_version` range and warn "conflicting blender
  versions" — Blender then shows the newest as available but reinstalls the FIRST/oldest entry,
  so updates appear stuck (hit 0.1.5↔0.1.7, 2026-06-15). Version history lives on the
  [Releases page](https://github.com/rickpalo/FileLinkUtilities/releases), not in the index.
- Base the worktree on `origin/gh-pages` (`-B`): the local `gh-pages` ref can lag behind origin.
- `index.json` uses a relative `archive_url`, so it and the zip must sit in the same directory
  (they do, at the Pages root). `.pages/` is git-ignored on `main`.
- **Renamed from AssetDoctor** (Phase R, 2026-07-05): package id, repo, and gh-pages URL all
  changed. Existing users must manually remove the old
  `rickpalo.github.io/AssetDoctor/index.json` repository entry and add the new one above
  (the package id change means this can't auto-migrate).
