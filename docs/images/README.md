# Documentation screenshots

I can't capture these myself (no GUI control), so the User Guide references them as
placeholders. Drop PNGs with these exact names into this folder and they'll render in
[../USER_GUIDE.md](../USER_GUIDE.md) and the main README.

**Status (2026-06-15):** all captured. Extra shots beyond the table below:
`install-repository-post.png` (post-add install state) and `progress-bar.png` (the shared
progress bar/status + Esc shown for any long-running action).

Capture in Blender 5.x at a readable size (≈ the N-panel width; crop tight). Suggested ~1× UI
scale, light or dark theme is fine — just be consistent.

| Filename | What to capture | Notes |
|---|---|---|
| `panel-overview.png` | The full **File & Link Utilities** N-panel, all sections expanded | The hero shot for the README. Press `N` in the 3D viewport → File & Link Utilities tab. Show the version + ? icon in the header. |
| `scan-progress.png` | The **Scan Link Map** progress bar mid-scan | Run F1 on a folder with several `.blend` files; grab while the progress bar + "N / M files" is visible. |
| `progress-bar.png` | The **shared progress bar** for any modal action | The top-of-panel progress bar + status + "Press ESC to cancel", e.g. during a dedup/orphan scan. |
| `report-panel.png` | The **Report** panel with a tree expanded | Run e.g. *Orphans → Scan* or *Materials → Find Duplicates*, expand a couple of rows; show the per-feature **selector row** at the top and the **Export…** button. |
| `report-tooltip.png` *(optional)* | A **row tooltip** showing full text | Hover a long item (e.g. a broken-link path) so the full-text tooltip is visible. Nice-to-have for the "tooltips" section. |
| `resource-panel.png` | The **Resource Usage** panel | Run *Analyze Memory/Disk* (ideally also *Profile Render*), expand the Images/Meshes types so the size columns + "Profiled real peak RAM" line show. |
| `preferences.png` | File & Link Utilities **Preferences** | Edit → Preferences → Add-ons → File & Link Utilities; show backup toggle/dir, resolution tokens, white/black lists. |
| `install-repository.png` | **Add Remote Repository** dialog | Get Extensions → ⌄ → Repositories → Add Remote Repository, with the `…/index.json` URL filled in. For the install section. |
| `install-repository-post.png` | File & Link Utilities **in the repo after adding** | Get Extensions list showing File & Link Utilities available to install from the rickpalo.github.io repo. |
| `material-dedup-report.png` *(optional)* | A **material dedup** report | Find Duplicates on a file with a 1K/2K pair; show the "keep X / remap N" finding. Good for the F3 section. |

Tips:
- PNG, trimmed to the relevant UI (avoid full-screen captures).
- Keep file sizes modest (these live in git); a few hundred KB each is fine.
- If you rename/add shots, update the references in `USER_GUIDE.md` / `README.md`.
