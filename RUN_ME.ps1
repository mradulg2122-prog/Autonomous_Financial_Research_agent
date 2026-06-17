#!/usr/bin/env pwsh
# ARA-1 — One-Click Startup Script (PowerShell version)
# Run: .\RUN_ME.ps1

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$PgBin   = Join-Path $Root "infra\pgsql\pgsql\bin"
$PgData  = Join-Path $Root "infra\pgdata"
$PgPid   = Join-Path $PgData "postmaster.pid"

# ─── Colors ───────────────────────────────────────────────────────
function Write-Header {
    Clear-Host
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║    ARA-1: Autonomous Financial Research Agent    ║" -ForegroundColor Cyan
    Write-Host "  ║              One-Click Startup                   ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Ok($msg)   { Write-Host "  ✅ $msg" -ForegroundColor Green  }
function Write-Warn($msg) { Write-Host "  ⚠️  $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "  ❌ $msg" -ForegroundColor Red    }
function Write-Step($msg) { Write-Host "  ► $msg"  -ForegroundColor White  }

Write-Header
Set-Location $Root

# ─── Kill stale processes ─────────────────────────────────────────
Write-Step "Cleaning up stale processes..."
Stop-Process -Name "redis-server" -Force -ErrorAction SilentlyContinue
Stop-Process -Name "qdrant"       -Force -ErrorAction SilentlyContinue
Stop-Process -Name "postgres"     -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Remove stale PostgreSQL pid file so it starts cleanly
if (Test-Path $PgPid) {
    Write-Warn "Removing stale PostgreSQL pid file..."
    Remove-Item $PgPid -Force
}

# ─── 1. PostgreSQL (run postgres.exe directly - more reliable than pg_ctl) ────
Write-Step "[1/5] Starting PostgreSQL..."
$PgExe = Join-Path $PgBin "postgres.exe"
if (Test-Path $PgExe) {
    # Run postgres.exe directly in a hidden window - binds reliably to 127.0.0.1:5432
    $PgJob = Start-Process -FilePath $PgExe `
        -ArgumentList "-D `"$PgData`" -p 5432 -h 127.0.0.1" `
        -WorkingDirectory $Root -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 4
    $pg = netstat -ano | Select-String "127.0.0.1:5432" | Where-Object { $_ -match "LISTEN" }
    if ($pg) { Write-Ok "PostgreSQL running on 127.0.0.1:5432 (PID: $($PgJob.Id))" }
    else     { Write-Warn "PostgreSQL may still be starting... (PID: $($PgJob.Id))" }
} else {
    Write-Err "PostgreSQL not found at $PgExe"
}

# ─── 2. Redis ─────────────────────────────────────────────────────
Write-Step "[2/5] Starting Redis..."
$RedisDir = Join-Path $Root "infra\redis\Redis-7.4.2-Windows-x64-msys2"
$RedisExe = Join-Path $RedisDir "redis-server.exe"
if (Test-Path $RedisExe) {
    $RedisJob = Start-Process -FilePath $RedisExe `
        -ArgumentList "--port 6379 --requirepass redis_secure_password_change_me --loglevel warning" `
        -WorkingDirectory $RedisDir -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 2
    $rd = netstat -ano | Select-String "6379" | Where-Object { $_ -match "LISTEN" }
    if ($rd) { Write-Ok "Redis running on port 6379 (PID: $($RedisJob.Id))" }
    else     { Write-Warn "Redis may still be starting... (PID: $($RedisJob.Id))" }
} else {
    Write-Err "Redis not found at $RedisExe"
}

# ─── 3. Qdrant ────────────────────────────────────────────────────
Write-Step "[3/5] Starting Qdrant..."
$QdrantExe     = Join-Path $Root "infra\qdrant\qdrant.exe"
$QdrantStorage = Join-Path $Root "infra\qdrant_storage"
if (Test-Path $QdrantExe) {
    $env:QDRANT__STORAGE__STORAGE_PATH = $QdrantStorage
    $QdrantJob = Start-Process -FilePath $QdrantExe `
        -WorkingDirectory $Root -PassThru -WindowStyle Hidden `
        -Environment @{ QDRANT__STORAGE__STORAGE_PATH = $QdrantStorage }
    Start-Sleep -Seconds 3
    $qd = netstat -ano | Select-String "6333" | Where-Object { $_ -match "LISTEN" }
    if ($qd) { Write-Ok "Qdrant running on port 6333 (PID: $($QdrantJob.Id))" }
    else     { Write-Warn "Qdrant may still be starting... (PID: $($QdrantJob.Id))" }
} else {
    Write-Err "Qdrant not found at $QdrantExe"
}

# ─── 4. Frontend ──────────────────────────────────────────────────
Write-Step "[4/5] Starting Frontend..."
$FrontendJob = Start-Process -FilePath $VenvPython `
    -ArgumentList "-m http.server 3000 --directory frontend" `
    -WorkingDirectory $Root -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 1
Write-Ok "Frontend running on http://localhost:3000 (PID: $($FrontendJob.Id))"

# ─── 5. Backend ───────────────────────────────────────────────────
Write-Host ""
Write-Host "  ─────────────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Ok "[5/5] Starting FastAPI Backend..."
Write-Host ""
Write-Host "  📡  API:     http://localhost:8000" -ForegroundColor Cyan
Write-Host "  📖  Docs:    http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "  ❤️   Health:  http://localhost:8000/health" -ForegroundColor Cyan
Write-Host "  🖥️   UI:      http://localhost:3000" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Press Ctrl+C to stop the backend." -ForegroundColor DarkGray
Write-Host "  ─────────────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host ""

Start-Sleep -Seconds 1
Start-Process "http://localhost:3000"

& $VenvPython -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir backend
