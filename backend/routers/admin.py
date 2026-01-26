"""Admin router - User management, project management, and system maintenance endpoints."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from time import perf_counter
from typing import Any, Dict, List, Literal, Optional, Tuple
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from psycopg2.extras import Json
from pydantic import BaseModel, Field
import structlog

from app.clients import ServiceClients
from backend.auth import User, get_current_user, require_role


logger = structlog.get_logger("app.api.admin")

# =============================================================================
# Admin Ops enums (closed sets)
# =============================================================================

OpsKind = Literal["all", "errors", "mutations"]
OpsOp = Literal["all", "backfill", "repair", "sync", "maintenance", "ontology"]
OpsIntent = Literal["all", "write_intent_post"]


# =============================================================================
# DEPENDENCIES
# =============================================================================

from typing import AsyncGenerator

async def get_service_clients() -> AsyncGenerator[ServiceClients, None]:
    """
    Dependency that builds ServiceClients with automatic cleanup.
    
    CRITICAL: Uses yield + finally to ensure connections are returned to pool!
    """
    from app.clients import build_service_clients
    from app.settings import load_settings
    import os
    env_file = os.getenv("APP_ENV_FILE")
    settings = load_settings(env_file)
    clients = build_service_clients(settings)
    try:
        yield clients
    finally:
        clients.close()


async def require_auth(user: User = Depends(get_current_user)) -> User:
    return user


# =============================================================================
# MODELS
# =============================================================================

class UserUpdate(BaseModel):
    """Model for updating user properties."""
    role: Optional[str] = None  # admin, analyst, viewer
    is_active: Optional[bool] = None


class UserListItem(BaseModel):
    """User info for admin list."""
    id: str
    email: str
    full_name: Optional[str]
    role: str
    organization_id: str
    is_active: bool
    created_at: str
    last_login_at: Optional[str]


class LinkPredictionReopenRequest(BaseModel):
    """Reapertura controlada de una predicción cerrada."""
    reason: str = Field(..., min_length=5, description="Motivo de reapertura (obligatorio)")
    evidence_link: Optional[str] = Field(None, description="Link opcional a evidencia o ticket")


# =============================================================================
# ROUTERS
# =============================================================================

router = APIRouter(prefix="/api", tags=["Admin"])
health_router = APIRouter(tags=["Health"])


def _pg_has_table(pg, table_name: str) -> bool:
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT 1
              FROM information_schema.tables
             WHERE table_schema = 'public'
               AND table_name = %s
             LIMIT 1
            """,
            (table_name,),
        )
        return cur.fetchone() is not None


def _pg_has_column(pg, table_name: str, column_name: str) -> bool:
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = %s
               AND column_name = %s
             LIMIT 1
            """,
            (table_name, column_name),
        )
        return cur.fetchone() is not None


def _pg_get_column_udt(pg, table_name: str, column_name: str) -> Optional[str]:
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT udt_name
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = %s
               AND column_name = %s
             LIMIT 1
            """,
            (table_name, column_name),
        )
        row = cur.fetchone()
        return str(row[0]) if row and row[0] is not None else None


def _advisory_lock_key(project: str, op: str) -> Tuple[int, int]:
    """Claves estables para advisory locks.

    Usamos la variante `pg_try_advisory_lock(int4, int4)` para evitar
    desbordes/"numeric" cuando la clave no cabe en BIGINT con signo.
    """

    payload = f"code_id:{op}:{project}".encode("utf-8")
    digest = hashlib.sha256(payload).digest()

    # Convertir a int32 con signo.
    k1 = int.from_bytes(digest[:4], byteorder="big", signed=False)
    k2 = int.from_bytes(digest[4:8], byteorder="big", signed=False)
    if k1 >= 2**31:
        k1 -= 2**32
    if k2 >= 2**31:
        k2 -= 2**32
    return (k1, k2)


def _try_advisory_lock(pg, key: Tuple[int, int]) -> bool:
    with pg.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s, %s)", key)
        return bool((cur.fetchone() or [False])[0])


def _advisory_unlock(pg, key: Tuple[int, int]) -> None:
    with pg.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(%s, %s)", key)


def _require_code_id_columns(pg) -> None:
    missing = []
    if not _pg_has_column(pg, "catalogo_codigos", "code_id"):
        missing.append("code_id")
    if not _pg_has_column(pg, "catalogo_codigos", "canonical_code_id"):
        missing.append("canonical_code_id")
    if missing:
        raise HTTPException(
            status_code=409,
            detail=(
                "La base aún no tiene columnas de Fase 1.5 en catalogo_codigos: "
                + ", ".join(missing)
                + ". Aplica primero la migración de code_id/canonical_code_id."
            ),
        )


def _require_ontology_freeze_table(pg) -> None:
    if not _pg_has_table(pg, "project_ontology_freeze"):
        raise HTTPException(
            status_code=409,
            detail=(
                "La base aún no tiene tabla de freeze ontológico (project_ontology_freeze). "
                "Aplica la migración 015_ontology_freeze.sql y reintenta."
            ),
        )


