"""
GraphRAG router - Graph analysis, axial coding, and link prediction endpoints.
"""
from typing import Dict, Any, List, Optional, Union, cast
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
import structlog
from functools import lru_cache
import os

from app.clients import ServiceClients
from app.settings import AppSettings, load_settings
from app.axial import run_gds_analysis, AxialError, AxialNotReadyError
from backend.auth import User, get_current_user

# Logger
api_logger = structlog.get_logger("app.api")

# Dependencies
@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    env_file = os.getenv("APP_ENV_FILE")
    return load_settings(env_file)

def build_clients_or_error(settings: AppSettings) -> ServiceClients:
    try:
        from app.clients import build_service_clients
        return build_service_clients(settings)
    except Exception as exc:
        from app.error_handling import api_error, ErrorCode
        raise api_error(
            status_code=502,
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Error conectando con servicios externos. Intente más tarde.",
            exc=exc,
        ) from exc

def build_neo4j_only(settings: AppSettings):
    """Build Neo4j-only clients for GDS operations."""
    from neo4j import GraphDatabase
    from dataclasses import dataclass
    
    @dataclass
    class Neo4jOnlyClients:
        neo4j: any
        def close(self):
            try:
                self.neo4j.close()
            except Exception:
                pass
    
    driver = GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.username, settings.neo4j.password or ""),
    )
    return Neo4jOnlyClients(neo4j=driver)

async def require_auth(user: User = Depends(get_current_user)) -> User:
    return user

# Request Models
class GDSRequest(BaseModel):
    project: str = Field(default="default", description="ID del proyecto (multi-tenant)")
    algorithm: str = Field(..., pattern="^(louvain|pagerank|betweenness)$")
    persist: bool = False
    formats: Optional[List[str]] = Field(
        default=None,
        description="Lista de formatos a devolver (raw, table, graph, all).",
    )

class GraphRAGRequest(BaseModel):
    """Request for GraphRAG query."""
    query: str = Field(..., min_length=3)
    project: str = Field(default="default")
    include_fragments: bool = Field(default=True)
    chain_of_thought: bool = Field(default=False)
    node_ids: Optional[List[Union[int, str]]] = Field(
        default=None,
        description="Scope estricto: IDs internos de nodos Neo4j (id(n)); acepta números o strings numéricos.",
    )
    # Campos opcionales proporcionados por la UI (Neo4jExplorer)
    view_nodes: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Lista de nodos visibles en la vista (id, label, optional community).",
    )
    graph_metrics: Optional[Dict[str, Dict[str, float]]] = Field(
        default=None,
        description="Métricas calculadas sobre el subgrafo (pagerank/degree/betweenness).",
    )
    graph_edges: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Lista de relaciones del subgrafo (from,to,type).",
    )
    communities_detected: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Comunidades detectadas (community_id, top_nodes).",
    )
    evidence_candidates: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Fragmentos candidatos con fragment_id, doc_id, snippet y score.",
    )
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Filtros aplicados desde la UI")
    max_central: Optional[int] = Field(default=10, description="Máximo de nodos centrales a devolver (<=10)")
    force_mode: Optional[str] = Field(default=None, description="Forzar modo 'deep' o 'exploratory'")

# Create routers
graphrag_router = APIRouter(prefix="/api/graphrag", tags=["GraphRAG"])
axial_router = APIRouter(prefix="/api/axial", tags=["Axial"])

