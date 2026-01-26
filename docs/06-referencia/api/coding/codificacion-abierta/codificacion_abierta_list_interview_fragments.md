# Ficha metodológica: `list_interview_fragments()` (Fragmentos por entrevista)

> **Fecha**: 2026-01-20
>
> **Código fuente**: `app/coding.py`
>
> **Endpoint relacionado**: `GET /api/coding/fragments`

## 1) Resumen

`list_interview_fragments()` obtiene fragmentos de una entrevista/archivo para que el analista los codifique o explore.

## 2) Propósito y contexto

Este listado alimenta el flujo de codificación abierta:

- Seleccionar fragmentos pendientes.
- Navegar por entrevista.
- Visualizar contexto.

## 3) Firma e inputs

- `archivo`: identificador del archivo/entrevista.
- `limit`: máximo de fragmentos a retornar.

## 4) Salida

Lista de fragmentos (dicts) con texto y metadatos mínimos (según `list_fragments_for_file`).

## 5) Flujo interno

Wrapper a `list_fragments_for_file(pg, project_id, archivo, limit)`.

## 6) Persistencia

- Solo lectura PG.

## 7) Errores

- `archivo` inválido o permisos/DB se reflejan en el endpoint.

## 8) Operación

- En UI: paginar o aumentar `limit` según performance y tamaño de entrevistas.

## 9) Referencias internas

- `app/coding.py` (`list_interview_fragments`)
- `app/postgres_block.py` (`list_fragments_for_file`)
- `backend/app.py` (`GET /api/coding/fragments`)
