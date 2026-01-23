# Valor de Negocio: Potencial Empresarial y Escenarios de Uso

> **Documento actualizado: 8 Enero 2026**  
> Nota: este apartado está en desarrollo; aterriza visión y mercado objetivo.
> Complemento: `docs/04-arquitectura/chat_empresarial_anti_alucinaciones.md` (Chat empresarial anti‑alucinaciones / grounded chat)
> **NUEVO**: `docs/04-arquitectura/estrategia_grafos_fallback.md` (Licencias Neo4j/Memgraph corregidas, algoritmos GDS/MAGE, fallback)
> **NUEVO**: `docs/06-agente-autonomo/README.md` (Agente autónomo LangGraph para pipeline GT)

## Productos derivados (líneas de producto separadas)

Además del producto base (análisis cualitativo de entrevistas), se han identificado **productos independientes** que reutilizan parte del stack (PG + Qdrant + grafo + LLM) pero tienen **objetivos y roadmap propios**:

- **Chat Enterprise anti‑alucinaciones** (conversacional + grounded): ver [docs/05-productos-derivados/chat-enterprise/README.md](docs/05-productos-derivados/chat-enterprise/README.md)
- **App bibliográfica (marco teórico desde literatura científica)**: ver [docs/05-productos-derivados/06-bibliografia/README.md](docs/05-productos-derivados/06-bibliografia/README.md)
- **Evidence Packs / Reporting Suite** (entregables defendibles para consultoría/impacto): ver [docs/05-productos-derivados/01-evidence-packs/README.md](docs/05-productos-derivados/01-evidence-packs/README.md)
- **Interoperabilidad CAQDAS** (exports estándar: REFI‑QDA/MAXQDA/NVivo/ATLAS.ti): ver [docs/05-productos-derivados/02-interoperabilidad-caqdas/README.md](docs/05-productos-derivados/02-interoperabilidad-caqdas/README.md)
- **Enterprise Governance** (SSO/OAuth + audit logging + compliance): ver [docs/05-productos-derivados/03-enterprise-governance/README.md](docs/05-productos-derivados/03-enterprise-governance/README.md)

---

## 0. Objetivo de negocio (visión 2025)

**APP_Jupter** busca convertirse en un **producto competitivo de análisis empresarial** basado en investigación cualitativa (teoría y metodología sociológica) + IA, ampliando el uso desde proyectos propios de investigación hacia un público amplio.

### 0.1 Público objetivo (personas)

- **Investigadores y analistas cualitativos** (academia y centros de estudio): codificación, trazabilidad, saturación y reporting.
- **ONG / filantropía / evaluación de impacto**: aprendizaje organizacional, evaluación de programas, análisis de narrativas y stakeholder mapping.
- **Consultoras** (estrategia, transformación, reputación, CX/EX): síntesis acelerada de entrevistas, hallazgos defendibles y “evidence packs”.
- **Gobierno / sector público**: análisis de entrevistas, participación ciudadana, diagnósticos territoriales y justificación de políticas.
- **Empresas**: research interno/externo, riesgos, cultura organizacional, sostenibilidad/ESG, innovación.

### 0.2 Promesa de valor (en una frase)

Convertir entrevistas y documentos en **insights accionables y auditables**, manteniendo **trazabilidad** desde el hallazgo hasta los fragmentos de evidencia, y reduciendo fricción entre exploración semántica, codificación y reporte.

### 0.3 Rol del stack (por qué 4 memorias)

- **PostgreSQL (fuente de verdad)**: fragmentos, códigos, evidencia, reportes; base estable para auditoría y exportación.
- **Qdrant (memoria semántica)**: recuperación por significado (embeddings), discovery exploratorio y similitud.
- **Neo4j (memoria topológica)**: relaciones explícitas (categorías ↔ códigos ↔ fragmentos), comunidades/centralidad, navegación y explicabilidad.
- **IA (LLM) + metodología**: acelera síntesis y propone hipótesis; la metodología (Grounded Theory y afines) regula el proceso y la calidad.

### 0.4 Mejor uso potencial: Neo4j vs Memgraph (en APP_Jupter)

Esta sección define **dónde aporta más** cada motor de grafos, aterrizado a tus objetivos (producto de análisis empresarial) y a tu stack actual (IA + Qdrant + PostgreSQL + grafo).

#### A) Neo4j: “Grafo persistente, gobernable y explicable”

Mejor cuando necesitas **persistencia fuerte**, consistencia de modelo, y un grafo que actúe como “memoria institucional” del proyecto.

