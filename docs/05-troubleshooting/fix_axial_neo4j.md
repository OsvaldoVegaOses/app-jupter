# Corrección: Persistencia de Códigos Axiales a Neo4j

> **Actualizado:** Diciembre 2024  
> **Estado:** ✅ Implementado, Verificado y en Producción

---

## Resumen Ejecutivo

Se identificó y corrigió un bug crítico donde **ningún código axial del análisis LLM se persistía a Neo4j**. El problema era que el tipo de relación devuelto por el LLM no coincidía con los tipos válidos.

### Estado Actual

| Componente | Estado | Verificación |
|------------|--------|--------------|
| Persistencia axial | ✅ Funcionando | Logs: `analysis.axial.persisted` |
| Inferencia de tipos | ✅ Implementado | `_infer_relation_type()` |
| GDS Analytics | ✅ Disponible | Louvain y PageRank |
| Fallback a `partede` | ✅ Activo | Nunca falla por tipo inválido |

---

## Cambios Implementados

### 1. Prompt del LLM

**Archivo:** `app/analysis.py`

```json
"etapa4_axial": [{
  "categoria": "...",
  "codigos": ["..."],
  "tipo_relacion": "partede",  // Campo requerido
  "relaciones": ["A->B"],
  "memo": "..."
}]
```

Tipos válidos: `partede`, `causa`, `condicion`, `consecuencia`

### 2. Inferencia Inteligente

**Archivo:** `app/analysis.py`

```python
def _infer_relation_type(relaciones, memo):
    text = " ".join(relaciones).lower() + " " + (memo or "").lower()
    
    if any(kw in text for kw in ["causa", "provoca", "genera"]):
        return "causa"
    if any(kw in text for kw in ["condición", "requiere"]):
        return "condicion"
    if any(kw in text for kw in ["consecuencia", "resultado"]):
        return "consecuencia"
    
    return "partede"  # Default seguro
```

### 3. Persistencia Directa a Neo4j

**Antes:** Usaba `assign_axial_relation()` que requería ≥2 fragmentos codificados.

**Ahora:** Usa `merge_category_code_relationship()` directamente:

```python
merge_category_code_relationship(
    clients.neo4j,
    settings.neo4j.database,
    categoria=categoria,
    codigo=codigo,
    relacion=relacion,
    evidencia=[],
    memo=memo,
    project_id=project_id,
)
```

---

## GDS Analytics (Nuevo Dic 2024)

Una vez que hay datos en Neo4j, GDS está disponible:

### Algoritmos implementados

| Algoritmo | Propiedad | UI |
|-----------|-----------|-----|
| **Louvain** | `community_id` | Botón "Detectar Comunidades" |
| **PageRank** | `score_centralidad` | Botón "Calcular Importancia" |

### Visualización en Frontend

```typescript
// Neo4jExplorer.tsx
nodeVal: score_centralidad * 50    // Tamaño por centralidad
nodeAutoColorBy: community_id      // Color por comunidad
```

---

## Verificación

### Consulta Cypher

```cypher
MATCH (c:Categoria)-[r:REL]->(k:Codigo) 
RETURN c.nombre, r.tipo, k.nombre 
LIMIT 20
```

### Logs esperados

```
analysis.axial.persisted categoria=X codigo=Y relacion=partede
```

### Verificación GDS

```cypher
MATCH (n:Codigo) 
WHERE n.score_centralidad IS NOT NULL 
RETURN n.nombre, n.score_centralidad 
ORDER BY n.score_centralidad DESC 
LIMIT 10
```

---

## Impacto en el Sistema

| Componente | Antes | Ahora |
|------------|-------|-------|
| Análisis LLM | ❌ No persistía | ✅ Persiste con tipo válido |
| Neo4j Explorer | ❌ Sin datos | ✅ Grafo visible |
| GDS Analytics | ❌ Sin grafo | ✅ Louvain + PageRank |
| Visualización | ❌ Estática | ✅ Dinámica por centralidad |

---

## Compatibilidad

- ✅ Análisis existentes sin `tipo_relacion` usan inferencia
- ✅ Fallback a `partede` garantiza que nunca falle
- ✅ `assign_axial_relation()` sigue disponible para uso manual
- ✅ GDS funciona sin Neo4j GDS plugin (fallback NetworkX)

---

## Archivos Modificados

| Archivo | Descripción |
|---------|-------------|
| `app/analysis.py` | Prompt, inferencia, persistencia |
| `app/axial.py` | `partede` añadido a `ALLOWED_REL_TYPES` |
| `app/axial.py` | `run_gds_analysis()` con persistencia |
| `frontend/.../Neo4jExplorer.tsx` | Botones GDS, visualización |

---

*Última verificación: 13 Diciembre 2024*
