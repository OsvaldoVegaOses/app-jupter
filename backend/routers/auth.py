"""
Auth router - Authentication endpoints for login, registration, and token refresh.
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Body, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
import structlog
from functools import lru_cache
import os
import asyncio
import time

import psycopg2

from app.clients import ServiceClients, build_service_clients
from app.settings import AppSettings, load_settings

# Logger
api_logger = structlog.get_logger("app.api.auth")

# Circuit breaker for login
_LOGIN_CB = {
    "failures": 0,
    "opened_until": 0.0,
    "last_failure": 0.0,
}
_LOGIN_CB_WINDOW_SECONDS = 30
_LOGIN_CB_OPEN_SECONDS = 20
_LOGIN_CB_THRESHOLD = 3


def _login_cb_is_open() -> float:
    now = time.monotonic()
    opened_until = float(_LOGIN_CB.get("opened_until") or 0.0)
    if opened_until > now:
        return max(0.0, opened_until - now)
    return 0.0


def _login_cb_record_failure() -> None:
    now = time.monotonic()
    last_failure = float(_LOGIN_CB.get("last_failure") or 0.0)
    if now - last_failure > _LOGIN_CB_WINDOW_SECONDS:
        _LOGIN_CB["failures"] = 0
    _LOGIN_CB["failures"] = int(_LOGIN_CB.get("failures") or 0) + 1
    _LOGIN_CB["last_failure"] = now
    if _LOGIN_CB["failures"] >= _LOGIN_CB_THRESHOLD:
        _LOGIN_CB["opened_until"] = now + _LOGIN_CB_OPEN_SECONDS
        api_logger.warning(
            "auth.login.circuit_open",
            failures=_LOGIN_CB["failures"],
            open_seconds=_LOGIN_CB_OPEN_SECONDS,
        )


def _login_cb_record_success() -> None:
    _LOGIN_CB["failures"] = 0
    _LOGIN_CB["opened_until"] = 0.0
    _LOGIN_CB["last_failure"] = 0.0

# Dependencies
@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    env_file = os.getenv("APP_ENV_FILE")
    return load_settings(env_file)

from typing import AsyncGenerator

async def get_service_clients(settings: AppSettings = Depends(get_settings)) -> AsyncGenerator[ServiceClients, None]:
    """
    Dependency helper that builds ServiceClients with automatic cleanup.
    
    CRITICAL: Uses yield + finally to ensure connections are returned to pool!
    """
    clients = build_service_clients(settings)
    try:
        yield clients
    finally:
        clients.close()

# Create routers
# Main auth router with /api/auth prefix
router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# OAuth2 router for /token endpoint (no prefix, standard OAuth2)
oauth_router = APIRouter(tags=["OAuth2"])


# =============================================================================
# OAuth2 Token Endpoint (Standard Flow)
# =============================================================================

@oauth_router.post("/token")
async def api_login_oauth(
    form_data: OAuth2PasswordRequestForm = Depends(),
    clients: ServiceClients = Depends(get_service_clients),
):
    """
    Login de usuario - genera access token y refresh token.
    
    Usa OAuth2 password flow estándar.
    """
    from backend.auth_service import authenticate_user, create_tokens_for_user
    
    user, error = authenticate_user(
        clients.postgres, 
        form_data.username,  # OAuth2 usa 'username' aunque nosotros usamos email
        form_data.password
    )
    
    if error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error,
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        tokens = create_tokens_for_user(clients.postgres, user)
    except Exception as e:
        api_logger.error("auth.token_generation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error generando tokens",
        )
    
    api_logger.info("auth.login.success", user_id=user["id"], email=user["email"])
    
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "expires_in": tokens.expires_in,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user.get("full_name"),
            "organization_id": user.get("organization_id", "default_org"),
            "role": user.get("role", "analyst"),
            "roles": [user.get("role", "analyst")],
        }
    }


# =============================================================================
# JSON Auth Endpoints
# =============================================================================

@router.post("/login")
async def api_login_json(
    request: Dict[str, Any] = Body(...),
    clients: ServiceClients = Depends(get_service_clients),
):
    """
    Login de usuario con JSON - genera access token y refresh token.
    
    El frontend envía JSON en lugar of form-data.
    """
    from backend.auth_service import authenticate_user, create_tokens_for_user
    
    email = request.get("email", "")
    password = request.get("password", "")

    cooldown = _login_cb_is_open()
    if cooldown > 0:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Servicio temporalmente no disponible. Reintenta en unos segundos."},
            headers={"Retry-After": str(int(cooldown) + 1)},
        )
    
    if not email or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email y password son requeridos",
        )
    
    user = None
    error = None
    try:
        user, error = authenticate_user(clients.postgres, email, password)
    except (psycopg2.OperationalError, psycopg2.InterfaceError, psycopg2.DatabaseError) as exc:
        api_logger.warning("auth.login.db_error", error=str(exc)[:200])
        await asyncio.sleep(0.2)
        try:
            user, error = authenticate_user(clients.postgres, email, password)
        except (psycopg2.OperationalError, psycopg2.InterfaceError, psycopg2.DatabaseError) as exc2:
            api_logger.warning("auth.login.db_error.retry_failed", error=str(exc2)[:200])
            _login_cb_record_failure()
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": "Login temporalmente no disponible. Reintenta en unos segundos."},
                headers={"Retry-After": str(_LOGIN_CB_OPEN_SECONDS)},
            )
    
    if error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error,
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        tokens = create_tokens_for_user(clients.postgres, user)
    except Exception as e:
        _login_cb_record_failure()
        api_logger.error("auth.login.token_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error generando tokens",
        )

    _login_cb_record_success()
    
    api_logger.info("auth.login.json.success", user_id=user["id"], email=user["email"])
    
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "expires_in": tokens.expires_in,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user.get("full_name"),
            "organization_id": user.get("organization_id", "default_org"),
            "role": user.get("role", "analyst"),
            "roles": [user.get("role", "analyst")],
        }
    }


@router.post("/register")
async def api_register(
    request: Dict[str, Any] = Body(...),
    clients: ServiceClients = Depends(get_service_clients),
):
    """
    Registro de nuevo usuario.
    
    Campos requeridos:
    - email: Email válido
    - password: Mínimo 8 caracteres, debe incluir mayúscula, minúscula, número y símbolo
    
    Campos opcionales:
    - full_name: Nombre completo
    - organization_id: ID de organización (default: "default_org")
    """
    from backend.auth_service import RegisterRequest, register_user, create_tokens_for_user
    
    try:
        reg_request = RegisterRequest(
            email=request.get("email", ""),
            password=request.get("password", ""),
            full_name=request.get("full_name"),
            organization_id=request.get("organization_id", "default_org"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    user, error = register_user(clients.postgres, reg_request)
    
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    # Auto-asignar al proyecto default para evitar errores de permisos iniciales.
    try:
        from app.postgres_block import add_project_member, ensure_default_project_db

        ensure_default_project_db(clients.postgres)
        role = user.get("role", "analyst")
        project_role = "admin" if role == "admin" else "codificador"
        add_project_member(
            clients.postgres,
            "default",
            user["id"],
            project_role,
            added_by="system",
        )
    except Exception as exc:  # noqa: BLE001
        api_logger.warning("auth.register.default_membership_failed", error=str(exc)[:120])
    
    # Generar tokens automáticamente después del registro
    try:
        tokens = create_tokens_for_user(clients.postgres, user)
    except Exception as e:
        # Usuario creado pero error en tokens - retornar solo confirmación
        api_logger.warning("auth.register.token_error", user_id=user["id"], error=str(e))
        return {
            "message": "Usuario registrado. Por favor inicia sesión.",
            "user_id": user["id"],
        }
    
    api_logger.info("auth.register.success", user_id=user["id"], email=user["email"])
    
    return {
        "message": "Usuario registrado exitosamente",
        "user_id": user["id"],
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user.get("full_name"),
            "organization_id": user.get("organization_id", "default_org"),
            "role": user.get("role", "analyst"),
        }
    }


@router.post("/refresh")
async def api_refresh_token(
    request: Dict[str, Any] = Body(...),
    clients: ServiceClients = Depends(get_service_clients),
):
    """
    Renueva access token usando refresh token.
    """
    from backend.auth_service import refresh_access_token
    
    refresh_token = request.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="refresh_token es requerido",
        )
    
    tokens, error = refresh_access_token(clients.postgres, refresh_token)
    
    if error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error,
        )
    
    api_logger.info("auth.refresh.success")
    
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "expires_in": tokens.expires_in,
    }


@router.delete("/me")
async def api_delete_own_account(
    clients: ServiceClients = Depends(get_service_clients),
    token: str = Depends(lambda: None),  # Will be overridden below
):
    """
    Elimina la cuenta del usuario actual.
    
    Requiere autenticación. Elimina:
    - Todas las sesiones del usuario
    - El registro del usuario
    
    Esta acción es irreversible.
    """
    from backend.auth import get_current_user, User
    from fastapi.security import OAuth2PasswordBearer
    
    # This implementation requires the user to be injected
    # For now, return not implemented - use frontend to call with token
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Este endpoint requiere implementación adicional. Use el panel de admin para eliminar usuarios."
    )


# Self-delete with proper user injection
from backend.auth import User, get_current_user

@router.post("/me/delete")
async def api_confirm_delete_own_account(
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(get_current_user),
):
    """
    Elimina la cuenta del usuario actual (confirmada).
    
    POST en lugar de DELETE para compatibilidad con más clientes.
    Requiere autenticación Bearer token.
    
    Elimina:
    - Todas las sesiones del usuario
    - El registro del usuario
    
    Esta acción es irreversible.
    """
    with clients.postgres.cursor() as cur:
        # Get user email for logging
        cur.execute("SELECT email FROM app_users WHERE id = %s", (user.user_id,))
        result = cur.fetchone()
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )
        email = result[0]
        
        # Delete all sessions first
        cur.execute("DELETE FROM app_sessions WHERE user_id = %s", (user.user_id,))
        sessions_deleted = cur.rowcount
        
        # Delete user
        cur.execute("DELETE FROM app_users WHERE id = %s", (user.user_id,))
        
        clients.postgres.commit()
    
    api_logger.info("auth.self_delete.success", user_id=user.user_id, email=email, sessions_deleted=sessions_deleted)
    
    return {
        "status": "deleted",
        "message": "Tu cuenta ha sido eliminada permanentemente",
        "email": email,
        "sessions_revoked": sessions_deleted
    }


# Legacy /register endpoint (non-prefixed)
legacy_router = APIRouter(tags=["Auth-Legacy"])

@legacy_router.post("/register")
async def api_register_legacy(
    request: Dict[str, Any] = Body(...),
    clients: ServiceClients = Depends(get_service_clients),
):
    """Legacy register endpoint - redirects to /api/auth/register logic"""
    return await api_register(request, clients)


@legacy_router.post("/refresh")
async def api_refresh_legacy(
    request: Dict[str, Any] = Body(...),
    clients: ServiceClients = Depends(get_service_clients),
):
    """Legacy refresh endpoint - redirects to /api/auth/refresh logic"""
    return await api_refresh_token(request, clients)
