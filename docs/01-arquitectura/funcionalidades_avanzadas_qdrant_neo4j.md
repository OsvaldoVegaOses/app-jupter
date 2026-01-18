# Arquitectura de Bases de Datos y Algoritmos Avanzados

Este documento describe las funcionalidades avanzadas de Qdrant, Neo4j y PostgreSQL utilizadas en el sistema de análisis cualitativo, incluyendo estrategias de fallback y decisiones de diseño.

---

## Tabla de Contenidos

1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Qdrant - Base de Datos Vectorial](#qdrant---base-de-datos-vectorial)
3. [Neo4j - Base de Datos de Grafos](#neo4j---base-de-datos-de-grafos)
4. [PostgreSQL - Extensiones Avanzadas](#postgresql---extensiones-avanzadas)
5. [Estrategias de Fallback](#estrategias-de-fallback)
6. [Matriz de Decisión](#matriz-de-decisión)
7. [Configuración y Umbrales](#configuración-y-umbrales)

---

## Resumen Ejecutivo

El sistema utiliza una arquitectura de bases de datos especializadas con fallbacks automáticos:

| Base de Datos | Propósito | Features Avanzados |
|---------------|-----------|-------------------|
| **Qdrant** | Búsqueda semántica | Discovery API, Grouped Search, Hybrid Search |
| **Neo4j** | Análisis de grafos | GDS Algorithms, Link Prediction |
| **PostgreSQL** | Persistencia + Fuzzy Match | fuzzystrmatch, Levenshtein |

### Principios de Diseño

1. **Fallback Automático**: Si el feature avanzado falla, usar alternativa robusta
2. **Control de Calidad**: Validar inputs antes de usar APIs nativos
3. **Logging Detallado**: Registrar qué método se usó y por qué
4. **Umbrales Configurables**: Parámetros ajustables sin cambiar código

---

## Qdrant - Base de Datos Vectorial

### 1. Discovery API (Triangulación Semántica)

**Archivo**: `app/queries.py:discover_search()`

**Propósito**: Búsqueda exploratoria con contexto positivo/negativo para Codificación Selectiva.

**Estrategia Híbrida Implementada**:

```
┌─────────────────────────────────────────────────────────────┐
│  Usuario ingresa: Target + Positivos + Negativos (textos)  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  PASO 1: Generar embeddings para todos los textos          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  PASO 2: Buscar IDs representativos + VALIDAR CALIDAD      │
│  - Score >= 0.55 → Ancla válida                            │
│  - Score < 0.55  → Ancla rechazada (evita envenenamiento)  │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
┌──────────────────────────┐   ┌──────────────────────────────┐
│  ≥1 ancla válida         │   │  Sin anclas válidas          │
│  → Discovery API Nativo  │   │  → Fallback Ponderado        │
│     client.discover()    │   │     avg(pos) - 0.3*neg       │
└──────────────────────────┘   └──────────────────────────────┘
```

**Control de Calidad de Anclas**:

```python
ANCHOR_QUALITY_THRESHOLD = 0.55  # Score mínimo

if point.score >= ANCHOR_QUALITY_THRESHOLD:
    positive_ids.append(point.id)  # ✅ Ancla válida
else:
    weak_anchors.append(...)       # ⚠️ Rechazada
    _logger.warning("discover.weak_anchors_rejected", ...)
```

**Logs Generados**:

| Evento | Descripción |
|--------|-------------|
| `discover.using_native` | Usó API nativo con anclas válidas |
| `discover.using_fallback` | Usó vectores ponderados |
| `discover.weak_anchors_rejected` | Anclas rechazadas por baja calidad |
| `discover.native.complete` | Búsqueda nativa exitosa |
| `discover.fallback.complete` | Fallback exitoso |

**Resultado**: Campo `discovery_type` indica método usado (`"native"` | `"fallback"`).

---

### 2. Grouped Search (Evitar Sesgo de Fuente)

**Archivo**: `app/qdrant_block.py:search_similar_grouped()`

**Propósito**: Muestreo teórico equilibrado entre fuentes (entrevistas).

```python
results = search_similar_grouped(
    client, "fragmentos", vector,
    group_by="archivo",      # Agrupar por entrevista
    group_size=2,            # Máx 2 fragmentos por grupo
    limit=10,                # 10 grupos totales
    genero="mujer",          # Filtro demográfico
    actor_principal="dirigente",
)
```

**Campos de Agrupación**:

| Campo | Uso Metodológico |
|-------|------------------|
| `archivo` | Evitar que una entrevista domine |
| `speaker` | Separar entrevistador/entrevistado |
| `actor_principal` | Comparar entre tipos de actores |
| `genero` | Análisis de género |
| `area_tematica` | Comparación entre áreas |

**Fallback**: Si `search_groups()` falla, usa `search_similar()` regular.

---

### 3. Hybrid Search (Dense + Keyword)

**Archivo**: `app/qdrant_block.py:search_hybrid()`

**Propósito**: Combinar semántica con palabras clave exactas.

```python
results = search_hybrid(
    client, "fragmentos",
    query_text="PAC rural",      # Keyword matching
    vector=embedding,             # Semantic matching
    keyword_boost=0.3,           # Bonus para keyword matches
)
```

**Estrategia**:

1. Búsqueda semántica (embeddings) → conceptos abstractos
2. Búsqueda keyword (índice `text`) → acrónimos, términos técnicos
3. Fusión con boost para resultados que matchean ambos

**Índices Requeridos**:

```python
ensure_payload_indexes(client, collection):
    # Índices keyword para filtrado
    ("project_id", "keyword"),
    ("archivo", "keyword"),
    ("speaker", "keyword"),
    ("area_tematica", "keyword"),
    ("genero", "keyword"),
    # Índice text para búsqueda full-text
    ("fragmento", "text"),
```

---

## Neo4j - Base de Datos de Grafos

### 1. Graph Data Science (GDS) Algorithms

**Archivo**: `app/graph_algorithms.py`

**Clase**: `GraphAlgorithms` con detección automática de motor.

```python
from app.graph_algorithms import GraphAlgorithms, GraphEngine

ga = GraphAlgorithms(clients, settings)
print(ga.engine)  # NEO4J_GDS | MEMGRAPH_MAGE | NETWORKX
```

**Algoritmos Disponibles**:

| Algoritmo | Neo4j GDS | Memgraph | Python | Uso |
|-----------|-----------|----------|--------|-----|
| Louvain | ✅ | ✅ | ✅ | Comunidades de códigos |
| PageRank | ✅ | ✅ | ✅ | Códigos centrales |
| Betweenness | ✅ | ✅ | ✅ | Códigos puente |
| Leiden | ✅ | ❌ | ✅ | Comunidades (mejor que Louvain) |
| HDBSCAN | ❌ | ❌ | ✅ | Clustering jerárquico |
| K-Means | ❌ | ❌ | ✅ | Clustering partitivo |

**Detección de Motor**:

```python
def _detect_engine(self) -> GraphEngine:
    # 1. Intentar Neo4j GDS
    try:
        session.run("RETURN gds.version()")
        return GraphEngine.NEO4J_GDS
    except:
        pass
    
    # 2. Intentar Memgraph MAGE
    try:
        session.run("CALL mg.procedures()")
        return GraphEngine.MEMGRAPH_MAGE
    except:
        pass
    
    # 3. Fallback a NetworkX
    return GraphEngine.NETWORKX
```

**Graph Projections (Performance)**:

```python
# Proyección en memoria para algoritmos rápidos
def _create_gds_projection(session, graph_name, project_id):
    node_query = """
        MATCH (n) WHERE n.project_id = $project_id 
        AND (n:Categoria OR n:Codigo)
        RETURN id(n) AS id
    """
    rel_query = """
        MATCH (s)-[r:REL]->(t) 
        WHERE s.project_id = $project_id
        RETURN id(s) AS source, id(t) AS target
    """
    session.run("CALL gds.graph.project.cypher(...)")
```

---

### 2. Link Prediction

**Archivo**: `app/link_prediction.py`

**Propósito**: Descubrir relaciones faltantes en el grafo de codificación.

**Algoritmos Implementados**:

| Algoritmo | Fórmula | Uso |
|-----------|---------|-----|
| Common Neighbors | \|N(u) ∩ N(v)\| | Códigos con contexto similar |
| Jaccard | \|N(u) ∩ N(v)\| / \|N(u) ∪ N(v)\| | Normalizado por tamaño |
| Adamic-Adar | Σ 1/log(\|N(w)\|) | Pondera por rareza de vecinos |
| Preferential Attachment | \|N(u)\| × \|N(v)\| | Códigos populares se conectan |

**Funciones Principales**:

```python
# Sugerir enlaces por algoritmo específico
suggestions = suggest_links(clients, settings,
    source_type="Categoria",
    target_type="Codigo",
    algorithm="common_neighbors",
    top_k=10,
    project="mi_proyecto"
)

# Descubrir relaciones ocultas (combina 3 métodos)
hidden = discover_hidden_relationships(clients, settings,
    project="mi_proyecto",
    top_k=20
)

# Métodos combinados:
# 1. Co-ocurrencia en fragmentos
# 2. Similitud estructural (link prediction)
# 3. Misma comunidad sin conexión (Louvain)
```

---

## PostgreSQL - Extensiones Avanzadas

### 1. Extensión fuzzystrmatch (Levenshtein)

**Archivo**: `backend/app.py`

**Propósito**: Detección de códigos duplicados post-hoc.

```sql
-- Habilitar extensión
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;

-- Query de detección OPTIMIZADA
WITH unique_codes AS (
    SELECT DISTINCT codigo, LENGTH(codigo) AS len
    FROM codigos_candidatos
    WHERE project_id = $1 AND estado IN ('pendiente', 'validado')
)
SELECT 
    c1.codigo AS code1,
    c2.codigo AS code2,
    levenshtein(LOWER(c1.codigo), LOWER(c2.codigo)) AS distance,
    1.0 - (levenshtein(...) / GREATEST(c1.len, c2.len)) AS similarity
FROM unique_codes c1, unique_codes c2
WHERE c1.codigo < c2.codigo
  -- OPTIMIZACIÓN: Pre-filtro por longitud (evita O(N²) completo)
  AND ABS(c1.len - c2.len) <= max_distance
  AND levenshtein(...) <= max_distance
  AND levenshtein(...) > 0
ORDER BY similarity DESC
```

**Optimización de Rendimiento**:

| Problema | Solución |
|----------|----------|
| CROSS JOIN = O(N²) | Pre-filtro por longitud reduce a O(N*k) |
| 1,000 códigos = 1M comparaciones | Con filtro ~50k comparaciones |
| Levenshtein costoso | Solo se calcula si pasa filtro |

**Lógica**: Si `max_distance = 3`, no tiene sentido comparar "Organización" (12 chars) con "Si" (2 chars) porque la diferencia de longitud (10) ya garantiza que la distancia será > 3.

**Endpoints**:

| Endpoint | Descripción |
|----------|-------------|
| `POST /api/codes/detect-duplicates` | Detectar duplicados históricos |
| `GET /api/codes/similar` | Buscar similares para fusión |

---


### 2. Normalización Pre-Hoc (Python)

**Archivo**: `app/code_normalization.py`

**Propósito**: Prevenir duplicados ANTES de insertar.

```python
from app.code_normalization import normalize_code, find_similar_codes

# Normalización
normalize_code("Organización_Social")  # → "organizacion social"

# Detección de similares
similar = find_similar_codes('organizacion', ['organización', 'territorio'])
# → [('organización', 0.92)]
```

**Transformaciones de `normalize_code()`**:

1. Minúsculas
2. Eliminar acentos/tildes (excepto ñ→n)
3. Reemplazar guiones/underscores por espacios
4. Colapsar espacios múltiples
5. Strip whitespace

**Biblioteca**: `rapidfuzz` (con fallback a `difflib.SequenceMatcher`)

---

### 3. Deduplicación Intra-Batch (Corrección Batch Blindness)

**Archivo**: `app/code_normalization.py:suggest_code_merge()`

**Problema Detectado**: Cuando múltiples códigos idénticos llegaban en el mismo lote (ej: desde Link Prediction), el sistema los comparaba contra la BD pero NO contra otros códigos en el mismo batch.

**Solución Implementada**:

```python
def suggest_code_merge(
    new_codes: List[Dict],
    existing_codes: List[str],
    threshold: float = 0.85,
    deduplicate_batch: bool = True,  # ← NUEVO
) -> List[Dict]:
```

**Flujo de Deduplicación**:

```
┌─────────────────────────────────────────────────────────┐
│  Link Prediction genera 5 códigos "inundaciones"        │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  PASO 1: Agrupar por código normalizado                 │
│  batch_groups["inundaciones"] = [cod1, cod2, cod3, ...] │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  PASO 2: Fusionar duplicados intra-batch                │
│  - Combinar citas: "Cita1 | Cita2 | Cita3"             │
│  - Tomar max(score_confianza)                          │
│  - Marcar: _batch_merged=True, _batch_count=5           │
│  - Memo: "[BATCH-MERGE] 5 entradas fusionadas"          │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  PASO 3: Comparar contra BD (como antes)               │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  RESULTADO: 1 código "inundaciones" con 5 evidencias    │
└─────────────────────────────────────────────────────────┘
```

**Logs Generados**:

| Evento | Descripción |
|--------|-------------|
| `code_normalization.batch_duplicates_merged` | Código fusionado con detalles |
| `code_normalization.batch_blindness_prevented` | Resumen de deduplicación |

---

### 4. Detección Post-Hoc Mejorada

**Archivo**: `backend/app.py:find_similar_codes_posthoc()`

**Mejora**: Ahora detecta duplicados exactos (mismo código, diferentes entradas) además de similares fuzzy.

```python
def find_similar_codes_posthoc(
    pg_conn,
    project_id: str,
    threshold: float = 0.80,
    include_exact: bool = True,  # ← NUEVO
) -> List[Dict]:
```

**Resultado Mejorado**:

```json
[
  {
    "code1": "inundaciones",
    "code2": "inundaciones",
    "distance": 0,
    "similarity": 1.0,
    "is_exact_duplicate": true,
    "duplicate_count": 5,
    "sources": ["link_prediction", "discovery"],
    "files": ["entrevista1.docx", "entrevista2.docx"]
  },
  {
    "code1": "organizacion",
    "code2": "organización", 
    "distance": 1,
    "similarity": 0.92,
    "is_exact_duplicate": false
  }
]
```

---


## Estrategias de Fallback

### Tabla de Fallbacks

| Feature | Primario | Secundario | Terciario |
|---------|----------|------------|-----------|
| Discovery Search | Qdrant `discover()` | Vector ponderado | - |
| Graph Algorithms | Neo4j GDS | Memgraph MAGE | NetworkX/Python |
| Leiden | Neo4j GDS | igraph/leidenalg | Louvain (NetworkX) |
| HDBSCAN | - | - | hdbscan (Python) |
| Fuzzy Match | rapidfuzz | difflib | Levenshtein (SQL) |

### Logs de Fallback

```python
_logger.warning(
    "discover.native.failed_fallback",
    error=str(e),
    reason="Using weighted vector fallback",
)

_logger.warning(
    "graph_algorithms.mage_failed_fallback",
    algorithm="louvain",
    error=str(e),
)
```

---

## Matriz de Decisión

### Cuándo usar cada método

| Escenario | Método Recomendado | Razón |
|-----------|-------------------|-------|
| Concepto existe en BD (score ≥0.55) | Discovery Nativo | Más preciso |
| Concepto abstracto/nuevo | Fallback Ponderado | Flexible |
| Neo4j GDS disponible | GDS Algorithms | 10-100x más rápido |
| Sin GDS | NetworkX/Python | Universal |
| Datos históricos sucios | Levenshtein (SQL) | Post-hoc |
| Nuevo código entrando | rapidfuzz (Python) | Pre-hoc |

---

## Configuración y Umbrales

### Umbrales Configurables

| Parámetro | Valor | Archivo | Descripción |
|-----------|-------|---------|-------------|
| `ANCHOR_QUALITY_THRESHOLD` | 0.55 | `queries.py` | Mínimo para ancla Discovery |
| `SIMILARITY_THRESHOLD` | 0.85 | `code_normalization.py` | Pre-hoc fuzzy match |
| `DISCOVERY_THRESHOLD` | 0.35 | `code_normalization.py` | Mínimo para Discovery |
| Post-hoc threshold | 0.80 | `app.py` | Levenshtein detección |

### Variables de Entorno

| Variable | Valores | Default | Descripción |
|----------|---------|---------|-------------|
| `GRAPH_ENGINE` | `auto\|neo4j\|memgraph\|python` | `auto` | Forzar motor de grafos |

---

## Referencias

- [Qdrant Discovery API](https://qdrant.tech/documentation/concepts/explore/)
- [Neo4j GDS Library](https://neo4j.com/docs/graph-data-science/)
- [PostgreSQL fuzzystrmatch](https://www.postgresql.org/docs/current/fuzzystrmatch.html)
- [rapidfuzz Documentation](https://rapidfuzz.github.io/RapidFuzz/)

---

*Última actualización: 2025-12-27*