- **Mejor descubrimiento (discovery guiado por grafo)**: usar el grafo para “expandir” desde un hallazgo semántico (Qdrant) hacia vecinos relevantes (códigos co‑ocurrentes, categorías cercanas, relaciones confirmadas), priorizando caminos cortos y vecinos con mayor centralidad/comunidad.
- **Calidad/consistencia (data quality)**: validar integridad del grafo (huérfanos, duplicados lógicos, relaciones sin evidencia, fragmentos sin anclaje) y reforzar multi‑proyecto con reglas/constraints.
- **Recomendaciones con trazabilidad**: sugerir códigos/categorías/relaciones no solo por similitud, sino por estructura (comunidades, patrones repetidos, co‑ocurrencia) y siempre devolviendo “por qué” (evidencias + subgrafo mínimo).
- **Explicabilidad y auditoría**: entregar respuestas y reportes con “evidence graph” (qué fragmentos sustentan qué código, qué relaciones axiales se confirmaron, qué hipótesis se rechazaron) y permitir reconstrucción del razonamiento.

Lectura práctica: Neo4j rinde más cuando el valor está en **navegar, justificar y gobernar** conocimiento a lo largo del tiempo.

#### B) Memgraph: “Grafo rápido para analítica online y extensibilidad Python”

Mejor cuando priorizas **velocidad in‑memory** y/o quieres ejecutar analítica no estándar sin salir del motor (según disponibilidad de extensiones).

- **Recomendaciones/analítica en caliente**: recalcular métricas o heurísticas frecuentes (p. ej. centralidad/comunidades) con baja latencia para UI interactiva.
- **Extensiones como comodín**: cuando aparezcan necesidades que no encajan en Cypher “puro” o que convenga ejecutar cerca de los datos (procedimientos propios / módulos), especialmente si buscas rapidez de iteración.
- **Entornos de experimentación**: probar algoritmos, features y pipelines de grafo sin impactar la base “de referencia” del producto.

Lectura práctica: Memgraph rinde más cuando el valor está en **compute** y rapidez de iteración, no necesariamente en gobernanza.

#### C) Recomendación concreta para tu producto (sin sobrediseñar)

1) **Usa PostgreSQL como ledger canónico (fuente de verdad)** y **Neo4j como proyección persistida y gobernable** para:
	- relaciones axiales confirmadas, evidencia, y navegación explicable.
	- controles de consistencia (reglas de integridad por proyecto).

2) **Usa Qdrant como puerta de entrada** (recuperación semántica) y deja que Neo4j haga la **expansión explicable**.

3) **Considera Memgraph solo si** el cuello de botella real es compute/latencia o si quieres un sandbox de analítica:
	- No como “sustituto por defecto”, sino como **acelerador** o **entorno de experimentación**.

4) **Evita la dualidad sin motivo**: mantener dos grafos en paralelo (Neo4j + Memgraph) exige sincronización, definición explícita de “fuente de verdad” (PostgreSQL) y planes de recuperación.



## 1. Evaluación de Viabilidad Empresarial

### Veredicto: **Alta Viabilidad con Diferenciación Clara**

**APP_Jupter** ha evolucionado de un prototipo académico a una **plataforma de análisis cualitativo asistido por IA** con capacidades que lo diferencian de herramientas existentes como NVivo, ATLAS.ti, o MAXQDA.

### Propuesta de Valor Única

| Característica | Herramientas Tradicionales | APP_Jupter |
|----------------|---------------------------|------------|
| **Análisis con LLM** | ❌ No disponible | ✅ GPT-4/5 integrado para codificación |
| **Grafo de Conocimiento** | ⚠️ Básico (jerárquico) | ✅ Neo4j con relaciones causales |
| **Búsqueda Semántica** | ❌ Solo palabras clave | ✅ Embeddings + BM25 híbrido |
| **Descubrimiento Automático** | ❌ Manual | ✅ Discovery + Relaciones Ocultas |
| **Chat con Contexto** | ❌ No existe | ✅ GraphRAG con Chain of Thought |
| **Predicción de Enlaces** | ❌ No existe | ✅ Link Prediction + Comunidades |

### Fundamentos Técnicos Verificados (15 Dic 2024)

