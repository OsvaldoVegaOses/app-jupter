# Plan de Pruebas: Sprint 4 Security Hardening

## Resumen

Este documento describe las pruebas para validar el Sprint 4 (Security Hardening).

---

## 1. Pruebas Automatizadas

### 1.1 Test de Aislamiento por Proyecto
```bash
python tests/test_project_isolation.py
```

**Verifica:**
- PostgreSQL: Fragmentos solo visibles en su proyecto
- Qdrant: Búsquedas filtradas por project_id
- Neo4j: Nodos aislados por project_id

**Datos de prueba:** `data/test_interviews/transcription_interviews/Claudia_Cesfam.docx`

### 1.2 Test de Parsing JSON
```bash
python tests/test_json_parsing.py
```

**Verifica:**
- JSON válido parseado correctamente
- JSON con texto extra extraído
- Missing keys trigger retry
- Malformed JSON falla gracefully
- Respuestas >32k truncadas

---

## 2. Pruebas Manuales

### 2.1 Verificar Conexiones Hardened

1. **Neo4j TLS:**
   ```python
   from app.clients import build_service_clients
   from app.settings import load_settings
   
   clients = build_service_clients(load_settings())
   # Si falla con SSL error, verificar que Neo4j tenga TLS habilitado
   ```

2. **PostgreSQL Timeout:**
   ```sql
   -- Desde psql, verificar settings
   SHOW statement_timeout;  -- Debe ser 30s
   SHOW application_name;   -- Debe ser app_jupter
   ```

### 2.2 Verificar Guardrails de Cypher

```python
from app.queries import run_cypher
from app.clients import build_service_clients
from app.settings import load_settings

clients = build_service_clients(load_settings())

# Debería fallar: verbo no permitido
try:
    run_cypher(clients, "DELETE (n) RETURN n")
except ValueError as e:
    print(f"✓ Bloqueado: {e}")

# Debería fallar: patrón bloqueado
try:
    run_cypher(clients, "MATCH (n) CALL apoc.help('test')")
except ValueError as e:
    print(f"✓ Bloqueado: {e}")

# Debería pasar: query válida
result = run_cypher(clients, "MATCH (n) RETURN n LIMIT 5")
print(f"✓ Resultado: {len(result['raw'])} rows")
```

### 2.3 Verificar Qdrant Wrappers

```python
from app.qdrant_block import search_similar
from app.clients import build_service_clients
from app.settings import load_settings

clients = build_service_clients(load_settings())
settings = load_settings()

# Crear vector de prueba
vector = clients.aoai.embeddings.create(
    model=settings.azure.deployment_embed,
    input="participación comunitaria"
).data[0].embedding

# Buscar con project_id
results = search_similar(
    clients.qdrant,
    settings.qdrant.collection,
    vector,
    project_id="mi_proyecto",
    exclude_interviewer=True,
    limit=5,
)
# Verificar que todos los resultados tengan el project_id correcto
```

---

## 3. Lista de Verificación Manual

### Conexiones
- [ ] Neo4j conecta con TLS (o falla con error claro si no hay TLS)
- [ ] PostgreSQL muestra statement_timeout=30s
- [ ] PostgreSQL muestra application_name=app_jupter

### Guardrails Cypher
- [ ] DELETE bloqueado
- [ ] apoc.* bloqueado
- [ ] MATCH/RETURN permitido
- [ ] LIMIT automático aplicado

### Qdrant
- [ ] search_similar requiere project_id
- [ ] exclude_interviewer funciona
- [ ] limit cap en 100

### JSON Parsing
- [ ] Retry en schema incorrecto
- [ ] Truncamiento en 32k chars
- [ ] Log de errores truncado

---

## 4. Archivos de Prueba Disponibles

### Transcripciones (data/test_interviews/transcription_interviews/)
| Archivo | Tamaño | Uso Recomendado |
|---------|--------|-----------------|
| Claudia_Cesfam.docx | 32KB | Pruebas rápidas |
| Comite de Vivienda Santa Ana.docx | 76KB | Pruebas medianas |
| Natalia Molina.docx | 2MB | Stress test |

---

## 5. Comandos Rápidos

```bash
# Iniciar servicios
docker compose up -d

# Ejecutar todas las pruebas
python tests/test_project_isolation.py
python tests/test_json_parsing.py

# Verificar sintaxis de archivos modificados
python -m py_compile app/qdrant_block.py app/clients.py app/queries.py app/analysis.py app/isolation.py
```
