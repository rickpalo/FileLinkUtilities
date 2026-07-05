# File & Link Utilities

A Blender **5.0+** extension to **map, diagnose, and clean** the asset debt in multi-file
projects — tangled library links, duplicate/multi-resolution materials, orphaned data,
duplicated geometry, and unclear memory/disk usage.

(Renamed from **AssetDoctor** — see [CHANGELOG.md](CHANGELOG.md) for the migration note if
you have an existing install.)

![The File & Link Utilities panel](docs/images/panel-overview.png)

## Features

| Feature | What it does | Mode |
|---|---|---|
| **Scan Link Map** (F1) | Recursively map which `.blend` files link which across a folder; flag broken / absolute / circular links. Offline (no files opened in Blender). | Read-only |
| **Make Local** (F2) | Make linked assets local — as a separate `*_local.blend` copy or in place. Resolves overrides; purges emptied libraries. | Mutating |
| **Duplicate Materials** (F3) | Find duplicate & **multi-resolution** (1K/2K) materials and remap them to one source, via white/black lists. | Mutating |
| **Orphans & Fake Users** (F4) | Find orphaned / fake-user-only data, group identical copies, optionally purge true orphans. | Read-only + optional purge |
| **Duplicate Geometry** | Find identical separate meshes and **instance** them onto one datablock to save memory. | Mutating |
| **Resource Analyzer** (F5) | Estimate RAM / VRAM / disk by datablock type; **Profile Render** for real peak RAM. | Read-only |

Every mutating action is **report-first → explicit Apply**, with a timestamped `.blend`
auto-backup before any change. Results show in an in-panel **Report** viewer (persistent per
feature, expandable, click-to-select, export to txt/CSV).

## Install

**Auto-updating (recommended):** Preferences → System → **Allow Online Access**; then
Get Extensions → **⌄ → Repositories → Add Remote Repository** →
`https://rickpalo.github.io/FileLinkUtilities/index.json` → install **File & Link Utilities**.

**From disk:** download the latest `file_link_utilities-*.zip` from
[Releases](https://github.com/rickpalo/FileLinkUtilities/releases) →
Get Extensions → **⌄ → Install from Disk…**

**Upgrading from AssetDoctor:** the package id changed, so this can't auto-update over an
existing install. Remove the old `rickpalo.github.io/AssetDoctor/index.json` repository entry
(and the AssetDoctor add-on) in Preferences, then add the new repo above and install fresh.
Saved preferences (backup folder, resolution-token regex, etc.) are keyed by package id and
won't carry over — reconfigure them once after reinstalling.

Full instructions and feature walkthrough: **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)**.

## Documentation

- **[User Guide](docs/USER_GUIDE.md)** — complete manual (install, every feature, preferences, FAQ)
- [Architecture](docs/ARCHITECTURE.md) · [Releasing](docs/RELEASING.md) · [Changelog](CHANGELOG.md) · [Backlog](docs/TODO.md)

## Development

`core/` is pure-Python and **bpy-free**, so it runs under plain pytest (no Blender):

```pwsh
pip install pytest
pytest
```

In-Blender behavior is verified with headless smoke scripts
(`blender --background --factory-startup --python tests/smoke_*.py`). Offline `.blend` parsing
uses **Blender Asset Tracer**, bundled as a wheel. Targets Blender **5.0+**.

## License

GPL-3.0-or-later.