| Componente | Estado | Implementación |
|------------|--------|----------------|
| **Arquitectura Híbrida (GraphRAG)** | ✅ Completo | `graphrag.py` + `neo4j_block.py` + `qdrant_block.py` |
| **Pipeline DOCX → Grafo** | ✅ Completo | `documents.py` → `ingestion.py` → embeddings → persistencia |
| **Codificación Abierta (Etapa 3)** | ✅ Completo | `coding.py`, `analysis.py` |
| **Codificación Axial (Etapa 4)** | ✅ Corregido | `axial.py` con inferencia de tipos de relación |
| **Búsqueda Híbrida** | ✅ Completo | `queries.py`: semántica + BM25 |
| **Discovery (Exploración pos/neg/target)** | ✅ **NUEVO** | `queries.py:discover_search()` (búsqueda ponderada portable; opcional `qdrant_block.py:discover_search()` si la versión de Qdrant lo soporta) |
| **GraphRAG + CoT** | ✅ **NUEVO** | Chat con contexto de grafo + razonamiento paso a paso |
| **Relaciones Ocultas** | ✅ **NUEVO** | Descubrimiento de conexiones latentes |
| **Persistencia de Reportes y Memos** | ✅ **NUEVO** | GraphRAG → `reports/<proyecto>/`; Discovery → `notes/<proyecto>/`; informe integrado → `informes/` |
| **Saturación Teórica** | ✅ Implementado | `cumulative_code_curve()`, `evaluate_curve_plateau()` |
| **Núcleo Selectivo** | ✅ Implementado | `nucleus.py`: centralidad y reportes |
| **Autenticación Production-Ready** | ✅ **27 Dic** | `auth_service.py`: bcrypt, JWT, refresh tokens, rate limiting (slowapi) |
| **Multi-tenancy** | ✅ **27 Dic** | `owner_id` en proyectos, `list_projects_for_user()` |
| **Informe Científico 2.0** | ✅ **27 Dic** | `report_templates.py`: Exportación Markdown estructurada |
| **RBAC (Roles)** | ✅ **1 Ene 2026** | `auth.py`: `require_role()`, roles admin/analyst/viewer |
| **Admin Panel** | ✅ **1 Ene 2026** | `routers/admin.py`: CRUD usuarios, stats org; `AdminPanel.tsx` |
| **Export Before Delete** | ✅ **1 Ene 2026** | `GET /api/projects/{id}/export`: ZIP backup antes de eliminar |
| **Self-Service Account Deletion** | ✅ **1 Ene 2026** | `POST /api/auth/me/delete`: Usuario puede eliminar su cuenta |
| **Neo4j Resilience** | ✅ **7 Ene 2026** | `neo4j_sync.py`: PostgreSQL fallback, sync diferida |
| **Agente Autónomo (MVP)** | ✅ **8 Ene 2026** | `agent_standalone.py`: LangGraph orquestador GT |

### Trazabilidad y Resiliencia

```
Trazabilidad: ✅ Mejorado (~85% - fragmentos linkean a códigos, códigos a reportes)
Resiliencia: ✅ MUY ROBUSTO (Neo4j opcional, PostgreSQL fallback, sync diferida)
Persistencia: ✅ Completo (reportes en `reports/`, memos en `notes/`)
Autonomía: ✅ NUEVO (Agente LangGraph ejecuta pipeline GT sin intervención)
```

---

## 1.1 Trazabilidad Técnica (Cascada desde `app/`)

Esta sección aterriza lo descrito arriba en **módulos reales** (carpeta `app/`) y cómo se exponen por **CLI** (`main.py`) y **API** (`backend/app.py`).

### 1.1.1 Cascada end-to-end (datos → IA → grafo → reporting)

1) **Ingesta (DOCX → Fragmentos → Vectores + Persistencia)**
- Lectura/fragmentación: `app/documents.py` (`load_fragment_records`, `make_fragment_id`)
- Orquestación de ingesta: `app/ingestion.py` (`ingest_documents`)
- Embeddings: `app/embeddings.py` (`embed_batch`)
- Persistencia:
	- Qdrant (vectores/payload): `app/qdrant_block.py` (`ensure_collection`, `ensure_payload_indexes`, `upsert`)
	- PostgreSQL (tabla `entrevista_fragmentos`): `app/postgres_block.py` (`ensure_fragment_table`, `insert_fragments`)
	- Neo4j (nodos Fragmento/Entrevista y relaciones): `app/neo4j_block.py` (`ensure_constraints`, `merge_fragments`)

2) **Análisis cualitativo asistido por LLM (Etapas 0–4)**
- LLM + JSON estructurado: `app/analysis.py` (`analyze_interview_text`, `call_llm_chat_json`)
- GraphRAG “global” previo (centralidad/comunidades ya persistidas): `app/analysis.py` (`get_graph_context`)
- Persistencia de resultados:
	- Etapa 3 (códigos abiertos): `app/postgres_block.py` (`ensure_open_coding_table`, `upsert_open_codes`)
	- Etapa 4 (axial): `app/axial.py` (`assign_axial_relation`) + `app/neo4j_block.py` (`merge_category_code_relationship`)

