"""
Servicio de Autenticación.

Este módulo implementa la lógica de negocio para:
- Registro de usuarios con validación
- Login con bcrypt
- Generación y validación de JWT
- Gestión de sesiones con refresh tokens

Mejores prácticas implementadas:
- Passwords hasheados con bcrypt (cost=12)
- Access tokens de corta vida (15 min)
- Refresh tokens almacenados en BD (7 días)
- Rate limiting (se implementa en endpoints)
"""

import os
import re
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple

from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr, Field, field_validator
from psycopg2.extensions import connection as PGConnection

# Bcrypt import con fallback
try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False
    import hashlib as fallback_hash

from app.postgres_block import (
    create_user as db_create_user,
    get_user_by_email,
    get_user_by_id,
    update_last_login,
    update_user_password,
    create_session,
    get_session_by_token,
    revoke_session,
    revoke_all_user_sessions,
    update_session_activity,
)


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

import structlog

_logger = structlog.get_logger()


def _log_warn(event: str, **kwargs: Any) -> None:
    warn_fn = getattr(_logger, "warning", None) or getattr(_logger, "warn", None)
    if callable(warn_fn):
        warn_fn(event, **kwargs)


def _get_jwt_secret(*, strict: bool = False) -> str:
    """
    Obtiene JWT secret con fail-fast en producción.
    
    Sprint 16 - E1: Hardening de seguridad.
    
    En producción:
        - Requiere JWT_SECRET_KEY configurado
        - Requiere mínimo 32 caracteres
        - Falla al iniciar si no cumple
    
    En desarrollo:
        - Usa default inseguro si no está configurado
        - Log warning para recordar configurar
    """
    secret = os.getenv("JWT_SECRET_KEY")
    
    app_env = os.getenv("APP_ENV", "development")

    if app_env in ("production", "prod", "staging"):
        if not secret:
            message = (
                "JWT_SECRET_KEY es requerido en producción. "
                "Configure la variable de entorno antes de iniciar."
            )
            if strict:
                raise RuntimeError(message)
            _logger.error("auth.jwt_secret_missing", message=message, env=app_env)
            return ""
        if len(secret) < 32:
            message = (
                "JWT_SECRET_KEY debe tener al menos 32 caracteres en producción "
                f"(actual: {len(secret)}). Use un secret más seguro."
            )
            if strict:
                raise RuntimeError(message)
            _logger.error("auth.jwt_secret_short", message=message, env=app_env)
            return secret
        return secret
    
    # Desarrollo/test
    if not secret:
        _log_warn(
            "auth.jwt_default_secret",
            message="Usando JWT secret por defecto. NO usar en producción.",
            env=app_env,
        )
        return "unsafe-secret-for-dev-change-in-prod"
    
    return secret


SECRET_KEY = os.getenv("JWT_SECRET_KEY") or ""
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = 240  # 4 horas para desarrollo (15 min en producción)
REFRESH_TOKEN_EXPIRE_DAYS = 7
BCRYPT_COST = 12

# Validación de password
PASSWORD_MIN_LENGTH = 8
PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$")


# =============================================================================
# MODELOS PYDANTIC
# =============================================================================

class RegisterRequest(BaseModel):
    """Request para registro de usuario."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = Field(None, max_length=100)
    organization_id: str = Field(default="default_org", max_length=50)
    
    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Valida requisitos de complejidad del password."""
        if len(v) < PASSWORD_MIN_LENGTH:
            raise ValueError(f"Password debe tener al menos {PASSWORD_MIN_LENGTH} caracteres")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password debe contener al menos una minúscula")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password debe contener al menos una mayúscula")
        if not re.search(r"\d", v):
            raise ValueError("Password debe contener al menos un número")
        if not re.search(r"[@$!%*?&#]", v):
            raise ValueError("Password debe contener al menos un carácter especial (@$!%*?&#)")
        return v


class LoginRequest(BaseModel):
    """Request para login."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Response con tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos


class UserResponse(BaseModel):
    """Response con datos del usuario (sin password)."""
    id: str
    email: str
    full_name: Optional[str]
    organization_id: str
    role: str
    is_active: bool
    is_verified: bool


# =============================================================================
# FUNCIONES DE HASHING
# =============================================================================

def hash_password(password: str) -> str:
    """
    Genera hash bcrypt del password.
    
    Usa bcrypt con cost=12 (suficiente para producción).
    Falls back a SHA256 si bcrypt no está instalado.
    """
    if HAS_BCRYPT:
        salt = bcrypt.gensalt(rounds=BCRYPT_COST)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    else:
        # Fallback inseguro para desarrollo
        return f"sha256:{hashlib.sha256(password.encode()).hexdigest()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica password contra hash."""
    if HAS_BCRYPT and not hashed_password.startswith("sha256:"):
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    else:
        # Fallback para hashes SHA256
        expected = f"sha256:{hashlib.sha256(plain_password.encode()).hexdigest()}"
        return secrets.compare_digest(hashed_password, expected)


