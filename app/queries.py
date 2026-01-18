"""
Consultas híbridas (semánticas + BM25) sobre el corpus.

Este módulo implementa el sistema de búsqueda híbrida que combina:
1. Búsqueda semántica: Similitud de embeddings vectoriales (Qdrant)
2. Búsqueda BM25: Ranking textual clásico (PostgreSQL ts_rank_cd)

Funciones principales:
    - semantic_search(): Búsqueda híbrida principal
    - graph_counts(): Conteo de fragmentos por entrevista (Neo4j)
    - sample_postgres(): Muestreo de fragmentos recientes
    - run_cypher(): Ejecutar consultas Cypher arbitrarias

Parámetros de búsqueda:
    - top_k: Número de resultados a retornar
    - use_hybrid: Activar combinación con BM25 (default: True)
    - bm25_weight: Peso del componente BM25 (default: 0.35)
    - score_threshold: Umbral mínimo de relevancia

Estrategia de scoring:
    score_final = (semantic_score * (1 - bm25_weight)) + (bm25_score * bm25_weight)

Fallback:
    Si no hay resultados para speaker específico, intenta sin filtro de speaker.

Example:
    >>> from app.queries import semantic_search
    >>> results = semantic_search(
    ...     clients, settings,
    ...     query="adaptación al cambio climático",
    ...     top_k=5,
    ...     project="mi_proyecto"
    ... )
    >>> for r in results:
    ...     print(f"{r['score']:.3f}: {r['fragmento'][:50]}...")
"""

from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, cast

import structlog

try:
    from neo4j.graph import Node, Relationship, Path  # type: ignore
except ImportError:  # pragma: no cover
    Node = Relationship = Path = None  # type: ignore
from qdrant_client.models import FieldCondition, Filter, MatchValue

from .clients import ServiceClients
from .settings import AppSettings

_logger = structlog.get_logger()


def semantic_search(
    clients: ServiceClients,
    settings: AppSettings,
    query: str,
    top_k: int = 5,
    project: Optional[str] = None,
    speaker: Optional[str] = "interviewee",
    use_hybrid: bool = True,
    bm25_weight: float = 0.35,
    score_threshold: float = 0.0,
) -> List[Dict[str, Any]]:
    start = time.perf_counter()
    project_id = project or "default"
    
    # Embedding creation with logging
    embed_start = time.perf_counter()
    vector = clients.aoai.embeddings.create(model=settings.azure.deployment_embed, input=query).data[0].embedding
    _logger.info(
        "embedding.create",
        model=settings.azure.deployment_embed,
        input_chars=len(query),
        elapsed_ms=round((time.perf_counter() - embed_start) * 1000, 2),
    )
    q_filter = _build_project_filter(project_id, speaker)
    qdrant_limit = max(top_k * 3, 10)
    response = clients.qdrant.query_points(
        collection_name=settings.qdrant.collection,
        query=vector,
        limit=qdrant_limit,
        with_payload=True,
        query_filter=q_filter,
    )
    if speaker and not response.points:
        q_filter = _build_project_filter(project_id, None)
        response = clients.qdrant.query_points(
            collection_name=settings.qdrant.collection,
            query=vector,
            limit=qdrant_limit,
            with_payload=True,
            query_filter=q_filter,
        )

    combined: Dict[str, Dict[str, Any]] = {}
    for point in response.points:
        payload = point.payload or {}
        fragment_id = str(point.id)
        combined[fragment_id] = {
            "fragmento_id": fragment_id,
            "score": point.score,
            "semantic_score": point.score,
            "bm25_score": 0.0,
            "archivo": payload.get("archivo"),
            "par_idx": payload.get("par_idx"),
            "char_len": payload.get("char_len"),
            "fragmento": payload.get("fragmento"),
            "speaker": payload.get("speaker"),
        }

    if use_hybrid:
        bm25_weight = min(max(bm25_weight, 0.0), 1.0)
        bm25_candidates = _bm25_search(clients.postgres, query, project_id, speaker, limit=qdrant_limit)
        max_rank = max((item["bm25_raw"] for item in bm25_candidates), default=0.0)
        for item in bm25_candidates:
            fid = item["fragmento_id"]
            bm25_norm = (item["bm25_raw"] / max_rank) if max_rank else 0.0
            existing = combined.get(fid)
            if existing:
                existing["bm25_score"] = bm25_norm
            else:
                combined[fid] = {
                    "fragmento_id": fid,
                    "score": bm25_norm,
                    "semantic_score": 0.0,
                    "bm25_score": bm25_norm,
                    "archivo": item["archivo"],
                    "par_idx": item["par_idx"],
                    "char_len": item["char_len"],
                    "fragmento": item["fragmento"],
                    "speaker": item.get("speaker"),
                }
        for item in combined.values():
            semantic = item.get("semantic_score") or 0.0
            bm25_score = item.get("bm25_score") or 0.0
            item["score"] = (semantic * (1 - bm25_weight)) + (bm25_score * bm25_weight)

    results = sorted(combined.values(), key=lambda entry: entry.get("score", 0.0), reverse=True)
    if score_threshold > 0:
        results = [r for r in results if r.get("score", 0.0) >= score_threshold]
    
    final_results = results[:top_k]
    _logger.info(
        "search.semantic.complete",
        project=project_id,
        query_preview=query[:50],
        top_k=top_k,
        results=len(final_results),
        use_hybrid=use_hybrid,
        elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
    )
    return final_results


