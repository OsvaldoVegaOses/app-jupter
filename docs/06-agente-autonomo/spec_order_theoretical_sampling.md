# Spec técnica: `order=theoretical-sampling` (priorización epistemológica)

> **Actualización:** Enero 2026

Esta spec define cómo implementar `order=theoretical-sampling` en `GET /api/interviews` para ordenar entrevistas de manera **teórica/metodológicamente fundada**, sin inventar datos cuando falta backlog de reclutamiento.

## 0) Objetivo

Ordenar entrevistas **pendientes** para maximizar valor informativo bajo un enfoque de Grounded Theory:

- Detectar **saturación** (baja aparición de códigos nuevos).
- Cubrir **puntos ciegos** (segmentos poco explorados según metadatos disponibles).
- Dirigir la recolección hacia **códigos/temas clave con baja evidencia**, pero solo cuando exista una señal explícita (parámetro del usuario o lista validada).

## 1) Contrato API (mínimo viable)

### Endpoint

`GET /api/interviews?project=...&limit=...&order=theoretical-sampling`

### Respuesta (mínimo)

- `interviews: List[InterviewSummary]` (igual que hoy: `archivo`, `fragmentos`, `area_tematica`, `actor_principal`, `actualizado`)
- `order: str`

### Parámetros opcionales (recomendados)

Para no inventar “temas clave”:

- `focus_codes`: string CSV (ej: `Dificultad de pago,Acceso a subsidio`) **opcional**.
  - Si no viene, la parte “tema clave con baja evidencia” se desactiva (solo saturación + gaps).
- `recent_window`: int (default `3`) para detectar saturación en los últimos N reportes.
- `saturation_new_codes_threshold`: int (default `2`). Si `sum(codigos_nuevos)` en `recent_window` < threshold ⇒ saturación.
- `include_analyzed`: bool (default `false`). Si `false`, se priorizan entrevistas sin `interview_report`.

Nota: estos parámetros pueden implementarse como query params en el endpoint (preferible) o como defaults internos inicialmente.

## 2) Fuentes de datos (esquema existente)

### 2.1 Inventario de entrevistas + metadatos (proxy de backlog)

Tabla base (ya existe): `entrevista_fragmentos`.

Se usa un agregado existente (ya implementado en `list_interviews_summary`):

- `archivo`
- `fragmentos = COUNT(*)`
- `area_tematica` (máximo no nulo)
- `actor_principal` (máximo no nulo)
- `actualizado = MAX(updated_at)` (proxy de última actualización/ingesta)

SQL (referencial):

```sql
SELECT archivo,
       COUNT(*) AS fragmentos,
       COALESCE(MAX(actor_principal) FILTER (WHERE actor_principal IS NOT NULL), '') AS actor_principal,
       COALESCE(MAX(area_tematica) FILTER (WHERE area_tematica IS NOT NULL), '') AS area_tematica,
       MAX(updated_at) AS actualizado
  FROM entrevista_fragmentos
 WHERE project_id = $1
   AND (speaker IS NULL OR speaker <> 'interviewer')
 GROUP BY archivo
 ORDER BY MAX(updated_at) DESC, archivo ASC
 LIMIT $2;
```

### 2.2 Reportes por entrevista (señales de saturación)

Tabla (ya existe): `interview_reports` con `report_json`.

Campos relevantes del `InterviewReport` (en `report_json`):

- `archivo`
- `fecha_analisis`
- `codigos_nuevos` (int)
- `codigos_reutilizados` (int)
- `aporte_novedad` (float, %)
- `contribucion_saturacion` ("alta"|"media"|"baja")
- `tasa_cobertura` (float)

Query (referencial):

```sql
SELECT report_json
  FROM interview_reports
 WHERE project_id = $1
 ORDER BY fecha_analisis DESC
 LIMIT $2;
```

### 2.3 Evidencia por código (para `focus_codes`)

Tabla (ya existe): `analisis_codigos_abiertos`.

Métrica base:

- `evidence_count(codigo) = COUNT(DISTINCT fragmento_id)` por proyecto.
- `interview_coverage(codigo) = COUNT(DISTINCT archivo)` por proyecto.

Queries:

```sql
SELECT codigo,
       COUNT(DISTINCT fragmento_id) AS evidencias,
       COUNT(DISTINCT archivo) AS entrevistas
  FROM analisis_codigos_abiertos
 WHERE project_id = $1
 GROUP BY codigo;
```

Para una lista específica (`focus_codes`), filtrar por `codigo IN (...)`.

## 3) Señales (métricas) definidas

### 3.1 Indicador de saturación: Code Discovery Rate (CDR)

Definición operacional (por ventana reciente):

- `new_codes_recent = SUM(codigos_nuevos)` en los últimos `recent_window` reportes.
- Saturación si `new_codes_recent < saturation_new_codes_threshold`.

Observación: esto replica tu regla:

```text
IF new_codes_last_3_interviews < 2 THEN saturación
```

### 3.2 Code Frequency (sobre-representación)

Definición operacional (corpus):

- `coverage_ratio(c) = entrevistas_con_codigo(c) / entrevistas_analizadas_total`.

