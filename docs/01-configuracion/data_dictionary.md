# Data Dictionary

This document summarises the core tables managed by the CLI. Keep it versioned; any structural change must ship with migrations and regression tests.

## Table `entrevista_fragmentos`
| Column | Type | Description | Source | Notes |
| --- | --- | --- | --- | --- |
| `id` | TEXT (PK) | Deterministic fragment identifier (`uuid5` of file + index). | Ingestion | Stable even if content repeats; `sha256` tracks changes. |
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
| `codigo` | TEXT (PK part) | Open code label. | Analysts / LLM | Combined with `fragmento_id` is unique. |
| `archivo` | TEXT | File of origin. | Derived | Indexed for quick queries. |
| `cita` | TEXT | Literal extract supporting the code (<=60 words). | Analysts | Provide evidence textual. |
| `fuente` | TEXT | Anonymised source identifier. | Analysts | Optional. |
| `created_at` | TIMESTAMPTZ | Registration timestamp. | PostgreSQL | Useful for saturation tracking. |

## Table `analisis_axial`
| Column | Type | Description | Source | Notes |
| --- | --- | --- | --- | --- |
| `categoria` | TEXT (PK part) | Axial category. | Analysts | Combined with `codigo` + `relacion`. |
| `codigo` | TEXT (PK part) | Associated open code. | Analysts | Must exist in `analisis_codigos_abiertos`. |
| `relacion` | TEXT (PK part) | Relation type (`causa`, `condicion`, `consecuencia`, `partede`). | Analysts | Maintain controlled vocabulary. |
| `archivo` | TEXT | Representative file. | Analysts | Often the first evidence file. |
| `memo` | TEXT | Analytic memo/justification. | Analysts | Optional but recommended. |
| `evidencia` | TEXT[] | Fragment IDs supporting the relation (>=2). | Analysts | Stored as array of strings. |
| `created_at` | TIMESTAMPTZ | Registration timestamp. | PostgreSQL | Set on insert. |

## Table `analisis_axial` (Neo4j projection)
| Node/Edge | Properties | Notes |
| --- | --- | --- |
| `(:Categoria {nombre})` | `nombre` | Unique constraint enforced. |
| `(:Codigo {nombre})` | `nombre` | Unique constraint enforced. |
| `(:Fragmento {id})` | `id`, `texto`, `par_idx`, `char_len`, `speaker`, `interviewer_tokens`, `interviewee_tokens` | Ingested previously. |
| `(:Fragmento)-[:TIENE_CODIGO]->(:Codigo)` | none | Built during open coding. |
| `(:Categoria)-[:REL {tipo, memo, evidencia, actualizado_en}]->(:Codigo)` | `tipo`, `memo`, `evidencia` (list), timestamp | Created via `axial relate` or analysis persistence; requires >=2 fragment IDs in `evidencia`. |
| `(:Entrevista)-[:TIENE_FRAGMENTO {speaker, char_len}]->(:Fragmento)` | `speaker`, `char_len` | Relationship created during ingestion. |

## Materialized Views (Transversal)
| View | Description | Notes |
| --- | --- | --- |
| `mv_categoria_por_rol` | Aggregates categorías vs `actor_principal` (entrevistas, códigos, relaciones). | Refreshed via `python main.py transversal pg --refresh`. |
| `mv_categoria_por_genero` | Cross-tab categorías por `metadata->>'genero'`. | Requires `genero` in ingestion metadata JSON. |
| `mv_categoria_por_periodo` | Agrupa categorías por `metadata->>'periodo'` (ej. `2010s`, `2020s`). | Populate `periodo` en metadata previo al análisis transversal. |

Maintain this dictionary under version control; accompany structural changes with migrations and regression tests.
