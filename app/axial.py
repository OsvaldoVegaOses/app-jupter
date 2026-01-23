"""
Codificación axial para análisis cualitativo.

La codificación axial es una técnica de la Teoría Fundamentada (Grounded Theory)
que agrupa códigos abiertos en categorías y establece relaciones entre ellos.

Este módulo implementa:
1. Asignación de relaciones entre categorías y códigos
2. Validación de evidencia (fragmentos que soportan la relación)
3. Persistencia en Neo4j y PostgreSQL
4. Detección de comunidades usando algoritmo Louvain

Flujo de trabajo:
    Códigos Abiertos → Agrupación → Categorías Axiales → Relaciones → Neo4j
    
Tipos de relación (ALLOWED_REL_TYPES):
    - "partede": Código pertenece a categoría (jerárquico)
    - "causa": Código A causa/origina Código B
    - "condicion": Código A condiciona Código B  
    - "consecuencia": Código A es resultado de Código B

Clases:
    - AxialError: Error específico de operaciones axiales

Funciones principales:
    - assign_axial_relation(): Asigna código a categoría con validación
    - detect_louvain_categories(): Detecta categorías automáticamente
    - build_category_network(): Construye grafo NetworkX de relaciones

Requisitos de evidencia:
    Por defecto, se requieren al menos 2 fragmentos únicos para validar
    una relación axial (configurable).

Example:
    >>> from app.axial import assign_axial_relation
    >>> assign_axial_relation(
    ...     clients, settings,
    ...     codigo="adaptacion_climatica",
    ...     categoria="resiliencia_comunitaria",
    ...     relacion="partede",
    ...     evidencias=["frag_001", "frag_002"],
    ...     memo="Códigos relacionados con adaptación ante el cambio climático",
    ...     project="mi_proyecto"
    ... )
"""

from __future__ import annotations

from typing import Dict, List, Optional
from uuid import uuid4

import structlog
import networkx as nx
from networkx.algorithms.community import louvain_communities
from neo4j.exceptions import ClientError

from .clients import ServiceClients
from .settings import AppSettings
from .neo4j_block import (
    ensure_category_constraints,
    ensure_code_constraints,
    merge_category_code_relationship,
)
from .postgres_block import (
    coded_fragments_for_code,
    ensure_axial_table,
    ensure_open_coding_table,
    fetch_fragment_by_id,
    upsert_axial_relationships,
    get_code_id_for_codigo,
    resolve_canonical_code_id,
    check_axial_ready,
)


class AxialError(Exception):
    """Error específico para operaciones de codificación axial."""


class AxialNotReadyError(Exception):
    """Error cuando la infraestructura ontológica no está lista para axialidad.
    
    Se lanza cuando `check_axial_ready()` retorna False, indicando que
    hay problemas estructurales que deben resolverse antes de operar.
    
    Attributes:
        blocking_reasons: Lista de razones de bloqueo (ej: 'missing_code_id')
        project_id: ID del proyecto afectado
    """
    def __init__(self, project_id: str, blocking_reasons: List[str]):
        self.project_id = project_id
        self.blocking_reasons = blocking_reasons
        message = (
            f"Proyecto '{project_id}' no está listo para operaciones axiales. "
            f"Razones de bloqueo: {', '.join(blocking_reasons)}. "
            f"Use GET /api/admin/code-id/status para diagnóstico."
        )
        super().__init__(message)


# Tipos de relación válidos para codificación axial
ALLOWED_REL_TYPES = {"causa", "condicion", "consecuencia", "partede"}

_logger = structlog.get_logger()


def _validate_evidence(pg_conn, codigo: str, evidencias: List[str], project: Optional[str]) -> List[str]:
    unique = list(dict.fromkeys(evidencias))
    if len(unique) < 2:
        raise AxialError("Se requieren al menos dos fragmentos unicos en la evidencia.")

    missing = [fid for fid in unique if not fetch_fragment_by_id(pg_conn, fid, project)]
    if missing:
        raise AxialError(f"Fragmentos inexistentes en PostgreSQL: {', '.join(missing)}")

    coded_map = coded_fragments_for_code(pg_conn, codigo, unique, project)
    not_coded = [fid for fid, ok in coded_map.items() if not ok]
    if not_coded:
        raise AxialError(
            "Los siguientes fragmentos no estan codificados con ese codigo abierto: "
            + ", ".join(not_coded)
        )
    return unique