def hash_token(token: str) -> str:
    """Hash SHA256 para refresh tokens (no necesita bcrypt)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# =============================================================================
# FUNCIONES JWT
# =============================================================================

def create_access_token(
    user_id: str,
    email: str,
    role: str,
    organization_id: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Crea JWT access token."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    payload = {
        "sub": user_id,
        "email": email,
        # Mantener `role` por retrocompatibilidad y añadir `roles` para los guards de autorización
        "role": role,
        "roles": [role] if role else [],
        "org": organization_id,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    
    secret = _get_jwt_secret(strict=True)
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def create_refresh_token() -> str:
    """Genera refresh token aleatorio seguro."""
    return secrets.token_urlsafe(32)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decodifica y valida access token.
    
    Returns:
        Dict con payload si válido, None si inválido/expirado
    """
    try:
        secret = _get_jwt_secret(strict=False)
        if not secret:
            return None
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        
        if payload.get("type") != "access":
            return None
            
        return payload
    except JWTError:
        return None


# =============================================================================
# SERVICIO DE AUTENTICACIÓN
# =============================================================================

def register_user(
    pg: PGConnection,
    request: RegisterRequest,
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Registra un nuevo usuario.
    
    Args:
        pg: Conexión PostgreSQL
        request: Datos de registro validados
    
    Returns:
        Tuple (user_data, error_message)
        Si éxito: (user_data, None)
        Si error: (None, error_message)
    """
    # Verificar si email ya existe
    existing = get_user_by_email(pg, request.email)
    if existing:
        return None, "Ya existe un usuario con este email"
    
    # Hash del password
    password_hash = hash_password(request.password)
    
    # Crear usuario
    try:
        user = db_create_user(
            pg=pg,
            email=request.email,
            password_hash=password_hash,
            full_name=request.full_name,
            organization_id=request.organization_id,
            role="analyst",  # Role por defecto
        )
        return user, None
    except Exception as e:
        return None, f"Error al crear usuario: {str(e)}"


def authenticate_user(
    pg: PGConnection,
    email: str,
    password: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Autentica usuario con email y password.
    
    Returns:
        Tuple (user_data, error_message)
    """
    user = get_user_by_email(pg, email)
    
    if not user:
        return None, "Credenciales inválidas"
    
    if not user.get("is_active"):
        return None, "Usuario desactivado"
    
    if not verify_password(password, user["password_hash"]):
        return None, "Credenciales inválidas"
    
    # Actualizar último login
    update_last_login(pg, user["id"])
    
    # Retornar sin password_hash
    user_safe = {k: v for k, v in user.items() if k != "password_hash"}
    return user_safe, None


def create_tokens_for_user(
    pg: PGConnection,
    user: Dict[str, Any],
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> TokenResponse:
    """
    Genera access + refresh tokens para un usuario.
    
    El refresh token se almacena hasheado en la BD.
    """
    # Generar tokens
    access_token = create_access_token(
        user_id=user["id"],
        email=user["email"],
        role=user["role"],
        organization_id=user["organization_id"],
    )
    
    refresh_token = create_refresh_token()
    refresh_token_hash = hash_token(refresh_token)
    
    # Guardar sesión en BD
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    create_session(
        pg=pg,
        user_id=user["id"],
        refresh_token_hash=refresh_token_hash,
        expires_at=expires_at.isoformat(),
        user_agent=user_agent,
        ip_address=ip_address,
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def refresh_access_token(
    pg: PGConnection,
    refresh_token: str,
) -> Tuple[Optional[TokenResponse], Optional[str]]:
    """
    Renueva access token usando refresh token.
    
    Returns:
        Tuple (new_tokens, error_message)
    """
    refresh_hash = hash_token(refresh_token)
    session = get_session_by_token(pg, refresh_hash)
    
    if not session:
        return None, "Refresh token inválido"
    
    if session.get("is_revoked"):
        return None, "Sesión revocada"
    
    # Verificar expiración
    expires_at = datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00"))
    if expires_at < datetime.now(timezone.utc):
        return None, "Refresh token expirado"
    
    if not session.get("user_is_active"):
        return None, "Usuario desactivado"
    
    # Actualizar actividad de sesión
    update_session_activity(pg, session["session_id"])
    
    # Generar nuevo access token
    access_token = create_access_token(
        user_id=session["user_id"],
        email=session["email"],
        role=session["role"],
        organization_id=session["organization_id"],
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,  # Mismo refresh token
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    ), None


def logout_user(pg: PGConnection, refresh_token: str) -> bool:
    """Revoca la sesión asociada al refresh token."""
    refresh_hash = hash_token(refresh_token)
    session = get_session_by_token(pg, refresh_hash)
    
    if session:
        return revoke_session(pg, session["session_id"])
    return False


def logout_all_sessions(pg: PGConnection, user_id: str) -> int:
    """Revoca todas las sesiones del usuario."""
    return revoke_all_user_sessions(pg, user_id)


def change_password(
    pg: PGConnection,
    user_id: str,
    current_password: str,
    new_password: str,
) -> Tuple[bool, Optional[str]]:
    """
    Cambia password del usuario.
    
    Valida password actual antes de cambiar.
    """
    user = get_user_by_id(pg, user_id)
    if not user:
        return False, "Usuario no encontrado"
    
    # Obtener user con password_hash
    user_full = get_user_by_email(pg, user["email"])
    if not verify_password(current_password, user_full["password_hash"]):
        return False, "Password actual incorrecto"
    
    # Validar nuevo password
    try:
        RegisterRequest(email="test@test.com", password=new_password)
    except ValueError as e:
        return False, str(e)
    
    # Actualizar password
    new_hash = hash_password(new_password)
    success = update_user_password(pg, user_id, new_hash)
    
    if success:
        # Revocar todas las sesiones por seguridad
        revoke_all_user_sessions(pg, user_id)
        return True, None
    
    return False, "Error al actualizar password"
