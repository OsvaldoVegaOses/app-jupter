# Análisis de Brechas y Potencial Tecnológico no Utilizado

> **Actualizado: Diciembre 2024** - Revisado contra estado actual del código

Este documento detalla las capacidades avanzadas de **Qdrant** y **Neo4j** y su estado de implementación actual.

---

## 1. Qdrant: Estado de Aprovechamiento

### ✅ Funcionalidades IMPLEMENTADAS

| Capacidad | Estado | Ubicación |
|-----------|--------|-----------|
| **Índices de filtrado** | ✅ Hecho | `qdrant_block.py:ensure_payload_indexes()` |
| **Filtros por proyecto** | ✅ Hecho | `project_id`, `archivo`, `speaker`, etc. |
| **Búsqueda semántica** | ✅ Hecho | `search_similar()` en `qdrant_block.py` |
| **Retry con backoff** | ✅ Hecho | 3 intentos, batch splitting |

### ⚠️ Funcionalidades PARCIALES

| Capacidad | Estado | Descripción |
|-----------|--------|-------------|
| **Discovery API** | ⚠️ Prep | Endpoint `/api/search/discover` preparado pero no usa triplete completo |
| **Recommendation API** | ❌ No | No hay feedback loop de relevancia |
| **Clustering dinámico** | ❌ No | No hay agrupación automática sin códigos |

### 📋 Próximos pasos Qdrant
1. Implementar `/api/discover` con triplete (positivo, negativo, explorar)
2. Añadir feedback de relevancia ("Irrelevante" → excluir similares)
3. Explorar clustering para codificación abierta automática

---

## 2. Neo4j: Estado de Aprovechamiento

### ✅ Funcionalidades IMPLEMENTADAS

| Capacidad | Estado | Ubicación |
|-----------|--------|-----------|
| **GDS Louvain (comunidades)** | ✅ Hecho | `axial.py:run_gds_analysis()` |
| **GDS PageRank (centralidad)** | ✅ Hecho | `axial.py:run_gds_analysis()` |
| **Persistencia GDS** | ✅ Hecho | Escribe `community_id` y `score_centralidad` en nodos |
| **Visualización en Frontend** | ✅ Hecho | `Neo4jExplorer.tsx` usa propiedades GDS |
| **Botones GDS en UI** | ✅ Hecho | "Detectar Comunidades" y "Calcular Importancia" |
| **Tamaño de nodos por centralidad** | ✅ Hecho | `nodeVal: score_centralidad * 50` |
| **Color por comunidad** | ✅ Hecho | `nodeAutoColorBy: community_id` |

### 📊 Código verificado (axial.py)

```python
# Louvain → community_id
prop_name = "community_id"

# PageRank → score_centralidad
prop_name = "score_centralidad"
write_property = "score_centralidad"
```

### 📊 Frontend verificado (Neo4jExplorer.tsx)

```typescript
// Tamaño por centralidad
nodeVal={(node) => {
  const score = node.raw.properties?.score_centralidad;
  return typeof score === 'number' ? score * 50 : 2;
}}

// Color por comunidad
nodeAutoColorBy={(node) => {
  const comm = node.raw.properties?.community_id;
  return comm !== undefined ? String(comm) : node.group;
}}
```

### ⚠️ Funcionalidades PARCIALES

| Capacidad | Estado | Descripción |
|-----------|--------|-------------|
| **GraphRAG completo** | ⚠️ Parcial | Requiere recorrer grafo para respuestas contextuales |
| **Link Prediction** | ❌ No | No hay predicción de relaciones faltantes |

### 📋 Próximos pasos Neo4j
1. Implementar consultas GraphRAG que recorran `Persona -> Edad -> Fragmento -> Código`
2. Explorar algoritmos de Link Prediction para sugerir relaciones axiales

---

## 3. Resumen de Brechas

| Área | Antes (Nov 2024) | Ahora (Dic 2024) |
|------|------------------|------------------|
| **GDS Persistente** | ❌ No guardaba en nodos | ✅ `community_id`, `score_centralidad` persistidos |
| **Visualización GDS** | ❌ Solo dibujo estático | ✅ Nodos dimensionados y coloreados por GDS |
| **Botones GDS en UI** | ❌ Solo CLI | ✅ Botones en Neo4jExplorer |
| **Índices Qdrant** | ❌ Faltaban campos | ✅ 9 campos indexados |
| **Discovery API** | ❌ No existía | ⚠️ Endpoint preparado |
| **GraphRAG** | ❌ Búsqueda texto plano | ⚠️ Parcialmente implementado |
| **Link Prediction** | ❌ No existía | ❌ Pendiente |
| **Clustering Qdrant** | ❌ No existía | ❌ Pendiente |

---

## 4. Hoja de Ruta Actualizada (Phase 5: Cognitive Engine)

### ✅ Completado (Dic 2024)
- [x] GDS Louvain y PageRank persistentes
- [x] Visualización con dimensiones y colores por GDS
- [x] Botones en UI para ejecutar algoritmos
- [x] Índices de filtrado completos en Qdrant

### 🔄 En Progreso
- [ ] GraphRAG para consultas contextuales
- [ ] Discovery API con triplete completo

### 📋 Pendiente
- [ ] Link Prediction para relaciones sugeridas
- [ ] Clustering dinámico para codificación automática
- [ ] Feedback de relevancia en búsqueda

---

*Última verificación: 13 Diciembre 2024*
*Archivos revisados: `axial.py`, `qdrant_block.py`, `Neo4jExplorer.tsx`*