3) **Descubrimiento exploratorio (Discovery)**
- Implementación principal usada por API: `app/queries.py` (`discover_search`)
	- Nota: actualmente usa **búsqueda ponderada** sobre `qdrant.query_points()` para ser portable entre versiones.
	- Alternativa disponible: `app/qdrant_block.py` (`discover_search`) usa `client.discover()` si la instalación de Qdrant lo soporta.
- Exposición API:
	- Buscar: `POST /api/search/discover`
	- Analizar con IA: `POST /api/discovery/analyze`
	- Guardar memo Markdown: `POST /api/discovery/save_memo` → `notes/<proyecto>/...md`

4) **Chat con contexto de grafo (GraphRAG)**
- Core: `app/graphrag.py` (`graphrag_query`, `extract_relevant_subgraph`, `format_subgraph_for_prompt`)
- Modo “CoT visible” (pasos explícitos): `app/graphrag.py` (`graphrag_chain_of_thought`)
- Exposición API:
	- Consultar: `POST /api/graphrag/query` (flag `chain_of_thought`)
	- Guardar reporte Markdown: `POST /api/graphrag/save_report` → `reports/<proyecto>/...md`

5) **Relaciones ocultas y predicción de enlaces**
- Predicción/heurísticas: `app/link_prediction.py` (`suggest_links`, `detect_missing_links_by_community`, `discover_hidden_relationships`)
- Comunidades/centralidad (GDS o fallback NetworkX): `app/axial.py` (`run_gds_analysis` con `persist=True` escribe `community_id` / `score_centralidad`)
- Exposición API:
	- Predicción: `GET /api/axial/predict`
	- Relaciones ocultas: `GET /api/axial/hidden-relationships`
	- Confirmar relación descubierta: `POST /api/axial/confirm-relationship`

6) **Reporting y validación**
- Informe integrado (Stage 9): `app/reporting.py` (`build_integrated_report`) → `informes/informe_integrado.md` + `informes/report_manifest.json`
- Informes por entrevista (persisten en PostgreSQL): `app/reports.py` (tabla `interview_reports`)
- Validación/saturación/outliers/member-checking: `app/validation.py`

### 1.1.2 Tabla de trazabilidad (Valor → Implementación)

| Valor/capacidad (doc) | Implementación principal (`app/`) | Exposición (API/CLI) | Persistencia |
|---|---|---|---|
| Pipeline DOCX → grafo | `documents.py` + `ingestion.py` | API: `POST /api/ingest` · CLI: `main.py ingest` | Qdrant + PostgreSQL + Neo4j |
| Búsqueda híbrida | `queries.py` (`semantic_search`) | API: (vía endpoints de search/similar) · CLI: `main.py search` | Qdrant + PostgreSQL |
| Discovery exploratorio | `queries.py` (`discover_search`) | API: `POST /api/search/discover` | (resultados) response; memo opcional en `notes/<proyecto>/` |
| GraphRAG | `graphrag.py` | API: `POST /api/graphrag/query` | reporte opcional en `reports/<proyecto>/` |
| Codificación (Etapa 3/4) | `analysis.py` + `axial.py` | API: `POST /api/analyze` (+ persist) · CLI: `main.py analyze` | PostgreSQL + Neo4j |
| Comunidades / centralidad | `axial.py` (`run_gds_analysis`) | API: `POST /api/axial/gds` · CLI: `main.py axial gds` | Neo4j (propiedades `community_id`, `score_centralidad`) |
| Relaciones ocultas | `link_prediction.py` | API: `GET /api/axial/hidden-relationships` | Neo4j cuando se confirma |
| Informe integrado | `reporting.py` | CLI: `main.py report build` | `informes/` (+ manifiesto) |

### 1.1.3 Observaciones de alineación (brechas/riesgos)

- **Discovery “API” vs portabilidad**: hoy el endpoint usa `app/queries.py:discover_search()` (búsqueda ponderada). Si se quiere depender del **Discovery API nativo** de Qdrant, el switch natural es `app/qdrant_block.py:discover_search()` (pero requiere compatibilidad de versión).
- **Persistencia distribuida**: hay tres “canales” de salida distintos: archivos en `reports/` y `notes/`, artefactos de informe en `informes/`, y métricas por entrevista en PostgreSQL (`interview_reports`). Para enterprise conviene definir política única de backup/retención.
- **“CoT” como formato, no garantía**: `graphrag_chain_of_thought()` fuerza un formato por pasos; algunos modelos pueden resumir/omitir razonamiento interno. En práctica es mejor describirlo como **explicación estructurada**.
- **Multi-tenancy**: ✅ **IMPLEMENTADO (27 Dic 2024)** - `owner_id` en proyectos, `list_projects_for_user()` filtra por owner/org/rol. Gobernanza SSO/OAuth pendiente.


