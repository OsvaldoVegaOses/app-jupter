Param(
    [Parameter(Mandatory = $true)]
    [string]$WorkspaceId,
    [string]$ContainerAppName = "axial-api",
    [int]$WindowHours = 24,
    [string]$OutDir = "reports/daily",
    [string]$QueriesDir = "queries"
)

$env:LOG_WORKSPACE_ID = $WorkspaceId
$env:CONTAINER_APP_NAME = $ContainerAppName
$env:REPORT_WINDOW_HOURS = $WindowHours
$env:REPORT_OUT_DIR = $OutDir
$env:REPORT_QUERIES_DIR = $QueriesDir

python scripts/daily_logs_reporter.py
