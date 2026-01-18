"""
Operaciones de base de datos vectorial Qdrant.

Este módulo encapsula todas las operaciones con Qdrant para almacenamiento
y búsqueda de embeddings de fragmentos de entrevistas.

Funciones principales:
    - ensure_collection(): Crea/verifica colección con dimensiones correctas
    - ensure_payload_indexes(): Crea índices para filtrado eficiente
    - build_points(): Construye puntos con payload canónico
    - upsert(): Inserta puntos con retry automático y splitting
    - search_similar(): Búsqueda KNN básica
    - discover_search(): Búsqueda con contexto positivo/negativo

Campos de payload canónicos (CANONICAL_PAYLOAD_FIELDS):
    - project_id: Identificador del proyecto
    - archivo: Nombre del archivo origen
    - par_idx: Índice del fragmento
    - fragmento: Texto del fragmento
    - speaker: interviewer | interviewee
    - area_tematica, actor_principal: Metadatos de clasificación
    - codigos_ancla: Códigos iniciales asignados

Características de resiliencia:
    - Retry con exponential backoff (máx 3 intentos)
    - Splitting automático de batches en caso de timeout
    - Logging de latencia para diagnóstico de rendimiento

Configuración recomendada (desde settings.py):
    - QDRANT_BATCH_SIZE=20 (reducido de 64 para evitar timeouts)
    - QDRANT_TIMEOUT=30 segundos

Example:
    >>> from app.qdrant_block import upsert, build_points
    >>> points = build_points(ids, payloads, vectors)
    >>> upsert(client, "fragmentos", points)
"""

from __future__ import annotations

from typing import Any, Iterable, List, Mapping, Sequence, Optional

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams, ContextExamplePair
from tenacity import retry, stop_after_attempt, wait_exponential


# Campos que siempre se incluyen en el payload de cada punto
# Estos campos se utilizan para filtrado y agrupación
CANONICAL_PAYLOAD_FIELDS = (
    "project_id",        # Identificador del proyecto (multitenancy)
    "archivo",           # Nombre del archivo fuente
    "par_idx",           # Índice del fragmento dentro del archivo
    "fragmento",         # Texto completo del fragmento
    "char_len",          # Longitud en caracteres
    "speaker",           # Rol: interviewer | interviewee
    "interviewer_tokens",  # Tokens del entrevistador en este fragmento
    "interviewee_tokens",  # Tokens del entrevistado en este fragmento
    "area_tematica",     # Área temática clasificada
    "actor_principal",   # Actor principal mencionado
    "requiere_protocolo_lluvia",  # Flag para protocolos especiales
    "genero",            # Género del entrevistado
    "periodo",           # Período temporal de referencia
    "codigos_ancla",     # Códigos iniciales asignados
    "metadata",          # Metadatos adicionales
)

_logger = structlog.get_logger()


def ensure_collection(client: QdrantClient, name: str, dimensions: int, distance: Distance = Distance.COSINE) -> None:
    """Ensure the Qdrant collection exists with the expected vector size."""
    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dimensions, distance=distance),
        )
        return

    info = client.get_collection(name)
    config = info.config.params.vectors
    size = getattr(config, "size", None)
    if size is None and isinstance(config, dict):
        size = config.get("size")
    if size and size != dimensions:
        raise ValueError(f"Collection '{name}' has size={size}, expected {dimensions}")


def ensure_payload_indexes(client: QdrantClient, name: str) -> None:
    """Create payload indexes for common filters if they do not exist."""
    index_specs = (
        ("project_id", "keyword"),
        ("archivo", "keyword"),
        ("speaker", "keyword"),
        ("area_tematica", "keyword"),
        ("actor_principal", "keyword"),
        ("genero", "keyword"),
        ("periodo", "keyword"),
        ("codigos_ancla", "keyword"),
        ("fragmento", "text"),
    )
    for field_name, schema in index_specs:
        try:
            client.create_payload_index(
                collection_name=name,
                field_name=field_name,
                field_schema=schema,
            )
        except Exception as exc:  # noqa: BLE001 - surface unexpected errors
            message = str(exc).lower()
            if "already exists" in message or "already has index" in message:
                continue
            raise


def build_points(
    ids: Sequence[str],
    payloads: Sequence[Mapping[str, Any]],
    vectors: Sequence[Sequence[float]],
) -> List[PointStruct]:
    points: List[PointStruct] = []
    for _id, payload, vector in zip(ids, payloads, vectors):
        enriched_payload = {field: payload.get(field) for field in CANONICAL_PAYLOAD_FIELDS}
        points.append(
            PointStruct(
                id=str(_id),
                vector=list(vector),
                payload=enriched_payload,
            )
        )
    return points


