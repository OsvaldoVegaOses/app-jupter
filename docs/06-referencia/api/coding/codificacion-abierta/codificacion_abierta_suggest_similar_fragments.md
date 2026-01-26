# Ficha metodológica: `suggest_similar_fragments()` (Comparación constante)

> **Fecha**: 2026-01-20
>
> **Código fuente**: `app/coding.py`
>
> **Endpoint relacionado**: `POST /api/coding/suggest`

## 1) Resumen

`suggest_similar_fragments()` implementa la **comparación constante**: dado un fragmento “semilla”, recupera fragmentos semánticamente similares (embeddings + Qdrant). Opcionalmente genera un memo LLM y/o persiste la comparación para auditoría.

## 2) Fundamento teórico (Teoría Fundamentada)

La comparación constante busca contrastar incidentes (fragmentos) para:

- Refinar propiedades del código.
- Detectar variación y límites de una categoría.
- Evaluar densidad y saturación.

Operacionalmente, el sistema usa **similitud semántica** (embeddings) como heurística para encontrar incidentes comparables.

## 3) Firma e inputs

- `fragment_id`: fragmento semilla.
- `top_k`: número de sugerencias.
- `filters`: filtros por metadatos (archivo, área temática, actor principal, etc.).
- `exclude_coded`: si `True`, excluye fragmentos ya codificados.
- `persist`: si `True`, guarda la corrida de comparación.
- `llm_model`: si se provee, intenta memo LLM.

Precondiciones:

- El fragmento debe existir.
- Debe tener `embedding` almacenado.

## 4) Salida

`dict` con:

- `suggestions`: lista de fragmentos sugeridos con `score` y payload.
- `comparison_id`: id de auditoría (si se persiste).
- `llm_summary`, `llm_model`: memo opcional.

## 5) Flujo interno (alto nivel)

1. Carga fragmento semilla desde PostgreSQL.
2. Toma el vector embedding.
3. Construye filtro Qdrant (`_build_qdrant_filter`).
4. Calcula exclusiones:
   - `list_coded_fragment_ids` (si `exclude_coded`).
   - el propio `fragment_id`.
5. Consulta Qdrant (`query_points`) y arma la lista `suggestions`.
6. Si se solicita, genera memo LLM (`_generate_comparison_memo`).
7. Si `persist` o hay memo, persiste auditoría (`log_constant_comparison`).

## 6) Persistencia y side-effects

- Qdrant: lectura (consulta vectorial).
- PostgreSQL: lectura de fragmentos y, opcionalmente, escritura de auditoría.
- LLM: llamada opcional a Azure OpenAI.

## 7) Errores y validaciones

- `CodingError` si:
  - no existe el fragmento,
  - no hay embedding,
  - Qdrant falla o requiere índices para filtros.

La función tiene comportamiento defensivo: memo LLM es best‑effort (si falla, no rompe sugerencias).

## 8) Parámetros operativos / calibración

- `top_k`: 5–10 para UX; 20+ para exploración.
- `exclude_coded=True` por defecto evita sesgos y repetición.
- Filtros Qdrant requieren índices; ejecutar `scripts/healthcheck.py` si aparece error “Index required”.

## 9) Referencias internas

- `app/coding.py` (`suggest_similar_fragments`, `_build_qdrant_filter`, `_generate_comparison_memo`)
- `app/postgres_block.py` (`fetch_fragment_by_id`, `list_coded_fragment_ids`, `log_constant_comparison`)
- `backend/app.py` (`POST /api/coding/suggest`)
