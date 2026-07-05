<#
.SYNOPSIS
    Switch the dev install to a LIVE junction so code edits need only
    "F3 > Reload Scripts" in Blender — no rebuild/reinstall per change.

.DESCRIPTION
    dev_install.ps1 copies a snapshot into Blender's user_default repo, so you
    must re-run it after every edit. This instead replaces that copy with a
    directory *junction* pointing at this working tree, so the installed
    extension IS the source. After running once:
        edit code -> Blender: F3 > Reload Scripts  (restart if a submodule's
        register/unregister changed and reload won't take).

    Junctions don't need admin. Blender reads the manifest from the junction and
    installs the bundled BAT wheel as usual. Extra files (tests/, docs/) sit in
    the dir but aren't imported, so they're harmless when loading live.

    RUN WITH BLENDER CLOSED (the folder can't be swapped while it's loaded).
    To go back to a snapshot copy, just run dev_install.ps1 again.

.PARAMETER BlenderVersion
    Blender version folder under %APPDATA%\Blender Foundation\Blender. Default 5.1.

.EXAMPLE
    pwsh tools/dev_link.ps1            # close Blender first, then run, then reopen
#>
param(
    [string]$BlenderVersion = "5.1"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ExtRoot = Join-Path $env:APPDATA "Blender Foundation\Blender\$BlenderVersion\extensions\user_default"
$Link = Join-Path $ExtRoot "file_link_utilities"

if (-not (Test-Path $ExtRoot)) {
    throw "User Default extensions folder not found: $ExtRoot. Install once via dev_install.ps1 first."
}

# Remove whatever is there (a copied dir, or a stale junction).
if (Test-Path $Link) {
    $item = Get-Item $Link -Force
    if ($item.LinkType) {
        # Existing reparse point (junction/symlink): remove the link only.
        & cmd /c rmdir "$Link"
    } else {
        Remove-Item $Link -Recurse -Force
    }
    Write-Host "Removed existing install at $Link" -ForegroundColor DarkGray
}

& cmd /c mklink /J "$Link" "$RepoRoot" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "mklink /J failed (exit $LASTEXITCODE)" }

Write-Host "Linked $Link  ->  $RepoRoot" -ForegroundColor Green
Write-Host ""
Write-Host "Next:" -ForegroundColor Green
Write-Host "  1. Start Blender; enable 'File & Link Utilities' under User Default if needed." -ForegroundColor Green
Write-Host "  2. After code edits: F3 > Reload Scripts (or restart Blender)." -ForegroundColor Green
Write-Host "     No rebuild needed — the install now points at your source tree." -ForegroundColor Green