---

## 1.2 Trazabilidad UX (Frontend `frontend/src/`)

Esta sección completa la cascada conectando **capacidad/valor** → **pantalla/acción de usuario** → **endpoint** (`backend/app.py`) → **módulos** (`app/`) → **persistencia**.

### 1.2.1 Orquestación del dashboard (workflow por etapas)

- Selección/creación de proyecto: `GET /api/projects`, `POST /api/projects` (UI: `frontend/src/App.tsx`).
- Progreso y checklist de etapas: `GET /api/status?project=...&update_state=true`.
- Cierre manual de etapa: `POST /api/projects/{project_id}/stages/{stage}/complete`.

### 1.2.2 Tabla UX → API → implementación → persistencia

| UX (panel/acción) | Endpoint (backend) | Implementación principal (`app/`) | Persistencia |
|---|---|---|---|
| Ingesta DOCX (Etapa 1) | `POST /api/ingest` | `documents.py` + `ingestion.py` + `embeddings.py` | Qdrant + PostgreSQL + Neo4j |
| Estado/progreso del proyecto | `GET /api/status` | `project_state.py` (detección de etapas) | `data/projects/<id>/` + `metadata/` (snapshot) |
| Transcripción audio (1 archivo) | `POST /api/transcribe` | `transcription.py` (chunked + diarización) + `ingestion.py` (si ingest=true) | DOCX en `data/projects/<id>/audio/transcriptions/` (+ Qdrant/PG/Neo4j si ingest) |
| Transcripción audio (batch) | `POST /api/transcribe/batch` + `GET /api/jobs/{task_id}/status` | `backend/celery_worker.py` + `transcription.py` | idem + estado en Celery/Redis |
| Merge de transcripciones | `POST /api/transcribe/merge` | (backend) construcción DOCX | DOCX en `data/projects/<id>/audio/transcriptions/` + descarga base64 |
| Familiarización (Etapa 2) | `GET /api/familiarization/fragments` | Qdrant scroll (payload) | Qdrant (lee payload: speaker/archivo/idx) |
| Codificación abierta (Etapa 3) asignar código | `POST /api/coding/assign` | `coding.py` (assign) + `postgres_block.py` + `neo4j_block.py` | PostgreSQL + Neo4j (+ payload/anchors en Qdrant si aplica) |
| Sugerencias semánticas (fragmentos similares) | `POST /api/coding/suggest` | `coding.py` (suggest_similar_fragments) + Qdrant search | Qdrant (consulta); opcional persistencia si `persist=true` |
| Citas por código (evidencia) | `GET /api/coding/citations` | `coding.py`/queries Postgres | PostgreSQL |
| Métricas de cobertura/saturación | `GET /api/coding/stats` (+ `GET /api/coding/saturation`) | `validation.py` / stats helpers | PostgreSQL |
| Export (REFI-QDA / MAXQDA) | `GET /api/export/refi-qda`, `GET /api/export/maxqda` | export helpers | Descarga (archivo generado en respuesta) |
| Análisis asistido LLM (Etapas 0–4) | `POST /api/analyze` + `GET /api/tasks/{task_id}` | `analysis.py` (LLM) vía Celery | Resultado en task; persist opcional |
| Persistir análisis | `POST /api/analyze/persist` | `analysis.py` (`persist_analysis`) | PostgreSQL + Neo4j |
| Neo4j Explorer (Cypher) | `POST /api/neo4j/query` | `neo4j_block.py` (driver) | Neo4j |
| Neo4j Explorer (export) | `POST /api/neo4j/export` | `neo4j_block.py` (driver) | Descarga (CSV/JSON) |
| GDS (Louvain/PageRank) | `POST /api/axial/gds` | `axial.py` (`run_gds_analysis`) | Neo4j (propiedades: `community_id`, `score_centralidad`) |
| GraphRAG (chat contextual) | `POST /api/graphrag/query` | `graphrag.py` | Response; opcional persistencia |
| Guardar reporte GraphRAG | `POST /api/graphrag/save_report` | (backend) formateo MD | `reports/<proyecto>/...md` |
| Discovery (búsqueda pos/neg/target) | `POST /api/search/discover` | `queries.py` (`discover_search`) | Response |
| Discovery (síntesis IA) | `POST /api/discovery/analyze` | LLM (AOAI) | Response |
| Guardar memo Discovery | `POST /api/discovery/save_memo` | (backend) formateo MD | `notes/<proyecto>/...md` |
| Link Prediction | `GET /api/axial/predict`, `GET /api/axial/community-links` | `link_prediction.py` | Response |
| Link Prediction (análisis IA) | `POST /api/axial/analyze-predictions` | LLM (AOAI) | Response |
| Relaciones ocultas | `GET /api/axial/hidden-relationships` | `link_prediction.py` (`discover_hidden_relationships`) | Response |
| Confirmar relación oculta | `POST /api/axial/confirm-relationship` | `link_prediction.py` (`confirm_hidden_relationship`) | Neo4j (relación creada) |
| Informes por entrevista | `GET /api/reports/interviews` | `reports.py` | PostgreSQL (`interview_reports`) |
| Resumen Etapa 4 | `GET /api/reports/stage4-summary` | `reports.py` | PostgreSQL (consulta/agregación) |
| **Export proyecto (backup)** | `GET /api/projects/{id}/export` | `app.py` | ZIP descargable |
| **Admin: listar usuarios** | `GET /api/admin/users` | `routers/admin.py` | PostgreSQL |
| **Admin: editar usuario** | `PATCH /api/admin/users/{id}` | `routers/admin.py` | PostgreSQL |
| **Admin: eliminar usuario** | `DELETE /api/admin/users/{id}` | `routers/admin.py` | PostgreSQL |
| **Admin: estadísticas org** | `GET /api/admin/stats` | `routers/admin.py` | PostgreSQL |
| **Self-delete cuenta** | `POST /api/auth/me/delete` | `routers/auth.py` | PostgreSQL (elimina usuario) |

