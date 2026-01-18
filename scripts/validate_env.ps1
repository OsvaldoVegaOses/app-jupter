# Script de Validación del Entorno de Desarrollo
# Ejecutar antes de iniciar el desarrollo para verificar la configuración

Write-Host "Validando configuracion del entorno..." -ForegroundColor Cyan
Write-Host ""

$errors = @()
$warnings = @()

# 1. Verificar que existe .env del frontend
$frontendEnv = "frontend\.env"
if (Test-Path $frontendEnv) {
    $content = Get-Content $frontendEnv -Raw
    
    # Verificar VITE_API_BASE / VITE_BACKEND_URL
    # CANÓNICO (DEV LOCAL): VITE_API_BASE vacío para usar el proxy same-origin de Vite.
    if ($content -match "(?m)^\s*VITE_API_BASE\s*=\s*$") {
        Write-Host "OK: VITE_API_BASE vacio (modo proxy same-origin recomendado)" -ForegroundColor Green
    }
    elseif ($content -match "(?m)^\s*VITE_API_BASE\s*=\s*.+$") {
        $warnings += "WARN: VITE_API_BASE esta definido: el navegador llamara directo al backend (puede requerir CORS si Vite usa 5174/5175). Recomendado: dejarlo vacio y usar VITE_BACKEND_URL."
    }
    else {
        $warnings += "WARN: VITE_API_BASE no esta presente (ok si usas proxy); revisa frontend/.env"
    }

    if ($content -match "(?m)^\s*VITE_BACKEND_URL\s*=\s*http://127\.0\.0\.1:8000\s*$") {
        Write-Host "OK: VITE_BACKEND_URL configurado correctamente (backend 8000)" -ForegroundColor Green
    }
    elseif ($content -match "(?m)^\s*VITE_BACKEND_URL\s*=") {
        $warnings += "WARN: VITE_BACKEND_URL no apunta a http://127.0.0.1:8000"
    }
    else {
        $warnings += "WARN: VITE_BACKEND_URL no esta definido (Vite usara http://localhost:8000 por defecto)"
    }
    
    # Verificar VITE_NEO4J_API_KEY
    if ($content -match "VITE_NEO4J_API_KEY") {
        Write-Host "OK: VITE_NEO4J_API_KEY esta definido" -ForegroundColor Green
    }
    else {
        $errors += "ERROR: VITE_NEO4J_API_KEY no esta definido"
    }
}
else {
    $errors += "ERROR: No existe frontend/.env"
}

# 2. Verificar que existe .env principal
$mainEnv = ".env"
if (Test-Path $mainEnv) {
    $content = Get-Content $mainEnv -Raw
    
    # Verificar PostgreSQL
    if ($content -match "PGHOST") {
        Write-Host "OK: Configuracion de PostgreSQL presente" -ForegroundColor Green
    }
    else {
        $errors += "ERROR: Configuracion de PostgreSQL faltante (PGHOST)"
    }
    
    # Verificar Azure OpenAI
    if ($content -match "AZURE_OPENAI_API_KEY") {
        Write-Host "OK: Azure OpenAI API Key configurada" -ForegroundColor Green
    }
    else {
        $warnings += "WARN: Azure OpenAI API Key no esta configurada"
    }

    # Verificar Azure Storage (opcional)
    if ($content -match "AZURE_STORAGE_CONNECTION_STRING") {
        Write-Host "OK: Azure Storage connection string esta definido (archivado DOCX habilitado)" -ForegroundColor Green
    }
    else {
        $warnings += "WARN: AZURE_STORAGE_CONNECTION_STRING no esta configurada (no se archivaran DOCX en Blob)"
    }
    
}
else {
    $errors += "ERROR: No existe .env en la raiz del proyecto"
}

# 3. Verificar que PostgreSQL está corriendo
Write-Host ""
Write-Host "Verificando servicios..." -ForegroundColor Cyan
try {
    $null = & pg_isready -h localhost -p 5432 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "OK: PostgreSQL esta corriendo en puerto 5432" -ForegroundColor Green
    }
    else {
        $warnings += "WARN: PostgreSQL no responde en localhost:5432"
    }
}
catch {
    $warnings += "WARN: No se pudo verificar PostgreSQL (pg_isready no disponible)"
}

# 4. Verificar que el backend está corriendo
try {
    $null = Invoke-WebRequest -Uri "http://localhost:8000/healthz" -Method GET -TimeoutSec 5 -ErrorAction Stop
    Write-Host "OK: Backend esta corriendo en puerto 8000" -ForegroundColor Green
}
catch {
    $warnings += "WARN: Backend no responde en localhost:8000"
}

# 5. Verificar node_modules
if (Test-Path "frontend\node_modules") {
    Write-Host "OK: node_modules existe en frontend" -ForegroundColor Green
}
else {
    $errors += "ERROR: Falta ejecutar 'npm install' en frontend/"
}

# Resultados
Write-Host ""
Write-Host "===================================================" -ForegroundColor White

if ($errors.Count -gt 0) {
    Write-Host ""
    Write-Host "ERRORES:" -ForegroundColor Red
    foreach ($err in $errors) {
        Write-Host $err -ForegroundColor Red
    }
}

if ($warnings.Count -gt 0) {
    Write-Host ""
    Write-Host "ADVERTENCIAS:" -ForegroundColor Yellow
    foreach ($warn in $warnings) {
        Write-Host $warn -ForegroundColor Yellow
    }
}

Write-Host ""
if ($errors.Count -eq 0 -and $warnings.Count -eq 0) {
    Write-Host "OK: Configuracion valida. Listo para desarrollar." -ForegroundColor Green
    exit 0
}
elseif ($errors.Count -eq 0) {
    Write-Host "WARN: Hay advertencias pero puedes continuar." -ForegroundColor Yellow
    exit 0
}
else {
    Write-Host "ERROR: Hay errores que deben corregirse antes de continuar." -ForegroundColor Red
    exit 1
}
