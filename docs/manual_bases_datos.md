# Arquitectura de Bases de Datos

> **Guía técnica para usuarios del sistema de análisis cualitativo**

## 1. Visión General: La Triada de Datos

El sistema utiliza **tres bases de datos especializadas** que trabajan en conjunto para ofrecer capacidades complementarias de análisis cualitativo:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        TRIADA DE DATOS                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐            │
│   │ PostgreSQL  │      │   Neo4j     │      │   Qdrant    │            │
│   │ (Relacional)│◄────►│  (Grafo)    │◄────►│ (Vectores)  │            │
│   └─────────────┘      └─────────────┘      └─────────────┘            │
│         │                    │                    │                     │
│         ▼                    ▼                    ▼                     │
│   • Datos crudos       • Relaciones         • Búsqueda                 │
│   • Metadatos          • Comunidades          semántica                │
│   • Auditoría          • Centralidad        • Similitud                │
│   • Usuarios           • Navegación         • Discovery                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. PostgreSQL (Base de Datos Relacional)

### 2.1 Propósito
Almacena los **datos estructurados** del sistema: fragmentos de texto, códigos, metadatos de proyectos y usuarios.

### 2.2 Tablas Principales

| Categoría | Tabla | Descripción |
|-----------|-------|-------------|
| **Datos de Entrevistas** | `entrevista_fragmentos` | Fragmentos de texto extraídos de las entrevistas |
| **Codificación** | `analisis_codigos_abiertos` | Códigos asignados a fragmentos (codificación abierta) |
| | `codigos_candidatos` | Códigos propuestos pendientes de validación |
| | `codigo_versiones` | Historial de cambios en códigos |
| **Análisis** | `analisis_axial` | Relaciones axiales entre códigos |
| | `analisis_comparacion_constante` | Comparaciones constantes |
| | `analisis_nucleo_notas` | Notas de codificación selectiva |
| **Reportes** | `analysis_reports` | Informes de análisis generados |
| | `analysis_memos` | Memos analíticos del investigador |
| | `interview_reports` | Reportes por entrevista |
| | `doctoral_reports` | Reportes doctorales |
| **Proyectos** | `proyectos` | Proyectos de investigación |
| | `project_members` | Miembros de proyectos |
| | `project_audit_log` | Log de auditoría |
| | `proyecto_estado` | Estado actual de proyectos |
| **Usuarios** | `app_users` | Usuarios del sistema |
| | `app_sessions` | Sesiones activas |
| **Discovery** | `discovery_runs` | Ejecuciones del agente Discovery |
| | `discovery_navigation_log` | Log de navegación semántica |
| **Etapa 0** | `stage0_protocols` | Protocolos de investigación |
| | `stage0_actors` | Actores principales identificados |
| | `stage0_consents` | Consentimientos informados |
| | `stage0_sampling_criteria` | Criterios de muestreo |
| | `stage0_analysis_plans` | Planes de análisis |

### 2.3 Vistas Disponibles

| Vista | Descripción |
|-------|-------------|
| `vw_codigos_candidatos_stats` | Estadísticas de códigos candidatos por proyecto |
| `vw_interview_files_stats` | Estadísticas de archivos de entrevista |

---

## 3. Neo4j (Base de Datos de Grafos)

### 3.1 Propósito
Modela las **relaciones** entre entidades del análisis cualitativo, permitiendo:
- Navegación entre códigos y fragmentos
- Cálculo de comunidades (Louvain)
- Análisis de centralidad (PageRank)
- Visualización del grafo conceptual

### 3.2 Tipos de Nodos (Labels)

| Label | Descripción | Propiedades Clave |
|-------|-------------|-------------------|
| `Entrevista` | Archivo de entrevista | `nombre`, `project_id`, `metadata` |
| `Fragmento` | Unidad de texto analizada | `id`, `texto`, `par_idx`, `speaker`, `project_id` |
| `Codigo` | Código emergente | `nombre`, `project_id` |
| `Categoria` | Categoría conceptual | `nombre`, `project_id` |