### 1.2.3 Desalineaciones detectadas (Frontend vs Backend)

- `frontend/src/components/LinkPredictionPanel.tsx` permite “Guardar Informe” descargándolo localmente; no existe persistencia server-side equivalente (por diseño actual).

**Correcciones aplicadas**

- Se añadió en backend el endpoint `POST /api/maintenance/delete_file` para soportar la acción “Eliminar datos del archivo” desde `AnalysisPanel`.
- Se corrigió la documentación de `CodingPanel` para reflejar el endpoint real `GET /api/interviews`.


---

## 2. Mercado Objetivo y Competencia

### Análisis de Mercado

| Segmento | Tamaño Estimado | Competidores | Posición APP_Jupter |
|----------|-----------------|--------------|---------------------|
| **Software CAQDAS** | $500M+ anual | NVivo, ATLAS.ti, MAXQDA | Diferenciador: IA + Grafos |
| **Research Tech** | $2B+ anual | Dovetail, Notably, Condens | Competidor directo |
| **AI Analytics** | $15B+ anual | Palantir, Tableau | Nicho especializado |

### Ventaja Competitiva Real

1. **GraphRAG + Neo4j**: Ningún competidor ofrece chat con contexto de grafo
2. **Discovery Semántico**: Búsqueda exploratoria que supera palabras clave
3. **Relaciones Ocultas**: Descubrimiento automático de patrones
4. **Open-Source Friendly**: Stack basado en tecnologías open (Neo4j, Qdrant, FastAPI)
5. **Metodología Grounded Theory**: Implementación completa de las 4 etapas

### Barreras de Entrada

| Barrera | Estado | Descripción |
|---------|--------|-------------|
| Complejidad técnica | ✅ Superada | Arquitectura híbrida funcionando |
| Costos de LLM | ⚠️ Variable | Azure OpenAI puede ser costoso a escala |
| Adopción de usuarios | 🔄 Por validar | Requiere piloto con investigadores |
| Cumplimiento legal | ⚠️ Parcial | Necesita auditoría GDPR/SOC2 |

---

## 3. Estado Actual vs Enterprise-Ready

| Componente | Estado | Ubicación | Próximo Paso |
|------------|--------|-----------|--------------|
| **API REST (FastAPI)** | ✅ ~60 endpoints | `backend/app.py` | Documentación OpenAPI |
| **Dashboard Web (React)** | ✅ Funcional | `frontend/` (11+ componentes) | UX polish |
| **GraphRAG** | ✅ **NUEVO** | `app/graphrag.py` | - |
| **Discovery** | ✅ **NUEVO** | `app/queries.py` | - |
| **Relaciones Ocultas** | ✅ **NUEVO** | `app/link_prediction.py` | UI integrada |
| **Persistencia Reportes** | ✅ **NUEVO** | `reports/`, `notes/` | Búsqueda en reportes |
| **Autenticación** | ✅ **Production-Ready** | `backend/auth_service.py` | bcrypt, JWT, refresh, rate limiting |
| **Multi-tenancy** | ✅ **Implementado** | `project_state.py` | owner_id + org_id + filtrado |
| **Informe Científico 2.0** | ✅ **NUEVO** | `app/report_templates.py` | Exportación Markdown estructurada |
| **Tareas Asíncronas** | ✅ Celery/Redis | `celery_worker.py` | - |
| **Health Checks** | ✅ Implementado | `healthcheck.py` | - |

