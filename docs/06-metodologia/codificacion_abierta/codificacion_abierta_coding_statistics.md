# Ficha metodológica: `coding_statistics()` (Cobertura y avance)

> **Fecha**: 2026-01-20
>
> **Código fuente**: `app/coding.py`
>
> **Endpoint relacionado**: `GET /api/coding/stats`

## 1) Resumen

`coding_statistics()` calcula métricas de progreso del proyecto en codificación abierta: cobertura, total de códigos, fragmentos codificados, etc.

## 2) Propósito y contexto

La codificación abierta requiere monitoreo continuo:

- Cobertura (% fragmentos con al menos un código).
- Distribución de citas por código (densidad).
- Ritmo de producción de códigos (posible saturación o explosión de duplicados).

## 3) Firma e inputs

- `project`: proyecto.

Precondición:

- Asegura que existan tablas de codificación abierta y axial.

## 4) Salida

`dict` con indicadores (estructura provista por `coding_stats`), típicamente:

- `total_codes`, `total_fragments`, `coded_fragments`, `coverage_percent`, etc.

## 5) Flujo interno

1. `ensure_open_coding_table(pg)`
2. `ensure_axial_table(pg)`
3. `coding_stats(pg, project_id)`

## 6) Persistencia y side-effects

- Solo lectura, pero puede crear tablas si faltan (idempotente).

## 7) Errores

- Si hay bloqueos/latencias PG, el endpoint puede activar timeout (en `backend/app.py` hay wrapper con timeout duro).

## 8) Operación y calibración

- Usar en UI como “salud de progreso”.
- Objetivos operativos típicos: cobertura > 70% para pasar a axial.

## 9) Referencias internas

- `app/coding.py` (`coding_statistics`)
- `app/postgres_block.py` (`coding_stats`, `ensure_open_coding_table`, `ensure_axial_table`)
- `backend/app.py` (`GET /api/coding/stats`)
