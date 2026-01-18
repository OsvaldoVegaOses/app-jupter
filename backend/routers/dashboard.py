"""
Dashboard router - Project status, metrics, and real-time counts.
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
import structlog
from functools import lru_cache
import os

from app.clients import ServiceClients, build_service_clients
from app.settings import AppSettings, load_settings
from app.project_state import resolve_project, detect_stage_status, mark_stage
from main import STAGE_DEFINITIONS, STAGE_ORDER
from backend.auth import User, get_current_user

# Logger
api_logger = structlog.get_logger("app.api.dashboard")

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

# Create router
router = APIRouter(prefix="/api", tags=["Dashboard"])

# Endpoints
@router.get("/status")
async def api_status(
    project: str = Query(..., description="Proyecto requerido"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Get project stage status and progress."""
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        snapshot = detect_stage_status(
            clients.postgres,
            project_id,
            stages=STAGE_DEFINITIONS,
            stage_order=STAGE_ORDER,
        )
        return snapshot
    finally:
        clients.close()

@router.get("/dashboard/counts")
async def api_dashboard_counts(
    project: str = Query(..., description="Proyecto requerido"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Obtiene conteos en tiempo real para el dashboard.
    
    Este endpoint resuelve el Bug E1.1: "0 fragmentos" en Etapa 2.
    A diferencia de /api/status que lee el state guardado, este endpoint
    consulta directamente la base de datos para obtener conteos actualizados.
    
    Returns:
        Dict con conteos por etapa:
        - ingesta: archivos, fragmentos, speaker distribution
        - codificacion: códigos, citas, cobertura
        - axial: relaciones, categorías
        - candidatos: pendientes, validados, rechazados
    """
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        from app.dashboard import get_dashboard_counts
        counts = get_dashboard_counts(clients.postgres, project_id)
        return counts
    finally:
        clients.close()

@router.post("/projects/{project_id}/stages/{stage}/complete")
async def api_complete_stage(
    project_id: str,
    stage: str,
    run_id: Optional[str] = None,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Mark a project stage as complete."""
    if stage not in STAGE_DEFINITIONS:
        raise HTTPException(status_code=400, detail=f"Etapa desconocida: {stage}")
    
    try:
        resolved_project = resolve_project(project_id, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        payload = mark_stage(
            clients.postgres,
            resolved_project,
            stage,
            run_id=run_id or "-",
            command="workflow",
            subcommand="complete",
            extras=None,
        )
        return payload
    finally:
        clients.close()

