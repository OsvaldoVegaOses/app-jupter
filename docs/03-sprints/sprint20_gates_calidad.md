# Sprint 20: Gates de Calidad para Flujo de Codificación

**Fecha inicio:** 2025-12-27  
**Fecha fin:** 2025-12-27  
**Duración real:** ~20min  
**Estado:** ✅ COMPLETADO (T1)  
**Prioridad:** 🟡 MEDIA

---

## Objetivo

Implementar gates de calidad que prevengan degradación del proceso de codificación.

---

## Brechas a Cerrar

| ID | Brecha | Descripción |
|----|--------|-------------|
| B5 | Gate de backlog | Bloquear análisis nuevo si hay demasiados códigos pendientes |
| B6 | Doble validación | Implementar verificación de consistencia inter-rater |

---

## Tareas

| ID | Tarea | Archivo | Estado |
|----|-------|---------|--------|
| T1 | Gate: bloquear análisis si backlog > umbral | `backend/app.py` | ⏳ |
| T2 | Endpoint health check mejorado | `backend/app.py` | ⏳ |
| T3 | Doble validación UI | `frontend/*` | ⏳ |
| T4 | Tests de gates | `tests/` | ⏳ |

---

## T1: Gate de Backlog

### Lógica

Cuando se invoca `/api/analyze`, verificar:
1. Contar códigos candidatos pendientes
2. Si `count > BACKLOG_THRESHOLD` (default: 100), rechazar con mensaje

### Implementación

```python
# backend/app.py - en api_analyze()
BACKLOG_THRESHOLD = int(os.getenv("CANDIDATE_BACKLOG_THRESHOLD", "100"))

# Al inicio del endpoint:
pending_count = get_pending_candidates_count(clients.postgres, project)
if pending_count > BACKLOG_THRESHOLD:
    raise HTTPException(
        status_code=429,
        detail={
            "code": "BACKLOG_LIMIT_EXCEEDED",
            "message": f"Hay {pending_count} códigos pendientes de validar. "
                       f"Valida al menos {pending_count - BACKLOG_THRESHOLD} antes de analizar más.",
            "pending_count": pending_count,
            "threshold": BACKLOG_THRESHOLD,
        }
    )
```

---

## T2: Health Check Mejorado

Agregar indicadores de calidad al endpoint `/api/codes/candidates/health`:

- `pending_count`: Códigos pendientes
- `oldest_pending_age_hours`: Edad del más antiguo
- `can_analyze`: Boolean si se puede ejecutar análisis nuevo
- `recommendations`: Lista de acciones sugeridas

---

## T3: Doble Validación (Inter-rater)

### Concepto

Para códigos importantes (alta frecuencia o marcados como "requiere revisión"):
1. Mostrar alerta visual en la bandeja
2. Requerir memo obligatorio al validar
3. Opcionalmente: segunda validación por otro usuario

### Implementación Mínima

- Agregar campo `requires_review: boolean` en UI
- Si `occurrences > 5` o `score_confianza < 0.6`, marcar automáticamente
- Mostrar indicador visual (ícono ⚠️)

---

## Criterios de Aceptación

- [ ] Análisis rechazado si backlog > 100 pendientes
- [ ] Mensaje claro indica cuántos faltan validar
- [ ] Health endpoint muestra `can_analyze`
- [ ] Códigos con baja confianza marcados visualmente
