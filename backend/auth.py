"""
Autenticación y autorización para la API REST.

Este módulo implementa dos métodos de autenticación:
1. JWT Bearer Token: Para aplicaciones con login de usuario
2. API Key Header: Para integraciones simples (scripts, CI/CD)

Flujo de autenticación:
    1. Cliente envía Authorization: Bearer <token> o X-API-Key: <key>
    2. get_current_user() valida las credenciales
    3. Si es válido, retorna objeto User con user_id, org, roles
    4. Si no es válido, retorna 401 Unauthorized

Variables de entorno:
    - JWT_SECRET_KEY: Secreto para firmar/verificar tokens
    - JWT_ALGORITHM: Algoritmo de firma (default: HS256)
    - NEO4J_API_KEY o API_KEY: Key para autenticación por header

Modelos Pydantic:
    - User: Usuario autenticado con roles
    - TokenData: Payload decodificado del JWT

Dependencias FastAPI:
    - get_current_user: Obtiene usuario de token o API key
    - get_current_active_user: Wrapper (para futuro filtro de usuarios activos)

Example:
    # En endpoint FastAPI
    @app.get("/api/protected")
    async def protected_route(user: User = Depends(get_current_user)):
        return {"user": user.user_id}
"""

import os
from typing import Optional, Dict, Any, List
from functools import lru_cache

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from dotenv import load_dotenv, find_dotenv

from app.tenant_context import set_current_user_context

ENV_FILE_VAR = "APP_ENV_FILE"

# Load .env early so module-level auth settings (API_KEY_*) are correctly
# initialized even under uvicorn --reload where cwd/app-dir can vary.
try:
    _env_file = os.getenv(ENV_FILE_VAR) or find_dotenv(usecwd=True)
    if not _env_file:
        try:
            from pathlib import Path

            candidate = Path(__file__).resolve().parents[1] / ".env"
            if candidate.exists():
                _env_file = str(candidate)
        except Exception:
            _env_file = None
    if _env_file:
        load_dotenv(_env_file, override=True)
    else:
        # best-effort: fall back to default dotenv behavior
        load_dotenv(override=True)
except Exception:
    # Never fail import due to dotenv issues.
    pass

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Secreto para firmar tokens JWT (usar valor seguro en producción)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "unsafe-secret-for-dev")

# Algoritmo de firma JWT
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# Tiempo de expiración de tokens (minutos)
ACCESS_TOKEN_EXPIRE_MINUTES = 240  # 4 horas para desarrollo

def _get_api_key_config() -> tuple[Optional[str], Optional[str], str, List[str]]:
    """Lee configuración de API key desde el entorno (runtime).

    Nota: no confiamos en valores inicializados en import-time porque uvicorn
    --reload y diferentes cwd/app-dir pueden desincronizar la carga del .env.
    """

    @lru_cache(maxsize=1)
    def _ensure_env_loaded() -> None:
        try:
            env_file = os.getenv(ENV_FILE_VAR) or find_dotenv(usecwd=True)
            if not env_file:
                try:
                    from pathlib import Path

                    candidate = Path(__file__).resolve().parents[1] / ".env"
                    if candidate.exists():
                        env_file = str(candidate)
                except Exception:
                    env_file = None
            if env_file:
                load_dotenv(env_file, override=True)
        except Exception:
            pass

    # Ensure env is loaded before reading values.
    _ensure_env_loaded()

    api_key = os.getenv("NEO4J_API_KEY") or os.getenv("API_KEY")
    org_id = os.getenv("API_KEY_ORG_ID")
    user_id = os.getenv("API_KEY_USER_ID", "api-key-user")
    roles = [r.strip() for r in os.getenv("API_KEY_ROLES", "admin").split(",") if r.strip()]
    return api_key, org_id, user_id, roles

# Esquema OAuth2 para extraer token del header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


# =============================================================================
# MODELOS PYDANTIC
# =============================================================================

