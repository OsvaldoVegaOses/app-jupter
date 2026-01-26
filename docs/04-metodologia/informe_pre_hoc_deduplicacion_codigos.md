# Informe de desarrollo y fundamento teórico: Deduplicación Pre‑Hoc de Códigos

> **Ubicación**: `docs/06-metodologia/informe_pre_hoc_deduplicacion_codigos.md`
> 
> **Fecha**: 2026-01-20

## 1) Resumen ejecutivo

La deduplicación **Pre‑Hoc** es un mecanismo preventivo que intenta **detectar duplicados y casi‑duplicados de códigos** *antes* de que entren al flujo de validación o se “consoliden” en la base de conocimiento.

En esta implementación, el Pre‑Hoc:

- Normaliza textos para reducir variaciones superficiales (mayúsculas, acentos, puntuación, espacios).
- Calcula similitud mediante una combinación de:
  - **Levenshtein normalizado** (similaridad de edición)
  - **Token Set Ratio** (similaridad robusta al orden y stopwords)
- Aplica **guardrails** (criterios de solapamiento de tokens) para reducir falsos positivos.
- Se integra en:
  - Inserción de candidatos en PostgreSQL (bandeja de validación).
  - Endpoint de chequeo por lotes (para UI/ingesta): `POST /api/codes/check-batch`.

El objetivo no es “borrar” o “fusionar automáticamente” (eso corresponde a la **gobernanza** y a flujos Post‑Hoc), sino **anticipar** problemas y mejorar la calidad antes de que escalen.

---

## 2) Contexto y motivación (problema real)

En codificación cualitativa (y especialmente en flujos asistidos por LLM/Discovery), es común que aparezcan códigos que son semánticamente idénticos o muy similares, pero con variaciones:

- “escasez de agua” vs “escasez agua”
- “falta de empleo” vs “desempleo” (a veces equivalentes, a veces no)
- “violencia intrafamiliar” vs “violencia familiar”

Sin controles, estas variaciones:

- Inflan el catálogo de códigos.
- Dificultan métricas (saturación, cobertura).
- Introducen ruido en grafos (Neo4j) y búsquedas semánticas (Qdrant).
- Generan trabajo extra de revisión y fusión.

La deduplicación Pre‑Hoc busca **detectar temprano** duplicados probables y preparar un workflow de fusión/validación alineado con la arquitectura de gobernanza.

---

## 3) Marco conceptual: Pre‑Hoc vs Post‑Hoc (y gobernanza)

### 3.1 Definiciones operativas

- **Pre‑Hoc**: verificación preventiva **antes** de insertar o validar/confirmar.
  - Ideal para: bandeja de candidatos, chequeo por lote, sugerencias UX.
  - Riesgo principal: **falsos positivos** (bloquear o etiquetar como duplicado cuando no lo es).

- **Post‑Hoc**: diagnóstico **después** de acumulación de datos (con visibilidad global), para limpieza y gobernanza.
  - Ideal para: detectar clusters de duplicados, sugerir fusiones, auditoría.
  - Riesgo principal: costo computacional y manejo de “historia” y trazabilidad.

- **Gobernanza de fusión**: la fusión no debe ser una “eliminación”; debe preservar evidencia y auditoría.
  - En arquitectura del sistema, las fusiones se manejan como cambios trazables (p.ej. marcar `estado='fusionado'`, almacenar destino `fusionado_a`, usar idempotencia, registrar auditoría).

### 3.2 Principio clave

El Pre‑Hoc debe ser **conservador**:

- Mejor *avisar* y sugerir que *bloquear* indiscriminadamente.
- Debe priorizar minimizar falsos positivos.
- Debe dejar la decisión final en el humano (panel de validación) o en flujos Post‑Hoc gobernados.

---

## 4) Fundamento teórico de la similitud

### 4.1 Normalización de texto

La normalización transforma cadenas $s$ a una forma canónica $n(s)$ para que diferencias superficiales no afecten la comparación.

Ejemplos típicos:

