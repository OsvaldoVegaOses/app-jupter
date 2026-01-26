# Ficha metodológica: `GET /api/coding/gate` (Gate operativo antes de análisis)

> **Fecha**: 2026-01-20
>
> **Código fuente**: `backend/app.py`
>
> **Dependencias**: `get_backlog_health()` (PostgreSQL)

## 1) Resumen

El endpoint `/api/coding/gate` decide si es recomendable ejecutar un nuevo análisis LLM, basándose en la salud del backlog de candidatos pendientes.

## 2) Justificación metodológica/operativa

En flujos iterativos (ingesta → sugerencias → validación), generar más candidatos sin validar aumenta ruido y reduce control de calidad. Este “gate” fuerza disciplina: primero validar, luego generar.

## 3) Parámetros

- `project` (requerido)
- `threshold_count` (default 50)
- `threshold_days` (default 3)

## 4) Respuesta

`Dict[str, Any]` con:

- `can_proceed`: boolean
- `reason`: string o `null`
- `health`: métricas completas (ver `get_backlog_health`)
- `recommendation`: texto sugerido cuando bloquea

## 5) Flujo

1. Resuelve `project_id`.
2. Calcula `health = get_backlog_health(...)`.
3. `can_proceed = health['is_healthy']`.
4. Si bloquea, construye `reason` priorizando:
   - backlog saturado por conteo
   - backlog saturado por antigüedad

## 6) Seguridad

- Requiere auth (`require_auth`).
- Respeta multi‑tenant por org (según configuración global del backend).

## 7) Operación

- Ideal para que el Frontend muestre “Debe validar antes de analizar”.
- Ajustar umbrales por proyecto (o exponer presets por organización).

## 8) Referencias internas

- `backend/app.py` (`api_coding_gate`)
- `app/postgres_block.py` (`get_backlog_health`)
