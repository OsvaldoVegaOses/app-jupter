# Evaluación crítica del flujo (modelo híbrido)

**Fecha:** 2025-12-24  
**Repositorio/Workspace:** APP_Jupter  
**Alcance:** Evaluación doctoral del flujo híbrido (LLM propone → humano valida → sistema promueve) y oportunidades de mejora en UX/UI y calidad de investigación.

---

## 1) Resumen ejecutivo

El flujo híbrido implementado es metodológicamente sólido: conserva el control interpretativo en el investigador, reduce el riesgo de automatización acrítica y habilita trazabilidad auditada. El principal riesgo no es técnico sino **socio-metodológico**: si la bandeja de validación se convierte en un “backlog administrativo”, la práctica deriva hacia validaciones rápidas (sesgo de automatización, fatiga, inconsistencia) y se erosiona la reflexividad (núcleo de Teoría Fundamentada).

Prioridad recomendada: fortalecer **(a)** el protocolo de decisión (criterios/umbrales), **(b)** la UX de evidencia + contexto + consistencia, y **(c)** métricas de calidad (fiabilidad/saturación/deriva del vocabulario), por encima de más endpoints o más “inteligencia”.

### 1.1 Decisiones recomendadas (para ejecutar desarrollo)

Esta sección está escrita para que el equipo pueda **decidir y actuar** sin reinterpretar el documento.

**Decisión A — Hacer de la bandeja el “centro” del producto (no un listado):**
- **Qué cambia:** priorizar UX de validación basada en evidencia (cita + contexto + códigos existentes + acciones rápidas).
- **Por qué:** reduce sesgo de automatización, fatiga y backlog infinito.
- **Impacto:** alto (calidad investigativa + retención del usuario).
- **Esfuerzo:** medio.

**Decisión B — Formalizar un protocolo de decisión mínimo (y medir adherencia):**
- **Qué cambia:** definir reglas operativas (nuevo vs sinónimo, criterios de validación/rechazo, cuándo fusionar).
- **Por qué:** sin protocolo, el sistema produce inconsistencia y deriva terminológica.
- **Impacto:** alto.
- **Esfuerzo:** bajo (documento + pequeñas ayudas en UI).

**Decisión C — Métricas de calidad como “gates” (no solo dashboards):**
- **Qué cambia:** establecer umbrales y alertas (p.ej., backlog pendiente, tasa de fusión, tasa de corrección de citas, saturación).
- **Por qué:** obliga a pasar de volumen → rigor; evita inflar códigos.
- **Impacto:** alto.
- **Esfuerzo:** medio.

**Decisión D — Aislamiento por proyecto como requisito no negociable:**
- **Qué cambia:** garantizar que consultas de grafo/contexto y sugerencias no mezclen proyectos.
- **Por qué:** amenaza directa a validez interna/confirmabilidad.
- **Estado hoy (verificado 2025-12-24):** mitigación aplicada en consultas clave (GraphRAG y Link Prediction ya filtran por `project_id` en el grafo consultado).
- **Impacto:** muy alto.
- **Esfuerzo:** bajo–medio (completar el aislamiento donde falte, y validar con tests/queries de regresión).

### 1.2 Plan de implementación (2 sprints)

**Sprint 1 (1–2 semanas): “Bandeja operable + control básico”**
- UX/UI: bandeja con vista por `pendiente` (default), acciones por fila (validar/rechazar/fusionar), y acceso a “ver contexto”.
- Reglas: checklist/protocolo mínimo visible (microcopy) para validar.
- Métricas mínimas: `pendientes_total`, `pendientes_por_origen`, `tiempo_medio_resolucion`.

**Sprint 2 (1–2 semanas): “Consistencia + calidad como gate”**
- UX/UI: ejemplos canónicos por código al validar + sugerencia de fusión (sinónimos frecuentes).
- Calidad: alertas/gates (p.ej. si `pendientes_total` crece N días, bloquear “análisis nuevo” o sugerir sesión de consolidación).
- Investigación: flujo de muestreo para doble validación en muestra pequeña.

### 1.3 Criterios de aceptación (Definition of Done)

