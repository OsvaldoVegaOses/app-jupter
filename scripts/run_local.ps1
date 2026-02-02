<#
.SYNOPSIS
######
Desarrollo local (NO DOCKER) + smoke/tests.
#####  Correr
    C:\Users\osval\Downloads\APP_Jupter\.venv\Scripts\python.exe -m uvicorn --app-dir C:\Users\osval\Downloads\APP_Jupter backend.app:app --host 127.0.0.1 --port 8000 --reload
Frontend (cwd=frontend): npm run dev -- --port 5173
####### En otra ventana
cd frontend
npm run dev
#### Matar procesos
python "C:\Users\osval\Downloads\APP_Jupter\scripts\Cerrar_procesos.py" --kill-python
# Solo liberar puertos 8000 y 5173-5180 (Vite puede moverse de 5173 a 5174+)

python scripts/Cerrar_procesos.py

# Matar frontend (node.exe)
python scripts/Cerrar_procesos.py --kill-node

# Matar backend (python.exe excepto este script)
python scripts/Cerrar_procesos.py --kill-python

# Matar TODO (recomendado)
python scripts/Cerrar_procesos.py --kill-app

.DESCRIPTION
  Acciones soportadas:
  - `dev`: inicia backend (FastAPI/uvicorn) + frontend (Vite).
  - `smoke`: verifica `/healthz` y hace un POST mínimo a `/neo4j/query`.
  - `tests`: ejecuta pytest + vitest.
  - `all`: ejecuta `tests` + `dev` + `smoke`.
  - Auto-retry Neo4j (link_predictions): si está activo, reintenta sync en loop.

  GUIA PASO A PASO (Quickstart)
  1) Prerrequisitos
     - Python + venv listo: .venv\Scripts\python.exe debe existir (o el script usa `python`).
     - Node.js instalado.
     - Dependencias frontend instaladas: `cd frontend` y `npm install`.

     ########
     Activar el venv (opcional, pero recomendado si vas a correr comandos a mano)
     - PowerShell (desde la raiz del repo):
       Set-ExecutionPolicy -Scope Process Bypass
       .\.venv\Scripts\Activate.ps1
     - CMD:
       .\.venv\Scripts\activate.bat
