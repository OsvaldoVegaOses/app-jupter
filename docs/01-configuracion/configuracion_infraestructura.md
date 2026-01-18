# Configuración de Infraestructura

> **Última actualización:** Diciembre 2024 (puertos actualizados)

---

## Arquitectura General

```
┌─────────────────────────────────────────────────────────────────┐
│                    FRONTEND (Vite + React)                      │
│                    http://localhost:5173                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI)                            │
│                    http://localhost:8000                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│   PostgreSQL  │   │    Neo4j      │   │    Qdrant     │
│   (Códigos)   │   │   (Grafo)     │   │  (Vectores)   │
│   :5432       │   │   :7687       │   │   :6333       │
└───────────────┘   └───────────────┘   └───────────────┘
                             │
                             ▼
                    ┌───────────────┐
                    │     Redis     │
                    │   (Broker)    │
                    │   :16379      │  ← Puerto externo (evita conflicto Hyper-V)
                    └───────────────┘
                             │
                             ▼
                    ┌───────────────┐
                    │    Celery     │
                    │   (Worker)    │
                    └───────────────┘
```

---

## 1. Qdrant (Base de Datos Vectorial)

### Propósito
- Almacena embeddings de fragmentos de entrevistas
- Habilita búsqueda semántica por similitud
- Soporta Discovery API para exploración triplete

### Configuración `.env`

```env
QDRANT_URI="https://xxx.cloud.qdrant.io"
QDRANT_API_KEY="tu-api-key"
QDRANT_COLLECTION=entrevistas
EMBED_DIMS=3072
```

### Configuración `app/settings.py`

```python
@dataclass
class QdrantSettings:
    uri: str                # URL del servidor
    api_key: Optional[str]  # API key (cloud)
    collection: str         # Nombre de colección
    timeout: int = 30       # Timeout en segundos
    batch_size: int = 20    # Batch para upsert
```

### Uso en la Aplicación

| Módulo | Función | Propósito |
|--------|---------|-----------|
| `app/ingest.py` | `upsert_fragments()` | Indexar fragmentos |
| `app/queries.py` | `semantic_search()` | Búsqueda híbrida |
| `app/queries.py` | `discover_search()` | Exploración triplete |

### Docker Local

```yaml
# docker-compose.yml
qdrant:
  image: qdrant/qdrant:latest
  ports:
    - "6333:6333"
  volumes:
    - qdrant_data:/qdrant/storage
```

---

## 2. Neo4j (Base de Datos de Grafos)

### Propósito
- Almacena relaciones axiales entre códigos y categorías
- Ejecuta algoritmos GDS (PageRank, Louvain)
- Soporta consultas Cypher para exploración

### Configuración `.env`

```env
NEO4J_URI="neo4j+s://xxx.databases.neo4j.io"
NEO4J_USERNAME="neo4j"
NEO4J_PASSWORD="tu-password"
NEO4J_DATABASE="neo4j"
```

### Configuración `app/settings.py`

```python
@dataclass
class Neo4jSettings:
    uri: str          # Bolt URI
    username: str     # Usuario
    password: str     # Contraseña
    database: str     # Nombre de DB
```

### Uso en la Aplicación

| Módulo | Función | Propósito |
|--------|---------|-----------|
| `app/neo4j_block.py` | `merge_category_code_relationship()` | Persistir relaciones |
| `app/neo4j_block.py` | `run_gds_algorithms()` | Ejecutar PageRank/Louvain |
| `app/graphrag.py` | `extract_relevant_subgraph()` | Extraer contexto |
| `app/link_prediction.py` | `suggest_links()` | Predecir enlaces |

### Docker Local

```yaml
# docker-compose.yml
neo4j:
  image: neo4j:5-community
  ports:
    - "7474:7474"
    - "7687:7687"
  environment:
    - NEO4J_AUTH=neo4j/password
    - NEO4J_PLUGINS=["graph-data-science"]
```

### Algoritmos GDS

| Algoritmo | Campo | Propósito |
|-----------|-------|-----------|
| PageRank | `score_centralidad` | Importancia de nodos |
| Louvain | `community_id` | Detección de comunidades |

---

## 3. PostgreSQL (Base de Datos Relacional)

### Propósito
- Almacena fragmentos con texto completo (BM25)
- Guarda códigos abiertos y axiales
- Registra proyectos y metadatos