**Bandeja de candidatos**
- Un investigador puede: listar pendientes, validar, rechazar con memo opcional y fusionar, sin cambiar de pantalla más de lo necesario.
- Cada decisión muestra (antes de confirmar): cita + contexto del fragmento + archivo + origen.

**Promoción a definitivo**
- Promover mueve solo `validado` a definitivos y deja rastro (quién/cuándo) a nivel de candidato.

**Calidad/validez**
- No se mezcla evidencia/códigos entre proyectos en consultas de contexto o sugerencias.
- Existe una verificación básica (manual o automatizada) con 2 proyectos y datos mínimos que demuestra que GraphRAG/LinkPrediction no “cruzan” nodos.

### 1.4 Métricas de éxito (para decidir si funcionó)

- **Backlog saludable:** `pendientes_total` no crece indefinidamente; tendencia a estabilizar.
- **Consistencia:** aumenta `tasa_fusion` cuando hay deriva (señal de consolidación).
- **Rigor:** disminuye `idx_mismatch_unfixable` y aumenta `linkage_rate` en análisis.
- **Eficiencia:** baja el tiempo medio a resolver un candidato sin bajar tasa de rechazo justificado.

---

## 2) Qué es el modelo híbrido en este sistema (lectura operacional)

### 2.1 Ciclo de vida del código
1. **Proposición** (orígenes típicos):
   - Análisis automático LLM (Etapa 3: codificación abierta).
   - Codificación manual (investigador asigna código a un fragmento).
   - Exploración (Discovery / búsqueda conceptual).
   - Sugerencias por similitud semántica.
2. **Bandeja (candidato)**: cada propuesta entra como “código candidato” con estado `pendiente`.
3. **Decisión humana**:
   - Validar: el candidato pasa a `validado`.
   - Rechazar: el candidato pasa a `rechazado` (idealmente con motivo/memo).
   - Fusionar: el candidato pasa a `fusionado` con referencia al destino.
4. **Promoción**: solo los candidatos `validado` se promueven a la tabla definitiva de codificación abierta.

### 2.2 Ventaja metodológica clave
El sistema separa explícitamente:
- **Generación de hipótesis** (máquina / heurística / exploración)
- **Afirmación interpretativa** (humano como autoridad epistémica)

Esta separación es compatible con prácticas CAQDAS modernas: el software puede acelerar el muestreo y la comparación constante, pero no debe cerrar el significado.

---

## 3) Evaluación crítica (nivel doctoral): fortalezas

### 3.1 Control epistémico y auditabilidad
- Mantiene la responsabilidad interpretativa en el investigador.
- Favorece trazabilidad: la decisión de validar/rechazar/fusionar es un artefacto de investigación (auditable).

### 3.2 Mitigación de “ghost links” (cita → fragmento)
- La recuperación/corrección basada en cita y el registro de métricas de linkeo es un mecanismo serio para evitar códigos sin evidencia.
- En teoría, esto protege la cadena: **dato → evidencia → código → categoría**.

### 3.3 Compatibilidad con comparación constante
- La capacidad de sugerir fragmentos similares (para revisar consistencia o refinar códigos) favorece el método de comparación constante.

---

## 4) Evaluación crítica: riesgos y amenazas a la validez

### 4.1 Riesgo 1 — Proceduralización de la interpretación
Si la bandeja crece, la validación puede degenerar en una tarea de “triage” rápida:
- **Amenaza:** se valida por velocidad, no por reflexión.
- **Efecto:** inflaciona códigos, reduce densidad conceptual, y retrasa axial/selectiva.

**Recomendación doctoral:** diseñar explícitamente un **protocolo de validación** (ver Sección 6) y medir su adherencia.

### 4.2 Riesgo 2 — Sesgo de automatización
Cuando la UI presenta un candidato con “score” o con el sello de “IA”, el usuario tiende a sobreconfiar.
- **Amenaza:** confirmabilidad baja; se aprueba por autoridad percibida.
- **Mitigación:** hacer visible la incertidumbre y forzar acceso a evidencia/contexto antes de validar.