####################
  2) Configuracion de variables de entorno
     - Backend: edita `.env` en la raiz (por defecto este script carga `.env`).
     - Frontend: revisa `frontend/.env` (o crea `frontend/.env.local` para overrides locales).
       Recomendado (DEV): `VITE_API_BASE=` vacío para usar proxy same-origin de Vite.
       Si necesitas cambiar el backend target del proxy, usa `VITE_BACKEND_URL=http://127.0.0.1:8000`.
       Nota: si levantas el backend en otro puerto (ej. 8010), actualiza `VITE_BACKEND_URL=http://127.0.0.1:8010`.

  3) Arrancar DEV (backend + frontend)
     - Recomendado (abre dos ventanas PowerShell):
         powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1 -Action dev
     - En la misma consola (sin abrir ventanas nuevas):
         powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1 -Action dev -NoNewWindow
     - Solo imprimir comandos (no ejecuta nada):
         powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1 -Action dev -PrintOnly

  4) Abrir la UI
     - Vite normalmente usa http://localhost:5173/.
       Si el puerto esta ocupado, Vite puede usar otro (mira la salida: 5174, 5175, etc.).

  5) Smoke test (rapido)
     - Verifica que el backend responda y prueba un POST minimo a Neo4j:
         powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1 -Action smoke

  6) Tests
     - Backend + frontend:
         powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1 -Action tests
  
  7) Auto-retry Neo4j (link predictions)
     - Por defecto está habilitado en local para facilitar operación.
     - Para desactivarlo:
         powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1 -Action dev -DisableNeo4jRetry

  Troubleshooting comun
  - Si ves errores de "Tiempo de espera agotado" en el frontend: casi siempre es porque el backend no esta escuchando en el puerto configurado (por defecto http://127.0.0.1:8000).
  - Si `5173` esta en uso: cambia `-FrontendPort` o usa el puerto que imprime Vite.
  - Si ves un warning tipo "Could not auto-determine entry point" y luego 404 en http://localhost:5173/:
      - Probablemente Vite se arrancó como `vite 5173` (o `npm run dev 5173`). En ese caso, `5173` NO es el puerto, es el "root" y Vite no encuentra `index.html`.
      - Solucion: inicia con `npm run dev -- --port 5173` (o deja que el script maneje `--port`).
  - Si definiste `VITE_API_BASE` (no recomendado en DEV): asegúrate de que el backend permita CORS para el puerto real de Vite (5173/5174/etc.).
  - Si uvicorn falla con WinError 10048 ("solo se permite un uso de cada dirección de socket"):
      - Verifica el PID: `netstat -ano | findstr :8000` (o `:8010`)
      - Mata el proceso: `taskkill /PID <PID> /F`
      - O cambia el puerto con `-BackendPort 8010`.
  - Neo4j no disponible: algunos endpoints de admin pueden estar degradados; el UI igual deberia cargar.
  - Si necesitas parar todo: cierra las consolas abiertas por `dev` o finaliza los procesos `python`/`uvicorn` y `node`.

  Este script está pensado para PowerShell. Si prefieres CMD, usa los `.bat` en `scripts/`.
  Nota PowerShell: si tu consola tiene problemas raros con `$env:...` dentro de un comando inline, usa el ejemplo con `[System.Environment]::SetEnvironmentVariable(...)` o el ejemplo `cmd /c`.

.EXAMPLE
  # Backend solo (debug) en 8010 (PowerShell)
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Set-Location 'c:\Users\osval\Downloads\APP_Jupter'; [System.Environment]::SetEnvironmentVariable('APP_ENV_FILE','.env','Process'); .\\.venv\\Scripts\\python.exe -m uvicorn --app-dir . backend.app:app --host 127.0.0.1 --port 8010 --log-level debug"

.EXAMPLE
  # DEV (recomendado): abre 2 ventanas (backend + frontend)
  powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1 -Action dev

.EXAMPLE
  # DEV sin abrir nuevas ventanas (imprime los comandos)
  powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1 -Action dev -NoNewWindow

.EXAMPLE
  # Smoke: valida que el backend responda
  powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1 -Action smoke

.EXAMPLE
  # Tests: backend + frontend
  powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1 -Action tests

.EXAMPLE
  # Cambiar puertos/host
  powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1 -Action dev -BackendHost 127.0.0.1 -BackendPort 8000 -FrontendPort 5173

.EXAMPLE
  # Backend solo (debug) en 8010 (CMD)
  cmd /c "cd /d c:\Users\osval\Downloads\APP_Jupter & set APP_ENV_FILE=.env & .\.venv\Scripts\python.exe -m uvicorn --app-dir . backend.app:app --host 127.0.0.1 --port 8010 --log-level debug"
  # Si quieres dejar la ventana abierta (para ver logs), usa `cmd /k` en vez de `cmd /c`.
  # Alternativa CMD (abre ventanas CMD)
  cmd /c scripts\start_local.bat

.EXAMPLE
  # Alternativa CMD: solo backend / solo frontend
  cmd /c scripts\start_backend.bat
  cmd /c scripts\start_frontend.bat

.EXAMPLE
  # Alternativa PowerShell: comando backend explícito (ruta completa al python del venv)
  & "C:\Users\osval\Downloads\APP_Jupter\.venv\Scripts\python.exe" -m uvicorn --app-dir "C:\Users\osval\Downloads\APP_Jupter" backend.app:app --host 127.0.0.1 --port 8000 --reload

.EXAMPLE
  # Alternativa PowerShell: iniciar frontend manualmente
  cd frontend
  npm run dev
#>

param (
  [ValidateSet("dev","smoke","tests","all")]
  [string]$Action = "dev",

  [string]$EnvFile = ".env",
  [string]$BackendHost = "127.0.0.1",
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173,

  [switch]$NoReload,
  [switch]$NoNewWindow,
  [switch]$PrintOnly,

  # Auto-retry Neo4j para link_predictions (production-friendly)
  [switch]$DisableNeo4jRetry,
  [int]$RetryInterval = 60,
  [int]$RetryBatchSize = 200,
  [int]$RetryCooldownMinutes = 2,
  [string]$RetryProject = ""
)

function Import-DotEnvFile {
  param (
    [Parameter(Mandatory = $true)]
    [string]$Path
  )
  if (-not (Test-Path $Path)) { return }
  Get-Content $Path | ForEach-Object {
    if ($_ -match '^\s*#') { return }
    if ($_ -match '^\s*$') { return }
    $parts = ($_ -split '=', 2)
    if ($parts.Count -lt 2) { return }
    $k = $parts[0].Trim()
    $v = $parts[1].Trim().Trim('"').Trim("'")
    if ($k) { Set-Item -Path "Env:\$k" -Value $v }
  }
}

function Resolve-RepoRoot {
  # Make the script runnable from any working directory.
  return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-VenvPython {
  param([string]$RepoRoot)
  $py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
  if (Test-Path $py) { return $py }
  return "python"
}

function Wait-HttpOk {
  param(
    [Parameter(Mandatory = $true)][string]$Url,
    [int]$TimeoutSec = 30
  )
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $resp = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 2
      if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) { return $true }
    } catch {
      Start-Sleep -Seconds 1
    }
  }
  return $false
}

