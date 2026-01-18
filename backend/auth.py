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
from dotenv import load_dotenv

from app.tenant_context import set_current_user_context

load_dotenv()

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Secreto para firmar tokens JWT (usar valor seguro en producción)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "unsafe-secret-for-dev")

# Algoritmo de firma JWT
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# Tiempo de expiración de tokens (minutos)
ACCESS_TOKEN_EXPIRE_MINUTES = 240  # 4 horas para desarrollo

# API Key alternativa (para integraciones simples)
# Prioriza NEO4J_API_KEY por compatibilidad con configuración existente
API_KEY = os.getenv("NEO4J_API_KEY") or os.getenv("API_KEY")
# En multi-tenant estricto, la API key debe estar acotada a una organización.
API_KEY_ORG_ID = os.getenv("API_KEY_ORG_ID")
API_KEY_USER_ID = os.getenv("API_KEY_USER_ID", "api-key-user")
API_KEY_ROLES = [r.strip() for r in os.getenv("API_KEY_ROLES", "admin").split(",") if r.strip()]

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
    if x_api_key and API_KEY and x_api_key == API_KEY:
        if not API_KEY_ORG_ID:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API Key requires API_KEY_ORG_ID for strict multi-tenant",
                headers={"WWW-Authenticate": "Bearer"},
            )
        roles = [str(r).strip().lower() for r in API_KEY_ROLES if str(r).strip()]
        user = User(user_id=API_KEY_USER_ID, organization_id=API_KEY_ORG_ID, roles=roles)
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
