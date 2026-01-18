<#
.SYNOPSIS
    Orquestador de pruebas End-to-End para el pipeline de ingesta.

.DESCRIPTION
    Este script ejecuta un ciclo completo de prueba E2E:
    1. Preparación de datos de prueba
    2. Creación/verificación del proyecto
    3. Limpieza pre-test (opcional)
    4. Ejecución de ingesta
    5. Verificación cross-database
    6. Limpieza post-test (opcional)

.PARAMETER EnvFile
    Ruta al archivo .env (default: .env)

.PARAMETER ProjectID
    ID del proyecto de prueba (default: test-ingesta-proj)

.PARAMETER SourceFile
    Archivo DOCX a ingestar (default: data/interviews/test_ingesta.docx)

.PARAMETER AutoCleanup
    Si está presente, ejecuta limpieza automática al finalizar

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/run_e2e.ps1
    
.EXAMPLE
    .\scripts\run_e2e.ps1 -ProjectID "mi-proyecto" -AutoCleanup

.NOTES
    Genera reporte JSON en report_e2e.json
#>

param (
    [string]$EnvFile = ".env",
    [string]$ProjectID = "test-ingesta-proj",
    [string]$SourceFile = "data/interviews/test_ingesta.docx",
    [switch]$Cleanup,
    [switch]$AutoCleanup
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path
}

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

function Get-VenvPython {
    param([string]$RepoRoot)
    $py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $py) { return $py }
    return "python"
}

$repoRoot = Resolve-RepoRoot
Set-Location $repoRoot

$envPath = Join-Path $repoRoot $EnvFile
Import-DotEnvFile -Path $envPath

# Make backend helpers load the same env file.
$env:APP_ENV_FILE = $EnvFile
$python = Get-VenvPython -RepoRoot $repoRoot

Write-Host ">>> [E2E] Starting End-to-End Test for Project: $ProjectID" -ForegroundColor Cyan

# 1. Setup
Write-Host ">>> [E2E] Step 1: Data Preparation" -ForegroundColor Yellow
if (-not (Test-Path $SourceFile)) {
    Write-Host "Creating test file copy..."
    Copy-Item "data/interviews/Natalia Molina.docx" -Destination $SourceFile
}

# 1.1 Ensure Project Exists
Write-Host ">>> [E2E] Step 1.1: Ensure Project Exists" -ForegroundColor Yellow
& $python main.py --env $EnvFile project create --name "$ProjectID" --description "E2E Test Project" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Project might already exist (ignoring create error)." -ForegroundColor Gray
}

# 2. Pre-Cleanup (Optional)
if ($Cleanup -or $AutoCleanup) {
    Write-Host ">>> [E2E] Step 2: Pre-Test Cleanup" -ForegroundColor Yellow
    $env:CLEANUP_CONFIRM = "true"
    & $python scripts/verify_ingestion.py --project $ProjectID --env $EnvFile --cleanup --force
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Pre-cleanup failed with code $LASTEXITCODE"
    }
} else {
    Write-Host ">>> [E2E] Step 2: Pre-Test Cleanup (SKIPPED)" -ForegroundColor DarkGray
}

# 3. Ingestion
Write-Host ">>> [E2E] Step 3: Running Ingestion" -ForegroundColor Yellow
$StartTime = Get-Date
& $python main.py --env $EnvFile --project $ProjectID ingest "$SourceFile"
$EndTime = Get-Date
$Duration = $EndTime - $StartTime
Write-Host "Ingestion took $($Duration.TotalSeconds) seconds." -ForegroundColor Gray
if ($LASTEXITCODE -ne 0) {
    Write-Error "Ingestion failed with code $LASTEXITCODE"
}

# 4. Verification
Write-Host ">>> [E2E] Step 4: Verification" -ForegroundColor Yellow
& $python scripts/verify_ingestion.py --project $ProjectID --env $EnvFile --json-out "report_e2e.json" --timeout 120
if ($LASTEXITCODE -eq 0) {
    Write-Host ">>> [E2E] VERIFICATION PASSED" -ForegroundColor Green
}
else {
    Write-Host ">>> [E2E] VERIFICATION FAILED (Code $LASTEXITCODE)" -ForegroundColor Red
}

# 5. Post-Cleanup (Optional)
if ($AutoCleanup) {
    Write-Host ">>> [E2E] Step 5: Post-Test Cleanup" -ForegroundColor Yellow
    $env:CLEANUP_CONFIRM = "true"
    & $python scripts/verify_ingestion.py --project $ProjectID --env $EnvFile --cleanup --force
}

Write-Host ">>> [E2E] Test Cycle Complete. Report saved to report_e2e.json" -ForegroundColor Cyan