import time

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=30), reraise=True)
def _upsert_once(
    client: QdrantClient,
    collection: str,
    points: List[PointStruct],
    logger: Optional[structlog.BoundLogger] = None,
) -> None:
    """Upsert points with retry logic and latency tracking."""
    log = logger or _logger
    start = time.time()
    client.upsert(collection_name=collection, points=points)
    elapsed_ms = (time.time() - start) * 1000
    log.info(
        "qdrant.upsert.success",
        count=len(points),
        elapsed_ms=round(elapsed_ms, 2),
    )


def upsert(
    client: QdrantClient,
    collection: str,
    points: Iterable[PointStruct],
    logger: Optional[structlog.BoundLogger] = None,
) -> None:
    point_list = list(points)
    if not point_list:
        return

    log = logger or _logger
    try:
        _upsert_once(client, collection, point_list, logger=log)
    except Exception as exc:
        if len(point_list) <= 1:
            log.error("qdrant.upsert.failure", error=str(exc), size=len(point_list))
            raise
        midpoint = max(1, len(point_list) // 2)
        log.warning("qdrant.upsert.split", size=len(point_list), reason=str(exc))
        upsert(client, collection, point_list[:midpoint], logger=log)
        upsert(client, collection, point_list[midpoint:], logger=log)


def search_similar(
    client: QdrantClient,
    collection: str,
    vector: Sequence[float],
    limit: int = 5,
    score_threshold: float = 0.5,
    project_id: str = None,
    exclude_interviewer: bool = False,
    **kwargs: Any,
) -> List[Any]:
    """
    KNN Search con aislamiento por proyecto.
    
    Args:
        client: Cliente Qdrant
        collection: Nombre de la colección
        vector: Vector de búsqueda
        limit: Máximo de resultados (capped a 100)
        score_threshold: Umbral mínimo de score (sanitizado 0-1)
        project_id: ID del proyecto (requerido para aislamiento)
        exclude_interviewer: Excluir fragmentos del entrevistador
        **kwargs: Parámetros adicionales para client.search
    
    Returns:
        Lista de resultados de búsqueda
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    # Sanitize parameters
    safe_limit = min(max(1, limit), 100)
    safe_threshold = max(0.0, min(1.0, score_threshold))
    
    # Project isolation: warn if no project_id provided
    if not project_id:
        _logger.warning(
            "qdrant.search_similar.no_project_id",
            msg="project_id not provided - using 'default'. This may cause cross-project leakage.",
        )
        project_id = "default"
    
    # Build filter
    must_conditions = [
        FieldCondition(key="project_id", match=MatchValue(value=project_id))
    ]
    must_not_conditions = []
    
    if exclude_interviewer:
        must_not_conditions.append(
            FieldCondition(key="speaker", match=MatchValue(value="interviewer"))
        )
    
    if must_conditions or must_not_conditions:
        kwargs["query_filter"] = Filter(
            must=must_conditions if must_conditions else None,
            must_not=must_not_conditions if must_not_conditions else None,
        )
    
    _logger.info(
        "qdrant.search_similar",
        project_id=project_id,
        limit=safe_limit,
        score_threshold=safe_threshold,
        exclude_interviewer=exclude_interviewer,
    )
    
    return client.search(
        collection_name=collection,
        query_vector=list(vector),
        limit=safe_limit,
        score_threshold=safe_threshold,
        **kwargs,
    )


def discover_search(
    client: QdrantClient,
    collection: str,
    target: Optional[Sequence[float]],
    context: List[ContextExamplePair],
    limit: int = 10,
    project_id: str = None,
    **kwargs: Any,
) -> List[Any]:
    """
    Qdrant Discovery API con aislamiento por proyecto.
    
    Args:
        client: Cliente Qdrant
        collection: Nombre de la colección
        target: Vector objetivo (puede ser None)
        context: Lista de pares positivo/negativo
        limit: Máximo de resultados (capped a 100)
        project_id: ID del proyecto (requerido para aislamiento)
        **kwargs: Parámetros adicionales
    
    Returns:
        Lista de resultados de búsqueda
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    # Sanitize limit
    safe_limit = min(max(1, limit), 100)
    
    # Project isolation: warn if no project_id provided
    if not project_id:
        _logger.warning(
            "qdrant.discover_search.no_project_id",
            msg="project_id not provided - using 'default'. This may cause cross-project leakage.",
        )
        project_id = "default"
    
    # Build project filter (always applied)
    kwargs["query_filter"] = Filter(must=[
        FieldCondition(key="project_id", match=MatchValue(value=project_id))
    ])
    
    _logger.info(
        "qdrant.discover_search",
        project_id=project_id,
        limit=safe_limit,
        context_pairs=len(context),
    )
    
    return client.discover(
        collection_name=collection,
        target=list(target) if target else None,
        context=context,
        limit=safe_limit,
        **kwargs,
    )


def search_similar_grouped(
    client: QdrantClient,
    collection: str,
    vector: Sequence[float],
    limit: int = 10,
    group_by: str = "archivo",
    group_size: int = 2,
    score_threshold: float = 0.5,
    project_id: str = None,
    exclude_interviewer: bool = False,
    # Filtros avanzados (Payload Filtering)
    genero: str = None,
    actor_principal: str = None,
    area_tematica: str = None,
    periodo: str = None,
    archivo_filter: str = None,
    **kwargs: Any,
) -> List[Any]:
    """
    Búsqueda KNN con agrupación y filtros avanzados.
    
    Soporta filtrado demográfico para Comparación Constante entre grupos.
    
    Args:
        client: Cliente Qdrant
        collection: Nombre de la colección
        vector: Vector de búsqueda
        limit: Máximo de grupos a retornar
        group_by: Campo para agrupar ("archivo" | "speaker" | "actor_principal")
        group_size: Máximo de resultados por grupo
        score_threshold: Umbral mínimo de score
        project_id: ID del proyecto
        exclude_interviewer: Excluir fragmentos del entrevistador
        genero: Filtrar por género (ej. "mujer", "hombre")
        actor_principal: Filtrar por rol (ej. "dirigente", "vecino")
        area_tematica: Filtrar por área temática
        periodo: Filtrar por periodo temporal
        archivo_filter: Filtrar por archivo específico
        **kwargs: Parámetros adicionales
    
    Returns:
        Lista de grupos con resultados
    
    Example:
        >>> # Buscar "miedo al cambio" solo en mujeres dirigentes
        >>> results = search_similar_grouped(
        ...     client, "fragmentos", vector,
        ...     genero="mujer", actor_principal="dirigente"
        ... )
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    # Sanitize parameters
    safe_limit = min(max(1, limit), 50)
    safe_group_size = min(max(1, group_size), 10)
    safe_threshold = max(0.0, min(1.0, score_threshold))
    
    # Validate group_by field
    valid_group_fields = {"archivo", "speaker", "actor_principal", "genero", "area_tematica"}
    if group_by not in valid_group_fields:
        _logger.warning(
            "qdrant.search_grouped.invalid_group_by",
            field=group_by,
            valid=list(valid_group_fields),
        )
        group_by = "archivo"
    
    # Project isolation
    if not project_id:
        _logger.warning(
            "qdrant.search_grouped.no_project_id",
            msg="project_id not provided - using 'default'.",
        )
        project_id = "default"
    
    # Build filter with all conditions
    must_conditions = [
        FieldCondition(key="project_id", match=MatchValue(value=project_id))
    ]
    must_not_conditions = []
    
    # Apply advanced filters
    if genero:
        must_conditions.append(
            FieldCondition(key="genero", match=MatchValue(value=genero))
        )
    if actor_principal:
        must_conditions.append(
            FieldCondition(key="actor_principal", match=MatchValue(value=actor_principal))
        )
    if area_tematica:
        must_conditions.append(
            FieldCondition(key="area_tematica", match=MatchValue(value=area_tematica))
        )
    if periodo:
        must_conditions.append(
            FieldCondition(key="periodo", match=MatchValue(value=periodo))
        )
    if archivo_filter:
        must_conditions.append(
            FieldCondition(key="archivo", match=MatchValue(value=archivo_filter))
        )
    
    if exclude_interviewer:
        must_not_conditions.append(
            FieldCondition(key="speaker", match=MatchValue(value="interviewer"))
        )
    
    query_filter = Filter(
        must=must_conditions if must_conditions else None,
        must_not=must_not_conditions if must_not_conditions else None,
    )
    
    _logger.info(
        "qdrant.search_similar_grouped",
        project_id=project_id,
        limit=safe_limit,
        group_by=group_by,
        group_size=safe_group_size,
        score_threshold=safe_threshold,
    )
    
    # Use Qdrant's search_groups API
    try:
        result = client.search_groups(
            collection_name=collection,
            query_vector=list(vector),
            group_by=group_by,
            limit=safe_limit,
            group_size=safe_group_size,
            score_threshold=safe_threshold,
            query_filter=query_filter,
            **kwargs,
        )
        return result.groups
    except Exception as e:
        _logger.error(
            "qdrant.search_grouped.error",
            error=str(e),
            msg="Falling back to regular search",
        )
        # Fallback to regular search
        return search_similar(
            client, collection, vector, 
            limit=safe_limit * safe_group_size,
            score_threshold=safe_threshold,
            project_id=project_id,
            exclude_interviewer=exclude_interviewer,
            **kwargs,
        )


def search_hybrid(
    client: QdrantClient,
    collection: str,
    query_text: str,
    vector: Sequence[float],
    limit: int = 10,
    score_threshold: float = 0.3,
    project_id: str = None,
    keyword_boost: float = 0.3,
    **kwargs: Any,
) -> List[Any]:
    """
    Búsqueda híbrida: semántica (dense) + texto exacto (keyword).
    
    Combina la potencia de embeddings para conceptos abstractos con
    la precisión de palabras clave para acrónimos y términos técnicos.
    
    Estrategia:
    1. Buscar por vector semántico (embeddings)
    2. Buscar fragmentos que contengan el texto exacto
    3. Fusionar resultados, boosteando los que match ambos
    
    Args:
        client: Cliente Qdrant
        collection: Nombre de la colección
        query_text: Texto de búsqueda (para keyword matching)
        vector: Vector de embeddings
        limit: Máximo de resultados
        score_threshold: Umbral mínimo
        project_id: ID del proyecto
        keyword_boost: Bonus de score para matches de keyword (0.0-1.0)
        **kwargs: Parámetros adicionales
    
    Returns:
        Lista de resultados fusionados
    
    Example:
        >>> # "Protocolo PAC en zonas rurales"
        >>> # Dense encuentra: "participación comunitaria"
        >>> # Keyword garantiza: fragmentos con "PAC" exacto
        >>> results = search_hybrid(client, col, "PAC rural", vector)
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchText
    
    # Sanitize parameters
    safe_limit = min(max(1, limit), 100)
    safe_threshold = max(0.0, min(1.0, score_threshold))
    safe_boost = max(0.0, min(1.0, keyword_boost))
    
    # Project isolation
    if not project_id:
        project_id = "default"
    
    project_filter = Filter(must=[
        FieldCondition(key="project_id", match=MatchValue(value=project_id))
    ])
    
    _logger.info(
        "qdrant.search_hybrid",
        project_id=project_id,
        query_text=query_text[:50],
        limit=safe_limit,
        keyword_boost=safe_boost,
    )
    
    # 1. Búsqueda semántica (dense vectors)
    semantic_results = client.search(
        collection_name=collection,
        query_vector=list(vector),
        limit=safe_limit,
        score_threshold=safe_threshold,
        query_filter=project_filter,
    )
    
    # 2. Búsqueda por texto exacto (keyword) - usa el índice de texto
    try:
        keyword_filter = Filter(must=[
            FieldCondition(key="project_id", match=MatchValue(value=project_id)),
            FieldCondition(key="fragmento", match=MatchText(text=query_text)),
        ])
        keyword_results = client.scroll(
            collection_name=collection,
            scroll_filter=keyword_filter,
            limit=safe_limit,
            with_payload=True,
            with_vectors=False,
        )[0]  # scroll returns (points, offset)
    except Exception as e:
        _logger.warning("qdrant.hybrid.keyword_search_failed", error=str(e))
        keyword_results = []
    
    # 3. Fusionar resultados
    # Crear mapa de IDs de keyword matches
    keyword_ids = {str(point.id) for point in keyword_results}
    
    # Boost score para los que matchean keyword
    final_results = []
    seen_ids = set()
    
    for result in semantic_results:
        result_id = str(result.id)
        if result_id in seen_ids:
            continue
        seen_ids.add(result_id)
        
        # Si también está en keyword results, aplicar boost
        if result_id in keyword_ids:
            # Ajustar score (capped a 1.0)
            boosted_score = min(1.0, result.score + safe_boost)
            result.score = boosted_score
        
        final_results.append(result)
    
    # Agregar keyword results que no estaban en semánticos (con score base)
    for point in keyword_results:
        point_id = str(point.id)
        if point_id not in seen_ids:
            seen_ids.add(point_id)
            # Crear objeto similar a ScoredPoint
            class KeywordResult:
                def __init__(self, p, base_score):
                    self.id = p.id
                    self.score = base_score  # Score base para keywords-only
                    self.payload = p.payload
            
            final_results.append(KeywordResult(point, safe_threshold + 0.1))
    
    # Ordenar por score descendente
    final_results.sort(key=lambda x: x.score, reverse=True)
    
    return final_results[:safe_limit]
