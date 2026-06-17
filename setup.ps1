# ARA-1 PowerShell Setup Script
# Run with: .\setup.ps1

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  ===================================================" -ForegroundColor Cyan
Write-Host "   ARA-1: Autonomous Financial Research Agent" -ForegroundColor Cyan
Write-Host "   Setup Script for Windows (PowerShell)" -ForegroundColor Cyan
Write-Host "  ===================================================" -ForegroundColor Cyan
Write-Host ""

# ── Check Docker ─────────────────────────────────────────────
try {
    $dockerVer = docker --version 2>&1
    Write-Host "[OK] $dockerVer" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Docker not found. Install Docker Desktop first." -ForegroundColor Red
    exit 1
}

# ── Create .env ───────────────────────────────────────────────
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "[OK] Created .env from .env.example" -ForegroundColor Green
        Write-Host ""
        Write-Host "  !!! IMPORTANT: Edit .env and set OPENAI_API_KEY=sk-..." -ForegroundColor Yellow
        Write-Host ""
        $edit = Read-Host "Open .env in Notepad now? (Y/n)"
        if ($edit -ne "n" -and $edit -ne "N") { notepad .env }
    } else {
        Write-Host "[ERROR] .env.example not found" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[OK] .env already exists." -ForegroundColor Green
}

# ── Verify OPENAI key ─────────────────────────────────────────
$envContent = Get-Content ".env" -Raw
if ($envContent -notmatch "OPENAI_API_KEY=sk-") {
    Write-Host "[WARN] OPENAI_API_KEY not set in .env" -ForegroundColor Yellow
}

# ── Build & Start ─────────────────────────────────────────────
Write-Host ""
Write-Host "[*] Building Docker images..." -ForegroundColor Cyan
docker-compose build
Write-Host "[OK] Images built." -ForegroundColor Green

Write-Host ""
Write-Host "[*] Starting services..." -ForegroundColor Cyan
docker-compose up -d
Write-Host "[OK] Services started." -ForegroundColor Green

# ── Wait for backend ──────────────────────────────────────────
Write-Host ""
Write-Host "[*] Waiting for backend (up to 60s)..." -ForegroundColor Cyan
$attempts = 0
$healthy = $false
while ($attempts -lt 12) {
    $attempts++
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) { $healthy = $true; break }
    } catch {}
    Write-Host "    Waiting... ($attempts/12)" -ForegroundColor DarkGray
    Start-Sleep -Seconds 5
}

if ($healthy) {
    Write-Host "[OK] Backend healthy!" -ForegroundColor Green
    # Run migrations
    Write-Host ""
    Write-Host "[*] Applying database migrations..." -ForegroundColor Cyan
    docker-compose exec backend alembic upgrade head
    Write-Host "[OK] Migrations applied." -ForegroundColor Green
} else {
    Write-Host "[WARN] Backend didn't respond. Check: docker-compose logs backend" -ForegroundColor Yellow
}

# ── Done ──────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ===================================================" -ForegroundColor Green
Write-Host "   ARA-1 is running!" -ForegroundColor Green
Write-Host "  ===================================================" -ForegroundColor Green
Write-Host ""
Write-Host "   Frontend  : http://localhost:3000" -ForegroundColor White
Write-Host "   API Docs  : http://localhost:8000/docs" -ForegroundColor White
Write-Host "   Grafana   : http://localhost:3001  (admin/admin)" -ForegroundColor White
Write-Host "   Prometheus: http://localhost:9090" -ForegroundColor White
Write-Host "   Qdrant UI : http://localhost:6333/dashboard" -ForegroundColor White
Write-Host ""
Write-Host "   Stop all  : docker-compose down" -ForegroundColor DarkGray
Write-Host "   Logs      : docker-compose logs -f" -ForegroundColor DarkGray
Write-Host ""

$open = Read-Host "Open frontend in browser? (Y/n)"
if ($open -ne "n" -and $open -ne "N") {
    Start-Process "http://localhost:3000"
}

Write-Host ""
Write-Host "  Setup complete! Happy researching." -ForegroundColor Green
