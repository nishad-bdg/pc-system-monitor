#Requires -Version 5.1
<#
.SYNOPSIS
  Build system-info.exe with PyInstaller (run on Windows).

.EXAMPLE
  .\packaging\windows\build.ps1
#>
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

Write-Host "== sync deps =="
uv sync
uv pip install pyinstaller

Write-Host "== pyinstaller =="
uv run pyinstaller --noconfirm --clean (Join-Path $PSScriptRoot "system-info.spec")

$Out = Join-Path $Root "dist\system-info.exe"
if (-not (Test-Path $Out)) {
  # onedir vs onefile: one-file writes to dist/system-info.exe
  $Alt = Join-Path $Root "dist\system-info\system-info.exe"
  if (Test-Path $Alt) { $Out = $Alt }
}
if (-not (Test-Path $Out)) {
  throw "Build failed: system-info.exe not found under dist/"
}
Write-Host "Built: $Out"
Write-Host "Next: compile packaging\windows\SystemInfoSetup.iss with Inno Setup"
