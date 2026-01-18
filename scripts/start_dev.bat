@REM ============================================================================
@REM start_dev.bat - Iniciador del stack de desarrollo HÍBRIDO
@REM ============================================================================
@REM
@REM Descripción:
@REM   Inicia el entorno de desarrollo híbrido:
@REM   - Docker: PostgreSQL, Redis (locales)
@REM   - Cloud: Neo4j Aura, Qdrant Cloud (configurados en .env.docker)
@REM   - Celery Worker (tareas asíncronas)
@REM   - FastAPI Backend (http://localhost:8000)
@REM   - Vite Frontend (http://localhost:5173)
@REM
@REM Uso:
@REM   cmd /c scripts\start_dev.bat
@REM
@REM Requisitos:
@REM   - Docker Desktop ejecutándose
@REM   - Node.js instalado (para frontend)
@REM   - Python 3.10+ con dependencias instaladas
@REM   - Archivo .env.docker configurado
@REM
@REM ============================================================================

@echo off
cd /d "%~dp0\.."
echo ===================================================
echo STARTING HYBRID DEV STACK
echo ===================================================
echo.
echo Arquitectura:
echo   - PostgreSQL: Docker local (localhost:5432)
echo   - Redis: Docker local (localhost:16379)
echo   - Neo4j: Cloud (Aura)
echo   - Qdrant: Cloud
echo ===================================================
echo.

echo 1. Verificando .env.docker...
if not exist ".env.docker" (
    echo [ERROR] Archivo .env.docker no encontrado!
    echo        Copia .env.docker.example y configura tus credenciales.
    pause
    exit /b 1
)

echo 2. Starting Docker Services (PostgreSQL, Redis)...
docker-compose -f docker-compose.dev.yml up -d
if errorlevel 1 (
    echo [ERROR] Docker failed to start. Is Docker Desktop running?
    pause
    exit /b 1
)

echo.
echo 3. Waiting for services to be healthy...
timeout /t 5 /nobreak > nul

echo.
echo 4. Launching Services in new windows...

:: Launch Worker
cd scripts
start "Celery Worker" cmd /c "call start_worker.bat"

:: Launch Backend (en modo local, no Docker)
start "FastAPI Backend" cmd /c "call start_backend.bat"

:: Launch Frontend
start "Vite Frontend" cmd /c "call start_frontend.bat"

cd ..

echo.
echo ===================================================
echo [SUCCESS] All services launched!
echo ===================================================
echo.
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
echo   Postgres: localhost:5432
echo   Redis:    localhost:16379
echo.
echo   Neo4j:   (Cloud - ver .env.docker)
echo   Qdrant:  (Cloud - ver .env.docker)
echo.
pause
