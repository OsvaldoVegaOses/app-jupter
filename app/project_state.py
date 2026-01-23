"""
Gestión de estado y configuración de proyectos.

Este módulo maneja el estado persistente de proyectos de análisis.
Usa PostgreSQL para almacenamiento cloud-ready (no archivos locales).

Funciones principales:
    - create_project(): Crea un nuevo proyecto
    - get_project_config(): Obtiene configuración de un proyecto
    - list_projects(): Lista todos los proyectos registrados
    - resolve_project(): Resuelve identificador a project_id
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from psycopg2.extensions import connection as PGConnection

# Import PostgreSQL functions for cloud storage
from app.postgres_block import (
    list_projects_db,
    get_project_db,
    resolve_project_db,
    create_project_db,
    update_project_db,
    update_project_config_db,
    ensure_default_project_db,
    load_project_state_db,
    save_project_stage_db,
    check_project_permission,
    add_project_member,
    log_project_action,
)
from app.tenant_context import get_current_user_context

_logger = logging.getLogger(__name__)

DEFAULT_PROJECT = "default"

# Legacy paths (kept for backward compatibility during transition)
PROJECTS_DIR = Path("metadata/projects")
REGISTRY_PATH = Path("metadata/projects_registry.json")
MANIFEST_PATH = Path("informes/report_manifest.json")
LOGS_DIR = Path("logs")


def _slugify(value: str) -> str:
    """Convierte un string a slug válido para ID de proyecto."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or DEFAULT_PROJECT


# =============================================================================
# Project Management Functions (PostgreSQL-backed)
# =============================================================================

def list_projects(pg: Optional[PGConnection] = None) -> List[Dict[str, Any]]:
    """
    Lista todos los proyectos registrados.
    
    Args:
        pg: Conexión PostgreSQL (requerida para cloud mode)
        
    Returns:
        Lista de proyectos
    """
    if pg is None:
        _logger.warning("list_projects called without pg connection - returning empty list")
        return []
    
    return list_projects_db(pg)


def list_projects_for_user(
    pg: PGConnection,
    user_id: Optional[str] = None,
    org_id: Optional[str] = None,
    role: str = "analyst",
) -> List[Dict[str, Any]]:
    """
    Lista proyectos filtrados por usuario/organización.
    
    Args:
        pg: Conexión PostgreSQL
        user_id: ID del usuario actual
        org_id: ID de la organización del usuario
        role: Rol del usuario (admin ve todos)
        
    Returns:
        Lista de proyectos que el usuario puede ver
    """
    # Admins ven proyectos de su organización (estricto)
    if role == "admin":
        return list_projects_db(pg, org_id=org_id)
    
    # Para otros roles, filtrar por owner_id o org_id
    return list_projects_db(pg, org_id=org_id, owner_id=user_id)


def _enforce_project_access(pg: PGConnection, project_id: str) -> None:
    """Enforce acceso estricto por organización/miembro usando el contexto de usuario."""
    user_ctx = get_current_user_context()
    if not user_ctx:
        return

    project = get_project_db(pg, project_id)
    if not project:
        raise ValueError(f"Proyecto '{project_id}' no existe.")

    user_id = str(user_ctx.get("user_id"))
    org_id = user_ctx.get("organization_id")
    roles = {str(r).strip().lower() for r in (user_ctx.get("roles") or [])}

    project_org = project.get("org_id")
    if project_org and org_id != project_org:
        raise ValueError("Acceso denegado: organización no coincide.")

    if "admin" in roles:
        return

    if project.get("owner_id") and project.get("owner_id") == user_id:
        return

    if check_project_permission(pg, project_id, user_id, "lector"):
        return

    auto_enroll_enabled = os.getenv("AUTO_ENROLL_DEFAULT_PROJECT", "true").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if auto_enroll_enabled and project_id == DEFAULT_PROJECT:
        try:
            project_role = "lector"
            if "admin" in roles:
                project_role = "admin"
            elif "analyst" in roles:
                project_role = "codificador"

            member = add_project_member(pg, project_id, user_id, project_role, added_by="system")
            log_project_action(
                pg,
                project_id,
                user_id,
                "auto_enroll",
                entity_type="member",
                entity_id=user_id,
                details={"role": member.get("role"), "source": "default_project"},
            )
            return
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "project.auto_enroll_failed",
                extra={"project_id": project_id, "user_id": user_id, "error": str(exc)[:200]},
            )

    raise ValueError("Acceso denegado: usuario sin permisos en el proyecto.")