### 4.3 Riesgo 3 — Deriva terminológica y proliferación de sinónimos
En codificación abierta, es natural generar variantes. El sistema puede amplificarlo si no guía fusiones:
- **Amenaza:** el “vocabulario” de códigos deriva y dificulta axialidad.
- **Señal:** aumento sostenido de códigos nuevos sin aumento de cobertura/insight.

### 4.4 Riesgo 4 — Pérdida de densidad analítica (múltiples incidencias por fragmento)
Si el esquema/UX trata el par (fragmento, código) como un único registro, se puede perder:
- Varias citas o matices para el mismo código sobre el mismo fragmento.
- La diferenciación entre “aplicación” del código y “memo interpretativo”.

**Mitigación:** asegurar que la UI permita capturar memo/justificación por decisión, y que no “aplane” múltiples evidencias.

### 4.5 Riesgo 5 — Contaminación entre proyectos (contexto de grafo)
**Estado hoy (verificado 2025-12-24):** riesgo parcialmente mitigado.
- En GraphRAG, la extracción de subgrafo filtra fragmentos por `f.project_id`.
- En Link Prediction, la extracción de aristas filtra por `a.project_id`.

**Lo que aún puede requerir endurecimiento:** asegurar que *todos* los nodos/relaciones usados para contexto (categorías/códigos relacionados) queden aislados por proyecto, especialmente cuando se expanden relaciones más allá del fragmento.

**Impacto:** si existiera mezcla residual, sería una amenaza directa a validez interna y confirmabilidad.

**Decisión de desarrollo:** mantener este punto como requisito de calidad, pero ya no como “riesgo activo sin mitigación”.

---

## 5) Oportunidades de mejora UX/UI (orientadas a rigor, no a “más features”)

### 5.1 Objetivo UX
Reducir fricción sin reducir rigor: la UI debe hacer **fácil** validar bien, y **difícil** validar mal.

### 5.2 Bandeja de candidatos: información mínima para decisión de calidad
Para cada candidato, mostrar en la tarjeta o panel:
- Cita (≤60 palabras) + enlace a “ver en contexto”.
- Contexto del fragmento (anterior/siguiente o párrafo completo).
- Metadatos básicos: archivo, `par_idx`, hablante.
- Origen: `manual` / `llm` / `discovery` / `semantic_suggestion`.
- Campo de memo de decisión (corto, opcional pero recomendado).

### 5.3 Antisesgo: visibilizar incertidumbre sin sobrecargar
- Mostrar score como **señal** (no como recomendación “aprobada”).
- Etiquetas claras: “Sugerido por IA” ≠ “Validado”.

### 5.4 Consistencia: “definición operacional viva” del código
Al validar un candidato para un código existente:
- Mostrar 2–3 citas validadas previas (ejemplos canónicos).
- Mostrar códigos “cercanos” (posibles sinónimos) para sugerir fusión.

### 5.5 Priorización para evitar backlog infinito
- Vista por “código” (agrupa pendientes por etiqueta) y por “archivo”.
- Indicadores de deuda: pendientes por origen y antigüedad.

---

## 6) Oportunidades de mejora investigativa (protocolo, métricas, rigor)

### 6.1 Protocolo explícito de validación (recomendación doctoral)
Definir reglas operativas:
- ¿Cuándo es un código nuevo vs sinónimo?
- ¿Cuándo fusionar?
- ¿Qué evidencia mínima se exige para validar? (p.ej., cita + contexto concordante)
- ¿Qué hacer ante citas que no matchean fragmento? (regla de corrección o rechazo)

Este protocolo debe quedar documentado como apéndice metodológico del proyecto.

### 6.2 Fiabilidad (intra/inter-codificador)
- Muestreo de N fragmentos para doble validación (ciega si es posible).
- Medir acuerdo (aunque sea simple: % acuerdo por código / por decisión validar-rechazar).

### 6.3 Saturación: usarla como regla de decisión
La curva de saturación debe convertirse en un “gate”:
- Si la mayoría de nuevos candidatos son sinónimos o baja novedad, priorizar fusión/densificación.
- Incorporar muestreo teórico: búsqueda deliberada de casos negativos.

