# Sprint 10: Fallback de Grafos Neo4j → Memgraph → Python

> **Objetivo**: Implementar sistema de fallback robusto que permita operar sin Neo4j Desktop/Aura  
> **Duración estimada**: 2 semanas (10 días hábiles)  
> **Fecha inicio**: Enero 2025

---

## 🎯 Objetivos del Sprint

1. **Abstraer algoritmos existentes** → `axial.py` ya tiene Louvain/PageRank/Betweenness con fallback NetworkX; crear wrapper unificado
2. **Añadir soporte Memgraph MAGE** → Traducir llamadas GDS a API de MAGE (sin `gds.graph.project`)
3. **Implementar algoritmos pendientes** → Leiden, HDBSCAN, K-Means con fallback Python
4. **Detección automática** → El sistema detecta qué motor está disponible

> ⚠️ **Estado actual**: `axial.py:196-340` ya implementa Louvain, PageRank, Betweenness con fallback NetworkX. Este sprint extrae esa lógica a un wrapper reutilizable.

---

## 📋 Backlog del Sprint

### **Epic 1: Infraestructura de Fallback** (3 días)

| ID | Historia de Usuario | Criterio de Aceptación | Puntos |
|----|---------------------|------------------------|--------|
| F1.1 | **Como desarrollador**, quiero que `clients.py` detecte automáticamente si el motor es Neo4j o Memgraph | El driver se conecta correctamente a ambos motores usando el mismo código | 3 |
| F1.2 | **Como desarrollador**, quiero un docker-compose con Memgraph MAGE como alternativa | `docker-compose -f docker-compose.memgraph.yml up` levanta Memgraph funcional | 2 |
| F1.3 | **Como desarrollador**, quiero variables de entorno para configurar el motor de grafos | `GRAPH_ENGINE=memgraph` o `GRAPH_ENGINE=neo4j` controla qué motor usar | 2 |

### **Epic 2: Wrapper y Traducción GDS→MAGE** (4 días)

| ID | Historia de Usuario | Criterio de Aceptación | Puntos |
|----|---------------------|------------------------|--------|
| F2.1 | **NUEVO archivo** `app/graph_algorithms.py` que extrae lógica de `axial.py` | El archivo existe y reutiliza código existente de `axial.py:196-340` | 5 |
| F2.2 | Traducción **Louvain**: `gds.louvain` → `community_detection.louvain()` de MAGE | Louvain funciona con Memgraph sin `gds.graph.project` | 3 |
| F2.3 | Traducción **PageRank**: `gds.pageRank` → `pagerank.get()` de MAGE | PageRank funciona con Memgraph | 3 |
| F2.4 | Traducción **Betweenness**: `gds.betweenness` → `betweenness_centrality.get()` de MAGE | Betweenness funciona con Memgraph | 3 |
| F2.5 | **Eliminar dependencia de `gds.graph.project.cypher`** en wrapper | Algoritmos usan queries Cypher directas o NetworkX como fallback | 3 |

### **Epic 3: Algoritmos Avanzados (Python Fallback)** (3 días)

| ID | Historia de Usuario | Criterio de Aceptación | Puntos |
|----|---------------------|------------------------|--------|
| F3.1 | Implementar **Leiden** con fallback Python (igraph + leidenalg) | `graph_algorithms.leiden(project_id)` funciona aunque no haya Neo4j GDS | 3 |
| F3.2 | Implementar **HDBSCAN** con fallback Python (hdbscan library) | `graph_algorithms.hdbscan(embeddings)` agrupa nodos por densidad | 3 |
| F3.3 | Implementar **K-Means** con fallback Python (scikit-learn) | `graph_algorithms.kmeans(embeddings, k)` agrupa nodos en k clusters | 2 |
| F3.4 | Añadir dependencias a `requirements.txt` | igraph, leidenalg, hdbscan, cdlib instalables | 1 |

### **Epic 4: Integración con Código Existente** (2 días)

| ID | Historia de Usuario | Criterio de Aceptación | Puntos |
|----|---------------------|------------------------|--------|
| F4.1 | Refactorizar `app/axial.py` para usar el wrapper (extraer lógica existente) | `run_gds_analysis()` delega a `graph_algorithms` | 3 |
| F4.2 | Refactorizar `app/link_prediction.py` para usar el wrapper | Los algoritmos de predicción usan el wrapper | 3 |
| F4.3 | Actualizar `app/reports.py` para identificar núcleo con wrapper | `identify_nucleus_candidates()` usa PageRank/Betweenness del wrapper | 2 |

