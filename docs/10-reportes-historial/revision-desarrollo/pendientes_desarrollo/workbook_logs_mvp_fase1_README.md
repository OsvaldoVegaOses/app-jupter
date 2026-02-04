# Workbook Logs MVP Fase 1

Ubicación del archivo:

* `workbook_logs_mvp_fase1.workbook` (archivo JSON en el repo)

---

## Importación rápida (Azure Portal)

1. Log Analytics Workspace → **Workbooks** → **New**
2. **Edit** → **Advanced editor (</>)**
3. Pegar el JSON del archivo `workbook_logs_mvp_fase1.workbook`
4. **Apply** → **Save**

---

## Parámetros principales

* **TimeRange**: rango de tiempo del workbook
* **AppName**: `axial-api` (por defecto)
* **BuildVersion**, **TestRunId**, **RouteFilter**
* **ValidateRoute**: `/api/codes/candidates/{id}/validate` (por defecto)
* **SlowMs**: `5000` (por defecto)

---

## Paneles incluidos

* **00 Detector tabla**
* **01 Schema Health**
* **02 Top endpoints**
* **03 Validate hourly**
* **04 Validate top request_id**
* **05 Segments dominant**
* **06 Regression by build**

---

## Cambios recientes (implementación aplicada)

* **Alertas creadas**:

  * `alert-error-rate-validate` (Sev2, frecuencia 5m, ventana 10m)
  * `alert-slow-rate-validate` (Sev2, frecuencia 5m, ventana 15m)
  * `alert-schema-health` (Sev3, frecuencia 15m, ventana 1h)
    Todas apuntan a Action Group `ag-axial-warn` y workspace `axial-law` (RG: `newsites`).

* **KQL actualizadas**:

  * `queries/09_alert_schema_health.kql` incluye medición de parseabilidad JSON (`pct_json`), guardias mínimos y condición dual.
  * `queries/07_alert_slow_rate.kql` y `queries/08_alert_error_rate.kql` se usan como base para las alertas.

* **Runbooks y triage**:

  * `runbooks/slow_rate.md`, `runbooks/error_rate.md`
  * `reporter/triage.py` con pasos de respuesta y clasificación de severidad.

* **Reporter**:

  * `scripts/daily_logs_reporter.py` genera reportes Markdown en `reports/daily` e integra la sección de triage.

---

## Notas operativas y pruebas

* Para pruebas controladas, establecer el header `X-Test-Run-Id` en las solicitudes y filtrar en workbook/reportes.
* Para validar alertas manualmente:

  * ejecutar tráfico que cumpla `min_req` (p.ej. 20–50)
  * y provocar errores o latencias (según el tipo de alerta)

---

## Guardias y recomendaciones (producción con tráfico estable)

* **Schema Health** (ventana 1h):

  * Guardia: `request_events >= 50`
  * Condición: `pct_request_min < 95 OR pct_json < 99`

* **Error/Slow**:

  * Las queries incluyen `min_req` (p.ej. 20) para evitar falsos positivos.

---

## Cómo recrear/actualizar las alertas por CLI (ejemplo)

```powershell
# obtener workspace id y action group id
$wsId = az monitor log-analytics workspace show -g newsites -n axial-law --query id -o tsv
$agId = az monitor action-group show -g newsites -n ag-axial-warn --query id -o tsv

# crear la alerta (ejemplo error-rate)
az monitor scheduled-query create -g newsites -n alert-error-rate-validate `
  --scopes $wsId `
  --condition "count 'Q1' > 0 resource id _ResourceId" `
  --condition-query "Q1=$(Get-Content -Raw queries/08_alert_error_rate.kql)" `
  --evaluation-frequency 5m --window-size 10m --severity 2 --action-groups $agId
```

> Nota: para `alert-schema-health`, el `condition` no usa `resource id _ResourceId` si la query no proyecta `_ResourceId`.

---

## Archivos clave (repo)

* `queries/07_alert_slow_rate.kql`
* `queries/08_alert_error_rate.kql`
* `queries/09_alert_schema_health.kql` (actualizada)
* `scripts/daily_logs_reporter.py`
* `reporter/triage.py`
* `runbooks/slow_rate.md`, `runbooks/error_rate.md`

---

## Próximos pasos recomendados

* Importar el workbook en el portal y verificar visualizaciones.
* Ejecutar pruebas controladas con `X-Test-Run-Id` para confirmar triggers de alertas.
* Ajustar guardias y umbrales (`min_req`, `request_events`, `pct_json`, `pct_request_min`) según ruido/volumen observado.
* Si aparece ruido principalmente por `pct_json`, considerar el refinamiento futuro (sección siguiente).

---

## Refinamientos futuros (Hardening)

### 1) Separar mínimos de muestra para Schema Health

**Motivación:** en producción con alto volumen, `pct_json` puede fluctuar por pocas líneas no-JSON (stacktraces o logs de librerías). Separar el mínimo de muestra reduce falsos positivos sin perder cobertura de schema drift real.

**Propuesta:**

* `min_n_request = 50` (para evaluar `pct_request_min`)
* `min_n_lines = 200` (para evaluar `pct_json`)

**Regla:**

* Alertar por **schema drift** cuando:

  * `request_events >= min_n_request` y `pct_request_min < 95`
* Alertar por **parseabilidad** cuando:

  * `total_lines >= min_n_lines` y `pct_json < 99`

**Implementación (conceptual en KQL):**

* Mantener `try_parse_json`
* Aplicar guardias distintos por condición:

  * `(request_events >= min_n_request and pct_request_min < 95) OR (total_lines >= min_n_lines and pct_json < 99)`

**Cuándo activarlo:**

* `alert-schema-health` dispara esporádicamente por `pct_json`, pero `pct_request_min` se mantiene sano.
* Hay logs no estructurados ocasionales y se busca reducir ruido (Sev3).

---

## Smoke-test (controlado) recomendado

* Definir un `X-Test-Run-Id` y ejecutar un escenario completo (login → proyecto → ingesta → candidatos → validate).
* Confirmar en Workbook:

  * `/validate` hourly y top request_id
  * segmentos dominantes (si existen `segment.*`)
* Para probar el pipeline de salud de esquema sin dejar cambios permanentes:

  * bajar temporalmente `min_pct_json` a `100` en `09_alert_schema_health.kql`
  * esperar 1 ciclo de evaluación
  * restaurar `min_pct_json` al valor original (p.ej. `99`)
