# Arquitectura del Módulo `app/`

Sistema de Análisis Cualitativo con GraphRAG y Teoría Fundamentada.

**Actualizado:** 2025-12-26 | **Total:** 32 módulos

---

## Visión General

```
                            ARQUITECTURA
+------------------------------------------------------------------+
|  Frontend (React)  -->  Backend (FastAPI)  -->  app/ (Core)      |
|                                                    |              |
|                     +-------------+----------------+----------+   |
|                     v             v                v          |   |
|                  Qdrant       PostgreSQL        Neo4j         |   |
|                 (Vector)      (Análisis)       (Grafo)        |   |
+------------------------------------------------------------------+
```

---

## Módulos por Capa (32 archivos)

### 1. Configuración y Conexiones
| Archivo | Responsabilidad | Bytes |
|---------|-----------------|-------|
| `settings.py` | Dataclasses config, carga .env | 11.7K |
| `clients.py` | Factory de conexiones (Neo4j, PG, Qdrant, AOAI) | 7.9K |
| `logging_config.py` | Configuración structlog JSON | 5.0K |
| `logging_utils.py` | Helpers para logging | 2.6K |
| `celery_app.py` | Configuración Celery worker | 1.2K |

### 2. Persistencia de Datos
| Archivo | Responsabilidad | Bytes |
|---------|-----------------|-------|
| `postgres_block.py` | CRUD PostgreSQL (fragmentos, códigos, candidatos) | **68.7K** |
| `neo4j_block.py` | CRUD Neo4j (grafo categorías/códigos) | 9.0K |
| `qdrant_block.py` | CRUD Qdrant (vectores, búsqueda semántica, grouping) | **19.9K** |
| `isolation.py` | Helpers aislamiento por project_id | 3.9K |

### 3. Procesamiento de Documentos
| Archivo | Responsabilidad | Bytes |
|---------|-----------------|-------|
| `documents.py` | Lectura DOCX, fragmentación, parsing speaker | 12.9K |
| `embeddings.py` | Generación embeddings Azure OpenAI | 2.6K |
| `ingestion.py` | Pipeline: DOCX -> fragmentos -> vectores | 14.6K |
| `transcription.py` | Transcripción audio (Whisper) | 36.6K |

### 4. Análisis LLM y Codificación
| Archivo | Responsabilidad | Bytes |
|---------|-----------------|-------|
| `analysis.py` | Análisis LLM con Grounded Theory | 24.9K |
| `coding.py` | Codificación abierta y comparación constante | 23.1K |
| `axial.py` | Codificación axial y relaciones | 11.5K |
| `coherence.py` | Verificación coherencia de códigos | 2.1K |
| `validation.py` | Validación de resultados LLM | 6.8K |
| `code_normalization.py` | **[NEW]** Normalización y fusión de códigos (Levenshtein) | 8.9K |

### 5. GraphRAG y Descubrimiento
| Archivo | Responsabilidad | Bytes |
|---------|-----------------|-------|
| `graphrag.py` | GraphRAG: contexto de grafo para LLM | 13.2K |
| `link_prediction.py` | Predicción de enlaces entre códigos | 19.6K |
| `queries.py` | Consultas híbridas (vector + grafo) + guardrails | 21.6K |
| `transversal.py` | Análisis transversal multi-entrevista | 9.4K |
| `nucleus.py` | Núcleo semántico y patrones centrales | 14.4K |
| `graph_algorithms.py` | **[NEW]** Wrapper unificado algoritmos grafos (Louvain, PageRank, Leiden, HDBSCAN, K-Means) | **32.0K** |

### 6. Reportes y Estado
| Archivo | Responsabilidad | Bytes |
|---------|-----------------|-------|
| `reports.py` | Generación de reportes Stage 4/5 | 21.7K |
| `reporting.py` | Reportes por entrevista | 12.9K |
| `project_state.py` | Gestión estado proyectos + **config por proyecto** | **12.9K** |
| `metadata_ops.py` | Operaciones de metadatos | 12.1K |