function Start-Neo4jRetryLoop {
  param(
    [string]$RepoRoot,
    [string]$PythonPath,
    [int]$IntervalSec,
    [int]$BatchSize,
    [int]$CooldownMinutes,
    [string]$Project,
    [switch]$NoNewWindow,
    [switch]$PrintOnly
  )
  $scriptPath = Join-Path $RepoRoot "scripts\retry_link_predictions_neo4j.py"
  if (-not (Test-Path $scriptPath)) { return $null }

  $retryArgs = @($scriptPath, "--loop", "--interval", $IntervalSec, "--batch-size", $BatchSize, "--cooldown-minutes", $CooldownMinutes)
  if ($Project) { $retryArgs += @("--project", $Project) }

  if ($PrintOnly) {
    Write-Host "Neo4j retry: $PythonPath $($retryArgs -join ' ')" -ForegroundColor DarkGray
    return $null
  }

  if ($NoNewWindow) {
    return Start-Process -FilePath $PythonPath -ArgumentList $retryArgs -WorkingDirectory $RepoRoot -NoNewWindow -PassThru
  }

  Start-Process -FilePath $PythonPath -ArgumentList $retryArgs -WorkingDirectory $RepoRoot | Out-Null
  return $null
}

function Free-DiskSpace {
  param(
    [switch]$Perform
  )
  Write-Host "Attempting to free disk space (safe cleanup)..." -ForegroundColor Cyan

  # npm cache + frontend caches
  if (Get-Command npm -ErrorAction SilentlyContinue) {
    try {
      Write-Host "Cleaning npm cache (if available)..." -ForegroundColor DarkGray
      npm cache clean --force | Out-Null
    } catch {
      Write-Host "npm cache clean failed: $($_)" -ForegroundColor Yellow
    }

    $viteCache = Join-Path $repoRoot "frontend\node_modules\.vite"
    $npmCacheFolder = Join-Path $repoRoot "frontend\node_modules\.cache"
    if (Test-Path $viteCache) { Remove-Item -Recurse -Force $viteCache -ErrorAction SilentlyContinue }
    if (Test-Path $npmCacheFolder) { Remove-Item -Recurse -Force $npmCacheFolder -ErrorAction SilentlyContinue }
  }

  # pip cache purge (if pip available)
  if (Get-Command pip -ErrorAction SilentlyContinue) {
    try {
      pip cache purge | Out-Null
    } catch {
      # ignore
    }
  }

  # Remove pytest cache and large log files
  $pytestCache = Join-Path $repoRoot ".pytest_cache"
  if (Test-Path $pytestCache) { Remove-Item -Recurse -Force $pytestCache -ErrorAction SilentlyContinue }

  $logDir = Join-Path $repoRoot "logs"
  if (Test-Path $logDir) {
    Get-ChildItem $logDir -File | Where-Object { $_.Length -gt 10MB } | ForEach-Object { Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue }
  }

  Write-Host "Safe cleanup finished." -ForegroundColor Green
}

$repoRoot = Resolve-RepoRoot
Set-Location $repoRoot

$envPath = Join-Path $repoRoot $EnvFile
Import-DotEnvFile -Path $envPath

# Make backend load the same .env the CLI uses.
$env:APP_ENV_FILE = $EnvFile
$python = Get-VenvPython -RepoRoot $repoRoot

if ($Action -in @('tests','all')) {
  Write-Host "Preparing test environment: freeing disk space and caches..." -ForegroundColor Cyan
  Free-DiskSpace

  Write-Host "Running backend tests (pytest)..." -ForegroundColor Cyan
  try {
    & $python -m pytest -q
  } catch {
    Write-Host "pytest failed." -ForegroundColor Red
  }

  Write-Host "Running frontend tests (npm test)..." -ForegroundColor Cyan
  Push-Location frontend
  try {
    npm test
  } catch {
    Write-Host "npm test failed." -ForegroundColor Red
  }
  Pop-Location
}

