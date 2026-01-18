# Implementation Plan: Migración a Routers (FastAPI)

**Última actualización:** 2026-01-13

Este plan describe la migración gradual desde el monolito `backend/app.py` hacia routers dedicados bajo `backend/routers/`, manteniendo estabilidad y compatibilidad con el Frontend.

> Estado actual: la base ya está activa para el flujo de Coding (ver `backend/routers/coding.py`). La migración restante debe ser incremental y guiada por valor/risgo.

---

## Objetivos

- Reducir el tamaño/complexidad de `backend/app.py` sin romper el contrato de API.
- Aislar dependencias y errores por dominio (projects, ingest, coding, reports, etc.).
- Mejorar mantenibilidad, observabilidad y testabilidad.

## Principios

- Migrar por **vertical slices** (endpoint + lógica + validación) evitando grandes refactors.
- Mantener rutas existentes (`/api/*`) y auth (`X-API-Key`) sin cambios de contrato.
- Cada migración debe incluir:
  - logs estructurados
  - manejo de errores consistente (`api_error`/códigos)
  - timeouts razonables para Postgres

---

## Fase 1 (alta prioridad): Projects + Overview + Ingest

- Projects CRUD y estado del proyecto.
- `GET /api/research/overview` (Panorama/NBA) como punto estable del Home.
- `POST /api/ingest` y endpoints relacionados.

Criterio de salida:
- Home carga KPIs y NBA desde router.
- Ingest funciona end-to-end con logs y errores consistentes.

## Fase 2 (alta prioridad): Coding + Candidates

- Consolidar todo lo relativo a coding en routers:
  - `GET/POST /api/coding/*`
  - `GET/POST /api/codes/candidates/*`

Notas:
- El runner semántico ya expone status/result/memos en `backend/routers/coding.py`.
- Mantener contrato único de métricas: ver `docs/05-calidad/contrato_metricas_candidatos_runner.md`.

Criterio de salida:
- Bandeja de candidatos 100% servida por router.
- Métricas coherentes entre runner-status y bandeja.

## Fase 3 (media prioridad): Transcription + Interviews

- Transcripción y endpoints de entrevistas (listado, detalles, etc.).
- Asegurar reintentos/backoff y trazabilidad por request_id.

## Fase 4 (media/baja): Reports + Insights + Limpieza

- Reports, exportaciones y endpoints de insights.
- Depurar rutas legacy del monolito y eliminar duplicados.

---

## Checklist por endpoint migrado

- [ ] Router agrega `tags` y `prefix` adecuados.
- [ ] Validación Pydantic request/response.
- [ ] Manejo de errores consistente.
- [ ] No introducir nuevas dependencias pesadas.
- [ ] Logs con `task_id` o `request_id`.
- [ ] Prueba manual mínima desde Frontend + script (si existe).

