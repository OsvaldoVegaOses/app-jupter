# Estrategia de Grafos: Neo4j + Memgraph Fallback

> **Documento creado**: 25 Diciembre 2025  
> **Propósito**: Definir estrategia de licencias, servicios avanzados y fallback para APP_Jupter

---

## 1. Resumen de Licencias

### 1.1 Opciones Evaluadas

| Motor | Licencia | Costo | ¿Válido para SaaS Comercial? | Notas |
|-------|----------|-------|------------------------------|-------|
| **Neo4j Community** | GPLv3 | $0 | ⚠️ Problemático | Requiere código GPL si distribuyes |
| **Neo4j Enterprise** | Comercial | $$$ | ✅ Sí | Negociable / Startup Program |
| **Neo4j Aura** | Comercial | $65-200/mes | ✅ Sí | Managed cloud |
| **Memgraph Community** | BSL 1.1 | $0 | ✅ **SÍ** | Válido si es componente interno |
| **Memgraph Enterprise** | Comercial | $$$ | ✅ Sí | Negociable |

### 1.2 Memgraph BSL: Usos Permitidos

| Uso | ¿Permitido? | Explicación |
|-----|-------------|-------------|
| Vender APP_Jupter como SaaS | ✅ **SÍ** | Memgraph es componente interno |
| Cobrar suscripción mensual | ✅ **SÍ** | El valor es la app, no la DB |
| Instalar en servidores de clientes | ✅ **SÍ** | Parte integral de la solución |
| Ofrecer Memgraph como servicio standalone | ❌ **NO** | Competiría con Memgraph Cloud |
| Revender Memgraph como DBaaS | ❌ **NO** | Uso excluido en BSL |
| Crear producto competidor | ❌ **NO** | Licencia lo prohíbe |

### 1.3 Neo4j Startups Program

**Beneficios disponibles:**
- Hasta **$16,000 USD** en créditos Aura
- Licencia Enterprise gratis
- Consultoría técnica con ingenieros Neo4j

**Requisitos:**
- ≤50 empleados
- <$3M USD ingresos anuales
- Entre pre-seed y Series B
- Website y LinkedIn activos

