# Guía de Despliegue en Azure

**Fecha:** 2026-01-01  
**Propósito:** Documentar los cambios realizados para habilitar el despliegue de APP_Jupter en Azure Cloud.

---

## 📋 Resumen Ejecutivo

Esta guía documenta las modificaciones realizadas a la infraestructura de despliegue para permitir una prueba de producción en Azure. Los cambios aseguran:

1. **Seguridad**: Credenciales seguras separadas de desarrollo
2. **Portabilidad**: Configuración dinámica de servicios backend
3. **Protección**: Archivos sensibles excluidos del control de versiones

---

## 🔐 Cambios Realizados

### 1. Archivo `.env.production` (NUEVO)

**Propósito:** Separar la configuración de producción de desarrollo.

**Ubicación:** `/.env.production`

**Contenido clave:**

| Variable | Valor Desarrollo | Valor Producción |
|----------|------------------|------------------|
| `ENVIRONMENT` | (no definido) | `production` |
| `JWT_SECRET_KEY` | `unsafe-secret-for-dev` | Token seguro de 64 caracteres |
| `PGHOST` | `localhost` | `pg-qualitative-prod.postgres.database.azure.com` |
| `PGSSLMODE` | (no definido) | `require` |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | `rediss://...redis.cache.windows.net:6380/0` |

**Seguridad:**
- JWT generado con `secrets.token_urlsafe(48)` (criptográficamente seguro)
- Archivo añadido a `.gitignore` para evitar commits accidentales

**Acción requerida:**
```bash
# Después de ejecutar deploy-azure.sh, actualizar:
PGPASSWORD="<password-de-azure-postgresql>"
CELERY_BROKER_URL="rediss://:<redis-access-key>@redis-qualitative-prod.redis.cache.windows.net:6380/0"
```

---

### 2. Dockerfile.prod del Frontend (MODIFICADO)

**Propósito:** Permitir configuración dinámica del backend URL en runtime.

**Ubicación:** `/frontend/Dockerfile.prod`

**Problema original:**
El archivo `nginx.conf` contenía `${BACKEND_URL}` que nginx no podía resolver porque no procesa variables de entorno automáticamente.

**Solución implementada:**

```dockerfile
# ANTES:
COPY nginx.conf /etc/nginx/nginx.conf
CMD ["nginx", "-g", "daemon off;"]

# DESPUÉS:
COPY nginx.conf /etc/nginx/templates/nginx.conf.template
ENV BACKEND_URL=http://backend:8000
CMD ["/bin/sh", "-c", "envsubst '${BACKEND_URL}' < /etc/nginx/templates/nginx.conf.template > /etc/nginx/nginx.conf && nginx -g 'daemon off;'"]
```

**Beneficios:**
- El `BACKEND_URL` puede sobrescribirse al iniciar el contenedor
- Soporta diferentes backends (local, staging, producción)
- Ejemplo: `docker run -e BACKEND_URL=https://api.midominio.com ...`

---

### 3. Archivo `.gitignore` (NUEVO)

**Propósito:** Proteger archivos sensibles y optimizar el repositorio.

**Ubicación:** `/.gitignore`

**Archivos protegidos:**

| Categoría | Patrones |
|-----------|----------|
| **Secretos** | `.env.production`, `.env.local`, `.env.*.local` |
| **Python** | `__pycache__/`, `*.pyc`, `venv/`, `.venv/` |
| **Node** | `node_modules/`, `frontend/dist/` |
| **IDE** | `.vscode/`, `.idea/` |
| **Logs** | `*.log`, `logs/` |
| **Audio** | `data/projects/*/audio/`, `*.mp3`, `*.wav` |

---

### 4. Dockerfile.backend (CORREGIDO)

**Propósito:** Corregir el endpoint de healthcheck.

**Ubicación:** `/Dockerfile.backend`

**Cambio:**
```dockerfile
# ANTES:
CMD curl -f http://localhost:8000/health || exit 1

# DESPUÉS:
CMD curl -f http://localhost:8000/healthz || exit 1
```

**Razón:** El endpoint real de la API es `/healthz`, no `/health`.

---

## 🏗️ Arquitectura de Despliegue

```
┌─────────────────────────────────────────────────────────────────┐
│                        Azure Cloud                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Frontend   │───▶│   Backend    │───▶│   Celery     │       │
│  │   (Nginx)    │    │   (FastAPI)  │    │   Worker     │       │
│  │   Port 80    │    │   Port 8000  │    │              │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│         │                   │                   │                │
│         │                   ▼                   │                │
│         │         ┌─────────────────┐           │                │
│         │         │  Azure Redis    │◀──────────┘                │
│         │         │  (Celery Broker)│                            │
│         │         └─────────────────┘                            │
│         │                   │                                    │
│         ▼                   ▼                                    │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐         │
│  │ Qdrant Cloud │   │   Azure PG   │   │  Neo4j Aura  │         │
│  │  (Vectors)   │   │ (PostgreSQL) │   │   (Grafo)    │         │
│  └──────────────┘   └──────────────┘   └──────────────┘         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 Archivos Modificados

| Archivo | Tipo | Descripción |
|---------|------|-------------|
| `.env.production` | NUEVO | Config de producción con JWT seguro |
| `.gitignore` | NUEVO | Protección de archivos sensibles |
| `frontend/Dockerfile.prod` | MODIFICADO | envsubst para BACKEND_URL |
| `Dockerfile.backend` | MODIFICADO | Healthcheck corregido |

---

## ✅ Verificación Pre-Deploy

```bash
# 1. Validar docker-compose
docker-compose -f docker-compose.prod.yml config

# 2. Build local de prueba
docker-compose -f docker-compose.prod.yml build

# 3. Dry-run del script de Azure
./scripts/deploy-azure.sh --dry-run
```

---

## 🚀 Pasos para Deploy

1. **Revisar `.env.production`** - Verificar que los valores cloud son correctos
2. **Ejecutar infraestructura** - `./scripts/deploy-azure.sh --skip-containers`
3. **Obtener credenciales** - Copiar passwords de Azure Portal
4. **Actualizar `.env.production`** - Con passwords reales
5. **Deploy containers** - `./scripts/deploy-azure.sh --skip-infra`
6. **Ejecutar migraciones** - Crear tablas PostgreSQL
7. **Probar endpoints** - Verificar `/healthz`

---

## 📚 Documentos Relacionados

- [Gap Analysis Completo](../../.gemini/antigravity/brain/.../azure_deployment_gaps.md)
- [Script de Deploy](../scripts/deploy-azure.sh)
- [Docker Compose Producción](../docker-compose.prod.yml)

---

*Documento creado: 2026-01-01*
