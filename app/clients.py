"""
Factory y gestión de conexiones a servicios externos.

Este módulo proporciona la clase `ServiceClients` que encapsula todas las
conexiones a servicios externos (Azure OpenAI, Qdrant, Neo4j, PostgreSQL)
y la función `build_service_clients()` para inicializarlas.

Uso típico:
    from app.settings import load_settings
    from app.clients import build_service_clients
    
    settings = load_settings()
    clients = build_service_clients(settings)
    
    try:
        # Usar clients.aoai, clients.qdrant, etc.
        response = clients.aoai.embeddings.create(...)
    finally:
        clients.close()  # Liberar conexiones

Nota:
    Este módulo soporta dos modos de autenticación para Azure:
    1. API Key: Si AZURE_OPENAI_API_KEY está configurada
    2. DefaultAzureCredential: Para autenticación basada en roles (RBAC)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import threading
import os
from time import perf_counter

import psycopg2
from psycopg2 import pool
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from neo4j import GraphDatabase, Driver
from openai import AzureOpenAI
from psycopg2.extensions import connection as PGConnection
from qdrant_client import QdrantClient

from .settings import AppSettings


# =============================================================================
# POSTGRESQL CONNECTION POOL (Singleton)
# =============================================================================

_pg_pool: Optional[pool.ThreadedConnectionPool] = None
_pg_pool_lock = threading.Lock()
_pool_stats_lock = threading.Lock()
_pool_stats = {
    "checked_out": 0,
}
_pool_health = {
    "slow_events": 0,
    "exhausted_events": 0,
    "last_event_ts": 0.0,
    "last_reset_ts": 0.0,
}


def reset_pg_pool(*, reason: str) -> None:
    """Close and reset the global Postgres pool.

    Use with caution: this will drop existing idle connections and force
    new connections to be established on the next request.
    """
    import structlog

    _pool_logger = structlog.get_logger("app.pool")
    global _pg_pool
    with _pg_pool_lock:
        if _pg_pool is None:
            return
        try:
            _pg_pool.closeall()
            _pool_logger.warning("pool.reset", reason=reason)
        except Exception as exc:  # pragma: no cover - best effort
            _pool_logger.error("pool.reset.failed", reason=reason, error=str(exc))
        finally:
            _pg_pool = None
            with _pool_stats_lock:
                _pool_stats["checked_out"] = 0
            _pool_health["last_reset_ts"] = perf_counter()


def _maybe_reset_pool(*, reason: str) -> None:
    """Decide if we should reset the pool based on recent health signals."""
    now = perf_counter()
    last_reset = _pool_health.get("last_reset_ts", 0.0)
    if now - last_reset < 120:
        return

    slow_events = _pool_health.get("slow_events", 0)
    exhausted_events = _pool_health.get("exhausted_events", 0)

    if slow_events >= 3 or exhausted_events >= 2:
        _pool_health["slow_events"] = 0
        _pool_health["exhausted_events"] = 0
        reset_pg_pool(reason=reason)


def get_pg_pool(settings: AppSettings) -> pool.ThreadedConnectionPool:
    """Get or create the PostgreSQL connection pool (thread-safe singleton)."""
    global _pg_pool
    
    if _pg_pool is not None:
        return _pg_pool
    
    with _pg_pool_lock:
        if _pg_pool is not None:
            return _pg_pool

        host = settings.postgres.host
        raw_user = settings.postgres.username
        sslmode = getattr(settings.postgres, "sslmode", None) or "prefer"

        # Azure Database for PostgreSQL requires SSL.
        # Username format differs by server type:
        # - Flexible Server: usually plain username (e.g., 'Osvaldo')
        # - Legacy Single Server: often 'username@servername'
        # We do NOT auto-append by default; allow opt-in via env for legacy setups.
        is_azure_pg = isinstance(host, str) and host.lower().endswith(".postgres.database.azure.com")
        if is_azure_pg:
            sslmode = "require" if sslmode in {"prefer", "allow", "disable", ""} else sslmode
            force_suffix = (str(os.environ.get("POSTGRES_FORCE_USERNAME_SUFFIX", "")).strip().lower() in {"1", "true", "yes"})
            if force_suffix and isinstance(raw_user, str) and raw_user and "@" not in raw_user:
                server_name = host.split(".", 1)[0]
                raw_user = f"{raw_user}@{server_name}"

            pw = settings.postgres.password
            if pw is None or str(pw).strip() == "":
                raise RuntimeError(
                    "PostgreSQL password is missing for Azure Postgres. "
                    "Set PGPASSWORD/POSTGRES_PASSWORD (and keep PGSSLMODE=require)."
                )
        
        _pg_pool = pool.ThreadedConnectionPool(
            minconn=10,
            maxconn=80,  # Increased significantly - frontend makes ~20 parallel requests per page load
            host=host,
            port=settings.postgres.port,
            dbname=settings.postgres.database,
            user=raw_user,
            password=settings.postgres.password,
            connect_timeout=10,
            sslmode=sslmode,
            options="-c statement_timeout=600000 -c application_name=app_jupter",
        )
        _pool_health["slow_events"] = 0
        _pool_health["exhausted_events"] = 0
        _pool_health["last_event_ts"] = perf_counter()
        with _pool_stats_lock:
            _pool_stats["checked_out"] = 0
        return _pg_pool


def get_pg_connection(settings: AppSettings) -> PGConnection:
    """Get a connection from the pool."""
    import structlog
    _pool_logger = structlog.get_logger("app.pool")
    
    pg_pool = get_pg_pool(settings)

    with _pool_stats_lock:
        used = int(_pool_stats["checked_out"])
    available = max(int(pg_pool.maxconn) - used, 0)
    
    # Log pool state for diagnostics - ALWAYS log as INFO
    _pool_logger.info("pool.getconn.request", used=used, available=available, maxconn=pg_pool.maxconn)
    
    if used >= pg_pool.maxconn - 10:  # Warning when pool is getting full
        _pool_logger.warning("pool.nearly_exhausted", used=used, available=available, maxconn=pg_pool.maxconn)
        _pool_health["exhausted_events"] += 1
        _pool_health["last_event_ts"] = perf_counter()
        _maybe_reset_pool(reason="pool.nearly_exhausted")
    
    try:
        wait_start = perf_counter()
        conn = pg_pool.getconn()
        wait_ms = (perf_counter() - wait_start) * 1000
        conn.set_client_encoding("UTF8")
        with _pool_stats_lock:
            _pool_stats["checked_out"] = int(_pool_stats["checked_out"]) + 1
            used_after = int(_pool_stats["checked_out"])
        _pool_logger.info(
            "pool.getconn.success",
            used=used_after,
            wait_ms=round(wait_ms, 2),
        )
        if wait_ms >= 1000:
            _pool_logger.warning(
                "pool.getconn.slow",
                used=used_after,
                wait_ms=round(wait_ms, 2),
                maxconn=pg_pool.maxconn,
            )
            _pool_health["slow_events"] += 1
            _pool_health["last_event_ts"] = perf_counter()
            _maybe_reset_pool(reason="pool.getconn.slow")
        return conn
    except Exception as e:
        _pool_logger.error("pool.getconn.FAILED", error=str(e), used=used, maxconn=pg_pool.maxconn)
        raise


def return_pg_connection(conn: PGConnection) -> None:
    """Return a connection to the pool.
    
    IMPORTANT: This function now does rollback before returning to ensure
    the connection is in a clean state. This is critical for connections
    that had statement timeouts or other errors.
    """
    import structlog
    _pool_logger = structlog.get_logger("app.pool")
    
    global _pg_pool
    if _pg_pool is not None and conn is not None:
        try:
            # CRITICAL: Rollback any uncommitted transaction before returning
            # This prevents connections in error state from polluting the pool
            try:
                conn.rollback()
            except Exception as rb_err:
                _pool_logger.warning("pool.rollback_before_return", error=str(rb_err))
            
            _pg_pool.putconn(conn)
            with _pool_stats_lock:
                _pool_stats["checked_out"] = max(int(_pool_stats["checked_out"]) - 1, 0)
                used = int(_pool_stats["checked_out"])
            _pool_logger.info("pool.putconn.success", used=used)
        except Exception as e:
            _pool_logger.error("pool.putconn.FAILED", error=str(e))
            # If putconn fails, try to close the connection directly
            try:
                conn.close()
                with _pool_stats_lock:
                    _pool_stats["checked_out"] = max(int(_pool_stats["checked_out"]) - 1, 0)
                _pool_logger.warning("pool.connection_closed_after_putconn_fail")
            except Exception:
                pass
    else:
        _pool_logger.warning("pool.putconn.skipped", pool_none=(_pg_pool is None), conn_none=(conn is None))


# =============================================================================
# DATACLASS DE CLIENTES
# =============================================================================

@dataclass
class ServiceClients:
    """
    Contenedor de conexiones a todos los servicios externos.
    
    Esta clase agrupa todas las conexiones necesarias para el funcionamiento
    del sistema de análisis cualitativo. Debe usarse como context manager
    o llamar a `close()` explícitamente para liberar recursos.
    
    Attributes:
        aoai: Cliente de Azure OpenAI para embeddings y análisis LLM
        qdrant: Cliente de Qdrant para búsqueda vectorial
        neo4j: Driver de Neo4j para operaciones de grafo
        postgres: Conexión a PostgreSQL para códigos y proyectos
        embed_dims: Dimensiones del modelo de embeddings (ej: 3072 para text-embedding-3-large)
        
    Example:
        >>> clients = build_service_clients(settings)
        >>> try:
        ...     # Usar los clientes
        ...     embeddings = clients.aoai.embeddings.create(...)
        ... finally:
        ...     clients.close()
    """
    aoai: AzureOpenAI
    qdrant: QdrantClient
    neo4j: Driver
    postgres: PGConnection
    embed_dims: int
    _uses_pool: bool = True  # Flag to track if using connection pool

    def close(self) -> None:
        """
        Cierra todas las conexiones abiertas.
        
        Es importante llamar a este método cuando ya no se necesiten los clientes
        para liberar conexiones de base de datos y evitar leaks.
        
        Sprint 16 - E4: Logging de errores en cierre (nivel debug).
        """
        import structlog
        _close_logger = structlog.get_logger("app.clients")
        
        _close_logger.info("clients.close.start", uses_pool=self._uses_pool)
        
        # PostgreSQL - Return to pool instead of close
        try:
            if self._uses_pool:
                return_pg_connection(self.postgres)
                _close_logger.info("clients.close.pg_returned")
            else:
                self.postgres.close()
                _close_logger.info("clients.close.pg_closed")
        except Exception as e:
            _close_logger.error("clients.close.pg_FAILED", error=str(e))
        
        # Neo4j - Don't close driver (it's reused)
        # The neo4j driver handles connection pooling internally
        
        # Qdrant (HTTP or gRPC) - Just cleanup if needed
        try:
            if hasattr(self.qdrant, "_grpc_channel") and self.qdrant._grpc_channel:
                self.qdrant._grpc_channel.close()
        except Exception as e:
            _close_logger.debug("clients.close_warning", resource="qdrant", error=str(e))


# =============================================================================
# CACHED CLIENTS (Singletons for reuse)
# =============================================================================

_neo4j_driver: Optional[Driver] = None
_neo4j_lock = threading.Lock()

_qdrant_client: Optional[QdrantClient] = None
_qdrant_lock = threading.Lock()

_aoai_client: Optional[AzureOpenAI] = None
_aoai_lock = threading.Lock()

_embed_dims: Optional[int] = None


def _get_cached_neo4j(settings: AppSettings) -> Driver:
    """Get or create cached Neo4j driver with connection resilience.
    
    Key settings for Azure environments:
    - max_connection_lifetime: Close connections before Azure idle timeout (typically 4-5 min)
    - liveness_check_timeout: Verify connections are still alive before use
    - keep_alive: Enable TCP keepalive to detect dead connections faster
    """
    global _neo4j_driver
    
    if _neo4j_driver is not None:
        return _neo4j_driver
    
    with _neo4j_lock:
        if _neo4j_driver is not None:
            return _neo4j_driver
        
        _neo4j_driver = GraphDatabase.driver(
            settings.neo4j.uri,
            auth=(settings.neo4j.username, settings.neo4j.password),
            # Pool settings
            max_connection_pool_size=50,
            # Connection resilience - CRITICAL for Azure
            max_connection_lifetime=180,  # 3 minutes - shorter than Azure LB timeout (~5 min)
            connection_acquisition_timeout=10,  # Keep API endpoints responsive
            connection_timeout=10,  # Initial connection timeout
            # Retry settings
            max_transaction_retry_time=30.0,
            # Liveness check - verify connection is alive before use
            liveness_check_timeout=5,  # Check connection health if idle >5s
            # TCP keepalive for better failure detection
            keep_alive=True,
        )
        return _neo4j_driver


def reset_neo4j_driver() -> None:
    """Reset the cached Neo4j driver.
    
    Call this when 'Unable to retrieve routing information' or
    'defunct connection' errors occur to force recreation of the driver.
    """
    global _neo4j_driver
    import structlog
    _logger = structlog.get_logger("app.clients")
    
    with _neo4j_lock:
        if _neo4j_driver is not None:
            try:
                _neo4j_driver.close()
                _logger.info("neo4j.driver.reset.closed_old")
            except Exception as e:
                _logger.warning("neo4j.driver.reset.close_error", error=str(e))
        _neo4j_driver = None
        _logger.info("neo4j.driver.reset.complete")


def _get_cached_qdrant(settings: AppSettings) -> QdrantClient:
    """Get or create cached Qdrant client."""
    global _qdrant_client
    
    if _qdrant_client is not None:
        return _qdrant_client
    
    with _qdrant_lock:
        if _qdrant_client is not None:
            return _qdrant_client
        
        _qdrant_client = QdrantClient(url=settings.qdrant.uri, api_key=settings.qdrant.api_key)
        return _qdrant_client


def _get_cached_aoai(settings: AppSettings) -> AzureOpenAI:
    """Get or create cached Azure OpenAI client."""
    global _aoai_client
    
    if _aoai_client is not None:
        return _aoai_client
    
    with _aoai_lock:
        if _aoai_client is not None:
            return _aoai_client
        
        _aoai_client = _create_aoai_client(settings)
        return _aoai_client


# =============================================================================
# FUNCIONES DE CONSTRUCCIÓN
# =============================================================================

def build_service_clients(settings: AppSettings) -> ServiceClients:
    """
    Construye e inicializa todos los clientes de servicios externos.
    
    Esta es la función principal para obtener conexiones a todos los servicios.
    Maneja la autenticación para cada servicio y valida que las conexiones
    sean exitosas antes de retornar.
    
    OPTIMIZED: Uses connection pooling and cached clients for better performance.
    
    Args:
        settings: Configuración de la aplicación cargada desde .env
        
    Returns:
        ServiceClients con todas las conexiones inicializadas
        
    Raises:
        Exception: Si algún servicio no puede ser conectado
    """
    global _embed_dims
    
    # 1. Cliente Azure OpenAI (cached)
    aoai = _get_cached_aoai(settings)
    
    # 2. Cliente Qdrant (cached)
    qdrant = _get_cached_qdrant(settings)
    
    # 3. Driver Neo4j (cached - has internal connection pooling)
    neo4j_driver = _get_cached_neo4j(settings)
    
    # 4. Conexión PostgreSQL (from pool)
    pg_conn = get_pg_connection(settings)

    # 5. Inferir dimensiones de embeddings si no están configuradas (cached)
    if _embed_dims is None:
        _embed_dims = settings.embed_dims or _infer_embed_dims(aoai, settings.azure.deployment_embed)

    return ServiceClients(
        aoai=aoai,
        qdrant=qdrant,
        neo4j=neo4j_driver,
        postgres=pg_conn,
        embed_dims=_embed_dims,
        _uses_pool=True,
    )



def _create_aoai_client(settings: AppSettings) -> AzureOpenAI:
    """
    Crea el cliente de Azure OpenAI con autenticación apropiada.
    
    Soporta dos modos de autenticación:
    1. API Key: Usa la key directamente si está configurada
    2. DefaultAzureCredential: Usa autenticación basada en roles (RBAC)
       cuando no hay API key (útil para Managed Identity)
    
    Args:
        settings: Configuración de la aplicación
        
    Returns:
        Cliente AzureOpenAI configurado
    """
    azure = settings.azure
    
    # Si hay API key, usar autenticación simple
    if azure.api_key:
        return AzureOpenAI(
            azure_endpoint=azure.endpoint,
            api_key=azure.api_key,
            api_version=azure.api_version,
        )

    # Fallback: Usar DefaultAzureCredential (RBAC/Managed Identity)
    scope = "https://cognitiveservices.azure.com/.default"
    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(credential, scope)
    return AzureOpenAI(
        azure_endpoint=azure.endpoint,
        azure_ad_token_provider=token_provider,
        api_version=azure.api_version,
    )


def _infer_embed_dims(aoai: AzureOpenAI, deployment: str) -> int:
    """
    Infiere las dimensiones del modelo de embeddings mediante una petición de prueba.
    
    Esto se usa cuando EMBED_DIMS no está configurada en el .env.
    Genera un embedding de prueba y cuenta las dimensiones del vector resultante.
    
    Args:
        aoai: Cliente de Azure OpenAI
        deployment: Nombre del deployment de embeddings
        
    Returns:
        Número de dimensiones del modelo (ej: 3072 para text-embedding-3-large)
    """
    response = aoai.embeddings.create(model=deployment, input="ping")
    return len(response.data[0].embedding)
