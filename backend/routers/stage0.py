"""Etapa 0 (Preparación): protocolo, actores anonimizados, consentimientos, muestreo, plan y overrides.

Diseño:
- PII no se almacena aquí (solo alias + demographics_anon).
- Overrides: doble validación: analyst solicita (pending) y admin aprueba/rechaza.
- Auditoría: se registra en project_audit_log vía app.postgres_block.log_project_action.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta
from time import perf_counter
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.clients import ServiceClients
from app.postgres_block import check_project_permission, log_project_action
from app.settings import load_settings
from backend.auth import User, get_current_user, require_role


# =============================================================================
# Dependencies
# =============================================================================

async def get_service_clients() -> AsyncGenerator[ServiceClients, None]:
    from app.clients import build_service_clients

    env_file = os.getenv("APP_ENV_FILE")
    settings = load_settings(env_file)
    clients = build_service_clients(settings)
    try:
        yield clients
    finally:
        clients.close()


# =============================================================================
# Models
# =============================================================================

ReasonCategory = Literal[
    "critical_incident",
    "data_validation",
    "service_continuity",
    "protocol_exception",
    "other",
]

Scope = Literal["ingest", "analyze", "both"]


class OverrideRequestIn(BaseModel):
    scope: Scope = "both"
    reason_category: ReasonCategory
    reason_details: str = Field(..., min_length=3, max_length=2000, description="Motivo detallado (obligatorio para auditoría)")
    requested_expires_hours: int = Field(24, ge=1, le=168, description="TTL sugerido (horas)")


class OverrideDecisionIn(BaseModel):
    decision_note: str = Field(..., min_length=3, max_length=2000, description="Nota de decisión (obligatoria para auditoría)")
    expires_hours: int = Field(24, ge=1, le=168)


class ActorIn(BaseModel):
    alias: str = Field(..., min_length=1, max_length=64)
    demographics_anon: Dict[str, Any] = Field(default_factory=dict)
    tags: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class ConsentIn(BaseModel):
    version: int = Field(..., ge=1)
    signed_at: Optional[str] = None
    scope: Dict[str, Any] = Field(default_factory=dict)
    evidence_url: Optional[str] = None
    notes: Optional[str] = None


class VersionedDocIn(BaseModel):
    version: int = Field(..., ge=1)
    title: Optional[str] = None
    content: Dict[str, Any] = Field(default_factory=dict)
    status: Optional[str] = None


# =============================================================================
# Router
# =============================================================================

router = APIRouter(prefix="/api/stage0", tags=["Stage0"])


def _now_iso() -> str:
    return datetime.now().isoformat()


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value)


@router.get("/status")
async def stage0_status(
    project: str = Query(..., description="Project id"),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Checklist de Etapa 0 para bloquear/permitir ingest/analyze."""
    t0 = perf_counter()

    with clients.postgres.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM stage0_protocols WHERE project_id = %s",
            (project,),
        )
        row = cur.fetchone()
        protocols = int(row[0]) if row else 0

        cur.execute(
            "SELECT COUNT(*) FROM stage0_actors WHERE project_id = %s",
            (project,),
        )
        row = cur.fetchone()
        actors = int(row[0]) if row else 0

        cur.execute(
            """
            SELECT COUNT(*)
              FROM stage0_actors a
             WHERE a.project_id = %s
               AND NOT EXISTS (
                 SELECT 1
                   FROM stage0_consents c
                  WHERE c.project_id = a.project_id
                    AND c.actor_id = a.actor_id
                    AND c.revoked_at IS NULL
               )
            """,
            (project,),
        )
        row = cur.fetchone()
        actors_missing_consent = int(row[0]) if row else 0

        cur.execute(
            "SELECT COUNT(*) FROM stage0_sampling_criteria WHERE project_id = %s",
            (project,),
        )
        row = cur.fetchone()
        sampling = int(row[0]) if row else 0

        cur.execute(
            "SELECT COUNT(*) FROM stage0_analysis_plans WHERE project_id = %s",
            (project,),
        )
        row = cur.fetchone()
        plans = int(row[0]) if row else 0

        # active approved override
        cur.execute(
            """
            SELECT override_id, scope, reason_category, requested_by, decided_by, decided_at, expires_at
              FROM stage0_override_requests
             WHERE project_id = %s
               AND status = 'approved'
               AND (expires_at IS NULL OR expires_at > NOW())
             ORDER BY decided_at DESC NULLS LAST
             LIMIT 1
            """,
            (project,),
        )
        override_row = cur.fetchone()

    protocol_ok = protocols > 0
    actors_ok = actors > 0
    consents_ok = actors > 0 and actors_missing_consent == 0
    sampling_ok = sampling > 0
    plan_ok = plans > 0

    ready = protocol_ok and actors_ok and consents_ok and sampling_ok and plan_ok

    override = None
    if override_row:
        override = {
            "override_id": override_row[0],
            "scope": override_row[1],
            "reason_category": override_row[2],
            "requested_by": override_row[3],
            "approved_by": override_row[4],
            "approved_at": override_row[5].isoformat() if override_row[5] else None,
            "expires_at": override_row[6].isoformat() if override_row[6] else None,
        }

    latency_ms = round((perf_counter() - t0) * 1000, 2)
    return {
        "project": project,
        "ready": ready,
        "checks": {
            "protocol": protocol_ok,
            "actors": actors_ok,
            "consents": consents_ok,
            "sampling": sampling_ok,
            "analysis_plan": plan_ok,
        },
        "counters": {
            "protocols": protocols,
            "actors": actors,
            "actors_missing_consent": actors_missing_consent,
            "sampling_versions": sampling,
            "plan_versions": plans,
        },
        "override": override,
        "latency_ms": latency_ms,
        "timestamp": _now_iso(),
    }