### 3.3 Tipos de Relaciones

| Relación | Origen → Destino | Descripción |
|----------|------------------|-------------|
| `TIENE_FRAGMENTO` | Entrevista → Fragmento | Una entrevista contiene fragmentos |
| `CODIFICA` | Codigo → Fragmento | Un código codifica un fragmento |
| `PERTENECE_A` | Codigo → Categoria | Un código pertenece a una categoría |
| `RELACIONADO_CON` | Codigo → Codigo | Relación axial entre códigos |

### 3.4 Algoritmos GDS Disponibles

| Algoritmo | Uso |
|-----------|-----|
| **Louvain** | Detección de comunidades de códigos |
| **PageRank** | Identificar códigos más centrales |
| **Node Similarity** | Encontrar códigos similares por estructura |

---

## 4. Qdrant (Base de Datos Vectorial)

### 4.1 Propósito
Almacena **embeddings** (representaciones vectoriales) de los fragmentos para:
- Búsqueda semántica
- Discovery de patrones
- Sugerencias de códigos similares

### 4.2 Colecciones

| Colección | Vectores | Dimensiones | Modelo |
|-----------|----------|-------------|--------|
| `fragments` | 296 | 3072 | text-embedding-3-large |

### 4.3 Operaciones Principales

| Operación | Descripción |
|-----------|-------------|
| **Search** | Búsqueda por similitud coseno |
| **Discover** | Búsqueda con contexto positivo/negativo (Discovery API) |
| **Scroll** | Iteración sobre todos los vectores |

---

## 5. Flujo de Datos Entre Bases

```
┌────────────────────────────────────────────────────────────────────────┐
│                    FLUJO DE SINCRONIZACIÓN                             │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  INGESTA (DOCX)                                                        │
│       │                                                                │
│       ▼                                                                │
│  ┌─────────────┐                                                       │
│  │ PostgreSQL  │ ←── Almacena fragmentos + metadatos                   │
│  └─────────────┘                                                       │
│       │                                                                │
│       ├──────────────────┐                                             │
│       │                  │                                             │
│       ▼                  ▼                                             │
│  ┌─────────────┐    ┌─────────────┐                                    │
│  │   Neo4j     │    │   Qdrant    │                                    │
│  └─────────────┘    └─────────────┘                                    │
│       │                  │                                             │
│       │  Crea nodos      │  Almacena                                   │
│       │  Entrevista,     │  embeddings                                 │
│       │  Fragmento       │                                             │
│       │                  │                                             │
├───────┴──────────────────┴─────────────────────────────────────────────┤
│                                                                        │
│  CODIFICACIÓN                                                          │
│       │                                                                │
│       ▼                                                                │
│  ┌─────────────┐                                                       │
│  │ PostgreSQL  │ ←── Guarda asignación código-fragmento                │
│  └─────────────┘                                                       │
│       │                                                                │
│       ▼                                                                │
│  ┌─────────────┐                                                       │
│  │   Neo4j     │ ←── Crea nodo Codigo + relación CODIFICA              │
│  └─────────────┘                                                       │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Consultas de Referencia

### 6.1 PostgreSQL

```sql
-- Fragmentos de un proyecto
SELECT * FROM entrevista_fragmentos WHERE project_id = 'jd-007';

-- Códigos más frecuentes
SELECT codigo, COUNT(*) as frecuencia 
FROM analisis_codigos_abiertos 
WHERE project_id = 'jd-007'
GROUP BY codigo 
ORDER BY frecuencia DESC;

-- Cobertura de codificación
SELECT 
    COUNT(DISTINCT fragmento_id) as codificados,
    (SELECT COUNT(*) FROM entrevista_fragmentos WHERE project_id = 'jd-007') as total
FROM analisis_codigos_abiertos 
WHERE project_id = 'jd-007';
```

### 6.2 Neo4j (Cypher)

```cypher
-- Fragmentos de una entrevista
MATCH (e:Entrevista {project_id: 'jd-007'})-[:TIENE_FRAGMENTO]->(f:Fragmento)
RETURN e.nombre, count(f) as fragmentos;