- Lowercasing: “Agua” → “agua”
- Eliminación/normalización de acentos: “pérdida” → “perdida”
- Compactación de espacios
- Limpieza de puntuación irrelevante

Esto reduce “varianza ortográfica” y aumenta la estabilidad del matching.

### 4.2 Distancia Levenshtein (edición)

La distancia de Levenshtein $d(a,b)$ cuenta ediciones mínimas (inserciones, borrados, sustituciones) para transformar $a$ en $b$.

Para convertirlo a similaridad en rango $[0,1]$ se usa:

$$
\text{sim}_{lev}(a,b) = 1 - \frac{d(a,b)}{\max(|a|, |b|)}
$$

Ventajas:

- Sensible a cambios finos.
- Muy útil cuando las cadenas son casi iguales.

Limitaciones:

- Penaliza mucho reordenamientos (“agua escasez” vs “escasez agua”).
- Puede fallar con stopwords (“escasez de agua” vs “escasez agua”).

### 4.3 Similaridad por tokens (Token Set Ratio)

La similaridad por conjuntos de tokens mide cercanía en vocabulario, robusta al orden.

- Divide en tokens (palabras) tras normalización.
- Compara conjuntos/solapes, ignorando reordenamientos.

Ventajas:

- Resiste diferencias de orden.
- Resiste inserción de stopwords.

Limitaciones:

- Puede sobre‑estimar similitud en casos con tokens genéricos (“problema de X”).

### 4.4 Enfoque híbrido

Se usa una combinación (práctica) de ambas medidas:

- Si Levenshtein es alto → casi igual por edición.
- Si Token Set Ratio es alto → mismas palabras esenciales, aun con orden/stopwords.

El sistema utiliza un criterio de “máximo” o combinación conservadora para capturar ambas señales.

---

## 5) Diseño de la solución Pre‑Hoc (desarrollo)

### 5.1 Archivos y puntos de integración

Componentes principales:

- `app/code_normalization.py`
  - Normalización y comparación de códigos.
  - Guardrails de tokens.
  - Funciones de búsqueda de similares.

- `app/postgres_block.py`
  - Inserción de candidatos: `insert_candidate_codes(...)`.
  - Hook Pre‑Hoc: sugiere potencial fusión (vía memo) antes de persistir.

- `backend/app.py`
  - Endpoint de chequeo por lote: `POST /api/codes/check-batch`.
  - Sirve para UI/ingesta antes de insertar.

### 5.2 Guardrails: solapamiento mínimo de tokens

Para disminuir falsos positivos, se valida que exista un solapamiento mínimo de tokens “significativos”.

Intuición:

- No basta con alta similitud por edición si el contenido conceptual no se alinea.
- La condición de tokens evita que frases distintas pero con “forma” parecida se marquen como duplicadas.

Ejemplo de riesgo sin guardrail:

- “falta de agua” vs “falta de apoyo”
  - Podrían tener ciertos patrones similares por estructura.
  - Los tokens clave difieren.

### 5.3 Filtro de longitud (prefiltro eficiente)

La comparación exhaustiva contra cientos/miles de códigos puede ser costosa.

Se aplica un prefiltro por longitud que descarta pares imposibles:

- Si $|a|$ y $|b|$ difieren demasiado y el umbral es alto, es improbable que sean equivalentes.

En la versión mejorada, este prefiltro se **relaja** cuando la similitud por tokens es alta, evitando falsos negativos por stopwords (p.ej. “de”).

### 5.4 Umbrales

Se utiliza un umbral $t$ (por defecto alrededor de 0.85 en flujos Pre‑Hoc) para declarar “similar”.

Recomendaciones:

- Pre‑Hoc (preventivo): $t \in [0.85, 0.92]$ según nivel de ruido.
- Post‑Hoc (diagnóstico): puede bajar a $0.80$ para explorar clusters.

En Pre‑Hoc se prioriza evitar falsos positivos, por eso tiende a ser más alto.

---

## 6) Flujo end‑to‑end (operativo)

### 6.1 Inserción de candidatos (bandeja)

