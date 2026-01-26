# Ficha metodológica: `unassign_open_code()` (Codificación Abierta)

> **Fecha**: 2026-01-20
>
> **Código fuente**: `app/coding.py`
>
> **Endpoint relacionado**: `DELETE /api/coding/unassign`

## 1) Resumen

`unassign_open_code()` deshace una asignación: elimina la vinculación **código ↔ fragmento** en PostgreSQL y Neo4j. Está diseñada como una operación correctiva sin pérdida del fragmento ni del catálogo.

## 2) Propósito y contexto

La codificación abierta es iterativa. Un analista puede reasignar criterios, corregir errores o refinar el sistema de códigos. Esta función soporta **reversibilidad** (método cualitativo reflexivo) y mantiene trazabilidad.

## 3) Firma e inputs

- `fragment_id`: fragmento afectado.
- `codigo`: código a desvincular.
- `project`: proyecto (por defecto `default`).
- `changed_by`: usuario (para auditoría best‑effort).

## 4) Salida

Retorna un `dict` con:

- `fragmento_id`, `codigo`, `project_id`
- `postgres_deleted`: conteo de filas afectadas.
- `neo4j_deleted`: conteo de borrado/relación afectada.

## 5) Flujo interno (alto nivel)

1. Elimina en PostgreSQL el registro de `analisis_codigos_abiertos` (vía `delete_open_code`).
2. Elimina en Neo4j la relación `TIENE_CODIGO` (vía `delete_fragment_code`).
3. Si no hubo cambios en ninguna capa, lanza `CodingError`.
4. Best‑effort: registra un evento en historial (`codigo_versiones`) para trazabilidad.
5. Log estructurado: `coding.unassign`.

## 6) Persistencia y side-effects

- PostgreSQL: delete en tabla de asignaciones abiertas.
- Neo4j: delete de relación fragmento‑código.
- Auditoría: `log_code_version` (best‑effort, no bloquea).

## 7) Errores y validaciones

- `CodingError` si no existe la asignación.
- Fallos Neo4j o PG pueden producir “borrado parcial” (dependiendo de en qué paso falla). Esto es aceptable si los procesos posteriores vuelven a sincronizar.

## 8) Operación y calibración

- Usar para corrección fina; para fusiones masivas usar flujos de gobernanza.
- Recomendación operativa: exponer en UI como acción confirmada (evitar misclick).

## 9) Referencias internas

- `app/coding.py` (`unassign_open_code`)
- `app/postgres_block.py` (`delete_open_code`, `get_code_history`, `log_code_version`)
- `app/neo4j_block.py` (`delete_fragment_code`)
- `backend/app.py` (`DELETE /api/coding/unassign`)
