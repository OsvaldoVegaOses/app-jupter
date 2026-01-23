"""
Link Prediction: Prediccion de relaciones faltantes en el grafo.

Este modulo implementa algoritmos de prediccion de enlaces para sugerir
relaciones axiales que podrian estar faltando en el grafo de codificacion.

Algoritmos implementados:
    - common_neighbors: Vecinos comunes entre nodos
    - jaccard_coefficient: Coeficiente de Jaccard
    - adamic_adar: Indice de Adamic-Adar (vecinos ponderados)
    - preferential_attachment: Producto de grados

Casos de uso:
    - Sugerir que Codigo A deberia relacionarse con Categoria B
    - Identificar codigos que deberian agruparse
    - Detectar relaciones causales implicitas

Ejemplo:
    >>> from app.link_prediction import suggest_links
    >>> suggestions = suggest_links(
    ...     clients, settings,
    ...     source_type="Categoria",
    ...     target_type="Codigo",
    ...     algorithm="common_neighbors",
    ...     top_k=10
    ... )
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

import structlog

from .clients import ServiceClients
from .settings import AppSettings

_logger = structlog.get_logger()


def get_graph_data(
    clients: ServiceClients,
    settings: AppSettings,
    project: Optional[str] = None,
) -> Tuple[Dict[str, set], Dict[str, str]]:
    """
    Extrae el grafo como diccionario de adyacencia.
    
    Intenta Neo4j/Memgraph primero, con fallback a PostgreSQL si falla.
    
    Returns:
        Tuple[adjacency, node_types]:
            - adjacency: Dict[node_id, Set[neighbor_ids]]
            - node_types: Dict[node_id, node_label]
    """
    project_id = project or "default"
    
    # 1. Intentar Neo4j/Memgraph
    try:
        adjacency, node_types = _get_graph_data_from_neo4j(clients, settings, project_id)
        if adjacency:  # Si hay datos, usar Neo4j
            _logger.info("link_prediction.data_source", source="neo4j", nodes=len(node_types))
            return adjacency, node_types
    except Exception as e:
        _logger.warning("link_prediction.neo4j_failed", error=str(e)[:100])
    
    # 2. Fallback: PostgreSQL
    try:
        adjacency, node_types = _get_graph_data_from_postgres(clients.postgres, project_id)
        _logger.info("link_prediction.data_source", source="postgresql", nodes=len(node_types))
        return adjacency, node_types
    except Exception as e:
        _logger.error("link_prediction.postgres_fallback_failed", error=str(e)[:100])
    
    return {}, {}


def _get_graph_data_from_neo4j(
    clients: ServiceClients,
    settings: AppSettings,
    project_id: str,
) -> Tuple[Dict[str, set], Dict[str, str]]:
    """Extrae grafo desde Neo4j/Memgraph."""
    cypher = """
    MATCH (a)-[r]->(b)
    WHERE (a:Categoria OR a:Codigo) AND (b:Categoria OR b:Codigo)
      AND a.project_id = $project_id
    RETURN a.nombre AS source, labels(a)[0] AS source_type,
           b.nombre AS target, labels(b)[0] AS target_type,
           type(r) AS rel_type
    """
    
    adjacency = defaultdict(set)
    node_types = {}
    
    with clients.neo4j.session(database=settings.neo4j.database) as session:
        result = session.run(cypher, project_id=project_id)
        for record in result:
            source = record["source"]
            target = record["target"]
            
            adjacency[source].add(target)
            adjacency[target].add(source)  # Grafo no dirigido para prediccion
            
            node_types[source] = record["source_type"]
            node_types[target] = record["target_type"]
    
    return dict(adjacency), node_types


def _get_graph_data_from_postgres(
    pg,
    project_id: str,
) -> Tuple[Dict[str, set], Dict[str, str]]:
    """
    Construye grafo desde tablas PostgreSQL.
    
    Fuentes de datos:
    1. analisis_axial: Relaciones Categoria -> Codigo
    2. analisis_codigos_abiertos: Co-ocurrencias de códigos en fragmentos
    """
    adjacency = defaultdict(set)
    node_types = {}

    # Canonicalize codes so predictions don't learn from merged aliases.
    try:
        from app.postgres_block import ensure_codes_catalog_table, resolve_canonical_codigos_bulk

        ensure_codes_catalog_table(pg)
    except Exception:
        resolve_canonical_codigos_bulk = None  # type: ignore
    
    # 1. Obtener relaciones axiales (Categoria -> Codigo)
    with pg.cursor() as cur:
        cur.execute("""
            SELECT categoria, codigo, relacion 
            FROM analisis_axial 
            WHERE project_id = %s
        """, (project_id,))
        axial_rows = cur.fetchall() or []

    canon_map = {}
    if resolve_canonical_codigos_bulk is not None:
        unique_codes = {str(r[1]).strip() for r in axial_rows if r and r[1]}
        try:
            canon_map = resolve_canonical_codigos_bulk(pg, project_id, unique_codes)
        except Exception:
            canon_map = {}

    for cat, cod, rel in axial_rows:
        cod_s = str(cod).strip() if cod is not None else ""
        cod_c = canon_map.get(cod_s, cod_s)
        adjacency[cat].add(cod_c)
        adjacency[cod_c].add(cat)
        node_types[cat] = "Categoria"
        node_types[cod_c] = "Codigo"
    
    # 2. Obtener co-ocurrencias de códigos en fragmentos (códigos relacionados)
    with pg.cursor() as cur:
        cur.execute("""
            SELECT a.codigo, b.codigo, COUNT(*) as cooccurrences
            FROM analisis_codigos_abiertos a
            JOIN analisis_codigos_abiertos b 
              ON a.fragmento_id = b.fragmento_id 
              AND a.project_id = b.project_id
              AND a.codigo < b.codigo
            WHERE a.project_id = %s
            GROUP BY a.codigo, b.codigo
            HAVING COUNT(*) >= 2
        """, (project_id,))
        co_rows = cur.fetchall() or []

    if resolve_canonical_codigos_bulk is not None and co_rows:
        unique_codes2 = {str(c).strip() for r in co_rows for c in r[:2] if c}
        try:
            canon_map2 = resolve_canonical_codigos_bulk(pg, project_id, unique_codes2)
        except Exception:
            canon_map2 = {}
    else:
        canon_map2 = {}

    for cod1, cod2, count in co_rows:
        c1 = canon_map2.get(str(cod1).strip(), str(cod1).strip())
        c2 = canon_map2.get(str(cod2).strip(), str(cod2).strip())
        if not c1 or not c2 or c1.lower() == c2.lower():
            continue
        adjacency[c1].add(c2)
        adjacency[c2].add(c1)
        node_types.setdefault(c1, "Codigo")
        node_types.setdefault(c2, "Codigo")
    
    _logger.info(
        "link_prediction.postgres_graph", 
        nodes=len(node_types), 
        edges=sum(len(v) for v in adjacency.values()) // 2
    )
    
    return dict(adjacency), node_types


def common_neighbors(
    adjacency: Dict[str, set],
    node_a: str,
    node_b: str,
) -> int:
    """Calcula vecinos comunes entre dos nodos."""
    neighbors_a = adjacency.get(node_a, set())
    neighbors_b = adjacency.get(node_b, set())
    return len(neighbors_a & neighbors_b)


def jaccard_coefficient(
    adjacency: Dict[str, set],
    node_a: str,
    node_b: str,
) -> float:
    """Calcula coeficiente de Jaccard entre dos nodos."""
    neighbors_a = adjacency.get(node_a, set())
    neighbors_b = adjacency.get(node_b, set())
    
    intersection = len(neighbors_a & neighbors_b)
    union = len(neighbors_a | neighbors_b)
    
    return intersection / union if union > 0 else 0.0


def adamic_adar(
    adjacency: Dict[str, set],
    node_a: str,
    node_b: str,
) -> float:
    """
    Calcula indice de Adamic-Adar.
    Suma 1/log(degree) para cada vecino comun.
    """
    import math
    
    neighbors_a = adjacency.get(node_a, set())
    neighbors_b = adjacency.get(node_b, set())
    common = neighbors_a & neighbors_b
    
    score = 0.0
    for node in common:
        degree = len(adjacency.get(node, set()))
        if degree > 1:
            score += 1.0 / math.log(degree)
    
    return score


def preferential_attachment(
    adjacency: Dict[str, set],
    node_a: str,
    node_b: str,
) -> int:
    """Calcula producto de grados (preferential attachment)."""
    degree_a = len(adjacency.get(node_a, set()))
    degree_b = len(adjacency.get(node_b, set()))
    return degree_a * degree_b


def suggest_links(
    clients: ServiceClients,
    settings: AppSettings,
    source_type: str = "Categoria",
    target_type: str = "Codigo",
    algorithm: str = "common_neighbors",
    top_k: int = 10,
    project: Optional[str] = None,
    min_score: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Sugiere enlaces faltantes entre nodos del grafo.
    
    Args:
        clients: Clientes de servicios
        settings: Configuracion
        source_type: Tipo de nodo fuente (Categoria, Codigo)
        target_type: Tipo de nodo destino
        algorithm: Algoritmo a usar
        top_k: Numero de sugerencias
        project: ID del proyecto
        min_score: Score minimo para incluir
        
    Returns:
        Lista de sugerencias con source, target, score, algorithm
    """
    project_id = project or "default"
    
    _logger.info(
        "link_prediction.start",
        algorithm=algorithm,
        source_type=source_type,
        target_type=target_type,
    )
    
    # Obtener grafo
    adjacency, node_types = get_graph_data(clients, settings, project_id)
    
    if not adjacency:
        _logger.warning("link_prediction.empty_graph")
        return []
    
    # Seleccionar funcion de scoring
    score_funcs = {
        "common_neighbors": common_neighbors,
        "jaccard": jaccard_coefficient,
        "adamic_adar": adamic_adar,
        "preferential_attachment": preferential_attachment,
    }
    score_func = score_funcs.get(algorithm, common_neighbors)
    
    # Obtener nodos por tipo
    sources = [n for n, t in node_types.items() if t == source_type]
    targets = [n for n, t in node_types.items() if t == target_type]
    
    # Calcular scores para pares no conectados
    candidates = []
    
    for source in sources:
        source_neighbors = adjacency.get(source, set())
        for target in targets:
            # Solo considerar pares no conectados
            if target not in source_neighbors and source != target:
                score = score_func(adjacency, source, target)
                if score > min_score:
                    candidates.append({
                        "source": source,
                        "source_type": source_type,
                        "target": target,
                        "target_type": target_type,
                        "score": score,
                        "algorithm": algorithm,
                    })
    
    # Ordenar por score y retornar top_k
    candidates.sort(key=lambda x: x["score"], reverse=True)
    suggestions = candidates[:top_k]
    
    _logger.info(
        "link_prediction.complete",
        total_candidates=len(candidates),
        returned=len(suggestions),
    )
    
    return suggestions