1. Llega un candidato (manual/LLM/Discovery/etc.).
2. `insert_candidate_codes(...)` obtiene códigos existentes del proyecto.
3. Se ejecuta sugerencia Pre‑Hoc (similares).
4. Si hay coincidencias, se anota en `memo` como guía para la validación (no fusión automática).

Resultado: el validador humano tiene señales tempranas.

### 6.2 Chequeo por lote (UI/ingesta)

1. El frontend o una herramienta envía un lote de códigos propuestos.
2. `POST /api/codes/check-batch`:
   - Detecta duplicados vs DB.
   - Detecta duplicados **dentro del mismo lote** (intra‑batch).
3. Devuelve métricas (conteos) y flags por item (p.ej. `duplicate_in_batch`).

Resultado: el usuario puede corregir antes de insertar.

### 6.3 Post‑Hoc (no reemplazado)

El Pre‑Hoc **no reemplaza**:

- Fusión gobernada (con estado `fusionado`, `fusionado_a`, idempotencia).
- Detección global por lotes para limpieza.

Su rol es preventivo y de calidad.

---

## 7) Consideraciones de calidad y riesgos

### 7.1 Riesgo: falsos positivos

Mitigación:

- Guardrails por solapamiento de tokens.
- Umbrales conservadores en Pre‑Hoc.
- No se auto‑fusiona: se recomienda/etiqueta.

### 7.2 Riesgo: falsos negativos

Mitigación:

- Mezcla de Levenshtein + token_set_ratio.
- Relajar prefiltro de longitud cuando tokens sugieren alta coincidencia.

### 7.3 Rendimiento

- Prefiltro por longitud reduce comparaciones.
- Agrupación intra‑batch reduce trabajo redundante.

---

## 8) Recomendaciones de operación (para equipos)

- Ajustar umbral Pre‑Hoc (0.85–0.92) según el “ruido” del proyecto.
- Usar `check-batch` en el frontend antes de inserciones masivas.
- Mantener la deduplicación Post‑Hoc como auditoría periódica.
- Documentar decisiones de fusión en `memo` para trazabilidad.

---

## 9) Referencias internas (código y arquitectura)

- Implementación Pre‑Hoc:
  - `app/code_normalization.py`
  - `app/postgres_block.py` (`insert_candidate_codes`)
  - `backend/app.py` (`POST /api/codes/check-batch`)

- Marco de gobernanza y fusión:
  - `docs/04-arquitectura/Fusión_duplicados`
  - `docs/04-arquitectura/fusion_duplicados_api_spec.md`

---

## 10) Calibración por proyecto (guía práctica)

Esta sección describe cómo **calibrar** el Pre‑Hoc para un proyecto concreto (p.ej. `jd-007`) sin introducir falsos positivos.

### 10.1 Objetivo de calibración

Encontrar un umbral $t$ y reglas complementarias (tokens/longitud) que:

- Detecten duplicados *probables* de forma consistente.
- Mantengan el costo humano de revisión bajo control.
- Eviten bloquear o etiquetar como duplicado aquello que no lo es.

En Pre‑Hoc, el éxito se mide más por **baja tasa de falsos positivos** que por cobertura absoluta.

### 10.2 Procedimiento recomendado (iterativo)

1. **Recolectar una muestra**
  - Extraer una lista representativa de códigos existentes del proyecto (y/o candidatos recientes).
  - Tomar un subconjunto (ej.: 50–200) para revisión manual.

2. **Generar pares candidatos**
  - Comparar cada código nuevo vs catálogo existente.
  - Conservar el top‑K (ej.: 3–5) más similares por código.

3. **Etiquetado humano (rápido)**
  - Marcar cada par como: `duplicado`, `muy similar (posible fusión)`, `distinto`.
  - Registrar por qué (1 frase) cuando sea dudoso.

4. **Ajuste del umbral**
  - Subir $t$ si aparecen falsos positivos.
  - Bajar $t$ si hay demasiados falsos negativos en casos obvios.

5. **Re‑validación**
  - Repetir con una muestra distinta (idealmente de otra etapa/fuente).

### 10.3 Valores guía por escenario