def resolve_project(
    identifier: Optional[str],
    *,
    allow_create: bool = False,
    pg: Optional[PGConnection] = None,
) -> str:
    """
    Resuelve un identificador de proyecto a su ID canónico.
    
    Args:
        identifier: Nombre o ID del proyecto
        allow_create: Si True, retorna slug aunque el proyecto no exista
        pg: Conexión PostgreSQL (opcional - auto-conecta si es None)
        
    Returns:
        ID del proyecto
        
    Raises:
        ValueError: Si el proyecto no existe y allow_create es False
    """
    if identifier is None:
        return DEFAULT_PROJECT
    
    slug = _slugify(identifier)
    user_ctx = get_current_user_context() or {}
    org_id = user_ctx.get("organization_id")
    owner_id = user_ctx.get("user_id")

    if slug == DEFAULT_PROJECT and org_id and org_id != "default_org":
        slug = f"default-{org_id}"
        identifier = slug
    
    if pg is None:
        # Auto-connect using connection pool
        try:
            from app.clients import get_pg_connection, return_pg_connection
            from app.settings import load_settings
            import os
            
            settings = load_settings(os.getenv("APP_ENV_FILE"))
            auto_pg = get_pg_connection(settings)
            try:
                resolved = _resolve_project_with_pg(
                    identifier, slug, auto_pg, allow_create, org_id=org_id, owner_id=owner_id
                )
                if not allow_create:
                    _enforce_project_access(auto_pg, resolved)
                return resolved
            finally:
                return_pg_connection(auto_pg)
        except Exception as e:
            # If connection pool fails, fallback to slug
            _logger.debug(
                "resolve_project auto-connect failed, using slug fallback",
                extra={"identifier": identifier, "slug": slug, "error": str(e)}
            )
            return slug
    
    resolved = _resolve_project_with_pg(
        identifier, slug, pg, allow_create, org_id=org_id, owner_id=owner_id
    )
    if not allow_create:
        _enforce_project_access(pg, resolved)
    return resolved