def suggest_axial_relations(
    clients: ServiceClients,
    settings: AppSettings,
    categoria: Optional[str] = None,
    project: Optional[str] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    Sugiere relaciones axiales para una categoria especifica.
    
    Combina multiples algoritmos para dar sugerencias robustas.
    """
    project_id = project or "default"
    
    suggestions = []
    
    # Aplicar multiples algoritmos
    for algo in ["common_neighbors", "jaccard", "adamic_adar"]:
        results = suggest_links(
            clients, settings,
            source_type="Categoria",
            target_type="Codigo",
            algorithm=algo,
            top_k=top_k * 2,
            project=project_id,
        )
        
        # Filtrar por categoria si se especifica
        if categoria:
            results = [r for r in results if r["source"] == categoria]
        
        suggestions.extend(results)
    
    # Agregar scores por target
    target_scores = defaultdict(list)
    for s in suggestions:
        key = (s["source"], s["target"])
        target_scores[key].append(s["score"])
    
    # Calcular score promedio
    aggregated = []
    for (source, target), scores in target_scores.items():
        aggregated.append({
            "source": source,
            "target": target,
            "avg_score": sum(scores) / len(scores),
            "num_algorithms": len(scores),
            "confidence": "high" if len(scores) >= 2 else "medium",
        })
    
    aggregated.sort(key=lambda x: (x["num_algorithms"], x["avg_score"]), reverse=True)
    
    return aggregated[:top_k]


def detect_missing_links_by_community(
    clients: ServiceClients,
    settings: AppSettings,
    project: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Detecta enlaces faltantes basandose en comunidades (Louvain).
    
    Nodos en la misma comunidad que no estan conectados son candidatos.
    """
    project_id = project or "default"
    
    # Obtener nodos con community_id
    cypher = """
    MATCH (n)
    WHERE n.community_id IS NOT NULL AND (n:Categoria OR n:Codigo)
      AND n.project_id = $project_id
    RETURN n.nombre AS name, labels(n)[0] AS type, n.community_id AS community
    """
    
    communities = defaultdict(list)
    
    try:
        with clients.neo4j.session(database=settings.neo4j.database) as session:
            result = session.run(cypher, project_id=project_id)
            for record in result:
                comm = record["community"]
                communities[comm].append({
                    "name": record["name"],
                    "type": record["type"],
                })
    except Exception as e:
        _logger.error("link_prediction.community_error", error=str(e))
        return []
    
    # Obtener grafo para verificar conexiones existentes
    adjacency, _ = get_graph_data(clients, settings, project_id)
    
    # Buscar pares no conectados en misma comunidad
    suggestions = []
    
    for comm_id, nodes in communities.items():
        if len(nodes) < 2:
            continue
            
        for i, node_a in enumerate(nodes):
            for node_b in nodes[i+1:]:
                name_a = node_a["name"]
                name_b = node_b["name"]
                
                # Verificar si no estan conectados
                if name_b not in adjacency.get(name_a, set()):
                    suggestions.append({
                        "source": name_a,
                        "source_type": node_a["type"],
                        "target": name_b,
                        "target_type": node_b["type"],
                        "community_id": comm_id,
                        "reason": "same_community",
                    })
    
    return suggestions[:20]  # Limitar resultados


def discover_hidden_relationships(
    clients: ServiceClients,
    settings: AppSettings,
    project: Optional[str] = None,
    top_k: int = 20,
) -> List[Dict[str, Any]]:
    """
    Descubre relaciones ocultas/latentes entre códigos y categorías.
    
    Combina 3 métodos de descubrimiento:
    1. Co-ocurrencia en fragmentos (códigos que aparecen juntos)
    2. Categoría compartida (códigos bajo la misma categoría sin relación directa)
    3. Comunidad (nodos en la misma comunidad Louvain)
    
    Args:
        clients: Clientes de servicios
        settings: Configuración
        project: ID del proyecto
        top_k: Número máximo de sugerencias
        
    Returns:
        Lista de relaciones ocultas con scores y razones
    """
    project_id = project or "default"
    hidden_rels = []
    
    _logger.info("hidden_relationships.start", project=project_id)
    
    def _get_direct_cooccurrence_fragment_ids(code_a: str, code_b: str, limit: int = 3) -> List[str]:
        """Return fragment IDs where both codes co-occur in the same fragment."""
        # 1) Prefer Neo4j graph evidence if available.
        try:
            with clients.neo4j.session(database=settings.neo4j.database) as session:
                cypher = """
                MATCH (f:Fragmento {project_id: $project_id})-[:TIENE_CODIGO]->(c1:Codigo {nombre: $code_a, project_id: $project_id})
                MATCH (f)-[:TIENE_CODIGO]->(c2:Codigo {nombre: $code_b, project_id: $project_id})
                RETURN f.id AS fragmento_id
                LIMIT $limit
                """
                result = session.run(
                    cypher,
                    project_id=project_id,
                    code_a=code_a,
                    code_b=code_b,
                    limit=int(limit),
                )
                ids = [str(r["fragmento_id"]) for r in result if r and r.get("fragmento_id")]
                if ids:
                    return ids
        except Exception:
            pass

        # 2) Fallback: PostgreSQL co-occurrence (analisis_codigos_abiertos)
        try:
            with clients.postgres.cursor() as cur:
                cur.execute(
                    """
                    SELECT a.fragmento_id
                    FROM analisis_codigos_abiertos a
                    JOIN analisis_codigos_abiertos b
                      ON a.fragmento_id = b.fragmento_id
                     AND a.project_id = b.project_id
                    WHERE a.project_id = %s
                      AND a.codigo = %s
                      AND b.codigo = %s
                    LIMIT %s
                    """,
                    (project_id, code_a, code_b, int(limit)),
                )
                return [str(r[0]) for r in cur.fetchall() if r and r[0]]
        except Exception:
            return []

    def _get_single_code_fragment_ids(code: str, limit: int = 2) -> List[str]:
        """Return fragment IDs that contain a given code (supporting/indirect evidence)."""
        try:
            with clients.neo4j.session(database=settings.neo4j.database) as session:
                cypher = """
                MATCH (f:Fragmento {project_id: $project_id})-[:TIENE_CODIGO]->(c:Codigo {nombre: $code, project_id: $project_id})
                RETURN f.id AS fragmento_id
                LIMIT $limit
                """
                result = session.run(cypher, project_id=project_id, code=code, limit=int(limit))
                ids = [str(r["fragmento_id"]) for r in result if r and r.get("fragmento_id")]
                if ids:
                    return ids
        except Exception:
            pass

        try:
            with clients.postgres.cursor() as cur:
                cur.execute(
                    """
                    SELECT fragmento_id
                    FROM analisis_codigos_abiertos
                    WHERE project_id = %s AND codigo = %s
                    LIMIT %s
                    """,
                    (project_id, code, int(limit)),
                )
                return [str(r[0]) for r in cur.fetchall() if r and r[0]]
        except Exception:
            return []

    try:
        with clients.neo4j.session(database=settings.neo4j.database) as session:
            # 1. CO-OCURRENCIA: Códigos que aparecen juntos en fragmentos
            # NOTE: The canonical graph relation is (:Fragmento)-[:TIENE_CODIGO]->(:Codigo)
            cooccurrence_query = """
            MATCH (f:Fragmento {project_id: $project_id})-[:TIENE_CODIGO]->(c1:Codigo {project_id: $project_id})
            MATCH (f)-[:TIENE_CODIGO]->(c2:Codigo {project_id: $project_id})
            WHERE c1.nombre < c2.nombre
              AND NOT EXISTS { MATCH (c1)-[:REL]-(c2) }
              AND NOT EXISTS { MATCH (c1)<-[:REL]-(:Categoria)-[:REL]->(c2) }
            WITH c1, c2, collect(DISTINCT f.id) AS frag_ids
            WITH c1, c2, frag_ids, size(frag_ids) AS cooccurrences
            WHERE cooccurrences >= 2
            RETURN c1.nombre AS source, 'Codigo' AS source_type,
                   c2.nombre AS target, 'Codigo' AS target_type,
                   cooccurrences AS score,
                   'co-ocurrencia en fragmentos' AS reason,
                   'cooccurrence' AS method,
                   frag_ids[0..$evidence_limit] AS evidence_ids
            ORDER BY cooccurrences DESC
            LIMIT $limit
            """

            result = session.run(
                cooccurrence_query,
                project_id=project_id,
                limit=top_k,
                evidence_limit=3,
            )
            for record in result:
                hidden_rels.append({
                    "source": record["source"],
                    "source_type": record["source_type"],
                    "target": record["target"],
                    "target_type": record["target_type"],
                    "score": record["score"],
                    "reason": record["reason"],
                    "method": record["method"],
                    "evidence_ids": [str(v) for v in (record.get("evidence_ids") or []) if v],
                    "confidence": "high" if record["score"] >= 3 else "medium",
                })
            
            # 2. CATEGORÍA COMPARTIDA: Códigos que comparten categoría pero no están relacionados
            shared_category_query = """
            MATCH (c1:Codigo)<-[:REL]-(cat:Categoria)-[:REL]->(c2:Codigo)
            WHERE c1.project_id = $project_id 
              AND c2.project_id = $project_id
              AND NOT EXISTS { MATCH (c1)-[:REL]-(c2) }
              AND id(c1) < id(c2)
            WITH c1, c2, collect(DISTINCT cat.nombre) AS shared_categories
            RETURN c1.nombre AS source, 'Codigo' AS source_type,
                   c2.nombre AS target, 'Codigo' AS target_type,
                   size(shared_categories) AS score,
                   'comparten categoría: ' + shared_categories[0] AS reason,
                   'shared_category' AS method
            ORDER BY score DESC
            LIMIT $limit
            """
            
            result = session.run(shared_category_query, project_id=project_id, limit=top_k)
            for record in result:
                hidden_rels.append({
                    "source": record["source"],
                    "source_type": record["source_type"],
                    "target": record["target"],
                    "target_type": record["target_type"],
                    "score": record["score"],
                    "reason": record["reason"],
                    "method": record["method"],
                    "confidence": "medium",
                })
            
            # 3. MISMA COMUNIDAD: Nodos en la misma comunidad Louvain
            community_query = """
            MATCH (c1:Codigo), (c2:Codigo)
            WHERE c1.project_id = $project_id
              AND c2.project_id = $project_id
              AND c1.comunidad IS NOT NULL
              AND c1.comunidad = c2.comunidad
              AND id(c1) < id(c2)
              AND NOT EXISTS { MATCH (c1)-[:REL]-(c2) }
            RETURN c1.nombre AS source, 'Codigo' AS source_type,
                   c2.nombre AS target, 'Codigo' AS target_type,
                   1 AS score,
                   'misma comunidad temática: ' + toString(c1.comunidad) AS reason,
                   'community' AS method
            LIMIT $limit
            """
            
            result = session.run(community_query, project_id=project_id, limit=top_k)
            for record in result:
                hidden_rels.append({
                    "source": record["source"],
                    "source_type": record["source_type"],
                    "target": record["target"],
                    "target_type": record["target_type"],
                    "score": record["score"],
                    "reason": record["reason"],
                    "method": record["method"],
                    "confidence": "low",
                })
                
    except Exception as e:
        _logger.warning("hidden_relationships.neo4j_unavailable", error=str(e)[:200])

        # Fallback: compute suggestions from PostgreSQL tables.
        # This is less expressive than Neo4j (no communities), but keeps the feature usable.
        try:
            # 1) Co-occurrence from analisis_codigos_abiertos
            with clients.postgres.cursor() as cur:
                cur.execute(
                    """
                    SELECT a.codigo AS source, b.codigo AS target, COUNT(*) as cooccurrences
                    FROM analisis_codigos_abiertos a
                    JOIN analisis_codigos_abiertos b
                      ON a.fragmento_id = b.fragmento_id
                     AND a.project_id = b.project_id
                     AND a.codigo < b.codigo
                    WHERE a.project_id = %s
                    GROUP BY a.codigo, b.codigo
                    HAVING COUNT(*) >= 2
                    ORDER BY cooccurrences DESC
                    LIMIT %s
                    """,
                    (project_id, int(top_k)),
                )
                for source, target, count in cur.fetchall():
                    if not source or not target:
                        continue
                    hidden_rels.append({
                        "source": str(source),
                        "source_type": "Codigo",
                        "target": str(target),
                        "target_type": "Codigo",
                        "score": int(count) if count is not None else 0,
                        "reason": "co-ocurrencia en fragmentos (PG)",
                        "method": "cooccurrence",
                        "confidence": "high" if (count or 0) >= 3 else "medium",
                    })

            # 2) Shared category from analisis_axial (Categoria -> Codigo)
            with clients.postgres.cursor() as cur:
                cur.execute(
                    """
                    SELECT categoria, codigo
                    FROM analisis_axial
                    WHERE project_id = %s
                    """,
                    (project_id,),
                )
                rows = cur.fetchall()
            by_cat: Dict[str, List[str]] = defaultdict(list)
            for cat, cod in rows:
                if cat and cod:
                    by_cat[str(cat)].append(str(cod))

            generated = 0
            for cat, codes in by_cat.items():
                if len(codes) < 2:
                    continue
                # Limit pair generation per category to avoid quadratic blow-up
                codes = list(dict.fromkeys(codes))[:60]
                for i in range(len(codes)):
                    for j in range(i + 1, len(codes)):
                        hidden_rels.append({
                            "source": codes[i],
                            "source_type": "Codigo",
                            "target": codes[j],
                            "target_type": "Codigo",
                            "score": 1,
                            "reason": f"comparten categoría: {cat} (PG)",
                            "method": "shared_category",
                            "confidence": "low",
                        })
                        generated += 1
                        if generated >= int(top_k):
                            break
                    if generated >= int(top_k):
                        break
                if generated >= int(top_k):
                    break
        except Exception as pg_exc:
            _logger.error("hidden_relationships.postgres_fallback_failed", error=str(pg_exc)[:200])
            return []
    
    # Ordenar por score y eliminar duplicados
    seen = set()
    unique_rels = []
    for rel in sorted(hidden_rels, key=lambda x: x["score"], reverse=True):
        key = tuple(sorted([rel["source"], rel["target"]]))
        if key not in seen:
            seen.add(key)
            # Evidence backfill layer:
            # - direct evidence: same-fragment co-occurrence
            # - supporting evidence: best fragments for each code (indirect)
            direct_evidence_ids: List[str] = []
            supporting_ids: List[str] = []
            evidence_kind = "none"
            gap_reason: Optional[str] = None

            # Prefer any evidence_ids already returned by the query
            raw_existing = rel.get("evidence_ids") or []
            if isinstance(raw_existing, list):
                direct_evidence_ids = [str(v) for v in raw_existing if v]

            if (
                not direct_evidence_ids
                and rel.get("source_type") == "Codigo"
                and rel.get("target_type") == "Codigo"
            ):
                direct_evidence_ids = _get_direct_cooccurrence_fragment_ids(rel["source"], rel["target"], limit=3)

            if direct_evidence_ids:
                evidence_kind = "direct"
            else:
                # Structural methods can be valid hypotheses without direct co-occurrence.
                method = str(rel.get("method") or "unknown")
                if method in {"shared_category", "community"}:
                    gap_reason = "structural_method_no_direct_cooccurrence"
                elif method == "cooccurrence":
                    gap_reason = "cooccurrence_score_without_retrieved_fragments"
                else:
                    gap_reason = "no_direct_evidence_found"

                # Provide supporting evidence when possible (indirect)
                if rel.get("source_type") == "Codigo" and rel.get("target_type") == "Codigo":
                    a_ids = _get_single_code_fragment_ids(rel["source"], limit=2)
                    b_ids = _get_single_code_fragment_ids(rel["target"], limit=2)
                    # Keep order stable: a then b, unique
                    seen_ids = set()
                    for v in (a_ids + b_ids):
                        if v and v not in seen_ids:
                            supporting_ids.append(v)
                            seen_ids.add(v)
                    if a_ids and b_ids:
                        evidence_kind = "indirect"

            rel["evidence_ids"] = direct_evidence_ids
            rel["supporting_evidence_ids"] = supporting_ids
            rel["evidence_kind"] = evidence_kind
            rel["evidence_gap_reason"] = gap_reason
            rel["evidence_count"] = len(direct_evidence_ids)
            rel["supporting_evidence_count"] = len(supporting_ids)
            rel["epistemic_status"] = "hipotesis"
            rel["origin"] = "descubrimiento"
            rel["evidence_required"] = evidence_kind != "direct"
            unique_rels.append(rel)
    
    _logger.info("hidden_relationships.complete", total=len(unique_rels))
    
    return unique_rels[:top_k]


def confirm_hidden_relationship(
    clients: ServiceClients,
    settings: AppSettings,
    source: str,
    target: str,
    relation_type: str = "partede",
    project: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Confirma una relación oculta, creándola en Neo4j con marca 'descubierta'.
    
    Args:
        source: Nombre del nodo origen
        target: Nombre del nodo destino
        relation_type: Tipo de relación (causa, condicion, consecuencia, partede)
        project: ID del proyecto
        
    Returns:
        Resultado de la operación
    """
    from .neo4j_block import ALLOWED_REL_TYPES
    
    project_id = project or "default"
    
    if relation_type not in ALLOWED_REL_TYPES:
        return {"status": "error", "message": f"Tipo '{relation_type}' no válido"}
    
    cypher = """
    MATCH (s {nombre: $source, project_id: $project_id})
    MATCH (t {nombre: $target, project_id: $project_id})
    MERGE (s)-[r:REL {tipo: $relation_type}]->(t)
    SET r.origen = 'descubierta',
        r.project_id = $project_id,
        r.confirmado_en = datetime()
    RETURN s.nombre AS source, t.nombre AS target, r.tipo AS tipo
    """
    
    try:
        with clients.neo4j.session(database=settings.neo4j.database) as session:
            result = session.run(
                cypher,
                source=source,
                target=target,
                relation_type=relation_type,
                project_id=project_id,
            )
            record = result.single()
            
            if record:
                _logger.info(
                    "hidden_relationship.confirmed",
                    source=source,
                    target=target,
                    tipo=relation_type,
                )
                return {
                    "status": "ok",
                    "source": record["source"],
                    "target": record["target"],
                    "tipo": record["tipo"],
                    "origen": "descubierta",
                }
            else:
                return {"status": "error", "message": "Nodos no encontrados"}
                
    except Exception as e:
        _logger.error("hidden_relationship.confirm_error", error=str(e))
        return {"status": "error", "message": str(e)}
