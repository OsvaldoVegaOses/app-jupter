# 🔍 Auditoría de Calidad: Discovery Runner & Post-Run

Implementación evaluada tras una ejecución del Runner Discovery para el proyecto `jd-009`.

Esta auditoría se enfoca en reducir alucinaciones (claims no sustentados) y en alinear la salida del Runner con el objetivo de negocio:

> Convertir entrevistas y documentos en **insights accionables y auditables**, con **trazabilidad** desde el hallazgo hasta los fragmentos de evidencia.

## 1) Hechos verificables (anclados a código)

### 1.1 Muestreo de evidencia para el post-run ✅
- El runner mantiene una muestra de fragmentos únicos “mejores por score” acumulados a través de iteraciones (no solo la última iteración).
- Evidencia: `best_fragments` y `sample_fragments` en `app/discovery_runner.py`.

### 1.2 Resiliencia mínima ante fallos de infraestructura ✅
- Embeddings: retry con backoff implementado localmente en el runner (no usa Tenacity aquí).
- Qdrant search: retry con backoff implementado en el runner.
- Evidencia: `_embed_query_with_retry()` y `_search_qdrant_with_retry()` en `app/discovery_runner.py`.

### 1.3 Post-run: síntesis + artefactos ✅
- El post-run genera un JSON estructurado con: memo, códigos sugeridos, decisiones y próximos pasos; luego escribe un reporte Markdown.
- Evidencia: `_analyze_fragments_with_llm()` y `_write_runner_report()` en `backend/routers/agent.py`.

## 2) Métrica “Landing rate”: definición operativa (anti‑alucinación)

**Definición real (actual):**
- El “landing rate” se calcula como la proporción de fragmentos recuperados por Discovery que ya aparecen codificados en `analisis_codigos_abiertos` para el proyecto.
- Nota: `analisis_codigos_abiertos` contiene codificación abierta ya persistida (no necesariamente “axial/definitiva”).

**Salida y diagnóstico:**
- `landing_rate` se entrega como porcentaje (0–100).
- `reason` puede ser:
	- `no_fragments`: no hubo fragmentos.
	- `no_definitive_codes`: el proyecto no tiene filas en `analisis_codigos_abiertos` (por tanto, el landing rate tiende a 0 aunque haya buenos hallazgos).
	- `no_overlap_with_definitive_codes`: hay codificación previa, pero no hubo overlap.
	- `ok`: hay overlap.

Evidencia: `calculate_landing_rate()` en `app/postgres_block.py`.

## 3) Controles anti‑alucinación (estado actual)

### 3.1 Controles ya presentes ✅
- El LLM está forzado a responder “solo JSON” (reduce texto libre y deriva de formato).
- El informe incluye `fragmento_id` y fragmentos textuales (permite verificación humana).

### 3.2 Brechas que aún permiten alucinaciones (y por qué importan)
- La síntesis/códigos no incluyen trazabilidad explícita “código → fragmentos que lo sustentan”.
- El post‑run usa una muestra (subset) de fragmentos (por diseño), por lo que afirmaciones del tipo “ausencia de X” pueden ser artefacto de muestreo.
- No hay score/umbral por código sugerido (todas las sugerencias se ven “planas”).

## 4) Conclusión (ajustada a evidencia)

- El Runner + post‑run está operativo y produce artefactos útiles para avanzar (reporte + sugerencias), con trazabilidad básica vía `fragmento_id`.
- No se debe presentar como “auditable/enterprise-ready” sin explicitar limitaciones y sin añadir trazabilidad código→evidencia y controles de calidad reproducibles.

## 5) Recomendaciones (para cumplir el objetivo 2025)

1) En los reportes: etiquetar explícitamente la síntesis como **hipótesis** basada en una muestra y exigir validación en bandeja.
2) Añadir “evidencia mínima por código”: 1–3 `fragmento_id` por código sugerido.
3) Añadir metadatos de ejecución al reporte: `top_k`, `score_threshold`, `max_interviews`, iters, y `reason/project_open_code_rows` para interpretar landing rate.

*Actualizado para enfoque anti‑alucinaciones - Enero 2026*