> **Nota técnica**: La lógica de fallback NetworkX ya existe en `axial.py:196-340`. El refactor extrae esta lógica al wrapper sin duplicar.

---

## 🏗️ Diseño Técnico

### Estructura del Wrapper

```python
# app/graph_algorithms.py

from enum import Enum
from typing import List, Dict, Any, Optional
import structlog

_logger = structlog.get_logger(__name__)

class GraphEngine(Enum):
    NEO4J_GDS = "neo4j_gds"
    MEMGRAPH_MAGE = "memgraph_mage"
    PYTHON_FALLBACK = "python_fallback"

class GraphAlgorithms:
    """Wrapper unificado para algoritmos de grafos con fallback automático."""
    
    def __init__(self, clients, settings):
        self.clients = clients
        self.settings = settings
        self.engine = self._detect_engine()
    
    def _detect_engine(self) -> GraphEngine:
        """Detecta qué motor de grafos está disponible."""
        try:
            # Intentar Neo4j GDS
            with self.clients.neo4j.session() as session:
                result = session.run("RETURN gds.version() AS version")
                version = result.single()
                if version:
                    _logger.info("graph_engine.detected", engine="neo4j_gds")
                    return GraphEngine.NEO4J_GDS
        except Exception:
            pass
        
        try:
            # Intentar Memgraph MAGE
            with self.clients.neo4j.session() as session:
                result = session.run("CALL mg.procedures() YIELD name RETURN name LIMIT 1")
                if result.single():
                    _logger.info("graph_engine.detected", engine="memgraph_mage")
                    return GraphEngine.MEMGRAPH_MAGE
        except Exception:
            pass
        
        _logger.warning("graph_engine.fallback", engine="python")
        return GraphEngine.PYTHON_FALLBACK
    
    def louvain(self, project_id: str) -> Dict[str, int]:
        """Detecta comunidades usando Louvain."""
        if self.engine == GraphEngine.NEO4J_GDS:
            return self._louvain_neo4j(project_id)
        elif self.engine == GraphEngine.MEMGRAPH_MAGE:
            return self._louvain_memgraph(project_id)
        else:
            return self._louvain_python(project_id)
    
    def pagerank(self, project_id: str) -> Dict[str, float]:
        """Calcula PageRank de nodos."""
        # Similar pattern...
        pass
    
    def leiden(self, project_id: str) -> Dict[str, int]:
        """Detecta comunidades usando Leiden (mejor que Louvain)."""
        if self.engine == GraphEngine.NEO4J_GDS:
            return self._leiden_neo4j(project_id)
        else:
            # Leiden no disponible en Memgraph, usar Python directamente
            return self._leiden_python(project_id)
    
    def hdbscan(self, embeddings: List[List[float]], min_cluster_size: int = 5) -> List[int]:
        """Clustering jerárquico por densidad."""
        # Solo disponible en Python fallback
        return self._hdbscan_python(embeddings, min_cluster_size)
    
    def kmeans(self, embeddings: List[List[float]], n_clusters: int = 5) -> List[int]:
        """Clustering K-Means."""
        # Solo disponible en Python fallback
        return self._kmeans_python(embeddings, n_clusters)
```

### Variables de Entorno