**URL**: [neo4j.com/startups](https://neo4j.com/startups/)

---

## 2. Servicios Avanzados de Neo4j (Diferenciales)

### 2.1 Servicios YA Implementados en APP_Jupter

| Servicio | Módulo | Estado | Impacto en Negocio |
|----------|--------|--------|-------------------|
| CRUD Cypher | `neo4j_block.py` | ✅ Completo | Base operativa |
| Constraints/Indexes | `neo4j_block.py` | ✅ Completo | Integridad datos |
| GraphRAG | `graphrag.py` | ✅ Completo | **Diferenciador clave** |
| Link Prediction (manual) | `link_prediction.py` | ✅ Completo | Descubrimiento relaciones |
| **Louvain** (GDS) | `axial.py:196-340` | ✅ Completo | Comunidades temáticas |
| **PageRank** (GDS) | `axial.py:196-340` | ✅ Completo | Códigos nucleares |
| **Betweenness** (GDS) | `axial.py:196-340` | ✅ Completo | Códigos puente |

> **Nota**: Los algoritmos GDS (Louvain, PageRank, Betweenness) ya tienen fallback a **NetworkX** implementado en `axial.py`.

### 2.2 Servicios GDS Pendientes de Implementar

| Algoritmo | Descripción | Valor para APP_Jupter | Prioridad |
|-----------|-------------|----------------------|-----------|
| **Leiden** | Comunidades (mejor que Louvain) | Clusters más precisos | 🟡 Media |
| **Node2Vec** | Embeddings de grafo | Similitud estructural de códigos | 🟡 Media |
| **HDBSCAN** | Clustering por densidad | Agrupación flexible | 🟢 Baja |
| **K-Means** | Clustering clásico | Agrupación rápida | 🟢 Baja |
| **Shortest Path** | Caminos entre nodos | Conexiones concepto A→B | 🟡 Media |

### 2.3 Funcionalidades Enterprise NO Disponibles en Community

| Funcionalidad | Impacto | ¿Necesario ahora? |
|---------------|---------|-------------------|
| Clustering/HA | Alta disponibilidad | 🟢 No (pre-funding) |
| RBAC granular | Seguridad multi-tenant | 🟡 Fase 3 |
| Backup online | Recuperación sin downtime | 🟡 Producción |
| Unlimited cores (GDS) | Performance | 🟢 No (datasets pequeños) |

---

## 3. Compatibilidad Neo4j GDS vs Memgraph MAGE

> ⚠️ **IMPORTANTE**: Neo4j GDS usa `gds.graph.project.cypher()` para crear proyecciones. Esta API **NO existe en Memgraph MAGE**. El fallback para Memgraph requiere:
> 1. Extraer datos con Cypher estándar (compatible)
> 2. Ejecutar algoritmo MAGE directamente sobre nodos (sin proyección)
> 3. O usar fallback Python (NetworkX/igraph) que ya está implementado en `axial.py`

### 3.1 Algoritmos con Fallback Directo

| Algoritmo | Neo4j GDS | Memgraph MAGE | Compatibilidad | Notas |
|-----------|-----------|---------------|----------------|-------|
| **Louvain** | `gds.louvain` | `community_detection.louvain` | ✅ 95% | API similar |
| **PageRank** | `gds.pageRank` | `pagerank.get` | ✅ 95% | Parámetros similares |
| **Betweenness** | `gds.betweenness` | `betweenness_centrality.get` | ✅ 90% | Disponible |
| **Label Propagation** | `gds.labelPropagation` | `community_detection.label_propagation` | ✅ 90% | Disponible |
| **Weakly Connected** | `gds.wcc` | `weakly_connected_components.get` | ✅ 95% | Equivalente |
| **Shortest Path** | `gds.shortestPath` | `path.dijkstra` | ✅ 85% | Diferente API |

### 3.2 Algoritmos con Fallback Parcial o Python

| Algoritmo | Neo4j GDS | Memgraph MAGE | Fallback Python | Librería |
|-----------|-----------|---------------|-----------------|----------|
| **Node2Vec** | `gds.node2vec` | `node2vec_online.get` | ⚠️ Parcial | MAGE versión streaming |
| **Leiden** | `gds.leiden` | ❌ No | ✅ **igraph + leidenalg** | Ver sección 3.4 |
| **HDBSCAN** | `gds.hdbscan` | ❌ No | ✅ **hdbscan** | Ver sección 3.4 |
| **K-Means** | `gds.kmeans` | ❌ No | ✅ **scikit-learn** | Ver sección 3.4 |

### 3.3 Ventajas Exclusivas de Memgraph MAGE

| Funcionalidad | Descripción | Valor para APP_Jupter |
|---------------|-------------|----------------------|
| **Dynamic PageRank** | Actualización incremental | Análisis en tiempo real |
| **Online Node2Vec** | Embeddings streaming | Recomendaciones dinámicas |
| **LabelRankT** | Comunidades dinámicas | Evolución de temas |

### 3.4 Fallbacks Python para Algoritmos sin Soporte en Memgraph

Para los algoritmos que Neo4j GDS soporta pero Memgraph MAGE no, usamos librerías Python como fallback:

| Algoritmo | Neo4j GDS | Memgraph MAGE | Fallback Python | Librería |
|-----------|-----------|---------------|-----------------|----------|
| **Leiden** | `gds.leiden` | ❌ No | ✅ Sí | `igraph`, `leidenalg`, `CDlib` |
| **HDBSCAN** | `gds.hdbscan` | ❌ No | ✅ Sí | `hdbscan`, `scikit-learn` |
| **K-Means** | `gds.kmeans` | ❌ No | ✅ Sí | `scikit-learn` |

#### Implementación de Fallbacks

**Leiden (detección de comunidades mejorada):**
```python
# Fallback con igraph + leidenalg
import igraph as ig
import leidenalg

# Extraer grafo de Neo4j/Memgraph y convertir a igraph
G = ig.Graph.TupleList(edges, directed=False)
partition = leidenalg.find_partition(G, leidenalg.ModularityVertexPartition)
communities = partition.membership
```

**HDBSCAN (clustering jerárquico por densidad):**
```python
# Fallback con hdbscan
import hdbscan
import numpy as np

# Usar embeddings de nodos (Node2Vec o similares)
embeddings = np.array([...])  # Extraídos del grafo
clusterer = hdbscan.HDBSCAN(min_cluster_size=5)
cluster_labels = clusterer.fit_predict(embeddings)
```

**K-Means (clustering clásico):**
```python
# Fallback con scikit-learn
from sklearn.cluster import KMeans

embeddings = np.array([...])  # Embeddings de nodos
kmeans = KMeans(n_clusters=5, random_state=42)
cluster_labels = kmeans.fit_predict(embeddings)
```

#### Dependencias Adicionales

```bash
# Añadir a requirements.txt
igraph>=0.10.0
leidenalg>=0.9.0
hdbscan>=0.8.29
python-cdlib>=0.2.0
```

#### Flujo de Fallback

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     FLUJO DE DECISIÓN PARA ALGORITMOS                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ¿Neo4j GDS disponible?                                                        │
│       │                                                                         │
│       ├── SÍ → Usar gds.leiden / gds.hdbscan / gds.kmeans                      │
│       │                                                                         │
│       └── NO → ¿Memgraph MAGE disponible?                                       │
│                    │                                                            │
│                    ├── SÍ (Louvain, PageRank) → Usar MAGE                      │
│                    │                                                            │
│                    └── NO o algoritmo no soportado →                           │
│                         │                                                       │
│                         └── Fallback Python:                                    │
│                              ├── Leiden → igraph + leidenalg                   │
│                              ├── HDBSCAN → hdbscan library                     │
│                              └── K-Means → scikit-learn                        │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Estrategia Recomendada

### 4.1 Arquitectura de Fallback

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        ARQUITECTURA DE FALLBACK                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  Producción (con funding):                                                      │
│  ├── Primario: Neo4j Aura Pro ($65-200/mes) o Startup Program                  │
│  └── GDS: Louvain, PageRank, Betweenness, Node2Vec                             │
│                                                                                 │
│  Desarrollo / Demo (pre-funding):                                               │
│  ├── Primario: Memgraph Community (Docker, $0)                                 │
│  │   └── MAGE: Louvain, PageRank, Betweenness                                  │
│  └── Fallback: NetworkX (para demos sin Docker)                                │
│                                                                                 │
│  Código con abstracción:                                                        │
│  └── app/graph_algorithms.py (wrapper para Neo4j GDS / Memgraph MAGE / NetworkX)│
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Prioridad de Implementación

| Fase | Algoritmo | Motor | Impacto |
|------|-----------|-------|---------|
| **Fase 1** | Louvain (comunidades) | Neo4j GDS + Memgraph | Clusters temáticos |
| **Fase 1** | PageRank | Neo4j GDS + Memgraph | Códigos nucleares |
| **Fase 2** | Betweenness | Neo4j GDS + Memgraph | Códigos puente |
| **Fase 2** | Shortest Path | Neo4j GDS + Memgraph | Conexiones A→B |
| **Fase 3** | Node2Vec | Neo4j GDS | Embeddings estructurales |

### 4.3 Cambios de Código Necesarios

| Archivo | Cambio | Prioridad |
|---------|--------|-----------|
| `app/clients.py` | Detectar Memgraph vs Neo4j automáticamente | 🔴 Alta |
| `app/graph_algorithms.py` | **NUEVO**: Wrapper para GDS/MAGE/NetworkX | 🔴 Alta |
| `app/axial.py` | Usar wrapper en lugar de GDS directo | 🟡 Media |
| `docker-compose.yml` | Añadir servicio Memgraph | 🔴 Alta |

---

## 5. Configuración Docker (Memgraph)

```yaml
# docker-compose.memgraph.yml
version: '3.8'
services:
  memgraph:
    image: memgraph/memgraph-mage:latest
    ports:
      - "7687:7687"    # Bolt (compatible con driver Neo4j)
      - "7444:7444"    # Lab UI
    volumes:
      - memgraph-data:/var/lib/memgraph
    environment:
      - MEMGRAPH_USER=memgraph
      - MEMGRAPH_PASSWORD=secret
    command: ["--log-level=WARNING"]

volumes:
  memgraph-data:
```

**Comandos:**
```bash
# Levantar Memgraph
docker-compose -f docker-compose.memgraph.yml up -d

# Verificar conexión (usa mismo driver de Neo4j)
python -c "from neo4j import GraphDatabase; d=GraphDatabase.driver('bolt://localhost:7687'); print(d.verify_connectivity())"
```

---

## 6. Conclusión

### Decisión Recomendada

| Escenario | Motor Principal | Fallback |
|-----------|-----------------|----------|
| **Pre-funding** | Memgraph Community (BSL) | NetworkX |
| **Post-funding** | Neo4j Aura Pro o Startup Program | Memgraph |
| **Enterprise** | Neo4j Enterprise | N/A |

### Beneficios de esta Estrategia

1. **$0 de costo** durante desarrollo (Memgraph BSL es gratuito y válido para SaaS)
2. **Código compatible** (~95% de queries Cypher funcionan igual)
3. **Escalabilidad clara** hacia Neo4j cuando haya funding
4. **Sin vendor lock-in** gracias a capa de abstracción

---

## 7. Estado de Implementación (Sprint 28 - Enero 2026)

### ✅ Completado

**PostgreSQL como Fuente de Datos Fallback**

La estrategia de fallback ha sido completamente implementada en Sprint 28:

| Componente | Estado | Detalles |
|------------|--------|----------|
| **PostgreSQL Fallback** | ✅ Implementado | `link_prediction.py`, `graph_algorithms.py` |
| **Ingesta Resiliente** | ✅ Implementado | Neo4j opcional en `ingestion.py` |
| **Sync Diferida** | ✅ Implementado | `app/neo4j_sync.py` + endpoints admin |
| **Frontend UI** | ✅ Implementado | AdminPanel con sección Neo4j Sync |
| **Migración SQL** | ✅ Creada | `010_neo4j_sync_tracking.sql` |

**Arquitectura Final Implementada:**

```
┌────────────────────────────────────────────────────────────────┐
│              FLUJO DE DATOS RESILIENTE                         │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Graph Algorithms (link_prediction, Louvain, PageRank):       │
│    ┌──────────────┐                                           │
│    │ 1. Intenta   │ → Neo4j/Memgraph disponible?              │
│    │  Neo4j/MAGE  │      ├─ SÍ → Usa GDS/MAGE                 │
│    └──────────────┘      └─ NO → Fallback PostgreSQL          │
│                                                                │
│  Ingesta:                                                      │
│    ┌──────────────┐                                           │
│    │ PostgreSQL   │ → Siempre se ejecuta (datos maestros)     │
│    │ Qdrant       │ → Siempre se ejecuta (vectores)           │
│    │ Neo4j        │ → Opcional (marca neo4j_synced)           │
│    └──────────────┘                                           │
│                                                                │
│  Sincronización:                                               │
│    Admin Panel → sync_pending_fragments() → Neo4j              │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**Beneficios Logrados:**

1. ✅ **0% dependencia** de Neo4j para operaciones críticas (ingesta, análisis)
2. ✅ **Deployment simplificado** - PostgreSQL es suficiente para MVP
3. ✅ **Azure-ready** - Puede desplegarse sin Neo4j/Memgraph inicialmente
4. ✅ **Sync diferida** - Neo4j se puede añadir después sin perder datos
5. ✅ **Código unificado** - Mismo código funciona con/sin Neo4j

**Ver documentación completa:** [Sprint 28: Neo4j Resilience](../03-sprints/sprint28_neo4j_resilience.md)

---

*Documento creado: 25 Diciembre 2025*  
*Actualizado: 7 Enero 2026 - Sprint 28 Completado*
