#!/usr/bin/env pwsh
# GDL-Web Docker Compose Manager
# Manage the local GDL-Web stack using compose.yaml in the repository root.

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("up", "down", "restart", "logs", "status", "build", "pull")]
    [string]$Action = "up"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ComposeDir = $PSScriptRoot
$ComposeFile = Join-Path $ComposeDir "compose.yaml"

if (-not (Test-Path -LiteralPath $ComposeFile)) {
    Write-Error "compose.yaml not found at '$ComposeFile'."
    exit 1
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker CLI not found in PATH. Install Docker Desktop or Docker Engine first."
    exit 1
}

Push-Location -LiteralPath $ComposeDir
try {
    $port = if ($env:PORT) { $env:PORT } else { "6969" }

    switch ($Action) {
        "up" {
            Write-Host "Starting GDL-Web..." -ForegroundColor Green
            docker compose -f $ComposeFile up -d
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            Write-Host "`nGDL-Web is running at http://127.0.0.1:$port" -ForegroundColor Cyan
        }
        "down" {
            Write-Host "Stopping GDL-Web..." -ForegroundColor Yellow
            docker compose -f $ComposeFile down
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        "restart" {
            Write-Host "Restarting GDL-Web..." -ForegroundColor Yellow
            docker compose -f $ComposeFile restart
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        "logs" {
            Write-Host "Showing logs (Ctrl+C to exit)..." -ForegroundColor Cyan
            docker compose -f $ComposeFile logs -f
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        "status" {
            Write-Host "GDL-Web Status:" -ForegroundColor Cyan
            docker compose -f $ComposeFile ps
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        "build" {
            Write-Host "Building GDL-Web..." -ForegroundColor Green
            docker compose -f $ComposeFile build
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        "pull" {
            Write-Host "Pulling latest image..." -ForegroundColor Green
            docker compose -f $ComposeFile pull
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
    }
} finally {
    Pop-Location
}
