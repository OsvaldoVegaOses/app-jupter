#!/bin/bash
# =============================================================================
# Script de Despliegue Automatizado en Azure
# Aplicación de Análisis Cualitativo de Entrevistas
# =============================================================================
# Uso: ./deploy-azure.sh [--dry-run] [--skip-infra] [--skip-containers]
# =============================================================================

set -e  # Exit on error

# -----------------------------------------------------------------------------
# CONFIGURACIÓN
# -----------------------------------------------------------------------------
RESOURCE_GROUP="rg-qualitative-analysis"
LOCATION="eastus2"
ENVIRONMENT_NAME="cae-qualitative-prod"

# Servicios
PG_SERVER_NAME="pg-qualitative-prod"
REDIS_NAME="redis-qualitative-prod"
STORAGE_ACCOUNT="stqualitativeprod"
ACR_NAME="acrqualitativeprod"
STATIC_WEB_APP="swa-qualitative-prod"

# Container Apps
BACKEND_APP="backend-api"
QDRANT_APP="qdrant"
NEO4J_APP="neo4j"

# Flags
DRY_RUN=false
SKIP_INFRA=false
SKIP_CONTAINERS=false

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true ;;
        --skip-infra) SKIP_INFRA=true ;;
        --skip-containers) SKIP_CONTAINERS=true ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

run_cmd() {
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}[DRY-RUN]${NC} $1"
    else
        log_info "Ejecutando: $1"
        eval "$1"
    fi
}

# -----------------------------------------------------------------------------
# VERIFICAR PREREQUISITOS
# -----------------------------------------------------------------------------
check_prerequisites() {
    log_info "Verificando prerequisitos..."
    
    # Azure CLI
    if ! command -v az &> /dev/null; then
        log_error "Azure CLI no instalado. Visita: https://aka.ms/installazurecli"
        exit 1
    fi
    
    # Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker no instalado."
        exit 1
    fi
    
    # Check login
    if ! az account show &> /dev/null; then
        log_warn "No has iniciado sesión en Azure. Ejecutando 'az login'..."
        az login
    fi
    
    log_info "✓ Prerequisitos verificados"
}

# -----------------------------------------------------------------------------
# CREAR RESOURCE GROUP
# -----------------------------------------------------------------------------
create_resource_group() {
    log_info "Creando Resource Group: $RESOURCE_GROUP"
    run_cmd "az group create --name $RESOURCE_GROUP --location $LOCATION --output none"
}

# -----------------------------------------------------------------------------
# CREAR POSTGRESQL
# -----------------------------------------------------------------------------
create_postgresql() {
    log_info "Creando Azure Database for PostgreSQL..."
    
    if [ -z "$PG_PASSWORD" ]; then
        log_error "Variable PG_PASSWORD no configurada. Exporta: export PG_PASSWORD='tu-password'"
        exit 1
    fi
    
    run_cmd "az postgres flexible-server create \
        --resource-group $RESOURCE_GROUP \
        --name $PG_SERVER_NAME \
        --location $LOCATION \
        --admin-user pgadmin \
        --admin-password '$PG_PASSWORD' \
        --sku-name Standard_B1ms \
        --tier Burstable \
        --storage-size 32 \
        --version 15 \
        --output none"
    
    run_cmd "az postgres flexible-server db create \
        --resource-group $RESOURCE_GROUP \
        --server-name $PG_SERVER_NAME \
        --database-name entrevistas \
        --output none"
    
    log_info "✓ PostgreSQL creado"
}

# -----------------------------------------------------------------------------
# CREAR REDIS
# -----------------------------------------------------------------------------
create_redis() {
    log_info "Creando Azure Cache for Redis..."
    
    run_cmd "az redis create \
        --resource-group $RESOURCE_GROUP \
        --name $REDIS_NAME \
        --location $LOCATION \
        --sku Basic \
        --vm-size c0 \
        --output none"
    
    log_info "✓ Redis creado"
}

# -----------------------------------------------------------------------------
# CREAR STORAGE
# -----------------------------------------------------------------------------
create_storage() {
    log_info "Creando Azure Blob Storage..."
    
    run_cmd "az storage account create \
        --resource-group $RESOURCE_GROUP \
        --name $STORAGE_ACCOUNT \
        --location $LOCATION \
        --sku Standard_LRS \
        --kind StorageV2 \
        --output none"
    
    for container in audio documents transcriptions; do
        run_cmd "az storage container create \
            --account-name $STORAGE_ACCOUNT \
            --name $container \
            --public-access off \
            --output none"
    done
    
    log_info "✓ Storage creado con contenedores"
}

# -----------------------------------------------------------------------------
# CREAR CONTAINER APPS ENVIRONMENT
# -----------------------------------------------------------------------------
create_container_environment() {
    log_info "Creando Container Apps Environment..."
    
    run_cmd "az monitor log-analytics workspace create \
        --resource-group $RESOURCE_GROUP \
        --workspace-name law-qualitative-prod \
        --location $LOCATION \
        --output none"
    
    LOG_ID=$(az monitor log-analytics workspace show \
        --resource-group $RESOURCE_GROUP \
        --workspace-name law-qualitative-prod \
        --query customerId -o tsv)
    
    LOG_KEY=$(az monitor log-analytics workspace get-shared-keys \
        --resource-group $RESOURCE_GROUP \
        --workspace-name law-qualitative-prod \
        --query primarySharedKey -o tsv)
    
    run_cmd "az containerapp env create \
        --resource-group $RESOURCE_GROUP \
        --name $ENVIRONMENT_NAME \
        --location $LOCATION \
        --logs-workspace-id $LOG_ID \
        --logs-workspace-key $LOG_KEY \
        --output none"
    
    log_info "✓ Container Apps Environment creado"
}

