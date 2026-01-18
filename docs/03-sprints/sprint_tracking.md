# Seguimiento de Sprints – Desarrollo APP_Jupter

> **Actualizado:** Enero 2026 - Estado verificado contra código y documentación

Este documento centraliza la planificación y el seguimiento de todos los sprints del proyecto.

---

## Resumen Ejecutivo

| Sprint | Objetivo | Estado |
|--------|----------|--------|
| Sprint 0 | CLI Neo4j Query | ✅ Completado |
| Sprint 1 | Backend HTTP + Frontend Explorer | ✅ Completado |
| Sprint 2 | CI/CD y Autenticación | ✅ Completado |
| Sprint 3 | Exportes y Observabilidad | ✅ Completado |
| Sprint 4 | Carga y Monitoreo | ✅ Completado |
| Sprint 5 | GDS Analytics (Grafo Vivo) | ✅ Completado |
| Sprint 6 | Descubrimiento Semántico | ⚠️ 80% |
| Sprint 7 | Documentación Completa | ✅ Completado |
| Sprint 8–29 | Ver `docs/03-sprints/sprint*.md` | ✅/⚠️ |
| Sprint 30 | Etapa 0 + Usabilidad del Output | ✅ Completado |

> Para el detalle de Sprint 30, ver: `docs/03-sprints/sprint30_etapa0_usabilidad_output_auditoria_2026-01.md`.

---

## Sprint 0 – CLI Neo4j Query ✅

- [x] Helper `run_cypher` con vistas `raw/table/graph`
- [x] Subcomando `main.py neo4j query`
- [x] Documentación y pruebas

---

## Sprint 1 – Backend HTTP + Frontend Explorer ✅

- [x] Backend FastAPI (`/neo4j/query`)
- [x] Frontend `Neo4jExplorer` con tabs Raw/Table/Graph
- [x] Tests pytest + Vitest

---

## Sprint 2 – CI/CD y Autenticación ✅

- [x] Workflow CI/CD con pytest + vitest
- [x] API Key (header `X-API-Key`)
- [x] JWT Bearer + API Key fallback (`backend/auth.py`)

---

## Sprint 3 – Exportes y Observabilidad ✅

- [x] Endpoint `/neo4j/export` (CSV/JSON)
- [x] Botón de exporte en Neo4jExplorer
- [x] Métricas de latencia (`X-Query-Duration`)
- [x] Logging estructurado con structlog

---

## Sprint 4 – Carga y Monitoreo ✅

- [x] Script `scripts/load_test.py`
- [x] Métricas estructuradas
- [x] Guía de alertas en README

---

## Sprint 5 – GDS Analytics (Grafo Vivo) ✅ NUEVO

**Objetivo:** Que el grafo genere datos, no solo los guarde.

| Tarea | Estado | Evidencia |
|-------|--------|-----------|
| PageRank persistente | ✅ | `score_centralidad` en nodos |
| Louvain persistente | ✅ | `community_id` en nodos |
| Botones GDS en UI | ✅ | Neo4jExplorer.tsx |
| Visualización dinámica | ✅ | Tamaño y color por GDS |
| Fallback NetworkX | ✅ | Cuando GDS plugin no disponible |

**Entregables:**
- `run_gds_analysis()` en `app/axial.py`
- Botones "Detectar Comunidades" y "Calcular Importancia"
- Nodos dimensionados por centralidad, coloreados por comunidad

---

## Sprint 6 – Descubrimiento Semántico ⚠️ 80%

**Objetivo:** Exploración por conceptos abstractos.

| Tarea | Estado |
|-------|--------|
| Sugerencias semánticas | ✅ `/api/coding/suggest` |
| Índices Qdrant completos | ✅ 9 campos |
| Retry con backoff | ✅ Exponential, 3 intentos |
| Discovery API triplete | ⚠️ Preparado, falta implementar |
| Clustering automático | ❌ Pendiente |

---

## Sprint 7 – Documentación Completa ✅ NUEVO

**Objetivo:** Documentar todos los módulos para el equipo de desarrollo.

| Módulo | Archivos | README | Docstrings |
|--------|----------|--------|------------|
| `app/` | 22 | ✅ | ✅ Español |
| `backend/` | 4 | ✅ | ✅ Español |
| `frontend/` | 9+ | ✅ | ✅ JSDoc |
| `scripts/` | 34 | ✅ | ✅ Headers |
| **Total** | **69+** | **4** | **100%** |

**Documentos actualizados:**
- [x] `docs/valor_negocio.md`
- [x] `docs/ajustes_nucleo.md`
- [x] `docs/brechas_tecnicas_avanzadas.md`
- [x] `docs/etapa0_reflexividad.md`
- [x] `docs/etapas1-4_informe.md`
- [x] `docs/etapas1-4_informe_critico.md`
- [x] `docs/fix_axial_neo4j.md`
- [x] `docs/informe_consolidado_alineacion.md`
- [x] `docs/plan_iteracion_cognitiva.md`

---

## Backlog Futuro

| Tarea | Prioridad | Sprint |
|-------|-----------|--------|
| GraphRAG completo | Alta | 8 |
| Discovery API triplete | Media | 8 |
| Link Prediction | Baja | 9 |
| Exportación REFI-QDA | Baja | 9 |
| SSO/OAuth | Media | 10 |

---

## Métricas de Testing

| Suite | Comando | Resultado |
|-------|---------|-----------|
| Backend | `pytest -q` | 11+ passed |
| Frontend | `npm run test` | 7+ passed |
| TypeScript | `npx tsc --noEmit` | Exit 0 |
| E2E | `run_e2e.ps1` | ✅ Disponible |

---

## Notas de Seguimiento

- **Dic 2024:** Sprints 5-7 completados con GDS y documentación
- **Vinculación LLM:** ~70% códigos con fragmento real (mejorado desde ~50%)
- **GDS:** Operativo sin plugin Neo4j (fallback NetworkX)

---

*Última verificación: 13 Diciembre 2024*