def _get_ontology_freeze(pg, project: str) -> Dict[str, Any]:
    """Retorna estado de freeze. Si no hay fila, asume no congelado."""
    _require_ontology_freeze_table(pg)
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT is_frozen, frozen_at, frozen_by, broken_at, broken_by, note, updated_at
              FROM project_ontology_freeze
             WHERE project_id = %s
            """,
            (project,),
        )
        row = cur.fetchone()

    if row is None:
        return {
            "project": project,
            "is_frozen": False,
            "frozen_at": None,
            "frozen_by": None,
            "broken_at": None,
            "broken_by": None,
            "note": None,
            "updated_at": None,
        }

    return {
        "project": project,
        "is_frozen": bool(row[0]),
        "frozen_at": row[1].isoformat() if row[1] else None,
        "frozen_by": row[2],
        "broken_at": row[3].isoformat() if row[3] else None,
        "broken_by": row[4],
        "note": row[5],
        "updated_at": row[6].isoformat() if row[6] else None,
    }


def _require_not_frozen(pg, project: str, *, operation: str) -> None:
    state = _get_ontology_freeze(pg, project)
    if state.get("is_frozen"):
        raise HTTPException(
            status_code=423,
            detail=(
                f"Proyecto '{project}' está en freeze ontológico. "
                f"Operación '{operation}' bloqueada. Rompe el freeze explícitamente desde /api/admin/ontology/freeze/break."
            ),
        )


@health_router.get("/healthz")
async def healthz() -> Dict[str, Any]:
    """Health check endpoint for frontend BackendStatus component."""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }


@health_router.get("/api/health/postgres")
async def health_postgres() -> Dict[str, Any]:
    """Lightweight PostgreSQL check that exercises the *runtime* env + pool.

    This is useful when the frontend reports "CORS" but the real root cause is
    a backend 500/503 due to Postgres connectivity or stale env in the running
    uvicorn process.
    """
    import os

    from app.clients import get_pg_connection, return_pg_connection
    from app.settings import load_settings

    env_file = os.getenv("APP_ENV_FILE")
    settings = load_settings(env_file)

    started = perf_counter()
    conn = None
    try:
        conn = get_pg_connection(settings)
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            cur.fetchone()

        latency_ms = round((perf_counter() - started) * 1000, 2)
        return {
            "status": "ok",
            "service": "postgres",
            "latency_ms": latency_ms,
            "host": settings.postgres.host,
            "database": settings.postgres.database,
            "user": settings.postgres.username,
            "sslmode": getattr(settings.postgres, "sslmode", None),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as exc:  # noqa: BLE001
        latency_ms = round((perf_counter() - started) * 1000, 2)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "service": "postgres",
                "latency_ms": latency_ms,
                "error": str(exc),
            },
        )
    finally:
        if conn is not None:
            return_pg_connection(conn)


# =============================================================================
# USER MANAGEMENT ENDPOINTS (Admin only)
# =============================================================================

@router.get("/admin/users", response_model=Dict[str, Any])
async def list_users(
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """
    Lista todos los usuarios de la organización del admin.
    Solo accesible para usuarios con rol 'admin'.
    """
    with clients.postgres.cursor() as cur:
        cur.execute("""
            SELECT id, email, full_name, role, organization_id, is_active, 
                   created_at, last_login_at
            FROM app_users 
            WHERE organization_id = %s
            ORDER BY created_at DESC
        """, (user.organization_id,))
        
        columns = [desc[0] for desc in cur.description]
        users = []
        for row in cur.fetchall():
            user_dict = dict(zip(columns, row))
            # Convert datetime to string
            for key in ['created_at', 'last_login_at']:
                if user_dict.get(key):
                    user_dict[key] = user_dict[key].isoformat()
            users.append(user_dict)
    
    return {
        "organization_id": user.organization_id,
        "total": len(users),
        "users": users
    }


# =============================================================================
# CODE_ID TRANSITION (Fase 1.5) — Maintenance-only endpoints (Admin only)
# =============================================================================


class CodeIdBackfillRequest(BaseModel):
    mode: Literal["code_id", "canonical_code_id", "all"] = "all"
    dry_run: bool = True
    confirm: bool = False
    batch_size: int = Field(default=500, ge=10, le=5000)


class CodeIdRepairRequest(BaseModel):
    action: Literal["derive_text_from_id", "derive_id_from_text", "fix_self_pointing_mapped"]
    dry_run: bool = True
    confirm: bool = False
    batch_size: int = Field(default=1000, ge=10, le=5000)


class OntologyFreezeRequest(BaseModel):
    note: Optional[str] = None


class OntologyFreezeBreakRequest(BaseModel):
    confirm: bool = False
    phrase: str = ""
    note: Optional[str] = None


@router.get("/admin/code-id/status")
async def api_admin_code_id_status(
    project: str,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Estado de la transición a code_id (Fase 1.5). Operativo/infra, no analítico."""

    # Ensure base table exists (legacy-compatible).
    try:
        from app.postgres_block import ensure_codes_catalog_table

        ensure_codes_catalog_table(clients.postgres)
    except Exception:
        # Best-effort: if something fails here, we still return schema facts.
        pass

    has_table = _pg_has_table(clients.postgres, "catalogo_codigos")
    if not has_table:
        return {
            "project": project,
            "supported": False,
            "reason": "catalogo_codigos no existe",
            "has_table": False,
        }

    has_code_id = _pg_has_column(clients.postgres, "catalogo_codigos", "code_id")
    has_canonical_code_id = _pg_has_column(clients.postgres, "catalogo_codigos", "canonical_code_id")
    has_canonical_codigo = _pg_has_column(clients.postgres, "catalogo_codigos", "canonical_codigo")
    supported = bool(has_code_id and has_canonical_code_id and has_canonical_codigo)

    counts: Dict[str, Any] = {}
    blocking_reasons: List[str] = []

    ontology_freeze: Optional[Dict[str, Any]]
    if _pg_has_table(clients.postgres, "project_ontology_freeze"):
        try:
            ontology_freeze = _get_ontology_freeze(clients.postgres, project)
        except Exception:
            ontology_freeze = None
    else:
        ontology_freeze = None

    with clients.postgres.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*)::INT FROM catalogo_codigos WHERE project_id = %s",
            (project,),
        )
        counts["total_rows"] = int((cur.fetchone() or [0])[0] or 0)

        if has_code_id:
            cur.execute(
                "SELECT COUNT(*)::INT FROM catalogo_codigos WHERE project_id = %s AND code_id IS NULL",
                (project,),
            )
            counts["missing_code_id"] = int((cur.fetchone() or [0])[0] or 0)
        else:
            counts["missing_code_id"] = None

        if has_canonical_code_id:
            cur.execute(
                """
                SELECT COUNT(*)::INT
                  FROM catalogo_codigos
                 WHERE project_id = %s
                   AND status IN ('merged','superseded')
                   AND canonical_code_id IS NULL
                """,
                (project,),
            )
            counts["missing_canonical_code_id_for_noncanonical"] = int((cur.fetchone() or [0])[0] or 0)
        else:
            counts["missing_canonical_code_id_for_noncanonical"] = None

        # Merges pendientes: merged sin puntero canónico por ID.
        if has_canonical_code_id:
            cur.execute(
                """
                SELECT COUNT(*)::INT
                  FROM catalogo_codigos
                 WHERE project_id = %s
                   AND status = 'merged'
                   AND canonical_code_id IS NULL
                """,
                (project,),
            )
            counts["pending_merges"] = int((cur.fetchone() or [0])[0] or 0)
        else:
            counts["pending_merges"] = None

        # Auto-referencias por ID (invalidan la redirección)
        if has_canonical_code_id and has_code_id:
            cur.execute(
                """
                SELECT COUNT(*)::INT
                  FROM catalogo_codigos
                 WHERE project_id = %s
                   AND canonical_code_id IS NOT NULL
                   AND code_id IS NOT NULL
                   AND canonical_code_id = code_id
                """,
                (project,),
            )
            counts["self_pointing_canonical_code_id"] = int((cur.fetchone() or [0])[0] or 0)
        else:
            counts["self_pointing_canonical_code_id"] = None

        # Alias semántico: self-canonical es estado esperado (NO bloqueante).
        counts["self_canonical_nodes"] = counts.get("self_pointing_canonical_code_id")

        if supported:
            cur.execute(
                """
                SELECT COUNT(*)::INT
                  FROM catalogo_codigos src
                  JOIN catalogo_codigos tgt
                    ON tgt.project_id = src.project_id
                   AND tgt.code_id = src.canonical_code_id
                 WHERE src.project_id = %s
                   AND src.canonical_code_id IS NOT NULL
                   AND src.canonical_codigo IS NOT NULL
                   AND lower(src.canonical_codigo) <> lower(tgt.codigo)
                """,
                (project,),
            )
            counts["divergences_text_vs_id"] = int((cur.fetchone() or [0])[0] or 0)
        else:
            counts["divergences_text_vs_id"] = None

                # Detección de ciclos NO triviales en canonical_code_id (best-effort, profundidad limitada).
        if supported:
            cur.execute(
                """
                WITH RECURSIVE walk AS (
                  SELECT project_id,
                         code_id,
                         canonical_code_id,
                         ARRAY[code_id] AS path,
                         FALSE AS cycle
                    FROM catalogo_codigos
                   WHERE project_id = %s
                     AND code_id IS NOT NULL
                     AND canonical_code_id IS NOT NULL
                  UNION ALL
                  SELECT w.project_id,
                         c.code_id,
                         c.canonical_code_id,
                         w.path || c.code_id,
                         (c.code_id = ANY(w.path)) AS cycle
                    FROM walk w
                    JOIN catalogo_codigos c
                      ON c.project_id = w.project_id
                     AND c.code_id = w.canonical_code_id
                   WHERE w.cycle = FALSE
                     AND array_length(w.path, 1) < 25
                     AND c.code_id IS NOT NULL
                )
                                SELECT COUNT(DISTINCT n)::INT
                                    FROM (
                                        SELECT unnest(path) AS n
                                            FROM walk
                                         WHERE cycle = TRUE
                                             AND array_length(path, 1) > 2
                                    ) s
                """,
                (project,),
            )
            counts["cycle_nodes"] = int((cur.fetchone() or [0])[0] or 0)
        else:
            counts["cycle_nodes"] = None

        # Alias explícito: cycle_nodes ya excluye self-loops; se mantiene por compatibilidad.
        counts["cycles_non_trivial_nodes"] = counts.get("cycle_nodes")

    # Evaluación de readiness (pre-axialidad) — SOLO consistencia estructural.
    # Nota: ontology_freeze es control operativo de mutación (backfill/repair), no criterio de readiness.
    if not supported:
        blocking_reasons.append("supported=false")
    if isinstance(counts.get("missing_code_id"), int) and counts["missing_code_id"] > 0:
        blocking_reasons.append("missing_code_id")
    if isinstance(counts.get("missing_canonical_code_id_for_noncanonical"), int) and counts["missing_canonical_code_id_for_noncanonical"] > 0:
        blocking_reasons.append("missing_canonical_code_id")
    if isinstance(counts.get("divergences_text_vs_id"), int) and counts["divergences_text_vs_id"] > 0:
        blocking_reasons.append("divergences_text_vs_id")
    if isinstance(counts.get("cycle_nodes"), int) and counts["cycle_nodes"] > 0:
        blocking_reasons.append("cycles_non_trivial")

    axial_ready = supported and (not blocking_reasons)

    return {
        "project": project,
        "supported": supported,
        "has_table": True,
        "ontology_freeze": ontology_freeze,
        "columns": {
            "code_id": has_code_id,
            "canonical_code_id": has_canonical_code_id,
            "canonical_codigo": has_canonical_codigo,
        },
        "counts": counts,
        "axial_ready": axial_ready,
        "blocking_reasons": blocking_reasons,
        "notes": [
            "Este endpoint es infra-operativo (Fase 1.5), no analítico.",
            "Si supported=false, aplica la migración de columnas (code_id/canonical_code_id) y reintenta.",
            "axial_ready valida consistencia estructural (identidad/canonicidad/ausencia de ciclos no triviales).",
            "self-canonical (canonical_code_id = code_id) es estado esperado y NO bloquea axial_ready.",
            "ontology_freeze es un control operativo de mutación; no afecta axial_ready.",
        ],
    }


