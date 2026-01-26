# Ficha metodológica: `find_similar_codes()` (Sugerencia de códigos similares)

> **Fecha**: 2026-01-20
>
> **Código fuente**: `app/coding.py`
>
> **Uso típico**: sugerir sinónimos/fusiones al validar códigos candidatos.

## 1) Resumen

`find_similar_codes()` busca códigos “cercanos” semánticamente a un código dado, usando embeddings de fragmentos asociados y recuperación vectorial en Qdrant. Produce una lista de códigos alternativos con score promedio.

## 2) Fundamento teórico

En codificación abierta, códigos redundantes (sinónimos) fragmentan el análisis. Detectar proximidad semántica ayuda a:

- Sugerir fusiones (gobernadas).
- Sugerir jerarquías (sub‑código vs macro‑código).

El método usa similitud de embeddings como heurística de cercanía conceptual.

## 3) Firma e inputs

- `codigo`: código fuente.
- `top_k`: máximo de sugerencias.
- `project`: proyecto.

## 4) Salida

Lista de dicts:

- `codigo`: nombre del código similar.
- `score`: promedio de scores de fragmentos.
- `occurrences`: cantidad de evidencias encontradas.

## 5) Flujo interno

1. Obtiene citas del código (`get_citations_by_code`).
2. Extrae fragmentos asociados y toma el primer fragmento como referencia.
3. Consulta Qdrant con ese embedding (limit 50).
4. Obtiene fragment_ids similares y consulta en PostgreSQL los códigos asignados a esos fragmentos (`analisis_codigos_abiertos`).
5. Agrega scores por código y calcula promedio.
6. Ordena y retorna top‑K.

## 6) Persistencia y side-effects

- Lectura Qdrant.
- Lectura PG.
- No persiste auditoría (actualmente).

## 7) Riesgos y limitaciones

- Usa solo el primer fragmento del código como “vector representante”: puede sesgar si el código es heterogéneo.
- Dependiente de calidad de embeddings y de que existan citas.

## 8) Operación y calibración

- Para códigos con muchas citas, se recomienda una versión futura que agregue múltiples embeddings (promedio o centroides).
- Si `top_k` es alto, aumentar limit de Qdrant o mejorar agrupación.

## 9) Referencias internas

- `app/coding.py` (`find_similar_codes`)
- `app/postgres_block.py` (`get_citations_by_code`, `fetch_fragment_by_id`)
- `backend/app.py` (endpoints que consumen sugerencias/validación)
