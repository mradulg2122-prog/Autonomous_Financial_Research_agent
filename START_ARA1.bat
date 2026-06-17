@echo off
title ARA-1 Startup
color 0A

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║   ARA-1: Autonomous Financial Research Agent    ║
echo  ║              Starting All Services...           ║
echo  ╚══════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

:: ── Kill stale processes ──────────────────────────────────
echo [0/5] Cleaning up stale processes...
taskkill /F /IM redis-server.exe /T >nul 2>&1
taskkill /F /IM qdrant.exe /T >nul 2>&1
taskkill /F /IM postgres.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul

:: Delete stale pid file so postgres.exe starts cleanly
if exist infra\pgdata\postmaster.pid (
    echo         Removing stale PostgreSQL pid file...
    del /F /Q infra\pgdata\postmaster.pid >nul 2>&1
)

:: ── 1. PostgreSQL ─────────────────────────────────────────
echo [1/5] Starting PostgreSQL on port 5432...
start "ARA1-PostgreSQL" /min infra\pgsql\pgsql\bin\postgres.exe -D infra\pgdata -p 5432 -h 127.0.0.1
timeout /t 4 /nobreak >nul
echo      OK - PostgreSQL on port 5432

:: ── 2. Redis ─────────────────────────────────────────────
echo [2/5] Starting Redis...
start "ARA1-Redis" /min "infra\redis\Redis-7.4.2-Windows-x64-msys2\redis-server.exe" --port 6379 --requirepass redis_secure_password_change_me --loglevel warning
timeout /t 3 /nobreak >nul
echo      OK - Redis on port 6379

:: ── 3. Qdrant ────────────────────────────────────────────
echo [3/5] Starting Qdrant...
set QDRANT__STORAGE__STORAGE_PATH=%~dp0infra\qdrant_storage
start "ARA1-Qdrant" /min "infra\qdrant\qdrant.exe"
timeout /t 4 /nobreak >nul
echo      OK - Qdrant on port 6333

:: ── 4. Frontend ──────────────────────────────────────────
echo [4/5] Starting Frontend...
start "ARA1-Frontend" /min .venv\Scripts\python.exe -m http.server 3000 --directory frontend
timeout /t 2 /nobreak >nul
echo      OK - Frontend on http://localhost:3000

:: ── 5. Backend ───────────────────────────────────────────
echo [5/5] Starting Backend API...
echo.
echo  ─────────────────────────────────────────────────────
echo   API:    http://localhost:8000
echo   Docs:   http://localhost:8000/docs
echo   UI:     http://localhost:3000
echo  ─────────────────────────────────────────────────────
echo.
echo  Press Ctrl+C to stop the backend.
echo.
timeout /t 2 /nobreak >nul
start "" "http://localhost:3000"
.venv\Scripts\python.exe -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir backend
pause