```env
# .env
GRAPH_ENGINE=auto  # auto | neo4j | memgraph | python
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

### Docker Compose para Memgraph

```yaml
# docker-compose.memgraph.yml
version: '3.8'
services:
  memgraph:
    image: memgraph/memgraph-mage:latest
    ports:
      - "7687:7687"
      - "7444:7444"
    volumes:
      - memgraph-data:/var/lib/memgraph
    environment:
      - MEMGRAPH_USER=memgraph
      - MEMGRAPH_PASSWORD=memgraph
    command: ["--log-level=WARNING"]
    healthcheck:
      test: ["CMD", "mg_client", "--host", "localhost", "--port", "7687", "-c", "RETURN 1"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  memgraph-data:
```

---

## ✅ Criterios de Aceptación del Sprint

### Funcionales

1. `python main.py --env .env axial gds` funciona aunque no haya Neo4j GDS
2. El sistema detecta automáticamente Memgraph si Neo4j no está disponible
3. Los algoritmos Leiden, HDBSCAN y K-Means funcionan con librerías Python
4. No hay cambios en la API pública del backend

### No Funcionales

1. Tiempo de respuesta de algoritmos < 5 segundos para grafos de < 10,000 nodos
2. Logs claros indicando qué motor se está usando
3. Tests unitarios para cada backend del wrapper

---

## 🧪 Plan de Verificación

### Tests Unitarios (Nuevos)

```bash
# Crear: tests/test_graph_algorithms.py
pytest tests/test_graph_algorithms.py -v
```

| Test | Descripción |
|------|-------------|
| `test_detect_engine_neo4j` | Detecta Neo4j GDS cuando disponible |
| `test_detect_engine_memgraph` | Detecta Memgraph MAGE cuando disponible |
| `test_detect_engine_fallback` | Usa Python cuando ninguno disponible |
| `test_louvain_python` | Louvain funciona con igraph |
| `test_pagerank_python` | PageRank funciona con NetworkX |
| `test_leiden_python` | Leiden funciona con leidenalg |
| `test_hdbscan_python` | HDBSCAN funciona con librería hdbscan |
| `test_kmeans_python` | K-Means funciona con scikit-learn |

### Tests de Integración

```bash
# Con Memgraph levantado
docker-compose -f docker-compose.memgraph.yml up -d
pytest tests/test_graph_algorithms.py::test_integration_memgraph -v

# Sin ningún motor de grafos (Python puro)
docker-compose down
pytest tests/test_graph_algorithms.py::test_integration_python_only -v
```

### Verificación Manual

1. **Con Neo4j Aura (si disponible)**:
   ```bash
   export GRAPH_ENGINE=neo4j
   python main.py --env .env axial gds --algorithm louvain
   # Debe mostrar: "graph_engine.detected engine=neo4j_gds"
   ```

2. **Con Memgraph**:
   ```bash
   docker-compose -f docker-compose.memgraph.yml up -d
   export GRAPH_ENGINE=auto
   python main.py --env .env axial gds --algorithm louvain
   # Debe mostrar: "graph_engine.detected engine=memgraph_mage"
   ```

3. **Python puro**:
   ```bash
   docker-compose down
   export GRAPH_ENGINE=python
   python main.py --env .env axial gds --algorithm louvain
   # Debe mostrar: "graph_engine.fallback engine=python"
   ```

---

## 📊 Estimación de Esfuerzo

| Epic | Puntos | Días |
|------|--------|------|
| Epic 1: Infraestructura | 7 | 3 |
| Epic 2: Wrapper + Traducción GDS→MAGE | 17 | 4 |
| Epic 3: Algoritmos avanzados | 9 | 3 |
| Epic 4: Integración | 8 | 2 |
| **TOTAL** | **41** | **12 días** |

---

## 🚀 Definición de "Done"

- [ ] Código implementado y revisado
- [ ] Tests unitarios pasando (>80% cobertura del wrapper)
- [ ] Tests de integración pasando con Memgraph
- [ ] Documentación actualizada (`estrategia_grafos_fallback.md`)
- [ ] Variables de entorno documentadas en `.env.example`
- [ ] `requirements.txt` actualizado con nuevas dependencias
- [ ] PR aprobado y mergeado

---

## 📝 Notas Técnicas

### Dependencias a añadir

```
# requirements.txt (añadir)
igraph>=0.10.0
leidenalg>=0.9.0
hdbscan>=0.8.29
python-cdlib>=0.2.0
```

### Compatibilidad de Drivers

El driver `neo4j` de Python es compatible con Memgraph porque ambos usan protocolo Bolt:

```python
from neo4j import GraphDatabase

# Funciona igual para Neo4j y Memgraph
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("user", "pass"))
```

### Queries MAGE equivalentes a GDS

| Neo4j GDS | Memgraph MAGE |
|-----------|---------------|
| `CALL gds.louvain.stream(...)` | `CALL community_detection.louvain(...)` |
| `CALL gds.pageRank.stream(...)` | `CALL pagerank.get()` |
| `CALL gds.betweenness.stream(...)` | `CALL betweenness_centrality.get()` |

---

*Sprint creado: 25 Diciembre 2025*
