Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
Set-Location $workspace

$port = if ($env:PORT) { $env:PORT } else { "8000" }

uv run --no-sync uvicorn app.main:app --reload --host 127.0.0.1 --port $port
