# Plan de Despliegue en Azure
## Aplicación de Análisis Cualitativo de Entrevistas

**Fecha**: 2026-01-07  
**Propósito**: Despliegue para prueba de producción  
**Versión**: 1.1

> [!IMPORTANT]
> **Cambio v1.1**: Neo4j reemplazado por **Memgraph MAGE** (open source).
> - 41x más rápido (in-memory)
> - Algoritmos MAGE incluidos gratis (Louvain, PageRank, etc.)
> - Compatible con protocolo Bolt (mismo driver)
> - El código lo detecta automáticamente via `graph_algorithms.py`

---

## 1. Resumen Ejecutivo

Este documento describe el plan para desplegar la aplicación de análisis cualitativo en Azure, configurando todos los servicios necesarios para un ambiente de pruebas de producción.

### Componentes de la Aplicación

| Componente | Tecnología | Servicio Azure Propuesto |
|------------|------------|--------------------------|
| Frontend | React + Vite | Azure Static Web Apps |
| Backend API | FastAPI + Python | Azure Container Apps |
| Base Vectorial | Qdrant | Azure Container Apps |
| Grafo | Memgraph MAGE | Azure Container Apps |
| Base Relacional | PostgreSQL | Azure Database for PostgreSQL |
| Cache/Broker | Redis | Azure Cache for Redis |
| AI/ML | OpenAI GPT-4o | Azure OpenAI Service (ya configurado) |
| Storage | Archivos/Audio | Azure Blob Storage |

---

## 2. Arquitectura Propuesta

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Azure Cloud                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌──────────────────┐     ┌──────────────────────────────────────────┐ │
│   │  Static Web Apps │     │         Container Apps Environment       │ │
│   │    (Frontend)    │     │  ┌──────────┐ ┌───────┐ ┌─────────────┐ │ │
│   │                  │────▶│  │ FastAPI  │ │Qdrant │ │   Neo4j     │ │ │
│   │  React + Vite    │     │  │ Backend  │ │       │ │   Graph     │ │ │
│   └──────────────────┘     │  └────┬─────┘ └───────┘ └─────────────┘ │ │
│                            │       │                                  │ │
│                            └───────┼──────────────────────────────────┘ │
│                                    │                                     │
│   ┌────────────────────────────────┼────────────────────────────────┐   │
│   │           Managed Services     │                                │   │
│   │  ┌─────────────┐  ┌───────────┴───┐  ┌─────────────────────┐   │   │
│   │  │ PostgreSQL  │  │ Azure OpenAI  │  │  Azure Blob Storage │   │   │
│   │  │  Flexible   │  │   (GPT-4o)    │  │  (Audio/Documents)  │   │   │
│   │  └─────────────┘  └───────────────┘  └─────────────────────┘   │   │
│   │                                                                 │   │
│   │  ┌─────────────────┐                                           │   │
│   │  │ Azure Cache     │                                           │   │
│   │  │ for Redis       │                                           │   │
│   │  └─────────────────┘                                           │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Prerequisitos

### 3.1 Recursos Azure Existentes
- [x] Suscripción Azure activa
- [x] Azure OpenAI Service con modelos desplegados:
  - `gpt-5.2-chat` (chat/análisis)
  - `gpt-4o-transcribe-diarize` (transcripción)
  - `text-embedding-3-large` (embeddings)

### 3.2 Herramientas Requeridas
```bash
# Azure CLI
az --version  # >= 2.50.0

# Docker
docker --version  # >= 24.0

# Node.js (para build frontend)
node --version  # >= 18.0
```

---

## 4. Paso a Paso del Despliegue

### 4.1 Configuración Inicial

```bash
# Login a Azure
az login

# Configurar suscripción
az account set --subscription "<SUBSCRIPTION_ID>"

# Crear Resource Group
az group create \
  --name rg-qualitative-analysis \
  --location eastus2
```

### 4.2 Crear Azure Database for PostgreSQL