@router.post("/protocol")
async def upsert_protocol(
    payload: VersionedDocIn,
    project: str = Query(...),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin", "analyst"])),
) -> Dict[str, Any]:
    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            INSERT INTO stage0_protocols (project_id, version, title, content, status, created_by)
            VALUES (%s, %s, %s, %s::jsonb, %s, %s)
            ON CONFLICT (project_id, version) DO UPDATE SET
              title = EXCLUDED.title,
              content = EXCLUDED.content,
              status = COALESCE(EXCLUDED.status, stage0_protocols.status)
            RETURNING project_id, version, status, created_at
            """,
            (
                project,
                payload.version,
                payload.title,
                json.dumps(payload.content or {}),
                payload.status or "draft",
                user.user_id,
            ),
        )
        row = cur.fetchone()
    clients.postgres.commit()

    if not row:
        raise HTTPException(status_code=500, detail="Database error: protocol upsert returned no data")

    log_project_action(
        clients.postgres,
        project=project,
        user_id=user.user_id,
        action="stage0.protocol.upsert",
        entity_type="stage0_protocols",
        entity_id=str(payload.version),
        details={"status": payload.status or "draft", "title": payload.title},
    )

    return {"project_id": row[0], "version": row[1], "status": row[2], "created_at": row[3].isoformat() if row[3] else None}


@router.get("/protocol/latest")
async def get_latest_protocol(
    project: str = Query(...),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retorna la última versión del protocolo (si existe)."""
    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            SELECT project_id, version, title, content, status, created_by, created_at
              FROM stage0_protocols
             WHERE project_id = %s
             ORDER BY version DESC, created_at DESC
             LIMIT 1
            """,
            (project,),
        )
        row = cur.fetchone()

    if row is None:
        return {"project": project, "protocol": None}

    return {
        "project": project,
        "protocol": {
            "project_id": row[0],
            "version": row[1],
            "title": row[2],
            "content": row[3] or {},
            "status": row[4],
            "created_by": row[5],
            "created_at": row[6].isoformat() if row[6] else None,
        },
    }


@router.post("/actors")
async def create_actor(
    payload: ActorIn,
    project: str = Query(...),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin", "analyst"])),
) -> Dict[str, Any]:
    actor_id = str(uuid.uuid4())
    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            INSERT INTO stage0_actors (actor_id, project_id, alias, demographics_anon, tags, notes, created_by)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
            RETURNING actor_id, alias, created_at
            """,
            (
                actor_id,
                project,
                payload.alias,
                json.dumps(payload.demographics_anon or {}),
                json.dumps(payload.tags) if payload.tags is not None else None,
                payload.notes,
                user.user_id,
            ),
        )
        row = cur.fetchone()
    clients.postgres.commit()

    if not row:
        raise HTTPException(status_code=500, detail="Database error: actor creation returned no data")

    log_project_action(
        clients.postgres,
        project=project,
        user_id=user.user_id,
        action="stage0.actor.create",
        entity_type="stage0_actors",
        entity_id=actor_id,
        details={"alias": payload.alias},
    )

    return {"actor_id": row[0], "alias": row[1], "created_at": row[2].isoformat() if row[2] else None}