### 6.4 Confirmabilidad y auditoría
- Registrar memos de decisión (por rechazo/fusión/validación compleja).
- Mantener rastro de cambios del vocabulario (historial de código, fusiones).

---

## 7) Priorización propuesta (impacto alto / costo bajo)

1. **Bandeja de validación centrada en evidencia** (cita + contexto + ejemplos canónicos + origen).
2. **Protocolo de decisión** (documentado, simple, aplicable por todo el equipo).
3. **Métricas de calidad**:
   - tasa de corrección de citas,
   - tiempo a resolución de pendientes,
   - tasa de fusión vs creación,
   - fiabilidad en muestra.
4. **Aislamiento estricto por proyecto** en consultas de grafo/contexto.

---

## 8) Verificación contra código real (alineación y gaps)

Esta sección existe para que el documento sirva como base de decisiones de desarrollo (qué ya está, qué falta y qué es parcial).

### 8.1 Afirmaciones validadas (✅)

- **Promoción mueve solo `validado`:** correcto. La promoción a definitivos selecciona candidatos con `estado='validado'` y `fragmento_id` no nulo.
- **Bandeja lista por fecha:** correcto en backend. El listado ordena por `created_at DESC` (lo “más reciente primero”).

### 8.2 Afirmaciones parcialmente ciertas (⚠️)

- **Memo de decisión por rechazo/fusión:**
   - Rechazo: existe y la UI lo solicita (prompt) como memo opcional.
   - Fusión: el modelo soporta `fusionado_a` y auditoría básica (quién/cuándo), pero la UX no fuerza/recoge un memo de fusión consistente.
- **Aislamiento por proyecto:** mitigación aplicada en consultas centrales; mantener como requisito de calidad y revisar expansión de contexto cuando se navegan relaciones más profundas.

### 8.3 No implementado (❌)

- **Ejemplos canónicos al validar (2–3 citas previas del mismo código):** no existe en la UI actual.
- **Códigos “cercanos” / sinónimos sugeridos en la validación:** no existe como función explícita en el panel.
- **Alertas/gates si backlog crece N días:** no existe.
- **Fiabilidad inter-codificador (doble validación ciega):** no existe.

### 8.4 Implicación para roadmap

- El documento ya no asume que “todo está roto”: distingue entre **ya resuelto**, **parcial** y **pendiente**, para priorizar sin re-trabajo.

### 8.5 Auditoría sistemática del aislamiento por `project_id` (Cypher/SQL)

**Objetivo:** confirmar si el aislamiento por proyecto es **completo** (no solo en GraphRAG/LinkPrediction) y dejar una lista cerrada de “lugares a endurecer”.

**Cómo se auditó (2025-12-24):** barrido por módulos con queries a Neo4j/PostgreSQL/Qdrant buscando patrones `MATCH (...)`, `session.run(...)`, `FROM ...`, `WHERE project_id ...` y uso de filtros Qdrant.

#### 8.5.1 Resultado ejecutivo

- **Conclusión:** el aislamiento **no es completo todavía**.
- **Motivo:** hay rutas que siguen operando en modo “grafo global” o con claves de MERGE/constraints no compuestas (por nombre sin `project_id`), lo que permite colisiones y contaminación entre proyectos aunque algunas consultas recientes ya filtren por proyecto.

#### 8.5.2 Superficies donde el aislamiento sí está aplicado (✅)

- **Qdrant + BM25 (búsqueda híbrida):** `app/queries.py` construye filtro obligatorio `project_id` en Qdrant y filtra `project_id` en SQL BM25.
- **Conteos por grafo:** `app/queries.py:graph_counts()` filtra Entrevista/Fragmento por `project_id`.
- **Transversal/validación/reporting (varios):** `app/transversal.py`, `app/validation.py`, `app/reporting.py` incluyen `project_id` en sus queries principales.

#### 8.5.3 Lugares a endurecer (lista cerrada)

**P0 (bloqueante si se trabaja multi-proyecto real):**