-- Códigos y sus fragmentos
MATCH (c:Codigo {project_id: 'jd-007'})-[:CODIFICA]->(f:Fragmento)
RETURN c.nombre, count(f) as citas 
ORDER BY citas DESC LIMIT 10;

-- Grafo completo de un código
MATCH path = (c:Codigo {nombre: 'participacion_comunitaria'})-[*1..2]-(n)
WHERE c.project_id = 'jd-007'
RETURN path;
```

### 6.3 Qdrant (Python)

```python
# Búsqueda semántica
results = qdrant_client.search(
    collection_name="fragments",
    query_vector=embedding,
    limit=10,
    query_filter={"project_id": "jd-007"}
)

# Discovery con contexto
results = qdrant_client.discover(
    collection_name="fragments",
    target=target_id,
    context=[positive_id],
    limit=5
)
```

---

## 7. Mantenimiento y Sincronización

### 7.1 Verificar Coherencia

Ejecutar el script de verificación:
```powershell
python db_coherence_check.py
```

### 7.2 Indicadores de Salud

| Indicador | Valor Esperado |
|-----------|----------------|
| Fragmentos PG = Neo4j = Qdrant | ✅ Iguales |
| Códigos PG ⊆ Neo4j | ✅ Todos en Neo4j |
| Relaciones CODIFICA = Asignaciones PG | ✅ Iguales |
| Relaciones TIENE_FRAGMENTO = Fragmentos | ✅ Iguales |

### 7.3 Acciones Correctivas

| Problema | Solución |
|----------|----------|
| Fragmentos sin embedding | Re-ejecutar ingesta |
| Códigos solo en PG | Ejecutar sync Neo4j |
| Relaciones faltantes | Ejecutar resync_relations |
| Registros con fragmento_id vacío | Eliminar de analisis_codigos_abiertos |

### 7.4 Validaciones Automáticas Implementadas

El sistema ahora incluye validaciones automáticas para prevenir incoherencias:

```python
# En upsert_open_codes(): Filtra automáticamente registros inválidos
valid_data = [row for row in rows 
              if row[1] is not None and row[1] != '' and len(str(row[1])) > 10]

# En promote_to_definitive(): Excluye candidatos sin fragmento válido
WHERE fragmento_id IS NOT NULL AND fragmento_id != '' AND LENGTH(fragmento_id) > 10
```

**Protecciones activas:**
- ✅ No se insertan códigos con `fragmento_id` vacío o NULL
- ✅ No se promueven candidatos de `link_prediction` (que no tienen fragmento asociado)
- ✅ Los candidatos de `link_prediction` permanecen solo en `codigos_candidatos` para referencia

---

## 8. Estadísticas Actuales (Proyecto jd-007)

### 8.1 Volumen de Datos

| Base de Datos | Entidad | Cantidad |
|---------------|---------|----------|
| **PostgreSQL** | Fragmentos | 296 |
| | Códigos asignados | 361 |
| | Códigos únicos | 325 |
| | Candidatos | ~400 |
| **Neo4j** | Nodos Fragmento | 296 |
| | Nodos Codigo | 325 |
| | Nodos Entrevista | 14 |
| | Nodos Categoria | 52 |
| | Rel TIENE_FRAGMENTO | 296 |
| | Rel CODIFICA | 361 |
| **Qdrant** | Vectores | 296 |

### 8.2 Estado de Coherencia

| Verificación | Estado |
|--------------|--------|
| Fragmentos sincronizados (PG-Neo4j-Qdrant) | ✅ 100% |
| Entrevistas sincronizadas | ✅ 100% |
| Códigos sincronizados | ✅ 100% |
| Relaciones CODIFICA = Asignaciones PG | ✅ 100% |
| Códigos huérfanos en Neo4j | ✅ 0 |
| **Índice de Coherencia Global** | **100%** |

---

*Documento actualizado: Enero 2026 - Post corrección de coherencia*