# GDS Endpoints
@axial_router.post("/gds")
async def api_run_gds_analysis(
    payload: GDSRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> List[Dict[str, Any]]:
    """Execute Graph Data Science algorithms (Louvain, PageRank, Betweenness)."""
    clients = build_neo4j_only(settings)
    try:
        from app.project_state import resolve_project

        try:
            project_id = resolve_project(payload.project, allow_create=False)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        api_logger.info(
            "api.gds.start",
            project=project_id,
            algorithm=payload.algorithm,
            persist=payload.persist,
        )
        results = run_gds_analysis(
            cast(ServiceClients, clients),
            settings,
            payload.algorithm,
            persist=payload.persist,
            project=project_id,
        )
        api_logger.info(
            "api.gds.complete",
            project=project_id,
            algorithm=payload.algorithm,
            rows=len(results),
        )
        return results
    except AxialError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        api_logger.error("api.gds.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()

# GraphRAG Query Endpoint
@graphrag_router.post("/query")
async def api_graphrag_query(
    payload: GraphRAGRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Ejecuta una consulta GraphRAG con contexto de grafo.
    
    Combina busqueda semantica + estructura del grafo + LLM para respuestas
    contextualizadas sobre la investigacion cualitativa.
    """
    from app.graphrag import graphrag_query, graphrag_chain_of_thought
    
    clients = build_clients_or_error(settings)
    try:
        api_logger.info("api.graphrag.start", query=payload.query[:50], project=payload.project)
        
        if payload.chain_of_thought:
            result = graphrag_chain_of_thought(
                clients, settings,
                query=payload.query,
                project=payload.project,
                context_node_ids=payload.node_ids,
            )
        else:
            result = graphrag_query(
                clients, settings,
                query=payload.query,
                project=payload.project,
                include_fragments=payload.include_fragments,
                context_node_ids=payload.node_ids,
                force_mode=payload.force_mode,
            )
        
        api_logger.info("api.graphrag.complete")
        return result
        
    except Exception as exc:
        api_logger.error("api.graphrag.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()

# Link Prediction Endpoints
@axial_router.get("/predict")
async def api_axial_predict(
    source_type: str = Query(default="Codigo"),
    target_type: str = Query(default="Codigo"),
    algorithm: str = Query(default="common_neighbors"),
    top_k: int = Query(default=10, ge=1, le=50),
    project: str = Query(default="default"),
    categoria: Optional[str] = Query(default=None),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Predice enlaces faltantes en el grafo axial.
    
    Usa algoritmos de link prediction para sugerir relaciones
    que podrian estar faltando entre cÃ³digos (CÃ³digoâ†”CÃ³digo).
    """
    from app.link_prediction import suggest_links, suggest_axial_relations
    from app.project_state import resolve_project
    
    clients = build_clients_or_error(settings)
    try:
        project_id = resolve_project(project, allow_create=False, pg=clients.postgres)
        api_logger.info(
            "api.predict.start",
            algorithm=algorithm,
            source_type=source_type,
            target_type=target_type,
            project=project_id,
        )
        
        if categoria:
            # Sugerencias especificas para una categoria
            suggestions = suggest_axial_relations(
                clients, settings,
                categoria=categoria,
                project=project_id,
                top_k=top_k,
            )
        else:
            # Sugerencias generales
            suggestions = suggest_links(
                clients, settings,
                source_type=source_type,
                target_type=target_type,
                algorithm=algorithm,
                top_k=top_k,
                project=project_id,
            )
        
        api_logger.info("api.predict.complete", suggestions=len(suggestions))
        
        return {"suggestions": suggestions, "algorithm": algorithm, "project": project_id}
        
    except Exception as exc:
        api_logger.error("api.predict.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()

@axial_router.get("/community-links")
async def api_axial_community_links(
    project: str = Query(default="default"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Detecta enlaces faltantes basandose en comunidades.
    
    Nodos en la misma comunidad (Louvain) que no estan conectados
    son candidatos para nuevas relaciones.
    """
    from app.link_prediction import detect_missing_links_by_community
    from app.project_state import resolve_project
    
    clients = build_clients_or_error(settings)
    try:
        project_id = resolve_project(project, allow_create=False, pg=clients.postgres)
        suggestions = detect_missing_links_by_community(clients, settings, project_id)
        
        return {
            "project": project_id,
            "suggestions": suggestions,
            "count": len(suggestions),
        }
        
    except Exception as exc:
        api_logger.error("api.community_links.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()
