# Scripts de Auditoría - Guía de Uso

## Scripts Disponibles

### 1. `audit_global.py`
Auditoría de todo el sistema. Muestra todos los proyectos y conteos globales.

```bash
.\.venv\Scripts\python.exe scripts/audit_global.py
```

**Salida:**
- Lista de todos los proyectos registrados
- Total de fragmentos, códigos, archivos
- Conteos en Neo4j, Qdrant
- Matriz de consistencia

### 2. `audit_project_specific.py`
Auditoría específica de un proyecto por UUID.

```bash
.\.venv\Scripts\python.exe scripts/audit_project_specific.py
```

**Audita:**
- PostgreSQL (fragmentos, códigos, códigos candidatos)
- Neo4j (nodos asociados)
- Qdrant (colecciones específicas)
- Blob Storage (archivos de proyecto)

### 3. `audit_storage_state.py`
Auditoría completa con opciones avanzadas.

```bash
# Solo diagnóstico
.\.venv\Scripts\python.exe scripts/audit_storage_state.py \
  --project-id [uuid] \
  --account [email] \
  --diagnose

# Con detalles
.\.venv\Scripts\python.exe scripts/audit_storage_state.py \
  --project-id [uuid] \
  --detailed

# Exportar a JSON
.\.venv\Scripts\python.exe scripts/audit_storage_state.py \
  --project-id [uuid] \
  --format json
```

### 4. `clean_orphan_files.py` (Existente)
Limpieza de archivos huérfanos.

```bash
# Diagnóstico
.\.venv\Scripts\python.exe scripts/clean_orphan_files.py \
  --project [project-id] \
  --diagnose

# Limpiar
.\.venv\Scripts\python.exe scripts/clean_orphan_files.py \
  --project [project-id] \
  --clean
```

---

## Casos de Uso Comunes

### Caso 1: "Mi proyecto no aparece"

```bash
# 1. Verificar si existe en el sistema
.\.venv\Scripts\python.exe scripts/audit_global.py

# 2. Si no aparece, crear proyecto via API
curl -X POST http://localhost:8000/api/projects \
  -H "X-API-Key: [clave]" \
  -H "Content-Type: application/json" \
  -d '{"name": "Mi Proyecto"}'
```

### Caso 2: "Perdí datos en un proyecto"

```bash
# 1. Auditar el proyecto específico
.\.venv\Scripts\python.exe scripts/audit_storage_state.py \
  --project-id [uuid] \
  --detailed

# 2. Verificar fragmentos en PostgreSQL
.\.venv\Scripts\python.exe -c "
from app.clients import build_service_clients
from app.settings import load_settings

clients = build_service_clients(load_settings())
with clients.postgres.cursor() as cur:
    cur.execute(
        'SELECT archivo, COUNT(*) FROM entrevista_fragmentos WHERE project_id = %s GROUP BY archivo',
        ('[uuid]',)
    )
    for row in cur.fetchall():
        print(f'{row[0]}: {row[1]} fragmentos')
clients.close()
"

# 3. Si hay fragmentos pero no en Neo4j/Qdrant, re-sincronizar
.\.venv\Scripts\python.exe backend/app.py --resync [uuid]
```

### Caso 3: "Bases de datos inconsistentes"

```bash
# 1. Auditoría global
.\.venv\Scripts\python.exe scripts/audit_global.py

# 2. Si hay inconsistencias, ejecutar limpieza
.\.venv\Scripts\python.exe scripts/clean_orphan_files.py \
  --project [project-id] \
  --diagnose

# 3. Verificar integridad post-limpieza
.\.venv\Scripts\python.exe scripts/audit_storage_state.py \
  --project-id [uuid]
```

### Caso 4: "Embeddings faltantes"

