# Ficha metodológica: `get_backlog_health()` (Salud del backlog de candidatos)

> **Fecha**: 2026-01-20
>
> **Código fuente**: `app/postgres_block.py`
>
> **Consumido por**: `GET /api/coding/gate` (backend)

## 1) Resumen

`get_backlog_health()` calcula métricas de salud del backlog de `codigos_candidatos` en estado `pendiente` para un proyecto. Se usa como “termómetro operativo” para evitar que el sistema siga generando candidatos sin validar.

## 2) Propósito

- Prevenir saturación del backlog.
- Dar visibilidad a validación pendiente (conteo y antigüedad).
- Apoyar decisiones: “validar antes de ejecutar más análisis”.

## 3) Firma e inputs

- `project`: ID del proyecto.
- `threshold_days`: máximo de días del candidato pendiente más antiguo (default 3).
- `threshold_count`: máximo de pendientes permitidos (default 50).

## 4) Salida

`Dict[str, Any]` con:

- `is_healthy`
- `pending_count`
- `oldest_pending_days`
- `avg_pending_age_hours`
- `avg_resolution_hours` (últimos 30 días, para validados/rechazados)
- `alerts` (lista de strings)
- `thresholds`

## 5) Flujo interno

1. `ensure_candidate_codes_table(pg)`.
2. Query de pendientes (`COUNT`, `MIN(created_at)`, promedio de antigüedad).
3. Query de resolución para candidatos cerrados en últimos 30 días.
4. Calcula `oldest_pending_days` y regla `is_healthy`.
5. Genera `alerts` si se superan umbrales.

## 6) Persistencia

- Lectura PG únicamente.
- Aplica `SET LOCAL statement_timeout = 10000` (best‑effort para UX/health checks).

## 7) Riesgos y limitaciones

- La salud se basa en conteo y antigüedad; no mide “calidad” de candidatos.
- En proyectos muy activos, umbrales deben calibrarse por equipo.

## 8) Referencias internas

- `app/postgres_block.py` (`get_backlog_health`, `ensure_candidate_codes_table`)
- `backend/app.py` (`GET /api/coding/gate`)
