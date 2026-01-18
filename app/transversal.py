"""
Análisis transversal multi-fuente.

Este módulo implementa análisis que cruzan datos de los tres backends:
PostgreSQL, Qdrant y Neo4j para obtener perspectivas integradas.

Tipos de análisis transversal:
    1. pg_cross_tab(): Tablas cruzadas desde vistas materializadas de PG
    2. qdrant_segment_probe(): Búsqueda semántica por segmentos/filtros
    3. neo4j_subgraph_summary(): Resúmenes de subgrafos por atributo
    4. build_dashboard_payload(): Agregación completa para dashboards

Atributos soportados para segmentación:
    - actor_principal: Por tipo de actor entrevistado
    - genero: Por género del participante
    - periodo: Por período temporal

Uso típico:
    El endpoint de dashboard llama a build_dashboard_payload() para
    obtener datos integrados de las tres fuentes en una sola respuesta.

Example:
    >>> from app.transversal import build_dashboard_payload
    >>> data = build_dashboard_payload(
    ...     clients, settings,
    ...     dimension="archivo",
    ...     categoria="resiliencia",
    ...     prompt="adaptación climática",
    ...     segments=[{"name": "pescadores", "filters": {"actor_principal": "pescador"}}],
    ...     attribute="actor_principal",
    ...     values=["pescador", "agricultor"],
    ... )
"""

from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional, Sequence

import structlog

from .clients import ServiceClients
from .settings import AppSettings
from .postgres_block import (
    ensure_transversal_views,
    fetch_cross_tab,
    refresh_transversal_views,
)
from .nucleus import probe_semantics

_logger = structlog.get_logger()


def pg_cross_tab(
    clients: ServiceClients,
    dimension: str,
    categoria: Optional[str] = None,
    *,
    project: Optional[str] = None,
    limit: int = 50,
    refresh: bool = False,
    logger: Optional[structlog.BoundLogger] = None,
) -> Dict[str, Any]:
    project_id = project or "default"
    log = (logger or _logger).bind(source="pg_cross_tab", dimension=dimension, project=project_id)
    ensure_transversal_views(clients.postgres, project_id)
    if refresh:
        log.info("transversal.pg.refresh")
        refresh_transversal_views(clients.postgres)
    start = time.perf_counter()
    rows = fetch_cross_tab(clients.postgres, dimension, categoria, limit, project=project_id)
    latency = time.perf_counter() - start
    log.info("transversal.pg.rows", returned=len(rows), latency=latency)
    return {
        "dimension": dimension,
        "categoria": categoria,
        "limit": limit,
        "rows": rows,
        "latency_seconds": latency,
    }


def qdrant_segment_probe(
    clients: ServiceClients,
    settings: AppSettings,
    prompt: str,
    segments: Sequence[Dict[str, Any]],
    *,
    project: Optional[str] = None,
    top_k: int = 10,
    logger: Optional[structlog.BoundLogger] = None,
) -> Dict[str, Any]:
    project_id = project or "default"
    log = (logger or _logger).bind(source="qdrant_segment_probe", project=project_id)
    results: List[Dict[str, Any]] = []
    interview_sets: List[set[str]] = []

    for segment in segments:
        name = segment.get("name") or segment.get("label") or "segment"
        filters = segment.get("filters") or {}
        start = time.perf_counter()
        points = probe_semantics(
            clients,
            settings,
            prompt=prompt,
            top_k=top_k,
            filters=filters,
            project=project_id,
        )
        duration = time.perf_counter() - start
        entrevistas = sorted({p.get("archivo") for p in points if p.get("archivo")})
        interview_sets.append(set(entrevistas))
        results.append(
            {
                "segment": name,
                "filters": filters,
                "latency_seconds": duration,
                "total": len(points),
                "entrevistas": entrevistas,
                "points": points,
            }
        )
        log.info(
            "transversal.qdrant.segment",
            segment=name,
            filters=filters,
            resultados=len(points),
            latency=duration,
        )

    shared: List[str] = []
    if interview_sets:
        shared = sorted(set.intersection(*interview_sets)) if len(interview_sets) > 1 else sorted(interview_sets[0])

    return {
        "prompt": prompt,
        "top_k": top_k,
        "segments": results,
        "entrevistas_compartidas": shared,
    }


_ALLOWED_ATTRIBUTES = {"actor_principal", "genero", "periodo"}


def _attribute_condition(attribute: str) -> str:
    if attribute == "actor_principal":
        return "coalesce(e.actor_principal, '(sin actor)') = $value"
    if attribute == "genero":
        return "coalesce(e.genero, '(sin genero)') = $value"
    if attribute == "periodo":
        return "coalesce(e.periodo, '(sin periodo)') = $value"
    raise ValueError(f"Atributo no soportado: {attribute}")


