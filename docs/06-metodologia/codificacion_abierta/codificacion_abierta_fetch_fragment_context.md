# Ficha metodológica: `fetch_fragment_context()` (Contexto del fragmento)

> **Fecha**: 2026-01-20
>
> **Código fuente**: `app/coding.py`
>
> **Endpoint relacionado**: `GET /api/coding/fragment-context`

## 1) Resumen

`fetch_fragment_context()` arma el contexto ampliado de un fragmento (texto, metadatos, códigos asignados y fragmentos adyacentes). Se usa para modales o inspección contextual.

## 2) Propósito y contexto

En análisis cualitativo, el significado de un extracto depende del contexto conversacional. Esta función habilita:

- Ver continuidad antes/después.
- Inspeccionar asignaciones ya aplicadas.
- Reducir errores de codificación por “cita aislada”.

## 3) Firma e inputs

- `fragment_id`: fragmento.
- `project`: proyecto.

## 4) Salida

`dict` (o `None` si no existe) con:

- `fragment`
- `codes`, `codes_count`
- `adjacent_fragments`

## 5) Flujo interno

Wrapper a `get_fragment_context(pg, fragment_id, project_id)`.

## 6) Persistencia

- Lectura PG.

## 7) Errores

- En el endpoint: si `None`, responde 404.

## 8) Operación

- Para UX: usar cuando el analista abre detalle, no en listados masivos.

## 9) Referencias internas

- `app/coding.py` (`fetch_fragment_context`)
- `app/postgres_block.py` (`get_fragment_context`)
- `backend/app.py` (`GET /api/coding/fragment-context`)