# -----------------------------------------------------------------------------
# DESPLEGAR QDRANT
# -----------------------------------------------------------------------------
deploy_qdrant() {
    log_info "Desplegando Qdrant..."
    
    run_cmd "az containerapp create \
        --resource-group $RESOURCE_GROUP \
        --name $QDRANT_APP \
        --environment $ENVIRONMENT_NAME \
        --image qdrant/qdrant:latest \
        --target-port 6333 \
        --ingress internal \
        --min-replicas 1 \
        --max-replicas 1 \
        --cpu 0.5 \
        --memory 1.0Gi \
        --output none"
    
    log_info "✓ Qdrant desplegado"
}

# -----------------------------------------------------------------------------
# DESPLEGAR NEO4J
# -----------------------------------------------------------------------------
deploy_neo4j() {
    log_info "Desplegando Neo4j..."
    
    if [ -z "$NEO4J_PASSWORD" ]; then
        log_error "Variable NEO4J_PASSWORD no configurada."
        exit 1
    fi
    
    run_cmd "az containerapp create \
        --resource-group $RESOURCE_GROUP \
        --name $NEO4J_APP \
        --environment $ENVIRONMENT_NAME \
        --image neo4j:5-community \
        --target-port 7474 \
        --ingress internal \
        --min-replicas 1 \
        --max-replicas 1 \
        --cpu 0.5 \
        --memory 1.0Gi \
        --env-vars NEO4J_AUTH=neo4j/$NEO4J_PASSWORD \
        --output none"
    
    log_info "✓ Neo4j desplegado"
}

# -----------------------------------------------------------------------------
# BUILD Y DEPLOY BACKEND
# -----------------------------------------------------------------------------
deploy_backend() {
    log_info "Desplegando Backend API..."
    
    # Crear ACR si no existe
    run_cmd "az acr create \
        --resource-group $RESOURCE_GROUP \
        --name $ACR_NAME \
        --sku Basic \
        --output none"
    
    run_cmd "az acr login --name $ACR_NAME"
    
    # Build y push
    log_info "Construyendo imagen Docker..."
    run_cmd "docker build -t $ACR_NAME.azurecr.io/backend:latest -f Dockerfile.backend ."
    run_cmd "docker push $ACR_NAME.azurecr.io/backend:latest"
    
    # Deploy
    run_cmd "az containerapp create \
        --resource-group $RESOURCE_GROUP \
        --name $BACKEND_APP \
        --environment $ENVIRONMENT_NAME \
        --image $ACR_NAME.azurecr.io/backend:latest \
        --registry-server $ACR_NAME.azurecr.io \
        --target-port 8000 \
        --ingress external \
        --min-replicas 1 \
        --max-replicas 3 \
        --cpu 1.0 \
        --memory 2.0Gi \
        --output none"
    
    log_info "✓ Backend desplegado"
}

# -----------------------------------------------------------------------------
# BUILD Y DEPLOY FRONTEND
# -----------------------------------------------------------------------------
deploy_frontend() {
    log_info "Desplegando Frontend..."
    
    cd frontend
    npm install
    npm run build
    cd ..
    
    run_cmd "az staticwebapp create \
        --resource-group $RESOURCE_GROUP \
        --name $STATIC_WEB_APP \
        --location $LOCATION \
        --output none"
    
    log_info "✓ Frontend desplegado"
}

# -----------------------------------------------------------------------------
# MOSTRAR RESUMEN
# -----------------------------------------------------------------------------
show_summary() {
    echo ""
    echo "=============================================="
    echo "         DESPLIEGUE COMPLETADO"
    echo "=============================================="
    echo ""
    
    BACKEND_URL=$(az containerapp show \
        --resource-group $RESOURCE_GROUP \
        --name $BACKEND_APP \
        --query properties.configuration.ingress.fqdn \
        --output tsv 2>/dev/null || echo "N/A")
    
    echo "Backend API: https://$BACKEND_URL"
    echo "PostgreSQL:  $PG_SERVER_NAME.postgres.database.azure.com"
    echo "Redis:       $REDIS_NAME.redis.cache.windows.net"
    echo ""
    echo "Próximos pasos:"
    echo "  1. Configurar variables de entorno en Container Apps"
    echo "  2. Ejecutar migraciones de PostgreSQL"
    echo "  3. Crear colección en Qdrant"
    echo "  4. Configurar dominio personalizado (opcional)"
    echo ""
}

# -----------------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------------
main() {
    echo "=============================================="
    echo "  Azure Deployment Script"
    echo "  Análisis Cualitativo de Entrevistas"
    echo "=============================================="
    
    if [ "$DRY_RUN" = true ]; then
        log_warn "Modo DRY-RUN activado (no se ejecutarán comandos)"
    fi
    
    check_prerequisites
    
    if [ "$SKIP_INFRA" = false ]; then
        create_resource_group
        create_postgresql
        create_redis
        create_storage
        create_container_environment
    else
        log_warn "Saltando creación de infraestructura (--skip-infra)"
    fi
    
    if [ "$SKIP_CONTAINERS" = false ]; then
        deploy_qdrant
        deploy_neo4j
        deploy_backend
        deploy_frontend
    else
        log_warn "Saltando despliegue de containers (--skip-containers)"
    fi
    
    show_summary
}

main "$@"