def _resolve_project_with_pg(
    identifier: str,
    slug: str,
    pg: PGConnection,
    allow_create: bool,
    *,
    org_id: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> str:
    """Internal function to resolve project with a PostgreSQL connection."""
    
    # Asegurar que existe el proyecto default
    ensure_default_project_db(pg)

    # Si el usuario pertenece a una organización distinta, crear default por org
    if slug.startswith("default-") and org_id:
        existing_default = get_project_db(pg, slug)
        if not existing_default:
            create_project_db(
                pg,
                project_id=slug,
                name="Proyecto default",
                description="Proyecto base inicial",
                org_id=org_id,
                owner_id=owner_id,
            )
    
    # Buscar en PostgreSQL
    resolved = resolve_project_db(pg, identifier)
    if resolved:
        return resolved
    
    # Buscar por slug
    resolved = resolve_project_db(pg, slug)
    if resolved:
        return resolved
    
    if allow_create:
        _logger.debug(
            "project.resolve.auto_create",
            extra={"identifier": identifier, "slug": slug, "allow_create": True}
        )
        return slug
    
    # Proyecto no encontrado
    _logger.warning(
        "project.resolve.not_found",
        extra={
            "identifier": identifier,
            "slug": slug,
        }
    )
    raise ValueError(f"Proyecto '{identifier}' no existe.")


def create_project(
    pg: PGConnection,
    name: str,
    description: Optional[str] = None,
    org_id: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Crea un nuevo proyecto.
    
    Args:
        pg: Conexión PostgreSQL
        name: Nombre del proyecto
        description: Descripción opcional
        org_id: ID de la organización propietaria (multi-tenant)
        owner_id: ID del usuario que crea el proyecto
        
    Returns:
        Dict con datos del proyecto creado
        
    Raises:
        ValueError: Si el nombre es vacío
    """
    if not name.strip():
        raise ValueError("El nombre del proyecto no puede ser vacío.")
    
    slug = _slugify(name)
    
    # Verificar si ya existe DENTRO DE LA MISMA ORGANIZACIÓN
    # Multi-tenant: cada org puede tener un proyecto con el mismo slug
    existing = get_project_db(pg, slug, org_id=org_id)
    if existing:
        created_at = existing.get("created_at", "fecha desconocida")
        existing_name = existing.get("name", slug)
        raise ValueError(
            f"Ya existe un proyecto '{existing_name}' (ID: {slug}) creado el {created_at}. "
            "Intente refrescar la página (F5) para verlo, o cree un proyecto con diferente nombre."
        )
    
    return create_project_db(
        pg,
        project_id=slug,
        name=name.strip(),
        description=(description or "").strip() or None,
        org_id=org_id,
        owner_id=owner_id,
    )


def get_project(pg: PGConnection, project_id: str) -> Optional[Dict[str, Any]]:
    """Obtiene un proyecto por su ID."""
    return get_project_db(pg, project_id)


def get_project_config(pg: PGConnection, project_id: str) -> Dict[str, Any]:
    """
    Obtiene la configuración de un proyecto.
    
    Retorna valores por defecto si el proyecto no tiene configuración.
    """
    default_config = {
        "discovery_threshold": 0.30,
        "analysis_temperature": 0.3,
        "analysis_max_tokens": 2000,

        # Axial gating (Etapa 4): situational rules for unlocking.
        # - auto: chooses between coverage and saturation based on signals
        # - coverage: only coverage threshold applies
        # - saturation: plateau detection can unlock (still requires minimal coverage)
        # - manual: only axial_manual_unlocked controls access
        "axial_gate_policy": "auto",
        "axial_min_coverage_percent": 70.0,
        "axial_min_saturation_window": 3,
        "axial_min_saturation_threshold": 2,
        "axial_manual_unlocked": False,
    }
    
    project = get_project_db(pg, project_id)
    if not project:
        return default_config
    
    return {**default_config, **project.get("config", {})}


def update_project_config(
    pg: PGConnection,
    project_id: str,
    config_updates: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Actualiza la configuración de un proyecto.
    
    Args:
        pg: Conexión PostgreSQL
        project_id: ID del proyecto
        config_updates: Dict con campos a actualizar
        
    Returns:
        Dict con configuración actualizada
        
    Raises:
        ValueError: Si el proyecto no existe
    """
    result = update_project_config_db(pg, project_id, config_updates)
    if result is None:
        raise ValueError(f"Proyecto '{project_id}' no encontrado.")
    return result


def update_project_details(
    pg: PGConnection,
    project_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Actualiza el nombre/descripcion de un proyecto."""
    if name is not None and not name.strip():
        raise ValueError("El nombre del proyecto no puede ser vacío.")

    result = update_project_db(pg, project_id, name=name, description=description)
    if result is None:
        raise ValueError(f"Proyecto '{project_id}' no encontrado.")
    return result


# =============================================================================
# Project State Functions (PostgreSQL-backed)
# =============================================================================

def load_state(pg: PGConnection, project: str) -> Dict[str, Any]:
    """Carga el estado de un proyecto desde PostgreSQL."""
    return load_project_state_db(pg, project)


def save_state(pg: PGConnection, project: str, state: Dict[str, Any]) -> None:
    """Guarda el estado completo de un proyecto."""
    for stage, data in state.items():
        if isinstance(data, dict):
            save_project_stage_db(
                pg,
                project,
                stage,
                completed=data.get("completed", False),
                run_id=data.get("last_run_id"),
                command=data.get("command"),
                subcommand=data.get("subcommand"),
                extras=data.get("extras"),
            )


def mark_stage(
    pg: PGConnection,
    project: str,
    stage: str,
    *,
    run_id: str,
    command: str,
    subcommand: Optional[str] = None,
    extras: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Marca una etapa como completada."""
    return save_project_stage_db(
        pg,
        project,
        stage,
        completed=True,
        run_id=run_id,
        command=command,
        subcommand=subcommand,
        extras=extras,
    )


# =============================================================================
# Helper Functions
# =============================================================================

def detect_stage_status(
    pg: PGConnection,
    project: str,
    stages: Dict[str, Dict[str, Any]],
    *,
    stage_order: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """
    Detecta el estado de las etapas de un proyecto.
    
    Args:
        pg: Conexión PostgreSQL
        project: ID del proyecto
        stages: Definición de etapas
        stage_order: Orden de las etapas
        
    Returns:
        Dict con estado de cada etapa
    """
    state = load_state(pg, project)
    order = list(stage_order or stages.keys())
    results: Dict[str, Dict[str, Any]] = {}
    
    for key in order:
        definition = dict(stages.get(key, {}))
        stored = state.get(key, {})
        merged: Dict[str, Any] = {}
        merged.update(definition)
        merged.update(stored)
        merged["label"] = merged.get("label") or definition.get("label") or key
        results[key] = merged
    
    return {
        "project": project,
        "stages": results,
        "updated": True,
    }
