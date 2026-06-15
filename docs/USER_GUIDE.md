# AssetDoctor — User Guide

AssetDoctor is a Blender **5.0+** extension for **mapping, diagnosing, and cleaning** the
asset debt that builds up in multi-file projects: tangled library links, duplicate and
multi-resolution materials, orphaned data, duplicated geometry that could be instanced, and
unclear memory/disk usage.

- [Installation & updates](#installation--updates)
- [Core ideas & safety model](#core-ideas--safety-model)
- [The AssetDoctor panel](#the-assetdoctor-panel)
- [Features](#features)
  - [F1 — Scan Link Map (folder)](#f1--scan-link-map-folder)
  - [F2 — Make Local](#f2--make-local)
  - [F3 — Duplicate Materials](#f3--duplicate-materials)
  - [F4 — Orphans & Fake Users](#f4--orphans--fake-users)
  - [Duplicate Geometry (instancing)](#duplicate-geometry-instancing)
  - [F5 — Resource Analyzer](#f5--resource-analyzer)
- [The Report panel](#the-report-panel)
- [Preferences](#preferences)
- [Utilities & the debug log](#utilities--the-debug-log)
- [The find_datablocks dev tool](#the-find_datablocks-dev-tool)
- [Glossary](#glossary)
- [Troubleshooting / FAQ](#troubleshooting--faq)

---

## Installation & updates

**Requirements:** Blender **5.0 or newer**.

### Recommended: install from the auto-updating repository
1. **Edit → Preferences → System →** enable **Allow Online Access**.
2. **Edit → Preferences → Get Extensions →** the **⌄ (Settings) dropdown → Repositories… → ＋ Add Remote Repository**.
3. URL: `https://rickpalo.github.io/AssetDoctor/index.json` — tick **Enabled** and **Check for Updates on Startup**.
4. Back in **Get Extensions**, search **AssetDoctor** and **Install**. Blender will offer updates automatically from then on.

![Adding the remote repository](images/install-repository.png)

### Alternative: install from disk (no auto-update)
**Get Extensions → ⌄ → Install from Disk…** and pick `assetdoctor-<version>.zip`
(from the [Releases page](https://github.com/rickpalo/AssetDoctor/releases)). You'll update by
reinstalling newer zips.

> The panel header shows the installed version (e.g. `v0.1.5`) so you can confirm what you have.

---

## Core ideas & safety model

- **Linked vs appended.** *Linked* data is referenced live from another `.blend` (a library);
  *appended* data was copied in with no link kept. See the [Glossary](#glossary).
- **Report-first → Apply.** Every destructive action has a **dry-run report** first; you only
  change anything with the explicit Apply button.
- **Auto-backup.** Before any mutation, AssetDoctor saves a **timestamped `.blend` backup**
  (`<name>_assetdoctor_<timestamp>.blend`) next to your file (or to a folder you set in
  Preferences). In-session changes also support **Undo (Ctrl+Z)**.
- **Where results go.** A summary pops up in Blender's header; the **full detail** appears in
  the [Report panel](#the-report-panel), the System Console (Window → Toggle System Console),
  and — if enabled — the [debug log](#utilities--the-debug-log).

---

## The AssetDoctor panel

Open the 3D viewport sidebar (**press `N`**) and pick the **AssetDoctor** tab.

![The AssetDoctor N-panel](images/panel-overview.png)

The header shows the **version** and a **? documentation icon** (opens this repo). Sections:

| Section | Buttons |
|---|---|
| **Project (folder)** | folder field + **Scan Link Map** (F1) |
| **Make Local** | **Report (dry run)**, **→ New File**, **→ In Place** (F2) |
| **Duplicate Materials** | **Find Duplicates (report)**, **Dedup & Remap (apply)** (F3) |
| **Orphans & Fake Users** | **Scan (report)**, **Scan + Purge Orphans** (F4) |
| **Duplicate Geometry** | **Find Duplicates (report)**, **Instance & Merge (apply)** |
| **Resource Analyzer** | **Analyze Memory/Disk**, **Profile Render (real RAM)** (F5) |
| **Utilities** | **Enable Debug Log** |

Every button has a tooltip describing exactly what it does (and, for the apply variants, that
it backs up first).

---

## Features

### F1 — Scan Link Map (folder)

**What:** recursively reads every `.blend` under a folder **offline** (via Blender Asset
Tracer — no files are opened in Blender) and maps which file links which.

**Use:**
1. Set the **Project (folder)** path.
2. Click **Scan Link Map**. A progress bar shows files scanned; press **Esc** to cancel.

![Scan progress](images/scan-progress.png)

**Reports** (in the [Report panel](#the-report-panel), under "Link Map") and exports to
`<folder>/.assetdoctor/linkmap_<timestamp>.{json,csv,dot}`:
- **broken links** — a file references a library that's missing,
- **absolute paths** — non-portable links that should be relative,
- **circular references** — files that link each other in a loop,
- **unreadable files**, and a **summary** (file/link counts, roots vs leaf/asset files).

The `.dot` export opens in Graphviz to visualize the dependency graph.

> Read-only — F1 never modifies your files.

### F2 — Make Local

**What:** turn linked assets into local data so a file is self-contained (for archival,
render-farm submission, or handoff).

**Modes:**
- **Report (dry run)** — lists everything linked, grouped by source library, flagging
  *indirect* (transitively-linked) data. No changes.
- **→ New File** *(recommended)* — writes a fully-local copy `<name>_local.blend` beside your
  file and **leaves your working file's links untouched** (the session is reverted afterward).
  Requires the file be saved first.
- **→ In Place** — flattens the **current** file to local. Takes an auto-backup first; restore
  from that backup if you need to undo.

Apply shows a **progress bar + status** while it works and can be cancelled with **ESC**
(New File reverts cleanly; In Place leaves the file partially localized and points at the backup).

Both modes resolve **library overrides**, repeat until nothing is linked, then purge the
emptied libraries. On large/complex projects the heavy work is done in one batched pass, so it
finishes in seconds/minutes rather than grinding per-datablock.

### F3 — Duplicate Materials

**What:** find duplicate and **multi-resolution near-duplicate** materials (e.g. a 1K and a 2K
version of the same wood) and collapse them onto one canonical material.

How "same" is decided: a **resolution-agnostic fingerprint** of the material's node graph plus
**image base-name** matching (so `wood_1k` and `wood_2k` are treated as the same).

**Use:**
- **Find Duplicates (report)** — groups duplicates and shows which would be kept vs remapped.
- **Dedup & Remap (apply)** — auto-backup, then repoint every user of a duplicate onto the
  **canonical** material and remove the local duplicates. Supports Undo.

**Choosing the canonical** (configurable in [Preferences](#preferences)):
1. a **whitelisted** name is always kept;
2. a **blacklisted** name is never kept;
3. otherwise: prefer local over linked, then the **highest texture resolution**.

> Linked duplicates can be remapped *away from* (their local users repointed) but can't be
> deleted from their source library — the report says so.

### F4 — Orphans & Fake Users

**What:** find data that's unused or kept alive only by a Fake User, and group identical copies.

Classification (verified against Blender 5.1):
- **Orphan** — `users == 0` (removed on reload/save anyway),
- **Fake-user only** — kept solely by its Fake User,
- **Identical groups** — datablocks with the same content, each member tagged orphan / fake / in-use
  (so you can spot an orphan that's identical to something still in use).

**Use:**
- **Scan (report)** — read-only.
- **Scan + Purge Orphans** — auto-backup, then delete true orphans (`bpy.data.orphans_purge`).
  Fake-user and in-use data are preserved.

### Duplicate Geometry (instancing)

**What:** find identical-but-separate **mesh** datablocks used by different objects (wasteful
Shift-D copies) and make those objects share **one** datablock — i.e. turn copies into instances,
saving memory.

**Use:**
- **Find Duplicates (report)** — lists instanceable groups and how many datablocks would be freed.
- **Instance & Merge (apply)** — auto-backup, then repoint the duplicates onto one shared mesh and
  remove the copies. Supports Undo.

### F5 — Resource Analyzer

**What:** estimate what's using **System Memory / Video Memory / Disk**, broken down **by
datablock type** (Images, Meshes, …), each datablock counted **once**, biggest first.

**Use:**
- **Analyze Memory/Disk** — fills the **Resource Usage** panel: per-type totals, drill into
  individual datablocks showing est. RAM / est. VRAM / disk + user count.
- **Profile Render (real RAM)** — renders the current frame and reports Blender's **real peak
  system RAM** (whole process). Needs a camera; slow on heavy scenes.

![Resource Usage panel](images/resource-panel.png)

> **RAM and VRAM are estimates** (Blender exposes no exact per-datablock byte counts) and are
> labeled as such; **disk** sizes are accurate. Use *Profile Render* for a real RAM figure.
> Real per-object VRAM isn't available from Blender's Python API.

---

## The Report panel

Below the main panel, the **Report** panel (collapsed by default) shows results as an
**expandable tree** (category → finding → item).

![The Report panel](images/report-panel.png)

- **Persistent per feature.** Each scan keeps its own report — a Materials report survives a
  later Geometry scan. Use the **selector row** at the top to switch between the reports you've run.
- **Tooltips.** Hover any row to see the **full text** (e.g. a full broken-link path) even when
  the narrow panel truncates it.
- **Click to select.** Clicking a finding that names a datablock **selects the object(s)** that
  use it (the Outliner follows the active object); a material also gets its slot highlighted.
  Orphan/unused data with no object users shows a hint to view it via Outliner → Blender File /
  Orphan Data.
- **Export…** writes the current report to a **`.txt`** (indented) or **`.csv`** file.
- The **X** in the panel header clears the shown report.

The **Resource Usage** panel uses the same tree, with size columns and its own **Export…**.

---

## Preferences

**Edit → Preferences → Add-ons → AssetDoctor** (Extensions list).

![Preferences](images/preferences.png)

- **Auto-backup before mutating** *(on by default)* — save a timestamped `.blend` before any change.
- **Backup Folder** — where backups go (empty = next to the current file).
- **Resolution Tokens** (regex) — tokens stripped when matching multi-res textures/materials
  (default handles `_1k`, `_2k`, `-2048`, Blender's `.001` dup suffix, …).
- **Material Whitelist / Blacklist** — comma/newline lists (glob `*` allowed) controlling which
  material is kept as canonical in F3.

---

## Utilities & the debug log

**Utilities → Enable Debug Log** writes a detailed **`AssetDoctorDebugLog.txt`** next to your
`.blend` (or Blender's temp folder if unsaved). Tick it, reproduce an issue, then send that file
along when reporting a bug. (Normal summary/findings always print to the System Console too.)

---

## The find_datablocks dev tool

`tools/find_datablocks.py` is a standalone **command-line** utility (not part of the installed
add-on) that searches `.blend` files by datablock name **offline**:

```
python tools/find_datablocks.py <directory> <phrase> [--kind KIND] [--type TYPE] [--first]
```
- `--kind` — object (default), action, material, mesh, image, world, collection, scene, texture,
  node_group, armature, curve, camera, light/lamp, speaker, lattice, metaball, sound.
- `--type` — object sub-type filter (only with `--kind object`).
- plain phrase = case-insensitive substring; wildcards (`*?[ ]`) = glob; `--first` stops at the newest match.

```
python tools/find_datablocks.py "E:/proj" walk --kind action     # find an animation
python tools/find_datablocks.py "E:/proj" "wood*" --kind material
python tools/find_datablocks.py "E:/proj" "tree*" --type mesh
```
Run `--help` for the full list. On your host Python it needs `pip install zstandard` to read
compressed files (or run it with Blender's Python, which already has it).

---

## Glossary

- **Linked** — data referenced live from another `.blend` (a *library*). Edit it in the source file.
- **Appended** — data copied into the current file with no link kept.
- **Library override** — a local, editable override of linked data (replaced proxies in 2.9+).
- **Orphan** — a datablock with no users; removed when the file is reloaded/saved.
- **Fake User** — a flag that keeps an otherwise-unused datablock from being purged.
- **Instance** — multiple objects sharing one datablock (memory counted once).
- **Near-duplicate material** — same material at a different texture resolution.

---

## Troubleshooting / FAQ

- **F1 finds nothing / errors on every file.** Ensure the folder actually contains `.blend`
  files. Compressed files need `zstandard`, which Blender 5.x already bundles (the add-on uses
  Blender's Python, so this "just works").
- **"Make Local → New File" says to save first.** New File mode reverts the session after writing
  the copy, so the file must be saved on disk. Save, then retry (or use In Place).
- **The repository doesn't show updates.** Enable **Allow Online Access** (Preferences → System),
  confirm the URL ends in `/index.json`, and **Refresh** in Get Extensions.
- **Memory numbers look off.** RAM/VRAM are estimates; use **Profile Render** for real peak RAM.
- **I want to undo an Apply.** In-session ops (F2 In Place, F3, F4 purge, geometry instancing)
  support **Ctrl+Z**; an auto-backup `.blend` is also written beforehand.

Found a bug? Enable the debug log, reproduce, and open an issue with `AssetDoctorDebugLog.txt`:
https://github.com/rickpalo/AssetDoctor/issues