@router.get("/actors")
async def list_actors(
    project: str = Query(...),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    with clients.postgres.cursor() as cur:
        cur.execute(
            """
                        SELECT a.actor_id,
                                     a.alias,
                                     a.demographics_anon,
                                     a.tags,
                                     a.notes,
                                     a.created_at,
                                     EXISTS (
                                         SELECT 1
                                             FROM stage0_consents c
                                            WHERE c.project_id = a.project_id
                                                AND c.actor_id = a.actor_id
                                                AND c.revoked_at IS NULL
                                     ) AS has_active_consent,
                                     (
                                         SELECT c.version
                                             FROM stage0_consents c
                                            WHERE c.project_id = a.project_id
                                                AND c.actor_id = a.actor_id
                                            ORDER BY c.created_at DESC
                                            LIMIT 1
                                     ) AS latest_consent_version,
                                     (
                                         SELECT c.signed_at
                                             FROM stage0_consents c
                                            WHERE c.project_id = a.project_id
                                                AND c.actor_id = a.actor_id
                                            ORDER BY c.created_at DESC
                                            LIMIT 1
                                     ) AS latest_signed_at
                            FROM stage0_actors a
                         WHERE a.project_id = %s
                         ORDER BY a.created_at
            """,
            (project,),
        )
        rows = cur.fetchall()
    return {
        "project": project,
        "actors": [
            {
                "actor_id": r[0],
                "alias": r[1],
                "demographics_anon": r[2],
                "tags": r[3],
                "notes": r[4],
                "created_at": r[5].isoformat() if r[5] else None,
                                "has_active_consent": bool(r[6]),
                                "latest_consent_version": r[7],
                                "latest_signed_at": r[8].isoformat() if r[8] else None,
            }
            for r in rows
        ],
    }


@router.post("/actors/{actor_id}/consents")
async def create_consent(
    actor_id: str,
    payload: ConsentIn,
    project: str = Query(...),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin", "analyst"])),
) -> Dict[str, Any]:
    consent_id = str(uuid.uuid4())
    signed_at = _parse_dt(payload.signed_at)
    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            INSERT INTO stage0_consents (consent_id, project_id, actor_id, version, signed_at, scope, evidence_url, notes, created_by)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            RETURNING consent_id, version, created_at
            """,
            (
                consent_id,
                project,
                actor_id,
                payload.version,
                signed_at,
                json.dumps(payload.scope or {}),
                payload.evidence_url,
                payload.notes,
                user.user_id,
            ),
        )
        row = cur.fetchone()
    clients.postgres.commit()

    if not row:
        raise HTTPException(status_code=500, detail="Database error: consent creation returned no data")

    log_project_action(
        clients.postgres,
        project=project,
        user_id=user.user_id,
        action="stage0.consent.create",
        entity_type="stage0_consents",
        entity_id=consent_id,
        details={"actor_id": actor_id, "version": payload.version},
    )

    return {"consent_id": row[0], "version": row[1], "created_at": row[2].isoformat() if row[2] else None}


@router.post("/sampling")
async def upsert_sampling(
    payload: VersionedDocIn,
    project: str = Query(...),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin", "analyst"])),
) -> Dict[str, Any]:
    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            INSERT INTO stage0_sampling_criteria (project_id, version, content, created_by)
            VALUES (%s, %s, %s::jsonb, %s)
            ON CONFLICT (project_id, version) DO UPDATE SET
              content = EXCLUDED.content
            RETURNING project_id, version, created_at
            """,
            (project, payload.version, json.dumps(payload.content or {}), user.user_id),
        )
        row = cur.fetchone()
    clients.postgres.commit()

    if not row:
        raise HTTPException(status_code=500, detail="Database error: sampling upsert returned no data")

    log_project_action(
        clients.postgres,
        project=project,
        user_id=user.user_id,
        action="stage0.sampling.upsert",
        entity_type="stage0_sampling_criteria",
        entity_id=str(payload.version),
        details={},
    )

    return {"project_id": row[0], "version": row[1], "created_at": row[2].isoformat() if row[2] else None}


@router.get("/sampling/latest")
async def get_latest_sampling(
    project: str = Query(...),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retorna la última versión de criterios de muestreo (si existe)."""
    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            SELECT project_id, version, content, created_by, created_at
              FROM stage0_sampling_criteria
             WHERE project_id = %s
             ORDER BY version DESC, created_at DESC
             LIMIT 1
            """,
            (project,),
        )
        row = cur.fetchone()

    if row is None:
        return {"project": project, "sampling": None}

    return {
        "project": project,
        "sampling": {
            "project_id": row[0],
            "version": row[1],
            "content": row[2] or {},
            "created_by": row[3],
            "created_at": row[4].isoformat() if row[4] else None,
        },
    }


