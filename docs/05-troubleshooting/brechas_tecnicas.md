# Análisis de Brechas Técnicas para Evolución de Negocio

> **Última actualización:** 2026-01-23

## 1. Brechas Críticas (Must-Have)

### Backend (API)
*   ~~**Regression en `api_analyze`**~~: ✅ **RESUELTO** - El endpoint `/api/analyze` ya usa la estrategia Pre-Hoc con `[IDX: n]` para indexar fragmentos.

### Seguridad
*   ~~**Autenticación Débil**~~: ✅ **RESUELTO** - Implementado JWT + API Key con soporte multi-tenant (`organization_id`).
*   ~~**Autorización Nula**~~: ✅ **RESUELTO** - RBAC implementado con `require_role()` y roles: `admin`, `analyst`, `codificador`, `viewer`, `superadmin`.

### Identidad de Códigos
*   ~~**Propagación `code_id` end-to-end**~~: ✅ **RESUELTO** (Migración 018) - Columna `code_id` añadida a `analisis_codigos_abiertos` y `codigos_candidatos`. Propagación implementada en `upsert_open_codes()`, `insert_candidate_codes()`, y `promote_to_definitive()`.

### Modo Epistémico
*   ~~**Prompts hardcoded en `coding.py`**~~: ✅ **RESUELTO** - `suggest_code_from_fragments()` ahora usa `get_system_prompt()` del loader con modo epistémico diferenciado.

## 2. Brechas de Producto (Should-Have)

### Frontend (UX)
*   **Visualización de Grafos limitada**: ✅ **RESUELTO** - Neo4jExplorer implementado con react-force-graph y controles GDS.
*   **Editor de Codificación**: ✅ **RESUELTO** - CodingPanel y CodeValidationPanel implementados para Human-in-the-loop.

### Infraestructura
*   **Colas de Trabajo (Async)**: ✅ **RESUELTO** - Celery worker implementado en `backend/celery_worker.py` con Redis.

## 3. Estado Actual

Todas las brechas críticas y de producto han sido resueltas. El sistema está operativo con:
- Autenticación JWT + API Key
- RBAC con roles granulares
- Propagación de `code_id` end-to-end
- Modo epistémico diferenciado
- Celery para tareas async
- Neo4jExplorer con GDS