class User(BaseModel):
    """
    Usuario autenticado.
    
    Attributes:
        user_id: Identificador único del usuario (sub del JWT)
        organization_id: Organización a la que pertenece (multi-tenancy)
        roles: Lista de roles asignados (admin, analyst, viewer)
    """
    user_id: str
    organization_id: str = "default_org"
    roles: List[str] = []


class TokenData(BaseModel):
    """
    Datos extraídos del payload JWT.
    
    Attributes:
        sub: Subject (user_id)
        org: Organization ID
        roles: Lista de roles
    """
    sub: Optional[str] = None
    org: Optional[str] = "default_org"
    roles: List[str] = []


# =============================================================================
# FUNCIONES DE AUTENTICACIÓN
# =============================================================================

def verify_token(token: str) -> TokenData:
    """
    Verifica y decodifica un token JWT.
    
    Args:
        token: Token JWT a verificar
        
    Returns:
        TokenData con información del usuario
        
    Raises:
        HTTPException 401: Si el token es inválido o expirado
    """
    try:
        # Decodificar el token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        org_id: str = payload.get("org", "default_org")
        roles: List[str] = payload.get("roles", [])
        
        if user_id is None:
            raise JWTError("Missing subject")
            
        return TokenData(sub=user_id, org=org_id, roles=roles)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> User:
    """
    Dependencia principal de autenticación.
    
    Intenta autenticar en orden:
    1. Bearer JWT token
    2. X-API-Key header (fallback para scripts/integraciones)
    
    Args:
        token: Bearer token extraído por OAuth2PasswordBearer
        x_api_key: API Key del header X-API-Key
        
    Returns:
        User autenticado
        
    Raises:
        HTTPException 401: Si no hay credenciales válidas
    """
    # Opción 1: Bearer JWT
    if token:
        token_data = verify_token(token)
        user = User(
            user_id=token_data.sub,
            organization_id=token_data.org,
            roles=token_data.roles,
        )
        set_current_user_context(user.user_id, user.organization_id, user.roles)
        return user

    # Opción 2: API Key (para integraciones simples)
    api_key, org_id, api_user_id, api_roles = _get_api_key_config()

    # Best-effort: if org_id is missing, try to load settings (which loads .env
    # with override=True) and then re-read env. This avoids 401s when the running
    # process didn't pick up .env correctly.
    if x_api_key and api_key and x_api_key == api_key and not org_id:
        try:
            from app.settings import load_settings

            load_settings(os.getenv(ENV_FILE_VAR))
        except Exception:
            pass
        api_key, org_id, api_user_id, api_roles = _get_api_key_config()

    if x_api_key and api_key and x_api_key == api_key:
        if not org_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API Key requires API_KEY_ORG_ID for strict multi-tenant",
                headers={"WWW-Authenticate": "Bearer"},
            )
        roles = [str(r).strip().lower() for r in (api_roles or []) if str(r).strip()]
        user = User(user_id=str(api_user_id), organization_id=str(org_id), roles=roles)
        set_current_user_context(user.user_id, user.organization_id, user.roles)
        return user

    # Sin credenciales válidas
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated (Bearer token or valid API Key required)",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Wrapper para filtrar usuarios activos (futuro: verificar estado de cuenta).
    
    Actualmente solo retorna el usuario sin validación adicional.
    """
    return current_user


def require_role(allowed_roles: List[str]):
    """
    Factory de dependencia que verifica que el usuario tiene uno de los roles permitidos.
    
    Args:
        allowed_roles: Lista de roles que tienen acceso (cualquiera de ellos)
    
    Returns:
        Dependency function para usar con Depends()
    
    Example:
        @router.get("/admin/users")
        async def list_users(user: User = Depends(require_role(["admin"]))):
            ...
    """
    async def role_checker(user: User = Depends(get_current_user)) -> User:
        # Check if user has any of the allowed roles
        user_roles = {str(r).strip().lower() for r in (user.roles or []) if str(r).strip()}
        if "superadmin" in user_roles:
            return user
        allowed_set = {str(r).strip().lower() for r in allowed_roles if str(r).strip()}
        
        if not user_roles & allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Se requiere uno de estos roles: {', '.join(allowed_roles)}"
            )
        return user
    
    return role_checker
