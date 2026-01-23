# Resumen ejecutivo operativo (Dev) — APP_Jupter

> **Fecha:** 2026-01-23
> 
> **Objetivo:** poner al día al equipo de desarrollo para trabajar **de inmediato**. Este documento cierra decisiones ya tomadas y traduce el estado actual a acciones.

---

## 1) Qué es el sistema (1 frase)
Plataforma de investigación cualitativa con **PostgreSQL como ledger/source of truth**, **Neo4j como proyección** (grafo para visualización/GDS), y **Qdrant** como memoria semántica; el frontend (React/Vite) consume un backend (FastAPI) con guardrails operativos y logs estructurados.

---

## 2) Decisiones cerradas (no debatir en implementación)

### 2.1 PostgreSQL manda (ledger)
- **PostgreSQL es la fuente de verdad** (identidad de códigos, estado de proyectos, asignaciones, axial, etc.).
- **Neo4j es una proyección**: se sincroniza desde Postgres; no se “deciden verdades” en Neo4j.

### 2.2 Fase 1.5 (transición a `code_id` / `canonical_code_id`)
- Se migra desde “canon por texto” (`canonical_codigo`) hacia identidad estable por ID.
- Esta fase es **infraestructural** (operación), no metodológica/analítica.
- Guardrails obligatorios:
  - **dry-run por defecto**
  - **confirmación explícita** para mutaciones
  - **locks** (Postgres advisory locks) para evitar concurrencia
  - **logging estructurado** por `project` + `session`

### 2.3 Contrato normativo de `axial_ready` (sin ambigüedades)
`axial_ready` indica únicamente si la infraestructura ontológica está consistente para iniciar axialidad.

**Bloquea SOLO si:**
- `missing_code_id > 0`
- `missing_canonical_code_id > 0` (no canónicos sin puntero final)
- `divergences_text_vs_id > 0` (drift texto↔ID)
- `cycles_non_trivial_nodes > 0` (ciclos de longitud > 1)

**NO bloquea:**
- `self-canonical` (`canonical_code_id = code_id`) → estado esperado
- `ontology_freeze` → control operativo de mutación, no readiness

### 2.4 Freeze ontológico
- Freeze es un **bloqueo operacional**: si está activo, **bloquea mutaciones** (backfill/repair cuando `dry_run=false`).
- Freeze **no define** `axial_ready`.

---

## 3) Qué se implementó / estado actual (alto valor)

### 3.1 Observabilidad y operación (logs + panel Ops)
- Logging estructurado **JSONL** por sesión/proyecto: `logs/<project>/<session>/app.jsonl`.
- Panel **🧭 Operaciones (Post‑ejecución)**:
  - Lee historial desde logs (no “estado vivo”).
  - Filtros cerrados y literales (incluye filtro **intento de mutación (POST)**).
  - Columna HTTP + outcome técnico (`OK|NOOP|ERROR|UNKNOWN`).
  - Re-ejecutar con contrato seguro: payload visible + confirmación dura + nueva sesión.

### 3.2 Panel admin Fase 1.5 (transición a `code_id`)
- Panel infra para status/inconsistencias/backfill/repair/freeze.
- La UI incluye copy explícito para evitar lectura analítica.
- `self-canonical` se muestra como estado normal; `cycles` se interpreta como **ciclos no triviales**.

### 3.3 Hardening backend
- Endpoints admin-only con guardas de rol.
- Locks de concurrencia vía advisory locks.
- Correcciones previas de 500s: firma de advisory locks y SQL de repair.

---

## 4) Cómo arrancar a desarrollar (pasos mínimos)

### 4.1 Backend (FastAPI)
- Entorno Python: usar `.venv`.
- Ejecutar (ejemplo):
  - `python -m uvicorn --app-dir . backend.app:app --host 127.0.0.1 --port 8000 --reload`

### 4.2 Frontend (Vite)
- Instalar deps: `npm --prefix frontend install`
- Dev server: `npm --prefix frontend run dev`
- Build: `npm --prefix frontend run build`

### 4.3 Variables / configuración
- Revisar `env.example`.
- Puntos críticos: credenciales Postgres/Neo4j/Qdrant/Azure OpenAI, y `X-API-Key` para backend.
- Documentación base:
  - `docs/01-configuracion/run_local.md`
  - `docs/01-configuracion/configuracion_infraestructura.md`

---

## 5) Rutas y módulos clave (para orientarse rápido)

### Backend
- `backend/app.py`: FastAPI app y montaje de routers.
- `backend/routers/admin.py`: 
  - Fase 1.5: `/api/admin/code-id/*`
  - Freeze: `/api/admin/ontology/freeze/*`
  - Ops logs: `/api/admin/ops/*`
- `app/postgres_block.py`: ledger (tablas, upserts, queries).
- `app/neo4j_block.py` + `app/neo4j_sync.py`: proyección/graph.
- `app/axial.py`: lógica axial + GDS.

### Frontend
- `frontend/src/services/api.ts`: cliente HTTP (headers, retries, eventos globales de error).
- `frontend/src/components/AdminOpsPanel.tsx`: panel Ops.
- `frontend/src/components/CodeIdTransitionSection.tsx`: panel Fase 1.5.
- `frontend/src/components/Neo4jExplorer.tsx`: visualización + controles GDS.

---

## 6) Contratos operativos (reglas de contribución)

### 6.1 En endpoints mutantes admin
- `dry_run=true` por defecto.
- `dry_run=false` requiere `confirm=true`.
- Si `ontology_freeze` activo: bloquear mutaciones con `423`.
- Siempre loguear: `project_id`, `session_id`, `action/mode`, `dry_run`, `confirm`, `batch_size`, `updated.rows`.

### 6.2 En UI
- No mostrar métricas “interpretables” sin copy duro.
- La UI de operación debe ser literal:
  - no ranking
  - no “impacto”
  - no heurísticas

---

## 7) Qué queda como “trabajo inmediato” típico
- Verificar `axial_ready` real por proyecto antes de habilitar flujos axiales.
- Mantener alineados:
  - backend contrato de `axial_ready`/`blocking_reasons`
  - copy/UI (para evitar malentendidos epistemológicos)
  - docs de operación

---

## 8) Enlaces internos recomendados (lectura corta)
- `agents.md` (mapa de módulos/agentes)
- `docs/06-metodologia/codificacion_abierta/panel de transición a code_id/README.md`
- `docs/06-metodologia/codificacion_abierta/Transición_A_Cod_Axial/codificacion_abierta_paso_a_paso_codificacion_axial.md`
- `docs/05-troubleshooting/connection_pool_issues.md`
