# Ficha metodológica: `citations_for_code()` (Citas por código)

> **Fecha**: 2026-01-20
>
> **Código fuente**: `app/coding.py`
>
> **Endpoint relacionado**: `GET /api/coding/citations`

## 1) Resumen

`citations_for_code()` recupera la evidencia (citas) asociada a un código, para inspección de densidad, consistencia y alcance del código.

## 2) Propósito y contexto

En codificación abierta, revisar citas permite:

- Validar coherencia del código.
- Detectar variación (casos límites).
- Preparar fusiones o jerarquías.

## 3) Firma e inputs

- `codigo`: nombre del código.
- `project`: proyecto.

## 4) Salida

Lista de `dict` (estructura definida por `get_citations_by_code`), típicamente:

- `fragmento_id`, `archivo`, `cita` y metadatos relevantes.

## 5) Flujo interno

Wrapper directo a `get_citations_by_code(pg, codigo, project)`.

## 6) Persistencia y side-effects

- Solo lectura PostgreSQL.

## 7) Errores

- Errores de conexión/SQL se propagan al endpoint.

## 8) Operación

- Útil para QA y para preparar codificación axial (densidad y propiedades).

## 9) Referencias internas

- `app/coding.py` (`citations_for_code`)
- `app/postgres_block.py` (`get_citations_by_code`)
- `backend/app.py` (`GET /api/coding/citations`)
