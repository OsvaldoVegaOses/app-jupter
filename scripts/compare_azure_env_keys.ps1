param(
    [string]$ResourceGroup = "newsites",
    [string]$ContainerAppName = "axial-api",
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvFile)) {
    Write-Error "Env file not found: $EnvFile"
}

Write-Host "Comparing env var names..." -ForegroundColor Cyan
Write-Host "  Azure: $ResourceGroup / $ContainerAppName"
Write-Host "  Local: $EnvFile"
Write-Host ""

$azureNames = az containerapp show `
    -g $ResourceGroup `
    -n $ContainerAppName `
    --query "properties.template.containers[0].env[].name" `
    -o json | ConvertFrom-Json

$localNames = @()
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=') {
        $localNames += $matches[1]
    }
}
$localNames = $localNames | Select-Object -Unique

$onlyAzure = $azureNames | Where-Object { $_ -notin $localNames } | Sort-Object
$onlyLocal = $localNames | Where-Object { $_ -notin $azureNames } | Sort-Object

Write-Host "ONLY_AZURE:" -ForegroundColor Yellow
if ($onlyAzure.Count -eq 0) {
    Write-Host "  (none)" -ForegroundColor DarkGray
} else {
    $onlyAzure | ForEach-Object { Write-Host "  $_" }
}

Write-Host ""
Write-Host "ONLY_LOCAL:" -ForegroundColor Yellow
if ($onlyLocal.Count -eq 0) {
    Write-Host "  (none)" -ForegroundColor DarkGray
} else {
    $onlyLocal | ForEach-Object { Write-Host "  $_" }
}

Write-Host ""
if ($onlyAzure.Count -eq 0 -and $onlyLocal.Count -eq 0) {
    Write-Host "OK: No key drift detected." -ForegroundColor Green
    exit 0
}

Write-Host "Done. Review drift before deploy." -ForegroundColor Cyan
