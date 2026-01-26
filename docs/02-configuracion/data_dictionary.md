# Data Dictionary

This document summarises the core tables managed by the CLI. Keep it versioned; any structural change must ship with migrations and regression tests.

## Table `entrevista_fragmentos`
| Column | Type | Description | Source | Notes |
| --- | --- | --- | --- | --- |
| `id` | TEXT (PK) | Deterministic fragment identifier (`uuid5` of file + index). | Ingestion | Stable even if content repeats; `sha256` tracks changes. |
| `project_id` | TEXT | Project scope identifier (multi-tenant). | Project registry | Always filter by `project_id` in queries. |
| `archivo` | TEXT | Original `.docx` file name. | Ingestion metadata | Use descriptive names and versions. |
| `par_idx` | INT | Fragment index after paragraph coalescing (0-based). | Ingestion | |
| `fragmento` | TEXT | Normalised fragment text. | DOCX | Clean special characters when needed. |
| `embedding` | DOUBLE PRECISION[] | 3072-dim vector from Azure OpenAI `text-embedding-3-large`. | Azure OpenAI | Validated against `EMBED_DIMS`. |
| `char_len` | INT | Fragment length in characters. | Ingestion | Detect empty/very short fragments. |
| `sha256` | TEXT | Hash for change auditing. | Ingestion | Detect silent edits. |
| `area_tematica` | TEXT | Thematic category. | Provided metadata | Optional; use controlled vocabulary. |
| `actor_principal` | TEXT | Main actor/role mentioned. | Provided metadata | Optional taxonomy. |
| `requiere_protocolo_lluvia` | BOOLEAN | Mentions rain protocols/mitigation. | Provided metadata / heuristic | Optional flag. |
| `metadata` | JSONB | Free-form interview attributes (`genero`, `periodo`, `fecha_entrevista`, etc.). | Provided metadata | Populated via ingestion metadata; drives análisis transversal. |
| `speaker` | TEXT | Speaker role (`interviewee` or `interviewer`). | Ingestion | Defaults to `interviewee` after filtering. |
| `interviewer_tokens` | INT | Count of tokens spoken by the interviewer attached to this fragment. | Ingestion | Used for context tracking. |
| `interviewee_tokens` | INT | Count of tokens spoken by the interviewee in this fragment. | Ingestion | Used for filtering short fragments. |
| `created_at` | TIMESTAMPTZ | Insert timestamp. | PostgreSQL | Auto-generated. |
| `updated_at` | TIMESTAMPTZ | Last update timestamp. | PostgreSQL | Auto-managed on upsert. |

## Qdrant Payload Canonical
| Field | Type | Description |
| --- | --- | --- |
| `project_id` | keyword | Project scope identifier (multi-tenant). |
| `archivo` | keyword | Source file name. |
| `par_idx` | integer | Fragment index. |
| `fragmento` | full_text | Full text for keyword queries. |
| `char_len` | integer | Fragment length. |
| `area_tematica` | keyword | Optional thematic category. |
| `actor_principal` | keyword | Optional main actor. |
| `requiere_protocolo_lluvia` | bool | Optional boolean filter. |
| `metadata` | object | Free-form JSON attributes. |
| `speaker` | keyword | Speaker role (`interviewee` or `interviewer`). |
| `interviewer_tokens` | integer | Count of tokens spoken by the interviewer. |
| `interviewee_tokens` | integer | Count of tokens spoken by the interviewee. |

## Ingestion Metadata
| Key | Description | Example |
| --- | --- | --- |
| `area_tematica` | Macro category defined in the research plan. | `"drenaje"` |
| `actor_principal` | Main actor/group mentioned. | `"vecinos"`, `"autoridad municipal"` |
| `requiere_protocolo_lluvia` | Mentions rain protocol requirements. | `true` |
| `metadata` | Extra JSON attributes (gender, interview date, etc.). | `{ "genero": "F", "fecha_entrevista": "2025-08-12" }` |