Uso (opcional): penalizar seguir entrevistando perfiles similares cuando los códigos dominantes ya están en >X%.

Nota: sin backlog de reclutamiento ni señales semánticas por entrevista, esta señal se usa **solo para diagnóstico global** o para ajustar pesos (no para mapear automáticamente “quién menciona qué”).

### 3.3 Segment Gap (puntos ciegos)

Segmento proxy (sin inventar):

- `segment_key = (area_tematica, actor_principal)`
- (opcional) extender a `requiere_protocolo_lluvia` si está disponible a nivel entrevista.

Gap operacional:

- `analyzed_count_in_segment = #entrevistas con report en ese segmento`.
- mayor gap ⇒ mayor prioridad.

## 4) Features derivadas por entrevista (sin inventar datos)

Para cada entrevista `i` del summary:

- `has_report(i)` (bool): existe `interview_reports(project_id, archivo)`.
- `segment_key(i)`.
- `fragmentos(i)`.
- `actualizado(i)`.

Y a nivel global:

- `saturated` (bool) según CDR.
- `segment_analyzed_counts[segment_key]`.

## 5) Scoring function (primer modelo simple)

### 5.1 Normalizaciones

- `richness_norm(i) = log1p(fragmentos(i)) / log1p(max_fragmentos)` (0..1)
- `gap_norm(i) = 1 / sqrt(1 + segment_analyzed_counts[segment_key(i)])` (0..1 aprox)
- `unseen(i) = 1.0 si !has_report(i) else 0.0` (si `include_analyzed=false`, esto además filtra)

### 5.2 Pesos por estado de saturación

Si `saturated == false` (fase exploración):

- `w_gap = 0.55`
- `w_rich = 0.25`
- `w_recency = 0.20` (proxy operacional para no ignorar material recién ingresado)

Si `saturated == true` (fase theoretical sampling):

- `w_gap = 0.70` (buscar diferencia)
- `w_rich = 0.20`
- `w_recency = 0.10`

`recency_norm(i)` puede derivarse de `actualizado(i)` solo para desempatar (no imprescindible).

### 5.3 Score base

```python
score_base(i) = unseen(i) * (
    w_gap * gap_norm(i)
  + w_rich * richness_norm(i)
  + w_recency * recency_norm(i)
)
```

### 5.4 “Tema clave con baja evidencia” (solo si `focus_codes` existe)

Condición:

- `focus_codes` no vacío.
- calcular `need(codigo)` por código:
  - `need(c) = 1 - clamp01(evidence_count(c) / evidence_target)`

Sin inventar, `evidence_target` se define como un default (ej: `10`) o configurable.

¿Cómo afecta entrevistas, si no tenemos tags/backlog real?

- **MVP sin inventar**: no se mapea a entrevistas individuales; se usa como “modo activo”:
  - si hay `need(c)` alto para algún `c`, se **refuerza `w_gap`** y se **evita entrevistas en segmentos ya muy analizados**.

En un siguiente nivel (mejora), se agrega un “probe” semántico por entrevista para estimar afinidad a `focus_codes` (ver sección 8.2).

## 6) Orden final y desempates

1) Filtrar por `include_analyzed`:
   - si `false`: usar solo entrevistas con `!has_report`.
2) Ordenar por `score_base DESC`.
3) Desempate estable: `actualizado DESC`, `archivo ASC`.

## 7) Auditoría (sin romper compatibilidad)

Recomendación: cuando `order=theoretical-sampling`, incluir en cada item (o en un campo paralelo `ranking_debug`) los features usados:

- `has_report`
- `segment_key`
- `segment_analyzed_count`
- `gap_norm`, `richness_norm`
- `saturated`, `new_codes_recent`, `recent_window`, `threshold`
- `score`

Esto permite defender el orden con evidencia técnica.

## 8) Oportunidades de mejora (implementables sin “inventar”)

### 8.1 Backlog real de reclutamiento

Agregar una entidad explícita:

- tabla `recruitment_backlog` con `candidate_id`, `tags`, `screening_answers`, `target_segments`.

Entonces “Cruzar con backlog” se vuelve directo: `focus_codes`/segment gaps se traducen a candidatos reales.

### 8.2 Probe semántico por entrevista (con Qdrant)

Sin depender de formularios, se puede aproximar “quién menciona el tema”:

- Para cada `focus_code` generar embedding del texto del código.
- Buscar en Qdrant con filtro `archivo=...` y tomar `max(score)` o `topN_avg` como `affinity(i, code)`.
- Entonces:

```python
score(i) += w_affinity * max_c( need(c) * affinity(i, c) )
```

Esto agrega “tema clave” sin inventar, porque la evidencia proviene del corpus.

### 8.3 Test plan mínimo

- Caso A: no hay reports ⇒ `saturated=false`, ordenar por gap/richness/recency (equivale a `max-variation` suavizado).
- Caso B: hay reports y `new_codes_recent < threshold` ⇒ pesos cambian y favorece segmentos no cubiertos.
- Caso C: `include_analyzed=false` ⇒ nunca retorna entrevistas ya reportadas.
- Caso D: `focus_codes` provisto pero sin Qdrant probe ⇒ solo activa modo “gap-first” (no claim de afinidad).
