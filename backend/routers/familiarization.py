"""Familiarization router.

Adds best-practice progress tracking for Etapa 2 (Familiarización):
- Persist a reviewed flag per interview file (archivo)
- Expose progress for UI (reviewed/total + %)

This complements the existing `/api/familiarization/fragments` endpoint (kept in
`backend/app.py` for backwards compatibility).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ConfigDict

from app.clients import ServiceClients, build_service_clients
from app.settings import AppSettings, load_settings
from app.project_state import resolve_project
from app.postgres_block import (
    upsert_familiarization_review,
    delete_familiarization_review,
    list_familiarization_reviews,
)
from backend.auth import User, get_current_user

router = APIRouter(prefix="/api/familiarization", tags=["familiarization"])
logger = structlog.get_logger("app.api.familiarization")


def get_settings() -> AppSettings:
    import os

    env_file = os.getenv("APP_ENV_FILE")
    return load_settings(env_file)


from typing import AsyncGenerator


async def get_service_clients(settings: AppSettings = Depends(get_settings)) -> AsyncGenerator[ServiceClients, None]:
    """Yield clients and always close to protect PG pool."""
    clients = build_service_clients(settings)
    try:
        yield clients
    finally:
        clients.close()


async def require_auth(user: User = Depends(get_current_user)) -> User:
    return user


class ReviewMarkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: str = Field(..., description="Proyecto (nombre lógico)")
    archivo: str = Field(..., min_length=1, description="Nombre del archivo/entrevista")
    reviewed: bool = Field(True, description="true=marcar revisada, false=desmarcar")


@router.get("/reviews")
def get_reviews(
    project: str,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    project_id = resolve_project(project, allow_create=False)

    # total interviews = distinct archivo in fragments table (same basis as dashboard counts)
    with clients.postgres.cursor() as cur:
        cur.execute(
            "SELECT COUNT(DISTINCT archivo) FROM entrevista_fragmentos WHERE project_id = %s",
            (project_id,),
        )
        row = cur.fetchone()
        total_interviews = (row[0] if row else 0) or 0

    reviewed_files = list_familiarization_reviews(clients.postgres, project_id)
    reviewed_count = len(reviewed_files)
    percentage = round((reviewed_count / total_interviews) * 100, 1) if total_interviews else 0

    return {
        "project": project_id,
        "total_interviews": total_interviews,
        "reviewed_count": reviewed_count,
        "percentage": percentage,
        "reviewed_files": reviewed_files,
    }


@router.post("/reviews")
def mark_review(
    payload: ReviewMarkRequest,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    project_id = resolve_project(payload.project, allow_create=False)

    logger.info(
        "api.familiarization.review.update",
        project=project_id,
        archivo=payload.archivo,
        reviewed=payload.reviewed,
        user=user.user_id,
    )

    if payload.reviewed:
        upsert_familiarization_review(clients.postgres, project_id, payload.archivo, reviewed_by=user.user_id)
    else:
        delete_familiarization_review(clients.postgres, project_id, payload.archivo)

    # Return updated progress
    with clients.postgres.cursor() as cur:
        cur.execute(
            "SELECT COUNT(DISTINCT archivo) FROM entrevista_fragmentos WHERE project_id = %s",
            (project_id,),
        )
        row = cur.fetchone()
        total_interviews = (row[0] if row else 0) or 0

    reviewed_files = list_familiarization_reviews(clients.postgres, project_id)
    reviewed_count = len(reviewed_files)
    percentage = round((reviewed_count / total_interviews) * 100, 1) if total_interviews else 0

    return {
        "project": project_id,
        "total_interviews": total_interviews,
        "reviewed_count": reviewed_count,
        "percentage": percentage,
        "reviewed_files": reviewed_files,
    }