---

## 4. Escenarios de Uso Validados

### 4.1 Investigación de Mercado

**Caso**: Análisis de 50 entrevistas a profundidad sobre comportamiento de consumo

| Funcionalidad | Uso |
|---------------|-----|
| **Ingesta** | Cargar 50 DOCX, fragmentar automáticamente |
| **Coding LLM** | Generar códigos abiertos con GPT-4 o GPT-5.2-chat|
| **Discovery** | Buscar "motivación de compra" sin "precio" |
| **GraphRAG** | "¿Qué factores emocionales influyen en la decisión?" |
| **Relaciones Ocultas** | Encontrar conexiones entre "marca" y "identidad" |

### 4.2 Experiencia del Cliente (CX)

**Caso**: Análisis de 200 verbatims de NPS detractores

| Funcionalidad | Uso |
|---------------|-----|
| **Ingesta** | Importar desde CSV/DOCX |
| **Discovery** | Buscar "frustración" sin "precio" para aislar problemas operativos |
| **GraphRAG** | "¿Cuáles son las causas raíz de insatisfacción?" |
| **Axial** | Visualizar cadenas causales problema → impacto |

### 4.3 Recursos Humanos

**Caso**: Análisis de 30 exit interviews

| Funcionalidad | Uso |
|---------------|-----|
| **Anonimato** | Speakers como "Entrevistado 1", "Entrevistado 2" |
| **Coding** | Identificar patrones de rotación |
| **Relaciones Ocultas** | Conectar "liderazgo" con "desarrollo profesional" |
| **Reportes** | Generar hallazgos para RRHH |

### 4.4 Academia e Investigación Social

**Caso**: Tesis doctoral con 20 entrevistas etnográficas

| Funcionalidad | Uso |
|---------------|-----|
| **Grounded Theory** | Etapas 0-4 completas |
| **Saturación** | Curva de códigos para determinar suficiencia |
| **Memos** | Discovery + notas analíticas |
| **GraphRAG CoT** | Preguntas interpretativas con razonamiento visible |

---

## 5. Modelo de Negocio Potencial

### Opciones de Monetización

| Modelo | Precio Sugerido | Target |
|--------|-----------------|--------|
| **SaaS Team** | $99-199/mes/usuario | Agencias de research |
| **Enterprise** | $500-2000/mes flat | Corporativos (CX, RRHH) |
| **Academic** | $29/mes o gratis | Universidades |
| **On-Premise** | $10k-50k/año | Sectores regulados |

### Costos Operativos Estimados

| Componente | Costo/mes (10 usuarios) |
|------------|------------------------|
| Azure OpenAI (GPT-4) | $200-500 |
| Infraestructura (Azure) | $150-300 |
| Neo4j Aura | $65-200 |
| Qdrant Cloud | $25-100 |
| **Total** | **$440-1100/mes** |

---

## 6. Hoja de Ruta Actualizada

### ✅ Fase 1: Fundamentos (COMPLETADO)
- [x] API REST con FastAPI (~60 endpoints)
- [x] Dashboard React funcional
- [x] Persistencia Neo4j + Qdrant + PostgreSQL
- [x] Documentación completa

### ✅ Fase 2: Características Avanzadas (COMPLETADO 15 Dic 2024)
- [x] GraphRAG con Chain of Thought
- [x] Discovery API (búsqueda exploratoria)
- [x] Relaciones Ocultas (descubrimiento latente)
- [x] Persistencia de reportes y memos
- [x] Compatibilidad GPT-5/O1

### ✅ Fase 2.5: Seguridad y Multi-tenancy (COMPLETADO 27 Dic 2024)
- [x] Autenticación production-ready (bcrypt, JWT, refresh tokens)
- [x] Rate limiting con Redis (slowapi)
- [x] Multi-tenancy (owner_id, org_id, filtrado por rol)
- [x] Informe Científico 2.0 (report_templates.py)

### ✅ Fase 2.8: Resiliencia y Autonomía (COMPLETADO 8 Ene 2026)
- [x] Neo4j opcional con PostgreSQL fallback
- [x] Sincronización diferida Admin Panel
- [x] Agente autónomo LangGraph (MVP standalone)
- [x] Análisis estratégico: Hebbia, Devin, Elicit

