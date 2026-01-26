# Plan de Iteración: Fase 5 "Motor Cognitivo"

> **Actualizado:** Diciembre 2024 - Estado de implementación verificado

Este documento define los Sprints para transformar la aplicación de un "Repositorio de Datos" a un "Asistente de Investigación Activo".

---

## Sprint 5: El Grafo Vivo (Neo4j GDS & GraphRAG)

**Objetivo**: Que el grafo *genere* datos, no solo los guarde.

### Estado de Implementación

| Historia | Estado | Evidencia |
|----------|--------|-----------|
| Persistencia de Centralidad | ✅ COMPLETADO | `axial.py:score_centralidad` |
| Detección de Comunidades | ✅ COMPLETADO | `axial.py:community_id` |
| GraphRAG Chat | ⚠️ PARCIAL | Requiere inyección de subgrafos |

### Historias de Usuario

#### 1. ✅ Persistencia de Centralidad (COMPLETADO)
- *Como* investigador, *quiero* que los nodos calculen su importancia (PageRank)
- **Implementación**: `run_gds_analysis()` en `app/axial.py`
- **Propiedad**: `score_centralidad` persistida en nodos

#### 2. ✅ Detección de Comunidades (COMPLETADO)
- *Como* investigador, *quiero* ver qué códigos forman "clústeres"
- **Implementación**: Algoritmo Louvain en `app/axial.py`
- **Propiedad**: `community_id` persistida en nodos
- **UI**: Botón "Detectar Comunidades" en Neo4jExplorer

#### 3. ⚠️ GraphRAG Chat (PARCIAL)
- *Como* usuario del Chat, *quiero* respuestas con contexto de grafo
- **Estado**: Requiere inyección de subgrafos en prompt
- **Próximo paso**: Modificar `analysis.py` para incluir relaciones

### Frontend implementado

```typescript
// Neo4jExplorer.tsx
nodeVal: score_centralidad * 50     // Tamaño por PageRank
nodeAutoColorBy: community_id       // Color por Louvain
```

**Duración**: 2 semanas → ✅ Completado Dic 2024

---

## Sprint 6: Descubrimiento Semántico (Qdrant Discovery)

**Objetivo**: Exploración por conceptos abstractos.

### Estado de Implementación

| Historia | Estado | Evidencia |
|----------|--------|-----------|
| Navegación Triangulación | ⚠️ PREPARADO | Endpoint existe, falta triplete completo |
| Sugerencia de Códigos | ✅ COMPLETADO | `/api/coding/suggest` |
| Recomendación de Evidencia | ✅ COMPLETADO | Panel en CodingPanel |

### Historias de Usuario

#### 1. ⚠️ Navegación por Triangulación (PREPARADO)
- *Como* investigador, *quiero* buscar "X pero no Y"
- **Estado**: Endpoint preparado, falta implementar triplete
- **Tech Task**: Usar `client.discover()` de Qdrant

#### 2. ✅ Sugerencia de Códigos (COMPLETADO)
- *Como* codificador, *quiero* sugerencias semánticas
- **Implementación**: `POST /api/coding/suggest`
- **UI**: Pestaña "Sugerencias semánticas" en CodingPanel

#### 3. ✅ Recomendación de Evidencia (COMPLETADO)
- *Como* analista, *quiero* fragmentos similares
- **Implementación**: `suggest_similar_fragments()` en `coding.py`
- **UI**: Resultados en CodingPanel

**Duración**: 2 semanas → ⚠️ 80% completado

---

## Arquitectura de Soporte - ESTADO

| Pre-requisito | Estado | Evidencia |
|---------------|--------|-----------|
| Worker Asíncrono | ✅ Estable | `celery_worker.py` con Redis |
| Embeddings 3-large | ✅ Configurado | `AZURE_DEPLOYMENT_EMBED` |
| Retry logic | ✅ Implementado | Exponential backoff en Qdrant |
| Índices Qdrant | ✅ 9 campos | `ensure_payload_indexes()` |

---

## Próximos Pasos (Sprint 7+)

| Tarea | Prioridad | Estimación |
|-------|-----------|------------|
| GraphRAG completo | Alta | 1 semana |
| Discovery API triplete | Media | 3 días |
| Link Prediction | Baja | 1 semana |
| Clustering automático | Baja | 1 semana |

---

## Resumen de Progreso

| Sprint | Objetivo | Estado |
|--------|----------|--------|
| Sprint 5 | Grafo Vivo | ✅ 90% |
| Sprint 6 | Descubrimiento | ⚠️ 80% |
| Sprint 7 | GraphRAG + Link Pred | 📋 Pendiente |

---

*Última verificación: 13 Diciembre 2024*
