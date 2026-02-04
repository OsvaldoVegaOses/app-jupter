# Fase 1 (MVP) Logs: clasificacion, seguimiento y reportes

Fecha: 2026-02-03
Contexto: Azure Container Apps + Azure Monitor + Log Analytics

## Determinacion de valor (aporta o no aporta)

Aporta valor inmediato si hoy se cumple al menos una de estas condiciones:
- No hay visibilidad confiable de errores/lentitud por endpoint.
- Hay incidentes recurrentes y no hay evidencia trazable (request_id, duracion, build).
- Se necesita comparar deploys con metricas consistentes (p95/error rate).
- Los reportes actuales son manuales, lentos o no repetibles.

Valor concreto esperado en 1-2 semanas:
- Reporte diario con top problemas, evidencia (request_id) y recomendaciones.
- Diagnostico rapido de cuello de botella por segmentos (db/neo4j/qdrant/llm).
- Panel (Workbook) con 4-6 consultas core para revision rapida.
- Alertas simples para evitar degradacion silenciosa.

Si el equipo ya cuenta con:
- Logs estructurados con duracion, request_id, build_version.
- Panel p95 y error rate operativo y confiable.
Entonces el valor incremental puede ser menor; aun asi, el reporte diario y la clasificacion por reglas suele mejorar la disciplina operativa.

---

## Entregables finales de Fase 1 (MVP)

- Logs estandarizados en JSON con campos minimos.
- Clasificacion por reglas: slow/error/pool/dependency.
- Workbook con 4-6 consultas KQL core.
- Reporte diario automatico (Markdown/JSON) con top problemas + evidencia + recomendaciones.
- (Opcional) 1-2 alertas simples para p95 alto o error rate.

### Definition of Done (DoD) por entregable

- Logs JSON: 95%+ de requests con event, request_id, duration_ms, status_code, path, method.
- Workbook: 4-6 queries funcionando sin regex fragil (o con regex controlada) y filtros por tiempo/endpoint.
- Reporte diario: se genera automatico, se guarda y es legible; incluye Top 10 + /validate + evidencia request_id.
- Clasificacion: contadores diarios por clase (slow/error/dependency/pool).
- (Opcional) Alertas: 1 alerta dispara en test al forzar p95 alto o error rate.

---

## Implementacion paso a paso

### Paso 0 - Definir el alcance del MVP
- Ventana de analisis: ultimas 24h (y vista por hora).
- Umbral lento (slow): 5000 ms.
- Umbral muy lento: 15000 ms.
- Endpoint critico: /validate (o el endpoint mas caro).

No-goals (no incluye en Fase 1):
- OpenTelemetry / trazas distribuidas.
- Profiling.
- Deteccion de anomalias ML (solo reglas).
- Correlacion cross-service (solo request_id dentro del servicio).

### Paso 1 - Verificar ingesta en Log Analytics (sin codigo)
Checklist en Azure Portal:
- Container App -> Logs (Log Analytics).
- Confirmar tablas: ContainerAppConsoleLogs_CL y ContainerAppSystemLogs_CL.
- Si no existen, revisar: workspace correcto, permisos, localAuth, private link.
- Confirmar que el Workspace ID y el ContainerAppName_s correctos estan siendo usados en KQL.
- Confirmar que Log_s (o el campo de mensaje) trae JSON parseable.

### Paso 2 - Estandarizar log en la app (minimo viable)
Objetivo: un JSON consistente por request.

Nota clave: cada evento debe emitirse como una linea JSON completa (un objeto), sin prefijos ni sufijos.

Campos minimos por evento request.end / request.slow:
- event
- schema_version (ej. "1.0")
- timestamp
- request_id
- method, path
- route (template, p.ej. /api/codes/candidates/{id}/validate)
- status_code
- duration_ms
- org_id, project_id (si aplica)
- user_id_hash (sin PII)
- test_run_id
- build_version o git_sha
- sample_rate (si aplica; ej. 1.0 o 0.1)

Eventos adicionales (segmentos en endpoints caros):
- event=segment.db con duration_ms
- event=segment.neo4j con duration_ms
- event=segment.qdrant con duration_ms
- event=segment.llm con duration_ms (si aplica)