```bash
# 1. Verificar fragmentos vs Qdrant
.\.venv\Scripts\python.exe -c "
from app.clients import build_service_clients
from app.settings import load_settings

clients = build_service_clients(load_settings())

# PostgreSQL
with clients.postgres.cursor() as cur:
    cur.execute('SELECT COUNT(*) FROM entrevista_fragmentos WHERE project_id = %s')
    pg_count = cur.fetchone()[0]

# Qdrant
collections = clients.qdrant.get_collections()
qdrant_count = 0
for c in collections.collections:
    info = clients.qdrant.get_collection(c.name)
    qdrant_count += info.points_count

print(f'PostgreSQL: {pg_count}')
print(f'Qdrant: {qdrant_count}')
print(f'Faltantes: {pg_count - qdrant_count}')

clients.close()
"

# 2. Re-calcular embeddings (requiere LLM)
.\.venv\Scripts\python.exe -m app.ingestion --project [uuid] --embeddings-only
```

---

## Consultas SQL Útiles

### Top archivos por volumen
```sql
SELECT archivo, COUNT(*) as fragmentos
FROM entrevista_fragmentos
WHERE project_id = '[uuid]'
GROUP BY archivo
ORDER BY COUNT(*) DESC;
```

### Códigos sin fragmentos
```sql
SELECT codigo, COUNT(*) as citas
FROM analisis_codigos_abiertos
WHERE project_id = '[uuid]'
GROUP BY codigo
ORDER BY COUNT(*) DESC;
```

### Fragmentos sin códigos
```sql
SELECT f.id, f.archivo, f.indice
FROM entrevista_fragmentos f
LEFT JOIN analisis_codigos_abiertos c ON f.id = c.fragmento_id
WHERE f.project_id = '[uuid]' AND c.id IS NULL;
```

### Archivos huérfanos (sin fragmentos)
```sql
SELECT DISTINCT archivo
FROM (
  SELECT DISTINCT archivo FROM entrevista_fragmentos WHERE project_id = '[uuid]'
) f
WHERE NOT EXISTS (
  SELECT 1 FROM entrevista_fragmentos WHERE archivo = f.archivo AND project_id = '[uuid]'
);
```

---

## Monitoreo Proactivo

### Script de supervisión mensual
```bash
#!/bin/bash
# Ejecutar cada 1er domingo del mes

DATE=$(date +%Y%m%d)
.\.venv\Scripts\python.exe scripts/audit_global.py > logs/audit_$DATE.txt
.\.venv\Scripts\python.exe scripts/clean_orphan_files.py --project '*' --diagnose \
  > logs/orphans_$DATE.txt
```

### Alertas a monitorear
- ⚠️ Fragmentos > 5,000 sin embeddings
- ⚠️ Códigos candidatos sin fragmentos
- ⚠️ Neo4j nodos < 50% de PostgreSQL
- ⚠️ Blob Storage inaccesible

---

## Solución de Problemas

### Error: "relation does not exist"
**Causa:** Tabla faltante o nombre incorrecto
**Solución:**
```bash
.\.venv\Scripts\python.exe -c "
from app.clients import build_service_clients
from app.settings import load_settings

clients = build_service_clients(load_settings())
with clients.postgres.cursor() as cur:
    cur.execute('''
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    ''')
    for row in cur.fetchall():
        print(row[0])
clients.close()
"
```

### Error: "Neo4j driver connection timeout"
**Causa:** Neo4j no responde
**Solución:**
```bash
# Verificar status
docker exec neo4j neo4j-admin server report

# O verificar via endpoint
curl -X POST http://localhost:7687/browser/ping
```

### Error: "Qdrant collection not found"
**Causa:** Collection eliminada o nombre incorrecto
**Solución:**
```bash
.\.venv\Scripts\python.exe -c "
from app.clients import build_service_clients
from app.settings import load_settings

clients = build_service_clients(load_settings())
collections = clients.qdrant.get_collections()
for c in collections.collections:
    print(c.name)
clients.close()
"
```

---

## Notas Importantes

1. **Siempre hacer backup** antes de ejecutar `--clean`
2. **Validar en --diagnose primero** antes de limpiar
3. **Ejecutar en horarios de baja carga** para no afectar usuarios
4. **Revisar logs** después de cualquier operación
5. **Documentar cambios** en `docs/audit_log.md`

---

*Última actualización: 16 enero 2026*