def _build_project_filter(project_id: str, speaker: Optional[str]) -> Filter:
    must = [FieldCondition(key="project_id", match=MatchValue(value=project_id))]
    must_not: List[FieldCondition] = []
    if speaker:
        must.append(FieldCondition(key="speaker", match=MatchValue(value=speaker)))
    else:
        must_not.append(FieldCondition(key="speaker", match=MatchValue(value="interviewer")))
    return Filter(must=cast(List[Any], must), must_not=cast(List[Any], must_not) or None)


def _bm25_search(pg_conn, query: str, project_id: str, speaker: Optional[str], limit: int) -> List[Dict[str, Any]]:
    sql = """
        SELECT id,
               archivo,
               par_idx,
               char_len,
               fragmento,
               speaker,
               ts_rank_cd(to_tsvector('spanish', fragmento), plainto_tsquery('spanish', %s)) AS rank
         FROM entrevista_fragmentos
         WHERE project_id = %s
           AND (%s IS NULL OR speaker = %s OR speaker IS NULL)
         ORDER BY rank DESC
         LIMIT %s
    """
    with pg_conn.cursor() as cur:
        cur.execute(sql, (query, project_id, speaker, speaker, limit))
        rows = cur.fetchall()
    results: List[Dict[str, Any]] = []
    for row in rows:
        fragmento_id, archivo, par_idx, char_len, fragmento, speaker_val, rank = row
        results.append(
            {
                "fragmento_id": fragmento_id,
                "archivo": archivo,
                "par_idx": par_idx,
                "char_len": char_len,
                "fragmento": fragmento,
                "speaker": speaker_val,
                "bm25_raw": rank,
            }
        )
    return results


def graph_counts(clients: ServiceClients, settings: AppSettings, project: Optional[str]) -> List[Dict[str, Any]]:
    start = time.perf_counter()
    query = """
        MATCH (e:Entrevista {project_id: $project_id})-[:TIENE_FRAGMENTO]->(f:Fragmento {project_id: $project_id})
        WHERE coalesce(f.speaker, 'interviewee') <> 'interviewer'
        RETURN e.nombre AS entrevista, count(f) AS cantidad
        ORDER BY cantidad DESC
    """
    with clients.neo4j.session(database=settings.neo4j.database) as session:
        data = session.run(query, project_id=project or "default").data()
    _logger.info(
        "neo4j.graph_counts.complete",
        project=project or "default",
        rows=len(data),
        elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
    )
    return data


