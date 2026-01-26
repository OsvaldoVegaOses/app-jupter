# Troubleshooting: Docker y Azure PostgreSQL

**Fecha**: 2026-01-02  
**Versión**: 1.0

---

## 1. Error: pgcrypto Extension Not Allowed

### Síntoma
```
psycopg2.errors.FeatureNotSupported: extension "pgcrypto" is not allow-listed 
for users in Azure Database for PostgreSQL
```

### Causa
Azure PostgreSQL no permite a usuarios estándar instalar la extensión `pgcrypto` que el código usaba para generar UUIDs con `gen_random_uuid()`.

### Solución
Modificar `app/postgres_block.py`:
1. Eliminar `CREATE EXTENSION IF NOT EXISTS "pgcrypto"`
2. Eliminar `DEFAULT gen_random_uuid()` de las tablas
3. Generar UUIDs en Python con `uuid.uuid4()` antes del INSERT

**Archivos afectados**: 
- `app/postgres_block.py` - funciones `ensure_users_table`, `create_user`, `create_session`

---

## 2. Error: Column "is_verified" Does Not Exist

### Síntoma
```
psycopg2.errors.UndefinedColumn: column "is_verified" does not exist
```

### Causa
La tabla `app_users` fue creada con un esquema anterior que no incluye columnas nuevas.

### Solución
Ejecutar script de migración:
```bash
.\.venv\Scripts\python.exe scripts/fix_schema.py
```

Columnas agregadas:
- `is_verified BOOLEAN DEFAULT false`
- `updated_at TIMESTAMPTZ DEFAULT NOW()`
- `last_login_at TIMESTAMPTZ`

---

## 3. Error: Column "project_id" Does Not Exist

### Síntoma
```
psycopg2.errors.UndefinedColumn: column "project_id" does not exist
```

### Causa
La tabla `codigos_candidatos` tiene columna `proyecto` pero el código espera `project_id`.

### Solución
Ejecutar script de migración:
```bash
.\.venv\Scripts\python.exe scripts/migrate_candidatos.py
```

Renombra `proyecto` → `project_id` y agrega columnas faltantes.

---

## 4. Error: FastAPI.__call__() Missing Arguments

### Síntoma
```
TypeError: FastAPI.__call__() missing 2 required positional arguments: 'receive' and 'send'
```

### Causa
Conflicto con `uvloop` en contenedor Docker Linux cuando se usa multiprocessing.

### Solución
Modificar `Dockerfile.backend` línea del CMD:

**Antes:**
```dockerfile
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Después:**
```dockerfile
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "asyncio"]
```

El flag `--loop asyncio` fuerza el uso del event loop estándar de Python en lugar de uvloop.

**Importante**: Después de este cambio, ejecutar:
```bash
docker-compose build --no-cache backend
docker-compose up -d backend
```

---

## 5. Error: npm ci Package Lock Out of Sync

### Síntoma
```
npm error `npm ci` can only install packages when your package.json and 
package-lock.json are in sync
```

### Causa
Se agregaron dependencias a `package.json` sin actualizar `package-lock.json`.

### Solución
```bash
cd frontend
npm install  # Regenera package-lock.json
```

Luego reconstruir la imagen Docker del frontend.

---

## 6. Scripts de Migración Creados

| Script | Propósito | Cuándo usar |
|--------|-----------|-------------|
| `scripts/fix_schema.py` | Agrega columnas faltantes a `app_users` | Después de deploy inicial |
| `scripts/migrate_candidatos.py` | Migra `proyecto` → `project_id` | Si hay error de columna |
| `scripts/test_registration.py` | Prueba registro directo | Para debugging |
| `scripts/init_auth_admin.py` | Crea usuario admin | Setup inicial |

---

## 7. Variables de Entorno Críticas para Azure PostgreSQL

```bash
# En .env o docker-compose.yml
PGHOST=<nombre>.postgres.database.azure.com
PGPORT=5432
PGUSER=<usuario>
PGPASSWORD=<password>
PGDATABASE=entrevistas
PGSSLMODE=require  # CRÍTICO para Azure PostgreSQL
```

---

## 8. Verificación Post-Fix

```bash
# Test health check
curl http://localhost:8000/healthz

# Test login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"password"}'
```

---

**Última actualización**: 2026-01-02