- **Proyecto con mucha variación ortográfica (múltiples capturistas / LLM libre)**:
  - Pre‑Hoc: $t \approx 0.85–0.88$ (más sensible), pero mantener guardrails estrictos de tokens.
- **Proyecto con catálogo estable (taxonomía bien definida)**:
  - Pre‑Hoc: $t \approx 0.90–0.92$ (más conservador).
- **Códigos muy cortos (1–2 palabras)**:
  - Recomendación: aumentar $t$ (ej. $\ge 0.92$) o exigir solapamiento total de tokens.
  - Motivo: los falsos positivos crecen cuando hay poca señal textual.

### 10.4 Heurísticas recomendadas (para el equipo)

- Preferir tokens “informativos” (evitar que stopwords dominen el match).
- Si el código es muy genérico (p.ej. “problemas”, “apoyo”), exigir tokens adicionales o intervención humana.
- Cuando el Pre‑Hoc sugiera similitud, tratarlo como **alerta** y no como acción automática.

### 10.5 Notas específicas para `jd-007` (operativas)

Sin asumir el dominio exacto del proyecto, una pauta segura para `jd-007` es:

- Comenzar con **$t = 0.88–0.90$** en Pre‑Hoc.
- Revisar manualmente los *top‑matches* durante 1–2 sesiones de validación.
- Si aparecen falsos positivos por términos comunes (“falta”, “problema”, “acceso”), subir a **$t \ge 0.90$** o endurecer el guardrail de tokens.

Checklist de verificación en la bandeja:

- ¿El par comparte el núcleo semántico (mismo fenómeno) o solo estructura lingüística?
- ¿La diferencia es una stopword (“de”, “la”, “el”) o un concepto (“agua” vs “apoyo”)?
- ¿Conviene fusionar o conviene jerarquizar (sub‑código vs macro‑código)?

---

**Resultado esperado**: el Pre‑Hoc se convierte en un “control de calidad” ligero que reduce duplicación temprana sin reemplazar la gobernanza Post‑Hoc.

---

## 11) Observabilidad y auditoría operativa (logs)

Esta sección describe la **telemetría** agregada para entender:

- Dónde se está yendo el tiempo (rendimiento).
- Si el umbral está demasiado alto/bajo (calibración).
- Si los guardrails están descartando demasiado (falsos negativos) o demasiado poco (falsos positivos).

### 11.1 Eventos de log (backend)

El endpoint `POST /api/codes/check-batch` emite eventos estructurados:

- `api.codes.check_batch.start`
  - Campos: `project`, `threshold`, `input_count`.

- `api.codes.check_batch.completed`
  - Campos clave (resumen):
    - `empty_count`: entradas vacías (solo espacios) en el batch.
    - `existing_count`: tamaño del “catálogo” contra el que se compara.
    - `batch_unique_count`, `batch_duplicate_groups`, `batch_duplicates_total`: salud intra‑batch.
    - `matched_count`, `has_any_similar`: volumen de alertas por similitud.
    - `similarity_best_stats`: distribución de la **mejor** similitud por código (`min`, `p50`, `p90`, `max`).
    - `phase_ms`: tiempos por fase (`fetch_existing`, `scan_groups_total`, `build_results`, `total`).
    - `similarity_engine`: contadores agregados del motor (ver 11.2).

- `api.codes.check_batch.failed`
  - Campos: `project`, `threshold`, `input_count`, `error`.

### 11.2 Métricas internas del motor de similitud

En `api.codes.check_batch.completed.similarity_engine` se reportan contadores agregados:

- `groups_scanned`: cantidad de claves normalizadas comparadas (representantes del batch).
- `comparisons`: comparaciones totales (aprox. `groups_scanned * existing_count`).
- `skipped_len_prefilter`: descartes por prefiltro de longitud.
- `skipped_similarity`: descartes por similitud final bajo el umbral.
- `skipped_token_overlap`: descartes por guardrail de solapamiento de tokens.
- `kept`: candidatos que pasaron filtros y quedaron como matches antes de aplicar `limit`.
- `slow_scans`: cuántos scans individuales tardaron ≥ 200 ms.
- `scan_elapsed_ms_sum`: suma de tiempos de scans (para detectar presión de CPU).

