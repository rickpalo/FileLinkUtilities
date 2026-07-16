# Changelog

All notable changes to File & Link Utilities (renamed from AssetDoctor, see below). Versioning
is patch-only unless a change is flagged as major. From 0.2.x onward, entries below are grouped
by feature area rather than one per version bump (the project moved to much more frequent small
bumps) — see `docs/TODO.md` for the detailed session-by-session build history behind any entry.

Entries below [0.2.106] are kept as originally written, under the old "AssetDoctor" name and
`ASSETDOCTOR_*` identifiers, for historical accuracy — don't edit them to match the new naming.

## [0.3.29] — Stop listing missing libraries as "reconnectable data-blocks"

### Fixed
- **A missing library no longer shows up inside Datablock Reconnect.** The missing-block scan walked all
  of `bpy.data`, and a missing `Library` datablock has `is_missing = True` too — so each broken library
  appeared as a `Library: foo.blend` row grouped under "(source unknown)", a dead end (a library can't be
  reconnected via `user_remap` — it's fixed by Relink or Retarget). `_iter_missing_blocks` now skips
  `bpy.data.libraries`. This also removes the double-counting where the 3 broken libraries appeared both
  in Broken Library Links and again in the reconnect list.

## [0.3.28] — Declutter Connect + simpler reconnect messaging

### Changed
- **Retarget Library moved out of the Connect phase back to Utilities.** It's a specialized tool for
  *working* libraries (break a circular reference, stop depending on a healthy library), not part of the
  missing-library fix flow — the per-row Retarget button already handles broken libraries by routing to
  Datablock Reconnect. It was cluttering Connect.
- **Datablock Reconnect group headers dropped their redundant second line.** A group whose source library
  isn't found no longer repeats "library not found — pick a source manually" (the "⚠ Source library
  missing" label + pick-source button already say it); a group whose picked source has the same name as
  its library no longer echoes that name back. The info line now appears only when it adds something (a
  *differently*-named source, or "no source picked yet").
- **"(unknown library)" is now "(source unknown — pick a .blend below)"** — these are missing data-blocks
  with no recorded source, and you reconnect the blocks, not a library, so the old label misled.

## [0.3.27] — Fix a crash in Find Missing Textures on a file with missing libraries

### Fixed
- **Fixed a crash (`EXCEPTION_ACCESS_VIOLATION`) during Analyze All's Find Missing Textures step**
  when the file still has missing libraries. `_walk_image_nodes` walks every material/world node tree
  to attribute textures, but a node tree linked from a missing library is dangling — iterating its
  `.nodes` is an uncatchable native crash. It was the one heavy-read path in Find Missing Textures that
  never got the `extract.datablock_risk_reason` guard the mesh/shape-key/geometry/orphan scans already
  use. Now guarded by the same wholesale gate: while any library is missing, node-tree walks are
  skipped (texture→material attribution is simply incomplete until the libraries are relinked/retargeted,
  consistent with every other gated scan). Repro: reconnect/relink on PSM_Stage, save + reload with libs
  still missing, Analyze All (crash.v0.3.26).

## [0.3.26] — Retarget follow-through: reconnecting state, wider gate, clearer messaging

### Added
- **A retargeted broken library now shows its progress.** After you click Retarget, its Broken
  Library Links row greys out to **"→ reconnecting below (N blocks)"** (Relink dropped, Retarget kept
  as a re-jump). It disappears on its own once every one of its blocks is reconnected. Clarifies that
  Retarget *stages* the fix — the link is replaced one block at a time via Reconnect Selected, not
  severed on click.
- **Fully-reconnected libraries are now purged** so they stop showing as broken instead of lingering
  until Save. Reconnect Selected removes any library whose blocks were all reconnected away (0 users,
  still missing on disk) and reports *"N libraries de-linked (fully reconnected)."*

### Changed
- **The Restructure phase is now gated with the rest** (Deduplicate / Purge / Measure) while libraries
  are missing — Audit / Make Local / Flatten / Check Materials read and mutate linked & override data,
  so they're incomplete or wrong until connectivity is fixed. The Connect fix tools (Relink / Retarget /
  Datablock Reconnect) and the read-only Connect diagnostics stay live.
- **The reconnect group's "⚠ MISSING LIBRARY — relink first" flag is now "⚠ Source library missing"** —
  factual, not prescriptive. The old wording predated Retarget and contradicted the info line's own
  "pick a source .blend manually" (you don't have to relink the original library to reconnect — picking
  any source, the split-library case, is the whole point).
- **Shortened the preflight note** to "Linked data from a missing library is skipped — relink in Connect
  first" so it fits even a wide panel.

## [0.3.25] — Second live-review pass: freeze warning, Relink Library button, clearer gating, left-aligned links

### Added
- **Analyze All (and Find Duplicates) now warn before they run:** because the run is
  synchronous, the UI freezes with no live progress bar, so a confirm dialog first sets
  expectations — *"This can take several minutes… Blender will appear frozen until it
  finishes."* Only the button/INVOKE path shows it; headless/scripting (EXEC) is unaffected.

### Changed
- **Broken library links: the folder icon + "no match — pick a file" hint is now a full
  "Relink Library" button,** equal-width with Retarget so the two remedies read as a matched
  pair. Direct rows show the auto-matched target (if any) beside them; indirect rows keep just
  Retarget.
- **The gated Deduplicate / Purge / Measure phases now say so in alert red** — *"Disabled until
  missing libraries are fixed"* — instead of relying on Blender's easy-to-miss disabled dim. The
  gate is driven by `library_stats`, so it applies identically whether you ran Scan All or
  Analyze All (the missing-library state is the same either way).
- **The "fix at the source library" links now sit left-justified next to their file icon**
  instead of floating centre/right (a new `action_left` option on the shared group-header).

## [0.3.24] — Retarget as the safe per-library remedy on broken links + link affordance

### Added
- **Each broken library link now has a "Retarget" button** — the second per-library
  remedy beside Relink, for when Relink can't help (the library is gone, was split into
  several files, or is only linked indirectly). It hands that library's data-blocks to
  **Datablock Reconnect** below (expanding its group) so you re-source each one from your
  file or another library via the existing, backed-up Reconnect Selected. **It never calls
  the Examine/Retarget engine** — that reads what a missing library *provides* (dangling
  placeholders) and crashed Blender at v0.3.21; this reads only the local placeholders that
  link *from* the library, the same safe scan Analyze All already runs. Nothing is severed
  on click — the placeholders are already broken; reconnecting each one replaces the dead
  reference safely. (Realizes the "call it Retarget, but break the library link and let the
  missing items do a Datablock Reconnect" design.)

### Changed
- **Indirect broken libraries no longer offer a misleading Relink.** An indirect library
  (linked only *through* another library, not by this file) can't be relinked from here —
  its parent re-imposes the path on reload — so those rows drop the bulk-Relink checkbox and
  file-picker, show "indirect — can't relink here", and route to **Retarget** instead. They're
  also no longer pre-ticked for Relink Selected (it would have tried and failed on them).
- **"Open in a new Blender" file links now carry a trailing ``↗`` glyph** and stay flat/
  unembossed, so they read as "opens elsewhere." (Blender's Python UI has no coloured or
  underlined text, so the glyph is the closest hyperlink affordance available.)

## [0.3.23] — Connect header consolidation + gate crash-prone phases while libraries are missing

### Changed
- **The Connect phase header now carries the live missing-refs count and the single
  Scan/Rescan-All button.** Stacked under a "Connect" title, the separate "Fix Missing
  Libraries" sub-header read as a redundant second title, so it's gone — along with the
  duplicate "▶ Start here" pointer (its double arrow, and the redundancy, were both called
  out). After a scan the header shows e.g. "3 broken link(s), 31 missing data-block(s)" in
  alert red; the button reads **Scan All** before a scan and **Rescan All** after one (so it
  no longer invites re-running the scan Analyze All just did). The broken-links / retarget /
  reconnect / duplicate-path blocks below each keep their own labelled headline.

### Added
- **The Deduplicate, Purge and Measure phases are now gated while the file has missing
  libraries.** Those checks read heavy content (materials/meshes/geometry/data-blocks) that a
  missing library leaves dangling — they already skip it (via the risk-reason guard) and their
  results would be misleading, so they're drawn disabled beneath a "Fix missing libraries first
  — these skip linked data and stay incomplete until then" note. They re-enable the moment the
  libraries are relinked/retargeted. Restructure stays enabled.

## [0.3.22] — Revert the crashing Retarget-on-broken-links; guard Examine; phase-header polish

### Fixed
- **Fixed a crash (`EXCEPTION_ACCESS_VIOLATION`) when clicking Retarget on a broken library link.**
  v0.3.21 put a "Retarget" button on Broken Library Links rows, but those rows are always MISSING
  libraries, and Examine/Retarget reads the data-blocks a library *provides* — on a missing library
  those are dangling placeholders, and reading one's name crashed Blender (`pyrna_prop_to_py` →
  `PyUnicode_DecodeUTF8` on freed memory). The button and its operator are removed. Missing libraries
  are handled by **Relink** (same row) or **Datablock Reconnect**; **Retarget stays for working
  libraries** in its own section, its documented purpose.
