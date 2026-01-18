# SeedLoopAgent (MVP)

Este MVP convierte el **bucle manual intencional** de E3 (semilla→vecinos semánticos→consolidación) en una herramienta reproducible.

## Qué automatiza

Por iteración:

- Llama `POST /api/coding/suggest` usando un `fragmento_id` semilla y filtros.
- Calcula métricas simples: completitud, novedad, diversidad, overlap.
- Elige el siguiente seed usando una política (`diverse-first` o `greedy`).
- Opcionalmente:
  - Llama `POST /api/coding/suggest-code` (LLM propone código y memo).
  - Guarda memo con `POST /api/discovery/save_memo`.
  - Envía candidatos con `POST /api/codes/candidates/batch`.

## Ejecución

Requiere backend corriendo en `http://localhost:8000` y `NEO4J_API_KEY` en el entorno (se lee desde `.env` si existe).

Ejemplo (loop sobre una entrevista específica):

```bash
python scripts/seed_loop_agent.py \
  --project jd-009 \
  --seed 482148ec-1593-5c62-b09b-a8083062b587 \
  --archivo "Entrevista_Dirigentas_UV_20_La_Florida_20260110_164758.docx" \
  --steps 6 \
  --top-k 10 \
  --suggest-code \
  --save-memo \
  --submit-candidates
```

## Modo "segment-sweep" (recorrer todos los segmentos)

Este modo implementa la idea: **partir del segmento 1 y repetir el proceso por cada segmento** tal como lo haría un investigador de forma manual.

- Obtiene la lista de fragmentos con `GET /api/coding/fragments?project=...&archivo=...&limit=...` (ordenados por `par_idx`).
- Para cada `fragmento_id` (segmento), ejecuta `POST /api/coding/suggest` y calcula métricas.
- Opcionalmente, solo si `quality_score >= --min-quality`, ejecuta `suggest-code`/`save-memo`/`submit-candidates`.

Ejemplo:

```bash
python scripts/seed_loop_agent.py \
  --mode segment-sweep \
  --project jd-009 \
  --archivo "Entrevista_Dirigentas_UV_20_La_Florida_20260110_164758.docx" \
  --top-k 10 \
  --max-fragments 5000 \
  --suggest-code \
  --save-memo \
  --submit-candidates \
  --min-quality 0.60
```

## Modo "project-sweep" (entrevista 1 → entrevista 2 → ...)

Este modo implementa: **luego de pasar por la primera entrevista continuar con la siguiente y así sucesivamente**.

- Obtiene entrevistas con `GET /api/interviews?project=...&limit=...`.
- Para cada `archivo`, ejecuta internamente `segment-sweep`.

### Orden epistemológico / por ingesta

`project-sweep` soporta un clasificador de orden para que el recorrido sea **metodológicamente defendible** (y reproducible):

- `--interview-order ingest-desc` (default): proxy de **orden de ingesta/actualización** (`actualizado` DESC).
- `--interview-order ingest-asc`: **cronológico** (útil si quieres respetar secuencia temporal).
- `--interview-order fragments-desc`: prioriza **casos ricos** (más fragmentos primero).
- `--interview-order max-variation`: **muestreo de máxima variación** intercalando estratos por (`area_tematica`, `actor_principal`) para cubrir diversidad temprano.
- `--interview-order theoretical-sampling`: priorización epistemológica basada en **señales de saturación** (`interview_reports`) + **gaps** por segmento. Ver spec: `spec_order_theoretical_sampling.md`.

Ejemplo:

```bash
python scripts/seed_loop_agent.py \
  --mode project-sweep \
  --project jd-009 \
  --interviews-limit 500 \
  --max-fragments 5000 \
  --top-k 10 \
  --interview-order max-variation

Ejemplo (theoretical sampling, sin inventar backlog):

```bash
python scripts/seed_loop_agent.py \
  --mode project-sweep \
  --project jd-009 \
  --interview-order theoretical-sampling \
  --recent-window 3 \
  --saturation-threshold 2
```

Con códigos foco (activa modo gap-first si hay baja evidencia):

```bash
python scripts/seed_loop_agent.py \
  --mode project-sweep \
  --project jd-009 \
  --interview-order theoretical-sampling \
  --focus-codes "Dificultad de pago,Acceso a subsidio" \
  --include-analyzed-interviews
```
```

Con acciones opcionales (gatilladas por `--min-quality`):

```bash
python scripts/seed_loop_agent.py \
  --mode project-sweep \
  --project jd-009 \
  --interviews-limit 200 \
  --max-fragments 2000 \
  --top-k 10 \
  --suggest-code \
  --save-memo \
  --submit-candidates \
  --min-quality 0.60
```

Salida:
- Un JSON en `reports/seed_loop_YYYYMMDD_HHMMSS.json` con todo el rastro + métricas.

## Interpretación rápida de métricas

- `quality_score`: combinación de completitud, novedad, diversidad y score.
- `novelty`: fracción de sugerencias no vistas antes (0..1).
- `overlap_prev`: Jaccard con la iteración anterior (0..1).

Lecturas sugeridas:
- Alta `novelty` + baja `overlap_prev` ⇒ exploración útil.
- Baja `novelty` + alta `overlap_prev` ⇒ saturación local (posible consolidación).

## Próximos pasos (para el agente autónomo)

- Incorporar una política multi-objetivo (exploración/explotación) con memoria de “conceptos” emergentes.
- Persistir trazas a Postgres (tabla de runs), similar a `app/discovery_runner.py`.
- Añadir verificación de diversidad semántica real (embeddings entre seeds) en vez de solo metadatos.