def assign_axial_relation(
    clients: ServiceClients,
    settings: AppSettings,
    categoria: str,
    codigo: str,
    relacion: str,
    evidencia: List[str],
    memo: Optional[str] = None,
    project: Optional[str] = None,
    logger: Optional[structlog.BoundLogger] = None,
    skip_axial_ready_check: bool = False,
) -> Dict[str, object]:
    log = logger or _logger
    project_id = project or "default"
    
    # Gate: verificar axial_ready antes de proceder
    if not skip_axial_ready_check:
        axial_ready, blocking_reasons = check_axial_ready(clients.postgres, project_id)
        if not axial_ready:
            log.warning(
                "axial.blocked",
                project_id=project_id,
                blocking_reasons=blocking_reasons,
                operation="assign_axial_relation",
            )
            raise AxialNotReadyError(project_id, blocking_reasons)
    
    rel_tipo = relacion.lower().strip()
    ensure_open_coding_table(clients.postgres)
    from app.postgres_block import ensure_codes_catalog_table, resolve_canonical_codigo

    ensure_codes_catalog_table(clients.postgres)
    original_codigo = codigo
    codigo = resolve_canonical_codigo(clients.postgres, project_id, codigo)
    
    # Obtener code_id del código canónico para identidad estable
    code_id = get_code_id_for_codigo(clients.postgres, project_id, codigo)
    if code_id is not None:
        # Resolver al canónico por ID (más robusto que por texto)
        canonical_code_id = resolve_canonical_code_id(clients.postgres, project_id, code_id)
        if canonical_code_id is not None and canonical_code_id != code_id:
            # El código fue mergeado, usar el canónico
            code_id = canonical_code_id
            log.debug("axial.resolved_canonical_id", original_code_id=code_id, canonical_code_id=canonical_code_id)
    
    if codigo and original_codigo and codigo.strip().lower() != str(original_codigo).strip().lower():
        # Keep UX/audit context without changing the contract.
        prefix = f"[CANON:{codigo}; ORIG:{str(original_codigo).strip()}] "
        memo = f"{prefix}{memo}" if memo else prefix.strip()
    if rel_tipo not in ALLOWED_REL_TYPES:
        raise AxialError(
            f"Tipo de relacion '{relacion}' invalido. Debe ser uno de: {', '.join(sorted(ALLOWED_REL_TYPES))}."
        )

    evidence_ids = _validate_evidence(clients.postgres, codigo, evidencia, project_id)

    fragments = [fetch_fragment_by_id(clients.postgres, fid, project_id) for fid in evidence_ids]
    archivo = fragments[0]["archivo"] if fragments else ""

    ensure_axial_table(clients.postgres)
    ensure_category_constraints(clients.neo4j, settings.neo4j.database)
    ensure_code_constraints(clients.neo4j, settings.neo4j.database)

    upsert_axial_relationships(
        clients.postgres,
        [
            (
                project_id,
                categoria,
                codigo,
                rel_tipo,
                archivo,
                memo,
                evidence_ids,
            )
        ],
    )

    merge_category_code_relationship(
        clients.neo4j,
        settings.neo4j.database,
        categoria=categoria,
        codigo=codigo,
        relacion=rel_tipo,
        evidencia=evidence_ids,
        memo=memo,
        project_id=project_id,
        code_id=code_id,
    )

    payload = {
        "categoria": categoria,
        "codigo": codigo,
        "relacion": rel_tipo,
        "memo": memo,
        "evidencia": evidence_ids,
        "code_id": code_id,
    }
    log.info("axial.relate", **payload)
    return payload