- **Examine now refuses a missing library** with a clear message ("relink it, or use Datablock
  Reconnect") instead of risking the same read — protects the standalone Retarget picker too.
- Good news confirmed in the same crash log: **Analyze All ran all 15 steps and finished** before the
  Retarget click — the v0.3.17 synchronous-sequencer fix held on the real file.

### Changed
- **Phase headers are easier to pick out:** the phase name and its one-line intent now sit on the
  SAME row (was two lines), and each phase's contents are **slightly indented** beneath its header,
  so Connect / Restructure / Deduplicate / Purge / Measure read as titled blocks.

## [0.3.21] — Connect redesign stage 3b-3b: Retarget as a per-library remedy on broken links

### Added
- **Each Broken Library Links row now has a "Retarget" button** beside its Relink file-picker — the
  second per-library remedy. Retarget is the documented fix when a library is *gone or was split*
  into several files (Relink can't help then): it lists everything that library provides and
  re-sources it from your local file or another loaded library. The button seeds and runs the
  existing Retarget Library section (results appear there). This realizes the "per missing library,
  choose the remedy (Relink / Retarget / Merge / fix-at-source)" design — Relink + Retarget now sit
  on the row itself, Merge and fix-at-source already fold into the reconnect groups.
- Content-safe on a missing library: the Examine engine gates every heavy read behind
  `extract.datablock_risk_reason` (the 2026-07-09 hardening), so a missing placeholder is never read.
  Verified headless in Blender 5.1 (registration + reconnect + examine smoke tests pass).

## [0.3.20] — Connect redesign stage 4: "Start here" pointer + libraries-first order locked

### Added
- **A "▶ Start here" pointer** now appears under the Fix Missing Libraries header whenever the file
  has missing libraries: "relink/retarget N missing libraries first; other fixes cascade." Fixing a
  missing library auto-resolves many downstream missing data-blocks/textures, so it's unambiguously
  the first place to act. Uses the same instant, no-scan `library_stats` as the pre-flight banner.

### Notes
- The libraries-first order is fixed by design — Fix Missing Libraries leads the Connect phase (3a)
  and `core/analyze_steps.STEPS` is libraries-first — deliberately NOT dynamically reordered (that
  was judged disorienting); the pointer guides attention instead. This completes the Connect redesign
  arc (3a → 3b-1/2/3 → 4); the Retarget per-row fold remains the one deferred piece.

## [0.3.19] — Connect redesign stage 3b-3: "Open in New Blender" on resolvable reconnect groups

### Added
- **A Datablock Reconnect group whose source library exists on disk now has an "Open in New Blender"
  button** on its header (fix-at-source) — jump into the real library file to fix the renamed/removed
  data-blocks at their source, without disturbing the current session. Shown only when the library
  actually resolves (a broken/missing library has no file to open, and is flagged for relink instead).
  Whether to show it is precomputed at scan time, never `os.stat`'d per redraw (Synology paths).
- Generic second group-header action (`has_action2`) added to the reusable `core.picker` shell, so
  any single-level picker section can expose a second per-group action; unit-tested in `test_picker.py`.

### Deferred
- Folding Retarget's "Examine" onto each per-library row (the other half of 3b-3) is a larger change
  to the Examine engine and is held for a verifiable pass — Retarget stays its own section for now.

## [0.3.18] — Connect redesign stage 3b-2: flag reconnect groups whose library is also a broken link

### Changed
- **A Datablock Reconnect group whose source library is also a broken library LINK is now flagged**
  "⚠ MISSING LIBRARY — relink first" in red, so one per-library row tells the whole story: the link
  is broken AND it left these data-blocks dangling — relink the library (above) before trying to
  reconnect its blocks. Correlation is by exact normalized path only (a local `D:\` copy and the
  SynologyDrive original that merely share a filename are deliberately NOT treated as the same
  library); no match just means no flag.

### Fixed
- Declared the missing `alert` BoolProperty on `FILELINK_PG_picker_row`. Four picker rebuilds
  (reconnect / duplicate-textures / image-dedup / examine) already assigned `item.alert` from the
  bpy-free `core.picker` row, which would have raised `AttributeError` the first time any group set
  `alert=True` — latent until this stage's broken-link flag became the first to do so.

## [0.3.17] — Actually fix the Analyze All crash: run the sequencers synchronously

### Fixed
- **The Analyze All crash is fixed for real** (v0.3.15's warning-suppression did NOT work — it
  reproduced identically at v0.3.16, same `materialMaster.crash` stack). Every crash across
  v0.3.13–v0.3.16 had `rna_operator_modal_cb` in the stack: the modal step-pump drives `run_steps`
  as a *suspended* generator and calls `bpy.ops` sub-operators from inside it, so a Python warning
  during a nested call walks the suspended generator frame and dereferences NULL in CPython's frame
  code. Analyze All / Find Duplicates / Find Flattenable Links now run **synchronously** (`invoke`
  drains the generator via `execute`, a normal for-loop frame that every headless test already uses
  and that has never crashed). The `warnings` suppression stays as cheap console-noise defence.
- **Trade-off:** these three sequencers no longer show a live progress bar or accept ESC-cancel
  mid-run (the UI is busy until they finish). Each individual check is still its own button with its
  own modal progress. Restoring progress for the sequencers needs a generator-free modal (pump one
  step per tick directly) — a later step.

## [0.3.16] — Connect redesign stage 3b-1: Merge (duplicate library paths) moves into Fix Missing Libraries

### Changed
- **The duplicate-library-paths "Merge" list now lives in Fix Missing Libraries** (Connect phase),
  alongside Relink / Retarget / Reconnect, instead of under Check Library Paths. Merging two stored
  path forms of the *same* library is a connectivity fix, not path tidy-up. Absolute-path conversion
  stays under Check Library Paths. First increment of stage 3b (folding the Connect fixes toward
  per-library rows); the list, its radio-select, and its "Use Selected Paths" merge op are unchanged.
- Check Library Paths' headline no longer counts duplicate-library groups (the Merge UI they refer to
  moved), and its "Normalize" button no longer appears for a duplicate-only file — Normalize only ever
  fixed renames/absolute paths, never the merge.

### Note
- The Merge list is still populated by the **Check Library Paths** scan, so it appears in Fix Missing
  Libraries only after you run that check. Folding the dup scan into "Scan All" is a later 3b step.

## [0.3.15] — Fix Analyze All crash (Python warning during the modal step pump)

### Fixed
- **Analyze All no longer crashes Blender (`EXCEPTION_ACCESS_VIOLATION`).** Its sequencer runs each
  step by calling a sub-operator via `bpy.ops` from inside the modal's `run_steps` generator. If any
  Python warning fires during one of those nested calls, CPython's warning machinery walks the
  suspended generator frame and dereferences NULL in the frame code. Confirmed by two v0.3.13
  crashes — `materialMaster.crash.txt` and `PSM_Stage_v5.2.crash.txt` — both stopping at the
  `normalize_library_paths` (Check Library Paths) step, one with and one without a subprocess in
  play, proving the *warning itself* is the trigger, not any single source. Fix: the nested
  sub-operator call is now wrapped in `warnings.catch_warnings()` + `simplefilter("ignore")`, so no
  step-time warning can reach the crashing frame walk.
- **Secondary leak fixed:** `filelink.open_blend_external` ("Open in New Blender") launched the child
  with `subprocess.Popen(...)` and discarded the handle, so Python later emitted a `ResourceWarning`
  on GC — one possible source of the above. Launched handles are now retained and exited ones reaped
  via `poll()`.

## [0.3.14] — Connect redesign stage 3a: reorder Fix Missing Libraries above Check Link Chain

### Changed
- **The "Fix Missing Libraries" section now leads the Connect phase**, so Broken Library Links
  (Relink) is the first fix you see. **Check Link Chain moved to just below it** — it's a
  diagnostic read of the link graph, not a fix, so it belongs after the relink/retarget work it
  informs. No behavior change; ordering only.

## [0.3.13] — Connect redesign stage 2: one "Fix Missing Libraries" section

### Changed
- **Find Broken Library Links + Retarget Library + Find Reconnectable Data-blocks are now a single
  "Fix Missing Libraries" section** in Connect, under one header with one **Scan All** button (runs
  the broken-link, reconnect, and texture scans together). Replaces the three separate sub-sections
  plus the standalone "Find All Missing" button — fewer buttons, one place to fix libraries. The
  Relink / Retarget / Reconnect lists and their apply actions are unchanged; stage 3b will fold
  Relink / Retarget / Merge / fix-at-source per library row.

## [0.3.12] — Retarget Library moves into the Connect phase

### Changed
- **"Retarget Library" moved out of Utilities and into the Connect phase**, right after Find Broken
  Library Links — retargeting a missing or split library IS a connectivity fix, so it belongs where
  you fix broken links rather than buried among one-off tools. The operators are unchanged; only its
  location moved. (Stage 1 of the Connect redesign; later stages fold Relink / Retarget / Merge /
  fix-at-source per library into a single "Fix Missing Libraries" section.) Find Material Across
  Files stays in Utilities — it's a cross-file lookup, not a fix.

## [0.3.11] — "Open in new Blender" links for cross-file fixes

### Added
- **Wherever the addon points at a problem to fix in a different file, the file name is now a
  clickable link** that opens that `.blend` in a separate new Blender instance — so you can go fix
  it without disturbing the current session. First wired into the "Linked — fix at the source
  library" texture list (the library name is the link); it's the foundation for the Connect-phase
  redesign, where each missing library will offer Relink / Retarget / Merge / fix-at-source. New
  `filelink.open_blend_external` operator (launches `bpy.app.binary_path` on the file) and a
  `_draw_file_link` helper that shows the basename without the `.blend` extension.

## [0.3.10] — Crash fix: guard the last two unguarded heavy-read paths (resource, actions)

### Fixed
- **Analyze All crashed on its FINAL step (Analyze Memory/Disk)** on the missing-library file:
  `resource._gather_steps` read `len(mesh.vertices)` for its RAM estimate without the risk guard
  every other geometry path uses, so it was the one place left to crash after v0.3.9 got the run
  all the way to the end. It now skips risky/dangling datablocks via `datablock_risk_reason`
  (which includes the missing-library wholesale gate); a skipped block just isn't counted in the
  footprint estimate.
- **Proactively guarded the last unguarded heavy read in Find Duplicate Data-blocks — actions.**
  `extract_action` reads `fc.keyframe_points`, the same uncatchable native crash risk as mesh/
  shape-key data. An audit of every heavy-read path in the Analyze All flow (mesh geometry,
  shape-key points, action keyframes; image reads are metadata-only and safe) confirms these two
  were the last gaps.

## [0.3.9] — Crash fix (definitive): skip all content reads while a library is missing

### Fixed
- **The recurring Analyze All crash chain is closed at the root.** Four per-datablock guards
  (v0.3.4–0.3.7) each only let the run reach the *next* dangling block; the fifth crash was a
  **fully local** shape key whose point data was corrupt from the file's override loops — which no
  per-block flag can detect. `datablock_risk_reason` now applies a **wholesale gate**: when the file
  has ANY missing library, every content-fingerprint scan (Duplicate Materials / Meshes /
  Data-blocks / Geometry, and Orphans) skips reading heavy data entirely, through each scan's
  existing skip-and-report path (no false duplicates — skipped blocks are never clustered). Fix the
  missing libraries — by **relink OR retarget** — and full fingerprinting resumes automatically.
  This enforces "Connect before Deduplicate" at the engine level, matching the pre-flight banner.
  The library-missing check is cached so it costs nothing per datablock.

## [0.3.8] — Pre-flight risk banner: incomplete-analysis warning for missing libraries

### Added
- **A pre-flight risk banner at the top of "Analyze This File"** when the current file has missing
  libraries: *"N missing libraries — analysis will be incomplete,"* explaining that data linked
  from a missing library can't be read, so the Deduplicate / Geometry / Orphan checks skip it — and
  to relink in Connect first. Instant (no scan), shown only when there's a risk. This surfaces the
  connect-before-deduplicate consequence up front — the very condition behind the recent crash
  chain — so you fix connectivity before running geometry-heavy scans over dangling data.

## [0.3.7] — Crash fix: shape-key risk check missed the Key datablock itself

### Fixed
- **A fourth native crash in Analyze All → Find Duplicate Data-blocks** on the same missing-library
  file. `shape_key_risk_reason` guarded the shape key's OWNER mesh but never the **Key datablock
  itself**, so a Key linked from a missing library (carried by a *local* override owner, which
  looked safe) slipped through and reading its per-point `kb.data` crashed. Now both the Key and
  its owner are risk-checked, and a linked Key or owner is skipped outright (never a local merge
  candidate). Builds on v0.3.6's missing-library detection, which was right but only reached the
  owner.

## [0.3.6] — Crash fix: geometry reads on data linked from a missing library

### Fixed
- **A deeper native crash in Analyze All → Find Duplicate Data-blocks (and, latent, Find Duplicate
  Geometry)** on a file with missing libraries: a datablock linked from a library whose FILE is
  missing can be flagged neither `is_missing` nor a Library Override, yet its geometry / shape-key
  data is dangling — reading it (`extract_mesh`, shape-key coordinates) is an uncatchable native
  null read. `datablock_risk_reason` now also flags "linked from a missing library" (via the owning
  `Library.is_missing`), so **every** geometry-reading path (shape keys, Find Duplicate Geometry,
  Orphans) skips it as "unverified" instead of crashing — not just the one that happened to crash
  first. Shape-key fingerprinting additionally skips any linked owner mesh (never a local merge
  candidate anyway). Follows v0.3.4's depth cap, which stopped the recursion crash but let Analyze
  All reach this deeper one. Root-caused from three successive user crashlogs (PSM_Stage).

## [0.3.5] — Progressive disclosure: passed checks fold into a per-phase tally

### Added
- **Checks that run and find nothing now collapse into a per-phase "N passed" line** (in Connect,
  Restructure, and Purge), so the Analyze panel shrinks to just what needs attention — a healthy
  file is mostly phase headers and short "passed" tallies. Click a tally to expand the passed
  checks (and their buttons) back into place. "Clean" is decided from each check's real count,
  never a text match, so a check with findings can never be hidden by mistake. The primary trigger
  buttons (Analyze All, Find All Missing, Make Local, Audit, Check Materials, the Find Duplicates
  group, Analyze Memory/Disk) always stay visible.

## [0.3.4] — Crash fix (deep/cyclic fingerprint); Size on disk local/linked split

### Fixed
- **Blender crash during Analyze All → Find Duplicate Data-blocks** on a file whose shape-key
  extraction produced a deeply-nested or cyclic structure: `core.fingerprint._round` recursed
  until it overflowed the C stack — a hard `EXCEPTION_ACCESS_VIOLATION` that the caller's
  `try/except` could not catch (a C-stack overflow isn't a Python exception). `_round` is now
  depth-capped (400, far beyond any real payload's ~30 levels); crossing it raises a normal
  `ValueError` that every fingerprint caller already treats as "unverified" — the block hashes to
  `""` and is never merged, instead of crashing. Root-caused from a user crashlog (PSM_Stage file).

### Changed
- **The Health dashboard's "Size on disk" now shows a breakdown** — `34.8 GB (12 GB local + 22 GB
  linked)`: the current `.blend` plus its own external images (local) vs. linked library files and
  their images (linked). The disk walk runs once per redraw (previously it would have doubled).

## [0.3.3] — Confidence tier bulk-select toolbar

### Added
- **A "Select: High / High + Med / All / None" toolbar** on the Reconnectable Data-blocks list:
  tick a whole confidence tier at once instead of hand-ticking each row. "High" grabs the
  exact/near-exact matches, "High + Med" adds fuzzy ones, "All" includes weak guesses, "None"
  clears. Built on a shared confidence ladder (`core.confidence`) so one control means the same
  thing across every graded list (reconnect now; the texture/broken-link lists next), and one
  generic operator (`filelink.select_by_confidence`) drives it. This is the "keep the automation
  opt-in" control from the flow redesign — the safe matches are one click, not a hunt.

## [0.3.2] — Health dashboard: colored status dots + two-column layout

### Changed
- **The Health dashboard now lays its metrics in two columns** (collapsing to one when the
  Properties editor is narrow) and marks each with a **colored status dot**: green for a
  resolved/good metric, red (with red value text) for one needing attention — missing libraries,
  or an outstanding duplicate/missing/orphan count. Blender panels can't color arbitrary label
  text, so the dots (fixed-color `COLORSET_*` icons) carry the signal that the mockup showed in
  colored text; red text uses the one native color Blender exposes (`alert`).

## [0.3.1] — Health dashboard with live metric deltas

### Added
- **"Current File Data" is now a Health dashboard.** It shows the file's key metrics and, as you
  work through issues, how each has moved **since you opened the file** (baseline → now):
  **Size on disk** and **Linked libs** always; **Render RAM** once you've profiled and **VRAM**
  once Analyze Memory/Disk has run; **Duplicate Materials / Meshes** and the **missing-texture /
  broken-library / orphan** counts once a scan first surfaces a non-zero value — each then tracked
  down to zero (e.g. "14 → 0 ✓"). The baseline resets when you open another file. Size on disk is
  the current `.blend` + linked libraries + external (unpacked) images, computed instantly (no
  scan). Raw RAM/VRAM byte counts are now stashed by the resource/profile operators for the deltas.

## [0.3.0] — Analyze re-sequenced into a 6-phase pipeline; Automated Cleanup removed

A larger UX change than the 0.2.x stream (hence the minor bump), from a full flow review: the
"Analyze This File" section now leads the user biggest-fix-first instead of presenting an
undifferentiated stack of buttons.

### Changed
- **"Analyze This File" is now one ordered repair pipeline.** Both the panel's top-to-bottom
  order AND the "Analyze All" run follow the same sequence, grouped under labeled phase dividers:
  **Connect** (fix missing/broken references first) → **Restructure** (simplify the link graph) →
  **Deduplicate** → **Purge** → **Measure** (footprint). The four duplicate scans are contiguous
  now instead of scattered through the run.
- **"Find All Missing" also scans missing textures.** It previously ran only the broken-library-
  link and reconnectable-data-block scans, silently skipping textures — the one kind of "missing"
  a user would most expect it to cover.
- **Find Resolution Variants moved into the "Find Duplicates" group** (it's redundant-material
  data too) instead of floating as a standalone row. It stays out of the "Find All Duplicates"
  one-click sequencer — still a different kind of analysis (multi-res footprint, not strict
  duplicates).

### Added
- **Advisory "what to do" lines** under the two detection-only checks (Check Materials, Check
  Armature Deformation): they now say how to fix the flagged issues by hand, and why there's no
  safe bulk fix, instead of being silent dead ends.

### Removed
- **The "Automated Cleanup" section is gone.** The re-sequenced, self-paced Analyze flow already
  walks through the same fixes in order, so the separate one-click batch panel — its Scan /
  Apply Selected operators, per-function include toggles, post-Apply save option, and savings
  report — was redundant. Automation is moving into per-section best-guess defaults rather than a
  single magic button.

## [0.2.121] — Find Duplicate Materials/Geometry crash fix; Find Duplicates UI polish

### Fixed
- **Crash**: Find Duplicate Materials (F3) could take Blender down mid-sweep on a file with a
  Library Override material — `_gather_steps` only skipped its risky deep node-tree read for
  `mat.is_missing`, never for `mat.override_library is not None`, the other half of the
  documented disease class (`extract.datablock_risk_reason`, already used by Examine Library and
  Find Orphans). Root-caused from a user-supplied crashlog with an embedded Python traceback
  pointing straight at `extract.py:86`'s `sock.links` read. Fixed by switching to the shared
  `datablock_risk_reason` check. Found and fixed the identical latent gap in Find Duplicate
  Geometry (`ops/instance_dedup.py`, meshes) proactively — same narrow `is_missing`-only check,
  never exercised into a crash yet only because a Library-Override mesh is a rarer shape than an
  override material.

### Added
- **Find Duplicates** (the "Find Duplicate Data-blocks/Materials/Geometry/Textures" group) now
  shows a not-run/some-run/all-run status icon on its own header, and a not-run/done icon on each
  of its 4 child buttons — the one collapsible-group section that didn't already have this,
  unlike every Analyze-row sibling.
- **"Delete Empty Material Slots" button** on Check Materials' "Empty material slots" row —
  removes every empty slot the last scan found (backup first), previously read-only.
- **Find Duplicate Materials' result list is now collapsible**, and Automated Cleanup's own copy
  of that same list collapses independently (defaults collapsed) instead of sharing one expand
  state with the standalone section.
- **Find Content Dups now scans linked images too** (previously local-only), reporting a linked
  count per group/section; the merge step still only ever touches local duplicates.

### Changed
- Dropped the confusing leading dash from every "(−N)" removable-count label across Duplicate
  Data-blocks/Materials/Geometry/Textures — now just "(N)".
- "Examine Library" section retitled "Retarget Library" (the operator/button still reads
  "Examine").

## [0.2.120] — Examine Library: content verification extended to the manual-pick paths

### Added
- **Pick a Specific Item, Search a Folder, and a new "Search a Folder (all unresolved)" bulk
  operator now get the same content check the in-memory suggestion path has had since v0.2.118/119.**
  Previously all three trusted an exact/numbered NAME match alone and unconditionally staged the
  row for Apply — including, for Search a Folder, a purely FUZZY match, the exact same
  "same-generic-name ≠ same content" risk already fixed for in-memory suggestions
  (`smoke_examine_library.py`'s `Plane.070`/`Plane.099` case). Now: pass 1 (peek + rank) is
  unchanged; pass 2 real-links whichever candidate an exact/numbered match picked — never a fuzzy
  one, same `allow_fuzzy=False` reasoning as the in-memory path — and content-verifies it via the
  existing `_content_graph_match` fingerprinter (Material/Mesh/NodeTree), gated identically to
  `_populate_examine_rows`: `"differs"` or `"unverified"` blocks auto-select but keeps the row
  staged for manual review; a fuzzy-only top match is staged but never real-linked or auto-selected
  at all. Unblocked by `tests/probe_double_link.py` (2026-07-14): confirmed real-linking the SAME
  library a second time later (Apply Selected's own by-source reload) safely reuses the exact same
  datablock rather than duplicating it, so pass 2's verify load can be disposable — no caching or
  threading needed into Apply Selected.
- **New bulk operator** (`filelink.examine_bulk_search_folder`, fronted by the thin
  `filelink.examine_bulk_pick_folder` file-picker, same two-op split as
  `ops.image_relink.FILELINK_OT_relink_folder_search`) resolves EVERY still-unresolved row
  (`suggested_kind == "none"`) in one folder walk instead of one row at a time — peeks every needed
  `bpy.data` attribute per file in pass 1, then groups pass 2's real-link by source file so a folder
  walk resolving several rows from one file only opens it once. `ModalProgressMixin`-based (ESC to
  cancel), matching every other folder-walk in this addon. Button appears above Apply Selected
  whenever at least one row is still unresolved.
- **UI**: the manual-pick dropdown (`ui.panels.FILELINK_UL_examine_picker`) gained a compact
  content-check icon next to the `target` enum (checkmark/error/question, no label — the dropdown
  already eats row space). Manually swapping the dropdown to a candidate pass 2 never checked resets
  `graph_match`/`selected` (`ui.panels._on_examine_target_changed`) so a stale "verified" auto-select
  can't silently ride along on an unverified swap.
- New regression test `tests/smoke_examine_content_verify.py`: proves a genuinely-different-geometry
  candidate found via Pick a Specific Item, Search a Folder, and the bulk operator is all blocked
  from auto-apply the same way, a genuinely-identical one auto-selects, a fuzzy-only match never
  gets real-linked, and the dropdown-swap reset actually fires.

## [0.2.119] — Fix: v0.2.118's own content check treated "unverifiable" as "safe to auto-apply"

### Fixed
- **A missing placeholder in the examined library could still get auto-merged onto a same-named
  local data-block, immediately after v0.2.118 shipped to close exactly this hole.** Found live on
  the user's own `Asset_bundle.blend`: its `Plane.070` was itself a missing placeholder (broken
  link within that library), and Examine Library still auto-applied a merge onto a real, unrelated
  local `Plane.070`. Root cause: `_content_graph_match` correctly refused to read the missing
  placeholder's (nonexistent) geometry — reusing `extract.datablock_risk_reason`, the native-crash
  guard — but returned `""`, the SAME result used for "unsupported kind, name-only trust is fine
  here" (Object, Image, ...). `_populate_examine_rows` only blocked auto-apply on `"differs"`, so
  "couldn't verify" fell through to the old blind trust — exactly backwards, since a missing
  placeholder's content is GONE and is the single LEAST verifiable case there is. Fixed by giving
  the risk-flagged path (and any extraction that raises) its own `"unverified"` result, distinct
  from `""` (genuinely unsupported kind, e.g. Object/Image — behavior there is intentionally
  unchanged). Apply Selected now skips both `"differs"` AND `"unverified"` rows; the UI's
  `_graph_match_suffix` shows "(unverified — needs manual check)" so it's clear WHY, not just that
  nothing happened. New regression test `tests/smoke_examine_library_missing_vs_local.py`
  reproduces the exact shape (a linked Mesh reduced to a missing placeholder via a deleted source
  file, colliding by name with a real local Mesh) and asserts `graph_match == "unverified"` and
  Apply Selected does not stage it.

## [0.2.118] — Fix: Examine Library could silently merge unrelated Mesh/NodeTree data-blocks

### Fixed
- **Apply Selected could merge two completely unrelated data-blocks that happened to share one of
  Blender's own generic auto-names.** Found live on `human_bundle.blend`: an architectural
  column-cap Mesh and an unrelated clothesline Mesh both carried the name `Plane.070` (pure
  coincidence of creation order in a heavily-merged file) — Examine Library treated the exact
  name match as unambiguous and `user_remap`'d one onto the other, so the column-cap object
  silently inherited the clothesline's geometry/Array modifier. The same disease very likely hit
  several `NT*`-prefixed shader node-group duplicates too, corrupting their library-override
  references (seen as "Data corruption: ... removing all override data" on the next file open).
  `core/reconnect.py`'s "exact" match tier is pure name equality with no content check — safe for
  a meaningfully-named block, not for a generic one. Fixed by extending the existing Material
  node-graph fingerprint check (`ops/examine_library.py`, previously `_material_graph_match`,
  Material-only and advisory-only) into `_content_graph_match`, covering Mesh and NodeTree too,
  and — the actual fix — a confirmed content mismatch now BLOCKS Apply Selected from auto-touching
  that row instead of only annotating it in the UI. `ops/extract.py` gained `extract_node_tree()`
  (shared `_extract_tree()` walk behind both it and `extract_material()`, with a `NodeGroupOutput`
  fallback for node GROUPs, which don't have a Material/World/Light output node);
  `core/fingerprint.py` gained `fingerprint_node_tree()`. Content checks never read a missing
  placeholder's or Library Override's data (`extract.datablock_risk_reason`, the same native-crash
  risk class already mitigated in Find Orphans) — such a pair reports unverified and keeps the old
  name-only trust, a known residual gap. New regression coverage in
  `tests/smoke_examine_library.py` reproduces the exact Mesh (two differently-sized same-named
  planes) and NodeTree (two differently-valued same-named node groups) collisions and asserts both
  the flag AND that Apply Selected's auto-apply properties end up off.
- **Node/node-tree fingerprinting missed a node's OUTPUT-socket default value** (e.g. a
  `ShaderNodeValue`/RGB node's entire meaningful state lives on its output, not an input or a
  node-level property) — found while building the above fix's regression test, two differently-
  valued Value nodes hashed identical. `ops/extract.py`'s node walk and `core/fingerprint.py`'s
  `_node_hash` (plus the no-output-node fallback multiset) now include each node's output-socket
  values in the hash. Pre-existing gap in the F3/F4/Examine Library fingerprinter, not introduced
  by the above — worth knowing if a past "identical" material-diff verdict involved an unlinked
  Value/RGB-style node.

## [0.2.117] — Fix: Examine Apply Selected's real "0 remapped" bug, plus a persistent results summary

### Fixed
- **Apply Selected could resolve the WRONG data-block and silently no-op, reporting "Made 0
  local, remapped 0" for every ticked row.** Root cause, confirmed via the v0.2.116 diagnostics
  against a real production file: `ops/examine_library.py`'s per-row apply loop looked up each
  row's target with a PLAIN-NAME lookup (`target_coll.get(row.name)`), which has no library
  disambiguation. In a heavily-merged file, a local data-block can coincidentally share the exact
  name of a linked one (Blender allows this across libraries — no forced rename), so the lookup
  had no guarantee of returning the specific linked block the row was populated from; every row
  looked "stale" even though nothing had changed since the scan. Fixed by switching to `bpy.data`'s
  `(name, filepath)` tuple lookup, which is library-qualified. Covered by a new regression test,
  `tests/smoke_examine_library_name_collision.py`, that reproduces the exact shape of the bug
  (linked + same-named local block, one Apply Selected call, asserts the linked one resolves).

### Added
- **Apply Selected's result now persists in the panel** instead of only flashing as a one-shot
  toast. Applying used to clear `filelink_examine_rows` and fall straight back to the pre-scan
  look, so a user who missed the toast (or scrolled away) had no way to tell whether anything had
  actually happened — new WindowManager string `filelink_examine_apply_summary` holds the same
  text the toast shows, drawn in the panel until the next Examine or Apply Selected call.

## [0.2.116] — Diagnostics: Examine Apply Selected's silent "0 remapped" now self-explains

### Changed
- **`Apply Selected`'s "Made X local, remapped Y" toast now reports WHY when rows were skipped**
  (`N stale, M unresolved — see console for details`), and prints a line per skipped row naming
  the exact reason (row already changed since scan vs. no resolvable target, with the row's
  suggestion fields). Found live, 2026-07-09: a second Apply Selected pass on `human_bundle.blend`
  reported "Made 0 local, remapped 0" for 46 rows that had all shown an in-memory match moments
  earlier, and there was no way to tell from the toast alone which of the two skip conditions in
  `ops/examine_library.py::FILELINK_OT_examine_apply_selected` every row hit, or why. Not a fix —
  the next occurrence's console output will point at the exact cause instead of requiring another
  live repro.

## [0.2.115] — Fix: Examine Library could suggest remapping onto ANOTHER broken library's placeholder

### Fixed
- **Examine Library's in-memory suggestion pool could offer a candidate that was itself a missing
  placeholder from a DIFFERENT broken library** — real bug found live on a production file with
  two libraries both unreadable on disk (`human_bundle.blend`, `Asset_bundle.blend`): each can
  independently hold a same-BASE-name missing block purely by coincidence of Blender's own
  `.NNN` dedup-suffix numbering (e.g. one wants `hanger.001`, an unrelated asset in the OTHER
  broken library separately wants `hanger.002` — the "numbered" match tier strips both to base
  `hanger` and calls it a match). Remapping one placeholder onto another placeholder doesn't fix
  anything — the link is still broken, just pointed at a different broken thing — and the apply
  silently "succeeds" with zero visible effect, which is how a user's staged Apply Selected could
  report success yet leave the data-block count completely unchanged after a reload.
  `ops/examine_library.py::_in_memory_pools` now skips any candidate that is itself
  `is_missing`. New end-to-end smoke test (`tests/smoke_examine_library_missing_collision.py`)
  reproduces the exact two-broken-library collision and confirms no suggestion is offered.
- **`core/imagematch.py::best_match`** now skips (and logs) a single candidate that raises
  during scoring instead of aborting the whole modal search — a real, never-reproduced TypeError
  surfaced live mid-scan against a multi-thousand-file library search and cost the user every
  match already staged. New pytest coverage.
- **`ops/orphans.py`'s Find Orphans** now prints the exact datablock name right before each risky
  fingerprint read — a real `EXCEPTION_ACCESS_VIOLATION` crash (2026-07-09, `PSM_Stage_v5.2`)
  turned out to be on a LOCAL mesh, a corruption class the existing `datablock_risk_reason`
  mitigation never covered (its `is_missing`/`override_library` checks only ever apply to linked
  IDs, but the fingerprinting branch that crashed only runs on local data). A native access
  violation can't be caught with try/except, so this is a breadcrumb, not a fix — the next
  occurrence's console output will end with the exact datablock name instead of an anonymous
  crash log.

## [0.2.114] — New: Check Armature Deformation (detection-only scan for the "weighted to the wrong bone" bug)

### Added
- **New Analyze panel scan, "Check Armature Deformation"**, for a bug class found live on a real
  production file: a mesh vertex weighted (fully or partially) to the wrong bone — in the real
  case, Reallusion/CC facial `CTRL_*` control bones instead of a body `DEF_*` deform bone, most
  likely from an indiscriminate body→garment weight-paint transfer — looks completely normal in
  rest pose (nothing wrong in `mesh.vertices`) but gets dragged to that bone's posed position once
  the Armature modifier evaluates, sometimes thousands of units away. Invisible until posed, so it
  silently corrupts geometry that scan/export/render pipelines can't easily catch otherwise.
  Detection works by comparing each edge's REST length against its DEPSGRAPH-EVALUATED (posed)
  length — a healthy mesh keeps this ratio close to 1x (isometric-ish skin/cloth deformation);
  the real broken case measured ~84,000x against a default threshold of 20x. `core/deform_check.py`
  (bpy-free ratio math + `Report` building, 16 new pytest cases), `ops/deform_check.py` (modal
  chunked scan over every visible mesh with an enabled, vertex-group-bound Armature modifier,
  reusing one `evaluated_depsgraph_get()` across all objects), new `FILELINK_OT_scan_deform_issues`
  operator, new `FILELINK_PG_deform_row` / `FILELINK_UL_deform_rows` results list in
  `ui/panels.py` with a per-row checkbox for a future fix pass.
- **This release is detection/review only, by explicit design** — nothing is mutated. The results
  list exists so a future fix pass has something to select from, but no Apply/Fix action exists
  yet.
- **Linked objects/meshes are flagged but visibly tagged "linked — fix at source"** rather than
  silently scanned-and-ignored or mishandled — a fix would need to edit both the Object's vertex
  group definitions and the Mesh's per-vertex weight assignments, so either being linked blocks a
  local fix. `ObjectDeformSummary.is_locally_fixable` (`obj.library is None and mesh.library is
  None`) flows through to the report message and the UI row's icon/label.
- New end-to-end smoke test `tests/smoke_deform_check.py` (synthetic 2-bone armature + 2-vertex
  mesh, one bone posed 1000 units away vs. a healthy control pair posed a small amount) confirms
  the real operator flags the exploded object and not the healthy one, run against actual Blender
  5.1.

## [0.2.113] — Vendor catalog ID (Poliigon-style 4+ digit SKU) is now a primary match signal

### Changed
- **The fuzzy matcher now recognizes a bare 4+ digit token (Poliigon's own asset IDs — 7174,
  8819, 9322, ...) as a vendor catalog ID and weights it far more heavily than an ordinary
  descriptive word.** A shared catalog ID between the wanted and candidate name is now strong
  enough on its own to rescue a match whose descriptive words differ too much to pass the
  ordinary stem-similarity floor (e.g. a heavily vendor-abbreviated name), and pushes a
  same-channel, same-resolution match to "high" confidence. Conversely, **two DIFFERENT catalog
  IDs now hard-disqualify a match even if every other word is identical** — two different
  Poliigon products should never be treated as interchangeable just because their descriptive
  names happen to collide. Doesn't override a genuine channel conflict (a normal map still can't
  stand in for a roughness map just because the SKU matches) — `core/imagematch.py`'s
  `NameParts.catalog_id` / `_CATALOG_ID_RE`. New pytest coverage.

## [0.2.112] — Fix two real fuzzy-match misses found live (MemSaver cache hijack + dot-joined pseudo-extension)

### Fixed
- **A third-party RAM-saving addon (MemSaver) can silently rewrite an Image's stored `filepath`
  to point at its own hashed cache derivative instead of the original texture — if that cache
  entry later goes missing, the stored path has zero relation to the real texture name anymore,
  so neither exact nor fuzzy matching could ever bridge it, even though the image's own
  DATABLOCK NAME still preserved the real identity.** `ops/image_relink.py::_wanted_basename`
  now detects a `memSaver_cache` path and falls back to the datablock name in that case. Found
  live against a real missing texture (`FabricRope001_AO_1K_jpg.002`) that both "Search a
  Folder" and "Suggest Matches" came up empty on.
- **The pseudo-extension tokenizer only stripped an underscore-joined fake extension
  (`"..._jpg.001"`), not a dot-joined one (`"...1K.jpg.002"`)** — the latter is Blender's own
  ordinary dedup-on-collision naming when the requested datablock name already looked like it
  had a real extension baked in, leaving a stray `"jpg"` stem token that dragged an
  otherwise-perfect match from "high" confidence down to "low". `core/imagematch.py`'s
  `_PSEUDO_EXT_RE` now matches either separator.
- New pytest coverage for both in `tests/test_imagematch.py`.

## [0.2.111] — Confidence-floored bulk accept + Missing Textures categories

### Added
- **"Accept High Matches" / "Accept High/Med Matches" buttons** next to the existing "Accept
  All" in the Possible Matches (fuzzy Suggest Matches) results area — bulk-accept proposals at
  or above a confidence floor instead of an all-or-nothing choice. All three buttons share one
  operator (`filelink.accept_all_matches`, now taking a `min_confidence` property) rather than
  three near-duplicate operators; the ranking itself lives in a new
  `core.imagematch.meets_min_confidence` so the ops layer doesn't duplicate it.
- **Missing Textures now splits into three collapsible categories** — Missing Material Textures,
  Missing World Textures, Missing Other Textures — each with its own summary line ("N of M
  matched") and collapsed by default, same as every other section's group headers. World
  attribution is a new `core.imagematch`-style node-tree walk over `bpy.data.worlds` (mirroring
  the existing per-material walk); a texture that isn't found in any material's or world's node
  tree falls into Other. New `core.picker.CategorySpec` / `flatten_category_group_member_rows`
  generalize the existing single-level `GroupSpec` shell to a 3-level category → group → member
  shape (new pytest coverage in `tests/test_picker.py`); the per-group "point at folder" bulk
  action stays Material-category-only (a same-named World/Other group could otherwise pull in
  the wrong rows through the shared `item.material` lookup). Not yet live-verified in Blender.

## [0.2.110] — Fix Check Materials crash on large reports

### Fixed
- **Crash fixed: the Analyze panel's inline report disclosure (`_draw_report_detail` /
  `_feature_tree_nodes`, used by Check Materials and every other inline-disclosure section)
  re-parsed the ENTIRE stashed report from JSON and rebuilt its whole tree on every single panel
  redraw, unconditionally — even while collapsed. Fine for a small report; a real crash hit on a
  production file where Check Materials flagged ~1410 issues (many near-duplicate materials each
  with several broken image nodes), where a full JSON-parse + tree-rebuild on every redraw became
  a real perf/stability risk.** `_feature_tree_nodes` now caches its parsed result per feature,
  keyed on the exact raw JSON string last seen — a stashed report only changes when a scan
  actually re-runs (a fresh raw string), so this is an exact cache key with no staleness risk,
  it just skips redundant reparses of identical data between scans. NOT yet live-verified against
  the actual crash (see `docs/TODO.md` for the pending live-repro checklist).

## [0.2.109] — Material-name Tier 2 fuzzy relink + matcher precision fixes

### Added
- **Tier 2 material-name matching** for the fuzzy folder-search relink flow: a missing texture
  Tier 1 leaves unmatched (or only at medium/low confidence) now escalates to searching other
  `.blend` files under the same folder for a material of the same name — vendor names get
  manually shortened in-scene (`FabricFloralDuckeggJacquard001` → `DuckEgg`), so the new
  `core.material_search.score_material_name` matches bidirectionally by containment rather than
  token overlap. Once found, that file's own images are harvested and channel-matched against
  just its rows — a small, correct-source corpus instead of guessing across the whole library.
  A Tier 2 hit always replaces a Tier 1 medium/low (the right source beats a shakier name guess
  against the wrong one).
- Channel-alias vocabulary expanded from real texture-library naming: `REFL` (reflection),
  `DISP16`/`BUMP16`/`NRM16` (16-bit map suffix), `MicroN(Mask)`, `Cavity(Map)`/`GradAO`,
  `TransMap`/`Translucency`, plus new first-class channels `SSS`, `VertexColorMap`, `WeightMap`,
  and `ORM` (kept separate from AO/roughness/metallic — a packed ORM map isn't interchangeable
  with any single standalone channel map).

### Fixed
- The fuzzy folder-search candidate index no longer includes non-image files (a reorganized
  library that keeps a per-asset `.blend` alongside its textures was getting that `.blend`
  scored as a texture candidate itself, since name-matching strips extensions before scoring).
- `_wanted_basename` used `os.path.basename` on a bpy `//`-relative path — on Windows that's
  `ntpath`, which misreads a leading `//` as a UNC host\share marker and silently returns `''`
  for the single most common stored-path shape (`//folder/file.ext`), breaking fuzzy matching
  outright for those rows.
- The tokenizer didn't recognize `_png`/`_jpg`-style pseudo-extensions (some FBX/vendor export
  pipelines can't embed a literal `.` in an embedded texture name, so they substitute `_png` —
  Blender may then add its own real `.001` dedup suffix on top). That stray extra stem token
  was dragging otherwise-perfect matches down to "low"/"medium" confidence for no real reason.
- **Relink Selected** no longer aborts the entire ticked batch when one target file went missing
  between staging and relinking (e.g. a network-drive sync lag) — it relinks everything with a
  valid target and reports the rest, left ticked for a retry, instead of doing nothing at all.
- Accept / Accept All / Accept Material's Matches no longer auto-tick a proposal whose file
  doesn't actually exist — only a confirmed-present file gets ticked, so a stale proposal can't
  silently reach Relink Selected untested a second time.
- `imagematch.classify()` is now memoized — it's a pure function of the filename, so a large
  library's fuzzy match no longer re-tokenizes the same names millions of times over in one
  blocking modal step.

## [0.2.108] — Automated Cleanup (Scan/Review/Apply Selected) + Find Material Across Files

### Added
- **Automated Cleanup** panel: Scan every included cleanup function (Make Local / Duplicate
  Materials / Duplicate Geometry / Orphans), review and tick/untick individual results, then
  Apply Selected — one backup at the start, a before/after savings summary at the end. Make
  Local gained real per-datablock selection for the first time (previously all-or-nothing).
- **Find Material Across Files** (Utilities): recursively search every `.blend` under a folder
  for a material name, wildcard or substring, entirely offline (no Blender launch).

### Fixed
- Make Local's per-item selective apply now correctly leaves un-ticked linked datablocks (and
  their library) untouched, retries across multiple passes so a ticked child whose dependency
  only just went local still gets localized, and reports an accurate localized count instead of
  the attempted count.

## [0.2.107] — Multi-hop Link Chains display cleanup

### Changed
- **Find Flattenable Links'** multi-hop route rows no longer repeat the current file's own name
  on every line, and no longer inline the whole chain as one string — each hop in the route now
  shows as its own row with a link icon, matching the rest of this UI's tree rendering. (The
  "Link Directly" repoint action originally scoped alongside this was dropped — there's no real
  per-datablock action to take at the bpy level for a route that's also linked directly.)

## [0.2.106] — Phase R: renamed to File & Link Utilities

### Changed
- **Full rename**, package id `assetdoctor` → `file_link_utilities`, all `ASSETDOCTOR_*` class
  prefixes → `FILELINK_*`, `bpy.ops.assetdoctor.*` → `bpy.ops.filelink.*`, `assetdoctor_*`
  WM/Scene properties → `filelink_*`, `AssetDoctorPreferences` → `FileLinkPreferences`. GitHub
  repo and gh-pages URL renamed to `FileLinkUtilities`. See `docs/USER_GUIDE.md` and
  `README.md` for the one-time upgrade note (saved Preferences don't carry over; the gh-pages
  repository entry must be re-added under the new URL).

## [0.2.105] — Phase 2 live-verify fixes

### Changed
- **Find Orphans'** fake-user-only and identical-datablock sections now share the same
  virtualized `ASSETDOCTOR_UL_tree` every other diagnostic uses, instead of hand-rolled,
  unindented row loops — matters most on a real production file (1000+ identical-datablock
  groups instantiated every row regardless of scroll position before this).
- **Find Duplicates** is now a collapsed-by-default sub-section: expanding it reveals the 4
  individual scan buttons (Data-blocks / Materials / Geometry / Textures) each with their own
  results area, so one problematic scanner doesn't block running the other 3. "Find All
  Duplicates" still runs all 4 in sequence from the section's own header.
- **Check Materials** now looks inside node GROUPS: a group that internally mixes shaders
  (e.g. a "hair shader" convenience group wrapping Principled Hair + Glossy + Transparent) is
  classified as "Combined Shader" instead of being lumped under its group's own name as if it
  were one single shader type.
- "Make Local Impact" renamed to "Make Local" (the Analyze section already names the analysis,
  not its effect).
- Path Normalization's "Normalize" button now hides once the result is clean instead of
  offering a no-op.

### Fixed
- Every inline Analyze-button disclosure (Check Materials, Check Link Chain, Make Local, …)
  could jump back to the top of its list on any click — the shared expand-state prop these
  sections all share was never wired into the existing scroll-position-preservation logic.
- Make Local's own result line showed a generic "nothing found" instead of the real linked/
  library count when nothing needed making local, with the real text only visible one row
  down inside a pointless expand arrow.
- Find Flattenable Links' summary line kept an expand arrow with nothing real behind it when
  no flattenable characters were found.
- The Audit This File dependency-loop "no user found" message could read as "this datablock
  doesn't exist" when it actually meant "exists, but has no object instance in the current
  view layer."
- The expand/collapse triangle's tooltip was a multi-paragraph developer docstring instead of
  a short user-facing hint.

## [0.2.90 – 0.2.104] — UI virtualization + backlog cleanup

### Changed
- **Every report/picker list now virtualizes.** Reports tab, Resource Usage, every inline
  Analyze-button disclosure, and the Missing Textures / Duplicate Textures / Datablock
  Reconnect / Examine Library pickers all draw through the same `UIList`-backed renderer —
  closes out the last few manually-drawn row lists, which could show blank rows once
  deeply expanded on a large result.
- **Click-to-select now leaves a sticky per-row icon** (found / no live user / unresolved)
  instead of a one-shot status message that was easy to miss.
- F8's hierarchical link-map layout is root-at-top (the file that pulls everything in sits
  at the top; pure assets sink to the bottom).