```bash
# Crear servidor PostgreSQL Flexible
az postgres flexible-server create \
  --resource-group rg-qualitative-analysis \
  --name pg-qualitative-prod \
  --location eastus2 \
  --admin-user pgadmin \
  --admin-password "<SECURE_PASSWORD>" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 15

# Crear base de datos
az postgres flexible-server db create \
  --resource-group rg-qualitative-analysis \
  --server-name pg-qualitative-prod \
  --database-name entrevistas

# Habilitar extensiones (NOTA: pgcrypto NO está permitida para usuarios estándar)
az postgres flexible-server parameter set \
  --resource-group rg-qualitative-analysis \
  --server-name pg-qualitative-prod \
  --name azure.extensions \
  --value "uuid-ossp,pg_trgm"
# Los UUIDs se generan en Python con uuid.uuid4() en lugar de gen_random_uuid()
```

### 4.3 Crear Azure Cache for Redis

```bash
az redis create \
  --resource-group rg-qualitative-analysis \
  --name redis-qualitative-prod \
  --location eastus2 \
  --sku Basic \
  --vm-size c0
```

### 4.4 Crear Azure Blob Storage

```bash
# Crear cuenta de almacenamiento
az storage account create \
  --resource-group rg-qualitative-analysis \
  --name stqualitativeprod \
  --location eastus2 \
  --sku Standard_LRS \
  --kind StorageV2

# Crear contenedores
az storage container create \
  --account-name stqualitativeprod \
  --name audio \
  --public-access off

az storage container create \
  --account-name stqualitativeprod \
  --name documents \
  --public-access off

az storage container create \
  --account-name stqualitativeprod \
  --name transcriptions \
  --public-access off
```

### 4.5 Crear Container Apps Environment

```bash
# Crear Log Analytics Workspace
az monitor log-analytics workspace create \
  --resource-group rg-qualitative-analysis \
  --workspace-name law-qualitative-prod \
  --location eastus2

# Obtener credenciales
LOG_ANALYTICS_WORKSPACE_ID=$(az monitor log-analytics workspace show \
  --resource-group rg-qualitative-analysis \
  --workspace-name law-qualitative-prod \
  --query customerId -o tsv)

LOG_ANALYTICS_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group rg-qualitative-analysis \
  --workspace-name law-qualitative-prod \
  --query primarySharedKey -o tsv)

# Crear Container Apps Environment
az containerapp env create \
  --resource-group rg-qualitative-analysis \
  --name cae-qualitative-prod \
  --location eastus2 \
  --logs-workspace-id $LOG_ANALYTICS_WORKSPACE_ID \
  --logs-workspace-key $LOG_ANALYTICS_KEY
```

### 4.6 Desplegar Qdrant (Vector Database)

```bash
az containerapp create \
  --resource-group rg-qualitative-analysis \
  --name qdrant \
  --environment cae-qualitative-prod \
  --image qdrant/qdrant:latest \
  --target-port 6333 \
  --ingress internal \
  --min-replicas 1 \
  --max-replicas 1 \
  --cpu 0.5 \
  --memory 1.0Gi
```

### 4.7 Desplegar Memgraph MAGE (Graph Database)

> **Nota**: Memgraph MAGE reemplaza a Neo4j. Es más rápido (in-memory, 41x menor latencia),
> incluye algoritmos de grafo (Louvain, PageRank, etc.) gratis, y es compatible con el
> protocolo Bolt. El código ya lo detecta automáticamente via `graph_algorithms.py`.

```bash
# Crear volumen persistente para datos de Memgraph
az containerapp env storage set \
  --resource-group rg-qualitative-analysis \
  --name cae-qualitative-prod \
  --storage-name memgraph-storage \
  --azure-file-account-name stqualitativeprod \
  --azure-file-share-name memgraph-data \
  --azure-file-account-key <STORAGE_KEY> \
  --access-mode ReadWrite

# Desplegar Memgraph MAGE
az containerapp create \
  --resource-group rg-qualitative-analysis \
  --name memgraph \
  --environment cae-qualitative-prod \
  --image memgraph/memgraph-mage:latest \
  --target-port 7687 \
  --ingress internal \
  --min-replicas 1 \
  --max-replicas 1 \
  --cpu 1.0 \
  --memory 2.0Gi \
  --env-vars \
    MEMGRAPH_TELEMETRY_ENABLED=false \
    MEMGRAPH_STORAGE_PROPERTIES_ON_EDGES=true
```

