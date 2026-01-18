# Troubleshooting: Connection Pool Issues

> **Fecha de creación**: 2026-01-06
> **Estado**: Resuelto (con monitoreo activo)

---

## Índice de Problemas

| # | Problema | Estado | Fecha Resolución |
|---|----------|--------|------------------|
| 1 | Pool exhausted después de operaciones | ✅ Resuelto | 2026-01-06 |
| 2 | Usuarios table perdida | ✅ Resuelto | 2026-01-06 |
| 3 | Proyecto eliminado pero sigue en lista | ✅ Resuelto | 2026-01-06 |
| 4 | Statement timeout en /api/coding/stats | ✅ Resuelto | 2026-01-07 |
| 5 | Neo4j "defunct connection" error | ✅ Resuelto | 2026-01-07 |
| 6 | Contadores Neo4j no coinciden | ✅ Resuelto | 2026-01-17 |

---

## Problema 1: Connection Pool Exhausted

### Síntomas
- Backend deja de responder después de 2-3 ciclos de crear/eliminar proyecto
- Error: `psycopg2.pool.PoolError: connection pool exhausted`
- Login se queda en "Ingresando..." indefinidamente

### Causa Raíz
Múltiples routers tenían `get_service_clients()` que **no devolvía conexiones al pool**:

```python
# ❌ INCORRECTO - conexión nunca se cierra
def get_service_clients():
    return build_service_clients(settings)
```

### Solución Aplicada
Convertir a patrón `AsyncGenerator` con yield + finally:

```python
# ✅ CORRECTO - FastAPI cierra automáticamente
async def get_service_clients() -> AsyncGenerator[ServiceClients, None]:
    clients = build_service_clients(settings)
    try:
        yield clients
    finally:
        clients.close()
```

### Archivos Modificados
- `backend/routers/auth.py` - líneas 23-35
- `backend/routers/admin.py` - líneas 17-33
- `backend/routers/interviews.py` - líneas 37-48
- `backend/routers/ingest.py` - líneas 53-64

### Configuración del Pool
```python
# app/clients.py líneas 63-74
minconn=10,   # Era 2
maxconn=80,   # Era 20
```

---

## Problema 2: Tabla Users Perdida

### Síntomas
- Login falla con "Credenciales inválidas"
- Error en logs: `relation "users" does not exist`

### Causa Raíz
La tabla `users` no se crea automáticamente en Azure PostgreSQL.
Requiere ejecutar `ensure_users_table()` manualmente.

### Solución Aplicada
```bash
# Ejecutar cuando la tabla no existe
python scripts/create_admin.py --email admin@example.com --password "SecurePass!"
```

### Prevención
- Agregar migración en startup del backend (TODO)

---

## Problema 3: Proyecto Eliminado Sigue en Lista

### Síntomas
- Se muestra mensaje "Proyecto eliminado" exitosamente
- Pero el proyecto sigue apareciendo en el dropdown

### Causa Raíz
El endpoint `DELETE /api/projects/{id}` eliminaba datos de:
- Neo4j ✅
- Qdrant ✅
- PostgreSQL (fragmentos, códigos, etc.) ✅
- Registry JSON ✅

Pero **NO eliminaba de la tabla `proyectos`** en PostgreSQL.

### Solución Aplicada
```python
# backend/app.py línea ~1131-1138
cur.execute("DELETE FROM proyectos WHERE id = %s", (project_id,))
results["deleted"]["pg_proyectos"] = cur.rowcount
```

---

## Problema 4: Statement Timeout en /api/coding/stats

### Síntomas
- Error en logs: `canceling statement due to statement timeout`
- Pool no libera conexiones después del timeout
- App se desconecta después de varios requests

### Causa Raíz
- Query de estadísticas muy lento (>10 minutos original timeout)
- Cuando PostgreSQL cancela el query, la conexión queda en estado inválido
- El finally del generador de FastAPI no siempre se ejecuta con timeouts largos

### Solución Aplicada (RESUELTO - 2026-01-07)
1. **Timeout reducido a 30 segundos** en el endpoint específico:
```python
with clients.postgres.cursor() as cur:
    cur.execute("SET statement_timeout = '30s'")
```

2. **Catch-all exception handler** que devuelve stats vacías en vez de fallar:
```python
except Exception as exc:
    _logger.warning("api.coding.stats.timeout_or_error", ...)
    return {"total_codes": 0, "error": "Stats temporarily unavailable"}
```

3. **Rollback antes de putconn** (aplicado anteriormente):
```python
conn.rollback()  # Limpia transacción fallida
_pg_pool.putconn(conn)
```

## Trabajo Pendiente

### Prioridad MEDIA: Optimizar Query de Coding Statistics
- **Problema**: El query de `coding_statistics` tarda >30 segundos, causando timeouts
- **Impacto**: UI se "congela" brevemente al crear proyectos (~1 minuto)
- **Workaround actual**: Timeout de 30s + retorno de stats vacías
- **Solución propuesta**:
  1. Analizar query en `app/coding.py::coding_statistics`
  2. Agregar índices faltantes a PostgreSQL
  3. Implementar caché para stats que no cambian frecuentemente