@router.get("/admin/ontology/freeze")
async def api_admin_ontology_freeze_status(
    project: str,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Estado del freeze ontológico (pre-axialidad). Read-only."""

    state = _get_ontology_freeze(clients.postgres, project)
    return {
        **state,
        "notes": [
            "Freeze ontológico: bloquea operaciones con efectos (backfill/repair/merges equivalentes).",
            "Herramienta infra-operativa. No usar como análisis.",
        ],
    }


@router.post("/admin/ontology/freeze/freeze")
async def api_admin_ontology_freeze_set(
    payload: OntologyFreezeRequest,
    project: str,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Activa freeze ontológico (seguro por defecto)."""

    _require_ontology_freeze_table(clients.postgres)
    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            INSERT INTO project_ontology_freeze (project_id, is_frozen, frozen_at, frozen_by, note)
            VALUES (%s, TRUE, NOW(), %s, %s)
            ON CONFLICT (project_id) DO UPDATE SET
              is_frozen = TRUE,
              frozen_at = NOW(),
              frozen_by = EXCLUDED.frozen_by,
              note = EXCLUDED.note
            """,
            (project, getattr(user, "user_id", None), payload.note),
        )
    clients.postgres.commit()

    logger.info(
        "admin.ontology.freeze.set",
        extra={"project": project, "admin_id": getattr(user, "user_id", None), "note": payload.note},
    )

    return {
        **_get_ontology_freeze(clients.postgres, project),
        "status": "frozen",
    }


@router.post("/admin/ontology/freeze/break")
async def api_admin_ontology_freeze_break(
    payload: OntologyFreezeBreakRequest,
    project: str,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Rompe freeze ontológico de forma explícita (doble confirmación)."""

    if not payload.confirm or payload.phrase.strip() != "BREAK_FREEZE":
        raise HTTPException(
            status_code=409,
            detail="Para romper el freeze, se requiere confirm=true y phrase='BREAK_FREEZE'.",
        )

    _require_ontology_freeze_table(clients.postgres)
    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            INSERT INTO project_ontology_freeze (project_id, is_frozen, broken_at, broken_by, note)
            VALUES (%s, FALSE, NOW(), %s, %s)
            ON CONFLICT (project_id) DO UPDATE SET
              is_frozen = FALSE,
              broken_at = NOW(),
              broken_by = EXCLUDED.broken_by,
              note = EXCLUDED.note
            """,
            (project, getattr(user, "user_id", None), payload.note),
        )
    clients.postgres.commit()

    logger.info(
        "admin.ontology.freeze.break",
        extra={"project": project, "admin_id": getattr(user, "user_id", None), "note": payload.note},
    )

    return {
        **_get_ontology_freeze(clients.postgres, project),
        "status": "unfrozen",
    }


@router.get("/admin/code-id/inconsistencies")
async def api_admin_code_id_inconsistencies(
    project: str,
    limit: int = 50,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Lista inconsistencias (muestras) para operación/repair. Read-only."""

    try:
        from app.postgres_block import ensure_codes_catalog_table

        ensure_codes_catalog_table(clients.postgres)
    except Exception:
        pass

    if not _pg_has_table(clients.postgres, "catalogo_codigos"):
        return {
            "project": project,
            "supported": False,
            "reason": "catalogo_codigos no existe",
            "samples": {},
        }

    has_code_id = _pg_has_column(clients.postgres, "catalogo_codigos", "code_id")
    has_canonical_code_id = _pg_has_column(clients.postgres, "catalogo_codigos", "canonical_code_id")
    has_canonical_codigo = _pg_has_column(clients.postgres, "catalogo_codigos", "canonical_codigo")
    supported = bool(has_code_id and has_canonical_code_id and has_canonical_codigo)

    samples: Dict[str, Any] = {
        "missing_code_id": [],
        "missing_canonical_code_id": [],
        "divergences": [],
        "self_pointing": [],
        "cycles": [],
    }

    with clients.postgres.cursor() as cur:
        if has_code_id:
            cur.execute(
                """
                SELECT codigo, status, canonical_codigo
                  FROM catalogo_codigos
                 WHERE project_id = %s AND code_id IS NULL
                 ORDER BY updated_at DESC NULLS LAST, codigo ASC
                 LIMIT %s
                """,
                (project, int(limit)),
            )
            samples["missing_code_id"] = [
                {"codigo": r[0], "status": r[1], "canonical_codigo": r[2]} for r in (cur.fetchall() or [])
            ]

        if has_canonical_code_id:
            cur.execute(
                """
                SELECT codigo, status, canonical_codigo
                  FROM catalogo_codigos
                 WHERE project_id = %s
                   AND status IN ('merged','superseded')
                   AND canonical_code_id IS NULL
                 ORDER BY updated_at DESC NULLS LAST, codigo ASC
                 LIMIT %s
                """,
                (project, int(limit)),
            )
            samples["missing_canonical_code_id"] = [
                {"codigo": r[0], "status": r[1], "canonical_codigo": r[2]} for r in (cur.fetchall() or [])
            ]

        if supported:
            cur.execute(
                """
                SELECT src.codigo AS source_codigo,
                       src.status,
                       src.canonical_codigo AS canonical_text,
                       tgt.codigo AS canonical_by_id
                  FROM catalogo_codigos src
                  JOIN catalogo_codigos tgt
                    ON tgt.project_id = src.project_id
                   AND tgt.code_id = src.canonical_code_id
                 WHERE src.project_id = %s
                   AND src.canonical_code_id IS NOT NULL
                   AND src.canonical_codigo IS NOT NULL
                   AND lower(src.canonical_codigo) <> lower(tgt.codigo)
                 ORDER BY src.updated_at DESC NULLS LAST, src.codigo ASC
                 LIMIT %s
                """,
                (project, int(limit)),
            )
            samples["divergences"] = [
                {
                    "codigo": r[0],
                    "status": r[1],
                    "canonical_codigo": r[2],
                    "canonical_by_id": r[3],
                }
                for r in (cur.fetchall() or [])
            ]

            # Auto-referencias por ID (muestra, para operación)
            cur.execute(
                """
                SELECT src.codigo,
                       src.status,
                       src.code_id,
                       src.canonical_code_id,
                       src.canonical_codigo,
                       tgt.codigo AS canonical_by_text
                  FROM catalogo_codigos src
                  LEFT JOIN catalogo_codigos tgt
                    ON tgt.project_id = src.project_id
                   AND src.canonical_codigo IS NOT NULL
                   AND lower(tgt.codigo) = lower(src.canonical_codigo)
                 WHERE src.project_id = %s
                   AND src.code_id IS NOT NULL
                   AND src.canonical_code_id IS NOT NULL
                   AND src.canonical_code_id = src.code_id
                 ORDER BY src.updated_at DESC NULLS LAST, src.codigo ASC
                 LIMIT %s
                """,
                (project, int(limit)),
            )
            samples["self_pointing"] = [
                {
                    "codigo": r[0],
                    "status": r[1],
                    "code_id": r[2],
                    "canonical_code_id": r[3],
                    "canonical_codigo": r[4],
                    "canonical_by_text": r[5],
                }
                for r in (cur.fetchall() or [])
            ]

                        # Ciclos NO triviales en canonical_code_id (muestra best-effort, profundidad limitada)
            cur.execute(
                """
                WITH RECURSIVE walk AS (
                  SELECT project_id,
                         code_id,
                         canonical_code_id,
                         ARRAY[code_id] AS path,
                         FALSE AS cycle
                    FROM catalogo_codigos
                   WHERE project_id = %s
                     AND code_id IS NOT NULL
                     AND canonical_code_id IS NOT NULL
                  UNION ALL
                  SELECT w.project_id,
                         c.code_id,
                         c.canonical_code_id,
                         w.path || c.code_id,
                         (c.code_id = ANY(w.path)) AS cycle
                    FROM walk w
                    JOIN catalogo_codigos c
                      ON c.project_id = w.project_id
                     AND c.code_id = w.canonical_code_id
                   WHERE w.cycle = FALSE
                     AND array_length(w.path, 1) < 25
                     AND c.code_id IS NOT NULL
                ),
                cycle_nodes AS (
                                    SELECT DISTINCT n AS code_id
                                        FROM (
                                            SELECT unnest(path) AS n
                                                FROM walk
                                             WHERE cycle = TRUE
                                                 AND array_length(path, 1) > 2
                                        ) s
                                     LIMIT %s
                )
                SELECT src.codigo,
                       src.status,
                       src.code_id,
                       src.canonical_code_id,
                       src.canonical_codigo,
                       tgt.codigo AS canonical_by_id
                  FROM cycle_nodes n
                  JOIN catalogo_codigos src
                    ON src.project_id = %s
                   AND src.code_id = n.code_id
                  LEFT JOIN catalogo_codigos tgt
                    ON tgt.project_id = src.project_id
                   AND tgt.code_id = src.canonical_code_id
                 ORDER BY src.updated_at DESC NULLS LAST, src.codigo ASC
                """,
                (project, int(limit), project),
            )
            samples["cycles"] = [
                {
                    "codigo": r[0],
                    "status": r[1],
                    "code_id": r[2],
                    "canonical_code_id": r[3],
                    "canonical_codigo": r[4],
                    "canonical_by_id": r[5],
                }
                for r in (cur.fetchall() or [])
            ]

    return {
        "project": project,
        "supported": supported,
        "columns": {
            "code_id": has_code_id,
            "canonical_code_id": has_canonical_code_id,
            "canonical_codigo": has_canonical_codigo,
        },
        "samples": samples,
        "notes": [
            "Read-only: muestras para operar backfill/repair.",
            "Incluye muestras de self_pointing (self-canonical, estado esperado) y cycles (solo ciclos no triviales; best-effort) para facilitar incident response.",
            "No usar estos datos como base analítica/teórica (Fase 1.5).",
        ],
    }


@router.post("/admin/code-id/backfill")
async def api_admin_code_id_backfill(
    payload: CodeIdBackfillRequest,
    project: str,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Backfill controlado (con dry-run por defecto). Infra-operativo."""

    if not payload.dry_run and not payload.confirm:
        return {
            "status": "not_confirmed",
            "message": "Operación requiere confirm=true cuando dry_run=false.",
            "project": project,
            "mode": payload.mode,
        }

    _require_code_id_columns(clients.postgres)

    if not payload.dry_run:
        _require_not_frozen(clients.postgres, project, operation=f"code-id.backfill:{payload.mode}")

    lock_key = _advisory_lock_key(project, f"backfill:{payload.mode}")
    logger.info(
        "admin.code_id.lock.try",
        project_id=project,
        op=f"backfill:{payload.mode}",
        lock_key={"k1": lock_key[0], "k2": lock_key[1]},
        dry_run=payload.dry_run,
        confirm=payload.confirm,
        admin_id=getattr(user, "user_id", None),
    )
    try:
        got_lock = _try_advisory_lock(clients.postgres, lock_key)
    except Exception:
        logger.exception(
            "admin.code_id.lock.error",
            project_id=project,
            op=f"backfill:{payload.mode}",
            lock_key={"k1": lock_key[0], "k2": lock_key[1]},
            admin_id=getattr(user, "user_id", None),
        )
        raise

    if not got_lock:
        logger.warning(
            "admin.code_id.lock.busy",
            project_id=project,
            op=f"backfill:{payload.mode}",
            lock_key={"k1": lock_key[0], "k2": lock_key[1]},
        )
        raise HTTPException(status_code=409, detail="Otra operación de mantenimiento code_id está en progreso.")

    updated = {"code_id": 0, "canonical_code_id": 0}
    try:
        if payload.dry_run:
            preview: Dict[str, Any] = {}
            with clients.postgres.cursor() as cur:
                if payload.mode in ("code_id", "all"):
                    cur.execute(
                        "SELECT COUNT(*)::INT FROM catalogo_codigos WHERE project_id = %s AND code_id IS NULL",
                        (project,),
                    )
                    preview["missing_code_id"] = int((cur.fetchone() or [0])[0] or 0)

                if payload.mode in ("canonical_code_id", "all"):
                    cur.execute(
                        """
                        SELECT COUNT(*)::INT
                          FROM catalogo_codigos src
                         WHERE src.project_id = %s
                           AND src.canonical_codigo IS NOT NULL
                           AND src.canonical_code_id IS NULL
                           AND EXISTS (
                             SELECT 1
                               FROM catalogo_codigos tgt
                              WHERE tgt.project_id = src.project_id
                                AND lower(tgt.codigo) = lower(src.canonical_codigo)
                                AND tgt.code_id IS NOT NULL
                           )
                        """,
                        (project,),
                    )
                    preview["canonical_code_id_candidates"] = int((cur.fetchone() or [0])[0] or 0)
            return {
                "status": "dry_run",
                "project": project,
                "mode": payload.mode,
                "batch_size": payload.batch_size,
                "preview": preview,
                "notes": ["Dry-run: no se realizaron cambios."],
            }

        # 1) Backfill code_id
        if payload.mode in ("code_id", "all"):
            udt = _pg_get_column_udt(clients.postgres, "catalogo_codigos", "code_id")
            with clients.postgres.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*)::INT FROM catalogo_codigos WHERE project_id = %s AND code_id IS NULL",
                    (project,),
                )
                missing = int((cur.fetchone() or [0])[0] or 0)
            if payload.dry_run:
                updated["code_id"] = 0
            else:
                if missing <= 0:
                    updated["code_id"] = 0
                elif udt in ("uuid", "text", "varchar"):
                    # Batch update with python-generated UUIDs (works for uuid and text).
                    batch_size = int(payload.batch_size)
                    with clients.postgres.cursor() as cur:
                        cur.execute(
                            """
                            SELECT project_id, codigo
                              FROM catalogo_codigos
                             WHERE project_id = %s AND code_id IS NULL
                             ORDER BY codigo
                             LIMIT %s
                             FOR UPDATE SKIP LOCKED
                            """,
                            (project, batch_size),
                        )
                        rows = cur.fetchall() or []
                        assignments = []
                        for r in rows:
                            proj, codigo = r[0], r[1]
                            assignments.append((str(uuid.uuid4()), proj, codigo))
                        if assignments:
                            cur.executemany(
                                """
                                UPDATE catalogo_codigos
                                   SET code_id = %s
                                 WHERE project_id = %s AND codigo = %s AND code_id IS NULL
                                """,
                                assignments,
                            )
                            updated["code_id"] = len(assignments)
                    clients.postgres.commit()
                elif udt in ("int8", "bigint", "int4", "integer"):
                    # Batch update using the column's serial sequence.
                    with clients.postgres.cursor() as cur:
                        cur.execute("SELECT pg_get_serial_sequence('catalogo_codigos','code_id')")
                        seq = (cur.fetchone() or [None])[0]
                        if not seq:
                            raise HTTPException(
                                status_code=409,
                                detail="code_id es entero pero no tiene secuencia serial asociada. Ajusta la migración (BIGSERIAL) o backfill manual.",
                            )
                        cur.execute(
                            """
                            WITH to_upd AS (
                              SELECT ctid
                                FROM catalogo_codigos
                               WHERE project_id = %s AND code_id IS NULL
                               LIMIT %s
                            )
                            UPDATE catalogo_codigos c
                               SET code_id = nextval(%s::regclass)
                              FROM to_upd
                             WHERE c.ctid = to_upd.ctid
                            RETURNING 1
                            """,
                            (project, int(payload.batch_size), str(seq)),
                        )
                        updated["code_id"] = len(cur.fetchall() or [])
                    clients.postgres.commit()
                else:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Tipo de columna code_id no soportado para backfill automático: {udt}",
                    )

        # 2) Backfill canonical_code_id (best-effort desde canonical_codigo)
        if payload.mode in ("canonical_code_id", "all"):
            with clients.postgres.cursor() as cur:
                cur.execute(
                    """
                    WITH to_upd AS (
                      SELECT src.ctid
                        FROM catalogo_codigos src
                       WHERE src.project_id = %s
                         AND src.canonical_codigo IS NOT NULL
                         AND src.canonical_code_id IS NULL
                       ORDER BY src.updated_at DESC NULLS LAST, src.codigo ASC
                       LIMIT %s
                    ),
                    updated AS (
                      UPDATE catalogo_codigos src
                         SET canonical_code_id = tgt.code_id
                                                FROM to_upd,
                                                         catalogo_codigos tgt
                       WHERE src.ctid = to_upd.ctid
                                                 AND tgt.project_id = src.project_id
                                                 AND lower(tgt.codigo) = lower(src.canonical_codigo)
                         AND tgt.code_id IS NOT NULL
                       RETURNING 1
                    )
                    SELECT COUNT(*)::INT FROM updated
                    """,
                    (project, int(payload.batch_size)),
                )
                updated["canonical_code_id"] = int((cur.fetchone() or [0])[0] or 0)
            clients.postgres.commit()

        logger.info(
            "admin.code_id.backfill",
            project_id=project,
            mode=payload.mode,
            dry_run=payload.dry_run,
            confirm=payload.confirm,
            batch_size=payload.batch_size,
            updated=updated,
            admin_id=getattr(user, "user_id", None),
        )

        return {
            "status": "dry_run" if payload.dry_run else "completed",
            "project": project,
            "mode": payload.mode,
            "batch_size": payload.batch_size,
            "updated": updated,
            "notes": [
                "Infra-operativo (Fase 1.5). No usar para inferencia teórica.",
                "Repetir en batches hasta que missing_* sea 0.",
            ],
        }
    except Exception:
        logger.exception(
            "admin.code_id.backfill.error",
            project_id=project,
            mode=payload.mode,
            dry_run=payload.dry_run,
            confirm=payload.confirm,
            batch_size=payload.batch_size,
            admin_id=getattr(user, "user_id", None),
        )
        raise
    finally:
        try:
            # Si la transacción quedó abortada por un error, cualquier SQL (incl. unlock)
            # fallará hasta hacer ROLLBACK.
            try:
                clients.postgres.rollback()
            except Exception:
                pass
            _advisory_unlock(clients.postgres, lock_key)
            clients.postgres.commit()
            logger.info(
                "admin.code_id.lock.released",
                project_id=project,
                op=f"backfill:{payload.mode}",
                lock_key={"k1": lock_key[0], "k2": lock_key[1]},
            )
        except Exception:
            logger.exception(
                "admin.code_id.lock.release_error",
                project_id=project,
                op=f"backfill:{payload.mode}",
                lock_key={"k1": lock_key[0], "k2": lock_key[1]},
            )


@router.post("/admin/code-id/repair")
async def api_admin_code_id_repair(
    payload: CodeIdRepairRequest,
    project: str,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Repair controlado. Por defecto dry-run. Regla: ID manda."""

    if not payload.dry_run and not payload.confirm:
        return {
            "status": "not_confirmed",
            "message": "Operación requiere confirm=true cuando dry_run=false.",
            "project": project,
            "action": payload.action,
        }

    _require_code_id_columns(clients.postgres)

    if not payload.dry_run:
        _require_not_frozen(clients.postgres, project, operation=f"code-id.repair:{payload.action}")

    lock_key = _advisory_lock_key(project, f"repair:{payload.action}")
    logger.info(
        "admin.code_id.lock.try",
        project_id=project,
        op=f"repair:{payload.action}",
        lock_key={"k1": lock_key[0], "k2": lock_key[1]},
        dry_run=payload.dry_run,
        confirm=payload.confirm,
        admin_id=getattr(user, "user_id", None),
    )
    try:
        got_lock = _try_advisory_lock(clients.postgres, lock_key)
    except Exception:
        logger.exception(
            "admin.code_id.lock.error",
            project_id=project,
            op=f"repair:{payload.action}",
            lock_key={"k1": lock_key[0], "k2": lock_key[1]},
            admin_id=getattr(user, "user_id", None),
        )
        raise

    if not got_lock:
        logger.warning(
            "admin.code_id.lock.busy",
            project_id=project,
            op=f"repair:{payload.action}",
            lock_key={"k1": lock_key[0], "k2": lock_key[1]},
        )
        raise HTTPException(status_code=409, detail="Otra operación de mantenimiento code_id está en progreso.")

    try:
        if payload.action == "derive_text_from_id":
            # canonical_code_id manda: re-derivar canonical_codigo desde el target.
            with clients.postgres.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)::INT
                      FROM catalogo_codigos src
                      JOIN catalogo_codigos tgt
                        ON tgt.project_id = src.project_id
                       AND tgt.code_id = src.canonical_code_id
                     WHERE src.project_id = %s
                       AND src.canonical_code_id IS NOT NULL
                       AND (src.canonical_codigo IS NULL OR lower(src.canonical_codigo) <> lower(tgt.codigo))
                    """,
                    (project,),
                )
                preview = int((cur.fetchone() or [0])[0] or 0)

                if payload.dry_run:
                    return {
                        "status": "dry_run",
                        "project": project,
                        "action": payload.action,
                        "preview": {"rows_to_update": preview},
                        "notes": ["Dry-run: no se realizaron cambios.", "Regla: ID manda."],
                    }

                cur.execute(
                    """
                    WITH to_upd AS (
                      SELECT src.ctid
                        FROM catalogo_codigos src
                       WHERE src.project_id = %s
                         AND src.canonical_code_id IS NOT NULL
                       ORDER BY src.updated_at DESC NULLS LAST, src.codigo ASC
                       LIMIT %s
                    ),
                    updated AS (
                      UPDATE catalogo_codigos src
                         SET canonical_codigo = tgt.codigo
                                                FROM to_upd,
                                                         catalogo_codigos tgt
                       WHERE src.ctid = to_upd.ctid
                                                 AND tgt.project_id = src.project_id
                                                 AND tgt.code_id = src.canonical_code_id
                         AND (src.canonical_codigo IS NULL OR lower(src.canonical_codigo) <> lower(tgt.codigo))
                       RETURNING 1
                    )
                    SELECT COUNT(*)::INT FROM updated
                    """,
                    (project, int(payload.batch_size)),
                )
                updated = int((cur.fetchone() or [0])[0] or 0)
            clients.postgres.commit()
            logger.info(
                "admin.code_id.repair",
                project_id=project,
                action=payload.action,
                dry_run=payload.dry_run,
                confirm=payload.confirm,
                batch_size=payload.batch_size,
                updated={"rows": updated},
                admin_id=getattr(user, "user_id", None),
            )
            return {
                "status": "completed",
                "project": project,
                "action": payload.action,
                "batch_size": payload.batch_size,
                "updated": {"rows": updated},
                "notes": ["Regla: ID manda. canonical_codigo se considera compatibilidad."],
            }

        if payload.action == "derive_id_from_text":
            # canonical_codigo legacy -> canonical_code_id (best-effort)
            with clients.postgres.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)::INT
                      FROM catalogo_codigos src
                     WHERE src.project_id = %s
                       AND src.canonical_codigo IS NOT NULL
                       AND src.canonical_code_id IS NULL
                       AND EXISTS (
                         SELECT 1
                           FROM catalogo_codigos tgt
                          WHERE tgt.project_id = src.project_id
                            AND lower(tgt.codigo) = lower(src.canonical_codigo)
                            AND tgt.code_id IS NOT NULL
                       )
                    """,
                    (project,),
                )
                preview = int((cur.fetchone() or [0])[0] or 0)

                if payload.dry_run:
                    return {
                        "status": "dry_run",
                        "project": project,
                        "action": payload.action,
                        "preview": {"rows_to_update": preview},
                        "notes": ["Dry-run: no se realizaron cambios.", "Operación best-effort."],
                    }

                cur.execute(
                    """
                    WITH to_upd AS (
                      SELECT src.ctid
                        FROM catalogo_codigos src
                       WHERE src.project_id = %s
                         AND src.canonical_codigo IS NOT NULL
                         AND src.canonical_code_id IS NULL
                       ORDER BY src.updated_at DESC NULLS LAST, src.codigo ASC
                       LIMIT %s
                    ),
                    updated AS (
                      UPDATE catalogo_codigos src
                         SET canonical_code_id = tgt.code_id
                                                FROM to_upd,
                                                         catalogo_codigos tgt
                       WHERE src.ctid = to_upd.ctid
                                                 AND tgt.project_id = src.project_id
                                                 AND lower(tgt.codigo) = lower(src.canonical_codigo)
                         AND tgt.code_id IS NOT NULL
                       RETURNING 1
                    )
                    SELECT COUNT(*)::INT FROM updated
                    """,
                    (project, int(payload.batch_size)),
                )
                updated = int((cur.fetchone() or [0])[0] or 0)
            clients.postgres.commit()
            logger.info(
                "admin.code_id.repair",
                project_id=project,
                action=payload.action,
                dry_run=payload.dry_run,
                confirm=payload.confirm,
                batch_size=payload.batch_size,
                updated={"rows": updated},
                admin_id=getattr(user, "user_id", None),
            )
            return {
                "status": "completed",
                "project": project,
                "action": payload.action,
                "batch_size": payload.batch_size,
                "updated": {"rows": updated},
                "notes": ["Best-effort: deriva canonical_code_id desde canonical_codigo."],
            }

        if payload.action == "fix_self_pointing_mapped":
            # Fix determinista: solo cuando canonical_codigo permite mapear a OTRO code_id válido.
            with clients.postgres.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)::INT
                      FROM catalogo_codigos src
                      JOIN catalogo_codigos tgt
                        ON tgt.project_id = src.project_id
                       AND src.canonical_codigo IS NOT NULL
                       AND lower(tgt.codigo) = lower(src.canonical_codigo)
                     WHERE src.project_id = %s
                       AND src.code_id IS NOT NULL
                       AND src.canonical_code_id = src.code_id
                       AND tgt.code_id IS NOT NULL
                       AND tgt.code_id <> src.code_id
                    """,
                    (project,),
                )
                preview = int((cur.fetchone() or [0])[0] or 0)

                if payload.dry_run:
                    cur.execute(
                        """
                        SELECT src.codigo,
                               src.status,
                               src.code_id,
                               src.canonical_code_id,
                               src.canonical_codigo,
                               tgt.codigo AS canonical_by_text,
                               tgt.code_id AS mapped_canonical_code_id
                          FROM catalogo_codigos src
                          JOIN catalogo_codigos tgt
                            ON tgt.project_id = src.project_id
                           AND src.canonical_codigo IS NOT NULL
                           AND lower(tgt.codigo) = lower(src.canonical_codigo)
                         WHERE src.project_id = %s
                           AND src.code_id IS NOT NULL
                           AND src.canonical_code_id = src.code_id
                           AND tgt.code_id IS NOT NULL
                           AND tgt.code_id <> src.code_id
                         ORDER BY src.updated_at DESC NULLS LAST, src.codigo ASC
                         LIMIT 25
                        """,
                        (project,),
                    )
                    examples = [
                        {
                            "codigo": r[0],
                            "status": r[1],
                            "code_id": r[2],
                            "canonical_code_id": r[3],
                            "canonical_codigo": r[4],
                            "canonical_by_text": r[5],
                            "mapped_canonical_code_id": r[6],
                        }
                        for r in (cur.fetchall() or [])
                    ]
                    return {
                        "status": "dry_run",
                        "project": project,
                        "action": payload.action,
                        "preview": {"rows_to_update": preview, "examples": examples},
                        "notes": [
                            "Dry-run: no se realizaron cambios.",
                            "Regla literal: si canonical_code_id se auto-apunta, se re-mapea SOLO si canonical_codigo coincide con otro codigo con code_id válido.",
                        ],
                    }

                cur.execute(
                    """
                    WITH to_upd AS (
                      SELECT src.ctid
                        FROM catalogo_codigos src
                        JOIN catalogo_codigos tgt
                          ON tgt.project_id = src.project_id
                         AND src.canonical_codigo IS NOT NULL
                         AND lower(tgt.codigo) = lower(src.canonical_codigo)
                       WHERE src.project_id = %s
                         AND src.code_id IS NOT NULL
                         AND src.canonical_code_id = src.code_id
                         AND tgt.code_id IS NOT NULL
                         AND tgt.code_id <> src.code_id
                       ORDER BY src.updated_at DESC NULLS LAST, src.codigo ASC
                       LIMIT %s
                    ),
                    updated AS (
                      UPDATE catalogo_codigos src
                         SET canonical_code_id = tgt.code_id
                                                FROM to_upd,
                                                     catalogo_codigos tgt
                       WHERE src.ctid = to_upd.ctid
                         AND tgt.project_id = src.project_id
                         AND src.canonical_codigo IS NOT NULL
                         AND lower(tgt.codigo) = lower(src.canonical_codigo)
                         AND tgt.code_id IS NOT NULL
                         AND src.code_id IS NOT NULL
                         AND tgt.code_id <> src.code_id
                       RETURNING 1
                    )
                    SELECT COUNT(*)::INT FROM updated
                    """,
                    (project, int(payload.batch_size)),
                )
                updated = int((cur.fetchone() or [0])[0] or 0)
            clients.postgres.commit()
            logger.info(
                "admin.code_id.repair",
                project_id=project,
                action=payload.action,
                dry_run=payload.dry_run,
                confirm=payload.confirm,
                batch_size=payload.batch_size,
                updated={"rows": updated},
                admin_id=getattr(user, "user_id", None),
            )
            return {
                "status": "completed",
                "project": project,
                "action": payload.action,
                "batch_size": payload.batch_size,
                "updated": {"rows": updated},
                "notes": [
                    "Fix determinista: corrige self-pointing SOLO cuando canonical_codigo permite mapear a otro code_id.",
                    "Si no hay mapeo por texto, no muta ese registro (requiere intervención manual).",
                ],
            }

        raise HTTPException(status_code=400, detail="Acción no soportada")
    except Exception:
        logger.exception(
            "admin.code_id.repair.error",
            project_id=project,
            action=payload.action,
            dry_run=payload.dry_run,
            confirm=payload.confirm,
            batch_size=payload.batch_size,
            admin_id=getattr(user, "user_id", None),
        )
        raise
    finally:
        try:
            try:
                clients.postgres.rollback()
            except Exception:
                pass
            _advisory_unlock(clients.postgres, lock_key)
            clients.postgres.commit()
            logger.info(
                "admin.code_id.lock.released",
                project_id=project,
                op=f"repair:{payload.action}",
                lock_key={"k1": lock_key[0], "k2": lock_key[1]},
            )
        except Exception:
            logger.exception(
                "admin.code_id.lock.release_error",
                project_id=project,
                op=f"repair:{payload.action}",
                lock_key={"k1": lock_key[0], "k2": lock_key[1]},
            )


# =============================================================================
# ADMIN OPS PANEL (Ergonomía operativa) — Reads structured logs (Admin only)
# =============================================================================


def _sanitize_path_fragment(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(value).strip())
    cleaned = cleaned.strip("._-") or fallback
    return cleaned[:80]


def _tail_jsonl(path: Path, *, max_lines: int = 2000, max_bytes: int = 1_000_000) -> List[Dict[str, Any]]:
    if max_lines <= 0:
        return []
    if max_bytes < 1024:
        max_bytes = 1024

    try:
        data = path.read_bytes()
        if len(data) > max_bytes:
            data = data[-max_bytes:]
    except Exception:
        return []

    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return []

    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) > max_lines:
        lines = lines[-max_lines:]

    out: List[Dict[str, Any]] = []
    for ln in lines:
        try:
            obj = json.loads(ln)
            if isinstance(obj, dict):
                out.append(obj)
        except Exception:
            continue
    return out


def _extract_ops(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extrae operaciones admin relevantes agrupando por request_id."""

    interesting_admin_events = {
        "admin.code_id.backfill",
        "admin.code_id.backfill.error",
        "admin.code_id.repair",
        "admin.code_id.repair.error",
    }

    runs: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        ev = rec.get("event")
        request_id = rec.get("request_id")
        if not ev or not request_id:
            continue

        # Track request envelope for *maintenance-like* admin routes only
        if ev in {"request.start", "request.end"}:
            path = rec.get("path")
            method = rec.get("method")
            if isinstance(path, str):
                if path.startswith("/api/admin/ops/"):
                    continue
                is_maintenance_route = (
                    path.startswith("/api/admin/code-id/")
                    or path.startswith("/api/admin/ontology/")
                    or path.startswith("/api/admin/sync-neo4j")
                    or path.startswith("/api/maintenance/")
                )
            else:
                is_maintenance_route = False

            if is_maintenance_route:
                run = runs.get(request_id) or {"request_id": request_id}
                run.setdefault("session_id", rec.get("session_id"))
                run.setdefault("project_id", rec.get("project_id"))
                run["path"] = path
                if method:
                    run["http_method"] = method
                if ev == "request.start":
                    run.setdefault("timestamp", rec.get("timestamp"))
                else:
                    run["status_code"] = rec.get("status_code")
                    run["duration_ms"] = rec.get("duration_ms")
                runs[request_id] = run
            continue

        if ev not in interesting_admin_events:
            continue

        run = runs.get(request_id) or {"request_id": request_id}
        run.setdefault("session_id", rec.get("session_id"))
        run.setdefault("project_id", rec.get("project_id"))
        run.setdefault("timestamp", rec.get("timestamp"))
        run["event"] = ev

        for k in (
            "dry_run",
            "confirm",
            "batch_size",
            "mode",
            "action",
            "updated",
            "admin_id",
        ):
            if k in rec:
                run[k] = rec.get(k)

        if ev.endswith(".error"):
            run["is_error"] = True

        runs[request_id] = run

    out = list(runs.values())
    out.sort(key=lambda r: str(r.get("timestamp") or ""), reverse=True)
    return out


