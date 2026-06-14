# AssetDoctor — TODO / backlog

## Open decisions
- [ ] **Debug log: fresh-per-open vs continuous.** Today the handler opens `AssetDoctorDebugLog.txt`
  in **append** mode and only attaches when the user ticks the toggle in a session.
  **Recommendation: start a fresh log per file-open** (truncate on enable), because the log's
  purpose is to be reproduced and sent for one bug — a clean, small, single-session file is
  easier to read than an ever-growing multi-session append (which also grows unbounded).
  Implementation: open the handler in `mode="w"`, and add a `bpy.app.handlers.load_post` handler
  that re-arms/truncates the log when a file opens with the toggle on (Scene-prop `update`
  callbacks don't fire on load, so today an enabled toggle doesn't reactivate after open — fix
  this at the same time). If cross-session history is ever wanted instead, use a
  `RotatingFileHandler` with a size cap rather than plain append.

## Done
- [x] **(5) Split Project section** into a folder path field (`Scene.assetdoctor_scan_dir`)
  + a separate **Scan Link Map** button. Picking a folder no longer auto-runs.
- [x] **(1) Tooltips** — every operator has a `bl_description`; the multi-variant buttons
  (Make Local New File/In Place/report, dedup apply/report, orphans purge/report) use a
  `description(cls, context, properties)` classmethod for accurate per-button tooltips.
  Scene props carry descriptions too.
