#!/usr/bin/env pwsh
# ARA-1 Local Development Startup Script
# Starts: Redis, Qdrant, PostgreSQL, and FastAPI backend

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$InfraDir = Join-Path $Root "infra"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$VenvActivate = Join-Path $Root ".venv\Scripts\Activate.ps1"
$env:PYTHONUNBUFFERED = "1"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  ARA-1: Autonomous Financial Research Agent" -ForegroundColor Cyan
Write-Host "  Local Development Startup" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# ── 1. Start Redis ────────────────────────────────────────────
Write-Host "[1/4] Starting Redis..." -ForegroundColor Yellow
$RedisExe = Get-ChildItem "$InfraDir\redis" -Recurse -Filter "redis-server.exe" | Select-Object -First 1 -ExpandProperty FullName
$RedisConf = Join-Path $InfraDir "redis.conf"
if (-not $RedisExe) {
    Write-Host "  ❌ redis-server.exe not found in $InfraDir\redis" -ForegroundColor Red
    exit 1
}
$RedisJob = Start-Process -FilePath $RedisExe -ArgumentList "infra/redis.conf" -WorkingDirectory $Root -PassThru -NoNewWindow
Write-Host "  ✅ Redis started (PID: $($RedisJob.Id)) on port 6379" -ForegroundColor Green

Start-Sleep -Seconds 1

# ── 2. Start Qdrant ───────────────────────────────────────────
Write-Host "[2/4] Starting Qdrant..." -ForegroundColor Yellow
$QdrantExe = Join-Path $InfraDir "qdrant\qdrant.exe"
$QdrantStorage = Join-Path $InfraDir "qdrant_storage"
New-Item -ItemType Directory -Force -Path $QdrantStorage | Out-Null
$env:QDRANT__STORAGE__STORAGE_PATH = $QdrantStorage
$QdrantJob = Start-Process -FilePath $QdrantExe -WorkingDirectory $Root -PassThru -NoNewWindow
Write-Host "  ✅ Qdrant started (PID: $($QdrantJob.Id)) on port 6333" -ForegroundColor Green

Start-Sleep -Seconds 2

# ── 3. PostgreSQL setup ───────────────────────────────────────
Write-Host "[3/4] Checking PostgreSQL..." -ForegroundColor Yellow
$PgBinDir = Get-ChildItem "$InfraDir\pgsql" -Recurse -Filter "pg_ctl.exe" -ErrorAction SilentlyContinue | 
            Select-Object -First 1 -ExpandProperty DirectoryName

if (-not $PgBinDir) {
    Write-Host "  ⚠️  PostgreSQL binaries not found yet (still downloading?). Skipping..." -ForegroundColor Yellow
    Write-Host "     Once downloaded, extract infra\pgsql.zip to infra\pgsql and re-run." -ForegroundColor Gray
} else {
    $PgData = Join-Path $InfraDir "pgdata"
    $PgCtl = Join-Path $PgBinDir "pg_ctl.exe"
    $PgLogFile = Join-Path $InfraDir "postgres.log"
    
    if (-not (Test-Path (Join-Path $PgData "PG_VERSION"))) {
        Write-Host "  Initializing PostgreSQL data directory..." -ForegroundColor Gray
        $env:PGPASSWORD = "ara1_secure_password_change_me"
        & (Join-Path $PgBinDir "initdb.exe") -D $PgData -U postgres -A md5 --pwfile=(
            New-TemporaryFile | % { "ara1_secure_password_change_me" | Set-Content $_; $_.FullName }
        ) 2>&1 | Out-Null
        
        # Allow connections
        Add-Content (Join-Path $PgData "pg_hba.conf") "`nhost all all 127.0.0.1/32 md5"
    }
    
    Start-Process -FilePath $PgCtl -ArgumentList "-D ""$PgData"" -l ""$PgLogFile"" start" -WorkingDirectory $Root -NoNewWindow
    
    # Create user and database
    $PsqlExe = Join-Path $PgBinDir "psql.exe"
    $env:PGPASSWORD = "ara1_secure_password_change_me"
    
    # Wait for PostgreSQL to be ready
    Write-Host "  Waiting for PostgreSQL to accept connections..." -ForegroundColor Gray
    $attempts = 0
    $db_ready = $false
    while ($attempts -lt 15) {
        $attempts++
        & $PsqlExe -h 127.0.0.1 -U postgres -w -c "SELECT 1;" 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $db_ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    
    if (-not $db_ready) {
        Write-Host "  ❌ PostgreSQL failed to start or accept connections in time." -ForegroundColor Red
        exit 1
    }
    
    & $PsqlExe -h 127.0.0.1 -U postgres -w -c "CREATE USER ara1_user WITH PASSWORD 'ara1_secure_password_change_me';" 2>&1 | Out-Null
    & $PsqlExe -h 127.0.0.1 -U postgres -w -c "CREATE DATABASE ara1 OWNER ara1_user;" 2>&1 | Out-Null
    & $PsqlExe -h 127.0.0.1 -U postgres -w -d ara1 -c "CREATE EXTENSION IF NOT EXISTS ""uuid-ossp""; CREATE EXTENSION IF NOT EXISTS ""pg_trgm"";" 2>&1 | Out-Null
    Write-Host "  ✅ PostgreSQL started on port 5432 (user: ara1_user, db: ara1)" -ForegroundColor Green
}

Start-Sleep -Seconds 1

# ── 4. Run Alembic migrations ─────────────────────────────────
Write-Host "[3b/4] Running database migrations..." -ForegroundColor Yellow
& $VenvPython -m alembic upgrade head 2>&1 | Tee-Object -Variable MigrateOut | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✅ Migrations applied" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  Migration output: $MigrateOut" -ForegroundColor Yellow
}

# ── 5. Start Frontend Web Server ──────────────────────────────
Write-Host "[4/5] Starting Frontend Web Server..." -ForegroundColor Yellow
$FrontendJob = Start-Process -FilePath $VenvPython -ArgumentList "-m http.server 3000 --directory frontend" -WorkingDirectory $Root -PassThru -NoNewWindow
Write-Host "  ✅ Frontend started on port 3000" -ForegroundColor Green

# ── 6. Start FastAPI Backend ──────────────────────────────────
Write-Host "[5/5] Starting FastAPI backend..." -ForegroundColor Yellow
Write-Host "`n  📡 API:   http://localhost:8000" -ForegroundColor Cyan
Write-Host "  📖 Docs:  http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "  ❤️  Health: http://localhost:8000/health" -ForegroundColor Cyan
Write-Host "  🖥️  UI:    http://localhost:3000" -ForegroundColor Cyan
Write-Host "`n  Press Ctrl+C to stop the backend.`n" -ForegroundColor Gray

# Open UI in browser automatically
Start-Sleep -Seconds 1
Start-Process "http://localhost:3000"

& $VenvPython -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir backend