### Added
- **Check Materials** — a new read-only diagnostic: lists materials grouped by shader type,
  flags dangling node links and Image Texture nodes pointing at a missing file, and flags
  empty material slots.
- Broken Library Links rows flag whether a library is linked *directly* or only reachable
  through another linked library.

### Fixed
- A blank library name could appear in "Fix at Source" / Examine Library suggestions on
  Windows (a same-folder `//Name.blend` path was misread as a UNC path).
- Find Orphans could crash scanning a mesh belonging to a Library Override or missing
  placeholder; the same missing/override safety check Find Duplicates already used for
  shape keys now applies to every fingerprinted datablock type.
- Find Duplicate Data-blocks showed no progress/couldn't be cancelled on a file with one
  very large collection (e.g. hundreds of Actions) — now chunks per-item like the other
  duplicate scanners.

## [0.2.29 – 0.2.89] — Properties-editor migration, Flatten, fuzzy texture matching

### Changed
- Migrated from the 3D-viewport N-panel to **Properties → Scene**, restructured into
  **Analyze / Cleanup & Fixes / Utilities** panels as the feature set grew well past the
  original 6.
- Duplicate Textures redesigned around per-family keeper dropdowns + a material-mismatch
  eyedropper override.

### Added
- **Flatten** — detect Library-Override-with-transform "posing" setups (e.g. posed
  characters linked from a rig library) and flatten them to real local data, including a
  grouped "Flattenable Links" view and a background-subprocess-based cross-file resolver
  for more complex cases.