1) **Neo4j: constraints y claves de MERGE no compuestas**
   - Archivo: `app/neo4j_block.py`
   - Hallazgo:
     - `ensure_constraints()` crea unicidad global por `Entrevista.nombre` y `Fragmento.id`.
     - `ensure_code_constraints()` y `ensure_category_constraints()` crean unicidad global por `Codigo.nombre` y `Categoria.nombre`.
     - `merge_fragments()` hace `MERGE (e:Entrevista {nombre: r.archivo})` (sin `project_id`).
     - `merge_fragment_code()` / `merge_category_code_relationship()` hacen `MERGE` por `nombre` sin `project_id`.
   - Riesgo: colisión entre proyectos (mismo nombre de entrevista/código/categoría) y contaminación estructural del grafo.
   - Endurecimiento esperado:
     - Constraints **compuestas** por `(nombre, project_id)` donde aplique.
     - `MERGE` por claves compuestas (ej. `MERGE (c:Codigo {nombre:$codigo, project_id:$project_id})`).

2) **GDS / análisis de grafo sin filtro por proyecto (mezcla inter-proyecto)**
   - Archivo: `app/axial.py`
   - Hallazgo:
     - Fallback nativo: `MATCH (s)-[:REL]->(t)` sin `project_id`.
     - Proyección GDS: `gds.graph.project(... ['Categoria','Codigo'], {REL: {type: 'REL'}})` sin filtro por `project_id`.
   - Riesgo: centralidad/comunidades calculadas con un grafo “global” (mezcla proyectos) y, si se persiste, contamina propiedades (community/score) usadas después.
   - Endurecimiento esperado:
     - Proyección por proyecto (proyección Cypher con `WHERE n.project_id = $project_id` + relaciones filtradas por `project_id`).
     - Asegurar que cualquier persistencia de propiedades sea por proyecto.

3) **Contexto “global” para LLM sin `project_id`**
   - Archivo: `app/analysis.py` (`get_graph_context()`)
   - Hallazgo: consulta `MATCH (n:Codigo) WHERE ...` sin filtrar por proyecto.
   - Riesgo: el “contexto global” puede inyectar conceptos/códigos de otros proyectos → amenaza a validez interna.
   - Endurecimiento esperado: aceptar `project_id` y filtrar todos los MATCH por proyecto.

4) **Actualización de metadatos sin `project_id` (Postgres + Neo4j)**
   - Archivo: `app/metadata_ops.py`
   - Hallazgo:
     - `_ensure_fragment_ids()` consulta por `id` o por `archivo` sin `project_id`.
     - `_update_postgres()` hace `UPDATE ... WHERE id = ANY(%s)` sin `project_id`.
     - `_update_neo4j()` hace `MATCH (e:Entrevista {nombre:$archivo})` y actualiza fragmentos sin `project_id`.
   - Riesgo: actualizaciones cruzadas entre proyectos cuando hay colisión de `archivo` o `id`.
   - Endurecimiento esperado:
     - Requerir `project_id` en el plan/entry o derivarlo del contexto.
     - Incluir `project_id` en `WHERE`/`MATCH` en Postgres y Neo4j.

**P1 (importante, reduce riesgo residual):**

5) **GraphRAG filtra fragmentos pero no endurece expansión de contexto por proyecto**
   - Archivo: `app/graphrag.py`
   - Hallazgo: filtra `f.project_id = $project_id`, pero los `OPTIONAL MATCH` a `Categoria`/`Codigo` relacionados no fuerzan `project_id`.
   - Riesgo: si los nodos `Codigo/Categoria` no están estrictamente separados por proyecto (ver P0 #1), el subgrafo puede “saltar” de proyecto.
   - Endurecimiento esperado: añadir condiciones `{project_id:$project_id}` a nodos/relaciones en los OPTIONAL MATCH.

6) **Bypass de aislamiento mediante `project_id='default'`**
   - Archivo: `app/reports.py` (`identify_nucleus_candidates()`)
   - Hallazgo: `WHERE c.project_id = $project_id OR $project_id = 'default'`.
   - Riesgo: ejecutar con `default` puede mezclar categorías/códigos de múltiples proyectos.
   - Endurecimiento esperado: restringir/retirar el bypass o hacerlo explícitamente “modo admin global”.

