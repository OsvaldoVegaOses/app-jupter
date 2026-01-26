# Ficha metodológica: `get_saturation_data()` (Saturación teórica)

> **Fecha**: 2026-01-20
>
> **Código fuente**: `app/coding.py`
>
> **Endpoint relacionado**: `GET /api/coding/saturation`

## 1) Resumen

`get_saturation_data()` calcula una curva acumulada de códigos (por entrevista) y evalúa si el proyecto está entrando en **saturación teórica** (plateau de códigos nuevos).

## 2) Fundamento teórico

En Teoría Fundamentada, la saturación se aproxima cuando:

- Nuevos incidentes no producen propiedades/códigos nuevos relevantes.

Este sistema usa una operacionalización simple:

- En una ventana de las últimas $N$ entrevistas, si el número de códigos nuevos es ≤ `threshold`, se sugiere plateau.

## 3) Firma e inputs

- `window`: tamaño de ventana (default 3).
- `threshold`: máximo de códigos nuevos para considerar plateau (default 2).

## 4) Salida

`dict` con:

- `curve`: lista ordenada de entrevistas con `codigos_nuevos` y `codigos_acumulados`.
- `plateau`: detalle de evaluación.
- `summary`: resumen (totales y últimos nuevos).

## 5) Flujo interno

1. Asegura tabla open coding.
2. Calcula curva acumulada: `cumulative_code_curve(pg, project)`.
3. Evalúa plateau: `evaluate_curve_plateau(curve, window, threshold)`.
4. Arma `summary` para UX.

## 6) Persistencia

- Lectura PG.

## 7) Riesgos y limitaciones

- Es una heurística: plateau cuantitativo no garantiza saturación conceptual.
- Depende de calidad de codificación (si hay duplicados nominales, falsea “novedad”).

## 8) Operación y calibración

- `window=3` es un compromiso para UX.
- En proyectos grandes, considerar `window=5`.
- Si el equipo codifica muy granular, subir `threshold`.

## 9) Referencias internas

- `app/coding.py` (`get_saturation_data`)
- `app/postgres_block.py` (`cumulative_code_curve`, `evaluate_curve_plateau`, `ensure_open_coding_table`)
- `backend/app.py` (`GET /api/coding/saturation`)