- **Datablock Reconnect** — for a missing linked datablock, pick a source `.blend`,
  auto-suggest the closest-matching name (exact / renamed / fuzzy), and relink + remap in
  one step, grouped by source library.
- Fuzzy texture-name matching (`core/imagematch.py`) with a confidence score and a
  channel-synonym table, wired into Possible Matches; substitute-from-material and
  substitute-from-another-`.blend` corpora.
- Resolution Variants (multi-resolution texture footprint report, opt-in standardize).

## [0.2.11 – 0.2.28] — F8 link-map graph, missing data-blocks, safe-to-delete

### Added
- **F8** — a self-contained interactive HTML dependency graph (force-directed, zoom/pan/
  search, no external resources) as an alternative to the flat F1 report.
- Missing **data-block** detection (`id.is_missing`, distinct from a missing *library*),
  grouped by source library.
- **Safe to delete?** — reverse-dependency check: given a file, list what would break if it
  were removed, before you remove it.

## [0.2.5 – 0.2.10] — F6 texture relink & dedup suite

### Added
- Missing-texture relink: doubled-path-prefix fix, cross-drive remap, folder search by
  filename, and a group-by-directory-or-material "point group at folder" bulk action.
- Duplicate-texture cleanup: `.NNN`-family lossless merge (content-verified first) and a
  content-hash dedup pass across the whole file regardless of naming.

