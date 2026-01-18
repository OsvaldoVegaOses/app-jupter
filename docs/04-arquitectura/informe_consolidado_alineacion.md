# Informe Consolidado: Estrategia de Alineación Manual y Asistida (Etapas 1-4)

> **Actualizado:** Diciembre 2024 - Estado de implementación verificado

## 1. Resumen Ejecutivo

Este documento consolida el análisis técnico sobre la integración entre el flujo de codificación manual y el asistido por IA. 

### Estado Dic 2024

| Estrategia | Estado | Resultado |
|------------|--------|-----------|
| **Pre-Hoc (fragmento_idx)** | ✅ Implementado | ~70% códigos vinculados |
| **Post-Hoc fallback** | ✅ Implementado | `match_citation_to_fragment()` |
| **Inferencia de tipos** | ✅ Implementado | `_infer_relation_type()` |
| **Script remapeo** | ✅ Disponible | `remap_ghost_codes.py` |

---

## 2. Diagnóstico del Sistema (Actualizado)

| Característica | Carril Manual | Carril Asistido | Estado |
|:---------------|:--------------|:----------------|:-------|
| **Unidad de Análisis** | `Fragmento` (UUID) | `fragmento_idx` + fallback | ✅ Alineados |
| **Integridad** | Alta | Media (~70%) | ⚠️ Mejorado |
| **Conectividad** | Neo4j + Qdrant + PG | PG + Neo4j (parcial) | ⚠️ En progreso |
| **GDS Analytics** | ✅ Funciona | ✅ Funciona | ✅ Resuelto |

**Mejoras implementadas:**
- El LLM ahora recibe índices de fragmentos
- Persistencia usa `fragmento_idx` cuando disponible
- Fallback por coincidencia de cita para casos sin índice

---

## 3. Estrategia Implementada: Enfoque Híbrido

### 3.1. Pre-Hoc (Principal)

```python
# QUAL_SYSTEM_PROMPT incluye:
"etapa3_matriz_abierta": [{
  "codigo": "...",
  "cita": "...",
  "fragmento_idx": 0  # Índice del fragmento
}]
```

### 3.2. Post-Hoc Fallback

```python
# documents.py
def match_citation_to_fragment(fragments, citation):
    """Busca fragmento por coincidencia de texto."""
    for idx, frag in enumerate(fragments):
        if citation in frag.get("fragmento", ""):
            return idx
    return None
```

### 3.3. Persistencia Robusta

```python
# analysis.py - persist_analysis
if fragmento_idx is not None and fragmento_idx < len(fragments):
    fragmento_id = fragments[fragmento_idx]["fragmento_id"]
else:
    # Fallback por cita
    matched_idx = match_citation_to_fragment(fragments, cita)
    if matched_idx is not None:
        fragmento_id = fragments[matched_idx]["fragmento_id"]
    else:
        fragmento_id = f"{archivo}#auto#{idx}"  # Último recurso
```

---

## 4. Plan de Implementación - ESTADO

### ✅ Fase 1: Refactorización del Prompt (COMPLETADO)
- [x] Prompt con `fragmento_idx`
- [x] `QUAL_SYSTEM_PROMPT` actualizado
- [x] Tipos de relación explícitos

### ✅ Fase 2: Validación en Persistencia (COMPLETADO)
- [x] Mapeo `fragmento_idx` → `fragmento_id`
- [x] Fallback `match_citation_to_fragment()`
- [x] Validación de existencia

### ✅ Fase 3: Migración de Datos Históricos (DISPONIBLE)
- [x] Script `scripts/remap_ghost_codes.py`
- [x] Búsqueda semántica por similitud
- [x] Umbral configurable

---

## 5. Métricas de Vinculación

| Métrica | Nov 2024 | Dic 2024 |
|---------|----------|----------|
| Códigos con fragmento real | ~50% | ~70% |
| Códigos fantasma | ~50% | ~30% |
| Relaciones axiales | ❌ No persistían | ✅ Persistidas |

---

## 6. Pruebas de Validación

### Integridad Referencial
```sql
SELECT COUNT(*) FROM analisis_codigos_abiertos 
WHERE fragmento_id NOT LIKE '%#auto#%';
-- Resultado: ~70% de registros
```

### Conectividad del Grafo
```cypher
MATCH (e:Entrevista)-[:TIENE_FRAGMENTO]->(f:Fragmento)
      -[:TIENE_CODIGO]->(c:Codigo)
RETURN e.nombre, count(c) AS codigos
```

### Recuperación Vectorial
```python
# Los códigos con fragmento_id real aparecen en:
POST /api/coding/suggest
```

---

## 7. GDS Analytics (Nuevo)

Con datos en Neo4j, GDS ahora funciona:

| Algoritmo | Propiedad | Estado |
|-----------|-----------|--------|
| Louvain | `community_id` | ✅ Operativo |
| PageRank | `score_centralidad` | ✅ Operativo |

Frontend visualiza con tamaño y color por GDS.

---

## 8. Próximos Pasos

| Acción | Prioridad |
|--------|-----------|
| Ejecutar `remap_ghost_codes.py` en proyectos históricos | Alta |
| Medir tasa real con volumen de producción | Media |
| Optimizar prompt para mejorar accuracy | Baja |

---

## 9. Conclusión

La adopción del enfoque híbrido (Pre-Hoc + Fallback) ha **unificado los carriles manual y asistido**. La tasa de vinculación mejoró de ~50% a ~70%, habilitando GDS analytics y búsqueda semántica sobre códigos generados por IA.

---

*Última verificación: 13 Diciembre 2024*
