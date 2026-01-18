"""Admin router - User management, project management, and system maintenance endpoints."""
from datetime import datetime
from time import perf_counter
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel

from app.clients import ServiceClients
from backend.auth import User, get_current_user, require_role


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


# =============================================================================
# ROUTERS
# =============================================================================

router = APIRouter(prefix="/api", tags=["Admin"])
health_router = APIRouter(tags=["Health"])


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
