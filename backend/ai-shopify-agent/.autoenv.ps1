# Auto-activate virtual environment when entering this directory
# This script runs automatically when you open a terminal in this folder

$venvPath = Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1"

if (Test-Path $venvPath) {
    Write-Host "🐍 Activating Python virtual environment..." -ForegroundColor Cyan
    & $venvPath
    Write-Host "✅ Virtual environment activated!" -ForegroundColor Green
    Write-Host "Python: $(python --version)" -ForegroundColor Yellow
    Write-Host ""
} else {
    Write-Host "⚠️  Virtual environment not found at: $venvPath" -ForegroundColor Yellow
    Write-Host "Run: python -m venv .venv" -ForegroundColor Yellow
}
