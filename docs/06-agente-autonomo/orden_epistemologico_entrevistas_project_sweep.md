# Orden epistemológico de entrevistas (project-sweep)

> **Actualización:** Enero 2026

Este documento explica el **desarrollo**, las **opciones disponibles** y las **oportunidades de mejora** para ordenar entrevistas cuando automatizamos recorridos tipo `project-sweep` (entrevista 1 → entrevista 2 → ...).

## 1) Por qué el orden importa (fundamento metodológico)

En un flujo inspirado en Teoría Fundamentada (Grounded Theory), el orden en que se recorren entrevistas no es un detalle técnico: afecta el tipo de conocimiento que emerge y cómo se justifica el proceso.

- **Orden por ingesta / cronología**: favorece trazabilidad temporal y replicabilidad operativa. Útil cuando el análisis sigue la secuencia del trabajo de campo o se requiere auditoría del pipeline.
- **Máxima variación (maximum variation sampling)**: favorece diversidad temprana de casos para mapear el espacio conceptual antes de consolidar.
- **Casos ricos**: favorece densidad empírica temprana (más material) para construir categorías iniciales con evidencia.

En APP_Jupter, el objetivo no es imponer una sola metodología: es ofrecer un **orden defendible y explícito**, para que el usuario pueda elegir según su estrategia de investigación.

## 2) Desarrollo implementado (estado actual)

### API

Se extendió `GET /api/interviews` para aceptar un parámetro de orden:

- `GET /api/interviews?project=...&limit=...&order=...`

El endpoint retorna:

- `interviews`: lista de entrevistas (cada una con `archivo`, `fragmentos`, `area_tematica`, `actor_principal`, `actualizado`)
- `order`: eco del orden aplicado

**Fuente de datos** (proxy de ingesta): `actualizado = MAX(updated_at)` calculado desde `entrevista_fragmentos`.

### Agente (CLI)

El script `scripts/seed_loop_agent.py` incorpora:

- `--interview-order {ingest-desc|ingest-asc|alpha|fragments-desc|fragments-asc|max-variation}`

y lo envía al backend al listar entrevistas.

## 3) Órdenes disponibles (opciones y uso recomendado)

### 3.1 `ingest-desc` (default)

**Qué hace:** ordena por `actualizado` descendente (proxy de último update/ingesta), y luego por `archivo`.

**Para qué sirve:**

- Operación reproducible: “lo más reciente primero”.
- Escenarios donde el proyecto se está alimentando incrementalmente.

### 3.2 `ingest-asc`

**Qué hace:** cronológico por `actualizado` ascendente.

**Para qué sirve:**

- Reconstrucción temporal del campo.
- Auditoría secuencial del pipeline.

### 3.3 `alpha`

**Qué hace:** orden alfabético por `archivo`.

**Para qué sirve:**

- Orden determinístico simple cuando el naming ya codifica fecha/entrevistado.

### 3.4 `fragments-desc` / `fragments-asc`

**Qué hace:** ordena por cantidad de fragmentos (densidad empírica) y luego por `archivo`.

**Para qué sirve:**

- `fragments-desc`: empezar con entrevistas “ricas” para construir categorías iniciales.
- `fragments-asc`: revisar “casos mínimos” temprano (útil para detectar outliers o vacíos de captura).

### 3.5 `max-variation`

**Qué hace:** implementa un muestreo de máxima variación reproducible:

1) Agrupa entrevistas por estrato `(area_tematica, actor_principal)`.
2) Dentro de cada estrato, ordena por `actualizado` DESC.
3) Intercala estratos priorizando estratos pequeños (casos raros primero).

**Para qué sirve:**

- Cobertura temprana de diversidad temática/actores.
- Minimizar el riesgo de “encerrarse” en un solo subconjunto del corpus.

## 4) Limitaciones actuales (honestidad metodológica)

- `actualizado` es un **proxy operacional** (MAX(updated_at)), no necesariamente la fecha real de entrevista ni de ingesta del DOCX.
- `max-variation` depende de la **calidad de metadatos** (`area_tematica`, `actor_principal`). Si vienen vacíos, el estratificado se degrada.
- El orden aún no utiliza señales de análisis (saturación, novedad de códigos, landing rate, etc.). Es una base defendible, pero no “theoretical sampling” completo.

## 5) Oportunidades de mejora (backlog defendible)

Estas mejoras apuntan a que el orden se convierta en un componente explícito de una estrategia epistemológica y no solo operacional.

### 5.1 Orden por “theoretical sampling” (prioridad alta)

Idea: seleccionar la siguiente entrevista no por metadatos, sino por su **valor informativo esperado**.

Señales candidatas (ya existen o son alcanzables):

- `GET /api/reports/interviews`: métricas por entrevista (códigos nuevos/reutilizados, saturación, etc.).
- Métricas del propio loop: `novelty`, `overlap_prev`, `quality_score`.
- Conteo de candidatos validados/rechazados por entrevista.

Políticas posibles:

- **Exploración**: priorizar entrevistas con mayor probabilidad de códigos nuevos.
- **Consolidación**: priorizar entrevistas que confirman/contradicen categorías emergentes.
- **Negativos teóricos**: priorizar entrevistas “atípicas” (baja similitud / baja cobertura) para tensionar categorías.

### 5.2 Persistir “ingested_at” real (calidad de cronología)

Agregar un campo de ingesta explícito (p. ej. tabla `interviews` o columna derivada) para evitar depender de `updated_at` de fragmentos.

### 5.3 “Balanced workload” (costos y latencia)

Ordenar para controlar costo de LLM/Qdrant:

- Priorizar entrevistas con menos fragmentos cuando se habilitan acciones LLM.
- Cortar por presupuesto: `max_fragments` adaptativo según la entrevista.

### 5.4 Estratificación enriquecida

Extender `max-variation` para incluir:

- `requiere_protocolo_lluvia`
- distribución de `speaker`
- clusters semánticos (usando embeddings/Qdrant) como estratos

### 5.5 Observabilidad y reproducibilidad

- Guardar en el reporte: `interview_order`, versión de estrategia, y “razón” de selección por entrevista.
- (Opcional) persistir runs a PostgreSQL (similar a `discovery_runner`) para auditoría.

## 6) Cómo se usa hoy

Ejemplo (máxima variación):

```bash
python scripts/seed_loop_agent.py \
  --mode project-sweep \
  --project jd-009 \
  --interviews-limit 200 \
  --interview-order max-variation \
  --top-k 10 \
  --max-fragments 2000
```

Si se habilitan acciones LLM/memos/candidatos, se recomienda usar `--min-quality` para controlar costos y ruido.
