# ✅ Auditoría E2E de Flujo y Registro de Logs

**Fecha:** 2026-01-18  
**Objetivo:** Ejecutar una auditoría end‑to‑end para identificar desviaciones en el flujo definido y detectar fallos por ausencia de registro de logs.  
**Alcance:** Frontend (React), Backend (FastAPI), PostgreSQL, Neo4j, Qdrant, Azure OpenAI, Celery/Redis.

---

## 1) Flujo definido (baseline)

1. **Frontend** emite llamadas a `/api/*` con `X-API-Key` y `X-Session-ID`.
2. **Backend** registra `request.start` y `request.end` en logs.
3. **Backend** ejecuta lógica de negocio (proyectos, ingestión, análisis, GDS).
4. **Persistencia** en PostgreSQL / Neo4j / Qdrant.
5. **Respuesta** al frontend, y registro de evento de negocio (p. ej. `project.created`, `project.deleted`).

---

## 2) Auditoría E2E paso a paso (procedimiento)

### Paso A — Validar sesión y routing de logs
- **Entrada:** Abrir UI y verificar creación de `X-Session-ID`.
- **Evidencia esperada:**
  - Logs en `logs/default/<session_id>/app.jsonl`.
  - Si hay `project_id`, logs en `logs/<project_id>/<session_id>/app.jsonl`.
- **Desviación típica:** logs solo en `logs/app.jsonl` → indica que faltó el binding de sesión/proyecto.

### Paso B — Listado de proyectos (GET /api/projects)
- **Acción:** Refrescar listado de proyectos.
- **Logs esperados:**
  - `request.start` + `request.end` con `status_code: 200`.
  - (Opcional) métricas de pool (`pool.getconn.*`).
- **Desviación:** existe `request.start` pero no `request.end` → posible fallo sin cierre de request o crash.

### Paso C — Crear proyecto (POST /api/projects)
- **Acción:** Crear proyecto con nuevo identificador.
- **Logs esperados:**
  - `request.start` y `request.end`.
  - Evento `project.created`.
- **Desviación:**
  - `status_code: 400` con mensaje “Ya existe…” → flujo correcto (validación) pero **no** es fallo de logs.
  - Falta `project.created` en 201 → falla de registro de evento de negocio.

### Paso D — Actualizar proyecto (PATCH /api/projects/{id})
- **Acción:** Cambiar nombre/descripcion.
- **Logs esperados:**
  - `project.updated` con lista de `updates`.
- **Desviación:** `request.end` 200 sin `project.updated` → falta de evento de negocio.

### Paso E — Exportar proyecto (GET /api/projects/{id}/export)
- **Acción:** Exportar configuración.
- **Logs esperados:**
  - `project.exported`.
- **Desviación:** respuesta 200 sin `project.exported` → inconsistencia de auditoría.

### Paso F — Eliminar proyecto (DELETE /api/projects/{id})
- **Acción:** Eliminar proyecto.
- **Logs esperados:**
  - `project.deleted` con `deleted.pg_proyectos: 1`.
  - `request.end` con `status_code: 200`.
- **Desviación:**
  - `request.end` 200 sin `project.deleted` → falta de evento.
  - `project.deleted` sin `pg_proyectos` → posible fallo de limpieza.

### Paso G — Ingesta (POST /api/ingest)
- **Acción:** Cargar archivos DOCX.
- **Logs esperados:**
  - `ingestion.start`, `ingestion.batch`, `ingestion.end` (según implementación).
- **Desviación:** falta `ingestion.end` → ingestion incompleta o crash.

### Paso H — Análisis (POST /api/analyze)
- **Acción:** Ejecutar análisis LLM (Celery).
- **Logs esperados:**
  - `analysis.start` (API) y `analysis.completed` (worker).
- **Desviación:** request 202 sin `analysis.completed` → revisar worker o cola.

### Paso I — GDS / Graph (POST /neo4j/*)
- **Acción:** Ejecutar GDS en Neo4j.
- **Logs esperados:**
  - Evento de cálculo en backend (`gds.run` o equivalente).
- **Desviación:** request ok sin evento → falta de registro.

---

## 3) Matriz de control de logs críticos

| Fase | Log mínimo esperado | Ubicación |
|------|----------------------|-----------|
| Request | `request.start`, `request.end` | logs/<project_id>/<session_id>/app.jsonl o logs/default/... |
| Proyectos | `project.created|updated|deleted|exported` | mismo archivo de sesión |
| Ingesta | `ingestion.*` | mismo archivo de sesión |
| Análisis | `analysis.*` (API/worker) | logs/app.jsonl + logs/<project_id>/... |
| Qdrant | `qdrant.*` | logs/app.jsonl |
| Neo4j | `neo4j.*` | logs/app.jsonl |

---

## 4) Señales de desviación de flujo

- `request.start` sin `request.end` → fallo de respuesta o excepción no controlada.
- `request.end` 200 sin evento de negocio (`project.*`) → evento omitido.
- Eventos con `project_id` incorrecto → binding de contexto fallido.
- Logs solo en `logs/app.jsonl` y no en carpeta de sesión → middleware no asignó `session_id`.

---

## 5) Evidencia mínima a conservar

- `logs/<project_id>/<session_id>/app.jsonl` (sesión objetivo).
- `logs/default/<session_id>/app.jsonl` (sesión general).
- `logs/app.jsonl` (agregado).

---

## 6) Resultado esperado

- Flujo consistente entre UI → API → Persistencia.
- Eventos de negocio presentes para cada acción clave.
- Sin gaps de logging para requests y eventos de negocio.

---

## 7) Observaciones sobre JD‑007 (referencia)

- En sesiones específicas de `jd-007` se observaron únicamente lecturas exitosas (`/api/status`, `/api/research/overview`).
- Los errores 400 de creación se registraron en sesión `default` (POST `/api/projects`).

---

**Estado:** Documento generado para auditoría operativa y detección de ausencia de logs críticos.