@router.post("/analysis-plan")
async def upsert_analysis_plan(
    payload: VersionedDocIn,
    project: str = Query(...),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin", "analyst"])),
) -> Dict[str, Any]:
    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            INSERT INTO stage0_analysis_plans (project_id, version, content, created_by)
            VALUES (%s, %s, %s::jsonb, %s)
            ON CONFLICT (project_id, version) DO UPDATE SET
              content = EXCLUDED.content
            RETURNING project_id, version, created_at
            """,
            (project, payload.version, json.dumps(payload.content or {}), user.user_id),
        )
        row = cur.fetchone()
    clients.postgres.commit()

    if not row:
        raise HTTPException(status_code=500, detail="Database error: analysis plan upsert returned no data")

    log_project_action(
        clients.postgres,
        project=project,
        user_id=user.user_id,
        action="stage0.plan.upsert",
        entity_type="stage0_analysis_plans",
        entity_id=str(payload.version),
        details={},
    )

    return {"project_id": row[0], "version": row[1], "created_at": row[2].isoformat() if row[2] else None}


@router.get("/analysis-plan/latest")
async def get_latest_analysis_plan(
    project: str = Query(...),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retorna la última versión del plan de análisis (si existe)."""
    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            SELECT project_id, version, content, created_by, created_at
              FROM stage0_analysis_plans
             WHERE project_id = %s
             ORDER BY version DESC, created_at DESC
             LIMIT 1
            """,
            (project,),
        )
        row = cur.fetchone()

    if row is None:
        return {"project": project, "analysis_plan": None}

    return {
        "project": project,
        "analysis_plan": {
            "project_id": row[0],
            "version": row[1],
            "content": row[2] or {},
            "created_by": row[3],
            "created_at": row[4].isoformat() if row[4] else None,
        },
    }


@router.get("/overrides")
async def list_overrides(
    project: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Lista overrides recientes (pending/approved/rejected) para el proyecto."""
    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            SELECT override_id,
                   scope,
                   status,
                   reason_category,
                   reason_details,
                   requested_by,
                   requested_at,
                   decided_by,
                   decided_at,
                   decision_note,
                   expires_at
              FROM stage0_override_requests
             WHERE project_id = %s
             ORDER BY requested_at DESC
             LIMIT %s
            """,
            (project, limit),
        )
        rows = cur.fetchall()

    return {
        "project": project,
        "overrides": [
            {
                "override_id": r[0],
                "scope": r[1],
                "status": r[2],
                "reason_category": r[3],
                "reason_details": r[4],
                "requested_by": r[5],
                "requested_at": r[6].isoformat() if r[6] else None,
                "decided_by": r[7],
                "decided_at": r[8].isoformat() if r[8] else None,
                "decision_note": r[9],
                "expires_at": r[10].isoformat() if r[10] else None,
            }
            for r in rows
        ],
    }


@router.post("/overrides")
async def request_override(
    payload: OverrideRequestIn,
    project: str = Query(...),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin", "analyst"])),
) -> Dict[str, Any]:
    # Mínimos privilegios: para solicitar override debe tener rol de proyecto (>= codificador)
    # o ser admin global. (Los overrides afectan gating de ingest/analyze.)
    is_admin = "admin" in {str(r).strip().lower() for r in (user.roles or []) if r}
    if not is_admin and not check_project_permission(clients.postgres, project, user.user_id, "codificador"):
        raise HTTPException(status_code=403, detail="Permiso insuficiente: requiere rol codificador/admin en el proyecto para solicitar override")

    override_id = str(uuid.uuid4())
    # Request includes a suggested TTL; actual TTL will be set on approval.
    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            INSERT INTO stage0_override_requests (override_id, project_id, scope, reason_category, reason_details, requested_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING override_id, status, requested_at
            """,
            (
                override_id,
                project,
                payload.scope,
                payload.reason_category,
                payload.reason_details,
                user.user_id,
            ),
        )
        row = cur.fetchone()
    clients.postgres.commit()

    if not row:
        raise HTTPException(status_code=500, detail="Database error: override request returned no data")

    log_project_action(
        clients.postgres,
        project=project,
        user_id=user.user_id,
        action="stage0.override.requested",
        entity_type="stage0_override_requests",
        entity_id=override_id,
        details={
            "scope": payload.scope,
            "reason_category": payload.reason_category,
            "reason_details": payload.reason_details,
            "requested_expires_hours": payload.requested_expires_hours,
        },
    )

    return {"override_id": row[0], "status": row[1], "requested_at": row[2].isoformat() if row[2] else None}


