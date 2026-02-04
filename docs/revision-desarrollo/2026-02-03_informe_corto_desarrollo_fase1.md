# Informe corto - Desarrollo Fase 1 (Logs MVP)

Fecha: 2026-02-03

## Hecho
- Middleware de logs en API con schema_version, request_id, test_run_id, route, build_version y sample_rate.
- Logs de consola en JSON con LOG_CONSOLE_JSON (prod).
- KQL base + Schema Health en queries/.
- Workbook MVP generado (import JSON).
- Reporter diario (LogsQueryClient) y smoke test OK.
- Alertas creadas en Azure Monitor (slow_rate y error_rate) con action group ag-axial-warn.

## Pendiente
- Importar workbook actualizado en el portal y validar Schema Health (pct_request_min >= 95%).
- Disparar test controlado con X-Test-Run-Id y confirmar alertas en Action Group.
- Revisar el reporte diario y ajustar thresholds si hay ruido.

## Recursos claves
- Workbook: C:\Users\osval\Downloads\workbook_logs_mvp_fase1.workbook
- Reporte diario: reports/daily/2026-02-03.md
- Queries: queries/*.kql
- Reporter: scripts/daily_logs_reporter.py