> **Importante**: Memgraph es in-memory. El volumen persistente asegura que los datos
> sobrevivan reinicios del contenedor.

### 4.8 Build y Desplegar Backend (FastAPI)

```bash
# Crear Azure Container Registry
az acr create \
  --resource-group rg-qualitative-analysis \
  --name acrqualitativeprod \
  --sku Basic

# Login al registry
az acr login --name acrqualitativeprod

# Build y push de la imagen del backend
cd /path/to/APP_Jupter
docker build -t acrqualitativeprod.azurecr.io/backend:v1 -f Dockerfile.backend .
docker push acrqualitativeprod.azurecr.io/backend:v1

# Desplegar backend
az containerapp create \
  --resource-group rg-qualitative-analysis \
  --name backend-api \
  --environment cae-qualitative-prod \
  --image acrqualitativeprod.azurecr.io/backend:v1 \
  --registry-server acrqualitativeprod.azurecr.io \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3 \
  --cpu 1.0 \
  --memory 2.0Gi \
  --env-vars \
    AZURE_OPENAI_ENDPOINT=<ENDPOINT> \
    AZURE_OPENAI_API_KEY=secretref:aoai-key \
    AZURE_OPENAI_DEPLOYMENT_CHAT=gpt-5.2-chat \
    AZURE_OPENAI_DEPLOYMENT_EMBED=text-embedding-3-large \
    AZURE_OPENAI_DEPLOYMENT_TRANSCRIBE_DIARIZE=gpt-4o-transcribe-diarize \
    POSTGRES_HOST=pg-qualitative-prod.postgres.database.azure.com \
    POSTGRES_USER=pgadmin \
    POSTGRES_PASSWORD=secretref:pg-password \
    POSTGRES_DB=entrevistas \
    QDRANT_HOST=qdrant \
    QDRANT_PORT=6333 \
    NEO4J_URI=bolt://memgraph:7687 \
    NEO4J_USER=memgraph \
    NEO4J_PASSWORD= \
    REDIS_URL=redis://redis-qualitative-prod.redis.cache.windows.net:6380
```

### 4.9 Build y Desplegar Frontend

```bash
# Build del frontend
cd frontend
npm install
npm run build

# Desplegar a Azure Static Web Apps
az staticwebapp create \
  --resource-group rg-qualitative-analysis \
  --name swa-qualitative-prod \
  --location eastus2

# Configurar API backend URL
az staticwebapp appsettings set \
  --name swa-qualitative-prod \
  --setting-names VITE_API_BASE_URL=https://backend-api.<REGION>.azurecontainerapps.io
```

---

## 5. Variables de Entorno de Producción

### Backend (.env.production)
```env
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<api-key>
AZURE_OPENAI_DEPLOYMENT_CHAT=gpt-5.2-chat
AZURE_OPENAI_DEPLOYMENT_EMBED=text-embedding-3-large
AZURE_OPENAI_DEPLOYMENT_TRANSCRIBE_DIARIZE=gpt-4o-transcribe-diarize

# PostgreSQL
POSTGRES_HOST=pg-qualitative-prod.postgres.database.azure.com
POSTGRES_USER=pgadmin
POSTGRES_PASSWORD=<password>
POSTGRES_DB=entrevistas

# Qdrant
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_COLLECTION=fragments

# Memgraph (compatible con driver Neo4j via Bolt)
NEO4J_URI=bolt://memgraph:7687
NEO4J_USER=memgraph
NEO4J_PASSWORD=
NEO4J_DATABASE=memgraph

# Redis
REDIS_URL=rediss://redis-qualitative-prod.redis.cache.windows.net:6380

# API
API_KEY=<api-key-for-frontend>
```

### Frontend (.env.production)
```env
VITE_API_BASE_URL=https://backend-api.<REGION>.azurecontainerapps.io
```

