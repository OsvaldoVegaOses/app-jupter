# Backlog técnico — E3 Discovery-first (issues mapeados a endpoints y componentes)

> **Propósito**: traducir los 8 criterios de aceptación UX de E3 (Discovery-first) en **issues/tareas técnicas** implementables, con mapeo explícito a:
> - Endpoints FastAPI
> - Componentes Frontend
> - Tablas/funciones Postgres
> - Reportes en `reports/{project}/`
>
Referencias:
- Criterios UX: `criterios_aceptacion_ux_e3_discovery_first.md`
- Marco: `contrato_epistemico_y_ux.md` (sección “Discovery como modelo de referencia”)

---

## Epic 1 — E3 como navegación analítica (scope + logging)

### Issue 1.1 — Scope default “Modo Caso” visible y persistente
**Objetivo**: que E3 trabaje por defecto en entrevista activa (project+archivo) y el usuario vea/controle el alcance.

**Frontend**
- Componente: `frontend/src/components/CodingPanel.tsx`
  - Reusar/estandarizar el filtro existente: `activeInterviewFilter` y `suggestInterviewFilter`.
  - Mostrar el scope de forma textual (ej. “Entrevista actual” / “Todo el proyecto”).

**Backend**
- Endpoint(s) involucrados (ya existen):
  - `GET /api/interviews`
  - `GET /api/coding/fragments`
  - `POST /api/coding/suggest` (o el endpoint equivalente existente)
- Requisito: las consultas a Qdrant deben recibir filtros consistentes con scope (mínimo `project_id`, y por defecto `archivo`).

**Datos**
- Qdrant payload debe contener `project_id` y `archivo` (ya usado en filtros de borrado y diagnósticos).

**Criterio UX cubierto**: A.1

---

### Issue 1.2 — Log de navegación E3: “incidente → comparables”
**Objetivo**: cada acción de E3 deje rastro (no solo estado UI), siguiendo el patrón `discovery_navigation_log`.

**Diseño recomendado (mínimo viable)**
- Reutilizar el endpoint existente de logging Discovery:
  - `POST /api/discovery/log-navigation`
  - `GET /api/discovery/navigation-history`
- Extender el payload para E3 (sin romper compatibilidad):
  - `seed_fragmento_id` (opcional)
  - `scope_archivo` (opcional)
  - `top_k` / `include_coded` (opcionales)
  - `action_taken`: agregar valores tipo `e3_suggest`, `e3_send_candidates`

**Frontend**
- Servicio ya existe: `logDiscoveryNavigation()` en `frontend/src/services/api.ts`.
- Integración: llamar a `logDiscoveryNavigation()` desde `CodingPanel.tsx` al ejecutar sugerencias o envío a bandeja.

**Backend**
- Tabla actual: `discovery_navigation_log` (ya incluye `action_taken`, `refinamientos_aplicados`, `ai_synthesis`).
- Cambios: permitir `action_taken` más amplio y persistir los nuevos campos opcionales (si se agregan columnas).

**Criterio UX cubierto**: A.2

---

## Epic 2 — Evidencia obligatoria (1–3) antes de bandeja

### Issue 2.1 — Evidencia visible en E3 (pre-submit)
**Objetivo**: antes de enviar un código a bandeja, el usuario ve 1–3 evidencias asociadas.

**Frontend**
- `CodingPanel.tsx` (tab “Sugerencias semánticas”):
  - Para cada código propuesto (IA o manual), mostrar lista de `fragmento_id` evidenciales.
  - Bloquear envío si no hay evidencia (o marcar “sin evidencia” y no permitir promoción).

**Backend**
- Reusar lógica ya implementada en Runner para enlace código→fragmentos:
  - Función en `backend/routers/agent.py`: `_link_codes_to_fragments()`
- Exponer un endpoint reutilizable para E3, por ejemplo:
  - `POST /api/coding/evidence-link` (propuesto)
  - Input: `codes[]`, `fragments[]` (o `seed_fragmento_id` + resultados Qdrant)
  - Output: `codes_with_fragments[]`

**Criterio UX cubierto**: A.3

---

## Epic 3 — Persistencia unificada: E3 escribe candidatos (gate explícito)

### Issue 3.1 — E3 “Enviar a bandeja” usa `codigos_candidatos`
**Objetivo**: E3 no debe crear “definitivos” sin gate; debe insertar en `codigos_candidatos` con evidencia.

**Frontend**
- Usar `submitCandidate()` (ya importado en `CodingPanel.tsx`) o el batch endpoint.
- Para batch desde E3:
  - Preferir `POST /api/codes/candidates/batch` (ya existe en backend).

**Backend**
- Endpoints existentes:
  - `POST /api/codes/candidates`
  - `POST /api/codes/candidates/batch`
- Función de persistencia: `insert_candidate_codes()` en `app/postgres_block.py`

**Dato mínimo requerido por fila**
- `project_id`, `codigo`, `fragmento_id`, `archivo`, `fuente_origen`, `memo`, `estado='pendiente'`.

