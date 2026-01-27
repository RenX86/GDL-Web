#!/usr/bin/env pwsh
# GDL-Web Docker Compose Manager
# Run this script from anywhere to manage your GDL-Web container

param(
    [Parameter(Position=0)]
    [ValidateSet("up", "down", "restart", "logs", "status", "build", "pull")]
    [string]$Action = "up"
)

# Set the directory where your docker-compose.yaml is located
$ComposeDir = "C:\Users\Master\Documents\GitHub\GDL-Web"

# Change to the compose directory
Push-Location $ComposeDir

try {
    switch ($Action) {
        "up" {
            Write-Host "Starting GDL-Web..." -ForegroundColor Green
            docker compose up -d
            Write-Host "`nGDL-Web is running at http://localhost:6969" -ForegroundColor Cyan
        }
        "down" {
            Write-Host "Stopping GDL-Web..." -ForegroundColor Yellow
            docker compose down
        }
        "restart" {
            Write-Host "Restarting GDL-Web..." -ForegroundColor Yellow
            docker compose restart
        }
        "logs" {
            Write-Host "Showing logs (Ctrl+C to exit)..." -ForegroundColor Cyan
            docker compose logs -f
        }
        "status" {
            Write-Host "GDL-Web Status:" -ForegroundColor Cyan
            docker compose ps
        }
        "build" {
            Write-Host "Building GDL-Web..." -ForegroundColor Green
            docker compose build
        }
        "pull" {
            Write-Host "Pulling latest image..." -ForegroundColor Green
            docker compose pull
        }
    }
} finally {
    # Return to original directory
    Pop-Location
}