Nota: en produccion, desactivar colores ANSI para evitar ruido en parseo.
Nota: usar TimeGenerated como timestamp principal y timestamp interno como secundario (drift).
Nota: build_version sale de env BUILD_VERSION (inyectada por pipeline) con fallback a git_sha.

### Paso 3 - Clasificacion por reglas (MVP)
Reglas base:
- slow_request: duration_ms > 5000
- very_slow_request: duration_ms > 15000
- error_request: status_code >= 500
- pool_pressure: mensaje "pool exhausted" o metrica pool_used/pool_available
- decision: evento event="db.pool" con pool_used, pool_available, pool_max (cada N requests o cuando supere umbral)
- umbral: pool_used/pool_max > 0.8 durante 5 min -> Sev2
- dependency_slow: algun segment.* supera umbral (p.ej. db > 1000 ms)

Modelo minimo de severidad (para reporte diario):
- Sev1: error 5xx sostenido o p95 > 15000 ms en endpoint critico.
- Sev2: p95 > 5000 ms sostenido o spikes de 5xx.
- Sev3: outliers aislados.

Recomendacion practica: implementar estas reglas primero en KQL, no en codigo.

Regla operativa de sampling:
- request.end puede muestrearse en endpoints no criticos.
- request.slow, error_request y /validate no se muestrean nunca.
- cuando hay muestreo, incluir sample_rate para corregir metricas.

### Paso 4 - Consultas KQL core (listas para Workbook)

4.1 Top endpoints por p95/p99 y slow rate
- Agrupar por method, path.
- Calcular p95, p99, slow_over_5s, errors.

Riesgo de cardinalidad: si path incluye IDs, usar route o normalizar path en KQL (regex que reemplace numeros por {id}).

4.2 Drill-down por endpoint /validate
- Serie por hora con p95 y max.
- Contador de errores.
- Top request_id mas lentos.

4.3 Clasificacion por segmentos (si hay segment.*)
- Sumar segmentos por request_id.
- Detectar segmento dominante (db/neo4j/qdrant/llm).

4.4 Regresion post-deploy
- Agrupar por build_version.
- Comparar p95 y error rate antes/despues.

4.5 Schema Health (DoD 95%)
- Query KQL que calcule % de JSON parseable y % con campos requeridos.
- Si <95% -> bloqueo de release o alerta al equipo.

### Paso 5 - Workbook (dashboard MVP)
Estructura recomendada:
- Resumen 24h: total req, error rate, p95 global, top 10 endpoints lentos.
- Validacion: panel especifico /validate.
- Dependencias: db/neo4j/qdrant por segmento.
- Deploy compare: build_version vs p95/error.
- Explorar request_id: tabla filtrable.

Filtros requeridos:
- TimeRange
- build_version
- test_run_id
- route/path

### Paso 6 - Reporte diario automatico (MVP reporter)
Objetivo: un script que consulta KQL y genera Markdown.

Stack recomendado:
- Python + azure-monitor-query (LogsQueryClient).

Formato minimo:
- Periodo (UTC/local).
- p95 global + error rate global.
- Top 10 endpoints (p95 + slow rate).
- Seccion /validate.
- Sospechas automaticas (db domina, pool pressure).
- Acciones recomendadas (2-5 bullets).
- Evidencia: 3-5 request_id representativos.
- build_version actual (ultimo deployment).

Programacion sugerida:
- GitHub Actions (cron) si existe CI/CD.
- Azure Function si se requiere serverless.
- Job si ya se usa ACA Jobs.

Destino estandar sugerido:
- Ruta: reports/daily/YYYY-MM-DD.md
- Retencion: 30 dias (o 90 si estan ajustando performance)
- Consumo: link publicado en Teams/Slack si aplica

Ejecucion local (PowerShell):
- scripts/run_daily_logs_reporter.ps1 -WorkspaceId <GUID>

### Paso 7 - Alertas minimas (opcional)
- Alerta p95 > 5000 ms por 10-15 min.
- Alerta error_rate (5xx) > X%.

