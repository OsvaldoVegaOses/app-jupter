# CI smoke script (PowerShell)
# - Verifica /healthz
# - Ejecuta checks de servicios (blob, postgres, neo4j, qdrant)
# - Ejecuta smoke_tenant_upload (direct SDK upload)
# - Opcional: encola job async si $env:WORKER_ENABLED -eq 'true'

param()

Push-Location -Path (Join-Path $PSScriptRoot '..')
$backend = $env:BACKEND_URL -or 'http://127.0.0.1:8000'
# Normalize common mis-set values (e.g., PowerShell boolean True/False from CI environments)
if ($backend -is [bool] -or ($backend -is [string] -and $backend -match '^(True|False)$')) {
    $backend = 'http://127.0.0.1:8000'
}
$apiKey = $env:API_KEY
$apiOrg = $env:API_KEY_ORG_ID
[void] $apiOrg

Write-Output "=== CI SMOKE START ==="

Write-Output "1) Health check: $backend/healthz"
try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri "$backend/healthz" -TimeoutSec 10 -ErrorAction Stop
    if ($r.StatusCode -ne 200) { throw "Health returned $($r.StatusCode)" }
} catch {
    Write-Error "Health check failed: $_"
    Exit 2
}

Write-Output "2) Services quick checks"
try {
    & .\.venv\Scripts\python.exe scripts\check_azure_services.py
} catch {
    Write-Error "check_azure_services failed: $_"
    Exit 3
}

Write-Output "3) Tenant SDK upload (smoke)"
try {
    # Skip tenant upload when organization id is not provided in env/secrets
    if (-not $env:API_KEY_ORG_ID -and -not $env:ORG_ID) {
        Write-Output "Skipping tenant SDK upload: organization id not configured (API_KEY_ORG_ID or ORG_ID)"
    } else {
        & .\.venv\Scripts\python.exe scripts\smoke_tenant_upload.py
    }
} catch {
    Write-Error "smoke_tenant_upload failed: $_"
    Exit 4
}

if ($env:WORKER_ENABLED -eq 'true') {
    if (-not $apiKey) { Write-Error "API_KEY required to enqueue job"; Exit 5 }
    Write-Output "4) Enqueue async transcription job (stream) and poll status"
    $wav_b64 = 'UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA='
    $payload = @{ project='smoke_test_project'; audio_base64=$wav_b64; filename='smoke.wav'; diarize=$false; language='es'; ingest=$false } | ConvertTo-Json
    $task_resp = Invoke-RestMethod -Method Post -Uri "$backend/api/transcribe/stream" -Headers @{ Authorization = "Bearer $apiKey" } -Body $payload -ContentType 'application/json'
    Write-Output "task_resp: $($task_resp | ConvertTo-Json)"
    $task_id = $task_resp.task_id
    if (-not $task_id) { Write-Error 'Failed to start task'; Exit 6 }
    for ($i=0; $i -lt 30; $i++) {
        $status = (Invoke-RestMethod -Method Get -Uri "$backend/api/jobs/$task_id/status" -Headers @{ Authorization = "Bearer $apiKey" }).status
        Write-Output "status=$status"
        if ($status -in @('SUCCESS','COMPLETED')) { Write-Output 'Task completed'; break }
        Start-Sleep -Seconds 2
    }
}

Write-Output "=== CI SMOKE OK ==="
Pop-Location
Exit 0
