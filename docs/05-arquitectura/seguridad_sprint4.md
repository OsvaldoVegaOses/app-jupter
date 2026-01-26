# Arquitectura de Seguridad - Sprint 4

## Resumen

Sprint 4 implemento hardening de seguridad y aislamiento en todas las capas del sistema.

---

## 1. Aislamiento por Proyecto

### Qdrant (Vectores)
```python
# search_similar() y discover_search()
if not project_id:
    _logger.warning("no_project_id - using 'default'")
    project_id = "default"

filter = Filter(must=[
    FieldCondition(key="project_id", match=MatchValue(value=project_id))
])
```

**Archivo**: `app/qdrant_block.py`

### Neo4j (Grafo)
```cypher
-- Todas las queries incluyen:
WHERE n.project_id = $project_id
```

**Archivo**: `app/queries.py`

### PostgreSQL
```sql
-- Todas las queries incluyen:
WHERE project_id = %s
```

**Archivo**: `app/postgres_block.py`

---

## 2. Helpers Centralizados

**Archivo**: `app/isolation.py`

```python
from app.isolation import (
    qdrant_project_filter,  # Filter para Qdrant
    neo4j_project_clause,   # WHERE clause para Cypher
    pg_project_clause,      # WHERE clause para SQL
    require_project_id,     # Validacion
)
```

---

## 3. Conexiones Hardened

### Neo4j
```python
GraphDatabase.driver(
    uri,
    auth=(user, password),
    max_connection_pool_size=50,
    max_transaction_retry_time=30.0,
    connection_timeout=30,
)
```

### PostgreSQL
```python
psycopg2.connect(
    ...,
    connect_timeout=10,
    sslmode="prefer",
    options="-c statement_timeout=30000",
)
```

**Archivo**: `app/clients.py`

---

## 4. Guardrails Cypher

### Whitelist de Verbos
```python
ALLOWED_CYPHER_VERBS = {"MATCH", "RETURN", "WITH", "WHERE", "ORDER", "LIMIT", "OPTIONAL", "UNWIND", "CALL"}
```

### Blocklist de Patrones
```python
BLOCKED_CYPHER_PATTERNS = {"apoc.", "dbms.", "DELETE", "DETACH", "DROP", "CREATE", "MERGE", "SET", "REMOVE"}
```

### LIMIT Automatico
```python
if "LIMIT" not in cypher_upper:
    cypher = f"CALL {{ {cypher} }} LIMIT {max_rows}"
```

**Archivo**: `app/queries.py`

---

## 5. JSON Parsing Robusto

```python
# call_llm_chat_json()
- Limite tamanyo: 32k chars
- Retry: hasta 3 intentos
- Validacion schema: etapa3_matriz_abierta requerido
- Logging: errores truncados
```

**Archivo**: `app/analysis.py`

---

## 6. Tests de Verificacion

| Test | Archivo | Verifica |
|------|---------|----------|
| Aislamiento PG | `tests/test_project_isolation.py` | Fragmentos por proyecto |
| Aislamiento Qdrant | `tests/test_project_isolation.py` | Busquedas filtradas |
| Aislamiento Neo4j | `tests/test_project_isolation.py` | Nodos por proyecto |
| JSON malformado | `tests/test_json_parsing.py` | Retry y fallback |

---

## Comandos

```bash
# Ejecutar tests
python tests/test_project_isolation.py
python tests/test_json_parsing.py

# Verificar sintaxis
python -m py_compile app/isolation.py app/qdrant_block.py app/queries.py
```

---

*Diciembre 2024*