@router.post("/overrides/{override_id}/approve")
async def approve_override(
    override_id: str,
    payload: OverrideDecisionIn,
    project: str = Query(...),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    # Mínimos privilegios: solo admin del proyecto (o admin global) puede aprobar.
    is_admin = "admin" in {str(r).strip().lower() for r in (user.roles or []) if r}
    if not is_admin and not check_project_permission(clients.postgres, project, user.user_id, "admin"):
        raise HTTPException(status_code=403, detail="Permiso insuficiente: requiere admin del proyecto para aprobar overrides")

    # Separación de funciones: prohibir auto-aprobación (requested_by != decided_by)
    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            SELECT requested_by
              FROM stage0_override_requests
             WHERE override_id = %s
               AND project_id = %s
               AND status = 'pending'
            """,
            (override_id, project),
        )
        row_req = cur.fetchone()
    if row_req and str(row_req[0]) == str(user.user_id):
        raise HTTPException(status_code=403, detail="Separación de funciones: no se permite auto-aprobar un override solicitado por el mismo usuario")

    expires_at = datetime.now() + timedelta(hours=payload.expires_hours)

    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            UPDATE stage0_override_requests
               SET status = 'approved',
                   decided_by = %s,
                   decided_at = NOW(),
                   decision_note = %s,
                   expires_at = %s
             WHERE override_id = %s
               AND project_id = %s
               AND status = 'pending'
            RETURNING override_id, scope, reason_category, requested_by, decided_at, expires_at
            """,
            (user.user_id, payload.decision_note, expires_at, override_id, project),
        )
        row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Override no encontrado o no está pendiente")

    clients.postgres.commit()

    log_project_action(
        clients.postgres,
        project=project,
        user_id=user.user_id,
        action="stage0.override.approved",
        entity_type="stage0_override_requests",
        entity_id=override_id,
        details={
            "scope": row[1],
            "reason_category": row[2],
            "requested_by": row[3],
            "decision_note": payload.decision_note,
            "expires_at": row[5].isoformat() if row[5] else None,
        },
    )

    return {
        "override_id": row[0],
        "status": "approved",
        "scope": row[1],
        "reason_category": row[2],
        "requested_by": row[3],
        "approved_at": row[4].isoformat() if row[4] else None,
        "expires_at": row[5].isoformat() if row[5] else None,
    }


@router.post("/overrides/{override_id}/reject")
async def reject_override(
    override_id: str,
    payload: OverrideDecisionIn,
    project: str = Query(...),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    # Mínimos privilegios: solo admin del proyecto (o admin global) puede rechazar.
    is_admin = "admin" in {str(r).strip().lower() for r in (user.roles or []) if r}
    if not is_admin and not check_project_permission(clients.postgres, project, user.user_id, "admin"):
        raise HTTPException(status_code=403, detail="Permiso insuficiente: requiere admin del proyecto para rechazar overrides")

    # Separación de funciones: prohibir auto-rechazo (requested_by != decided_by)
    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            SELECT requested_by
              FROM stage0_override_requests
             WHERE override_id = %s
               AND project_id = %s
               AND status = 'pending'
            """,
            (override_id, project),
        )
        row_req = cur.fetchone()
    if row_req and str(row_req[0]) == str(user.user_id):
        raise HTTPException(status_code=403, detail="Separación de funciones: no se permite decidir (rechazar) un override solicitado por el mismo usuario")

    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            UPDATE stage0_override_requests
               SET status = 'rejected',
                   decided_by = %s,
                   decided_at = NOW(),
                   decision_note = %s
             WHERE override_id = %s
               AND project_id = %s
               AND status = 'pending'
            RETURNING override_id, scope, reason_category, requested_by, decided_at
            """,
            (user.user_id, payload.decision_note, override_id, project),
        )
        row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Override no encontrado o no está pendiente")

    clients.postgres.commit()

    log_project_action(
        clients.postgres,
        project=project,
        user_id=user.user_id,
        action="stage0.override.rejected",
        entity_type="stage0_override_requests",
        entity_id=override_id,
        details={
            "scope": row[1],
            "reason_category": row[2],
            "requested_by": row[3],
            "decision_note": payload.decision_note,
        },
    )

    return {
        "override_id": row[0],
        "status": "rejected",
        "scope": row[1],
        "reason_category": row[2],
        "requested_by": row[3],
        "rejected_at": row[4].isoformat() if row[4] else None,
    }
