"""
Módulo Backend - API REST para análisis cualitativo.

Este paquete contiene el servidor FastAPI que expone los servicios
del núcleo `app/` como endpoints HTTP REST.

Componentes:
    - app.py: Aplicación FastAPI con ~54 endpoints
    - auth.py: Autenticación JWT + API Key
    - celery_worker.py: Worker para tareas asíncronas

Arquitectura:
    Frontend (React) → Backend (FastAPI) → Core (app/) → Databases
    
Autenticación soportada:
    1. JWT Bearer Token: Authorization: Bearer <token>
    2. API Key Header: X-API-Key: <key>

Ejecución:
    uvicorn backend.app:app --reload --port 8000
"""

# Backend package placeholder for Neo4j Query API integrations.
