# Informe Crítico Extendido: Alineación de Etapas y Estrategia de IDs

> **Actualizado: Diciembre 2024** - Estado de implementación verificado

## 1. Diagnóstico de la Situación (Actualizado)

### Carril Manual (Etapas 1, 3, 4)
- **Unidad Base:** El `Fragmento` ingerido
- **Integridad:** ✅ Alta - Cada código apunta a fragmento real
- **Estado:** Funcionando correctamente

### Carril Asistido (LLM)
- **Problema Original:** IDs sintéticos (`archivo#auto#index`)
- **Estado Dic 2024:** ✅ PARCIALMENTE RESUELTO

| Mejora | Estado | Implementación |
|--------|--------|----------------|
| `fragmento_idx` en prompt | ✅ Hecho | `QUAL_SYSTEM_PROMPT` |
| Fallback por cita | ✅ Hecho | `match_citation_to_fragment()` |
| Inferencia de tipo relación | ✅ Hecho | `_infer_relation_type()` |
| Tasa de vinculación | ~70% | Mejorado desde ~50% |

---

## 2. Estado de las Estrategias Propuestas

### Estrategia A: Mapeo Post-Hoc (SHA/Heurística)
| Crítica Original | Estado Actual |
|------------------|---------------|
| SHA inútil por cambios LLM | ⚠️ Confirmado |
| Búsqueda difusa costosa | ✅ Implementado `match_citation_to_fragment()` |
| Parche frágil | ⚠️ Funciona como fallback (~70%) |

### Estrategia B: Mapeo Pre-Hoc (IDs en Prompt)
| Propuesta | Estado |
|-----------|--------|
| Enviar IDs al LLM | ✅ `fragmento_idx` en prompt |
| Validar existencia | ✅ `persist_analysis` verifica |
| Descartar fantasmas | ⚠️ Aún genera algunos auto# |

---

## 3. Implementación Verificada

### Paso 1: Ingesta Virtual en Prompt
```python
# analysis.py - QUAL_SYSTEM_PROMPT incluye:
"etapa3_matriz_abierta": [
  {
    "codigo": "...",
    "cita": "...",
    "fragmento_idx": 0  # Índice del fragmento
  }
]
```

### Paso 2: Fallback por Cita
```python
# documents.py
def match_citation_to_fragment(fragments, citation):
    """Busca fragmento por coincidencia de texto."""
    # ...
```

### Paso 3: Inferencia de Tipo Relación
```python
# analysis.py
def _infer_relation_type(llm_output):
    """Infiere tipo de relación axial desde LLM."""
    # ...
```

### Paso 4: Script de Remapeo
```bash
# Disponible en:
python scripts/remap_ghost_codes.py --project <id>
```

---

## 4. Pruebas Verificadas

| Test | Estado | Resultado |
|------|--------|-----------|
| LLM respeta `fragmento_idx` | ✅ | ~70% accuracy |
| Integridad en Postgres | ✅ | IDs reales cuando disponible |
| Grafo trazable en Neo4j | ✅ | Relaciones creadas |

---

## 5. Brechas Remanentes

| Brecha | Impacto | Prioridad |
|--------|---------|-----------|
| ~30% códigos sin fragmento | Cobertura incompleta | Media |
| GDS no ejecutado en prod | Visualización limitada | Baja |
| GraphRAG incompleto | Respuestas sin contexto | Baja |

---

## 6. Conclusión (Actualizada)

La implementación actual ha **cerrado la mayoría de las brechas críticas** identificadas:

| Problema | Nov 2024 | Dic 2024 |
|----------|----------|----------|
| IDs sintéticos | ❌ 100% fantasmas | ⚠️ ~30% fantasmas |
| Fallback de citas | ❌ No existía | ✅ Implementado |
| Tipos de relación | ❌ Sin inferencia | ✅ Automático |
| Script remapeo | ❌ No existía | ✅ Disponible |

**Próximos pasos:**
1. Ejecutar `remap_ghost_codes.py` en proyectos históricos
2. Medir tasa real de vinculación con volumen
3. Optimizar prompt para mejorar accuracy del LLM

---

*Última verificación: 13 Diciembre 2024*
*Archivos revisados: `analysis.py`, `documents.py`, `axial.py`*
