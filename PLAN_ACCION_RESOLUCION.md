# 🔧 PLAN DE ACCION - RESOLUCION DE PROBLEMAS DETECTADOS

**Fecha:** 16 enero 2026  
**Auditado por:** Sistema de Auditoría  
**Estado:** Pendiente de revisión

---

## 🎯 Problemas Críticos (Resolver ASAP)

### Problema 1: jose-domingo-vg - Códigos sin fragmentos

**Descripción:**
```
Proyecto ID: [a confirmar]
Datos en PostgreSQL:
  - 14 códigos candidatos
  - 0 fragmentos
  - 0 códigos abiertos
```

**Diagnosis:**
Los códigos candidatos fueron creados pero su fuente (fragmentos) no existe o fue eliminada.

**Pasos de Resolución:**

#### Opción A: Investigar el origen
```sql
-- 1. Ver detalles de los códigos candidatos
SELECT id, codigo, created_at, created_by
FROM codigos_candidatos
WHERE project_id = 'jose-domingo-vg'
ORDER BY created_at DESC
LIMIT 5;

-- 2. Ver si hay referencias a fragmentos eliminados
SELECT DISTINCT fragmento_id
FROM codigos_candidatos
WHERE project_id = 'jose-domingo-vg'
AND fragmento_id IS NOT NULL;

-- 3. Ver historial de borrados (si existe)
SELECT * FROM project_audit_log
WHERE project_id = 'jose-domingo-vg'
AND action = 'delete'
ORDER BY created_at DESC;
```

#### Opción B: Limpiar datos inconsistentes
```sql
-- ADVERTENCIA: Esta operación es destructiva

-- 1. Backup (si es necesario)
SELECT * INTO codigos_candidatos_backup_20260116
FROM codigos_candidatos
WHERE project_id = 'jose-domingo-vg';

-- 2. Eliminar códigos sin fragmentos
DELETE FROM codigos_candidatos
WHERE project_id = 'jose-domingo-vg'
AND fragmento_id NOT IN (
  SELECT id FROM entrevista_fragmentos
  WHERE project_id = 'jose-domingo-vg'
);

-- 3. Verificar
SELECT COUNT(*) FROM codigos_candidatos
WHERE project_id = 'jose-domingo-vg';
```

#### Opción C: Restaurar fragmentos
```sql
-- Si los fragmentos fueron eliminados accidentalmente:
-- 1. Verificar si hay backup
SELECT * FROM [tabla_backup] WHERE project_id = 'jose-domingo-vg';

-- 2. Restaurar desde backup
INSERT INTO entrevista_fragmentos
SELECT * FROM [tabla_backup]
WHERE project_id = 'jose-domingo-vg'
AND id NOT IN (SELECT id FROM entrevista_fragmentos WHERE project_id = 'jose-domingo-vg');

-- 3. Sincronizar Neo4j
-- Ejecutar: .\.venv\Scripts\python.exe app/neo4j_sync.py --project-id jose-domingo-vg
```

**Siguiente paso:** Elegir opción según circunstancia y ejecutar.

---

### Problema 2: Qdrant - 98% sin embeddings

**Descripción:**
```
Fragmentos en PostgreSQL: 1,872
Puntos en Qdrant:         38
Cobertura:               2%
Faltantes:               1,834
```

**Causa probable:**
- Ingesta de embeddings no completó
- Solo se calcularon embeddings para ciertos proyectos
- Error en batch processing de OpenAI

**Pasos de Resolución:**

#### Opción A: Recalcular todos los embeddings

```bash
# 1. Verificar que tenemos acceso a OpenAI
.\.venv\Scripts\python.exe -c "
from app.settings import load_settings
settings = load_settings()
print(f'OpenAI API Key: {settings.azure_openai_api_key[:10]}...')
"

# 2. Limpiar colección Qdrant (opcional)
.\.venv\Scripts\python.exe -c "
from app.clients import build_service_clients
from app.settings import load_settings

clients = build_service_clients(load_settings())
# Cuidado: esto elimina todos los embeddings actuales
# clients.qdrant.delete_collection('fragments')
# clients.qdrant.recreate_collection('fragments', size=3072)
clients.close()
"

# 3. Re-ingestar todos los fragmentos con embeddings
.\.venv\Scripts\python.exe app/ingestion.py --embeddings-only
```