7) **Ejecución de Cypher arbitrario (sin guardrails de `project_id`)**
   - Archivo: `app/queries.py` (`run_cypher()`)
   - Hallazgo: ejecuta el Cypher que se le pasa sin inyección/validación de `project_id`.
   - Riesgo: un usuario (o bug en UI) puede consultar/modificar datos fuera de su proyecto.
   - Endurecimiento esperado: endpoint/admin-only, o wrapper que exija `project_id` y bloquee patrones peligrosos.

8) **Qdrant: wrapper no fuerza filtro por proyecto**
   - Archivo: `app/qdrant_block.py`
   - Hallazgo: `search_similar()`/`discover_search()` aceptan `**kwargs` y no obligan `Filter` con `project_id`.
   - Riesgo: si algún caller olvida el filtro, aparecen resultados cross-proyecto.
   - Endurecimiento esperado: wrappers de “alto nivel” que requieran `project_id` o validen que el filtro existe.

**P2 (calidad/consistencia de métricas):**

9) **Métrica Postgres potencialmente global**
   - Archivo: `app/postgres_block.py` (`coding_stats()`)
   - Hallazgo: `SELECT COUNT(*) FROM analisis_axial` sin `project_id`.
   - Riesgo: reporta relaciones axiales globales en un dashboard por proyecto.
   - Endurecimiento esperado: filtrar por `project_id` (o etiquetar explícitamente como global).

#### 8.5.4 Checklist de regresión (para declarar “aislamiento completo”)

- Crear 2 proyectos (`P1`, `P2`) con:
  - mismo `archivo` (nombre de entrevista) en ambos,
  - mismo `codigo` y `categoria` (mismo nombre) en ambos,
  - al menos 2 fragmentos por archivo.
- Verificar:
  - GraphRAG devuelve solo nodos/relaciones del proyecto activo.
  - Link Prediction no sugiere enlaces usando evidencia del otro proyecto.
  - GDS/centralidad/comunidades se calculan sin influencia del otro proyecto.
  - Metadata Ops solo actualiza fragmentos del proyecto activo.
  - Ningún endpoint “admin” (run_cypher / modo default) está expuesto a usuarios normales.

---

## 9) Preguntas de investigación sugeridas (para robustecer tesis/artículo)

- ¿Cómo cambia la densidad conceptual (axialidad) cuando se introduce un filtro híbrido vs codificación manual directa?
- ¿Qué patrones de sesgo aparecen al presentar score/origen IA en la UI?
- ¿En qué medida la comparación constante asistida reduce el tiempo a saturación sin reducir confirmabilidad?

---

## 10) Anexo: Checklist operativo para sesiones de validación (mapeado a la UI actual)

- [ ] Revisión rápida de pendientes por antigüedad (evitar backlog eterno).
- [ ] Para cada candidato: verificar concordancia cita–fragmento.
- [ ] Si el código existe: comparar con ejemplos canónicos.
- [ ] Si hay sinónimo probable: fusionar y anotar memo.
- [ ] Registrar decisiones “difíciles” (memos cortos).
- [ ] Cerrar sesión con una mini-síntesis (1–3 bullets) de patrones emergentes.

### Mapeo práctico (UI actual)

- **Revisión de pendientes por antigüedad:** usar el filtro “Estado: Pendiente”. El backend ya entrega ordenado por `created_at DESC` (reciente primero). Si quieres “más antiguos primero”, hoy no hay control explícito de sorting en UI.
- **Validar:** botón “Validar” en cada fila (o “Validación por lote” si se seleccionan varios, según UI).
- **Rechazar con memo:** botón “Rechazar” abre prompt de memo opcional.
- **Fusionar:** seleccionar ≥2 candidatos → abrir fusión → definir `mergeTarget` (código destino) → confirmar.
- **Promover a definitivos:** botón de promover toma candidatos visibles con `estado=validado` y llama a “promote”.
- **“Verificar concordancia cita–fragmento” en UI:** hoy depende de que el panel muestre suficiente contexto; si solo muestra cita corta, esta acción requiere navegar a contexto en otra vista (gap UX).