### Configuración `.env`

```env
PGHOST="localhost"
PGPORT="5432"
PGUSER="postgres"
PGPASSWORD="tu-password"
PGDATABASE="system_inv_sociocultural_v1"
```

### Configuración `app/settings.py`

```python
@dataclass
class PostgresSettings:
    host: str
    port: int
    username: str
    password: str
    database: str
```

### Tablas Principales

| Tabla | Propósito |
|-------|-----------|
| `entrevista_fragmentos` | Fragmentos ingresados |
| `analisis_codigos_abiertos` | Códigos del LLM |
| `analisis_axial` | Relaciones axiales |
| `analisis_nucleo_notas` | Memos del núcleo teórico |

### Docker Local

```yaml
# docker-compose.yml
postgres:
  image: postgres:15
  ports:
    - "5432:5432"
  environment:
    POSTGRES_PASSWORD: password
    POSTGRES_DB: system_inv_sociocultural_v1
  volumes:
    - postgres_data:/var/lib/postgresql/data
```

---

## 4. Redis (Message Broker)

### Propósito
- Broker de mensajes para Celery
- Backend de resultados de tareas
- Cola de trabajos asíncronos

### Configuración `.env`

```env
# Conexión desde el host (desarrollo local)
CELERY_BROKER_URL=redis://localhost:16379/0

# Conexión entre contenedores Docker (usa puerto interno 6379)
# CELERY_BROKER_URL=redis://redis:6379/0
```

> [!IMPORTANT]
> El puerto externo es **16379** para evitar conflictos con Hyper-V en Windows.
> El puerto interno del contenedor sigue siendo 6379.

### Docker Local

```yaml
# docker-compose.yml
redis:
  image: redis:7-alpine
  ports:
    - "16379:6379"  # External 16379 avoids Windows Hyper-V port conflicts
  volumes:
    - redis_data:/data
```

---

## 5. Celery (Task Queue)

### Propósito
- Ejecuta análisis LLM en background
- Evita timeouts en requests HTTP largos
- Permite tracking de estado de tareas

### Configuración

```python
# backend/celery_worker.py
# El puerto por defecto es 16379 para desarrollo local
REDIS_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:16379/0")

celery_app = Celery(
    "backend_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
)
```

### Tareas Disponibles

| Tarea | Propósito |
|-------|-----------|
| `task_analyze_interview` | Análisis LLM (Etapas 0-4) |

### Ejecución del Worker

```bash
celery -A backend.celery_worker worker --loglevel=info --pool=solo
```

### Script de Inicio

```batch
:: scripts/start_worker.bat
.\.venv\Scripts\celery -A backend.celery_worker worker --loglevel=info --pool=solo
```

---

## 6. FastAPI (Backend HTTP)

### Propósito
- Expone API REST (~54 endpoints)
- Autenticación JWT + API Key
- Integra todos los servicios

### Ejecución

```bash
uvicorn backend.app:app --reload --port 8000
```

### Configuración CORS

> [!NOTE]
> En desarrollo local se permiten orígenes típicos de Vite (`http://localhost:5173`, etc.).
> En producción, configura explícitamente orígenes vía `CORS_ALLOW_ORIGINS`.

Ejemplo (patrón recomendado):

```python
_cors_allow_origins_raw = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
if _cors_allow_origins_raw:
  _cors_allow_origins = [o.strip() for o in _cors_allow_origins_raw.split(",") if o.strip()]
else:
  _cors_allow_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
  ]

_cors_allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "true").strip().lower() in {"1", "true", "yes"}
if "*" in _cors_allow_origins and _cors_allow_credentials:
  _cors_allow_credentials = False

app.add_middleware(
  CORSMiddleware,
  allow_origins=_cors_allow_origins,
  allow_credentials=_cors_allow_credentials,
  allow_methods=["*"],
  allow_headers=["*"],
)
```

---

## 7. Vite + React (Frontend)

### Propósito
- Dashboard de análisis cualitativo
- Visualización de códigos y fragmentos
- Explorador Neo4j integrado

### Configuración `frontend/.env`

```env
VITE_API_BASE=http://127.0.0.1:8000
VITE_NEO4J_API_KEY=dev-key
```

### Ejecución

```bash
cd frontend
npm run dev
```

---

## Docker Compose Completo

