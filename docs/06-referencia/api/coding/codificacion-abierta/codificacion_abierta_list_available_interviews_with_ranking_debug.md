# Ficha metodológica: `list_available_interviews_with_ranking_debug()`

> **Fecha**: 2026-01-20
>
> **Código fuente**: `app/coding.py`
>
> **Endpoint relacionado**: `GET /api/interviews` (usa ordenamientos; `theoretical-sampling` expone debug en algunos flujos)

## 1) Resumen

`list_available_interviews_with_ranking_debug()` lista entrevistas disponibles y, cuando se usa el orden `theoretical-sampling`, retorna además una estructura `ranking_debug` explicando por qué cada entrevista fue priorizada.

## 2) Propósito y contexto

En codificación abierta, la selección de “qué codificar después” no es trivial. Este componente implementa dos filosofías:

- Orden operacional (por fecha/alfabético/cantidad de fragmentos).
- **Muestreo teórico** (prioriza gaps + riqueza + recencia), alineado a GT sistemática.

El `ranking_debug` es clave para **transparencia metodológica**: evita “caja negra” y habilita auditoría.

## 3) Firma e inputs

- `limit`: máximo de entrevistas.
- `order`: `ingest-desc|ingest-asc|alpha|fragments-desc|fragments-asc|max-variation|theoretical-sampling`.
- `include_analyzed`: si incluye entrevistas ya analizadas (para theoretical-sampling).
- `focus_codes`: CSV de códigos foco.
- `recent_window`, `saturation_new_codes_threshold`: parámetros para saturación.

## 4) Salida

Tupla `(interviews, ranking_debug)`:

- `interviews`: lista ordenada.
- `ranking_debug`: lista de dicts con score y factores (cuando aplica).

## 5) Flujo interno

1. Obtiene entrevistas base desde PG: `list_interviews_summary`.
2. Si `order == theoretical-sampling`:
   - Usa `_order_interviews_theoretical_sampling_with_debug`, que consulta `interview_reports` si existe.
   - Calcula: `gap_norm`, `richness_norm`, `recency_norm`, `score` y flags.
3. Caso contrario:
   - Ordena con `_order_interviews_summary` y retorna `ranking_debug=[]`.

## 6) Persistencia y side-effects

- Solo lectura PG.
- Degrada a orden ingest-desc si `interview_reports` no está disponible.

## 7) Errores y validaciones

- Diseño defensivo: si falta tabla o hay errores, entrega orden degradado con `ranking_debug` explicando la degradación.

## 8) Operación y calibración

- `theoretical-sampling` es sensible a la calidad de metadatos (área temática/actor principal) y a la existencia de reportes.
- Ajustar pesos/ventana solo cuando el equipo observe sesgos (ej.: prioriza demasiado recencia).

## 9) Referencias internas

- `app/coding.py` (`list_available_interviews_with_ranking_debug`, `_order_interviews_summary`, `_order_interviews_theoretical_sampling_with_debug`)
- `app/postgres_block.py` (`list_interviews_summary`, tablas `interview_reports`, `analisis_codigos_abiertos`)