### 🔄 Fase 2.9: Validación (EN PROGRESO)
- [ ] Piloto con 3-5 investigadores reales
- [ ] Load test con >100 entrevistas
- [ ] Medir precisión de codificación LLM
- [ ] Feedback de UX

### 📋 Fase 3: Enterprise-Ready
- [x] Multi-tenancy con aislamiento ✅
- [ ] SSO/OAuth (Azure AD, Google)
- [ ] Audit logging (GDPR compliance)
- [ ] CI/CD automatizado
- [ ] Exportación a NVivo/ATLAS.ti format

### 🎯 Fase 4: Go-to-Market
- [ ] Landing page + demo
- [ ] Piloto pagado con 2-3 clientes
- [ ] Documentación de usuario final
- [ ] Onboarding automatizado

---

## 7. Evaluación Honesta del Estado Actual

### ✅ Lo que está RESUELTO (Diciembre 2024)

- Pipeline completo DOCX → Fragmentos → Vectores → Grafo
- Arquitectura híbrida moderna (PG + Qdrant + Neo4j)
- API REST funcional con ~60 endpoints
- Dashboard React operativo con 11+ componentes
- **GraphRAG funcional con Chain of Thought**
- **Discovery API operativo**
- **Relaciones Ocultas implementado**
- **Persistencia de reportes y memos**
- Autenticación JWT + API Key
- Tareas asíncronas con Celery/Redis
- Documentación completa (70+ archivos)

### ⚠️ Lo que requiere VALIDACIÓN

- Precisión del LLM para codificación (necesita medición con ground truth)
- Usabilidad por investigadores no técnicos
- Escalabilidad con >1000 fragmentos
- Costos reales de Azure OpenAI en producción

### ❌ Lo que falta para PRODUCCIÓN

- SSO/OAuth para enterprise (Azure AD, Google)
- ~~Multi-tenancy~~ ✅ Ya implementado (owner_id, org_id, RBAC)
- Exportación a formatos CAQDAS estándar (NVivo, ATLAS.ti)
- Cumplimiento GDPR/SOC2 formal (audit logging)
- CI/CD automatizado

---

## 8. Recomendación Estratégica

### Próximos 30 días

1. **Piloto interno**: Usar la herramienta con un proyecto real de investigación
2. **Medir métricas**: Tiempo de codificación, precisión, satisfacción
3. **Identificar gaps**: Qué falta para que un investigador lo adopte

### Próximos 90 días

1. **Piloto externo**: 2-3 clientes beta (academia + empresa)
2. **Pricing validation**: ¿Cuánto pagarían?
3. **Competidor deep-dive**: Comparar feature-by-feature vs NVivo/Dovetail

### Decisión Go/No-Go

| Criterio | Umbral |
|----------|--------|
| Tiempo de codificación | <50% vs manual |
| Satisfacción usuarios | >4/5 |
| Precisión códigos LLM | >75% concordancia |
| Disposición a pagar | >$50/mes |

---

## Conclusión

**APP_Jupter** ha alcanzado un nivel de madurez que lo posiciona como **MVP viable** para validación de mercado. Las funcionalidades implementadas (GraphRAG, Discovery, Relaciones Ocultas) son **diferenciadores reales** frente a la competencia.

**El siguiente paso crítico es la validación con usuarios reales**, no más desarrollo técnico.

---

## 9. Inspiración de Startups (Sprint 29)

| Startup | Concepto Adoptado | Estado |
|---------|-------------------|--------|
| **Hebbia** | Matrix UI para codificación masiva | 📋 Diseñado |
| **Devin** | Panel de observabilidad (ver pensar a la IA) | 📋 Diseñado |
| **Elicit** | Linkage estricto a citas originales | ✅ Implementado |
| **LangGraph** | Orquestación con grafos de estado | ✅ MVP (`agent_standalone.py`) |
| **DeepSeek** | LLM económico para loops intensivos | 📋 Diseñado |

Ver documentación completa: [docs/06-agente-autonomo/](../06-agente-autonomo/README.md)

---

*Documento verificado: 8 Enero 2026*  
*Funcionalidades nuevas (8 Ene 2026): Neo4j Resilience, Agente Autónomo LangGraph, Análisis Estratégico Startups*  
*Funcionalidades previas (1 Ene 2026): RBAC (roles), Admin Panel, Export Before Delete, Self-Delete Account*  
*Funcionalidades base (27 Dic): Autenticación Production-Ready, Multi-tenancy, Informe Científico 2.0*  
*Funcionalidades base (15 Dic): GraphRAG, Discovery, Relaciones Ocultas, Persistencia de Reportes*
