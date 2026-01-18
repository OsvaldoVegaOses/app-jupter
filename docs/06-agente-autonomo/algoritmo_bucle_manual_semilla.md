# Algoritmo: Bucle Manual (Semilla → Sugerencias → Código → Memo → Candidatos)

> Enero 2026

## Contexto

En la UX de Codificación Abierta (E3) aparece un **bucle manual e intencional**: el/la investigador(a) selecciona un **fragmento semilla**, ejecuta una búsqueda semántica de vecinos, inspecciona resultados, y decide el siguiente paso.

Este documento formaliza ese patrón como un **algoritmo reproducible** (human-in-the-loop) y como base para un **agente autónomo** que pueda:

- Automatizar partes mecánicas (consultar, resumir, consolidar)
- Medir **calidad** (no solo cantidad) de cada iteración
- Mantener trazabilidad (evidencia ↔ memo ↔ código ↔ fragmentos)

## Bucle manual observado (operacional)

Una iteración típica en E3:

1. `seed_fragment_id`: eliges un fragmento semilla.
2. `POST /api/coding/suggest`: recupera `top_k` fragmentos similares desde Qdrant, con filtros (archivo/actor/área/etc).
3. (Opcional) `POST /api/coding/suggest-code`: con los fragmentos seleccionados, el LLM propone un código + memo + confianza.
4. (Opcional) `POST /api/discovery/save_memo`: se guarda un memo Markdown con criterios + evidencia + síntesis IA.
5. (Opcional) `POST /api/codes/candidates/batch`: se envían fragmentos a la bandeja de candidatos para validación.
6. Se elige un nuevo seed (manual) y se repite.

Esto no es un loop del backend: es un **loop deliberado del investigador** (navegación/triangulación por semillas).

## Objetivo del algoritmo

Dado un `seed_fragment_id`, ejecutar N iteraciones y producir:

- Un rastro auditable de consultas (semillas usadas, filtros, tiempos, resultados)
- Métricas de calidad por iteración
- Propuestas de códigos con evidencia (si se habilita)
- Memos y/o candidatos para validación

### Variante: recorrido por segmentos (segment-sweep)

Además del loop "semilla → elegir siguiente semilla", existe la variante solicitada para E3:

- **Partir del segmento 1** (primer `par_idx` de una entrevista) y
- Repetir el proceso **por cada segmento** en orden, como lo haría un investigador revisando sistemáticamente el material.

Esta variante usa cada segmento como semilla **una sola vez** (en orden) y produce un reporte de calidad por segmento.

## Evaluación de calidad por iteración

La “calidad” en una iteración de vecinos semánticos no puede inferirse solo con `returned == requested`.

Este algoritmo usa señales operativas y metodológicas:

### Señales mínimas (sanidad)
- **Completitud:** `returned / requested`
- **Latencia:** `elapsed_ms` (para detectar degradación)
- **Puntajes:** promedio/mediana de `score` de Qdrant

### Señales metodológicas (Grounded Theory-friendly)
- **Novedad (novelty):** proporción de fragmentos no vistos en iteraciones previas.
- **Diversidad (diversity):** número de valores únicos en campos contextuales (archivo / actor / área temática).
- **Redundancia (redundancy):** overlap alto entre sets consecutivos (Jaccard) sugiere convergencia o estancamiento.

### Heurística sugerida (score de calidad)

Definir:
- $c = \frac{returned}{requested}$
- $n = novelty$ (0..1)
- $d = diversity$ normalizada (0..1)
- $s = \text{mediana(score)}$ (0..1 si está normalizada)

Una función simple:

$$
Q = 0.35c + 0.25n + 0.20d + 0.20s
$$

Uso:
- Si $Q$ cae sistemáticamente → el bucle no aporta nueva evidencia.
- Si $Q$ sube pero la redundancia también → convergencia (posible consolidación).

## Selección del siguiente seed (política)

El loop manual suele alternar entre:

- **Explotación:** seguir el vecino de mayor score para profundizar un tema.
- **Exploración:** saltar a un vecino “suficientemente similar” pero distinto en contexto (otro actor/área), para evitar túnel.

Política propuesta ("diverse-first"):

1. Preferir un candidato **no visto**.
2. Si existe alguno con **nuevo `actor_principal` o `area_tematica` o `archivo`**, elegir el de mayor score dentro de ese grupo.
3. Si no, elegir el **no visto** de mayor score.
4. Si todo ya fue visto, detener (saturación local) o bajar filtros.

## Criterios de detención

- **Saturación local:** novelty < 0.2 durante K iteraciones.
- **Estancamiento:** Jaccard overlap > 0.8 por K iteraciones.
- **Costo:** latencia p95 supera umbral (p.ej. 3–5s) repetidamente.

## Salidas (artefactos)

Por iteración:
- `seed_fragment_id`
- lista de sugerencias (IDs, score, contexto)
- métricas: completitud, novelty, diversidad, overlap

Por corrida:
- lista de semillas recorridas
- códigos sugeridos + confianza
- paths de memos guardados
- candidatos enviados

## Implementación MVP

- Script: `scripts/seed_loop_agent.py`
- Modo recomendado: usarlo como herramienta de “automatización de tareas mecánicas”, manteniendo control humano.

Ver también:
- `docs/06-agente-autonomo/contrato_epistemico_y_ux.md`
- `app/coding.py` (fuente de verdad de `suggest_similar_fragments`)

