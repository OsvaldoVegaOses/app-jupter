"""
Helpers para manejo uniforme de errores.

Sprint 16 - E7: Helpers reutilizables para errores.

Este módulo proporciona:
    - ErrorCode: Códigos de error estándar
    - ServiceError: Excepción con código y contexto
    - api_error(): Helper para HTTPException sanitizado
    - @with_retry: Decorator para reintentos con backoff
    - @wrap_external_call: Decorator para logging de servicios externos
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar

import structlog
from fastapi import HTTPException

_logger = structlog.get_logger()
T = TypeVar("T")


def _log_warn(event: str, **kwargs: Any) -> None:
    warn_fn = getattr(_logger, "warning", None) or getattr(_logger, "warn", None)
    if callable(warn_fn):
        warn_fn(event, **kwargs)


# =============================================================================
# CÓDIGOS DE ERROR ESTÁNDAR
# =============================================================================

class ErrorCode:
    """Códigos de error para respuestas HTTP."""
    
    # Servicios externos
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    DATABASE_ERROR = "DATABASE_ERROR"
    VECTOR_DB_ERROR = "VECTOR_DB_ERROR"
    GRAPH_DB_ERROR = "GRAPH_DB_ERROR"
    LLM_ERROR = "LLM_ERROR"
    
    # Autenticación
    AUTH_ERROR = "AUTH_ERROR"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    
    # Validación
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    
    # Operaciones
    OPERATION_FAILED = "OPERATION_FAILED"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"


# =============================================================================
# EXCEPCIONES DE DOMINIO
# =============================================================================

@dataclass
class ServiceError(Exception):
    """
    Error de servicio con código y contexto estructurado.
    
    Usar para traducir excepciones externas a errores de dominio.
    """
    code: str
    message: str
    context: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a dict para logging."""
        return {
            "code": self.code,
            "message": self.message,
            "context": self.context or {},
        }


# Excepciones específicas por servicio (Sprint 16 - E3)
class QdrantError(ServiceError):
    """Error en operaciones Qdrant (búsqueda vectorial)."""
    def __init__(self, message: str, context: Optional[Dict] = None):
        super().__init__(ErrorCode.VECTOR_DB_ERROR, message, context)


class Neo4jError(ServiceError):
    """Error en operaciones Neo4j (grafo)."""
    def __init__(self, message: str, context: Optional[Dict] = None):
        super().__init__(ErrorCode.GRAPH_DB_ERROR, message, context)


class PostgresError(ServiceError):
    """Error en operaciones PostgreSQL."""
    def __init__(self, message: str, context: Optional[Dict] = None):
        super().__init__(ErrorCode.DATABASE_ERROR, message, context)


class LLMError(ServiceError):
    """Error en operaciones LLM (Azure OpenAI)."""
    def __init__(self, message: str, context: Optional[Dict] = None):
        super().__init__(ErrorCode.LLM_ERROR, message, context)


# =============================================================================
# HELPERS HTTP
# =============================================================================

def api_error(
    status_code: int,
    code: str,
    message: str,
    exc: Optional[Exception] = None,
    log_level: str = "error",
) -> HTTPException:
    """
    Genera HTTPException sin exponer detalles internos.
    
    Sprint 16 - E5: Sanitización de errores HTTP.
    
    Args:
        status_code: Código HTTP (400, 500, etc.)
        code: Código de error interno (para debugging)
        message: Mensaje amigable para el usuario
        exc: Excepción original (se loguea pero no se expone)
        log_level: Nivel de log ("error", "warning", "info")
        
    Returns:
        HTTPException con detail estructurado y sin internals
    """
    log_fn = getattr(_logger, log_level, _logger.error)
    
    log_data = {
        "status": status_code,
        "code": code,
        "message": message,
    }
    
    if exc:
        log_data["error_type"] = type(exc).__name__
        log_data["error_detail"] = str(exc)
    
    log_fn("api.error", **log_data, exc_info=bool(exc))
    
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
        },
    )


def handle_service_error(exc: Exception, operation: str = "operación") -> HTTPException:
    """
    Traduce excepciones de servicio a HTTPException apropiada.
    
    Sprint 16 - E3: Manejo uniforme de errores por servicio.
    
    Mapeo de errores:
        - QdrantError → 503 (servicio no disponible)
        - Neo4jError → 503
        - PostgresError → 503
        - LLMError → 503
        - TimeoutError → 504 (gateway timeout)
        - ServiceError → 500 (genérico)
        - Exception → 500 (inesperado)
    """
    if isinstance(exc, QdrantError):
        return api_error(503, ErrorCode.VECTOR_DB_ERROR, 
                        f"Servicio de búsqueda no disponible durante {operation}", exc)
    
    elif isinstance(exc, Neo4jError):
        return api_error(503, ErrorCode.GRAPH_DB_ERROR,
                        f"Servicio de grafos no disponible durante {operation}", exc)
    
    elif isinstance(exc, PostgresError):
        return api_error(503, ErrorCode.DATABASE_ERROR,
                        f"Base de datos no disponible durante {operation}", exc)
    
    elif isinstance(exc, LLMError):
        return api_error(503, ErrorCode.LLM_ERROR,
                        f"Servicio de IA no disponible durante {operation}", exc)
    
    elif isinstance(exc, TimeoutError):
        return api_error(504, ErrorCode.TIMEOUT,
                        f"La {operation} demoró demasiado. Intente con menos datos.", exc)
    
    elif isinstance(exc, ServiceError):
        return api_error(500, exc.code, exc.message, exc)
    
    else:
        return api_error(500, ErrorCode.OPERATION_FAILED,
                        f"Error inesperado durante {operation}", exc)


# =============================================================================
# DECORATORS
# =============================================================================

def with_retry(
    max_retries: int = 3,
    backoff: float = 1.0,
    exceptions: tuple = (Exception,),
):
    """
    Decorator para reintentos con backoff exponencial.
    
    Args:
        max_retries: Número máximo de reintentos
        backoff: Tiempo base entre reintentos (se duplica cada vez)
        exceptions: Tupla de excepciones a reintentar
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        wait = backoff * (2 ** attempt)
                        _log_warn(
                            "retry.attempt",
                            func=func.__name__,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            wait_seconds=wait,
                            error=str(e),
                        )
                        time.sleep(wait)
            raise last_error
        return wrapper
    return decorator


def wrap_external_call(service: str):
    """
    Decorator para logging uniforme de llamadas a servicios externos.
    
    Args:
        service: Nombre del servicio (qdrant, neo4j, postgres, llm)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                _logger.error(
                    f"{service}.call_error",
                    func=func.__name__,
                    error_type=type(e).__name__,
                    error=str(e),
                    exc_info=True,
                )
                raise ServiceError(
                    code=f"{service.upper()}_ERROR",
                    message=f"Error en servicio {service}",
                    context={"original_error": str(e), "func": func.__name__},
                ) from e
        return wrapper
    return decorator


def log_and_continue(service: str, default: Any = None):
    """
    Decorator que loguea errores pero retorna valor default.
    
    Útil para operaciones no críticas que no deben bloquear el flujo.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                _log_warn(
                    f"{service}.error_ignored",
                    func=func.__name__,
                    error=str(e),
                )
                return default
        return wrapper
    return decorator