#### Opción B: Identificar fragmentos sin embeddings

```python
# Script para identificar gaps
from app.clients import build_service_clients
from app.settings import load_settings

clients = build_service_clients(load_settings())

# Fragmentos en PostgreSQL
with clients.postgres.cursor() as cur:
    cur.execute('SELECT id FROM entrevista_fragmentos ORDER BY id')
    pg_ids = set(row[0] for row in cur.fetchall())

# Puntos en Qdrant
collections = clients.qdrant.get_collections()
qdrant_ids = set()
for coll in collections.collections:
    if 'fragment' in coll.name:
        try:
            result = clients.qdrant.scroll(coll.name, limit=10000)
            for point in result[0]:
                if hasattr(point, 'payload') and 'fragment_id' in point.payload:
                    qdrant_ids.add(point.payload['fragment_id'])
        except:
            pass

# Diferencia
missing = pg_ids - qdrant_ids
print(f'Fragmentos sin embeddings: {len(missing)}')
print(f'Primeros 10: {list(missing)[:10]}')

clients.close()
```

#### Opción C: Cálculo incremental

```bash
# Calcular solo para fragmentos creados recientemente
.\.venv\Scripts\python.exe app/ingestion.py \
  --embeddings-only \
  --since "2026-01-10T00:00:00Z" \
  --batch-size 100
```

**Siguiente paso:** Ejecutar Opción A (más segura y completa).

---

### Problema 3: Neo4j - Sintaxis < 5.0

**Descripción:**
```
Error: Invalid input 'GROUP'
Expected: ','
Query: ... GROUP BY ...
```

**Causa:**
Neo4j < 5.0 no soporta cierta sintaxis Cypher en queries de auditoría.

**Pasos de Resolución:**

#### Paso 1: Verificar versión de Neo4j
```bash
curl -X GET http://localhost:7687/browser \
  -H "Accept: application/json"
```

O desde el contenedor:
```bash
docker exec neo4j neo4j-admin server report | grep -i version
```

#### Paso 2: Actualizar queries si es Neo4j < 5.0

**Consulta vieja (Neo4j 5.0+):**
```cypher
MATCH (n {project_id: $pid})
RETURN labels(n)[0] as label, count(n) as cnt
GROUP BY label
```

**Consulta compatible (Neo4j < 5.0):**
```cypher
MATCH (n {project_id: $pid})
WITH labels(n)[0] as label
RETURN label, count(n) as cnt
```

#### Paso 3: Actualizar scripts Python

En `scripts/audit_global.py`, línea ~70:

```python
# ANTES:
result = session.run(
    'MATCH (n) RETURN labels(n)[0] as label, count(n) as cnt GROUP BY label'
)

# DESPUÉS:
result = session.run(
    'MATCH (n) WITH labels(n)[0] as label RETURN label, count(n) as cnt'
)
```

**Siguiente paso:** Ejecutar si Neo4j < 5.0 confirmado.

---

## ⚠️ Problemas Importantes (Resolver esta semana)

### Problema 4: Blob Storage - Validación incompleta

**Descripción:**
```
51 archivos almacenados
Acceso: Parcialmente validado
```

**Pasos de Resolución:**

#### Paso 1: Validar conexión
```bash
.\.venv\Scripts\python.exe -c "
from azure.storage.blob import BlobServiceClient
from app.settings import load_settings

settings = load_settings()
try:
    client = BlobServiceClient.from_connection_string(
        settings.azure_storage_connection_string
    )
    containers = list(client.list_containers())
    print(f'Conectado: {len(containers)} contenedores')
except Exception as e:
    print(f'Error: {e}')
"
```

#### Paso 2: Verificar integridad de archivos
```python
from azure.storage.blob import BlobServiceClient
from app.settings import load_settings

settings = load_settings()
client = BlobServiceClient.from_connection_string(
    settings.azure_storage_connection_string
)

# Listar todos los archivos
container_client = client.get_container_client('interviews')
blobs = list(container_client.list_blobs())

print(f'Total archivos: {len(blobs)}')

# Verificar que cada uno sea accesible
errors = []
for blob in blobs:
    try:
        properties = container_client.get_blob_client(blob.name).get_blob_properties()
        print(f'✅ {blob.name}: {blob.size} bytes')
    except Exception as e:
        errors.append((blob.name, str(e)))
        print(f'❌ {blob.name}: {e}')

if errors:
    print(f'\nErrores detectados: {len(errors)}')
```