## [0.2.0 – 0.2.4] — F7 Link & Dependency Doctor

### Added
- Recursive, offline (BAT-based) folder dependency scan: broken/absolute/circular links,
  duplicate library blocks, inconsistent paths, most-linked libraries.
- Live in-file analysis: `.NNN` duplicate-datablock census, override/dependency loops.
- Library path fixes (normalize + relink missing) and datablock-level link inspection
  (what one file links from another, in either direction — the basis for later cycle-
  breaking and reconnect work).

## [0.1.10] — Report/Resource panels: virtualized UIList (fixes blank rows)

### Fixed
- **Blank rows in large reports.** The Report and Resource trees were drawn as manually-built
  rows, which the N-panel doesn't virtualize — so expanding a big category (e.g. an F1 link map
  with dozens of broken-link findings) left every row past ~13 blank (only the expand triangle
  drew). Both panels now use a real **`UIList`** (`template_list`), which virtualizes and scrolls,
  rendering correctly for any size. The 200-row draw cap and its "+N more — use Export…" hint are
  gone (no longer needed).

### Changed
- The flattened tree rows (`core.tree.flatten_visible`) are now materialised into a
  `WindowManager` `CollectionProperty` (`ASSETDOCTOR_PG_tree_row`) that the new `ASSETDOCTOR_UL_tree`
  draws; `ops.report_store` rebuilds it whenever the shown report, the selected feature, or its
  expansion changes. The report JSON stays the source of truth (export/title unchanged).