def neo4j_subgraph_summary(
    clients: ServiceClients,
    settings: AppSettings,
    attribute: str,
    value: str,
    *,
    project: Optional[str] = None,
    limit: int = 10,
    logger: Optional[structlog.BoundLogger] = None,
) -> Dict[str, Any]:
    attr = attribute.lower()
    if attr not in _ALLOWED_ATTRIBUTES:
        raise ValueError(f"Atributo no soportado: {attribute}")

    condition = _attribute_condition(attr)
    project_id = project or "default"
    log = (logger or _logger).bind(source="neo4j_subgraph", attribute=attr, value=value, project=project_id)

    summary_query = f"""
        MATCH (e:Entrevista {{project_id: $project_id}})-[:TIENE_FRAGMENTO]->(f:Fragmento {{project_id: $project_id}})
        WHERE {condition}
        WITH DISTINCT f
        OPTIONAL MATCH (f)-[:TIENE_CODIGO]->(cod:Codigo {{project_id: $project_id}})
        OPTIONAL MATCH (cat:Categoria {{project_id: $project_id}})-[rel:REL]->(cod)
        RETURN count(DISTINCT f) AS fragmentos,
               count(DISTINCT cod) AS codigos,
               count(DISTINCT cat) AS categorias,
               count(DISTINCT rel) AS relaciones
    """

    edges_query = f"""
        MATCH (e:Entrevista {{project_id: $project_id}})-[:TIENE_FRAGMENTO]->(f:Fragmento {{project_id: $project_id}})
        WHERE {condition}
        MATCH (f)-[:TIENE_CODIGO]->(cod:Codigo {{project_id: $project_id}})
        MATCH (cat:Categoria {{project_id: $project_id}})-[rel:REL]->(cod)
        RETURN cat.nombre AS categoria,
               rel.tipo AS relacion,
               COUNT(*) AS total,
               collect(DISTINCT cod.nombre)[0..5] AS codigos
        ORDER BY total DESC
        LIMIT $limit
    """

    start = time.perf_counter()
    with clients.neo4j.session(database=settings.neo4j.database) as session:
        summary_record = session.run(summary_query, value=value, project_id=project_id).single() or {}
        edge_records = session.run(edges_query, value=value, project_id=project_id, limit=limit).data()
    latency = time.perf_counter() - start

    summary_payload = {
        "fragmentos": summary_record.get("fragmentos", 0),
        "codigos": summary_record.get("codigos", 0),
        "categorias": summary_record.get("categorias", 0),
        "relaciones": summary_record.get("relaciones", 0),
    }
    edges_payload = [
        {
            "categoria": row.get("categoria"),
            "relacion": row.get("relacion"),
            "total": row.get("total", 0),
            "codigos": row.get("codigos", []),
        }
        for row in edge_records
    ]

    log.info(
        "transversal.neo4j.summary",
        fragmentos=summary_payload["fragmentos"],
        relaciones=summary_payload["relaciones"],
        latency=latency,
    )

    return {
        "attribute": attr,
        "value": value,
        "latency_seconds": latency,
        "summary": summary_payload,
        "top_relaciones": edges_payload,
    }


def neo4j_multi_summary(
    clients: ServiceClients,
    settings: AppSettings,
    attribute: str,
    values: Sequence[str],
    *,
    project: Optional[str] = None,
    limit: int = 10,
    logger: Optional[structlog.BoundLogger] = None,
) -> Dict[str, Any]:
    summaries = [
        neo4j_subgraph_summary(clients, settings, attribute, value, project=project, limit=limit, logger=logger)
        for value in values
    ]
    return {"attribute": attribute, "values": summaries, "limit": limit}


def build_dashboard_payload(
    clients: ServiceClients,
    settings: AppSettings,
    *,
    dimension: str,
    categoria: Optional[str],
    prompt: str,
    segments: Sequence[Dict[str, Any]],
    attribute: str,
    values: Sequence[str],
    project: Optional[str] = None,
    top_k: int = 10,
    limit: int = 10,
    refresh_views: bool = False,
) -> Dict[str, Any]:
    project_id = project or "default"
    pg_data = pg_cross_tab(
        clients,
        dimension,
        categoria,
        project=project_id,
        limit=limit,
        refresh=refresh_views,
    )
    qdrant_data = qdrant_segment_probe(
        clients,
        settings,
        prompt,
        segments,
        project=project_id,
        top_k=top_k,
    )
    neo4j_data = neo4j_multi_summary(
        clients,
        settings,
        attribute,
        values,
        project=project_id,
        limit=limit,
    )
    return {
        "postgres": pg_data,
        "qdrant": qdrant_data,
        "neo4j": neo4j_data,
    }