### Archivo: `docker-compose.yml`

```yaml
version: "3.8"
services:
  postgres:
    image: postgres:15
    container_name: postgres-db
    ports:
      - "5432:5432"
    environment:
      POSTGRES_PASSWORD: ${PGPASSWORD}
      POSTGRES_DB: ${PGDATABASE}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  neo4j:
    image: neo4j:5-community
    container_name: neo4j-db
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=${NEO4J_USERNAME}/${NEO4J_PASSWORD}
      - NEO4J_PLUGINS=["graph-data-science"]
    volumes:
      - neo4j_data:/data

  redis:
    image: redis:7-alpine
    container_name: redis-broker
    ports:
      - "16379:6379"  # External 16379 avoids Hyper-V conflicts

volumes:
  postgres_data:
  neo4j_data:
```

---

## Inicio Rápido

### Script Unificado

```bash
cmd /c scripts\start_all.bat
```

Este script:
1. Inicia Docker Compose (Neo4j, PostgreSQL, Redis)
2. Lanza Celery Worker
3. Lanza Backend FastAPI
4. Lanza Frontend Vite

### URLs y Puertos

| Servicio | URL / Puerto | Puerto Interno Docker |
|----------|--------------|----------------------|
| Frontend (Vite dev) | http://localhost:5173 | 5173 |
| Frontend (Docker) | http://localhost:5174 | 5173 |
| Backend API | http://localhost:8000 | 8000 |
| PostgreSQL | localhost:5432 | 5432 |
| Neo4j Browser | http://localhost:7474 | 7474 |
| Neo4j Bolt | localhost:7687 | 7687 |
| Redis | localhost:16379 | 6379 |
| Qdrant HTTP | localhost:6333 | 6333 |
| Qdrant gRPC | localhost:6334 | 6334 |

---

## Verificación de Servicios

```bash
# Backend health
curl http://localhost:8000/healthz

# Backend full health check
curl -H "X-API-Key: dev-key" http://localhost:8000/api/health/full

# Docker containers
docker ps

# Redis ping
docker exec redis-broker redis-cli PING

# PostgreSQL
docker exec postgres-db psql -U postgres -c "SELECT NOW()"
```

> [!NOTE]
> Si estás siguiendo esta documentación, el backend corre en `:8000`.

---

## Troubleshooting

| Problema | Causa | Solución |
|----------|-------|----------|
| Connection refused :5432 | PostgreSQL apagado | `docker-compose up postgres` |
| Neo4j auth error | Credenciales incorrectas | Verificar `.env` |
| Qdrant timeout | Cloud lento | Aumentar `QDRANT_TIMEOUT` |
| Celery PENDING | Worker no corre | Reiniciar worker |
| CORS error | Backend caído | Verificar :8000 |
| Port bind error :6379 | Hyper-V reserva puertos | Ver sección "Windows Hyper-V" abajo |

---

## Windows Hyper-V - Conflictos de Puertos

> [!WARNING]
> En Windows con Hyper-V/WSL2 habilitado, el sistema reserva rangos de puertos dinámicamente.
> Esto puede bloquear puertos comunes como 6379 (Redis) de forma intermitente.

### Síntoma

```
Error response from daemon: ports are not available: exposing port TCP 0.0.0.0:6379
-> listen tcp 0.0.0.0:6379: bind: An attempt was made to access a socket in a way
forbidden by its access permissions.
```

### Causa

Hyper-V reserva rangos de puertos para uso interno. Puedes ver los rangos reservados con:

```powershell
netsh interface ipv4 show excludedportrange protocol=tcp
```

### Solución Implementada

El proyecto usa **puertos externos altos** que están fuera de los rangos típicos de Hyper-V:

| Servicio | Puerto Estándar | Puerto Usado | Razón |
|----------|-----------------|--------------|-------|
| Redis | 6379 | **16379** | Evita rango Hyper-V 6267-6366 |

### Si el problema persiste

1. **Reiniciar Windows** - Libera los puertos reservados temporalmente
2. **Cambiar a puerto más alto** - Editar `docker-compose.yml`:
   ```yaml
   redis:
     ports:
       - "26379:6379"  # Probar otro puerto alto
   ```
3. **Deshabilitar Hyper-V temporalmente** (no recomendado si usas WSL2/Docker)

---

*Documento generado: Diciembre 2024*