Interpretación rápida:

- Mucho `skipped_len_prefilter` y poco `kept` suele indicar que el catálogo es heterogéneo y el prefiltro está ahorrando trabajo (bien).
- Mucho `skipped_token_overlap` con `matched_count` bajo puede indicar guardrail demasiado estricto para tu dominio (posible fuente de falsos negativos).
- `slow_scans` > 0 de forma consistente sugiere:
  - catálogo demasiado grande,
  - batch muy grande,
  - o necesidad de caching / pre‑indexado.

### 11.3 Logging de muestras (opcional)

Por defecto, los logs evitan volcar contenidos completos para reducir exposición de texto en auditoría.

Para depuración puntual (en ambiente controlado), se puede habilitar el muestreo:

- Variable de entorno: `PREHOC_LOG_SAMPLES=1`
- Efecto: añade `sample_matches` con hasta 3 ejemplos (`codigo`, `best_existing`, `best_similarity`) truncados.

Recomendación: activar solo para sesiones cortas de calibración y luego desactivarlo.

---

## 12) Informe de desarrollo (bitácora) — Pre‑Hoc y consolidación operativa

> **Addendum**: 2026-01-21

Esta sección resume, en formato de **informe de desarrollo**, los cambios implementados para hacer el flujo Pre‑Hoc usable, auditable y verificable en condiciones reales.

Dictamen formal de fase (defendible):
- [docs/06-metodologia/dictamen_fase1_consolidacion_y_limpieza_el_puente.md](docs/06-metodologia/dictamen_fase1_consolidacion_y_limpieza_el_puente.md)
- [docs/06-metodologia/codificacion_abierta/Transición_A_Cod_Axial/dictamen_fase1_consolidacion_y_limpieza_el_puente.md](docs/06-metodologia/codificacion_abierta/Transición_A_Cod_Axial/dictamen_fase1_consolidacion_y_limpieza_el_puente.md)

### 12.1 Objetivo de desarrollo

1) Hacer que el Pre‑Hoc sea **conservador y confiable** (alerta temprana sin fusiones automáticas “caja negra”).

2) Garantizar **observabilidad** (métricas + logs estructurados) para calibrar umbrales y diagnosticar rendimiento.

3) Asegurar un workflow completo desde UI:

- detectar (Pre‑Hoc)
- revisar
- ejecutar fusiones (gobernanza Post‑Hoc, con auditoría e idempotencia)

4) Tener evidencia verificable con:

- pruebas reales (datos persistidos en PostgreSQL)
- automatización E2E (Playwright)

---

### 12.2 Entregables implementados

#### A) Endpoint Pre‑Hoc de chequeo por lote

- Se fortaleció `POST /api/codes/check-batch` para:
  - analizar un lote de códigos contra el catálogo del proyecto (PostgreSQL)
  - detectar duplicados intra‑batch (mismo lote)
  - devolver resultados accionables por ítem (matches, similitudes, duplicado en el lote)

Motivo: el Pre‑Hoc debe operar sobre el **dataset completo**, no depender de paginación o de lo que esté visible en pantalla.

#### B) Motor de similitud con telemetría interna

- Se añadió instrumentación en el motor de comparación (normalización + similitud + guardrails) para poder reportar:
  - comparaciones realizadas
  - descartes por prefiltro de longitud
  - descartes por umbral de similitud
  - descartes por guardrail de solapamiento de tokens
  - tiempo total del escaneo

Objetivo: poder distinguir entre “no hay duplicados reales” vs “el guardrail/umbral está demasiado estricto”.

#### C) Observabilidad operativa en logs JSONL

- Se agregaron eventos estructurados para `check-batch` (ver sección 11), incluyendo:
  - tiempos por fase (`phase_ms`)
  - distribución de similitudes (`similarity_best_stats`)
  - agregados del motor (`similarity_engine`)
  - modo de muestreo opcional (`PREHOC_LOG_SAMPLES=1`)