def sample_postgres(clients: ServiceClients, project: Optional[str], limit: int = 3) -> List[Dict[str, Any]]:
    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            SELECT id, archivo, par_idx, char_len, fragmento
              FROM entrevista_fragmentos
             WHERE project_id = %s
               AND (speaker IS NULL OR speaker <> 'interviewer')
             ORDER BY updated_at DESC
             LIMIT %s
            """,
            (project or "default", limit),
        )
        rows = cur.fetchall()
    return [
        {
            "fragmento_id": row[0],
            "archivo": row[1],
            "par_idx": row[2],
            "char_len": row[3],
            "fragmento": row[4],
        }
        for row in rows
    ]


# Cypher guardrails
ALLOWED_CYPHER_VERBS = {"MATCH", "RETURN", "WITH", "WHERE", "ORDER", "LIMIT", "OPTIONAL", "UNWIND", "CALL"}
BLOCKED_CYPHER_PATTERNS = {"apoc.", "dbms.", "DELETE", "DETACH", "DROP", "CREATE", "MERGE", "SET", "REMOVE"}


def run_cypher(
    clients: ServiceClients,
    cypher: str,
    params: Optional[Dict[str, Any]] = None,
    database: Optional[str] = None,
    max_rows: int = 500,
    fetch_size: int = 100,
) -> Dict[str, Any]:
    """
    Ejecuta consultas Cypher con guardrails de seguridad.
    
    Security:
        - Whitelist de verbos permitidos (MATCH, RETURN, etc.)
        - Blocklist de patrones peligrosos (DELETE, DROP, apoc.*)
        - LIMIT automático si no presente
        - Fetch size para streaming
        - Timeout de 30s
    
    Args:
        clients: ServiceClients
        cypher: Consulta Cypher
        params: Parámetros de la consulta
        database: Base de datos Neo4j
        max_rows: Máximo de filas a retornar (default 500)
        fetch_size: Tamaño de batch para streaming
        
    Returns:
        Dict con raw, table, graph
        
    Raises:
        ValueError: Si la consulta usa verbos o patrones bloqueados
    """
    start = time.perf_counter()
    
    # Whitelist check
    first_word = cypher.strip().split()[0].upper() if cypher.strip() else ""
    if first_word not in ALLOWED_CYPHER_VERBS:
        raise ValueError(f"Cypher debe comenzar con verbo permitido: {ALLOWED_CYPHER_VERBS}")
    
    # Blocklist check
    cypher_upper = cypher.upper()
    for pattern in BLOCKED_CYPHER_PATTERNS:
        if pattern.upper() in cypher_upper:
            raise ValueError(f"Patrón bloqueado detectado: {pattern}")
    
    # LIMIT wrapper: si no tiene LIMIT, envolver en CALL {} con RETURN *
    if "LIMIT" not in cypher_upper:
        cleaned = cypher.rstrip().rstrip(";")
        cypher = f"CALL {{ {cleaned} }} RETURN * LIMIT {max_rows}"
    
    session_kwargs: Dict[str, Any] = {"fetch_size": fetch_size}
    if database:
        session_kwargs["database"] = database
    
    with clients.neo4j.session(**session_kwargs) as session:
        result = session.run(cypher, parameters=params or {}, timeout=30.0)
        records = list(result)

    raw_rows = [_record_to_dict(record) for record in records]
    columns = _collect_columns(records)
    table_rows = [
        [_convert_value(record.get(column)) for column in columns]
        for record in records
    ]
    nodes, relationships = _extract_graph_components(records)
    
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    
    _logger.info(
        "neo4j.query.complete",
        cypher_preview=cypher[:80].replace("\n", " "),
        records=len(records),
        database=database,
        elapsed_ms=elapsed_ms,
    )
    
    # Slow query detection
    if elapsed_ms > 500:
        _logger.warning(
            "neo4j.query.slow",
            cypher_preview=cypher[:120].replace("\n", " "),
            records=len(records),
            database=database,
            elapsed_ms=elapsed_ms,
        )
    
    return {
        "raw": raw_rows,
        "table": {"columns": columns, "rows": table_rows},
        "graph": {"nodes": nodes, "relationships": relationships},
    }



def _collect_columns(records: Sequence[Any]) -> List[str]:
    columns: List[str] = []
    for record in records:
        for key in getattr(record, "keys", lambda: [])():
            if key not in columns:
                columns.append(key)
    return columns


def _record_to_dict(record: Any) -> Dict[str, Any]:
    return {key: _convert_value(value) for key, value in getattr(record, "items", lambda: [])()}


def _convert_value(value: Any) -> Any:
    if _is_node(value):
        return _node_to_dict(value)
    if _is_relationship(value):
        return _relationship_to_dict(value)
    if _is_path(value):
        nodes = [_node_to_dict(node) for node in getattr(value, "nodes", [])]
        rels = [_relationship_to_dict(rel) for rel in getattr(value, "relationships", [])]
        return {"nodes": nodes, "relationships": rels}
    if isinstance(value, dict):
        return {key: _convert_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_convert_value(item) for item in value]
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        try:
            return iso()
        except Exception:  # pragma: no cover - fallback if isoformat fails
            pass
    return value


def _extract_graph_components(records: Sequence[Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    node_map: Dict[Any, Dict[str, Any]] = {}
    rel_map: Dict[Any, Dict[str, Any]] = {}

    def visit(item: Any) -> None:
        if _is_node(item):
            descriptor = _node_to_dict(item)
            node_map[descriptor["id"]] = descriptor
        elif _is_relationship(item):
            descriptor = _relationship_to_dict(item)
            rel_map[descriptor["id"]] = descriptor
            visit(getattr(item, "start_node", None))
            visit(getattr(item, "end_node", None))
        elif _is_path(item):
            for node in getattr(item, "nodes", []):
                visit(node)
            for rel in getattr(item, "relationships", []):
                visit(rel)
        elif isinstance(item, dict):
            for value in item.values():
                visit(value)
        elif isinstance(item, (list, tuple, set)):
            for value in item:
                visit(value)

    for record in records:
        if hasattr(record, "values"):
            values: Iterable[Any] = record.values()
        else:
            values = []
        for value in values:
            visit(value)

    return list(node_map.values()), list(rel_map.values())


def _node_to_dict(node: Any) -> Dict[str, Any]:
    labels = list(getattr(node, "labels", []))
    properties = _coerce_properties(node)
    return {
        "id": getattr(node, "id", None),
        "labels": labels,
        "properties": properties,
    }


def _relationship_to_dict(rel: Any) -> Dict[str, Any]:
    properties = _coerce_properties(rel)
    start_node = getattr(rel, "start_node", None)
    end_node = getattr(rel, "end_node", None)
    return {
        "id": getattr(rel, "id", None),
        "type": getattr(rel, "type", None),
        "start": getattr(start_node, "id", None),
        "end": getattr(end_node, "id", None),
        "properties": properties,
    }


def _coerce_properties(value: Any) -> Dict[str, Any]:
    if hasattr(value, "items"):
        try:
            return {key: _convert_value(val) for key, val in value.items()}
        except Exception:
            pass
    data = getattr(value, "__dict__", {})
    if data:
        return {key: _convert_value(val) for key, val in data.items() if not key.startswith("_")}
    return {}


def _is_node(value: Any) -> bool:
    if value is None:
        return False
    if Node and isinstance(value, Node):  # type: ignore[arg-type]
        return True
    return hasattr(value, "labels") and hasattr(value, "id") and hasattr(value, "__iter__")


def _is_relationship(value: Any) -> bool:
    if value is None:
        return False
    if Relationship and isinstance(value, Relationship):  # type: ignore[arg-type]
        return True
    return (
        hasattr(value, "type")
        and hasattr(value, "start_node")
        and hasattr(value, "end_node")
        and hasattr(value, "__iter__")
    )


def _is_path(value: Any) -> bool:
    if value is None:
        return False
    if Path and isinstance(value, Path):  # type: ignore[arg-type]
        return True
    return hasattr(value, "nodes") and hasattr(value, "relationships")


def discover_search(
    clients: ServiceClients,
    settings: AppSettings,
    positive_texts: List[str],
    negative_texts: Optional[List[str]] = None,
    target_text: Optional[str] = None,
    top_k: int = 10,
    project: Optional[str] = None,
    use_native_first: bool = True,
) -> List[Dict[str, Any]]:
    """
    Búsqueda exploratoria con estrategia híbrida (Nativo + Fallback).
    
    Estrategia:
    1. Buscar IDs de fragmentos representativos para conceptos positivos/negativos
    2. Si hay IDs suficientes, usar Discovery API nativo de Qdrant (más preciso)
    3. Si no hay IDs, usar fallback de vectores ponderados (más flexible)
    
    Args:
        clients: Clientes de servicios
        settings: Configuración
        positive_texts: Textos/conceptos positivos (buscar similares)
        negative_texts: Textos/conceptos negativos (evitar similares)
        target_text: Texto objetivo opcional para explorar
        top_k: Número de resultados
        project: ID del proyecto
        use_native_first: Intentar API nativo primero (default: True)
        
    Returns:
        Lista de fragmentos ordenados por relevancia exploratoria
        
    Example:
        >>> # "Conflicto" en contexto "Instituciones", no "Familia"
        >>> results = discover_search(
        ...     clients, settings,
        ...     positive_texts=["conflicto institucional", "junta de vecinos"],
        ...     negative_texts=["conflicto familiar", "hogar"],
        ...     target_text="violencia",
        ...     top_k=10
        ... )
    """
    import numpy as np
    from qdrant_client.models import ContextExamplePair
    
    project_id = project or "default"
    start = time.perf_counter()
    
    # =========================================================================
    # PASO 1: Generar embeddings para todos los textos
    # =========================================================================
    
    positive_vectors = []
    for text in positive_texts:
        try:
            emb = clients.aoai.embeddings.create(
                model=settings.azure.deployment_embed,
                input=text
            ).data[0].embedding
            positive_vectors.append(emb)
        except Exception as e:
            _logger.warning("discover.embed_error", text=text[:30], error=str(e))
    
    if not positive_vectors:
        return []
    
    negative_vectors = []
    if negative_texts:
        for text in negative_texts:
            try:
                emb = clients.aoai.embeddings.create(
                    model=settings.azure.deployment_embed,
                    input=text
                ).data[0].embedding
                negative_vectors.append(emb)
            except Exception as e:
                _logger.warning("discover.embed_error", text=text[:30], error=str(e))
    
    target_vector = None
    if target_text:
        try:
            target_vector = clients.aoai.embeddings.create(
                model=settings.azure.deployment_embed,
                input=target_text
            ).data[0].embedding
        except Exception as e:
            _logger.warning("discover.embed_error", text=target_text[:30], error=str(e))
    
    q_filter = _build_project_filter(project_id, None)
    
    # =========================================================================
    # PASO 2: Intentar Discovery API Nativo (si use_native_first=True)
    # =========================================================================
    
    # Umbral de calidad para anclas - evita envenenar búsqueda con fragmentos irrelevantes
    ANCHOR_QUALITY_THRESHOLD = 0.55  # Score mínimo para considerar ancla válida
    
    if use_native_first:
        try:
            # Buscar IDs representativos para conceptos positivos CON VALIDACIÓN
            positive_ids = []
            positive_scores = []
            weak_anchors = []
            
            for i, vec in enumerate(positive_vectors):
                response = clients.qdrant.query_points(
                    collection_name=settings.qdrant.collection,
                    query=vec,
                    limit=1,
                    with_payload=False,
                    query_filter=q_filter,
                )
                if response.points:
                    point = response.points[0]
                    score = point.score
                    
                    # CONTROL DE CALIDAD: solo usar anclas con score suficiente
                    if score >= ANCHOR_QUALITY_THRESHOLD:
                        positive_ids.append(str(point.id))
                        positive_scores.append(score)
                    else:
                        weak_anchors.append({
                            "concept": positive_texts[i][:30] if i < len(positive_texts) else "?",
                            "score": round(score, 3),
                        })
            
            # Log si hubo anclas débiles rechazadas
            if weak_anchors:
                _logger.warning(
                    "discover.weak_anchors_rejected",
                    count=len(weak_anchors),
                    threshold=ANCHOR_QUALITY_THRESHOLD,
                    details=weak_anchors,
                )
            
            # Buscar IDs representativos para conceptos negativos CON VALIDACIÓN
            negative_ids = []
            negative_scores = []
            
            for i, vec in enumerate(negative_vectors):
                response = clients.qdrant.query_points(
                    collection_name=settings.qdrant.collection,
                    query=vec,
                    limit=1,
                    with_payload=False,
                    query_filter=q_filter,
                )
                if response.points:
                    point = response.points[0]
                    score = point.score
                    
                    # También validar anclas negativas
                    if score >= ANCHOR_QUALITY_THRESHOLD:
                        negative_ids.append(str(point.id))
                        negative_scores.append(score)
                    # No logueamos negativos débiles, es menos crítico
            
            # Si tenemos al menos 1 positivo VÁLIDO, podemos usar Discovery nativo
            if positive_ids:
                avg_pos_score = sum(positive_scores) / len(positive_scores)
                
                _logger.info(
                    "discover.using_native",
                    positive_ids=len(positive_ids),
                    negative_ids=len(negative_ids),
                    avg_positive_score=round(avg_pos_score, 3),
                    threshold=ANCHOR_QUALITY_THRESHOLD,
                )

                
                # Construir pares de contexto
                context_pairs = []
                for i, pos_id in enumerate(positive_ids):
                    # Emparejar con negativo si existe, sino solo positivo
                    neg_id = negative_ids[i] if i < len(negative_ids) else None
                    if neg_id:
                        context_pairs.append(
                            ContextExamplePair(positive=pos_id, negative=neg_id)
                        )
                    else:
                        # Solo positivo (Qdrant acepta esto)
                        context_pairs.append(
                            ContextExamplePair(positive=pos_id, negative=None)
                        )
                
                # Agregar negativos restantes emparejados con el primer positivo
                if len(negative_ids) > len(positive_ids):
                    for neg_id in negative_ids[len(positive_ids):]:
                        context_pairs.append(
                            ContextExamplePair(positive=positive_ids[0], negative=neg_id)
                        )
                
                # Llamar a Discovery API nativo
                from qdrant_client.models import Filter, FieldCondition, MatchValue
                
                native_filter = Filter(must=[
                    FieldCondition(key="project_id", match=MatchValue(value=project_id))
                ])
                
                response = clients.qdrant.discover(
                    collection_name=settings.qdrant.collection,
                    target=list(target_vector) if target_vector else None,
                    context=context_pairs,
                    limit=top_k,
                    query_filter=native_filter,
                )
                
                results = []
                for point in response:
                    payload = point.payload or {}
                    results.append({
                        "fragmento_id": str(point.id),
                        "score": point.score,
                        "archivo": payload.get("archivo"),
                        "par_idx": payload.get("par_idx"),
                        "fragmento": payload.get("fragmento"),
                        "speaker": payload.get("speaker"),
                        "discovery_type": "native",
                    })
                
                _logger.info(
                    "discover.native.complete",
                    positive_count=len(positive_texts),
                    negative_count=len(negative_texts or []),
                    results=len(results),
                    project=project_id,
                    elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
                )
                
                return results
                
        except Exception as e:
            _logger.warning(
                "discover.native.failed_fallback",
                error=str(e),
                reason="Using weighted vector fallback",
            )
    
    # =========================================================================
    # PASO 3: Fallback - Búsqueda con vectores ponderados
    # =========================================================================
    
    _logger.info("discover.using_fallback", reason="weighted vector search")
    
    try:
        # Calcular vector promedio de positivos
        avg_positive = np.mean(positive_vectors, axis=0).tolist()
        
        # Si hay negativos, ajustar el vector
        if negative_vectors:
            avg_negative = np.mean(negative_vectors, axis=0).tolist()
            # Vector = positivo - 0.3 * negativo
            query_vector = [
                p - 0.3 * n for p, n in zip(avg_positive, avg_negative)
            ]
        else:
            query_vector = avg_positive
        
        # Si hay target, combinarlo
        if target_vector:
            query_vector = [
                0.7 * q + 0.3 * t for q, t in zip(query_vector, target_vector)
            ]
        
        response = clients.qdrant.query_points(
            collection_name=settings.qdrant.collection,
            query=query_vector,
            limit=top_k,
            with_payload=True,
            query_filter=q_filter,
        )
    except Exception as e:
        _logger.error("discover.fallback.error", error=str(e))
        return []
    
    # Procesar resultados
    results = []
    for point in response.points:
        payload = point.payload or {}
        results.append({
            "fragmento_id": str(point.id),
            "score": point.score,
            "archivo": payload.get("archivo"),
            "par_idx": payload.get("par_idx"),
            "fragmento": payload.get("fragmento"),
            "speaker": payload.get("speaker"),
            "discovery_type": "fallback",
        })
    
    _logger.info(
        "discover.fallback.complete",
        positive_count=len(positive_texts),
        negative_count=len(negative_texts or []),
        results=len(results),
        project=project_id,
        elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
    )
    
    return results