- [x] **(2) Utilities section + Enable Debug Log** — `Scene.assetdoctor_debug_log` toggle in a
  new Utilities box. Enabling attaches a DEBUG file handler writing `debugLog.txt` next to the
  .blend (or Blender's temp dir if unsaved). All operators log via the `assetdoctor` logger
  (`log.py`): INFO findings go to console + file; DEBUG detail (per-file scan, per-remap,
  localize passes) goes to the file only. Suitable for a remote user to send back.

## Done (cont.)
- [x] **(4) Progress / responsiveness.** Folder scan is now a **modal operator**: a
  time-bounded batch of files per `wm.event_timer` tick, ESC to cancel, live progress via
  WindowManager props (`assetdoctor_scan_active/_progress/_status`) shown as a `layout.progress`
  bar in the panel, plus the wait cursor and status-bar text. `core.blendscan` split into
  `new_scan_result`/`scan_into`/`map_folder` and `f1_linkmap.report_from_scan` so the modal
  and synchronous paths share logic. Synchronous `execute` retained for scripting/tests.
  Core verified by pytest (incremental == synchronous); modal/progress is interactive-only
  (can't run headless) — verify by running the scan in the UI.
- [x] **(doc link)** Documentation icon (HELP) right-aligned on the panel header via
  `draw_header`, opens `DOC_URL` (placeholder GitHub URL — update on push). `website` also
  added to the manifest.

## Planned — milestone "M7: Reporting + Resource Analyzer (F5)"

Decided sequencing (user): build the **shared tree/report widget** and the **geometry-dedup
engine** first, so the report viewer (#3), the instance-savings detector, and F5 all reuse
them instead of duplicating work. Proposed build order:

1. **Shared tree/report widget.** ✅ DONE. `core/tree.py` (TreeNode/Row, `report_to_tree`,
   `flatten_visible`) + `ops/report_store.py` (stash + toggle/clear/select) + the **Report**
   panel rendering an expandable tree with severity icons and click-to-select. Serves **(3)
   the report viewer** and will back F5's outliner display. Verified by `test_tree.py` +
   `smoke_report.py`.
2. **Geometry dedup engine.** Extend fingerprinting (mesh done; add curve/other geometry) to
   find identical-but-separate datablocks used by different objects → "instanceable"
   candidates. Apply = repoint `object.data` to one shared datablock (the geometry analogue of
   F3's material remap). This also subsumes the instance-savings part of F5 and overlaps M6.
3. **(F5) Resource Analyzer.** Analyze button → the tree from step 1, rows showing rolled-up
   **estimated RAM / estimated texture-VRAM / accurate disk**, biggest-first; shared/multi-user
   data counted once and flagged (surfaces "N copies → could be 1"). Feasibility:
   - Disk: accurate (`.blend` size + external dep sizes via BAT; per-block sizes offline).
   - System RAM: ESTIMATE from a documented model (mesh counts; image `size×channels×depth`
     or `packed_file.size`). No per-ID byte API in Blender.
   - Texture VRAM: ESTIMATE only (`res×channels×~1.33` mipmaps); no per-datablock VRAM API.
   Label estimates clearly; granularity toggle for the GPU column.
4. **(F5) "Profile Render" button** ✅ DONE (v0.1.5). Renders the current frame and reports
   real **peak process RAM** (OS-level). Real VRAM not attempted (no Python API); F5 estimates
   cover VRAM. `core.resource.peak_process_ram_bytes` + `smoke_profile.py`.

Note: the duplicate→instance detection is fully available from the **loaded** file (no
load-time profiling) — it's the existing fingerprint engine plus `data.users` sharing checks.
Only step 4 (real peak memory) needs a live render.

## Done — milestone "M8: Report system v2" (v0.1.4)
- [x] **Persistent per-type reports** — per-feature registry + selector; clear removes only the
  shown report. F5 resource separate.
- [x] **Per-line tooltips** — row labels are tooltip-bearing buttons (full text on hover);
  clicking does the row's natural action.
- [x] **Print/export** — Export… on Report + Resource panels → `.txt` (indented) or `.csv`.
- [x] **Select-in-Outliner** — non-intrusive select+activate (Outliner follows active);
  material slot highlighted; orphan/no-user → hint to Blender File / Orphan Data view.

### (original M8 notes for reference)
- [x] **Persistent per-type reports.** Today one slot (`assetdoctor_last_report`) is overwritten
  by each scan. Change to a **per-feature registry** (F1/F2/F3/F4/Geo each keep their own report
  + expanded state, persisting until that scan is re-run). Report panel gets a small selector
  (row of toggle buttons or enum) to choose which to view. F5 resource is already its own slot.
- [ ] **Per-line tooltips (full text).** The N-panel is narrow and lines truncate. Render each
  tree row's label as a no-emboss operator whose dynamic `description()` returns the full text
  (e.g. the full broken-link path), so hovering shows everything. Bonus: the whole row becomes
  clickable (parents toggle, leaves select).
- [ ] **Print / export report.** "Print" = save the current report to a formatted `.txt` (and/or
  CSV) via a file browser, for printing/sharing. Add an Export button to the Report and Resource
  panels (F1 already writes JSON/CSV/DOT; generalize to all).
- [ ] **Select-in-Outliner (needs your feedback — see chat).** Selecting a finding should also
  reflect in the Outliner. Recommendation: set active + select the user objects (Outliner follows
  active) **without** force-opening/rearranging editors; for a multi-use material, select all
  user objects + set the active object's material slot; for orphan/unused datablocks (no object
  users) or when no Outliner is open, show a status hint to view via Outliner → Blender File /
  Orphan Data (the API can't reliably select there).

## New requirement — auto-updates
- [ ] **Auto-updates.** Blender's extension system updates automatically only for extensions
  installed from a **repository URL**, not from a disk `.zip`. Recommended approach: publish a
  **self-hosted extension repository** (generate `index.json` + host the zips on GitHub
  Releases/Pages), which the user adds once in Preferences → Get Extensions → Repositories;
  Blender then checks/updates natively. No custom updater code needed. (A legacy in-addon
  GitHub-release updater is the fallback if we never host a repo.) Blocked on the GitHub repo
  existing — pairs with the first push. Also: keep `version` bumped (3rd digit per step) so the
  repo index advertises new versions.
  - **Effort: low.** No in-addon updater code. One-time: a publish step (build zip +
    `blender --command extension server-generate` → `index.json`, host on GitHub Pages/Releases)
    + user adds the repo URL once. Per release: re-run publish (script/GH Action). Local disk
    installs stay manual by design. Blocked only on the repo existing.

## Versioning
- [x] **Per-step patch bump + visible version.** Manifest `version` is bumped on each completed
  step; the N-panel header shows `vX.Y.Z` (read from the manifest) so the installed build is
  verifiable at a glance.

## Future / deferred
- [ ] **M6 — F1 cross-file duplication census** (deferred by user; may be re-scoped after
  testing). Largely folded into M7 step 2's geometry-dedup engine; the cross-*file* count
  still needs an offline fingerprint path (headless-Blender pass per file, or a BAT-level
  signature).
- [ ] First git commit once the tested baseline is accepted.