## Table `analisis_codigos_abiertos`
| Column | Type | Description | Source | Notes |
| --- | --- | --- | --- | --- |
| `fragmento_id` | TEXT (PK part) | References `entrevista_fragmentos.id`. | Coding workflow | Must exist before coding. |
| `project_id` | TEXT (PK part) | Project scope identifier (multi-tenant). | Project registry | Composite uniqueness uses `(project_id, fragmento_id, codigo)`. |
| `codigo` | TEXT (PK part) | Open code label. | Analysts / LLM | Combined with `fragmento_id` is unique. |
| `archivo` | TEXT | File of origin. | Derived | Indexed for quick queries. |
| `cita` | TEXT | Literal extract supporting the code (<=60 words). | Analysts | Provide evidence textual. |
| `fuente` | TEXT | Anonymised source identifier. | Analysts | Optional. |
| `created_at` | TIMESTAMPTZ | Registration timestamp. | PostgreSQL | Useful for saturation tracking. |

## Table `analisis_axial`
| Column | Type | Description | Source | Notes |
| --- | --- | --- | --- | --- |
| `categoria` | TEXT (PK part) | Axial category. | Analysts | Combined with `codigo` + `relacion`. |
| `project_id` | TEXT (PK part) | Project scope identifier (multi-tenant). | Project registry | Composite uniqueness uses `(project_id, categoria, codigo, relacion)`. |
| `codigo` | TEXT (PK part) | Associated open code. | Analysts | Must exist in `analisis_codigos_abiertos`. |
| `code_id` | BIGINT | Stable code identifier (from `catalogo_codigos`). | Code catalog | Optional but recommended for identity across renames/merges. |
| `relacion` | TEXT (PK part) | Relation type (`causa`, `condicion`, `consecuencia`, `partede`). | Analysts | Maintain controlled vocabulary. |
| `archivo` | TEXT | Representative file. | Analysts | Often the first evidence file. |
| `memo` | TEXT | Analytic memo/justification. | Analysts | Optional but recommended. |
| `evidencia` | TEXT[] | Fragment IDs supporting the relation (>=2). | Analysts | Stored as array of strings. |
| `estado` | TEXT | Ledger state (`pendiente`, `validado`, `rechazado`). | Workflow | Only `validado` should sync to Neo4j. |
| `validado_por` | TEXT | User ID that validated the relation. | Workflow | Optional. |
| `validado_en` | TIMESTAMPTZ | Validation timestamp. | Workflow | Optional. |
| `created_at` | TIMESTAMPTZ | Registration timestamp. | PostgreSQL | Set on insert. |
| `updated_at` | TIMESTAMPTZ | Last update timestamp. | PostgreSQL | Auto-updated on upsert. |

## Table `link_predictions`
| Column | Type | Description | Source | Notes |
| --- | --- | --- | --- | --- |
| `id` | SERIAL (PK) | Row identifier. | PostgreSQL | Auto-increment. |
| `project_id` | TEXT | Project scope identifier (multi-tenant). | Project registry | Always filter by project. |
| `source_code` | TEXT | Source code label. | Link Prediction | Canonicalize where possible. |
| `target_code` | TEXT | Target code label. | Link Prediction | Canonicalize where possible. |
| `relation_type` | TEXT | Proposed relationship type (`asociado_con`, `causa`, etc.). | Validation UI | Becomes `REL.tipo` in Neo4j when validated. |
| `algorithm` | TEXT | Algorithm used (e.g., `common_neighbors`, `jaccard`). | Link Prediction | Part of uniqueness constraint. |
| `score` | FLOAT | Algorithm score (can be >1 depending on algorithm). | Link Prediction | Used for ranking/prioritization. |
| `rank` | INTEGER | Rank within a run (optional). | Link Prediction | Stable ordering for review. |
| `estado` | TEXT | Workflow state (`pendiente`, `validado`, `rechazado`). | Validation UI | Only `validado` should sync to Neo4j. |
| `validado_por` | TEXT | User ID that validated/rejected. | Workflow | Optional. |
| `validado_en` | TIMESTAMPTZ | Validation timestamp. | Workflow | Optional. |
| `memo` | TEXT | Reviewer memo / rationale. | Workflow | Optional but recommended. |
| `created_at` | TIMESTAMPTZ | Registration timestamp. | PostgreSQL | Set on insert. |
| `updated_at` | TIMESTAMPTZ | Last update timestamp. | PostgreSQL | Updated on state changes/upserts. |