Recomendacion adicional: alertar por slow_rate (% de requests > 5000 ms) en vez de solo p95.

KQL base sugerido:
- queries/07_alert_slow_rate.kql
- queries/08_alert_error_rate.kql

Nota (alertas MVP): estas queries devuelven filas solo cuando se supera el umbral
y proyectan _ResourceId para split por recurso. Incluyen un minimo de req para
evitar falsos positivos en bajo volumen.

Configuracion rapida (Portal):
- Scope: Log Analytics Workspace
- Condition: Custom log search
- Query: 07/08 (segun alerta)
- Condition: Number of results > 0
- Evaluation frequency: 5m
- Window size: 10-15m
- Action Group: seleccionar existente o crear

Configuracion rapida (CLI):
- Usar az monitor scheduled-query create con --condition "count 'Q1' > 0 resource id _ResourceId"
- Q1 = contenido de la query (07 o 08)

### Paso 8 - Integracion con pruebas manuales
- Definir test_run_id antes de probar.
- Enviar test_run_id como header en todas las llamadas (X-Test-Run-Id).
- Reporte diario incluye seccion "Resultados por test_run_id".

Escenario canonico de prueba manual (5-8 pasos):
- login -> abrir proyecto -> ingestar -> candidatos -> validar -> sync grafo -> revisar reporte

---

## Avances (implementacion)

- [x] 2026-02-03: Middleware de logs en API con schema_version, request_id, test_run_id, route, build_version, sample_rate.
- [x] 2026-02-03: Logs de consola configurables a JSON via LOG_CONSOLE_JSON para prod.
- [x] 2026-02-03: KQL base + Schema Health (queries/).
- [x] 2026-02-03: Workbook MVP (import JSON).
- [x] 2026-02-03: Reporter diario (esqueleto) con LogsQueryClient.
- [x] 2026-02-03: Alertas minimas (KQL base para slow_rate/error_rate).
- [x] 2026-02-03: Reporter ejecutado (reports/daily/2026-02-03.md).
- [x] 2026-02-03: Alertas creadas en Azure (alert-slow-rate-validate, alert-error-rate-validate).

Recursos creados (Azure Monitor):
- Workspace: axial-law (RG: newsites)
- Action Group: ag-axial-warn
- Alert rules: alert-slow-rate-validate, alert-error-rate-validate

## Plan de trabajo (4-5 dias)

Dia 1 - Observabilidad base
- Confirmar tablas en Log Analytics.
- Logs JSON sin ANSI.
- Middleware con request_id y request.end con duration_ms.

Dia 2 - Clasificacion y dashboard
- KQL core (top endpoints + /validate).
- Workbook con 3 paginas (Resumen /validate / Exploracion).

Dia 3 - Reporte automatico
- Script Python con LogsQueryClient.
- Cron diario (Actions/Function/Job).
- Guardar reportes (Blob o repo ops-reports).

Dia 4-5 - Refinamiento
- Segmentos en /validate (db/neo4j/qdrant).
- Alerta simple (p95 o error rate).

---

## Riesgos y mitigaciones

- Logs no estructurados: el analisis KQL pierde precision.
  Mitigacion: forzar JSON y validar esquema con tests.

- Demasiado ruido: reportes poco accionables.
  Mitigacion: top 10 endpoints + umbrales claros.

- Falta de request_id: imposible auditar.
  Mitigacion: generar request_id en middleware si no existe.

- PII en logs.
  Mitigacion: no loguear texto de entrevistas/fragmentos; hash de user_id; redaccion de payloads.

- Costos/volumen.
  Mitigacion: sampling de request.end en endpoints no criticos (p.ej. 10%) y 100% para request.slow, error_request y /validate.

- Schema drift.
  Mitigacion: schema_version + validacion diaria + compatibilidad 1 version (minimo 1 semana).

---

## Resultado esperado

Un ciclo diario confiable y repetible:
- Detectar degradaciones y errores con evidencia.
- Explicar donde esta la lentitud (segmentos).
- Vincular cambios a build_version.
- Tomar decisiones con datos en 10-15 minutos.
