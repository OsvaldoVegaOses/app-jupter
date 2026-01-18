# Sprint 15: Gates Anti-Alucinaciones para GraphRAG

**Fecha inicio:** 2025-12-27  
**Fecha fin:** 2025-12-27  
**Duración real:** ~3h desarrollo  
**Estado:** ✅ COMPLETADO

---

## Objetivo

Implementar gates de validación sobre `graphrag_query()` que mejoren la confiabilidad de respuestas sin requerir nuevo frontend.

---

## Tabla Resumen

| Epic | Descripción | Esfuerzo | Estado |
|------|-------------|----------|--------|
| E1 | Gate de Evidencia Mínima | 4h | ✅ |
| E2 | Rechazo Seguro | 2h | ✅ |
| E3 | Contrato de Respuesta Estructurado | 4h | ✅ |
| E4 | Métricas Básicas | 2h | ✅ |

**Total:** 12h estimado → ~3h real

---

## E1: Gate de Evidencia Mínima (4h)

### Descripción
Validar que exista evidencia suficiente antes de generar respuesta.

### Criterios
- Rechazar si `top_score < 0.5`
- Rechazar si `fragments < 2`
- Umbral configurable via env var

### Archivos
- `app/graphrag.py` → `validate_evidence()`

---

## E2: Rechazo Seguro (2h)

### Descripción
Formato estructurado para cuando el sistema decide no responder.

### Formato
```json
{
    "is_grounded": false,
    "rejection": {
        "reason": "...",
        "suggestion": "..."
    }
}
```

### Criterios
- Respuesta clara y útil para el usuario
- Sugerencias de qué hacer

---

## E3: Contrato de Respuesta (4h)

### Descripción
Todas las respuestas incluyen evidencia citada obligatoria.

### Formato
```json
{
    "answer": "...",
    "evidence": [...],
    "confidence": "alta|media|baja",
    "is_grounded": true
}
```

### Criterios
- Prompt actualizado para forzar citas
- Cada evidencia con `archivo`, `fragmento_id`, `score`

---

## E4: Métricas Básicas (2h)

### Descripción
Registrar métricas de cada query para análisis posterior.

### Métricas
- `is_grounded`, `rejection_reason`
- `fragments_count`, `top_score`
- `confidence`, `response_length`

### Archivos
- `app/graphrag_metrics.py` (nuevo)
- `app/postgres_block.py` (tabla)
- `backend/app.py` (endpoint)

---

## Verificación

1. Query sin evidencia → rechaza correctamente
2. Query con evidencia → incluye citas
3. Métricas persisten
4. Frontend no se rompe

---

## Próximos Sprints

- **Sprint 16:** Verificador LLM
- **Sprint 17+:** Chat Enterprise
