# Panel de transición a `code_id` (Fase 1.5) — Operación y metodología

> **Última actualización:** 2026-01-22
>
> **Objetivo:** ejecutar y auditar la transición desde “canon por texto” hacia “identidad por ID” (`code_id`, `canonical_code_id`) con controles operativos (dry-run, confirmación explícita, locks y trazabilidad por sesión).

## 1) Resumen

Este panel soporta dos necesidades simultáneas:

1) **Migración segura** (Fase 1.5): ejecutar operaciones admin para completar/repair la transición a `code_id` sin introducir mutaciones accidentales.
2) **Incidentes / operación**: durante incident response, reducir ruido de `GET` repetitivos y localizar rápidamente **qué intentó cambiar algo y cuándo** (filtros + columna HTTP + Resultado técnico).

El panel **no analiza** ni infiere “importancia/impacto”: solo muestra **historial** derivado de logs estructurados.

## 2) Problema real que resuelve

Durante un incidente, el ruido típico es:

- llamadas `GET` de diagnóstico/status que no mutan,
- repetidas muchas veces,
- que esconden el evento relevante (el intento de cambio).

Este panel introduce un flujo operativo minimalista:

- filtrar por **intento de mutación (POST)**,
- ver **Resultado técnico** sin abrir logs,
- abrir detalle solo cuando hace falta,
- re-ejecutar bajo un **contrato “no mágico”**: payload visible + confirmación dura + nueva sesión.

## 3) Fuente de verdad y arquitectura (por qué esto es “seguro”)

- **PostgreSQL** es el *ledger/source of truth*.
- **Neo4j** es una proyección analítica (se alimenta desde el ledger).
- La transición a `code_id` evita depender de “texto canónico” como identidad.

El panel trabaja con:

- **Back-end (FastAPI)**: endpoints admin (mutantes) y endpoints ops (solo lectura).
- **Front-end (React/Vite)**: UI para operación con guardrails.
- **Logging**: JSONL estructurado por `project` + `session` para auditoría post-ejecución.

## 4) Componentes y archivos relevantes

Backend

- `backend/routers/admin.py`
  - Operaciones `code-id`: status, inconsistencias, backfill, repair.
  - Ops (solo lectura): `GET /api/admin/ops/recent`, `GET /api/admin/ops/log`.
  - Locks de concurrencia (Postgres advisory locks) para operaciones mutantes.

Frontend

- `frontend/src/components/AdminPanel.tsx`: integra el panel.
- `frontend/src/components/AdminOpsPanel.tsx`: UI de operación (filtros + tabla + modal log + re-ejecución).
- `frontend/src/services/api.ts`: cliente HTTP + enums de filtros + helpers para POST admin con sesión nueva.

## 5) Endpoints (contrato y responsabilidad)

### 5.1 Endpoints de transición `code_id` (mutantes, admin-only)

- `GET /api/admin/code-id/status?project=...`
- `GET /api/admin/code-id/inconsistencies?project=...&limit=...`
- `POST /api/admin/code-id/backfill?project=...`
- `POST /api/admin/code-id/repair?project=...`

Semántica clave de `axial_ready` (contrato normativo):

- `axial_ready` valida **consistencia estructural** para iniciar codificación axial.
- No depende de `ontology_freeze` (freeze bloquea mutaciones; no define readiness).
- `self-canonical` (`canonical_code_id = code_id`) es estado esperado y no bloquea.
- Solo bloquea por: identidad incompleta, canonicidad incompleta, divergencias texto↔ID, ciclos **no triviales**.

Propiedades clave:

- **admin-only** (guardia de roles).
- **dry-run por defecto** (el operador debe elegir mutar conscientemente).
- **confirmación explícita** (`confirm=true`) cuando corresponde.
- **locks** para evitar ejecuciones concurrentes del mismo tipo.

### 5.2 Endpoints de freeze ontológico (bloqueo operacional)

- `GET /api/admin/ontology/freeze?project=...`
- `POST /api/admin/ontology/freeze/freeze?project=...`
- `POST /api/admin/ontology/freeze/break?project=...`

Regla operativa:

- si el freeze está activo, el sistema debe bloquear mutaciones (`dry_run=false`).

### 5.3 Endpoints Ops (solo lectura sobre logs)

- `GET /api/admin/ops/recent?project=...&limit=...&kind=...&op=...&intent=...&since=...&until=...`
- `GET /api/admin/ops/log?project=...&session=...&request_id=...&tail=...`

Estos endpoints:

- **no leen DB** como “estado vivo”; leen **historial** desde `logs/<project>/<session>/app.jsonl`.
- aplican filtros seguros (sin heurísticas de “importancia”).

## 6) Filtros (enums cerrados: no crecen sin control)

Backend (`backend/routers/admin.py`) y Frontend (`frontend/src/services/api.ts`) usan sets cerrados.

### 6.1 `kind`

- `all`
- `errors` (solo runs con error)
- `mutations` (solo runs con `updated > 0` según log)

### 6.2 `op`

- `all`
- `backfill`
- `repair`
- `sync`
- `maintenance`
- `ontology`

### 6.3 `intent`

- `all`
- `write_intent_post`

Copy recomendado (y aplicado):

- “**Solo operaciones con intento de mutación (POST)**”
- “Filtra eventos que intentaron ejecutar cambios (incluye dry-run)”

> Nota: **POST ≠ mutó datos**. Es “intento de mutación” en términos operativos.

## 7) Columnas de tabla (minimalistas y literales)

Tabla diseñada para ser “aburrida” (técnica, no interpretativa).

- **Fecha**: timestamp del run.
- **Operación**: ruta/evento asociado.
- **HTTP**: `GET`/`POST` (derivado del log `request.start/end`).
- **Resultado**: outcome técnico (ver 7.1).
- **Parámetros**: `dry_run`, `confirm`, `batch_size`, etc.
- **Rows**: conteo derivado de `updated` si existe.
- **Duración**: `duration_ms`.
- **Sesión / Req**: IDs para auditoría.

### 7.1 Enum de “Resultado” (outcome técnico)

Definido en el cliente como:

- `OK`
- `NOOP`
- `ERROR`
- `UNKNOWN`

Reglas (derivadas solo de logs):

- `ERROR`: `is_error=true` o `status_code >= 400`.
- `OK`: `200 <= status_code < 300` y no aplica NOOP.
- `NOOP`: `200 <= status_code < 300` y `HTTP=POST` y `rows=0`.
- `UNKNOWN`: sin `status_code` o no clasificable.

**No** implica “impacto”, “criticidad” ni “riesgo”.

## 8) Re-ejecutar (contrato “no mágico”)

La re-ejecución existe para cerrar el ciclo operativo:

- filtrar `POST`,
- ver el intento fallido,
- entrar al detalle,
- re-ejecutar con confirmación.

Restricciones duras:

- no hay retry silencioso,
- no hay inferencias,
- **payload visible (read-only)**,
- confirmación dura (checkbox + escribir `EJECUTAR` cuando `dry_run=false`),
- **nueva sesión por ejecución** (`X-Session-ID` nuevo) para auditabilidad,
- si freeze está activo, se bloquea `dry_run=false` (además el backend lo rechaza).

## 9) Operación práctica

### 9.1 Checklist rápido (incidente)

1) Activar filtro “Solo operaciones con intento de mutación (POST)”.
2) Si hay ruido, sumar `kind=errors`.
3) Mirar “Resultado” (OK/NOOP/ERROR) + `status_code`.
4) Abrir log solo si el error requiere contexto.
5) Re-ejecutar solo con payload visible y confirmación.

### 9.2 Ejemplo (PowerShell)

```powershell
$headers = @{ 'X-API-Key'='dev-key'; 'X-Session-ID'=('ops-' + (Get-Random)) }
$since = (Get-Date).AddDays(-7).ToString('o')
$uri = 'http://localhost:8000/api/admin/ops/recent?project=jd-007&limit=20&intent=write_intent_post&since=' + [uri]::EscapeDataString($since)
Invoke-RestMethod -Method Get -Uri $uri -Headers $headers
```

## 10) Limitaciones y notas

- Este panel depende de que `request.start/end` registren `method` y `status_code`.
- “Rows” solo aparece si la operación loguea `updated` (no fuerza DB reads).
- Los logs son historia: no sustituyen métricas vivas ni diagnósticos de DB.

## 11) Troubleshooting mínimo

- No aparecen runs:
  - confirmar `project` correcto,
  - verificar que existan carpetas `logs/<project>/<session>/app.jsonl`.
- HTTP muestra `—`:
  - el run puede venir de logs antiguos (antes de loguear `method`).
- `NOOP` inesperado:
  - significa `POST` + `status 2xx` + `rows=0` reportado; no implica error.

## 12) Referencias internas

- Backend: `backend/routers/admin.py`
- Frontend: `frontend/src/components/AdminOpsPanel.tsx`, `frontend/src/services/api.ts`
- Logging: `app/logging_config.py` (handler contextual por `project/session`)