def _parse_iso_ts(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        v = str(value).strip()
        if not v:
            return None
        # Accept Z suffix
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        return datetime.fromisoformat(v)
    except Exception:
        return None


def _run_is_mutation(run: Dict[str, Any]) -> bool:
    updated = run.get("updated")
    if updated is None:
        return False

    # Common shapes:
    # - {"rows": 0}
    # - {"code_id": 10, "canonical_code_id": 5}
    if isinstance(updated, dict):
        for v in updated.values():
            try:
                if int(v) > 0:
                    return True
            except Exception:
                continue
        return False
    try:
        return int(updated) > 0
    except Exception:
        return False


@router.get("/admin/ops/recent")
async def api_admin_ops_recent(
    project: str,
    limit: int = 20,
    kind: OpsKind = "all",  # closed enum
    op: OpsOp = "all",  # closed enum
    intent: OpsIntent = "all",  # closed enum
    since: str | None = None,  # ISO
    until: str | None = None,  # ISO
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Lista ejecuciones admin recientes basadas en logs JSONL (ergonomía operativa)."""

    safe_project = _sanitize_path_fragment(project, "default")
    base = Path("logs") / safe_project
    if not base.exists() or not base.is_dir():
        return {"project": project, "limit": limit, "runs": [], "source": "logs"}

    try:
        session_dirs = [p for p in base.iterdir() if p.is_dir()]
    except Exception:
        session_dirs = []

    session_dirs.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)

    since_dt = _parse_iso_ts(since)
    until_dt = _parse_iso_ts(until)
    kind_norm: str = str(kind)
    op_norm: str = str(op)
    intent_norm: str = str(intent)

    runs: List[Dict[str, Any]] = []
    max_sessions = 60
    for session_dir in session_dirs[:max_sessions]:
        log_path = session_dir / "app.jsonl"
        if not log_path.exists():
            continue
        records = _tail_jsonl(log_path, max_lines=2500, max_bytes=1_500_000)
        extracted = _extract_ops(records)
        for run in extracted:
            run_project = run.get("project_id")
            if run_project and str(run_project) != str(project):
                continue

            # Time filter
            ts_dt = _parse_iso_ts(run.get("timestamp"))
            if since_dt and ts_dt and ts_dt < since_dt:
                continue
            if until_dt and ts_dt and ts_dt > until_dt:
                continue

            # Kind filter
            if kind_norm == "errors" and not run.get("is_error"):
                continue
            if kind_norm == "mutations" and not _run_is_mutation(run):
                continue

            # Intent filter (no inference: purely HTTP method logged)
            if intent_norm == "write_intent_post":
                method = str(run.get("http_method") or "").upper()
                if method != "POST":
                    continue

            # Op filter (inferred from path/event)
            path = str(run.get("path") or "")
            event = str(run.get("event") or "")
            if op_norm != "all":
                is_backfill = "/api/admin/code-id/backfill" in path or "code_id.backfill" in event
                is_repair = "/api/admin/code-id/repair" in path or "code_id.repair" in event
                is_sync = "/api/admin/sync-neo4j" in path
                is_maintenance = "/api/maintenance/" in path
                is_ontology = "/api/admin/ontology/" in path

                if op_norm == "backfill" and not is_backfill:
                    continue
                if op_norm == "repair" and not is_repair:
                    continue
                if op_norm == "sync" and not is_sync:
                    continue
                if op_norm == "maintenance" and not is_maintenance:
                    continue
                if op_norm == "ontology" and not is_ontology:
                    continue

            run.setdefault("session_id", session_dir.name)
            runs.append(run)

    def priority(run: Dict[str, Any]) -> int:
        # Lower is better
        try:
            status_code = int(run.get("status_code")) if run.get("status_code") is not None else None
        except Exception:
            status_code = None

        if run.get("is_error") or (status_code is not None and status_code >= 500):
            return 0

        path = str(run.get("path") or "")
        event = str(run.get("event") or "")

        if (
            "admin.code_id.backfill" in event
            or "admin.code_id.repair" in event
            or path.endswith("/api/admin/code-id/backfill")
            or path.endswith("/api/admin/code-id/repair")
            or "/api/admin/sync-neo4j" in path
            or "/api/maintenance/" in path
        ):
            return 1

        # status/read-only
        return 2

    runs.sort(key=lambda r: (priority(r), str(r.get("timestamp") or "")), reverse=False)
    runs = runs[: max(0, int(limit))]

    return {
        "project": project,
        "limit": int(limit),
        "filters": {
            "kind": kind_norm,
            "op": op_norm,
            "intent": intent_norm,
            "since": since,
            "until": until,
        },
        "runs": runs,
        "source": "logs",
    }


@router.get("/admin/ops/log")
async def api_admin_ops_log(
    project: str,
    session: str,
    request_id: str | None = None,
    tail: int = 400,
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Devuelve un excerpt del log JSONL de una sesión (opcionalmente filtrado por request_id)."""

    safe_project = _sanitize_path_fragment(project, "default")
    safe_session = _sanitize_path_fragment(session, "session")
    log_path = Path("logs") / safe_project / safe_session / "app.jsonl"

    if not log_path.exists():
        raise HTTPException(status_code=404, detail="No se encontró el log de la sesión.")

    tail_n = max(50, min(int(tail), 5000))
    records = _tail_jsonl(log_path, max_lines=tail_n, max_bytes=2_000_000)

    filtered: List[Dict[str, Any]] = []
    for rec in records:
        if request_id and rec.get("request_id") != request_id:
            continue
        ev = rec.get("event")
        if not ev:
            continue
        if ev.startswith("admin.") or ev in {"request.start", "request.end"}:
            filtered.append(rec)

    if len(filtered) > tail_n:
        filtered = filtered[-tail_n:]

    return {
        "project": project,
        "session": session,
        "request_id": request_id,
        "records": filtered,
        "notes": [
            "Fuente: logs/<project>/<session>/app.jsonl",
            "Se filtran eventos a admin.* y request.start/end para bajar ruido.",
        ],
    }


@router.patch("/admin/users/{user_id}")
async def update_user(
    user_id: str,
    update: UserUpdate,
    clients: ServiceClients = Depends(get_service_clients),
    admin: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """
    Actualiza rol o estado de un usuario.
    Solo accesible para usuarios con rol 'admin'.
    """
    # Verify user exists and belongs to same org
    with clients.postgres.cursor() as cur:
        cur.execute(
            "SELECT id, organization_id FROM app_users WHERE id = %s",
            (user_id,)
        )
        target_user = cur.fetchone()
        
        if not target_user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        if target_user[1] != admin.organization_id:
            raise HTTPException(status_code=403, detail="No puede modificar usuarios de otra organización")
        
        # Prevent self-demotion from admin
        if user_id == admin.user_id and update.role and update.role != "admin":
            raise HTTPException(status_code=400, detail="No puede quitarse el rol admin a sí mismo")
        
        # Build update query
        updates = []
        params = []
        
        if update.role is not None:
            if update.role not in ["admin", "analyst", "viewer"]:
                raise HTTPException(status_code=400, detail="Rol inválido. Use: admin, analyst, viewer")
            updates.append("role = %s")
            params.append(update.role)
        
        if update.is_active is not None:
            updates.append("is_active = %s")
            params.append(update.is_active)
        
        if not updates:
            return {"status": "no_changes", "user_id": user_id}
        
        params.append(user_id)
        cur.execute(
            f"UPDATE app_users SET {', '.join(updates)} WHERE id = %s",
            tuple(params)
        )
        clients.postgres.commit()
    
    return {"status": "updated", "user_id": user_id, "changes": update.model_dump(exclude_none=True)}


@router.delete("/admin/users/{user_id}")
async def delete_user(
    user_id: str,
    clients: ServiceClients = Depends(get_service_clients),
    admin: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """
    Elimina un usuario y sus sesiones.
    Solo accesible para usuarios con rol 'admin'.
    """
    # Prevent self-deletion
    if user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="No puede eliminarse a sí mismo")
    
    with clients.postgres.cursor() as cur:
        # Verify user exists and belongs to same org
        cur.execute(
            "SELECT id, email, organization_id FROM app_users WHERE id = %s",
            (user_id,)
        )
        target_user = cur.fetchone()
        
        if not target_user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        if target_user[2] != admin.organization_id:
            raise HTTPException(status_code=403, detail="No puede eliminar usuarios de otra organización")
        
        email = target_user[1]
        
        # Delete sessions first (foreign key)
        cur.execute("DELETE FROM app_sessions WHERE user_id = %s", (user_id,))
        sessions_deleted = cur.rowcount
        
        # Delete user
        cur.execute("DELETE FROM app_users WHERE id = %s", (user_id,))
        
        clients.postgres.commit()
    
    return {
        "status": "deleted",
        "user_id": user_id,
        "email": email,
        "sessions_deleted": sessions_deleted
    }


@router.get("/admin/stats")
async def get_org_stats(
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """
    Estadísticas de la organización.
    Solo accesible para usuarios con rol 'admin'.
    """
    org_id = user.organization_id
    
    with clients.postgres.cursor() as cur:
        # Users count by role
        cur.execute("""
            SELECT role, COUNT(*) as count 
            FROM app_users 
            WHERE organization_id = %s 
            GROUP BY role
        """, (org_id,))
        users_by_role = {row[0]: row[1] for row in cur.fetchall()}
        
        # Total projects (if projects table exists)
        try:
            cur.execute("""
                SELECT COUNT(*) FROM entrevista_fragmentos 
                WHERE project_id IN (
                    SELECT DISTINCT project_id FROM entrevista_fragmentos
                )
            """)
            total_fragments = cur.fetchone()[0]
        except Exception:
            total_fragments = 0
        
        # Active sessions
        cur.execute("""
            SELECT COUNT(*) FROM app_sessions s
            JOIN app_users u ON s.user_id = u.id
            WHERE u.organization_id = %s AND s.is_revoked = false
        """, (org_id,))
        active_sessions = cur.fetchone()[0]
    
    return {
        "organization_id": org_id,
        "users_by_role": users_by_role,
        "total_users": sum(users_by_role.values()),
        "total_fragments": total_fragments,
        "active_sessions": active_sessions,
        "timestamp": datetime.now().isoformat()
    }


# =============================================================================
# INSIGHTS ENDPOINT
# =============================================================================

@router.post("/insights/generate")
async def api_generate_insights(
    project: str = Body(..., embed=True),
    source: str = Body(default="coding", embed=True),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Genera insights manualmente desde una fuente."""
    from app.insights import extract_insights_from_coding
    
    if source == "coding":
        insight_ids = extract_insights_from_coding(
            clients.postgres,
            project=project,
        )
        
        return {
            "source": "coding",
            "insights_created": len(insight_ids),
            "insight_ids": insight_ids,
        }
    
    return {"source": source, "insights_created": 0, "message": "Fuente no soportada"}


# =============================================================================
# NEO4J SYNC ENDPOINTS
# =============================================================================

@router.get("/admin/sync-neo4j/status")
async def api_get_sync_status(
    project: str,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Obtiene estado de sincronización Neo4j para un proyecto.
    
    Returns:
        pending: Fragmentos pendientes de sincronizar
        synced: Fragmentos ya sincronizados
        total: Total de fragmentos
        neo4j_available: Si Neo4j está conectado
    """
    from app.neo4j_sync import get_sync_status, check_neo4j_connection
    from app.settings import load_settings
    import os
    
    settings = load_settings(os.getenv("APP_ENV_FILE"))
    
    status = get_sync_status(clients.postgres, project)
    status["neo4j_available"] = check_neo4j_connection(clients, settings)
    status["project"] = project
    
    return status


@router.post("/admin/sync-neo4j")
async def api_sync_neo4j(
    project: str,
    batch_size: int = 100,
    after_id: str | None = None,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Sincroniza fragmentos pendientes a Neo4j.
    
    Llamar múltiples veces para sincronizar todos los fragmentos en batches.
    
    Args:
        project: ID del proyecto
        batch_size: Número de fragmentos por batch (10-500)
        
    Returns:
        synced: Fragmentos sincronizados en este batch
        failed: Fragmentos que fallaron
        remaining: Fragmentos pendientes
    """
    from app.neo4j_sync import sync_pending_fragments
    from app.settings import load_settings
    import os
    
    if batch_size < 10:
        batch_size = 10
    elif batch_size > 500:
        batch_size = 500
    
    settings = load_settings(os.getenv("APP_ENV_FILE"))
    
    result = sync_pending_fragments(
        clients,
        settings,
        project=project,
        batch_size=batch_size,
        after_id=after_id,
    )
    
    result["project"] = project
    result["batch_size"] = batch_size
    result["after_id"] = after_id
    
    return result


@router.post("/admin/sync-neo4j/axial")
async def api_sync_neo4j_axial(
    project: str,
    batch_size: int = 500,
    offset: int = 0,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Sincroniza analisis_axial desde PostgreSQL hacia Neo4j.

    Crea nodos Categoria/Codigo y relaciones REL.
    """
    from app.neo4j_sync import sync_axial_relationships
    from app.settings import load_settings
    import os

    if batch_size < 50:
        batch_size = 50
    elif batch_size > 2000:
        batch_size = 2000

    if offset < 0:
        offset = 0

    settings = load_settings(os.getenv("APP_ENV_FILE"))

    result = sync_axial_relationships(
        clients,
        settings,
        project=project,
        batch_size=batch_size,
        offset=offset,
    )
    result["project"] = project
    result["batch_size"] = batch_size
    result["offset"] = offset
    return result


@router.get("/admin/neo4j-audit")
async def api_admin_neo4j_audit(
    project: str,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Auditoría rápida entre PostgreSQL y Neo4j por project_id.
    Compara conteos básicos y detecta nodos sin project_id.
    """
    from app.settings import load_settings
    import os

    settings = load_settings(os.getenv("APP_ENV_FILE"))

    pg_counts = {
        "fragmentos": 0,
        "codigos_abiertos": 0,
        "relaciones_axiales": 0,
        "archivos": 0,
    }

    with clients.postgres.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM entrevista_fragmentos WHERE project_id = %s", (project,))
        pg_counts["fragmentos"] = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(DISTINCT archivo) FROM entrevista_fragmentos WHERE project_id = %s", (project,))
        pg_counts["archivos"] = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM analisis_codigos_abiertos WHERE project_id = %s", (project,))
        pg_counts["codigos_abiertos"] = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM analisis_axial WHERE project_id = %s", (project,))
        pg_counts["relaciones_axiales"] = int(cur.fetchone()[0])

    neo_counts = {
        "fragmentos": 0,
        "entrevistas": 0,
        "codigos": 0,
        "categorias": 0,
        "rel_tiene_fragmento": 0,
        "rel_tiene_codigo": 0,
        "rel_axial": 0,
        "nodes_sin_project_id": 0,
        "rels_sin_project_id": 0,
    }

    with clients.neo4j.session(database=settings.neo4j.database) as session:
        neo_counts["fragmentos"] = int(session.run(
            "MATCH (f:Fragmento {project_id: $project}) RETURN count(f) AS c",
            project=project,
        ).single()["c"])
        neo_counts["entrevistas"] = int(session.run(
            "MATCH (e:Entrevista {project_id: $project}) RETURN count(e) AS c",
            project=project,
        ).single()["c"])
        neo_counts["codigos"] = int(session.run(
            "MATCH (c:Codigo {project_id: $project}) RETURN count(c) AS c",
            project=project,
        ).single()["c"])
        neo_counts["categorias"] = int(session.run(
            "MATCH (c:Categoria {project_id: $project}) RETURN count(c) AS c",
            project=project,
        ).single()["c"])
        neo_counts["rel_tiene_fragmento"] = int(session.run(
            "MATCH (e:Entrevista {project_id: $project})-[r:TIENE_FRAGMENTO]->(f:Fragmento {project_id: $project}) RETURN count(r) AS c",
            project=project,
        ).single()["c"])
        neo_counts["rel_tiene_codigo"] = int(session.run(
            "MATCH (f:Fragmento {project_id: $project})-[r:TIENE_CODIGO]->(c:Codigo {project_id: $project}) RETURN count(r) AS c",
            project=project,
        ).single()["c"])
        neo_counts["rel_axial"] = int(session.run(
            "MATCH (c:Categoria {project_id: $project})-[r:REL]->(k:Codigo {project_id: $project}) RETURN count(r) AS c",
            project=project,
        ).single()["c"])
        neo_counts["nodes_sin_project_id"] = int(session.run(
            "MATCH (n) WHERE n.project_id IS NULL RETURN count(n) AS c"
        ).single()["c"])
        neo_counts["rels_sin_project_id"] = int(session.run(
            "MATCH ()-[r]->() WHERE r.project_id IS NULL RETURN count(r) AS c"
        ).single()["c"])

    return {
        "status": "ok",
        "project": project,
        "postgres": pg_counts,
        "neo4j": neo_counts,
        "notes": [
            "PG usa flags neo4j_synced; Neo4j puede estar vacío si se limpió manualmente.",
            "nodes_sin_project_id/ rels_sin_project_id indican datos legacy sin scope.",
        ],
    }


@router.post("/admin/sync-neo4j/reset")
async def api_reset_neo4j_sync_flags(
    project: str,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Resetea la marca neo4j_synced en PostgreSQL para forzar re-sincronización.
    Útil cuando Neo4j fue limpiado manualmente.
    """
    from app.neo4j_sync import get_sync_status, _pg_has_column

    if not _pg_has_column(clients.postgres, "entrevista_fragmentos", "neo4j_synced"):
        return {
            "status": "not_supported",
            "message": "La columna neo4j_synced no existe. No hay flags para resetear.",
            "project": project,
        }

    with clients.postgres.cursor() as cur:
        cur.execute(
            "UPDATE entrevista_fragmentos SET neo4j_synced = FALSE WHERE project_id = %s",
            (project,),
        )
    clients.postgres.commit()

    status = get_sync_status(clients.postgres, project)
    status["project"] = project
    status["status"] = "reset"
    status["message"] = "Flags neo4j_synced reseteados. Listo para re-sincronizar."
    return status


@router.post("/admin/link-predictions/{prediction_id}/reopen")
async def api_reopen_link_prediction(
    prediction_id: int,
    payload: LinkPredictionReopenRequest,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """
    Reabre una predicción cerrada (rechazada/validada) con motivo obligatorio.

    - Solo admin puede reabrir.
    - No borra historial; deja audit trail y conserva memo/relación previa.
    """
    from app.postgres_block import (
        check_project_permission,
        ensure_link_predictions_table,
        ensure_project_members_table,
    )

    ensure_link_predictions_table(clients.postgres)
    ensure_project_members_table(clients.postgres)

    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            SELECT id, project_id, estado, memo
            FROM link_predictions
            WHERE id = %s
            """,
            (prediction_id,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Predicción no encontrada")

    project_id = row[1]
    current_estado = str(row[2] or "pendiente")

    # Requiere rol admin en el proyecto.
    if not check_project_permission(clients.postgres, project_id, user.user_id, "admin"):
        raise HTTPException(
            status_code=403,
            detail="Acceso denegado: se requiere rol admin en el proyecto.",
        )

    if current_estado not in ("validado", "rechazado"):
        raise HTTPException(
            status_code=409,
            detail="Solo se pueden reabrir predicciones cerradas (validado/rechazado).",
        )

    reason = (payload.reason or "").strip()
    if len(reason) < 5:
        raise HTTPException(status_code=400, detail="Motivo insuficiente (min 5 caracteres).")

    try:
        with clients.postgres.cursor() as cur:
            cur.execute(
                """
                UPDATE link_predictions
                SET estado = 'pendiente',
                    reopened_at = NOW(),
                    reopened_by = %s,
                    reopen_reason = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id, estado, reopened_at
                """,
                (user.user_id, reason, prediction_id),
            )
            updated = cur.fetchone()

            cur.execute(
                """
                INSERT INTO project_audit_log (project_id, user_id, action, entity_type, entity_id, details)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    project_id,
                    user.user_id,
                    "link_prediction.reopen",
                    "link_prediction",
                    str(prediction_id),
                    Json(
                        {
                            "before_estado": current_estado,
                            "after_estado": "pendiente",
                            "reason": reason,
                            "evidence_link": payload.evidence_link,
                        }
                    ),
                ),
            )
        clients.postgres.commit()
    except Exception:
        clients.postgres.rollback()
        raise

    return {
        "success": True,
        "prediction_id": prediction_id,
        "project": project_id,
        "estado": "pendiente",
        "reopened_at": updated[2].isoformat() if updated and updated[2] else None,
    }