## [0.1.9] — Duplicate Materials report (local/linked)

### Changed
- **Duplicate Materials report restructured.** The top row now shows the headline
  **`XX (YY Local & ZZ Linked)`** (total removable duplicates, split by local vs linked), with two
  child rows **Local** / **Linked** that expand to the actual material lists. The redundant
  bottom "Summary" row was removed. Apply behaviour is unchanged (the remap plan is the same).
- Generic report model gained an optional **`Finding.detail`** (right-aligned per-row value) and
  **`Report.category_details`** (per-category header override) — both serialized; used by F3 and
  available to any feature. `report_to_tree` renders them.

## [0.1.8] — progress bars for every scan/apply

### Added
- **Modal progress bar + ESC for F3, F4, Geometry, and Resource Analyzer.** Find Duplicate
  Materials, Scan Orphans (+ Purge), Instance Duplicate Geometry, and Analyze Resource Usage now
  run as modal operators with the shared progress bar/status and ESC-to-cancel — the heavy
  per-datablock fingerprinting/estimation is chunked through a `_gather_steps` generator, so big
  files no longer freeze the UI while they "look hung". Only **Profile Render** stays synchronous
  (a single render can't be chunked).
- **`ModalProgressMixin`** (`ops/progress.py`) — packages the modal/timer/ESC/progress-bar
  pattern with a per-tick time budget, so an operator only supplies a `run_steps(context)`
  generator that yields `(fraction, status)`. `execute` drains it for EXEC_DEFAULT/scripting/tests.

### Changed
- F3 (materials) and Geometry instancing apply paths **no longer push a native Undo step** (modal
  operators); they continue to take a timestamped **auto-backup before mutating** (same safety
  model as F2). Restore from the backup to revert.

## [0.1.0] — M0 Scaffold — unreleased

### Added
- Repo scaffold: `blender_manifest.toml` (Extension, Blender 5.0+), thin
  `register`/`unregister`, `AssetDoctorPreferences` (backup dir, auto-backup toggle,
  resolution-token regex).
- `core/` bpy-free package:
  - `report.py` — `Finding`/`Report` with JSON + CSV export. **Tested.**
  - `graph.py` — `DepGraph` with roots/leaves/cycle detection. **Tested.**
  - `fingerprint.py` — `strip_resolution_tokens` implemented & tested; node/mesh hashers
    stubbed for M2.
  - `blendscan.py` — BAT wrapper stub for M1.
- `ops/` scaffold operators (F1–F4) that register and report "implemented in M#".
- `ui/panels.py` — AssetDoctor N-panel with one button per feature.
- pytest harness (`conftest.py`, `pyproject.toml`) running the bpy-free core tests outside
  Blender; tests for report, graph, and `strip_resolution_tokens` (incl. doctests).
- `README.md`, `docs/ARCHITECTURE.md` (design + risks + milestone roadmap), `.gitignore`.

### Added (BAT bundling — TODO #2 resolved)
- Bundled `blender_asset_tracer==1.20` (pure-Python wheel) via `blender_manifest.toml`
  `wheels`. Confirmed `requests` is NOT required for dependency tracing (probe with
  requests blocked under Blender 5.1), so the requests/charset_normalizer chain is
  intentionally excluded to keep the extension cross-platform.
- `tests/smoke_register.py` (headless register/unregister + BAT-presence check) and
  `tests/probe_bat_imports.py` (confirms blendfile/trace import without requests).
- `[build] paths_exclude_pattern` so dev-only dirs stay out of the release zip.
- Verified: manifest parses, extension builds (`assetdoctor-0.1.0.zip`), and the addon
  registers/unregisters in Blender 5.1.

## [0.1.0] — M1: F1 folder link map — unreleased

### Added
- `core/blendscan.py` — BAT-backed offline reader: `scan_file` (reads `LI` Library
  blocks; Blender 5.x stores the path in the block's `name`, `//` = relative),
  `resolve_blend_relative`, `iter_blend_files`, and `map_folder` building the `DepGraph`.
- `core/graph.py` — added `to_dot()` Graphviz export.
- `core/f1_linkmap.py` — `build_link_report` flags broken links, absolute (non-portable)
  paths, circular references, unreadable files, plus a summary.
- `ops/scan_folder.py` — folder picker → report → writes `<root>/.assetdoctor/linkmap_*.{json,csv,dot}`.
- Fixtures: `tests/fixtures/build_linkproj.py` generates `linkproj/` (scene → libA → libB,
  relative links) — committed so pytest runs bpy-free. `tests/conftest.py` puts the BAT
  wheel on sys.path.
- Tests: `tests/test_blendscan.py` (7) — direct link, leaf, path resolution, transitive
  graph, clean-project report, broken-link detection, DOT smoke. `tests/smoke_f1.py`
  runs the operator end-to-end in Blender.

### Verified
- 28 pytest tests pass; F1 operator runs in Blender 5.1 (scene→libA→libB, exports written).

## [0.1.0] — M2: content fingerprinting — unreleased

### Added
- `core/fingerprint.py` — `fingerprint_material` (recursive hash from the Material Output,
  invariant to node naming/order, **resolution-agnostic** via image base-name),
  `fingerprint_mesh` (counts + rounded coords + topology, float-jitter tolerant),
  `fingerprint_image` (identity, resolution-SENSITIVE). Canonical JSON + SHA1 with float
  rounding.
- `ops/extract.py` — bpy→dict extractors (materials/meshes/images) feeding the hashers;
  generic node-prop extraction that skips cosmetic/layout attrs and normalises image refs.
- `core/cluster.py` — `group_identical` (fingerprint → duplicate groups), used by F3/F4/M6.
- Tests: `tests/test_fingerprint.py` (1K==2K equality, naming/order invariance,
  topology/param sensitivity, mesh tolerance, image res-sensitivity), `tests/test_cluster.py`,
  and `tests/smoke_fingerprint.py` validating the contract against real Blender 5.1 data.

### Verified
- 44 pytest tests pass. In Blender 5.1: a 1K and 2K material hash identically end-to-end;
  wood≠metal; mesh identity works; image identity stays resolution-sensitive.

## [0.1.0] — M3: F4 orphans, fake users & duplicates — unreleased

### Added
- `core/f4_orphans.py` — `classify` (orphan / fake_only / in_use / linked, per verified
  Blender 5.1 semantics: orphan=users0, fake_only=fake&users1) and `build_orphan_report`
  (orphan + fake-only lists, identity clusters via `group_identical` with per-member status,
  summary).
- `ops/orphans.py` — gathers datablocks across the common collections (materials/meshes/
  images fingerprinted), builds the report, and offers an optional `purge_orphans`
  (`bpy.data.orphans_purge`) behind the report-first/auto-backup safety model.
- `ops/safety.py` — `auto_backup` writes a timestamped `.blend` copy (save_as_mainfile
  copy=True) before any mutation, honouring the prefs backup dir / toggle.
- Tests: `tests/test_f4_orphans.py` (classification, orphan/fake lists, identity clusters,
  type isolation, linked exclusion, summary) + `tests/smoke_f4.py` end-to-end.

### Verified
- 50 pytest tests pass. In Blender 5.1: orphan/fake-only/identical classification correct;
  purge removes orphans while fake-user and in-use data survive.

## [0.1.0] — M4: F3 material dedup — unreleased

### Added
- `core/f3_materials.py` — `parse_name_list`, `choose_canonical` (whitelist > non-blacklisted
  > forced; tie-break local-over-linked then highest resolution), `build_dedup_plan`
  (fingerprint clusters → plan + report, flags linked victims).
- `ops/material_dedup.py` — gathers materials (fingerprint + max texture res + unique id that
  disambiguates local/linked same-name), report-first dry run; on Apply (after auto-backup)
  `user_remap`s duplicates onto the canonical and removes local victims. `REGISTER`+`UNDO`.
- `prefs.py` — `material_whitelist` / `material_blacklist` (comma/newline, glob-aware).
- Tests: `tests/test_f3_materials.py` (list parsing, all canonical-selection rules, plan +
  summary, linked-victim flagging) + `tests/smoke_f3.py` end-to-end.

### Verified
- 60 pytest tests pass. In Blender 5.1: a 1K+2K material pair clusters, the 2K wins canonical,
  Apply removes the 1K and repoints its object's slot to the 2K; whitelist override works.

## [0.1.7] — Make Local speed + collapsible panels

### Fixed
- **Select-in-Outliner for all report findings.** Clicking a finding now selects the object(s)
  that use the datablock, even for non-object kinds (materials, meshes, images, node groups) —
  it walks `user_map()` from the datablock up to the using objects. Previously only a few types
  resolved, so Make Local report items appeared to do nothing.
- **Make Local on complex files: observability + safety.** Added per-pass and per-100-datablock
  **heartbeat logging**, `log.debug` of each datablock before make-local (the debug log's last
  line pinpoints a hanging call), a **no-progress safety break**, and **bounded** purge loops —
  so a long run is visible (it stopped logging mid-run before) and can't grind indefinitely.
  Also fixed a latent **library-purge** bug (the user check was reversed and could force-remove
  still-used libraries).

### Changed
- **Make Local performance.** The apply path now does one **bulk**
  `bpy.ops.object.make_local(type='ALL')` call (internally batched) before the per-ID passes,
  instead of localizing thousands of datablocks one at a time. The per-ID passes only mop up
  what the bulk op can't reach (linked collections, node groups, un-resolved overrides), so the
  pathological ~hours run on complex files (botaniq/engon, circular links + overrides) collapses
  to seconds/minutes. Bulk pass is guarded by `poll()` + RuntimeError and degrades gracefully to
  the pure per-ID path. Verified by `smoke_f2` (New File + In Place still fully local).

### Added
- **Collapsible panel sections.** Each feature (Project, Make Local, Duplicate Materials, Orphans,
  Duplicate Geometry, Resource Analyzer, Utilities) is now a native child panel of the main
  AssetDoctor panel, so each has its own collapse triangle and Blender remembers its open/closed
  state. Utilities defaults closed.
- **Clickable "Add-on Preferences" in Utilities.** The old static "Lists/backups: Add-on
  Preferences" hint is now a button (`assetdoctor.open_preferences`) inside the Utilities section
  that opens Preferences with AssetDoctor expanded (`preferences.addon_show`, with a fallback).
- **Make Local progress bar + cancel.** Apply now runs as a **modal** operator with a live
  progress bar and status text in the panel (and the OS task-bar), and **ESC to cancel** —
  mirroring the F1 folder scan. New File reverts cleanly on cancel; In Place reports it's
  partially localized and points at the backup. Core work is a `localize_steps` generator that
  `execute` (scripting/tests) drains synchronously and the modal steps one chunk per timer tick.
- **Shared progress widget.** The folder-scan's progress props were generalized to one
  `assetdoctor_op_*` WindowManager trio + `ops/progress.py` helpers, drawn once at the top of
  the panel, so every modal action reuses a single progress bar.
- **Debug log starts fresh** on each enable and on each **file open** (`load_post` handler;
  the Scene-prop update didn't fire on load before). File is `AssetDoctorDebugLog.txt`.

## [0.1.6] — report drawing fix

### Fixed
- **Reports no longer show blank rows** on large projects. The N-panel doesn't virtualize
  manually-drawn rows, so a report with hundreds of findings left rows blank past a point
  (data was fine — the Export was complete). Now: **categories start collapsed**, each shows a
  **count**, and the tree draw is **capped (200 rows)** with an "use Export… for the full list"
  hint. Affects every report (Link Map, Materials, etc.). The full fix (a virtualized `UIList`)
  is tracked in docs/TODO.md "Report UI v2".

### Changed
- Duplicate-materials report category title capitalized ("Duplicate Materials").

## Unreleased — auto-update repository

- Published a self-hosted **extension repository** so Blender auto-updates: `gh-pages` branch
  serves `index.json` (from `extension server-generate`) + the version zips via GitHub Pages at
  **https://rickpalo.github.io/AssetDoctor/index.json**. Users add that URL once
  (Preferences → Get Extensions → Repositories). See `docs/RELEASING.md`.

## [0.1.5] — M7 step 4: Profile Render (real peak RAM)

### Added
- **Profile Render** button (Resource Analyzer): renders the current frame and reports
  Blender's **real peak system RAM** (whole process, via OS — Windows `GetProcessMemoryInfo`
  / Unix `getrusage`), shown in the Resource panel to complement the estimates.
  Real VRAM is intentionally not attempted (not exposed by Blender's Python API); F5's
  VRAM estimate covers that side.
- `core.resource.peak_process_ram_bytes()` (bpy-free) + test; `tests/smoke_profile.py`.

This completes **F5 / M7**.

## [0.1.4] — M8: Report system v2

### Added / changed (TODOs)
- **Persistent per-feature reports.** Each scan (Link Map / Make Local / Materials / Orphans /
  Geometry) keeps its OWN report — a Materials report survives a later Geometry scan. The
  Report panel gets a selector row to switch between whichever reports exist; clear removes
  only the shown one. (Replaces the single overwritten slot; F5 resource stays separate.)
- **Per-line tooltips.** Tree row labels are now tooltip-bearing buttons whose hover text is
  the FULL line (full broken-link path, full message + size) — readable despite the narrow
  panel. Clicking a row does its natural action (expand/collapse a parent, select a leaf).
- **Export/print.** "Export…" on the Report and Resource panels writes the current view to a
  `.txt` (indented tree) or `.csv` (reports) for printing/sharing.
- **Select-in-Outliner** (per chosen behaviour): selecting a finding selects + activates the
  user object(s) (Outliner follows the active object) without rearranging editors; a material
  also gets its slot highlighted; orphan/unused data shows a hint to use Outliner → Blender
  File / Orphan Data.
- Tests: `core/tree.all_keys` + updated `smoke_report.py` (persistence, selector, toggle,
  export, select, clear — 9/9).

## [0.1.3] — M7 step 3: F5 Resource Analyzer

### Added
- **Resource Analyzer (F5).** "Analyze Memory/Disk" estimates usage by **datablock type**
  (Images, Meshes, …), each datablock counted once, biggest-first, with est. RAM / est. VRAM /
  accurate disk + user count, shown in a new **Resource Usage** panel (reuses the tree widget).
  Chosen over a scene→object hierarchy to avoid double-counting shared data.
- `core/resource.py` (image/mesh byte estimates + `human_bytes`), `core/resource_tree.py`
  (by-type tree + totals), tree `detail` column + JSON (de)serialization, generalized expand
  toggle (works for both the report and resource trees).
- Tests: `test_resource.py`, `test_resource_tree.py` (+ tree round-trip) and `smoke_resource.py`.

### Changed (TODOs)
- Documentation icon pinned **far right** in the panel header (title · version · ⟶ icon).
- Debug log renamed **`AssetDoctorDebugLog.txt`** (was debugLog.txt).

## [0.1.2] — M7 step 2: instance duplicate geometry

### Added
- **Geometry dedup / instancing.** `core/geometry_dedup.py` (`build_instance_plan`,
  `choose_canonical`) finds identical-but-separate mesh datablocks used by different objects
  and plans to collapse them onto one shared datablock (turning wasteful copies into
  instances). Kind-agnostic engine; covers meshes now (curves/others extend via a fingerprint).
- `ops/instance_dedup.py` — report-first dry run; on Apply (after auto-backup) `user_remap`s
  duplicate meshes onto the canonical (most-used local one) and removes the copies. Panel:
  "Duplicate Geometry" box (report / apply). Report flows into the M7-step-1 viewer.
- Tests: `tests/test_geometry_dedup.py` + `tests/smoke_instance.py` (two identical separate
  meshes → instanced onto one; duplicate removed; distinct geometry untouched).

### Versioning
- **3rd-digit bump per completed step**; the N-panel header shows `vX.Y.Z` (from the manifest)
  so the installed build is verifiable. The built zip is named `assetdoctor-<version>.zip`.

## [0.1.1] — M7 step 1: report viewer (shared tree widget)

### Added
- **In-Blender report viewer.** Every feature now stashes its `Report` on the WindowManager
  and a collapsible **Report** panel renders it as an expandable tree (category → finding →
  item) with severity icons, expand/collapse toggles, and **click-to-select** the datablock a
  finding refers to (objects directly; materials/mesh-data via the objects that use them).
- `core/tree.py` (bpy-free): `TreeNode`/`Row`, `report_to_tree` (rolls up severity, parses
  `Type/Name` refs but not file paths), `flatten_visible` (tree + expanded keys → indented
  rows). `Report.from_dict`/`from_json` round-trip.
- `ops/report_store.py`: `stash_report` + toggle/clear/select operators.
- Tests: `tests/test_tree.py` (tree build, ref parsing, flatten/expand) + `tests/smoke_report.py`
  (operator → stash → reconstruct → toggle → select → clear, in Blender). Report round-trip test.

### Notes
- This is the shared widget the F5 Resource Analyzer (M7 step 3) will reuse. Panel *draw* is
  interactive; the data pipeline behind it is covered by tests.

## [0.1.0] — Build hygiene + compressed-file support — unreleased

### Fixed / clarified
- **Compressed .blend support confirmed.** Blender 5.x bundles `zstandard` (0.25.0 in 5.1)
  in its own Python, so BAT reads zstd-compressed files (Blender's default since 3.0) with
  nothing extra bundled. Locked by `tests/smoke_compressed.py`. (Our committed fixtures are
  uncompressed, which had hidden this.)
- **Removed a stray bundled `zstandard` wheel** from `wheels`/manifest and the
  **Windows-only `platforms` pin** that came with it — both unnecessary given the above, and
  the pin would have made the extension Windows-only. Package is platform-independent again
  and back to ~135 KB (was ~645 KB).
- **Excluded `tools/` from the shipped extension** (kept in the repo as a dev utility).
  `tools/find_datablocks.py` (originally find_billboards.py) is a host-Python offline search; on host Python it
  needs `pip install zstandard` for compressed files (Blender's bundle doesn't apply there).

## [0.1.0] — Responsive scan + doc link (TODO 4 + doc icon) — unreleased

### Added
- **Modal folder scan** (TODO 4): the F1 scan runs as a modal operator — time-bounded batch
  per timer tick, **ESC to cancel**, live progress bar in the panel (WindowManager props),
  wait cursor and status-bar text. `core.blendscan` refactored into
  `new_scan_result`/`scan_into`/`map_folder`; `f1_linkmap.report_from_scan` shares report
  building between the modal and synchronous (`execute`) paths.
- **Documentation icon**: right-aligned HELP button on the panel header (`draw_header`) opening
  the repo docs; `website` added to `blender_manifest.toml`. (URL is a placeholder pending push.)
- Tests: incremental-vs-synchronous scan equivalence + `report_from_scan` + `bat_available`.

### Verified / pending
- 69 pytest tests pass (core of the modal scan verified: incremental == synchronous).
- Blender-side checks (register smoke, zip rebuild) and the interactive modal/progress + doc
  icon are pending — deferred to avoid competing with an active render.

## [0.1.0] — UX batch (TODO 1/2/5) — unreleased

### Added
- **Project folder field + Scan button** (TODO 5): `Scene.assetdoctor_scan_dir` path picker;
  the scan operator runs the stored folder (only opens the browser when none is set).
- **Tooltips** (TODO 1): per-variant `description()` classmethods on the make-local / dedup /
  orphans operators; descriptions on the new Scene props.
- **Utilities section + Enable Debug Log** (TODO 2): `Scene.assetdoctor_debug_log` toggle and
  `log.py` (an `assetdoctor` logger). INFO findings → console + file; DEBUG detail → file.
  `debugLog.txt` is written next to the .blend (or Blender temp if unsaved). All four
  operators now log instead of bare `print`.
- Tests: `tests/test_log.py` + `tests/smoke_utils.py`.

### Notes
- Deferred to a planned "M7: UX & feedback" milestone — report viewer (TODO 3) and
  progress/responsiveness via a modal folder-scan operator (TODO 4). See docs/TODO.md.

## [0.1.0] — M5: F2 recursive make-local — unreleased

### Added
- `core/f2_makelocal.py` — `build_makelocal_report` groups linked datablocks by source
  library, counts indirect (transitively-linked) ones, summary.
- `ops/make_local.py` — dry-run report; on Apply iterates `make_local(clear_liboverride=True)`
  over all ID collections until nothing is linked, then purges emptied libraries.
  - **New File** mode (default): writes a fully-local copy (`save_as_mainfile copy=True`) then
    `revert_mainfile()` so the working file's linked setup is untouched. Requires a saved file.
  - **In Place** mode: flattens the current file after an auto-backup.
- Tests: `tests/test_f2_makelocal.py` + `tests/smoke_f2.py` (New File output BAT-verified to
  have zero library links; In Place leaves no linked data and no libraries).

### Fixed / discovered
- After `make_local`, `Library.users` can report a phantom count even when `user_map()` shows
  no real users. `_purge_libraries` now trusts `user_map()` to remove stale libraries.
  Regression covered by `smoke_f2.py` ("no libraries remain").

### Verified
- 63 pytest tests pass. In Blender 5.1: both F2 modes correct on the scene→libA→libB fixture.

### Notes
- Next: M6 — F1 cross-file object-duplication census (reuses M2 fingerprints) + polish.
