Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
Set-Location $workspace

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

uv python install 3.11
uv sync --all-groups

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Start the app with: .\\scripts\\dev.ps1"
Write-Host "Run tests with: .\\scripts\\test.ps1"
