# Ficha metodológica: `list_open_codes()` (Catálogo de códigos)

> **Fecha**: 2026-01-20
>
> **Código fuente**: `app/coding.py`
>
> **Endpoint relacionado**: `GET /api/coding/codes`

## 1) Resumen

`list_open_codes()` lista códigos abiertos (y sus frecuencias de citas/fragmentos) para inspección, búsqueda y selección desde UI.

## 2) Propósito y contexto

En codificación abierta, el catálogo se usa para:

- Reutilizar códigos existentes.
- Revisar densidad y distribución.
- Preparar fusiones o pasar a axial.

## 3) Firma e inputs

- `limit`: cantidad máxima (default 50).
- `search`: filtro por nombre.
- `archivo`: filtra por entrevista.

## 4) Salida

Lista de dicts (por código), típicamente:

- `codigo`, `citas`, `fragmentos`, `primera_cita`, `ultima_cita`.

## 5) Flujo interno

1. Asegura tabla open coding (`ensure_open_coding_table`).
2. Consulta resumen (`list_codes_summary`).

## 6) Persistencia

- Lectura PG. Puede crear tabla si faltara (idempotente).

## 7) Errores

- SQL/PG se propaga.

## 8) Operación y calibración

- Para UX: combinar `search` + `limit` bajo (50–200).
- Para export: usar endpoints de exportación.

## 9) Referencias internas

- `app/coding.py` (`list_open_codes`)
- `app/postgres_block.py` (`list_codes_summary`, `ensure_open_coding_table`)
- `backend/app.py` (`GET /api/coding/codes`)
