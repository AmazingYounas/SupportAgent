#!/usr/bin/env pwsh
# Quick start script for the Voice AI Agent

Write-Host "Starting Voice AI Agent..." -ForegroundColor Cyan
Write-Host ""

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
. .\.autoenv.ps1

# Start the server
Write-Host ""
Write-Host "Backend:  http://localhost:8000" -ForegroundColor Green
Write-Host "Test UI:  http://localhost:8000/"  -ForegroundColor Green
Write-Host "Logs:     agent.log"              -ForegroundColor Gray
Write-Host ""
Write-Host "Press CTRL+C to stop" -ForegroundColor Yellow
Write-Host ""

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
