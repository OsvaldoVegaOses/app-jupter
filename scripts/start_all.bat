@REM ============================================================================
@REM start_all.bat - Iniciador de todo el stack de desarrollo cmd /c scripts\start_all.bat
@REM ============================================================================
@REM
@REM Descripción:
@REM   Inicia todos los servicios necesarios para desarrollo local:
@REM   1. Docker Compose (Neo4j, Qdrant, PostgreSQL, Redis)
@REM   2. Celery Worker (tareas asíncronas)
@REM   3. FastAPI Backend (http://localhost:8000)
@REM   4. Vite Frontend (http://localhost:5173)
@REM
@REM Uso:
@REM   cmd /c scripts\start_all.bat
@REM
@REM Requisitos:
@REM   - Docker Desktop ejecutándose
@REM   - Node.js instalado (para frontend)
@REM   - Python 3.10+ con dependencias instaladas
@REM
@REM ============================================================================

@echo off
cd /d "%~dp0"
echo ===================================================
echo STARTING FULL STACK APP (MANUAL TESTING MODE)
echo ===================================================

echo 1. Starting Infrastructure (Docker)...
docker-compose -f ../docker-compose.yml up -d
echo 1b. Starting Celery Worker in Docker (preferred)...
docker-compose --profile workers -f ../docker-compose.yml up -d celery-worker
if errorlevel 1 (
    echo [ERROR] Docker failed to start. Is Docker Desktop running?
    pause
    exit /b
)

echo.
echo 2. Launching Services in new windows...

:: Worker recommendation: prefer Docker container above. Use local worker only for debugging.
@REM start "Celery Worker" cmd /c "call start_worker.bat"

:: Launch Backend
start "FastAPI Backend" cmd /c "call start_backend.bat"

:: Frontend runs in Docker on port 5174 (not launching dev mode on 5173)
@REM start "Vite Frontend" cmd /c "call start_frontend.bat"

echo.
echo [SUCCESS] All services launched!
echo - Backend: http://localhost:8000
echo - Frontend (Docker): http://localhost:5174
echo.
pause