#### Paso 3: Re-sincronizar si es necesario
```bash
# Ejecutar si hay archivos inaccesibles
.\.venv\Scripts\python.exe app/ingestion.py --resync-blob --project-id all
```

**Siguiente paso:** Ejecutar validación de integridad.

---

### Problema 5: Auditoría programada

**Descripción:**
Sistema requiere monitoreo proactivo para evitar inconsistencias futuras.

**Pasos de Resolución:**

#### Opción A: Script cron/scheduler (Linux/Mac)
```bash
# Agregar a /etc/crontab
# Ejecutar cada domingo a las 3am
0 3 * * 0 /home/user/app/.venv/bin/python /home/user/app/scripts/audit_global.py > /home/user/app/logs/audit_$(date +\%Y\%m\%d).txt 2>&1
```

#### Opción B: Task Scheduler (Windows)
```powershell
# Crear tarea programada PowerShell
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3am
$action = New-ScheduledTaskAction -Execute "C:\Users\osval\Downloads\APP_Jupter\.venv\Scripts\python.exe" `
  -Argument "scripts\audit_global.py"
Register-ScheduledTask -TaskName "AuditoriaSistema" -Trigger $trigger -Action $action -RunLevel Highest
```

#### Opción C: Backend scheduled task (Python/APScheduler)

En `app/tasks.py`:
```python
from apscheduler.schedulers.background import BackgroundScheduler
from scripts.audit_global import audit_system

scheduler = BackgroundScheduler()

@scheduler.scheduled_job('cron', day_of_week='sun', hour=3, minute=0)
def audit_job():
    """Auditoria semanal de integridad"""
    audit_system()
    send_email_report()

# En main o app.py:
scheduler.start()
```

**Siguiente paso:** Implementar opción B (Windows Task Scheduler).

---

## 📋 Checklist de Resolución

### Semana 1 (16-22 enero)
- [ ] Investigar jose-domingo-vg
  - [ ] Ejecutar consultas SQL diagnóstico
  - [ ] Decidir si limpiar o restaurar
  - [ ] Ejecutar acción elegida
- [ ] Validar Blob Storage
  - [ ] Verificar conexión
  - [ ] Validar 51 archivos
  - [ ] Re-sincronizar si falla
- [ ] Documentar hallazgos

### Semana 2 (23-29 enero)
- [ ] Calcular embeddings faltantes
  - [ ] Configurar parámetros de batch
  - [ ] Ejecutar en horario de baja carga
  - [ ] Validar completitud
- [ ] Actualizar queries Neo4j
  - [ ] Confirmar versión
  - [ ] Actualizar scripts
  - [ ] Testear

### Semana 3 (30 enero - 5 febrero)
- [ ] Implementar auditoría programada
  - [ ] Elegir método (scheduler/cron/task)
  - [ ] Implementar
  - [ ] Testear al menos 1 ciclo
- [ ] Crear dashboard de monitoreo

---

## 📞 Contacto y Escalación

| Severidad | Responsable | Acción |
|---|---|---|
| CRITICA | [Tu nombre] | Ejecutar inmediatamente |
| ALTA | [Equipo Data] | Esta semana |
| MEDIA | [Equipo Infra] | Próximas 2 semanas |
| BAJA | [PM] | Sprint siguiente |

---

## Notas Importantes

⚠️ **SIEMPRE:**
1. Hacer backup antes de ejecutar DELETE
2. Testear en ambiente de desarrollo primero
3. Documentar cambios en `docs/audit_log.md`
4. Notificar al equipo de cambios

⚠️ **NO:**
1. Ejecutar limpiezas en horario de usuarios activos
2. Cambiar contraseñas/claves sin rotación
3. Eliminar datos sin verificar backup
4. Hacer cambios sin documentar

---

**Documento válido hasta:** 30 enero 2026  
**Próxima revisión:** 23 enero 2026 (post auditoria semanal)