Resultado: es posible depurar y calibrar Pre‑Hoc sin inspección manual de grandes volúmenes de datos.

#### D) UI: modal Pre‑Hoc + acciones de fusión gobernada

- Se implementó en la Bandeja (frontend) un flujo operativo:
  - selección de candidatos
  - “Detectar Duplicados Prehoc” (consulta `check-batch`)
  - revisión de sugerencias
  - ejecución de fusiones vía endpoint de gobernanza (auto‑merge por pares)

Notas importantes:

- El Pre‑Hoc **no fusiona automáticamente**; el usuario decide.
- La ejecución de fusiones se hace por endpoints de gobernanza (`/api/codes/candidates/merge` y `/api/codes/candidates/auto-merge`).
- Se reforzó que las fusiones tengan `memo` (justificación) y `idempotency_key` (reintentos seguros).

#### E) Prueba con datos reales + automatización E2E

- Se probó `POST /api/codes/check-batch` con datos persistidos en PostgreSQL (códigos candidatos reales) para confirmar:
  - respuesta 200
  - estructura de salida
  - detección de intra‑batch y matches vs catálogo

- Se creó una prueba E2E con Playwright que:
  - crea usuario/proyecto
  - inserta candidatos
  - navega la UI
  - dispara “Detectar Duplicados Prehoc”
  - valida que se muestra el modal y que el backend responde 200

Esto garantiza regresión mínima del flujo UI↔backend.

---

### 12.3 Hallazgo clave: “La fusión se aplica pero no baja Pendientes” (explicación metodológica)

Durante la validación con el proyecto real, se observó el síntoma:

- la fusión “parece” ejecutarse,
- pero el resumen de la Bandeja no disminuye (p.ej. Pendientes ≈ 440).

Esto no necesariamente es un bug. Es una consecuencia de la semántica de gobernanza implementada:

- En muchos merges, la acción principal es **reasignar evidencia**: `codigo := target_codigo`.
- Esa reasignación puede mantener `estado='pendiente'` si la evidencia aún requiere revisión humana.
- Solo en casos de deduplicación estricta (misma `fragmento_id` ya existe bajo el destino) se marca `estado='fusionado'`.

En otras palabras:

- La fusión reduce **entropía del codebook** (menos variantes),
- pero no necesariamente reduce **backlog de validación** (pendientes por evidencia).

#### Mejora aplicada para que “se refleje” correctamente

Para evitar confusiones operativas, el endpoint de stats y la UI se extendieron para reportar:

- **conteo de filas** (candidatos/evidencias) por estado
- **conteo de códigos únicos** (`COUNT(DISTINCT codigo)`) por estado y total

Así se puede ver claramente el efecto de consolidación:

- “Pendientes” puede mantenerse alto
- pero “códigos únicos” debería bajar al consolidar variantes léxicas

---

### 12.4 Checklist de verificación (operación)

Cuando se ejecute un merge (manual o auto‑merge):

1) Revisar el mensaje/resultado en UI (conteos `total_merged`, `pairs_processed`).

2) Refrescar stats:
  - verificar cambio en **códigos únicos**
  - verificar `fusionado` solo cuando aplique dedupe por evidencia duplicada

3) Consultar logs (`logs/**/app.jsonl`) en caso de dudas:
  - `api.auto_merge_candidates.start`
  - `api.auto_merge_candidates.completed`
  - (y para Pre‑Hoc) `api.codes.check_batch.*`

4) Para investigación metodológica: registrar `memo` (justificación) como parte de la trazabilidad.

---

### 12.5 Próximos pasos recomendados (si se decide ampliar)

- **UX de validación de duplicados**: permitir editar el código destino por par antes de ejecutar merges en lote.
- **Política de backlog**: decidir si se desea que una fusión reasignada cambie estado (ej. marcar como “fusionado” o “pendiente”), entendiendo el impacto metodológico.
- **Auditoría avanzada**: persistir/consultar reportes de “planes” (runner IA) por `run_id` para reproducibilidad.