def _run_native_graph_analysis(
    session,
    algorithm: str,
    persist: bool,
    project_id: str,
) -> List[Dict[str, object]]:
    """Fallback implementation using NetworkX when GDS is not available.
    
    IMPORTANTE: Filtra por project_id para garantizar aislamiento entre proyectos.
    """
    _logger.info("gds.fallback_native", algorithm=algorithm, project_id=project_id)

    # 1. Fetch Graph - FILTRADO POR PROJECT_ID
    # Solo obtenemos nodos/relaciones del proyecto activo
    q = """
    MATCH (s)-[:REL]->(t)
    WHERE s.project_id = $project_id AND t.project_id = $project_id
      AND (NOT 'Codigo' IN labels(s) OR coalesce(s.status,'active') <> 'merged')
      AND (NOT 'Codigo' IN labels(t) OR coalesce(t.status,'active') <> 'merged')
    RETURN elementId(s) as sid, s.nombre as sname, labels(s) as slabels,
           elementId(t) as tid, t.nombre as tname, labels(t) as tlabels
    """
    try:
        data = session.run(q, project_id=project_id).data()
    except Exception:
        # Fallback for older Neo4j vs elementId
        q = """
        MATCH (s)-[:REL]->(t)
        WHERE s.project_id = $project_id AND t.project_id = $project_id
          AND (NOT 'Codigo' IN labels(s) OR coalesce(s.status,'active') <> 'merged')
          AND (NOT 'Codigo' IN labels(t) OR coalesce(t.status,'active') <> 'merged')
        RETURN id(s) as sid, s.nombre as sname, labels(s) as slabels,
               id(t) as tid, t.nombre as tname, labels(t) as tlabels
        """
        data = session.run(q, project_id=project_id).data()
        
    G = nx.DiGraph()
    # Map ID to props
    node_props = {}
    
    for row in data:
        sid, tid = str(row["sid"]), str(row["tid"])
        G.add_edge(sid, tid)
        if sid not in node_props:
            node_props[sid] = {"nombre": row["sname"], "etiquetas": row["slabels"]}
        if tid not in node_props:
            node_props[tid] = {"nombre": row["tname"], "etiquetas": row["tlabels"]}
            
    results = []
    
    # 2. Run Algorithm
    updates = [] # List of {id: ..., val: ...}
    
    if algorithm == "pagerank":
        # NetworkX PageRank
        scores = nx.pagerank(G) # dict {id: score}
        sorted_nodes = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        results = [
            {
                "nombre": node_props[nid]["nombre"],
                "etiquetas": node_props[nid]["etiquetas"],
                "score": score
            }
            for nid, score in sorted_nodes
        ]
        if persist:
            updates = [{"id": nid, "val": score} for nid, score in scores.items()]
            prop_name = "score_centralidad"

    elif algorithm == "louvain":
        # Louvain (undirected usually better for community, convert)
        GU = G.to_undirected()
        communities = louvain_communities(GU) # list of sets
        results = []
        updates = []
        for idx, comm in enumerate(communities):
            for nid in comm:
                if nid in node_props:
                    results.append({
                        "nombre": node_props[nid]["nombre"],
                        "etiquetas": node_props[nid]["etiquetas"],
                        "community_id": idx
                    })
                    updates.append({"id": nid, "val": idx})
        results.sort(key=lambda x: (x["community_id"], x["nombre"]))
        prop_name = "community_id"
        
    # 3. Persist
    if persist and updates:
        # Batch update
        # Using ElementId needs specific match, using WHERE elementId(n) = $id
        # We try to be compatible.
        
        # Check if we have integer IDs or string ElementIds
        sample_id = updates[0]["id"]
        is_int_id = isinstance(sample_id, int) or (isinstance(sample_id, str) and sample_id.isdigit())
        
        if is_int_id:
             match_clause = "WHERE id(n) = toInteger(row.id)"
        else:
             match_clause = "WHERE elementId(n) = row.id"

        batch_query = (
            f"UNWIND $batch as row "
            f"MATCH (n) {match_clause} "
            f"SET n.{prop_name} = row.val"
        )
        
        # Split into chunks of 1000
        chunk_size = 1000
        for i in range(0, len(updates), chunk_size):
            batch = updates[i:i+chunk_size]
            session.run(batch_query, batch=batch).consume()
            
    return results


def run_gds_analysis(
    clients: ServiceClients,
    settings: AppSettings,
    algorithm: str,
    persist: bool = False,
    project: str | None = None,
) -> List[Dict[str, object]]:
    """Ejecuta análisis de grafo usando el wrapper unificado GraphAlgorithms.
    
    Este método es un wrapper de compatibilidad que delega al nuevo módulo
    graph_algorithms.py, el cual detecta automáticamente el motor disponible
    (Neo4j GDS / Memgraph MAGE / NetworkX).
    
    IMPORTANTE: Filtra por project_id para garantizar aislamiento.
    
    Args:
        clients: ServiceClients
        settings: AppSettings
        algorithm: louvain, pagerank, betweenness, o leiden
        persist: Si True, persiste resultados como propiedades
        project: ID del proyecto (requerido para aislamiento)
        
    Returns:
        Lista de resultados del algoritmo
    """
    from .graph_algorithms import GraphAlgorithms
    
    algo = algorithm.lower()
    if algo not in {"louvain", "pagerank", "betweenness", "leiden"}:
        raise AxialError("Algoritmo no soportado. Usa louvain, pagerank, betweenness o leiden.")
    
    project_id = project or "default"
    
    # Usar el nuevo wrapper unificado
    ga = GraphAlgorithms(clients, settings)
    
    _logger.info("run_gds_analysis.using_wrapper", 
                 algorithm=algo, 
                 engine=ga.engine.value,
                 project_id=project_id)

    # Delegar al wrapper unificado
    if algo == "louvain":
        return ga.louvain(project_id, persist=persist)
    elif algo == "pagerank":
        return ga.pagerank(project_id, persist=persist)
    elif algo == "betweenness":
        return ga.betweenness(project_id, persist=persist)
    elif algo == "leiden":
        return ga.leiden(project_id, persist=persist)
    else:
        raise AxialError(f"Algoritmo no soportado: {algo}")
