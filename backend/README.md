# Módulo Backend - API REST FastAPI

Este directorio contiene el servidor API REST que expone los servicios del núcleo `app/` como endpoints HTTP.

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                      FRONTEND (React)                        │
│                      http://localhost:5173                   │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP/REST
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   BACKEND (FastAPI)                          │
│                   http://localhost:8000                      │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  app.py (54+ endpoints)                                 ││
│  │  - /api/ingest       → Ingesta de DOCX                  ││
│  │  - /api/analyze      → Análisis LLM                     ││
│  │  - /api/coding       → Codificación abierta/axial       ││
│  │  - /api/neo4j        → Consultas Cypher                 ││
│  │  - /api/transversal  → Análisis cruzado                 ││
│  │  - /api/nucleus      → Núcleo selectivo                 ││
│  │  - /api/validation   → Saturación y outliers            ││
│  └─────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────┐│
│  │  auth.py                                                ││
│  │  - JWT Bearer tokens                                    ││
│  │  - X-API-Key header fallback                            ││
│  └─────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────┐│
│  │  celery_worker.py                                       ││
│  │  - Tareas asíncronas (análisis largo)                   ││
│  │  - Broker: Redis                                        ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      CORE (app/)                             │
│  settings │ clients │ ingestion │ analysis │ coding │ ...   │
└─────────────────────────────────────────────────────────────┘
```

---

## Archivos

| Archivo | Descripción | LOC |
|---------|-------------|-----|
| `app.py` | Aplicación FastAPI con ~54 endpoints | 1063 |
| `auth.py` | Autenticación JWT + API Key | 80 |
| `celery_worker.py` | Worker para tareas asíncronas | 61 |
| `__init__.py` | Marcador de paquete | 2 |

---

## Autenticación

El sistema soporta dos métodos:

### 1. JWT Bearer Token
```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### 2. API Key (Fallback)
```http
X-API-Key: tu-api-key-aqui
```

Variables de entorno:
- `JWT_SECRET_KEY`: Secreto para firmar tokens
- `JWT_ALGORITHM`: Algoritmo (default: HS256)
- `NEO4J_API_KEY` o `API_KEY`: Para autenticación por header

---

## Endpoints Principales

### Ingesta
| Método | Path | Descripción |
|--------|------|-------------|
| POST | `/api/ingest/upload` | Subir DOCX para ingesta |
| POST | `/api/ingest/batch` | Ingesta de múltiples archivos |

### Análisis
| Método | Path | Descripción |
|--------|------|-------------|
| POST | `/api/analyze/run` | Ejecutar análisis LLM |
| POST | `/api/analyze/persist` | Persistir resultados |

### Codificación
| Método | Path | Descripción |
|--------|------|-------------|
| POST | `/api/coding/assign` | Asignar código a fragmento |
| POST | `/api/coding/suggest` | Sugerir fragmentos similares |
| GET | `/api/coding/stats` | Estadísticas de codificación |

### Neo4j
| Método | Path | Descripción |
|--------|------|-------------|
| POST | `/api/neo4j/query` | Ejecutar consulta Cypher |
| POST | `/api/neo4j/export` | Exportar a CSV/JSON |
| POST | `/api/neo4j/gds` | Algoritmos GDS |

### Transversal
| Método | Path | Descripción |
|--------|------|-------------|
| POST | `/api/transversal/crosstab` | Tablas cruzadas |
| POST | `/api/transversal/probe` | Búsqueda por segmentos |
| POST | `/api/transversal/dashboard` | Payload completo |

### Validación
| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/validation/saturation` | Curva de saturación |
| GET | `/api/validation/outliers` | Fragmentos atípicos |
| GET | `/api/validation/member-checking` | Paquetes para validación |

---

## Ejecución

```bash
# Desarrollo
uvicorn backend.app:app --reload --port 8000

# Producción
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --workers 4

# Worker Celery (para tareas asíncronas)
celery -A backend.celery_worker worker --loglevel=info
```

---

## Variables de Entorno Requeridas

```env
# Autenticación
JWT_SECRET_KEY=tu-secreto-seguro
API_KEY=tu-api-key

# Redis (para Celery)
CELERY_BROKER_URL=redis://localhost:6379/0

# Bases de datos (heredadas de app/)
NEO4J_URI=bolt://localhost:7687
QDRANT_URI=http://localhost:6333
POSTGRES_HOST=localhost
```

---

*Documento generado: Diciembre 2024*
