# Ficha metodológica: `fetch_code_history()` (Historial de versiones)

> **Fecha**: 2026-01-20
>
> **Código fuente**: `app/coding.py`
>
> **Endpoint relacionado**: `GET /api/coding/codes/{codigo}/history`

## 1) Resumen

`fetch_code_history()` obtiene el historial de cambios de un código desde `codigo_versiones`. Provee trazabilidad (memos, acciones, timestamps) para auditoría metodológica.

## 2) Propósito y contexto

En investigación cualitativa, la trazabilidad de decisiones (memos, redefiniciones, fusiones) es un componente de rigor.

## 3) Firma e inputs

- `codigo`: nombre del código.
- `limit`: máximo de entradas.

## 4) Salida

Lista de dicts con:

- `version`, `accion`, `memo_anterior`, `memo_nuevo`, `changed_by`, `created_at`, etc.

## 5) Flujo interno

Wrapper a `get_code_history(pg, project, codigo, limit)`.

## 6) Persistencia

- Lectura PG.

## 7) Riesgos

- Si no se registran eventos (best‑effort), el historial puede ser incompleto.

## 8) Operación

- Útil para panel de historia y auditorías post‑hoc.

## 9) Referencias internas

- `app/coding.py` (`fetch_code_history`)
- `app/postgres_block.py` (`get_code_history`, `codigo_versiones`)
- `backend/app.py` (`GET /api/coding/codes/{codigo}/history`)