## Table `axial_ai_analyses`
| Column | Type | Description | Source | Notes |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL (PK) | Row identifier. | PostgreSQL | Auto-increment. |
| `project_id` | TEXT | Project scope identifier (multi-tenant). | Project registry | Always filter by project. |
| `source_type` | TEXT | Origin of the artifact (e.g., `analyze_predictions`). | Backend | Audit trail. |
| `algorithm` | TEXT | Algorithm that produced the suggestions. | Link Prediction | Optional. |
| `algorithm_description` | TEXT | Human-readable algorithm description. | Backend | Optional. |
| `suggestions_json` | JSONB | Suggestions analyzed (source/target/score, etc.). | Backend | Stored as JSON array. |
| `analysis_text` | TEXT | Rendered memo text (human-readable). | LLM | Normalized from memo statements or raw output. |
| `memo_statements` | JSONB | Epistemic-tagged statements (`type`, `text`, `evidence_ids`, `evidence_fragment_ids`). | LLM | Used for UI rendering/audit. |
| `structured` | BOOLEAN | Whether structured output is available. | Backend | `true` when memo statements parsed. |
| `estado` | TEXT | Workflow state (`pendiente`, `validado`, `rechazado`). | Workflow | Does not auto-sync to Neo4j. |
| `created_by` | TEXT | User ID that created the artifact. | Auth | Optional. |
| `reviewed_by` | TEXT | User ID that reviewed/validated. | Workflow | Optional. |
| `reviewed_en` | TIMESTAMPTZ | Review timestamp. | Workflow | Optional. |
| `review_memo` | TEXT | Human review memo. | Workflow | Optional. |
| `epistemic_mode` | TEXT | Project epistemic mode at generation time. | Project config | `constructivist` or `post_positivist`. |
| `prompt_version` | TEXT | Version identifier from prompt loader. | Prompts | Persist for audit. |
| `llm_deployment` | TEXT | Azure OpenAI deployment used. | Azure | Audit. |
| `llm_api_version` | TEXT | Azure OpenAI API version used. | Azure | Audit. |
| `evidence_schema_version` | INTEGER | Evidence schema version stored in `evidence_json`. | Backend | Default `1`. |
| `evidence_json` | JSONB | Evidence pack snapshot (positive/negative fragments) used to ground the analysis. | Backend | Stored for review/audit reproducibility. |
| `created_at` | TIMESTAMPTZ | Registration timestamp. | PostgreSQL | Set on insert. |
| `updated_at` | TIMESTAMPTZ | Last update timestamp. | PostgreSQL | Updated on update. |

## Table `analisis_axial` (Neo4j projection)
| Node/Edge | Properties | Notes |
| --- | --- | --- |
| `(:Categoria {nombre, project_id})` | `nombre`, `project_id` | Composite uniqueness enforced (multi-tenant). |
| `(:Codigo {nombre, project_id})` | `nombre`, `project_id` | Composite uniqueness enforced (multi-tenant). |
| `(:Fragmento {id, project_id})` | `id`, `project_id`, `texto`, `par_idx`, `char_len`, `speaker`, `interviewer_tokens`, `interviewee_tokens` | Ingested previously. |
| `(:Fragmento)-[:TIENE_CODIGO]->(:Codigo)` | `project_id` | Built during open coding; relation is project-scoped. |
| `(:Categoria)-[:REL {tipo, memo, evidencia, actualizado_en}]->(:Codigo)` | `project_id`, `tipo`, `memo`, `evidencia` (list), timestamp | Created via `axial relate` or analysis persistence; requires >=2 fragment IDs in `evidencia`. |
| `(:Codigo)-[:REL {tipo, source, actualizado_en}]->(:Codigo)` | `project_id`, `tipo`, `source`, timestamp | Created by validating link predictions (code↔code). |
| `(:Entrevista {project_id})-[:TIENE_FRAGMENTO {speaker, char_len}]->(:Fragmento)` | `project_id`, `speaker`, `char_len` | Relationship created during ingestion. |

## Materialized Views (Transversal)
| View | Description | Notes |
| --- | --- | --- |
| `mv_categoria_por_rol` | Aggregates categorías vs `actor_principal` (entrevistas, códigos, relaciones). | Refreshed via `python main.py transversal pg --refresh`. |
| `mv_categoria_por_genero` | Cross-tab categorías por `metadata->>'genero'`. | Requires `genero` in ingestion metadata JSON. |
| `mv_categoria_por_periodo` | Agrupa categorías por `metadata->>'periodo'` (ej. `2010s`, `2020s`). | Populate `periodo` en metadata previo al análisis transversal. |

Maintain this dictionary under version control; accompany structural changes with migrations and regression tests.
