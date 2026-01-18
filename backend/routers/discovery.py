"""
Discovery router - Semantic search, Qdrant queries, and discovery navigation endpoints.
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
import structlog
from functools import lru_cache
import os

from app.clients import ServiceClients, build_service_clients
from app.settings import AppSettings, load_settings
from app.project_state import resolve_project
from backend.auth import User, get_current_user

# Logger
api_logger = structlog.get_logger("app.api.discovery")

# Dependencies
@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    env_file = os.getenv("APP_ENV_FILE")
    return load_settings(env_file)

def build_clients_or_error(settings: AppSettings) -> ServiceClients:
    try:
        return build_service_clients(settings)
    except Exception as exc:
        from app.error_handling import api_error, ErrorCode
        raise api_error(
            status_code=502,
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Error conectando con servicios externos. Intente más tarde.",
            exc=exc,
        ) from exc

async def require_auth(user: User = Depends(get_current_user)) -> User:
    return user

#Request Models
class GroupedSearchRequest(BaseModel):
    """Request para búsqueda semántica agrupada con filtros avanzados."""
    model_config = ConfigDict(extra="forbid")
    
    project: str = Field(..., description="Proyecto")
    query: str = Field(..., min_length=3, description="Texto de búsqueda")
    limit: int = Field(10, ge=1, le=50, description="Máximo de grupos")
    group_by: str = Field("archivo", description="Campo para agrupar")
    group_size: int = Field(2, ge=1, le=5, description="Resultados por grupo")
    score_threshold: float = Field(0.3, ge=0.0, le=1.0, description="Umbral de score")
    
    # Filtros avanzados (Payload Filtering - Comparación Constante)
    genero: Optional[str] = Field(None, description="Filtrar por género (mujer/hombre)")
    actor_principal: Optional[str] = Field(None, description="Filtrar por rol/actor")
    area_tematica: Optional[str] = Field(None, description="Filtrar por área temática")
    periodo: Optional[str] = Field(None, description="Filtrar por periodo temporal")
    archivo: Optional[str] = Field(None, description="Filtrar por archivo específico")

#Create routers
router = APIRouter(prefix="/api/discovery", tags=["Discovery"])
qdrant_router = APIRouter(prefix="/api/qdrant", tags=["Qdrant"])

# Qdrant Grouped Search Endpoint
@qdrant_router.post("/search-grouped")
async def api_qdrant_search_grouped(
    payload: GroupedSearchRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Búsqueda semántica agrupada para evitar sesgo de fuente.
    
    Garantiza diversidad en resultados: máximo N fragmentos por entrevista/speaker.
    Útil para muestreo teórico sin que una fuente domine.
    """
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        # Generar embedding del query
        from app.embedding import embed_texts
        embeddings = embed_texts(clients.aoai, settings.AZURE_OPENAI_DEPLOYMENT_EMBEDDING, [payload.query])
        if not embeddings or not embeddings[0]:
            raise HTTPException(status_code=500, detail="Error generando embedding")
        
        query_vector = embeddings[0]
        
        # Usar búsqueda agrupada con filtros
        from app.qdrant_block import search_similar_grouped
        groups = search_similar_grouped(
            clients.qdrant,
            settings.QDRANT_COLLECTION,
            query_vector,
            limit=payload.limit,
            group_by=payload.group_by,
            group_size=payload.group_size,
            score_threshold=payload.score_threshold,
            project_id=project_id,
            exclude_interviewer=True,
            # Filtros avanzados
            genero=payload.genero,
            actor_principal=payload.actor_principal,
            area_tematica=payload.area_tematica,
            periodo=payload.periodo,
            archivo_filter=payload.archivo,
        )
        
        # Formatear resultados
        results = []
        for group in groups:
            group_key = group.id if hasattr(group, 'id') else str(group)
            hits = []
            for hit in (group.hits if hasattr(group, 'hits') else []):
                hits.append({
                    "id": hit.id,
                    "score": hit.score,
                    "fragmento": hit.payload.get("fragmento", "")[:200],
                    "archivo": hit.payload.get("archivo"),
                    "speaker": hit.payload.get("speaker"),
                    "actor_principal": hit.payload.get("actor_principal"),
                })
            results.append({
                "group_key": group_key,
                "hits": hits,
            })
        
        return {
            "success": True,
            "query": payload.query,
            "group_by": payload.group_by,
            "results": results,
            "total_groups": len(results),
        }
    except Exception as e:
        api_logger.error("api.qdrant.search_grouped_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error en búsqueda agrupada: {str(e)}") from e
    finally:
        clients.close()

# Discovery Navigation History
@router.get("/navigation-history")
async def api_get_discovery_navigation_history(
    project: str = Query(..., description="Project ID"),
    limit: int = Query(default=50, ge=1, le=200, description="Max entries"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Sprint 24: Get discovery navigation history for a project.
    
    Returns chronological list of searches with their refinements.
    """
    from app.postgres_block import get_discovery_navigation_history
    
    clients = build_clients_or_error(settings)
    try:
        history = get_discovery_navigation_history(
            clients.postgres,
            project=project,
            limit=limit,
        )
        
        return {
            "project": project,
            "history": history,
            "count": len(history),
        }
    except Exception as exc:
        api_logger.error("api.discovery.navigation_history_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()
