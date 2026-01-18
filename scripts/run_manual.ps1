<#
.SYNOPSIS
    Manual/Referencia + runner opcional de etapas post-ingesta.

.DESCRIPTION
    Este script sirve para dos cosas:
    1) `reference`: imprimir comandos recomendados (sin ejecutarlos).
    2) `run`: ejecutar un subconjunto seguro de etapas (3-9) y guardar logs.

    Para etapas que requieren insumos contextuales (p.ej. núcleo), se activan solo si entregas parámetros.
#>

param(
    [ValidateSet("reference","run")]
    [string]$Action = "reference",

    [string]$EnvFile = ".env",
    [string]$LogDir = "logs",

    # Etapa 5/9 (opcional)
    [string]$CategoriaNucleo = "",
    [string]$PromptNucleo = "",

    # Etapa 7 outliers (opcional)
    [string]$OutliersArchivo = "",

    # Etapa 6 transversal (opcional)
    [string]$TransversalPrompt = "",
    [string]$TransversalAttribute = "genero",
    [string[]]$TransversalValues = @("F","M"),
    [string[]]$TransversalSegments = @("Mujeres|genero=F","Hombres|genero=M")
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-VenvPython {
    param([string]$RepoRoot)
    $py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $py) { return $py }
    return "python"
}

function Print-Command {
    param([string]$Title, [string]$Cmd)
    Write-Host "`n=== $Title ===" -ForegroundColor Yellow
    Write-Host $Cmd -ForegroundColor DarkGray
}

function Invoke-Stage {
    param(
        [string]$Name,
        [string]$Command,
        [string]$LogFile
    )
    Write-Host "`n=== $Name ===" -ForegroundColor Yellow
    Write-Host "Command: $Command" -ForegroundColor DarkGray
    try {
        Invoke-Expression $Command 2>&1 | Tee-Object -FilePath $LogFile
    } catch {
        Write-Host "Error en $Name, revisa $LogFile" -ForegroundColor Red
        throw
    }
}

$repoRoot = Resolve-RepoRoot
Set-Location $repoRoot
$python = Get-VenvPython -RepoRoot $repoRoot

if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

if ($Action -eq "reference") {
    Print-Command "Etapa 3 · coding stats" "& '$python' main.py --env $EnvFile coding stats"
    Print-Command "Etapa 4 · axial gds (louvain)" "& '$python' main.py --env $EnvFile axial gds --algorithm louvain"

    Print-Command "Etapa 5 · nucleus report (requiere inputs)" "& '$python' main.py --env $EnvFile nucleus report --categoria '<Categoria Núcleo>' --prompt '<Descripción semántica del núcleo>'"

    Print-Command "Etapa 6 · transversal (opcional)" "& '$python' main.py --env $EnvFile transversal dashboard --prompt '<tema a explorar>' --attribute $TransversalAttribute --values $($TransversalValues -join ' ') --segment '$($TransversalSegments[0])' --segment '$($TransversalSegments[1])'"

    Print-Command "Etapa 7 · validation curve" "& '$python' main.py --env $EnvFile validation curve --window 3 --threshold 0"
    Print-Command "Etapa 7 · validation outliers (opcional)" "& '$python' main.py --env $EnvFile validation outliers --archivo '<Archivo.docx>' --limit 30 --threshold 0.8"

    Print-Command "Etapa 9 · report outline" "& '$python' main.py --env $EnvFile report outline"
    Print-Command "Etapa 9 · report build (requiere inputs)" "& '$python' main.py --env $EnvFile report build --categoria-nucleo '<Categoria Núcleo>' --prompt-nucleo '<Descripción semántica>' --output informes/informe_integrado.md --annex-dir informes/anexos --manifest informes/report_manifest.json"

    Write-Host "`nTip: usa -Action run para ejecutar (con logs)." -ForegroundColor Cyan
    return
}

# Action = run
Invoke-Stage "Etapa 3 · coding stats" "& '$python' main.py --env $EnvFile coding stats" "$LogDir/etapa3_coding_stats.log"
Invoke-Stage "Etapa 4 · axial gds (louvain)" "& '$python' main.py --env $EnvFile axial gds --algorithm louvain" "$LogDir/etapa4_axial_louvain.log"

if ($CategoriaNucleo.Trim() -and $PromptNucleo.Trim()) {
    Invoke-Stage "Etapa 5 · nucleus report" "& '$python' main.py --env $EnvFile nucleus report --categoria '$CategoriaNucleo' --prompt '$PromptNucleo'" "$LogDir/etapa5_nucleus.log"
} else {
    Write-Host "`n[SKIP] Etapa 5 nucleus: falta -CategoriaNucleo/-PromptNucleo" -ForegroundColor Yellow
}

if ($TransversalPrompt.Trim()) {
    $valuesArg = ($TransversalValues | ForEach-Object { "$_" }) -join " "
    $segmentsArg = ($TransversalSegments | ForEach-Object { "--segment '$_'" }) -join " "
    Invoke-Stage "Etapa 6 · transversal dashboard" "& '$python' main.py --env $EnvFile transversal dashboard --prompt '$TransversalPrompt' --attribute $TransversalAttribute --values $valuesArg $segmentsArg" "$LogDir/etapa6_transversal_dashboard.log"
} else {
    Write-Host "`n[SKIP] Etapa 6 transversal: falta -TransversalPrompt" -ForegroundColor Yellow
}

Invoke-Stage "Etapa 7 · validation curve" "& '$python' main.py --env $EnvFile validation curve --window 3 --threshold 0" "$LogDir/etapa7_validation_curve.log"

if ($OutliersArchivo.Trim()) {
    Invoke-Stage "Etapa 7 · validation outliers" "& '$python' main.py --env $EnvFile validation outliers --archivo '$OutliersArchivo' --limit 30 --threshold 0.8" "$LogDir/etapa7_validation_outliers.log"
} else {
    Write-Host "`n[SKIP] Etapa 7 outliers: falta -OutliersArchivo" -ForegroundColor Yellow
}

Invoke-Stage "Etapa 9 · report outline" "& '$python' main.py --env $EnvFile report outline" "$LogDir/etapa9_report_outline.log"

if ($CategoriaNucleo.Trim() -and $PromptNucleo.Trim()) {
    Invoke-Stage "Etapa 9 · report build" "& '$python' main.py --env $EnvFile report build --categoria-nucleo '$CategoriaNucleo' --prompt-nucleo '$PromptNucleo' --output informes/informe_integrado.md --annex-dir informes/anexos --manifest informes/report_manifest.json" "$LogDir/etapa9_report_build.log"
} else {
    Write-Host "`n[SKIP] Etapa 9 build: falta -CategoriaNucleo/-PromptNucleo" -ForegroundColor Yellow
}

Write-Host "`nFlujo completado. Revisa '$LogDir' para detalles." -ForegroundColor Green
