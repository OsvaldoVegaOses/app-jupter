"""
Configuración de la aplicación mediante variables de entorno.

Este módulo define las dataclasses de configuración para todos los servicios externos
y proporciona la función `load_settings()` para cargar la configuración desde .env.

Servicios configurables:
    - Azure OpenAI: Embeddings y análisis LLM
    - Qdrant: Base de datos vectorial para búsqueda semántica
    - Neo4j: Base de datos de grafos para relaciones axiales
    - PostgreSQL: Base de datos relacional para códigos y proyectos

Uso:
    from app.settings import load_settings
    
    settings = load_settings()  # Carga desde .env
    settings = load_settings("ruta/a/.env.local")  # Carga desde archivo específico
    
    # Acceso seguro para logs (oculta credentials)
    print(settings.masked())

Variables de entorno soportadas (ver README.md para lista completa):
    - AZURE_OPENAI_*, QDRANT_*, NEO4J_*, POSTGRES_* o PG*
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv, find_dotenv


# =============================================================================
# DATACLASSES DE CONFIGURACIÓN
# =============================================================================

@dataclass
class AzureSettings:
    """
    Configuración para Azure OpenAI.
    
    Attributes:
        endpoint: URL del endpoint de Azure OpenAI (ej: https://eastus2.api.cognitive.microsoft.com/)
        api_key: API key para autenticación (opcional si usa DefaultAzureCredential)
        api_version: Versión de la API (ej: 2024-02-15-preview)
        deployment_embed: Nombre del deployment para embeddings (ej: text-embedding-3-large)
        deployment_chat: Nombre del deployment para chat/análisis (modelo correcto gpt-5.2-chat)
        deployment_chat_mini: Deployment alternativo para tareas ligeras (opcional)
        deployment_transcribe: Deployment para transcripción simple (gpt-4o-transcribe)
        deployment_transcribe_diarize: Deployment para transcripción con diarización (gpt-4o-transcribe-diarize)
        transcribe_api_version: Versión de API para transcripción (2025-03-01-preview)
    """
    endpoint: str
    api_key: Optional[str]
    api_version: str
    deployment_embed: str
    deployment_chat: str
    deployment_chat_mini: Optional[str] = None
    # Audio transcription deployments
    deployment_transcribe: Optional[str] = None
    deployment_transcribe_diarize: Optional[str] = None
    transcribe_api_version: str = "2025-03-01-preview"

    def masked(self) -> "AzureSettings":
        """Retorna una copia con credentials enmascaradas para logging seguro."""
        return AzureSettings(
            endpoint=self.endpoint,
            api_key=mask(self.api_key),
            api_version=self.api_version,
            deployment_embed=self.deployment_embed,
            deployment_chat=self.deployment_chat,
            deployment_chat_mini=self.deployment_chat_mini,
            deployment_transcribe=self.deployment_transcribe,
            deployment_transcribe_diarize=self.deployment_transcribe_diarize,
            transcribe_api_version=self.transcribe_api_version,
        )


@dataclass
class QdrantSettings:
    """
    Configuración para Qdrant (base de datos vectorial).
    
    Attributes:
        uri: URL del servidor Qdrant (local o cloud)
        api_key: API key para Qdrant Cloud (opcional para local)
        collection: Nombre de la colección para fragmentos
        timeout: Timeout en segundos para operaciones upsert (default: 30)
        batch_size: Número máximo de puntos por batch (default: 20, reducido para evitar timeouts)
    """
    uri: str
    api_key: Optional[str]
    collection: str
    timeout: int = 30  # segundos para operaciones upsert
    batch_size: int = 20  # puntos máximos por batch (reducido de 64 para evitar timeouts)

    def masked(self) -> "QdrantSettings":
        """Retorna una copia con credentials enmascaradas para logging seguro."""
        return QdrantSettings(self.uri, mask(self.api_key), self.collection, self.timeout, self.batch_size)


@dataclass
class Neo4jSettings:
    """
    Configuración para Neo4j (base de datos de grafos).
    
    Usado para almacenar relaciones axiales entre códigos y categorías.
    
    Attributes:
        uri: URI de conexión (bolt:// para local, neo4j+s:// para Aura)
        username: Usuario de Neo4j (default: neo4j)
        password: Contraseña
        database: Nombre de la base de datos (default: neo4j)
    """
    uri: str
    username: str
    password: Optional[str]
    database: str

    def masked(self) -> "Neo4jSettings":
        """Retorna una copia con credentials enmascaradas para logging seguro."""
        return Neo4jSettings(self.uri, self.username, mask(self.password), self.database)


@dataclass
class PostgresSettings:
    """
    Configuración para PostgreSQL.
    
    Usado para almacenar códigos abiertos, proyectos, y resultados de análisis.
    
    Attributes:
        host: Host del servidor
        port: Puerto (default: 5432)
        username: Usuario
        password: Contraseña
        database: Nombre de la base de datos
    """
    host: str
    port: int
    username: str
    password: Optional[str]
    database: str
    sslmode: str = "prefer"

    def masked(self) -> "PostgresSettings":
        """Retorna una copia con credentials enmascaradas para logging seguro."""
        return PostgresSettings(
            host=self.host,
            port=self.port,
            username=self.username,
            password=mask(self.password),
            database=self.database,
            sslmode=self.sslmode,
        )


@dataclass
class AppSettings:
    """
    Configuración consolidada de toda la aplicación.
    
    Agrupa todas las sub-configuraciones de servicios externos más
    configuraciones globales de la aplicación.
    
    Attributes:
        azure: Configuración de Azure OpenAI
        qdrant: Configuración de Qdrant
        neo4j: Configuración de Neo4j
        postgres: Configuración de PostgreSQL
        embed_dims: Dimensiones del modelo de embeddings (se infiere si no se especifica)
        api_key: API key para autenticación de la API REST (opcional)
    """
    azure: AzureSettings
    qdrant: QdrantSettings
    neo4j: Neo4jSettings
    postgres: PostgresSettings
    embed_dims: Optional[int]
    api_key: Optional[str]

    def masked(self) -> "AppSettings":
        """Retorna una copia con todas las credentials enmascaradas para logging seguro."""
        return AppSettings(
            azure=self.azure.masked(),
            qdrant=self.qdrant.masked(),
            neo4j=self.neo4j.masked(),
            postgres=self.postgres.masked(),
            embed_dims=self.embed_dims,
            api_key=mask(self.api_key),
        )


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def mask(value: Optional[str], prefix: int = 4) -> str:
    """
    Enmascara un valor sensible para logging seguro.
    
    Args:
        value: Valor a enmascarar (puede ser None)
        prefix: Número de caracteres a mostrar al inicio y final
        
    Returns:
        String enmascarado (ej: "3b43...f703")
        
    Example:
        >>> mask("mi-api-key-secreta-12345")
        'mi-a...2345'
    """
    if not value:
        return "****"
    if len(value) <= prefix * 2:
        return "****"
    return f"{value[:prefix]}...{value[-prefix:]}"


def load_settings(env_file: Optional[str | os.PathLike[str]] = None) -> AppSettings:
    """
    Carga la configuración desde variables de entorno.
    
    Busca un archivo .env en el directorio actual o usa el archivo especificado.
    Las variables existentes en el entorno tienen precedencia si override=True.
    
    Args:
        env_file: Ruta opcional al archivo .env. Si no se especifica,
                  busca automáticamente en el directorio actual.
                  
    Returns:
        AppSettings con toda la configuración cargada
        
    Raises:
        ValueError: Si alguna configuración requerida está ausente
        
    Example:
        >>> settings = load_settings()
        >>> print(settings.azure.endpoint)
        'https://eastus2.api.cognitive.microsoft.com/'
        
    Note:
        PostgreSQL soporta tanto variables POSTGRES_* como PG* por compatibilidad
        con diferentes convenciones de nombres.
    """
    # Cargar archivo .env
    if env_file:
        load_dotenv(env_file, override=True)
    else:
        dotenv_path = find_dotenv(usecwd=True)
        if dotenv_path:
            load_dotenv(dotenv_path, override=True)

    # Azure OpenAI
    azure = AzureSettings(
        endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        # Support both naming conventions: DEPLOYMENT_EMBED and EMBEDDING_DEPLOYMENT
        deployment_embed=os.getenv("AZURE_OPENAI_DEPLOYMENT_EMBED") or os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large"),
        # Support both naming conventions: DEPLOYMENT_CHAT and CHAT_DEPLOYMENT
        deployment_chat=os.getenv("AZURE_OPENAI_DEPLOYMENT_CHAT") or os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-5-2-chat"),
        deployment_chat_mini=os.getenv("AZURE_OPENAI_CHAT_MINI_DEPLOYMENT") or os.getenv("AZURE_DEPLOYMENT_GPT5_MINI"),
        # Audio transcription deployments
        deployment_transcribe=os.getenv("AZURE_OPENAI_DEPLOYMENT_TRANSCRIBE"),
        deployment_transcribe_diarize=os.getenv("AZURE_OPENAI_DEPLOYMENT_TRANSCRIBE_DIARIZE"),
        transcribe_api_version=os.getenv("AZURE_OPENAI_TRANSCRIBE_API_VERSION", "2025-03-01-preview"),
    )

    # Qdrant (vectores)
    qdrant = QdrantSettings(
        uri=os.getenv("QDRANT_URI", "http://localhost:6333"),
        api_key=os.getenv("QDRANT_API_KEY"),
        collection=os.getenv("QDRANT_COLLECTION", "fragmentos"),
        timeout=int(os.getenv("QDRANT_TIMEOUT", "30")),
        batch_size=int(os.getenv("QDRANT_BATCH_SIZE", "20")),
    )

    # Neo4j (grafo)
    neo4j = Neo4jSettings(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        username=os.getenv("NEO4J_USERNAME", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD"),
        database=os.getenv("NEO4J_DATABASE", "neo4j"),
    )

    # PostgreSQL (códigos y proyectos)
    # Soporta tanto POSTGRES_* como PG* para compatibilidad
    postgres = PostgresSettings(
        host=os.getenv("POSTGRES_HOST") or os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT") or os.getenv("PGPORT", "5432")),
        username=os.getenv("POSTGRES_USER") or os.getenv("PGUSER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD") or os.getenv("PGPASSWORD"),
        database=os.getenv("POSTGRES_DB") or os.getenv("PGDATABASE", "entrevistas"),
        sslmode=os.getenv("POSTGRES_SSLMODE") or os.getenv("PGSSLMODE", "prefer"),
    )

    # Dimensiones de embeddings (opcional, se infiere si no se especifica)
    embed_dims_raw = os.getenv("EMBED_DIMS")
    embed_dims = int(embed_dims_raw) if embed_dims_raw else None

    return AppSettings(
        azure=azure,
        qdrant=qdrant,
        neo4j=neo4j,
        postgres=postgres,
        embed_dims=embed_dims,
        api_key=os.getenv("API_KEY"),
    )