- **Estado**: NO hay leaks (585 getconn = 585 putconn). Sistema se recupera solo.

### Prioridad BAJA: Migrar endpoints a Depends pattern
- 59 endpoints usan `build_clients_or_error()` + try/finally
- Funcionan correctamente, pero `Depends(get_service_clients)` es más idiomático
- NO es urgente - código actual funciona sin leaks

---

## Monitoreo Activo

### Logs a Observar
```bash
# Buscar problemas de pool
Select-String -Path logs\app.jsonl -Pattern "pool.nearly_exhausted|pool.getconn.FAILED"

# Comparar getconn vs putconn
$get = (Select-String -Path logs\app.jsonl -Pattern "pool.getconn.success").Count
$put = (Select-String -Path logs\app.jsonl -Pattern "pool.putconn.success").Count
Write-Host "getconn: $get, putconn: $put, LEAK: $($get - $put)"
```

### Indicadores de Salud
| Métrica | Valor Normal | Valor Crítico |
|---------|--------------|---------------|
| Pool used | 0-10 | >70 |
| getconn - putconn | 0-2 | >10 |
| Requests sin close | 0 | >0 |

---

## Trabajo Pendiente

### No Urgente
- [ ] Migrar 59 endpoints de `build_clients_or_error` a `Depends(get_service_clients)`
- [ ] Optimizar query de `/api/coding/stats`
- [ ] Agregar índices para queries lentos
- [ ] Implementar health check automático del pool

### Decisión Tomada
Los 59 endpoints con `build_clients_or_error + try/finally` funcionan correctamente.
La migración a `Depends` es mejora de mantenibilidad, no corrección de bug.

---

## Historial de Cambios

| Fecha | Cambio | Archivos |
|-------|--------|----------|
| 2026-01-06 | Fix get_service_clients en 4 routers | auth.py, admin.py, interviews.py, ingest.py |
| 2026-01-06 | Pool size 20→80 | app/clients.py |
| 2026-01-06 | Rollback antes de putconn | app/clients.py |
| 2026-01-06 | Delete from proyectos table | backend/app.py |
| 2026-01-06 | Logging INFO para pool | app/clients.py |
| 2026-01-07 | Fix /api/coding/stats timeout 30s | backend/app.py, backend/routers/coding.py |
| 2026-01-07 | Neo4j driver resilience (max_connection_lifetime) | app/clients.py |

---

## Problema 5: Neo4j "Unable to retrieve routing information"

### Síntomas
- Error: `Unable to retrieve routing information`
- Error: `Failed to read from defunct connection`
- Ingesta de documentos falla con error 500

### Causa Raíz
- Azure Load Balancer cierra conexiones idle después de ~5 minutos
- El driver Neo4j mantiene conexiones cacheadas que se vuelven "defunct"
- El driver no detecta conexiones muertas hasta intentar usarlas

### Solución Aplicada (RESUELTO - 2026-01-07)
```python
# app/clients.py - _get_cached_neo4j()
_neo4j_driver = GraphDatabase.driver(
    settings.neo4j.uri,
    auth=(settings.neo4j.username, settings.neo4j.password),
    # Cerrar conexiones antes del timeout de Azure (~5min)
    max_connection_lifetime=180,  # 3 minutos
    # Verificar conexión antes de usar si estuvo idle
    liveness_check_timeout=5,
    # TCP keepalive para detectar conexiones muertas
    keep_alive=True,
)
```

### Función de Reset Manual
Si persiste el error, usar:
```python
from app.clients import reset_neo4j_driver
reset_neo4j_driver()  # Fuerza recreación del driver
```

---

## Problema 6: Contadores Neo4j no coinciden (PG vs Neo4j)

### Síntomas
- Admin Panel muestra "Sincronizados" > 0, pero Aura/Neo4j tiene 0 nodos/relaciones.
- Botón de sincronización no reingesta porque `pending=0`.

### Causa Raíz
Los contadores de la sección "Sincronización Neo4j" se calculan en PostgreSQL
usando `entrevista_fragmentos.neo4j_synced`. Si Neo4j se limpió manualmente,
los flags en PG pueden quedar en `TRUE` aunque Neo4j esté vacío.

### Solución Aplicada (2026-01-17)
1) **Resetear flags** desde Admin Panel → "Resetear flags de sincronización".
2) Ejecutar **Sincronizar X fragmentos** para reingestar en Neo4j.
3) Ejecutar **Sincronizar relaciones axiales**.

### Endpoints Relacionados
- `POST /api/admin/sync-neo4j/reset?project=...`
- `POST /api/admin/sync-neo4j?project=...`
- `POST /api/admin/sync-neo4j/axial?project=...`
