Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
Set-Location $workspace

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if (-not (Test-Path ".env")) {
        return $null
    }

    foreach ($line in Get-Content ".env" -Encoding UTF8) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith("#")) {
            continue
        }

        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) {
            continue
        }

        if ($parts[0].Trim() -eq $Name) {
            $value = $parts[1].Trim()
            if ($value.StartsWith('"') -and $value.EndsWith('"') -and $value.Length -ge 2) {
                return $value.Substring(1, $value.Length - 2)
            }
            return $value
        }
    }

    return $null
}

function Get-ConfiguredValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [string]$Fallback = ""
    )

    $envValue = [Environment]::GetEnvironmentVariable($Name)
    if (-not [string]::IsNullOrWhiteSpace($envValue)) {
        return $envValue.Trim()
    }

    $dotEnvValue = Get-DotEnvValue -Name $Name
    if (-not [string]::IsNullOrWhiteSpace($dotEnvValue)) {
        return $dotEnvValue.Trim()
    }

    return $Fallback
}

function Get-NgrokExecutable {
    $command = Get-Command ngrok -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $packageDir = Join-Path $env:LOCALAPPDATA "Microsoft\\WinGet\\Packages"
    if (Test-Path $packageDir) {
        $candidate = Get-ChildItem $packageDir -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "Ngrok.Ngrok*" } |
            ForEach-Object {
                Get-ChildItem $_.FullName -Recurse -Filter "ngrok.exe" -ErrorAction SilentlyContinue
            } |
            Select-Object -First 1
        if ($candidate) {
            return $candidate.FullName
        }
    }

    throw "ngrok.exe not found. Install it first with: winget install --id Ngrok.Ngrok"
}

function Test-NgrokConfigHasAuthtoken {
    $configPath = Join-Path $env:LOCALAPPDATA "ngrok\\ngrok.yml"
    if (-not (Test-Path $configPath)) {
        return $false
    }

    $content = Get-Content -Raw -Encoding UTF8 $configPath
    return $content -match "(?m)^\s*authtoken\s*:"
}

function Clear-NgrokProxyEnvironment {
    foreach ($name in @("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")) {
        if (-not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        }
    }
}

$port = Get-ConfiguredValue -Name "PORT" -Fallback "8000"
$authtoken = Get-ConfiguredValue -Name "NGROK_AUTHTOKEN"
$domain = Get-ConfiguredValue -Name "NGROK_DOMAIN"

if ([string]::IsNullOrWhiteSpace($domain)) {
    throw "NGROK_DOMAIN is required for a stable public endpoint. Put your assigned ngrok dev domain in .env."
}

$ngrok = Get-NgrokExecutable
$hasStoredAuthtoken = Test-NgrokConfigHasAuthtoken

if ([string]::IsNullOrWhiteSpace($authtoken) -and -not $hasStoredAuthtoken) {
    throw "NGROK_AUTHTOKEN is required for a stable public endpoint. Add it to .env or run ngrok config add-authtoken first."
}

Write-Host ""
Write-Host "Starting ngrok tunnel..."
Write-Host "  Local app : http://127.0.0.1:$port"
Write-Host "  Public URL: https://$domain"
Write-Host ""

Clear-NgrokProxyEnvironment
$arguments = @("http", "--domain=$domain", "127.0.0.1:$port")
if (-not [string]::IsNullOrWhiteSpace($authtoken)) {
    $arguments = @("http", "--authtoken=$authtoken", "--domain=$domain", "127.0.0.1:$port")
}

& $ngrok @arguments
