# Ficha metodológica: `POST /api/coding/suggestions` (Sugerencias por fragmento)

> **Fecha**: 2026-01-20
>
> **Código fuente**: `backend/app.py`

## 1) Resumen

`/api/coding/suggestions` genera sugerencias de códigos a partir del texto de un fragmento, usando:

- Embeddings (Azure OpenAI)
- Búsqueda vectorial (Qdrant)
- Agregación de códigos ancla (`codigos_ancla`) en el payload de Qdrant

Devuelve las “top suggestions” con una confianza simple.

## 2) Fundamento metodológico

Es un asistente de codificación: no asigna automáticamente, solo sugiere. La validación humana mantiene el control interpretativo.

## 3) Entrada (payload)

`CodeSuggestionRequest` incluye típicamente:

- `fragment_text`
- `limit`

## 4) Salida

`{"suggestions": [...]}` con elementos:

- `code`
- `confidence` (heurística: frecuencia / total de puntos)
- `example` (fragmento evidencia)

## 5) Flujo

1. Embed del texto del fragmento.
2. `search_similar()` en Qdrant (pide `limit * 2` para agregar mejor).
3. Itera puntos:
   - Extrae `codigos_ancla` (lista o string legacy).
   - Suma frecuencias por código.
   - Guarda un ejemplo de evidencia.
4. Devuelve top 5 sugerencias con confianza “naive”.

## 6) Persistencia

- No escribe; lectura Azure/Qdrant.

## 7) Riesgos y limitaciones

- Depende de que los puntos en Qdrant tengan `codigos_ancla` en payload.
- La confianza es simplificada; no es una probabilidad calibrada.

## 8) Recomendaciones de mejora

- Calibrar confianza con score real de similitud.
- Filtrar por proyecto/colección y metadatos.
- Incluir diversidad (evitar top por repetición de una misma fuente).

## 9) Referencias internas

- `backend/app.py` (`api_coding_suggestions`)
- `app/qdrant_block.py` (`search_similar`)
- `app/embeddings.py` (`embed_batch`)
