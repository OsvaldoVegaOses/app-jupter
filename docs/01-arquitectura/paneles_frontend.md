# Documentación de Paneles Frontend

Este documento describe todos los componentes frontend de la aplicación siguiendo el estándar de detalle del CodingPanel.

**Última actualización:** 2025-12-29

---

## Tabla de Contenidos

1. [IngestionPanel - Ingesta de documentos](#1-ingestionpanel---ingesta-de-documentos)
2. [FamiliarizationPanel - Revisión de fragmentos](#2-familiarizationpanel---revisión-de-fragmentos)
3. [AnalysisPanel - Análisis LLM](#3-analysispanel---análisis-llm)
4. [CodingPanel - Codificación](#4-codingpanel---codificación)
5. [Neo4jExplorer - Explorador de grafos](#5-neo4jexplorer---explorador-de-grafos)
6. [GraphRAGPanel - Chat con grafo](#6-graphragpanel---chat-con-grafo)
7. [DiscoveryPanel - Búsqueda exploratoria](#7-discoverypanel---búsqueda-exploratoria)
8. [LinkPredictionPanel - Predicción de enlaces](#8-linkpredictionpanel---predicción-de-enlaces)
9. [ReportsPanel - Informes](#9-reportspanel---informes)
10. [CodeValidationPanel - Validación de códigos](#10-codevalidationpanel---validación-de-códigos)

---

## 1. IngestionPanel - Ingesta de documentos

**Archivo:** `frontend/src/components/IngestionPanel.tsx` (312 líneas)

### Descripción
Panel de Etapa 1 que permite ingestar documentos DOCX al sistema.

### Componentes UI

| Componente | Líneas | Función |
|------------|--------|---------|
| Textarea (entradas) | 154-164 | Rutas/patrones de archivos (una por línea) |
| Input metadata JSON | 166-175 | Ruta opcional a archivo de metadatos |
| Input run_id | 177-186 | Identificador de ejecución |
| Fieldset fragmentación | 188-220 | batch_size, min_chars, max_chars |
| Button "Ejecutar ingesta" | 222-224 | Inicia el proceso |

### Funciones Principales

| Función | Líneas | Propósito |
|---------|--------|-----------|
| `parseInputs()` | 34-39 | Parsea textarea a array de rutas |
| `defaultRunId()` | 41-46 | Genera UUID para run_id |
| `handleSubmit()` | 66-129 | Envía POST `/api/ingest` y hace polling |

### Endpoints Backend

| Método | Endpoint | Líneas que lo llaman | Archivo lógica |
|--------|----------|---------------------|----------------|
| POST | `/api/ingest` | 84-87 | `app/ingestion.py` |
| GET | `/api/status?project=...` | 107 | `app/project_state.py` |

### Flujo de Datos

```
┌────────────────────────────────────────────────────────┐
│  Usuario ingresa rutas DOCX + parámetros               │
└─────────────────────────┬──────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────┐
│  handleSubmit() → POST /api/ingest                     │
│  payload: { project, inputs[], batch_size, ... }       │
└─────────────────────────┬──────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────┐
│  Backend procesa DOCX → PostgreSQL + Qdrant + Neo4j    │
└─────────────────────────┬──────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────┐
│  Polling /api/status hasta ingesta.completed = true    │
└────────────────────────────────────────────────────────┘
```

---

## 2. FamiliarizationPanel - Revisión de fragmentos

**Archivo:** `frontend/src/components/FamiliarizationPanel.tsx` (441 líneas)

### Descripción
Panel de Etapa 2 para revisar fragmentos transcritos antes de codificación.

### Componentes UI

| Componente | Líneas | Función |
|------------|--------|---------|
| Select archivo | ~120-145 | Filtrar por entrevista |
| Tabla fragmentos | ~200-350 | Lista fragmentos con speaker, texto, chars |
| Botones expandir/colapsar | 81-87 | Control de acordeones |
| Botón "Eliminar datos" | 89-115 | Borrar archivo seleccionado |

### Funciones Principales

| Función | Líneas | Propósito |
|---------|--------|-----------|
| `toggleFragment()` | 69-79 | Expande/colapsa fragmento |
| `expandAll()` | 81-83 | Expande todos |
| `collapseAll()` | 85-87 | Colapsa todos |
| `handleDeleteFile()` | 89-115 | Elimina datos de archivo |

### Endpoints Backend

| Método | Endpoint | Propósito |
|--------|----------|-----------|
| GET | `/api/fragments?project=...&limit=...` | Lista fragmentos |
| DELETE | `/api/maintenance/delete-file` | Elimina archivo |

### Interfaces TypeScript

```typescript
interface FragmentInfo {
  id: string;
  text: string;
  speaker: string;
  archivo: string;
  fragmento_idx: number;
  char_count: number;
  interviewee_tokens: number;
  interviewer_tokens: number;
}
```

---

## 3. AnalysisPanel - Análisis LLM

**Archivo:** `frontend/src/components/AnalysisPanel.tsx` (429 líneas)

### Descripción
Panel que ejecuta análisis LLM sobre entrevistas para generar códigos iniciales.

### Componentes UI

| Componente | Líneas | Función |
|------------|--------|---------|
| Select entrevista | ~240-270 | Selecciona archivo a analizar |
| Botón "Ejecutar Análisis" | ~275-285 | Inicia proceso |
| Botón "Eliminar Datos" | 83-112 | Limpia datos de archivo |
| Tabla códigos | ~320-400 | Muestra códigos generados |

### Funciones Principales

| Función | Líneas | Propósito |
|---------|--------|-----------|
| `loadInterviews()` | 55-70 | Carga lista de entrevistas |
| `handleDeleteFile()` | 83-112 | Elimina datos |
| `handleAnalyze()` | 114-201 | Ejecuta análisis con polling |
| `handleSave()` | 203-222 | Persiste códigos |
| `handleDeleteRow()` | 224-238 | Elimina código de tabla |

### Endpoints Backend

| Método | Endpoint | Líneas | Archivo lógica |
|--------|----------|--------|----------------|
| GET | `/api/interviews` | 60 | `backend/app.py` |
| POST | `/api/analyze` | 133 | `app/analysis.py` |
| GET | `/api/tasks/{task_id}` | 162 | Celery |

### Flujo de Datos

```
┌──────────────────────────────────────────────────────┐
│  Seleccionar entrevista → "Ejecutar Análisis"        │
└───────────────────────────┬──────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────┐
│  POST /api/analyze → Celery task_id                  │
└───────────────────────────┬──────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────┐
│  poll() → GET /api/tasks/{task_id}                   │
│  while status == "PROGRESS"                          │
└───────────────────────────┬──────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────┐
│  Display: códigos, citas, modelo ASCII               │
└──────────────────────────────────────────────────────┘
```

---

## 4. CodingPanel - Codificación

**Archivo:** `frontend/src/components/CodingPanel.tsx` (1854 líneas)

### Descripción
Panel principal de Etapa 3 con 4 pestañas para codificación manual y asistida.

### Pestañas (Tabs)

```typescript
const tabs = [
  { key: "assign", label: "📝 Asignar código" },
  { key: "suggest", label: "🔍 Sugerencias semánticas" },
  { key: "insights", label: "📊 Cobertura y avance" },
  { key: "citations", label: "📎 Citas por código" }
];
```

### 4.1 Tab "Asignar código"

| Componente | Líneas | Función |
|------------|--------|---------|
| Input código | ~400-420 | Nombre del código |
| Textarea cita | ~425-445 | Cita justificativa |
| Select fragmento | ~450-480 | Fragmento a codificar |
| Botón asignar | ~490-510 | `handleAssign()` |

### 4.2 Tab "Sugerencias semánticas"

| Componente | Líneas | Función |
|------------|--------|---------|
| Dropdown "Entrevista activa" | 862-912 | Filtro por archivo |
| Input fragmento semilla | 1021-1032 | fragment_id base |
| Botón "Buscar sugerencias" | ~1040 | `handleSuggest()` |
| Tabla resultados | 1294-1325 | Score, fragmento, archivo |
| Botón "Generar Sugerencia IA" | 651-691 | LLM code suggestion |

### 4.3 Tab "Cobertura y avance"

| Componente | Función |
|------------|---------|
| Métricas | % fragmentos codificados |
| Gráfico | Distribución por entrevista |

### 4.4 Tab "Citas por código"

| Componente | Función |
|------------|---------|
| Select código | Lista códigos existentes |
| Tabla citas | Fragmentos asociados al código |

### Funciones Principales

| Función | Líneas | Propósito |
|---------|--------|-----------|
| `handleSuggest()` | 554-593 | POST `/api/coding/suggest` |
| `handleAssign()` | ~280-330 | POST `/api/coding/assign` |
| `handleUnassign()` | ~340-380 | DELETE código de fragmento |

### Endpoints Backend

| Método | Endpoint | Archivo lógica |
|--------|----------|----------------|
| POST | `/api/coding/suggest` | `app/coding.py:suggest_similar_fragments()` |
| POST | `/api/coding/assign` | `app/coding.py:assign_code()` |
| POST | `/api/coding/suggest-code` | `app/coding.py` + LLM |
| GET | `/api/coding/stats` | `app/coding.py:get_coding_stats()` |
| GET | `/api/coding/citations` | `app/coding.py:get_citations()` |

### Base de Datos

**Qdrant (`app/qdrant_block.py`):**

| Función | Líneas | Propósito |
|---------|--------|-----------|
| `search_similar()` | 179-250 | KNN con aislamiento por proyecto |
| `search_similar_grouped()` | 311-460 | Búsqueda con agrupación |

---

## 5. Neo4jExplorer - Explorador de grafos

**Archivo:** `frontend/src/components/Neo4jExplorer.tsx` (638 líneas)

### Descripción
Permite ejecutar consultas Cypher y visualizar grafos interactivos.

### Componentes UI

| Componente | Líneas | Función |
|------------|--------|---------|
| Textarea Cypher | ~560-580 | Query editor |
| Checkboxes formato | ~585-600 | raw/table/graph |
| Input params JSON | ~600-615 | Parámetros Cypher |
| ResponseTabs | 75-129 | Vista de resultados |
| GraphView | 195-448 | Visualización D3.js |
| TableView | 135-168 | Vista tabular |

### Funciones Principales

| Función | Líneas | Propósito |
|---------|--------|-----------|
| `handleSubmit()` | 484-517 | Ejecuta query |
| `handleExport()` | 519-549 | Exporta CSV/JSON |
| `handleToggleFormat()` | 477-482 | Cambia formato vista |
| `handleNodeClick()` | 281-303 | Click en nodo → citas |

### Endpoints Backend

| Método | Endpoint | Archivo lógica |
|--------|----------|----------------|
| POST | `/api/neo4j/query` | `app/queries.py:run_cypher()` |
| POST | `/api/neo4j/export` | `backend/app.py` |

### Visualización D3.js

```typescript
interface ForceNode {
  id: string;
  name: string;
  group: string;  // Categoria | Codigo
  raw: Neo4jGraph["nodes"][number];
}

interface ForceLink {
  source: string;
  target: string;
  name: string;  // tipo relación
}
```

---

## 6. GraphRAGPanel - Chat con grafo

**Archivo:** `frontend/src/components/GraphRAGPanel.tsx` (326 líneas)

### Descripción
Chat que combina búsqueda semántica + contexto de grafo Neo4j + LLM.

### Componentes UI

| Componente | Función |
|------------|---------|
| Textarea pregunta | Input del usuario |
| Checkbox "Chain of Thought" | Activa razonamiento paso a paso |
| Botón "Preguntar" | Ejecuta consulta |
| Botón "Guardar Informe" | Persiste resultado |
| Panel contexto | Subgrafo extraído |
| Panel fragmentos | Evidencia de Qdrant |

### Funciones Principales

| Función | Propósito |
|---------|-----------|
| `handleQuery()` | POST `/api/graphrag/query` |
| `handleSaveReport()` | POST `/api/graphrag/save_report` |

### Endpoints Backend

| Método | Endpoint | Archivo lógica |
|--------|----------|----------------|
| POST | `/api/graphrag/query` | `app/graphrag.py:graphrag_query()` |
| POST | `/api/graphrag/save_report` | `app/graphrag.py` |

### Modos de Consulta

| Modo | Descripción |
|------|-------------|
| Normal | Respuesta directa del LLM |
| Chain of Thought | 5 secciones estructuradas |

---

## 7. DiscoveryPanel - Búsqueda exploratoria

**Archivo:** `frontend/src/components/DiscoveryPanel.tsx` (528 líneas)

### Descripción
Búsqueda con triplete positivo/negativo/target usando Qdrant Discovery API.

### Componentes UI

| Componente | Función |
|------------|---------|
| Textarea positivos | Conceptos a buscar (uno por línea) |
| Textarea negativos | Conceptos a evitar |
| Input target | Texto objetivo |
| Slider top_k | Cantidad de resultados |
| Tabla fragmentos | Resultados con score |
| Botón "Guardar Memo" | Persiste exploración |
| Botón "Enviar a Coding" | Por fragmento |

### Funciones Principales

| Función | Propósito |
|---------|-----------|
| `handleSearch()` | POST `/api/search/discover` |
| `handleSaveMemo()` | POST `/api/discovery/save_memo` |
| `handleAnalyze()` | POST `/api/discovery/analyze` |

### Endpoints Backend

| Método | Endpoint | Archivo lógica |
|--------|----------|----------------|
| POST | `/api/search/discover` | `app/queries.py:discover_search()` |
| POST | `/api/discovery/save_memo` | `backend/app.py` |
| POST | `/api/discovery/analyze` | `app/discovery.py` |

### Algoritmo Discovery

```
positive_embeddings = avg(embed(positive_texts))
negative_embeddings = avg(embed(negative_texts))
query_vector = positive - 0.3 * negative + 0.7 * target
```

---

## 8. LinkPredictionPanel - Predicción de enlaces

**Archivo:** `frontend/src/components/LinkPredictionPanel.tsx` (600 líneas)

### Descripción
Sugiere relaciones axiales faltantes usando algoritmos de predicción.

### Algoritmos Disponibles

| Algoritmo | Descripción |
|-----------|-------------|
| `common_neighbors` | Vecinos compartidos |
| `jaccard` | Coeficiente de similitud normalizado |
| `adamic_adar` | Pondera por rareza de vecinos |
| `preferential_attachment` | Nodos populares se conectan |

### Componentes UI

| Componente | Función |
|------------|---------|
| Select algoritmo | Elige método de predicción |
| Input categoría | Filtro opcional |
| Slider top_k | Cantidad de sugerencias |
| Tabla sugerencias | source, target, score |
| Botón "Confirmar" | Crear relación en Neo4j |
| Botón "Analizar con IA" | LLM valida predicción |

### Funciones Principales

| Función | Propósito |
|---------|-----------|
| `handlePredict()` | GET `/api/axial/predict` |
| `handleCommunityLinks()` | GET `/api/axial/community-links` |
| `handleAnalyze()` | POST `/api/link-prediction/analyze` |
| `handleConfirm()` | POST `/api/axial/confirm-relationship` |

### Endpoints Backend

| Método | Endpoint | Archivo lógica |
|--------|----------|----------------|
| GET | `/api/axial/predict` | `app/link_prediction.py:suggest_links()` |
| GET | `/api/axial/community-links` | `app/link_prediction.py` |
| GET | `/api/axial/hidden-relationships` | `app/link_prediction.py:discover_hidden_relationships()` |
| POST | `/api/axial/confirm-relationship` | `app/link_prediction.py:confirm_hidden_relationship()` |

---

## 9. ReportsPanel - Informes

**Archivo:** `frontend/src/components/ReportsPanel.tsx` (787 líneas)

### Descripción
Muestra informes de análisis por entrevista y resumen de Etapa 4.

### Componentes UI

| Componente | Función |
|------------|---------|
| Lista entrevistas | Cards con métricas |
| Matriz comparativa | Códigos × Entrevistas |
| Indicador saturación | Progreso hacia saturación teórica |
| Resumen Etapa 4 | Candidatos a núcleo |
| Botón exportar | Markdown/JSON |

### Funciones Principales

| Función | Líneas | Propósito |
|---------|--------|-----------|
| `getSaturationColor()` | 92-99 | Color por nivel saturación |
| `getSaturationLabel()` | 101-108 | Etiqueta texto |
| `formatDate()` | 110-118 | Formato fecha ISO |
| `exportToMarkdown()` | 120-146 | Genera MD exportable |

### Endpoints Backend

| Método | Endpoint | Propósito |
|--------|----------|-----------|
| GET | `/api/reports/interviews` | Lista informes |
| GET | `/api/reports/stage4-summary` | Resumen Etapa 4 |
| GET | `/api/reports/matrix` | Matriz códigos × archivos |

### Interfaces TypeScript

```typescript
interface InterviewReport {
  archivo: string;
  codigos_generados: string[];
  codigos_nuevos: number;
  codigos_reutilizados: number;
  tasa_cobertura: number;
  aporte_novedad: number;
  contribucion_saturacion: string;  // "alto" | "medio" | "bajo"
}

interface Stage4Summary {
  total_codigos_unicos: number;
  total_categorias: number;
  score_saturacion: number;  // 0.0 - 1.0
  saturacion_alcanzada: boolean;
  candidatos_nucleo: CandidatoNucleo[];
}
```

---

## 10. CodeValidationPanel - Validación de códigos

**Archivo:** `frontend/src/components/CodeValidationPanel.tsx` (829 líneas)

### Descripción
Workflow híbrido para validar, rechazar o fusionar códigos candidatos.

### Fuentes de Códigos

| Fuente | Icono | Descripción |
|--------|-------|-------------|
| `llm` | 🤖 | Generados por análisis LLM |
| `manual` | 📝 | Creados manualmente |
| `discovery` | 🔍 | Desde Discovery Panel |
| `semantic_suggestion` | 💡 | Sugerencias semánticas |
| `legacy` | 📦 | Importados |

### Estados de Códigos

| Estado | Icono | Color |
|--------|-------|-------|
| `pendiente` | ⏳ | Amarillo |
| `validado` | ✅ | Verde |
| `rechazado` | ❌ | Rojo |
| `fusionado` | 🔗 | Púrpura |

### Componentes UI

| Componente | Función |
|------------|---------|
| Filtros estado/fuente | Filtrar candidatos |
| Tabla candidatos | Lista con checkboxes |
| Botones batch | Validar/rechazar múltiples |
| Modal fusión | Consolidar códigos similares |
| Modal ejemplos | Ver citas canónicas |
| Detector duplicados | Post-hoc Levenshtein |

### Funciones Principales

| Función | Líneas | Propósito |
|---------|--------|-----------|
| `handleValidate()` | 155-163 | Valida un código |
| `handleReject()` | 165-174 | Rechaza un código |
| `handleBatchValidate()` | 176-187 | Validación masiva |
| `handleBatchReject()` | 189-201 | Rechazo masivo |
| `handleMerge()` | 203-217 | Fusiona códigos |
| `handlePromote()` | 219-234 | Promueve a código definitivo |
| `handleShowExamples()` | 236-250 | Modal citas canónicas |
| `handleOpenMerge()` | 252-270 | Carga similares para fusión |
| `handleDetectDuplicates()` | 272-286 | Detecta duplicados post-hoc |

### Endpoints Backend

| Método | Endpoint | Archivo lógica |
|--------|----------|----------------|
| GET | `/api/coding/candidates` | `app/postgres_block.py:list_candidate_codes()` |
| GET | `/api/coding/candidates/stats` | `app/postgres_block.py` |
| POST | `/api/coding/candidates/{id}/validate` | `app/postgres_block.py:validate_candidate()` |
| POST | `/api/coding/candidates/{id}/reject` | `app/postgres_block.py:reject_candidate()` |
| POST | `/api/coding/candidates/merge` | `app/postgres_block.py:merge_candidates()` |
| POST | `/api/coding/candidates/promote` | `app/postgres_block.py:promote_candidate()` |
| GET | `/api/coding/duplicates` | `app/code_normalization.py` |
| GET | `/api/coding/backlog-health` | `app/postgres_block.py:get_backlog_health()` |

### Flujo de Validación

```
┌────────────────────────────────────────────────────────────┐
│  Códigos de múltiples fuentes → tabla codigo_candidatos   │
└───────────────────────────┬────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────┐
│  Investigador revisa:                                      │
│  ✅ Validar → estado = 'validado'                          │
│  ❌ Rechazar → estado = 'rechazado'                        │
│  🔗 Fusionar → múltiples → uno + estado = 'fusionado'      │
└───────────────────────────┬────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────┐
│  Promover → Crear en analisis_codigos_abiertos + Neo4j     │
└────────────────────────────────────────────────────────────┘
```

---

## 11. Funciones de IA Transversales

Esta sección documenta las funciones similares al **"💡 Generar Sugerencia IA"** de CodingPanel que existen en otros paneles.

### Tabla Comparativa

| Panel | Botón | Función | Líneas | Endpoint |
|-------|-------|---------|--------|----------|
| **CodingPanel** | `💡 Generar Sugerencia IA` | `handleGenerateActionSuggestion()` | 651-691 | `POST /api/coding/suggest-code` |
| **LinkPredictionPanel** | `🤖 Analizar con IA` | `handleAIAnalysis()` | 100-114 | `analyzePredictions()` |
| **DiscoveryPanel** | `🤖 Sintetizar con IA` | `handleAIAnalysis()` | 67-104 | `analyzeDiscovery()` |
| **AnalysisPanel** | `Ejecutar Análisis` | `handleAnalyze()` | 114-201 | `POST /api/analyze` |
| **GraphRAGPanel** | `Preguntar` | `handleQuery()` | ~50-100 | `POST /api/graphrag/query` |

### Comparación de Inputs/Outputs

| Panel | Input | Output | Persistencia |
|-------|-------|--------|--------------|
| **CodingPanel** | Fragmentos seleccionados | Código + memo + confianza | Bandeja candidatos |
| **LinkPredictionPanel** | Sugerencias de enlaces | Análisis cualitativo | Guarda reporte BD |
| **DiscoveryPanel** | Fragmentos encontrados | Síntesis + sugerencias | Auto-guarda memo |
| **AnalysisPanel** | Archivo entrevista completo | Códigos + categorías + memo | Celery → BD |
| **GraphRAGPanel** | Pregunta usuario | Respuesta + contexto | Guarda informe |

### 11.1 CodingPanel - Generar Sugerencia IA

**Archivo:** `CodingPanel.tsx` (líneas 651-691)

```typescript
const handleGenerateActionSuggestion = async () => {
  const selectedFragments = suggestions.filter(s => selectedSuggestionIds.has(s.fragmento_id));

  const data = await apiFetchJson<{
    suggested_code?: string;
    memo?: string;
    confidence?: "alta" | "media" | "baja" | "ninguna";
  }>("/api/coding/suggest-code", {
    method: "POST",
    body: JSON.stringify({
      project,
      fragments: selectedFragments,
      llm_model: "chat",
    }),
  });

  setActionSuggestionCode(data.suggested_code);
  setActionSuggestionMemo(data.memo);
  setActionSuggestionConfidence(data.confidence);
};
```

**Características únicas:**
- ✅ Indicador de confianza (`alta` | `media` | `baja` | `ninguna`)
- ✅ Permite seleccionar múltiples fragmentos
- ✅ Genera código + memo explicativo

---

### 11.2 LinkPredictionPanel - Analizar con IA

**Archivo:** `LinkPredictionPanel.tsx` (líneas 100-114)

```typescript
const handleAIAnalysis = useCallback(async () => {
  if (suggestions.length === 0) return;

  setAiLoading(true);
  try {
    const result = await analyzePredictions(usedAlgorithm || algorithm, suggestions, project);
    setAiAnalysis(result.analysis);
  } catch (err) {
    setAiError(err instanceof Error ? err.message : "Error en análisis IA");
  } finally {
    setAiLoading(false);
  }
}, [suggestions, usedAlgorithm, algorithm, project]);
```

**Características únicas:**
- ✅ Analiza predicciones de enlaces (no fragmentos)
- ✅ Incluye algoritmo usado en el análisis
- ✅ Permite guardar informe a BD + descarga local

---

### 11.3 DiscoveryPanel - Sintetizar con IA

**Archivo:** `DiscoveryPanel.tsx` (líneas 67-104)

```typescript
const handleAIAnalysis = useCallback(async () => {
  if (!response || response.fragments.length === 0) return;

  const positives = positiveText.split("\n").map(s => s.trim()).filter(Boolean);
  const negatives = negativeText.split("\n").map(s => s.trim()).filter(Boolean);

  const result = await analyzeDiscovery(
    positives,
    negatives,
    targetText.trim() || null,
    response.fragments,
    project
  );
  setAiAnalysis(result.analysis);

  // Auto-guardar memo con síntesis
  await saveDiscoveryMemo({
    positive_texts: positives,
    negative_texts: negatives,
    fragments: response.fragments,
    project,
    ai_synthesis: result.analysis,
  });
}, [response, positiveText, negativeText, targetText, project]);
```

**Características únicas:**
- ✅ Incluye contexto de búsqueda (positivos/negativos/target)
- ✅ Auto-guarda memo con síntesis
- ✅ Proporciona contexto de exploración al LLM

---

### 11.4 AnalysisPanel - Ejecutar Análisis

**Archivo:** `AnalysisPanel.tsx` (líneas 114-201)

```typescript
const handleAnalyze = async () => {
  // Inicia análisis asíncrono vía Celery
  const startResponse = await apiFetchJson<{ task_id?: string; status: string }>("/api/analyze", {
    method: "POST",
    body: JSON.stringify({
      project,
      file: selectedFile,
      table: true,
    }),
  });

  // Polling hasta completar
  const poll = async () => {
    const taskStatus = await apiFetchJson(`/api/tasks/${startResponse.task_id}`);
    if (taskStatus.status === "SUCCESS") {
      setAnalysisResult(taskStatus.result);
    } else if (taskStatus.status === "PROGRESS") {
      setTimeout(poll, 2000);
    }
  };
  poll();
};
```

**Características únicas:**
- ✅ Análisis completo de entrevista (no fragmentos individuales)
- ✅ Usa Celery para procesamiento asíncrono
- ✅ Genera códigos + categorías + modelo ASCII
- ✅ Polling de progreso en tiempo real

---

### 11.5 GraphRAGPanel - Preguntar con Contexto de Grafo

**Archivo:** `GraphRAGPanel.tsx` (líneas ~50-100)

```typescript
const handleQuery = async () => {
  const response = await graphragQuery({
    query: questionText,
    project,
    include_fragments: true,
    chain_of_thought: enableCoT,
  });

  setAnswer(response.answer);
  setContext(response.context);
  setFragments(response.fragments);
};
```

**Características únicas:**
- ✅ Combina Qdrant (semántica) + Neo4j (grafo) + LLM
- ✅ Modo "Chain of Thought" con 5 secciones estructuradas
- ✅ Muestra subgrafo extraído como contexto

---

### Flujo General de Funciones IA

```
┌─────────────────────────────────────────────────────────────────────┐
│  USUARIO                                                            │
│  Selecciona datos (fragmentos, predicciones, pregunta)              │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FRONTEND                                                           │
│  handleXXX() → Prepara payload con contexto                         │
│  - CodingPanel: fragmentos seleccionados                            │
│  - LinkPrediction: sugerencias + algoritmo                         │
│  - Discovery: fragmentos + conceptos pos/neg                        │
│  - GraphRAG: pregunta + flags                                       │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  BACKEND → LLM                                                      │
│  POST /api/.../analyze                                              │
│  - Construye prompt con contexto                                    │
│  - Llama a Azure OpenAI                                             │
│  - Parsea respuesta estructurada                                    │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FRONTEND                                                           │
│  Muestra resultado + Opciones de persistencia                       │
│  - Guardar reporte                                                  │
│  - Enviar a bandeja candidatos                                      │
│  - Auto-save memo                                                   │
└─────────────────────────────────────────────────────────────────────┘
```

### Interpretación de Scores (Similitud Coseno)

Después de obtener sugerencias semánticas, el score indica la similitud:

| Rango | Nivel | Interpretación |
|-------|-------|----------------|
| **0.0 - 0.5** | 🔴 Baja | Fragmentos poco relacionados |
| **0.5 - 0.7** | 🟡 Moderada | Relación conceptual parcial |
| **0.7 - 0.85** | 🟢 Buena | Alta probabilidad de relación |
| **0.85+** | 🔵 Alta | Casi idénticos semánticamente |

---

## 12. Flujo Unificado: IA → Bandeja de Candidatos (Sprint 22-24)

Esta sección documenta el patrón común de enviar códigos generados por IA directamente a la bandeja de candidatos para validación.

### Paneles con Flujo IA → Candidatos

| Panel | Botón | Origen de Códigos | Pre-check Dedup |
|-------|-------|-------------------|-----------------|
| **CodingPanel** | `✓ Enviar a Bandeja (N)` | `suggested_code` de LLM | ✅ Sí |
| **DiscoveryPanel** | `📋 Enviar N Códigos a Bandeja` | `codigos_sugeridos` de JSON | ✅ Sí |
| **GraphRAGPanel** | `📋 Enviar N Códigos a Bandeja` | Nodos tipo `Codigo` | ✅ Sí |
| **AnalysisPanel** | (Automático) | `etapa3_matriz_abierta` | ✅ Post-hoc |

### Flujo Común

```
┌──────────────────────────────────────────────────────────────────┐
│  1. CONSULTA AL LLM                                              │
│  Panel hace POST /api/.../analyze con fragmentos/pregunta        │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  2. RESPUESTA ESTRUCTURADA (JSON)                                │
│  - codigos_sugeridos: ["codigo1", "codigo2"]                     │
│  - refinamiento_busqueda: {positivos, negativos, target}         │
│  - memo_sintesis: "..."                                          │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  3. PRE-CHECK DEDUPLICACIÓN (Sprint 23)                          │
│  POST /api/codes/check-batch                                     │
│  → Compara códigos vs existentes (threshold 85%)                 │
│  → Si hay similares: Modal de confirmación                       │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  4. MODAL DEDUPLICACIÓN (si aplica)                              │
│  - Cancelar                                                       │
│  - Enviar Solo Nuevos (N)                                        │
│  - Enviar Todos (M)                                              │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  5. INSERCIÓN EN BANDEJA                                         │
│  POST /api/codes/candidates (submitCandidate)                    │
│  - fuente_origen: "discovery_ai" | "llm" | "semantic_suggestion" │
│  - score_confianza: 0.7 - 0.85                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 12.1 CodingPanel - Sugerencia IA con Envío a Bandeja

**Componentes UI (Tab "Sugerencias semánticas"):**

| Componente | Líneas | Función |
|------------|--------|---------|
| Checkboxes fragmentos | 1294-1325 | Seleccionar fragmentos similares |
| Botón "💡 Generar Sugerencia IA" | 651-691 | Genera código + memo |
| Panel "Sugerencia de Acción" | 1135-1200 | Muestra código propuesto |
| Botón "✓ Enviar a Bandeja (N)" | 1180-1195 | Envía a candidatos |

**Datos de la Sugerencia:**

```typescript
interface ActionSuggestion {
  suggested_code?: string;    // Nombre snake_case
  memo?: string;              // Descripción analítica
  confidence?: "alta" | "media" | "baja" | "ninguna";
}
```

### 12.2 DiscoveryPanel - Síntesis IA con Códigos (Sprint 22)

**Nuevas Funcionalidades:**

| Función | Líneas | Propósito |
|---------|--------|-----------|
| `handleSendCodesToTray()` | 116-149 | Pre-check y envío |
| `sendCodesDirectly()` | 150-182 | Inserta en bandeja |
| Modal deduplicación | 548-660 | UI de confirmación |

**Respuesta JSON Estructurada:**

```json
{
  "memo_sintesis": "Análisis de fragmentos...",
  "codigos_sugeridos": ["movilidad_local", "acceso_servicios"],
  "refinamiento_busqueda": {
    "positivos": ["transporte", "desplazamiento"],
    "negativos": ["automóvil particular"],
    "target": "experiencia cotidiana movilidad"
  }
}
```

### 12.3 GraphRAGPanel - Envío de Códigos del Grafo (Sprint 24)

**Nuevas Funcionalidades:**

| Función | Líneas | Propósito |
|---------|--------|-----------|
| `extractedCodes` (useMemo) | 36-45 | Filtra nodos tipo Codigo |
| `handleSendCodesToTray()` | 74-100 | Pre-check y envío |
| `sendCodesDirectly()` | 102-130 | Inserta en bandeja |
| Modal deduplicación | 272-380 | UI de confirmación |

**Extracción de Códigos:**

```typescript
const extractedCodes = useMemo(() => {
  if (!response || !response.nodes) return [];
  return response.nodes
    .filter(n => n.type === 'Codigo' || n.type === 'Code')
    .map(n => n.id)
    .filter(Boolean);
}, [response]);
```

### 12.4 AnalysisPanel - Inserción Automática (Híbrido)

**Flujo Backend (automático):**

Los códigos generados por `/api/analyze` van directamente a `codigos_candidatos`:

```python
# app/analysis.py líneas 573-596
candidates = [
    {
        "project_id": project_id,
        "codigo": row[2],
        "fuente_origen": "llm",
        "score_confianza": 0.7,
    }
    for row in open_rows
]
insert_candidate_codes(clients.postgres, candidates)
```

### Endpoint de Pre-Check (Sprint 23)

| Método | Endpoint | Archivo |
|--------|----------|---------|
| POST | `/api/codes/check-batch` | `backend/app.py` |

**Request:**
```json
{
  "project": "default",
  "codigos": ["codigo1", "codigo2"],
  "threshold": 0.85
}
```

**Response:**
```json
{
  "has_any_similar": true,
  "results": [
    {
      "codigo": "codigo1",
      "has_similar": true,
      "similar": [{"existing": "codigo_existente", "similarity": 0.92}]
    },
    {"codigo": "codigo2", "has_similar": false, "similar": []}
  ]
}
```

---

## 13. Navigation Log - Trazabilidad Muestreo Teórico (Sprint 24)

### Descripción

Registra automáticamente cada búsqueda Discovery para reconstruir el camino de exploración.

### Tabla `discovery_navigation_log`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `busqueda_id` | UUID | ID único de búsqueda |
| `busqueda_origen_id` | UUID | ID de búsqueda padre (si es refinamiento) |
| `positivos` | TEXT[] | Conceptos positivos |
| `negativos` | TEXT[] | Conceptos negativos |
| `fragments_count` | INT | Cantidad de fragmentos encontrados |
| `codigos_sugeridos` | TEXT[] | Códigos sugeridos por IA |
| `action_taken` | TEXT | "search" / "refine" / "send_codes" |

### Endpoints

| Método | Endpoint | Propósito |
|--------|----------|-----------|
| POST | `/api/discovery/log-navigation` | Registra navegación |
| GET | `/api/discovery/navigation-history` | Obtiene historial |

---

## Resumen de Líneas de Código

| Panel | Líneas | Complejidad |
|-------|--------|-------------|
| CodingPanel | 1,854 | ⭐⭐⭐⭐⭐ |
| CodeValidationPanel | 829 | ⭐⭐⭐⭐ |
| DiscoveryPanel | 811 | ⭐⭐⭐⭐ |
| ReportsPanel | 787 | ⭐⭐⭐⭐ |
| Neo4jExplorer | 638 | ⭐⭐⭐⭐ |
| LinkPredictionPanel | 600 | ⭐⭐⭐ |
| FamiliarizationPanel | 539 | ⭐⭐⭐ |
| AnalysisPanel | 429 | ⭐⭐⭐ |
| GraphRAGPanel | 520 | ⭐⭐⭐ |
| IngestionPanel | 312 | ⭐⭐ |

**Total:** ~7,319 líneas de código frontend

---

*Última actualización: 2025-12-30 (Sprint 22-24)*

