# Workbook Logs MVP Fase 1

Ubicación del archivo:
- `workbook_logs_mvp_fase1.workbook` (archivo JSON en el repo)

Importación rápida:
1) Log Analytics Workspace -> Workbooks -> New
2) Edit -> Advanced editor (</>)
3) Pegar el JSON del archivo
4) Apply -> Save

Parámetros principales:
- **TimeRange**: rango de tiempo del workbook
- **AppName**: axial-api (por defecto)
- **BuildVersion**, **TestRunId**, **RouteFilter**
- **ValidateRoute**: /api/codes/candidates/{id}/validate (por defecto)
- **SlowMs**: 5000 (por defecto)

Paneles incluidos:
- **00 Detector tabla**
- **01 Schema Health**
- **02 Top endpoints**
- **03 Validate hourly**
- **04 Validate top request_id**
- **05 Segments dominant**
- **06 Regression by build**

Cambios recientes (implementación aplicada):
- **Alertas creadas**: `alert-error-rate-validate` (Sev2, 5m, ventana 10m), `alert-slow-rate-validate` (Sev2, 5m, ventana 15m), `alert-schema-health` (Sev3, 15m, ventana 1h). Todas usan Action Group `ag-axial-warn` y workspace `axial-law` (RG: newsites).
- **KQL actualizadas**: `queries/09_alert_schema_health.kql` ahora incluye medición de parseabilidad JSON (`pct_json`), guardias mínimos y condición dual; `queries/07_alert_slow_rate.kql` y `queries/08_alert_error_rate.kql` usados para las alertas.
- **Runbooks y triage**: se agregaron `runbooks/slow_rate.md`, `runbooks/error_rate.md` y `reporter/triage.py` con pasos de respuesta y clasificación de severidad.
- **Reporter**: `scripts/daily_logs_reporter.py` genera reportes Markdown en `reports/daily` y ahora integra la sección de triage.

Notas operativas y pruebas:
- Para pruebas controladas, establecé un header `X-Test-Run-Id` en las solicitudes y filtrá en el workbook/reportes.
- Para validar alertas manualmente, ejecutar tráfico que cumpla `min_req` (p.ej. 20–50) y provoque errores o latencias.

Guardias y recomendaciones (prod estable):
- Schema Health: `request_events >= 50` (ventana 1h) y condición: `pct_request_min < 95 OR pct_json < 99`.
- Error/Slow: las queries ya incluyen `min_req` (p.ej. 20) para evitar falsos positivos.

Cómo recrear/actualizar las alertas por CLI (ejemplo):
```powershell
# obtener workspace id y action group id
$wsId = az monitor log-analytics workspace show -g newsites -n axial-law --query id -o tsv
$agId = az monitor action-group show -g newsites -n ag-axial-warn --query id -o tsv

# crear la alerta (ejemplo error-rate)
az monitor scheduled-query create -g newsites -n alert-error-rate-validate \
	--scopes $wsId \
	--condition "count 'Q1' > 0 resource id _ResourceId" \
	--condition-query "Q1=$(Get-Content -Raw queries/08_alert_error_rate.kql)" \
	--evaluation-frequency 5m --window-size 10m --severity 2 --action-groups $agId
```

Archivos clave (repo):
- `queries/07_alert_slow_rate.kql`
- `queries/08_alert_error_rate.kql`
- `queries/09_alert_schema_health.kql` (actualizada)
- `scripts/daily_logs_reporter.py`
- `reporter/triage.py`
- `runbooks/slow_rate.md`, `runbooks/error_rate.md`

Próximos pasos recomendados:
- Importar el workbook en el portal y verificar visualizaciones.
- Ejecutar pruebas controladas con `X-Test-Run-Id` para confirmar triggers de alertas.
- Ajustar `min_n` (50) si detectas falsos positivos o tráfico bajo.

Contacto rápido:
- Si querés, importo el workbook en el portal y hago un smoke-test bajando temporalmente `min_pct_json`.
