# Ficha metodológica: `assign_open_code()` (Codificación Abierta)

> **Fecha**: 2026-01-20
>
> **Código fuente**: `app/coding.py`
>
> **Endpoint relacionado**: `POST /api/coding/assign`

## 1) Resumen

`assign_open_code()` registra una **asignación manual** como **código candidato** (estado `pendiente`) vinculado a un fragmento. Es un diseño híbrido: la acción del usuario no “crea” un código definitivo inmediatamente, sino que **envía evidencia a la bandeja de validación**.

## 2) Propósito y contexto

En Teoría Fundamentada (codificación abierta), el analista propone códigos emergentes. En un sistema multi‑fuente (manual/LLM/Discovery), se necesita gobernanza: evitar que el catálogo crezca sin control y mantener trazabilidad.

Esta función operacionaliza:

- **Propuesta** de código (manual)
- **Trazabilidad** mediante cita y fragmento
- **Gate** de gobernanza: pasa por `codigos_candidatos`

## 3) Firma e inputs

Parámetros relevantes:

- `fragment_id`: identificador del fragmento en PostgreSQL.
- `codigo`: nombre del código propuesto.
- `cita`: evidencia textual asociada.
- `fuente`/`memo`: metadatos opcionales.
- `project`: proyecto (por defecto `default`).

Precondiciones:

- El fragmento debe existir (se valida con `fetch_fragment_by_id`).

## 4) Salida

Retorna un `dict` con:

- `fragmento_id`, `archivo`, `codigo`, `cita`, `fuente`, `memo`
- `estado`: `pendiente` (porque entra a la bandeja)

## 5) Flujo interno (alto nivel)

1. Resuelve `project_id`.
2. Verifica que el fragmento exista en PostgreSQL.
3. Inserta un registro en `codigos_candidatos` con:
   - `fuente_origen='manual'`
   - `score_confianza=1.0`
   - `fragmento_id`, `archivo` y evidencia.
4. Registra log estructurado: `coding.assign.candidate`.

## 6) Persistencia y side-effects

- PostgreSQL: inserción en tabla `codigos_candidatos`.
- No crea relación en Neo4j ni inserta directo en `analisis_codigos_abiertos`.

## 7) Errores y validaciones

- Lanza `CodingError` si el fragmento no existe.
- Errores de base de datos se propagan como fallos del endpoint.

## 8) Operación y calibración

- Este flujo es conservador: prioriza gobernanza (validación) sobre velocidad.
- Recomendación: si el usuario necesita “inmediatez” en UI, usar el flujo de promoción/validación posterior.

## 9) Referencias internas

- `app/coding.py` (`assign_open_code`)
- `app/postgres_block.py` (`insert_candidate_codes`, `ensure_candidate_codes_table`, `fetch_fragment_by_id`)
- `backend/app.py` (`POST /api/coding/assign`)