if ($Action -in @('dev','all')) {
  Write-Host "Starting local dev (backend + frontend)..." -ForegroundColor Cyan

  $backendArgs = @("-m","uvicorn","--app-dir",$repoRoot,"backend.app:app","--host",$BackendHost,"--port",$BackendPort)
  if (-not $NoReload) { $backendArgs += "--reload" }
  $frontendArgs = @("run","dev","--","--port",$FrontendPort)

  if ($PrintOnly) {
    Write-Host "Backend: $python $($backendArgs -join ' ')" -ForegroundColor DarkGray
    Write-Host "Frontend (cwd=frontend): npm $($frontendArgs -join ' ')" -ForegroundColor DarkGray
    if (-not $DisableNeo4jRetry) {
      Start-Neo4jRetryLoop -RepoRoot $repoRoot -PythonPath $python -IntervalSec $RetryInterval -BatchSize $RetryBatchSize -CooldownMinutes $RetryCooldownMinutes -Project $RetryProject -NoNewWindow:$NoNewWindow -PrintOnly
    }
    Write-Host "Tip: abre 2 terminals y ejecuta esos comandos en paralelo." -ForegroundColor Yellow
  } elseif ($NoNewWindow) {
    # Run both processes without opening new windows (shares this console).
    $backendProc = Start-Process -FilePath $python -ArgumentList $backendArgs -WorkingDirectory $repoRoot -NoNewWindow -PassThru
    $frontendProc = Start-Process -FilePath "npm" -ArgumentList $frontendArgs -WorkingDirectory (Join-Path $repoRoot "frontend") -NoNewWindow -PassThru
    Write-Host "Started backend PID=$($backendProc.Id) and frontend PID=$($frontendProc.Id) (no new windows)." -ForegroundColor Green
    if (-not $DisableNeo4jRetry) {
      $retryProc = Start-Neo4jRetryLoop -RepoRoot $repoRoot -PythonPath $python -IntervalSec $RetryInterval -BatchSize $RetryBatchSize -CooldownMinutes $RetryCooldownMinutes -Project $RetryProject -NoNewWindow:$NoNewWindow
      if ($retryProc) {
        Write-Host "Started Neo4j retry PID=$($retryProc.Id)." -ForegroundColor Green
      }
    }
  } else {
    Start-Process -FilePath $python -ArgumentList $backendArgs -WorkingDirectory $repoRoot | Out-Null
    Start-Process -FilePath "npm" -ArgumentList $frontendArgs -WorkingDirectory (Join-Path $repoRoot "frontend") | Out-Null
    if (-not $DisableNeo4jRetry) {
      Start-Neo4jRetryLoop -RepoRoot $repoRoot -PythonPath $python -IntervalSec $RetryInterval -BatchSize $RetryBatchSize -CooldownMinutes $RetryCooldownMinutes -Project $RetryProject -NoNewWindow:$NoNewWindow
    }
  }

  $ok = Wait-HttpOk -Url "http://$BackendHost`:$BackendPort/healthz" -TimeoutSec 25
  if ($ok) {
    Write-Host "Backend OK: http://$BackendHost`:$BackendPort/healthz" -ForegroundColor Green
  } else {
    Write-Host "Backend no responde aún en http://$BackendHost`:$BackendPort/healthz" -ForegroundColor Yellow
  }

  if ($NoNewWindow -and (-not $PrintOnly)) {
    Write-Host "Dev running. Press CTRL+C to stop." -ForegroundColor Cyan
    # Keep the script alive so child processes remain running.
    try {
      if ($retryProc) {
        Wait-Process -Id @($backendProc.Id, $frontendProc.Id, $retryProc.Id)
      } else {
        Wait-Process -Id @($backendProc.Id, $frontendProc.Id)
      }
    } catch {
      # Best-effort: allow CTRL+C to break.
    }
  }
}

if ($Action -in @('smoke','all')) {
  $base = "http://$BackendHost`:$BackendPort"
  Write-Host "Running smoke test: $base/healthz" -ForegroundColor Cyan

  $healthy = Wait-HttpOk -Url "$base/healthz" -TimeoutSec 20
  if (-not $healthy) {
    Write-Host "Backend no responde en $base" -ForegroundColor Yellow
    Write-Host "Inicia con: powershell -ExecutionPolicy Bypass -File scripts/run_local.ps1 -Action dev" -ForegroundColor Yellow
  } else {
    Write-Host "Backend healthy — POST mínimo a /neo4j/query..." -ForegroundColor Green
    $key = $env:NEO4J_API_KEY
    if (-not $key -and (Test-Path $envPath)) {
      $key = (Get-Content $envPath | Where-Object { $_ -match '^\s*NEO4J_API_KEY\s*=' } | ForEach-Object { ($_ -split '=',2)[1].Trim().Trim('"').Trim("'") }) -join ''
    }
    if (-not $key) {
      Write-Host "NEO4J_API_KEY no encontrado (env/.env)." -ForegroundColor Yellow
      Write-Host "Saltando smoke Cypher; /healthz OK." -ForegroundColor Yellow
      return
    }

    $body = @{ cypher = "RETURN 1 AS ok"; formats = @("raw") } | ConvertTo-Json
    try {
      $resp = Invoke-RestMethod -Uri "$base/neo4j/query" -Method POST -Headers @{ "X-API-Key" = $key } -Body $body -ContentType "application/json" -ErrorAction Stop
      $resp | ConvertTo-Json -Depth 5 | Write-Output
    } catch {
      Write-Host "Smoke POST falló: $($_.Exception.Message)" -ForegroundColor Red
    }
  }
}

Write-Host "Done." -ForegroundColor Cyan