---

## 6. Dockerfile para Backend

```dockerfile
# Dockerfile.backend
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (ffmpeg for audio processing)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY backend/ ./backend/
COPY main.py .

# Expose port
EXPOSE 8000

# Run with uvicorn (--loop asyncio prevents uvloop issues in Docker)
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "asyncio"]
```

---

## 7. Estimación de Costos (USD/mes)

| Servicio | SKU | Costo Estimado |
|----------|-----|----------------|
| PostgreSQL Flexible | B1ms | ~$15 |
| Azure Cache for Redis | Basic C0 | ~$16 |
| Container Apps (Backend) | 1 vCPU, 2GB | ~$50 |
| Container Apps (Qdrant) | 0.5 vCPU, 1GB | ~$25 |
| Container Apps (Memgraph) | 1 vCPU, 2GB | ~$50 |
| Static Web Apps | Free tier | $0 |
| Blob Storage | Standard LRS | ~$5 |
| Azure OpenAI | Pay-as-you-go | ~$50-200 (variable) |
| **Total Estimado** | | **~$190-390/mes** |

> **Nota**: Los costos de Azure OpenAI dependen del volumen de uso.

---

## 8. Checklist de Despliegue

### Pre-despliegue
- [ ] Crear Resource Group
- [ ] Configurar PostgreSQL y ejecutar migraciones
- [ ] Configurar Redis
- [ ] Configurar Blob Storage con contenedores
- [ ] Crear Container Apps Environment

### Despliegue de Servicios
- [ ] Desplegar Qdrant
- [ ] Desplegar Memgraph MAGE (con volumen persistente)
- [ ] Build y push imagen del backend
- [ ] Desplegar backend con variables de entorno
- [ ] Build del frontend
- [ ] Desplegar frontend a Static Web Apps

### Post-despliegue
- [ ] Verificar conectividad entre servicios
- [ ] Ejecutar pruebas de salud (`/health`)
- [ ] Crear colección en Qdrant
- [ ] Verificar conexión a Memgraph (`CALL mg.procedures()` para confirmar MAGE)
- [ ] Probar transcripción de audio
- [ ] Probar análisis de entrevista
- [ ] Configurar monitoreo en Azure Portal

### Seguridad
- [ ] Habilitar HTTPS en todos los endpoints
- [ ] Configurar CORS en el backend
- [ ] Rotar credenciales y usar Key Vault
- [ ] Configurar firewall en PostgreSQL
- [ ] Habilitar autenticación en la API

---

## 9. Comandos Útiles Post-Despliegue

```bash
# Ver logs del backend
az containerapp logs show \
  --resource-group rg-qualitative-analysis \
  --name backend-api \
  --follow

# Escalar replicas
az containerapp update \
  --resource-group rg-qualitative-analysis \
  --name backend-api \
  --min-replicas 2 \
  --max-replicas 5

# Ver estado de los servicios
az containerapp list \
  --resource-group rg-qualitative-analysis \
  --output table

# Obtener URL del backend
az containerapp show \
  --resource-group rg-qualitative-analysis \
  --name backend-api \
  --query properties.configuration.ingress.fqdn \
  --output tsv
```

---

## 10. Rollback Plan

En caso de fallo durante el despliegue:

1. **Backend**: Revertir a imagen anterior
   ```bash
   az containerapp update \
     --name backend-api \
     --image acrqualitativeprod.azurecr.io/backend:v0
   ```

2. **Frontend**: Redesplegar desde commit anterior

3. **Base de datos**: Restaurar desde backup automático de Azure

---

## 11. Próximos Pasos

1. **Fase 1** (Semana 1): Crear infraestructura base (PostgreSQL, Redis, Storage)
2. **Fase 2** (Semana 2): Desplegar servicios containerizados (Qdrant, Neo4j, Backend)
3. **Fase 3** (Semana 3): Desplegar frontend y configurar dominio personalizado
4. **Fase 4** (Semana 4): Pruebas de carga y optimización

---

**Documento preparado por**: Sistema de Desarrollo  
**Última actualización**: 2025-12-17
