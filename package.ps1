# Builds the release zip: the mod folder, ready to drop into the game's ue4ss\Mods.
# Usage: .\package.ps1 v0.1.0
param(
    [Parameter(Mandatory = $true)][string]$Version
)

$dist = Join-Path $PSScriptRoot "dist"
$stage = Join-Path $dist "SasTimeAccelerate"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force $dist | Out-Null

Copy-Item (Join-Path $PSScriptRoot "SasTimeAccelerate") $stage -Recurse
Copy-Item (Join-Path $PSScriptRoot "LICENSE") $stage

$zip = Join-Path $dist "SasTimeAccelerate-$Version.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $stage -DestinationPath $zip
Remove-Item $stage -Recurse -Force
"Built $zip"
