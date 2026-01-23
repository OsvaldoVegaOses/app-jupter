"""
Wrapper unificado para algoritmos de grafos.

Este módulo proporciona una capa de abstracción sobre diferentes motores de grafos:
1. Neo4j GDS (Graph Data Science)
2. Memgraph MAGE
3. NetworkX/Python (fallback universal)

El wrapper detecta automáticamente qué motor está disponible y ejecuta
los algoritmos usando el backend apropiado.

Uso:
    from app.graph_algorithms import GraphAlgorithms, GraphEngine

    # Inicializar con clientes
    ga = GraphAlgorithms(clients, settings)
    
    # Ver qué motor se detectó
    print(ga.engine)  # GraphEngine.NEO4J_GDS | MEMGRAPH_MAGE | NETWORKX
    
    # Ejecutar algoritmos
    louvain_result = ga.louvain(project_id="mi_proyecto")
    pagerank_result = ga.pagerank(project_id="mi_proyecto", persist=True)
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
import structlog

import networkx as nx
from networkx.algorithms.community import louvain_communities

_logger = structlog.get_logger(__name__)


class GraphEngine(Enum):
    """Motor de grafos detectado."""
    NEO4J_GDS = "neo4j_gds"
    MEMGRAPH_MAGE = "memgraph_mage"
    NETWORKX = "networkx"


class GraphAlgorithmError(Exception):
    """Error en ejecución de algoritmos de grafos."""
    pass


class GraphAlgorithms:
    """
    Wrapper unificado para algoritmos de grafos con fallback automático.
    
    Detecta automáticamente el motor disponible y ejecuta algoritmos
    usando el backend apropiado.
    """

    def __init__(self, clients, settings, force_engine: Optional[GraphEngine] = None):
        """
        Inicializa el wrapper.
        
        Args:
            clients: ServiceClients con conexiones a Neo4j, etc.
            settings: AppSettings con configuración
            force_engine: Forzar un motor específico (para testing)
        """
        self.clients = clients
        self.settings = settings
        self._engine = force_engine or self._detect_engine()
        _logger.info("graph_algorithms.initialized", engine=self._engine.value)

    @property
    def engine(self) -> GraphEngine:
        """Motor de grafos detectado."""
        return self._engine

    def _detect_engine(self) -> GraphEngine:
        """Detecta qué motor de grafos está disponible."""
        
        # 1. Intentar Neo4j GDS
        try:
            with self.clients.neo4j.session(database=self.settings.neo4j.database) as session:
                result = session.run("RETURN gds.version() AS version")
                record = result.single()
                if record and record["version"]:
                    _logger.info("graph_engine.detected", engine="neo4j_gds", 
                                version=record["version"])
                    return GraphEngine.NEO4J_GDS
        except Exception as e:
            _logger.debug("graph_engine.neo4j_gds_not_available", error=str(e))
        
        # 2. Intentar Memgraph MAGE
        try:
            with self.clients.neo4j.session(database=self.settings.neo4j.database) as session:
                # Memgraph tiene mg.procedures() para listar procedimientos
                result = session.run("CALL mg.procedures() YIELD name RETURN name LIMIT 1")
                if result.single():
                    _logger.info("graph_engine.detected", engine="memgraph_mage")
                    return GraphEngine.MEMGRAPH_MAGE
        except Exception as e:
            _logger.debug("graph_engine.memgraph_not_available", error=str(e))
        
        # 3. Fallback a NetworkX
        _logger.info("graph_engine.fallback", engine="networkx")
        return GraphEngine.NETWORKX

    # =========================================================================
    # ALGORITMOS PÚBLICOS
    # =========================================================================

    def louvain(
        self, 
        project_id: str, 
        persist: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Detecta comunidades usando algoritmo Louvain.
        
        Args:
            project_id: ID del proyecto para aislamiento
            persist: Si True, guarda community_id en los nodos
            
        Returns:
            Lista de {nombre, etiquetas, community_id}
        """
        if self._engine == GraphEngine.NEO4J_GDS:
            try:
                return self._louvain_neo4j(project_id, persist)
            except Exception as e:
                _logger.warning(
                    "graph_algorithms.engine_failed.fallback",
                    algorithm="louvain",
                    from_engine=GraphEngine.NEO4J_GDS.value,
                    to_engine=GraphEngine.NETWORKX.value,
                    project_id=project_id,
                    error=str(e)[:200],
                )
                # Persist is not safe in fallback because NetworkX node IDs are not Neo4j IDs.
                return self._louvain_networkx(project_id, persist=False)
        elif self._engine == GraphEngine.MEMGRAPH_MAGE:
            try:
                return self._louvain_memgraph(project_id, persist)
            except Exception as e:
                _logger.warning(
                    "graph_algorithms.engine_failed.fallback",
                    algorithm="louvain",
                    from_engine=GraphEngine.MEMGRAPH_MAGE.value,
                    to_engine=GraphEngine.NETWORKX.value,
                    project_id=project_id,
                    error=str(e)[:200],
                )
                return self._louvain_networkx(project_id, persist=False)
        else:
            return self._louvain_networkx(project_id, persist)

    def pagerank(
        self, 
        project_id: str, 
        persist: bool = False,
        damping_factor: float = 0.85,
        max_iterations: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Calcula PageRank de nodos.
        
        Args:
            project_id: ID del proyecto para aislamiento
            persist: Si True, guarda score_centralidad en los nodos
            damping_factor: Factor de damping (default 0.85)
            max_iterations: Máximo de iteraciones
            
        Returns:
            Lista de {nombre, etiquetas, score} ordenada por score DESC
        """
        if self._engine == GraphEngine.NEO4J_GDS:
            try:
                return self._pagerank_neo4j(project_id, persist, damping_factor, max_iterations)
            except Exception as e:
                _logger.warning(
                    "graph_algorithms.engine_failed.fallback",
                    algorithm="pagerank",
                    from_engine=GraphEngine.NEO4J_GDS.value,
                    to_engine=GraphEngine.NETWORKX.value,
                    project_id=project_id,
                    error=str(e)[:200],
                )
                return self._pagerank_networkx(project_id, persist=False, damping_factor=damping_factor, max_iterations=max_iterations)
        elif self._engine == GraphEngine.MEMGRAPH_MAGE:
            try:
                return self._pagerank_memgraph(project_id, persist, damping_factor, max_iterations)
            except Exception as e:
                _logger.warning(
                    "graph_algorithms.engine_failed.fallback",
                    algorithm="pagerank",
                    from_engine=GraphEngine.MEMGRAPH_MAGE.value,
                    to_engine=GraphEngine.NETWORKX.value,
                    project_id=project_id,
                    error=str(e)[:200],
                )
                return self._pagerank_networkx(project_id, persist=False, damping_factor=damping_factor, max_iterations=max_iterations)
        else:
            return self._pagerank_networkx(project_id, persist, damping_factor, max_iterations)

    def betweenness(
        self, 
        project_id: str, 
        persist: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Calcula Betweenness Centrality de nodos.
        
        Args:
            project_id: ID del proyecto para aislamiento
            persist: Si True, guarda score_intermediacion en los nodos
            
        Returns:
            Lista de {nombre, etiquetas, score} ordenada por score DESC
        """
        if self._engine == GraphEngine.NEO4J_GDS:
            try:
                return self._betweenness_neo4j(project_id, persist)
            except Exception as e:
                _logger.warning(
                    "graph_algorithms.engine_failed.fallback",
                    algorithm="betweenness",
                    from_engine=GraphEngine.NEO4J_GDS.value,
                    to_engine=GraphEngine.NETWORKX.value,
                    project_id=project_id,
                    error=str(e)[:200],
                )
                return self._betweenness_networkx(project_id, persist=False)
        elif self._engine == GraphEngine.MEMGRAPH_MAGE:
            try:
                return self._betweenness_memgraph(project_id, persist)
            except Exception as e:
                _logger.warning(
                    "graph_algorithms.engine_failed.fallback",
                    algorithm="betweenness",
                    from_engine=GraphEngine.MEMGRAPH_MAGE.value,
                    to_engine=GraphEngine.NETWORKX.value,
                    project_id=project_id,
                    error=str(e)[:200],
                )
                return self._betweenness_networkx(project_id, persist=False)
        else:
            return self._betweenness_networkx(project_id, persist)

    def leiden(
        self, 
        project_id: str, 
        persist: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Detecta comunidades usando algoritmo Leiden (mejor que Louvain).
        
        NOTA: Solo disponible en Neo4j GDS o Python (igraph).
        Memgraph no soporta Leiden nativo.
        
        Args:
            project_id: ID del proyecto
            persist: Si True, guarda community_id en los nodos
            
        Returns:
            Lista de {nombre, etiquetas, community_id}
        """
        if self._engine == GraphEngine.NEO4J_GDS:
            return self._leiden_neo4j(project_id, persist)
        else:
            # Memgraph no soporta Leiden, usar Python
            return self._leiden_python(project_id, persist)

    def hdbscan(
        self, 
        embeddings: List[List[float]],
        node_names: List[str],
        min_cluster_size: int = 5,
        min_samples: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Clustering jerárquico basado en densidad usando HDBSCAN.
        
        NOTA: Solo disponible como fallback Python (librería hdbscan).
        No está disponible en Neo4j GDS Community ni Memgraph MAGE.
        
        Args:
            embeddings: Lista de vectores de embeddings (e.g., de Node2Vec o similitud semántica)
            node_names: Nombres de nodos correspondientes a cada embedding
            min_cluster_size: Mínimo de elementos para formar un cluster
            min_samples: Mínimo de muestras para considerar core point
            
        Returns:
            Lista de {nombre, cluster_id, probability}
        """
        _logger.info("graph_algorithms.hdbscan", engine="python", 
                     n_embeddings=len(embeddings), min_cluster_size=min_cluster_size)
        
        try:
            import hdbscan as hdbscan_lib
            import numpy as np
        except ImportError:
            raise GraphAlgorithmError(
                "HDBSCAN requiere la librería 'hdbscan'. Instalar con: pip install hdbscan"
            )
        
        if len(embeddings) < min_cluster_size:
            _logger.warning("graph_algorithms.hdbscan_insufficient_data", 
                           n_embeddings=len(embeddings), min_cluster_size=min_cluster_size)
            return []
        
        embeddings_array = np.array(embeddings)
        
        clusterer = hdbscan_lib.HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            metric='euclidean'
        )
        cluster_labels = clusterer.fit_predict(embeddings_array)
        probabilities = clusterer.probabilities_
        
        results = []
        for i, (name, cluster_id) in enumerate(zip(node_names, cluster_labels)):
            results.append({
                "nombre": name,
                "cluster_id": int(cluster_id),  # -1 = noise
                "probability": float(probabilities[i]) if probabilities is not None else 0.0,
                "is_noise": cluster_id == -1
            })
        
        # Ordenar por cluster, luego por probabilidad descendente
        results.sort(key=lambda x: (x["cluster_id"], -x["probability"]))
        
        return results

    def kmeans(
        self, 
        embeddings: List[List[float]],
        node_names: List[str],
        n_clusters: int = 5,
        random_state: int = 42
    ) -> List[Dict[str, Any]]:
        """
        Clustering K-Means.
        
        NOTA: Solo disponible como fallback Python (scikit-learn).
        
        Args:
            embeddings: Lista de vectores de embeddings
            node_names: Nombres de nodos correspondientes a cada embedding
            n_clusters: Número de clusters a crear
            random_state: Semilla para reproducibilidad
            
        Returns:
            Lista de {nombre, cluster_id, distance_to_centroid}
        """
        _logger.info("graph_algorithms.kmeans", engine="python", 
                     n_embeddings=len(embeddings), n_clusters=n_clusters)
        
        try:
            from sklearn.cluster import KMeans
            import numpy as np
        except ImportError:
            raise GraphAlgorithmError(
                "K-Means requiere scikit-learn. Instalar con: pip install scikit-learn"
            )
        
        if len(embeddings) < n_clusters:
            _logger.warning("graph_algorithms.kmeans_insufficient_data", 
                           n_embeddings=len(embeddings), n_clusters=n_clusters)
            n_clusters = max(1, len(embeddings))
        
        embeddings_array = np.array(embeddings)
        
        kmeans = KMeans(n_clusters=n_clusters, random_state=random_state, n_init='auto')
        cluster_labels = kmeans.fit_predict(embeddings_array)
        
        # Calcular distancia al centroide
        distances = np.linalg.norm(
            embeddings_array - kmeans.cluster_centers_[cluster_labels], 
            axis=1
        )
        
        results = []
        for i, (name, cluster_id) in enumerate(zip(node_names, cluster_labels)):
            results.append({
                "nombre": name,
                "cluster_id": int(cluster_id),
                "distance_to_centroid": float(distances[i])
            })
        
        # Ordenar por cluster, luego por distancia ascendente (más cercanos primero)
        results.sort(key=lambda x: (x["cluster_id"], x["distance_to_centroid"]))
        
        return results

    # =========================================================================
    # HELPERS: Extracción de grafo
    # =========================================================================

    def _extract_graph_data(self, project_id: str) -> Tuple[nx.DiGraph, Dict[str, Dict]]:
        """
        Extrae datos del grafo con fallback a PostgreSQL.
        
        Intenta Neo4j/Memgraph primero, luego PostgreSQL si falla.
        
        Returns:
            Tupla de (grafo NetworkX, diccionario de propiedades de nodos)
        """
        # 1. Intentar Neo4j/Memgraph
        try:
            G, node_props = self._extract_graph_data_from_neo4j(project_id)
            if G.nodes():
                _logger.info("graph_algorithms.data_source", source="neo4j", nodes=len(node_props))
                return G, node_props
        except Exception as e:
            _logger.warning("graph_algorithms.neo4j_failed", error=str(e)[:100])
        
        # 2. Fallback: PostgreSQL
        try:
            G, node_props = self._extract_graph_data_from_postgres(project_id)
            _logger.info("graph_algorithms.data_source", source="postgresql", nodes=len(node_props))
            return G, node_props
        except Exception as e:
            _logger.error("graph_algorithms.postgres_fallback_failed", error=str(e)[:100])
        
        return nx.DiGraph(), {}

    def _extract_graph_data_from_neo4j(self, project_id: str) -> Tuple[nx.DiGraph, Dict[str, Dict]]:
        """Extrae grafo desde Neo4j/Memgraph."""
        query = """
        MATCH (s)-[:REL]->(t) 
        WHERE s.project_id = $project_id AND t.project_id = $project_id
        RETURN id(s) as sid, s.nombre as sname, labels(s) as slabels, 
               id(t) as tid, t.nombre as tname, labels(t) as tlabels
        """
        
        with self.clients.neo4j.session(database=self.settings.neo4j.database) as session:
            data = session.run(query, project_id=project_id).data()
        
        G = nx.DiGraph()
        node_props = {}
        
        for row in data:
            sid, tid = str(row["sid"]), str(row["tid"])
            G.add_edge(sid, tid)
            if sid not in node_props:
                node_props[sid] = {"nombre": row["sname"], "etiquetas": row["slabels"]}
            if tid not in node_props:
                node_props[tid] = {"nombre": row["tname"], "etiquetas": row["tlabels"]}
        
        return G, node_props

    def _extract_graph_data_from_postgres(self, project_id: str) -> Tuple[nx.DiGraph, Dict[str, Dict]]:
        """
        Construye grafo desde PostgreSQL como fallback.
        
        Fuentes: analisis_axial (relaciones) + analisis_codigos_abiertos (co-ocurrencias)
        """
        G = nx.DiGraph()
        node_props = {}
        node_id_counter = 0
        name_to_id = {}

        # Canonicalize codes so graph algorithms don't amplify merged aliases.
        try:
            from app.postgres_block import ensure_codes_catalog_table, resolve_canonical_codigos_bulk

            ensure_codes_catalog_table(self.clients.postgres)
        except Exception:
            resolve_canonical_codigos_bulk = None  # type: ignore
        
        def get_or_create_id(name: str, label: str) -> str:
            nonlocal node_id_counter
            if name not in name_to_id:
                name_to_id[name] = str(node_id_counter)
                node_props[str(node_id_counter)] = {"nombre": name, "etiquetas": [label]}
                node_id_counter += 1
            return name_to_id[name]
        
        # 1. Relaciones axiales
        with self.clients.postgres.cursor() as cur:
            cur.execute("""
                SELECT categoria, codigo, relacion 
                FROM analisis_axial 
                WHERE project_id = %s
            """, (project_id,))
            axial_rows = cur.fetchall() or []

        canon_map = {}
        if resolve_canonical_codigos_bulk is not None and axial_rows:
            unique_codes = {str(r[1]).strip() for r in axial_rows if r and r[1]}
            try:
                canon_map = resolve_canonical_codigos_bulk(self.clients.postgres, project_id, unique_codes)
            except Exception:
                canon_map = {}

        for cat, cod, rel in axial_rows:
            cod_s = str(cod).strip() if cod is not None else ""
            cod_c = canon_map.get(cod_s, cod_s)
            cat_id = get_or_create_id(cat, "Categoria")
            cod_id = get_or_create_id(cod_c, "Codigo")
            G.add_edge(cat_id, cod_id)
        
        # 2. Co-ocurrencias de códigos (para Louvain/comunidades)
        with self.clients.postgres.cursor() as cur:
            cur.execute("""
                SELECT a.codigo, b.codigo, COUNT(*) as cnt
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

        canon_map2 = {}
        if resolve_canonical_codigos_bulk is not None and co_rows:
            unique_codes2 = {str(c).strip() for r in co_rows for c in r[:2] if c}
            try:
                canon_map2 = resolve_canonical_codigos_bulk(self.clients.postgres, project_id, unique_codes2)
            except Exception:
                canon_map2 = {}

        for cod1, cod2, cnt in co_rows:
            c1 = canon_map2.get(str(cod1).strip(), str(cod1).strip())
            c2 = canon_map2.get(str(cod2).strip(), str(cod2).strip())
            if not c1 or not c2 or c1.lower() == c2.lower():
                continue
            id1 = get_or_create_id(c1, "Codigo")
            id2 = get_or_create_id(c2, "Codigo")
            G.add_edge(id1, id2)
        
        _logger.info(
            "graph_algorithms.postgres_graph",
            nodes=len(node_props),
            edges=G.number_of_edges()
        )
        
        return G, node_props

    def _persist_property(
        self, 
        session, 
        updates: List[Dict[str, Any]], 
        property_name: str
    ) -> None:
        """Persiste propiedades en nodos Neo4j/Memgraph."""
        if not updates:
            return
            
        batch_query = """
        UNWIND $batch as row 
        MATCH (n) WHERE id(n) = toInteger(row.id)
        SET n[$prop_name] = row.val
        """
        
        # Batch en chunks de 1000
        chunk_size = 1000
        for i in range(0, len(updates), chunk_size):
            batch = updates[i:i + chunk_size]
            session.run(batch_query, batch=batch, prop_name=property_name).consume()

    # =========================================================================
    # IMPLEMENTACIONES: NetworkX (fallback universal)
    # =========================================================================

    def _louvain_networkx(self, project_id: str, persist: bool) -> List[Dict[str, Any]]:
        """Louvain con NetworkX."""
        _logger.info("graph_algorithms.louvain", engine="networkx", project_id=project_id)
        
        G, node_props = self._extract_graph_data(project_id)
        if not G.nodes():
            return []
        
        # Convertir a no dirigido para Louvain
        GU = G.to_undirected()
        communities = louvain_communities(GU)
        
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
        
        if persist:
            with self.clients.neo4j.session(database=self.settings.neo4j.database) as session:
                self._persist_property(session, updates, "community_id")
        
        return results

    def _pagerank_networkx(
        self, 
        project_id: str, 
        persist: bool,
        damping_factor: float,
        max_iterations: int
    ) -> List[Dict[str, Any]]:
        """PageRank con NetworkX."""
        _logger.info("graph_algorithms.pagerank", engine="networkx", project_id=project_id)
        
        G, node_props = self._extract_graph_data(project_id)
        if not G.nodes():
            return []

        def _pagerank_power_iteration(
            graph: nx.DiGraph,
            alpha: float,
            max_iter: int,
            tol: float = 1.0e-6,
        ) -> Dict[str, float]:
            nodes = list(graph.nodes())
            n = len(nodes)
            if n == 0:
                return {}
            idx = {node: i for i, node in enumerate(nodes)}

            # Initialize uniformly.
            r = [1.0 / n] * n

            out_degree = [0] * n
            incoming = [[] for _ in range(n)]

            for u in nodes:
                ui = idx[u]
                out_degree[ui] = int(graph.out_degree(u))
            for u, v in graph.edges():
                vi = idx[v]
                incoming[vi].append(idx[u])

            teleport = (1.0 - alpha) / n

            for _ in range(max_iter):
                # Distribute dangling mass.
                dangling_sum = sum(r[i] for i in range(n) if out_degree[i] == 0)
                dangling_contrib = alpha * dangling_sum / n

                new_r = [0.0] * n
                for i in range(n):
                    rank_sum = 0.0
                    for j in incoming[i]:
                        if out_degree[j] > 0:
                            rank_sum += r[j] / out_degree[j]
                    new_r[i] = teleport + dangling_contrib + alpha * rank_sum

                err = sum(abs(new_r[i] - r[i]) for i in range(n))
                r = new_r
                if err < tol:
                    break

            return {nodes[i]: float(r[i]) for i in range(n)}

        try:
            scores = nx.pagerank(G, alpha=damping_factor, max_iter=max_iterations)
        except ModuleNotFoundError as e:
            # Newer NetworkX versions may rely on SciPy for pagerank; keep a no-deps fallback.
            if getattr(e, "name", None) == "scipy":
                scores = _pagerank_power_iteration(G, alpha=damping_factor, max_iter=max_iterations)
            else:
                raise
        sorted_nodes = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        results = [
            {
                "nombre": node_props[nid]["nombre"],
                "etiquetas": node_props[nid]["etiquetas"],
                "score": score
            }
            for nid, score in sorted_nodes if nid in node_props
        ]
        
        if persist:
            updates = [{"id": nid, "val": score} for nid, score in scores.items()]
            with self.clients.neo4j.session(database=self.settings.neo4j.database) as session:
                self._persist_property(session, updates, "score_centralidad")
        
        return results

    def _betweenness_networkx(self, project_id: str, persist: bool) -> List[Dict[str, Any]]:
        """Betweenness Centrality con NetworkX."""
        _logger.info("graph_algorithms.betweenness", engine="networkx", project_id=project_id)
        
        G, node_props = self._extract_graph_data(project_id)
        if not G.nodes():
            return []
        
        scores = nx.betweenness_centrality(G)
        sorted_nodes = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        results = [
            {
                "nombre": node_props[nid]["nombre"],
                "etiquetas": node_props[nid]["etiquetas"],
                "score": score
            }
            for nid, score in sorted_nodes if nid in node_props
        ]
        
        if persist:
            updates = [{"id": nid, "val": score} for nid, score in scores.items()]
            with self.clients.neo4j.session(database=self.settings.neo4j.database) as session:
                self._persist_property(session, updates, "score_intermediacion")
        
        return results

    def _leiden_python(self, project_id: str, persist: bool) -> List[Dict[str, Any]]:
        """Leiden con igraph + leidenalg (fallback Python)."""
        _logger.info("graph_algorithms.leiden", engine="python", project_id=project_id)
        
        try:
            import igraph as ig
            import leidenalg
        except ImportError:
            _logger.warning("graph_algorithms.leiden_fallback_to_louvain", 
                           reason="igraph/leidenalg not installed")
            return self._louvain_networkx(project_id, persist)
        
        G, node_props = self._extract_graph_data(project_id)
        if not G.nodes():
            return []
        
        # Convertir NetworkX a igraph
        edges = list(G.edges())
        nodes = list(G.nodes())
        node_to_idx = {n: i for i, n in enumerate(nodes)}
        
        ig_edges = [(node_to_idx[s], node_to_idx[t]) for s, t in edges if s in node_to_idx and t in node_to_idx]
        ig_graph = ig.Graph(n=len(nodes), edges=ig_edges, directed=False)
        
        # Ejecutar Leiden
        partition = leidenalg.find_partition(ig_graph, leidenalg.ModularityVertexPartition)
        
        results = []
        updates = []
        
        for idx, nid in enumerate(nodes):
            if nid in node_props:
                community = partition.membership[idx]
                results.append({
                    "nombre": node_props[nid]["nombre"],
                    "etiquetas": node_props[nid]["etiquetas"],
                    "community_id": community
                })
                updates.append({"id": nid, "val": community})
        
        results.sort(key=lambda x: (x["community_id"], x["nombre"]))
        
        if persist:
            with self.clients.neo4j.session(database=self.settings.neo4j.database) as session:
                self._persist_property(session, updates, "community_id")
        
        return results

    # =========================================================================
    # IMPLEMENTACIONES: Neo4j GDS
    # =========================================================================

    def _louvain_neo4j(self, project_id: str, persist: bool) -> List[Dict[str, Any]]:
        """Louvain con Neo4j GDS."""
        _logger.info("graph_algorithms.louvain", engine="neo4j_gds", project_id=project_id)
        
        from uuid import uuid4
        graph_name = f"louvain_{project_id}_{uuid4().hex[:8]}"
        
        with self.clients.neo4j.session(database=self.settings.neo4j.database) as session:
            try:
                # Crear proyección
                self._create_gds_projection(session, graph_name, project_id)
                
                # Ejecutar algoritmo
                if persist:
                    session.run(
                        "CALL gds.louvain.write($graph, {writeProperty: 'community_id'})",
                        graph=graph_name
                    ).consume()
                
                # Stream results
                query = """
                CALL gds.louvain.stream($graph)
                YIELD nodeId, communityId
                RETURN gds.util.asNode(nodeId).nombre AS nombre, 
                       labels(gds.util.asNode(nodeId)) AS etiquetas, 
                       communityId AS community_id
                ORDER BY communityId, nombre
                """
                results = [dict(r) for r in session.run(query, graph=graph_name)]
                
            finally:
                self._drop_gds_projection(session, graph_name)
        
        return results

    def _pagerank_neo4j(
        self, 
        project_id: str, 
        persist: bool,
        damping_factor: float,
        max_iterations: int
    ) -> List[Dict[str, Any]]:
        """PageRank con Neo4j GDS."""
        _logger.info("graph_algorithms.pagerank", engine="neo4j_gds", project_id=project_id)
        
        from uuid import uuid4
        graph_name = f"pagerank_{project_id}_{uuid4().hex[:8]}"
        
        with self.clients.neo4j.session(database=self.settings.neo4j.database) as session:
            try:
                self._create_gds_projection(session, graph_name, project_id)
                
                config = {
                    "dampingFactor": damping_factor,
                    "maxIterations": max_iterations
                }
                
                if persist:
                    config["writeProperty"] = "score_centralidad"
                    session.run(
                        "CALL gds.pageRank.write($graph, $config)",
                        graph=graph_name, config=config
                    ).consume()
                
                query = """
                CALL gds.pageRank.stream($graph, $config)
                YIELD nodeId, score
                RETURN gds.util.asNode(nodeId).nombre AS nombre, 
                       labels(gds.util.asNode(nodeId)) AS etiquetas, 
                       score
                ORDER BY score DESC
                """
                results = [dict(r) for r in session.run(query, graph=graph_name, config=config)]
                
            finally:
                self._drop_gds_projection(session, graph_name)
        
        return results

    def _betweenness_neo4j(self, project_id: str, persist: bool) -> List[Dict[str, Any]]:
        """Betweenness con Neo4j GDS."""
        _logger.info("graph_algorithms.betweenness", engine="neo4j_gds", project_id=project_id)
        
        from uuid import uuid4
        graph_name = f"betweenness_{project_id}_{uuid4().hex[:8]}"
        
        with self.clients.neo4j.session(database=self.settings.neo4j.database) as session:
            try:
                self._create_gds_projection(session, graph_name, project_id)
                
                if persist:
                    session.run(
                        "CALL gds.betweenness.write($graph, {writeProperty: 'score_intermediacion'})",
                        graph=graph_name
                    ).consume()
                
                query = """
                CALL gds.betweenness.stream($graph)
                YIELD nodeId, score
                RETURN gds.util.asNode(nodeId).nombre AS nombre, 
                       labels(gds.util.asNode(nodeId)) AS etiquetas, 
                       score
                ORDER BY score DESC
                """
                results = [dict(r) for r in session.run(query, graph=graph_name)]
                
            finally:
                self._drop_gds_projection(session, graph_name)
        
        return results

    def _leiden_neo4j(self, project_id: str, persist: bool) -> List[Dict[str, Any]]:
        """Leiden con Neo4j GDS."""
        _logger.info("graph_algorithms.leiden", engine="neo4j_gds", project_id=project_id)
        
        from uuid import uuid4
        graph_name = f"leiden_{project_id}_{uuid4().hex[:8]}"
        
        with self.clients.neo4j.session(database=self.settings.neo4j.database) as session:
            try:
                self._create_gds_projection(session, graph_name, project_id)
                
                if persist:
                    session.run(
                        "CALL gds.leiden.write($graph, {writeProperty: 'community_id'})",
                        graph=graph_name
                    ).consume()
                
                query = """
                CALL gds.leiden.stream($graph)
                YIELD nodeId, communityId
                RETURN gds.util.asNode(nodeId).nombre AS nombre, 
                       labels(gds.util.asNode(nodeId)) AS etiquetas, 
                       communityId AS community_id
                ORDER BY communityId, nombre
                """
                results = [dict(r) for r in session.run(query, graph=graph_name)]
                
            finally:
                self._drop_gds_projection(session, graph_name)
        
        return results

    def _create_gds_projection(self, session, graph_name: str, project_id: str) -> None:
        """Crea proyección GDS con filtro de proyecto."""
        node_query = f"""
                        MATCH (n)
                        WHERE n.project_id = '{project_id}'
                            AND (
                                n:Categoria OR (n:Codigo AND coalesce(n.status,'active') <> 'merged')
                            )
            RETURN id(n) AS id
        """
        rel_query = f"""
            MATCH (s)-[r:REL]->(t) 
                        WHERE s.project_id = '{project_id}' AND t.project_id = '{project_id}'
                            AND (NOT s:Codigo OR coalesce(s.status,'active') <> 'merged')
                            AND (NOT t:Codigo OR coalesce(t.status,'active') <> 'merged')
            RETURN id(s) AS source, id(t) AS target, type(r) AS type
        """
        session.run(
            "CALL gds.graph.project.cypher($graph_name, $node_query, $rel_query)",
            graph_name=graph_name,
            node_query=node_query,
            rel_query=rel_query,
        ).consume()

    def _drop_gds_projection(self, session, graph_name: str) -> None:
        """Elimina proyección GDS."""
        try:
            session.run("CALL gds.graph.drop($graph)", graph=graph_name).consume()
        except Exception:
            pass

    # =========================================================================
    # IMPLEMENTACIONES: Memgraph MAGE
    # =========================================================================

    def _louvain_memgraph(self, project_id: str, persist: bool) -> List[Dict[str, Any]]:
        """Louvain con Memgraph MAGE."""
        _logger.info("graph_algorithms.louvain", engine="memgraph_mage", project_id=project_id)

        # MAGE no tiene graph catalog, ejecuta directamente sobre nodos
        query = """
        MATCH (n)-[r:REL]-(m)
        WHERE n.project_id = $project_id AND m.project_id = $project_id
          AND (NOT n:Codigo OR coalesce(n.status,'active') <> 'merged')
          AND (NOT m:Codigo OR coalesce(m.status,'active') <> 'merged')
        WITH collect(n) AS nodes, collect(r) AS rels
        CALL community_detection.louvain(nodes, rels)
        YIELD node, community_id
        RETURN node.nombre AS nombre, labels(node) AS etiquetas, community_id
        ORDER BY community_id, nombre
        """

        try:
            with self.clients.neo4j.session(database=self.settings.neo4j.database) as session:
                results = [dict(r) for r in session.run(query, project_id=project_id)]

                if persist and results:
                    # Persist community_id
                    update_query = """
                    UNWIND $data AS row
                    MATCH (n) WHERE n.nombre = row.nombre AND n.project_id = $project_id
                    SET n.community_id = row.community_id
                    """
                    session.run(update_query, data=results, project_id=project_id).consume()

                return results
        except Exception as e:
            _logger.warning("graph_algorithms.mage_failed_fallback", algorithm="louvain", error=str(e))
            return self._louvain_networkx(project_id, persist)

    def _pagerank_memgraph(
        self, 
        project_id: str, 
        persist: bool,
        damping_factor: float,
        max_iterations: int
    ) -> List[Dict[str, Any]]:
        """PageRank con Memgraph MAGE."""
        _logger.info("graph_algorithms.pagerank", engine="memgraph_mage", project_id=project_id)

        query = """
        CALL pagerank.get()
        YIELD node, rank
        WHERE node.project_id = $project_id
          AND (NOT node:Codigo OR coalesce(node.status,'active') <> 'merged')
        RETURN node.nombre AS nombre, labels(node) AS etiquetas, rank AS score
        ORDER BY score DESC
        """

        try:
            with self.clients.neo4j.session(database=self.settings.neo4j.database) as session:
                results = [dict(r) for r in session.run(query, project_id=project_id)]
                
                if persist and results:
                    update_query = """
                    UNWIND $data AS row
                    MATCH (n) WHERE n.nombre = row.nombre AND n.project_id = $project_id
                    SET n.score_centralidad = row.score
                    """
                    session.run(update_query, data=results, project_id=project_id).consume()
                
                return results
        except Exception as e:
            _logger.warning("graph_algorithms.mage_failed_fallback", algorithm="pagerank", error=str(e))
            return self._pagerank_networkx(project_id, persist, damping_factor, max_iterations)

    def _betweenness_memgraph(self, project_id: str, persist: bool) -> List[Dict[str, Any]]:
        """Betweenness con Memgraph MAGE."""
        _logger.info("graph_algorithms.betweenness", engine="memgraph_mage", project_id=project_id)
        
        query = """
        CALL betweenness_centrality.get()
        YIELD node, betweenness_centrality
        WHERE node.project_id = $project_id
        RETURN node.nombre AS nombre, labels(node) AS etiquetas, betweenness_centrality AS score
        ORDER BY score DESC
        """
        
        try:
            with self.clients.neo4j.session(database=self.settings.neo4j.database) as session:
                results = [dict(r) for r in session.run(query, project_id=project_id)]
                
                if persist and results:
                    update_query = """
                    UNWIND $data AS row
                    MATCH (n) WHERE n.nombre = row.nombre AND n.project_id = $project_id
                    SET n.score_intermediacion = row.score
                    """
                    session.run(update_query, data=results, project_id=project_id).consume()
                
                return results
        except Exception as e:
            _logger.warning("graph_algorithms.mage_failed_fallback", algorithm="betweenness", error=str(e))
            return self._betweenness_networkx(project_id, persist)
