@REM ============================================================================
@REM start_local.bat - Desarrollo 100% local (sin Docker)
@REM ============================================================================
@REM
@REM Descripción:
@REM   Inicia todos los servicios localmente sin Docker:
@REM   1. FastAPI Backend (http://localhost:8000)
@REM   2. Vite Frontend (http://localhost:5173)
@REM
@REM Servicios en Azure (no requieren Docker local):
@REM   - Neo4j (Azure VM)
@REM   - PostgreSQL (Azure Flexible Server)
@REM   - Qdrant (Azure Container)
@REM
@REM Nota: Celery/Redis deshabilitado - análisis LLM corre en modo sync
@REM
@REM Uso:
@REM   scripts\start_local.bat
@REM
@REM ============================================================================

@echo off
cd /d "%~dp0\.."

echo ===================================================
echo STARTING LOCAL DEVELOPMENT (NO DOCKER)
echo ===================================================
echo.

:: Verificar que exista el entorno virtual
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo Run: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

:: Verificar que exista node_modules
if not exist "frontend\node_modules" (
    echo [WARNING] Frontend dependencies not installed.
    echo Run: cd frontend ^&^& npm install
    echo.
)

echo [1/2] Starting Backend (FastAPI)...
start "FastAPI Backend" cmd /k "cd /d %~dp0\.. && .venv\Scripts\activate && set APP_ENV_FILE=.env && python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload"

:: Esperar un poco para que el backend inicie
timeout /t 3 /nobreak > nul

echo [2/2] Starting Frontend (Vite)...
start "Vite Frontend" cmd /k "cd /d %~dp0\..\frontend && npm run dev"

echo.
echo ===================================================
echo [SUCCESS] All services starting!
echo ===================================================
echo.
echo Backend:  http://localhost:8000 (API)
echo Frontend: http://localhost:5173 (UI)
echo.
echo [NOTE] Celery/Redis disabled - LLM analysis runs synchronously
echo [NOTE] Neo4j, PostgreSQL, Qdrant connect to Azure
echo.
echo Press any key to exit (services will keep running)...
pause > nul