### 7. Tareas Asíncronas
| Archivo | Responsabilidad | Bytes |
|---------|-----------------|-------|
| `tasks.py` | Tareas Celery (analyze, ingest) | 5.3K |

---

## Módulos Nuevos (Sprint 13-14)

### `graph_algorithms.py` (32K)
Wrapper unificado para algoritmos de grafos con fallback automático:
- **Neo4j GDS** → **Memgraph MAGE** → **NetworkX/Python**
- Algoritmos: Louvain, PageRank, Betweenness, Leiden, HDBSCAN, K-Means
- Detección automática de motor disponible

### `code_normalization.py` (8.9K)
Normalización Pre-Hoc de códigos candidatos:
- Detección de sinónimos (distancia Levenshtein con rapidfuzz)
- **[NEW] Deduplicación Intra-Batch** (evita Batch Blindness)
- Sugerencias de fusión automáticas
- Limpieza: lowercase, strip, remove_accents

### `queries.py` - Discovery API Híbrido
Estrategia de triangulación semántica:
- **Primario**: Discovery API nativo de Qdrant (`client.discover()`)
- **Fallback**: Vectores ponderados (`avg(pos) - 0.3*neg + 0.3*target`)
- **Control de calidad**: Umbral 0.55 para anclas válidas

### Actualizaciones en `project_state.py`
- Configuración por proyecto: `discovery_threshold`, `analysis_temperature`, `analysis_max_tokens`
- Funciones `get_project_config()`, `update_project_config()`

---

## Flujo de Datos Principal

```
DOCX/Audio --> documents/transcription --> embeddings --> Qdrant
                       |
                       v
                   analysis.py --> LLM Azure
                       |
                       v
               +-------+-------+
               |               |
               v               v
        postgres_block    axial.py --> neo4j_block
        (códigos abiertos)         (grafo categorías)
               |               |
               +-------+-------+
                       |
                       v
              graph_algorithms.py
              (Louvain, PageRank...)
                       |
                       v
                  reports.py
```

---

## Security Features

### Aislamiento por Proyecto
- `isolation.py`: Helpers centralizados (`qdrant_project_filter`, `neo4j_project_clause`)
- `qdrant_block.py`: `project_id` obligatorio con warning si None
- `queries.py`: Whitelist/blocklist Cypher, LIMIT automático

### Conexiones Hardened
- Neo4j: Pool 50, retry 30s, timeout 30s
- PostgreSQL: sslmode=prefer, statement_timeout=30s
- Qdrant: Close correcto con gRPC channel

### LLM Robusto
- `analysis.py`: Retry 3x, size limit 32k, schema validation

---

## Convenciones

### Logging
```python
_logger.info("event.name", key=value, project_id=project_id)
```

### Type Hints
```python
def func(clients: ServiceClients, project: Optional[str] = None) -> Dict[str, Any]:
```

### Aislamiento
```python
from app.isolation import qdrant_project_filter
filter = qdrant_project_filter(project_id, exclude_interviewer=True)
```

### Algoritmos de Grafos
```python
from app.graph_algorithms import GraphAlgorithms
ga = GraphAlgorithms(clients, settings)
communities = ga.louvain(project_id)  # Fallback automático
```

---

## Variables de Entorno

### Azure OpenAI
- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_DEPLOYMENT_CHAT`, `AZURE_OPENAI_DEPLOYMENT_EMBED`

### Qdrant
- `QDRANT_URI`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`

### Neo4j
- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`

### PostgreSQL
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`

### Grafos (Opcional)
- `GRAPH_ENGINE`: auto | neo4j | memgraph | python

---

*Actualizado: 2025-12-27 - Sprint 13-14 Consolidación + Discovery Híbrido + Batch Blindness Fix*


