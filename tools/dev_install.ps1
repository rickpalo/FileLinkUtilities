<#
.SYNOPSIS
    Build the File & Link Utilities extension from this working tree and install it into
    Blender's local "User Default" extension repo, for fast dev iteration.

.DESCRIPTION
    File & Link Utilities is normally installed from the published repo URL
    (rickpalo.github.io/FileLinkUtilities). That copy only updates when a release is
    published, so it can't be used to test in-progress work. This script builds
    the CURRENT tree into a zip and installs it locally instead.

    Both installs share the extension id "file_link_utilities", and two extensions with
    the same id register the same classes -> only ONE can be enabled at a time.
    So the first time you dev-install:
      Preferences > Add-ons : DISABLE "File & Link Utilities" under the online repo, and
      ENABLE  "File & Link Utilities" under "User Default".
    (You can re-enable the online one later; you won't need to toggle again.)

    Uses --factory-startup so the build doesn't load your other add-ons (one of
    which can stall Blender on startup). The BAT wheel is bundled per the manifest.

.PARAMETER Blender
    Path to blender.exe. Defaults to the installed Blender 5.1.

.PARAMETER Enable
    Pass -Enable to also enable the extension during install (its enabled state
    is written to your real prefs only when run without --factory-startup, so you
    may still need to tick it once in Preferences — see above).

.EXAMPLE
    pwsh tools/dev_install.ps1
    # build + install; then enable it once in Preferences > Add-ons (User Default)

.EXAMPLE
    pwsh tools/dev_install.ps1 -Blender "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
#>
param(
    [string]$Blender = "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
    [switch]$Enable
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DistDir = Join-Path $RepoRoot "dist"

if (-not (Test-Path $Blender)) {
    throw "Blender not found at '$Blender'. Pass -Blender <path to blender.exe>."
}
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

Write-Host "==> Building extension from $RepoRoot" -ForegroundColor Cyan
& $Blender --factory-startup --command extension build `
    --source-dir $RepoRoot --output-dir $DistDir
if ($LASTEXITCODE -ne 0) { throw "extension build failed (exit $LASTEXITCODE)" }

$zip = Get-ChildItem -Path $DistDir -Filter "file_link_utilities-*.zip" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $zip) { throw "No built zip found in $DistDir" }
Write-Host "==> Built $($zip.Name)" -ForegroundColor Green

$installArgs = @("--factory-startup", "--command", "extension", "install-file",
                 "--repo", "user_default", $zip.FullName)
if ($Enable) { $installArgs += "--enable" }

Write-Host "==> Installing into the 'User Default' local repo" -ForegroundColor Cyan
& $Blender @installArgs
if ($LASTEXITCODE -ne 0) { throw "extension install-file failed (exit $LASTEXITCODE)" }

Write-Host ""
Write-Host "Done. Next:" -ForegroundColor Green
Write-Host "  1. Launch Blender." -ForegroundColor Green
Write-Host "  2. Preferences > Add-ons: disable 'File & Link Utilities' (online repo)," -ForegroundColor Green
Write-Host "     enable 'File & Link Utilities' under 'User Default' (first time only)." -ForegroundColor Green
Write-Host "  3. Properties editor > Scene tab > 'File & Link Utilities'." -ForegroundColor Green
Write-Host "  Re-run this script after code changes (then F3 > Reload Scripts, or restart)." -ForegroundColor Green