**Criterio UX cubierto**: A.4

---

## Epic 4 — Bandeja: batch ops + promoción a definitivos (acto separado)

### Issue 4.1 — Batch validate/reject/merge consistente + confirmación mínima
**Objetivo**: operaciones batch confiables y trazables.

**Frontend**
- `frontend/src/components/CodeValidationPanel.tsx`
  - Ya implementa batch validate/reject/merge/promote; agregar confirmación mínima donde falte.
  - Asegurar que evidencias (IDs) estén visibles en la fila (si solo está en memo, elevar a campo visible).

**Backend**
- Endpoints existentes:
  - `PUT /api/codes/candidates/{id}/validate`
  - `PUT /api/codes/candidates/{id}/reject`
  - `POST /api/codes/candidates/merge`

**Criterio UX cubierto**: B.5

---

### Issue 4.2 — Promoción a definitivo con feedback (promovidos vs omitidos)
**Objetivo**: promoción separada, con reporte claro de resultados.

**Backend**
- Endpoint existente:
  - `POST /api/codes/candidates/promote`
- Función existente:
  - `promote_to_definitive()` en `app/postgres_block.py`
- Mejora propuesta:
  - Retornar estructura con `promoted_count`, `skipped_count` y razones (ej. `missing_fragmento_id`).

**Frontend**
- `CodeValidationPanel.tsx`: mostrar `promoted_count` y `skipped_count`.

**Criterio UX cubierto**: B.6

---

## Epic 5 — Reportes: auditable por diseño + anti-colapso

### Issue 5.1 — Reporte E3 auditable (código → evidencia → decisión)
**Objetivo**: generar/mostrar un reporte E3 que incluya fuentes, estados y evidencias por código.

**Backend (dos caminos, elegir uno)**
1) **Persistido como archivo** (rápido): escribir Markdown en `reports/{project}/e3/`.
2) **Persistido en DB** (robusto): nueva tabla o reutilizar `analysis_reports`/`doctoral_reports`.

**Inputs mínimos**
- Conteos de candidatos por estado (`codigos_candidatos`)
- Muestras de evidencias por código (1–3 fragmentos)
- Acciones registradas (ver Issue 1.2)

**Criterio UX cubierto**: C.7

---

### Issue 5.2 — Métricas anti-colapso en E3 y Runner (diversidad/overlap)
**Objetivo**: exponer métricas de diversidad en JSON + Markdown.

**Estado actual**
- Runner ya calcula métricas en `backend/routers/agent.py` (`_compute_evidence_diversity_metrics`).

**Tareas**
- Reusar cálculo para E3 (cuando se proponen códigos desde sugerencias semánticas).
- Mostrar interpretación breve en reporte.

**Criterio UX cubierto**: C.8

---

## Epic 6 — Memos analíticos + reportes en informes de avance y final (IMPORTANTE)

### Issue 6.1 — Informes doctorales (avance) incorporan memos + reportes recientes
**Objetivo**: que `stage3` y `stage4` consideren explícitamente:
- memos analíticos (Discovery, candidatos, notes)
- reportes generados (Runner, GraphRAG, reportes por entrevista)

**Backend**
- Archivo: `app/doctoral_reports.py`
- Estado actual: `_get_memos()` ya consume:
  - `discovery_navigation_log.ai_synthesis`
  - `codigos_candidatos.memo`
  - `notes/{project}/*.md`

**Falta (a implementar)**
- Agregar `_get_recent_report_artifacts(project)` que lea snippets/índices de:
  - `reports/{project}/` (incluye `doctoral/`, GraphRAG, runner, etc.)
  - y/o desde DB si existen tablas de reportes (ej. `interview_reports`, `doctoral_reports`).
- Inyectar “Artefactos recientes” al prompt STAGE3/4 para que el LLM los use como evidencia de avance.

**Endpoints**
- `POST /api/reports/generate-doctoral` (ya existe)

---

### Issue 6.2 — Informe final (Etapa 4 final) incorpora memos + artefactos
**Objetivo**: que el informe final no sea solo métricas+estructura, sino que incluya y cite:
- memos analíticos relevantes
- reportes previos (runner / graphrag / entrevistas)

**Backend**
- Archivo: `app/reports.py`
  - Función: `generate_stage4_final_report()`
- Tarea: añadir sección “Memos y artefactos” alimentada por Postgres + filesystem `reports/{project}/`.

**Endpoints**
- `POST /api/reports/stage4-final` (ya existe en backend)

---

## Notas de implementación (orden sugerido)
1) Issue 3.1 (E3 → candidatos) + Issue 1.1 (scope) para asegurar el “gate”.
2) Issue 2.1 (evidencia obligatoria) para auditabilidad.
3) Issue 1.2 (logging) para trazabilidad.
4) Issue 6.1/6.2 para que los informes (avance/final) usen memos+artefactos como evidencia.
5) Issue 5.1/5.2 para estandarizar reportes y calidad anti-colapso.
