# Ficha metodológica: `list_available_interviews()`

> **Fecha**: 2026-01-20
>
> **Código fuente**: `app/coding.py`
>
> **Endpoint relacionado**: `GET /api/interviews`

## 1) Resumen

`list_available_interviews()` retorna entrevistas ordenadas para el flujo de codificación abierta. Es un wrapper de conveniencia que llama a `list_available_interviews_with_ranking_debug()` y descarta el debug.

## 2) Propósito y contexto

Permite abastecer UI/CLI con un listado de entrevistas priorizadas según estrategia de muestreo/orden.

## 3) Firma e inputs

Mismos parámetros que `list_available_interviews_with_ranking_debug()`.

## 4) Salida

Lista de entrevistas (dicts) ordenadas.

## 5) Flujo interno

1. Llama a `list_available_interviews_with_ranking_debug(...)`.
2. Retorna solo `ordered`.

## 6) Persistencia

- Solo lectura PG (delegada).

## 7) Errores

- Hereda comportamiento defensivo del método con debug.

## 8) Operación

- Recomendación: si el equipo necesita trazabilidad, usar el método con debug en auditoría.

## 9) Referencias internas

- `app/coding.py` (`list_available_interviews`)
