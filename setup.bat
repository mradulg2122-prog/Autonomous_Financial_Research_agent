@echo off
setlocal EnableDelayedExpansion

echo.
echo  ===================================================
echo   ARA-1: Autonomous Financial Research Agent
echo   Setup Script for Windows
echo  ===================================================
echo.

:: ── Check Docker ─────────────────────────────────────────────
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not installed or not in PATH.
    echo         Please install Docker Desktop from https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)
echo [OK] Docker found.

docker-compose --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker Compose is not installed or not in PATH.
    pause
    exit /b 1
)
echo [OK] Docker Compose found.

:: ── Check Python ──────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Python not found. Tests will not run locally.
) else (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
    echo [OK] Python !PYVER! found.
)

:: ── Create .env from template ─────────────────────────────────
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo [OK] Created .env from .env.example
        echo.
        echo  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        echo  IMPORTANT: Edit .env and set your OPENAI_API_KEY
        echo  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        echo.
        set /p EDIT_NOW="Open .env for editing now? (y/N): "
        if /i "!EDIT_NOW!"=="y" notepad .env
    ) else (
        echo [ERROR] .env.example not found. Cannot create .env.
        pause
        exit /b 1
    )
) else (
    echo [OK] .env already exists.
)

:: ── Check OPENAI_API_KEY ──────────────────────────────────────
findstr /i "OPENAI_API_KEY=sk-" .env >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [WARN] OPENAI_API_KEY not set in .env
    echo        Edit .env and add: OPENAI_API_KEY=sk-...
    echo.
)

:: ── Pull Docker images ────────────────────────────────────────
echo.
echo [*] Pulling Docker images (this may take a few minutes)...
docker-compose pull
echo [OK] Images pulled.

:: ── Build custom images ───────────────────────────────────────
echo.
echo [*] Building ARA-1 Docker images...
docker-compose build
if %errorlevel% neq 0 (
    echo [ERROR] Docker build failed.
    pause
    exit /b 1
)
echo [OK] Images built.

:: ── Start services ────────────────────────────────────────────
echo.
echo [*] Starting all services...
docker-compose up -d
if %errorlevel% neq 0 (
    echo [ERROR] Failed to start services.
    pause
    exit /b 1
)
echo [OK] Services starting...

:: ── Wait for backend health ───────────────────────────────────
echo.
echo [*] Waiting for backend to become healthy (up to 60s)...
set /a ATTEMPTS=0
:WAIT_LOOP
set /a ATTEMPTS+=1
if %ATTEMPTS% gtr 12 (
    echo [WARN] Backend health check timed out. Check: docker-compose logs backend
    goto SHOW_URLS
)
curl -sf http://localhost:8000/health >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Backend is healthy!
    goto RUN_MIGRATIONS
)
echo     Waiting... (attempt %ATTEMPTS%/12)
timeout /t 5 /nobreak >nul
goto WAIT_LOOP

:: ── Run Migrations ────────────────────────────────────────────
:RUN_MIGRATIONS
echo.
echo [*] Running database migrations...
docker-compose exec backend alembic upgrade head
if %errorlevel% neq 0 (
    echo [WARN] Migration failed or already up to date.
) else (
    echo [OK] Database migrations applied.
)

:: ── Show URLs ─────────────────────────────────────────────────
:SHOW_URLS
echo.
echo  ===================================================
echo   ARA-1 is running!
echo  ===================================================
echo.
echo   Frontend:     http://localhost:3000
echo   API:          http://localhost:8000
echo   API Docs:     http://localhost:8000/docs
echo   Grafana:      http://localhost:3001  (admin / admin)
echo   Prometheus:   http://localhost:9090
echo   Qdrant UI:    http://localhost:6333/dashboard
echo.
echo   Logs:         docker-compose logs -f
echo   Stop:         docker-compose down
echo.

set /p OPEN_BROWSER="Open the frontend in your browser? (Y/n): "
if /i not "!OPEN_BROWSER!"=="n" (
    start http://localhost:3000
)

echo.
echo  Setup complete! Happy researching.
echo.
pause
