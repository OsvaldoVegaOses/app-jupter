# AUTH Task — Briefing+ (Anonimización contextual + gate de guardado)

**Fecha:** 2026-01-11  
**Estado:** Propuesto (Backlog)  
**Owner:** UX+Backend (ETAPA 3)  

## 1) Contexto
La sección **“Descripción de Entrevista (Briefing IA)”** se usa como preámbulo para:
- estructurar el análisis posterior,
- producir insumos para un **informe anonimizado**, y
- reducir sesgos (p.ej. anclaje) antes de codificación abierta.

Hoy existen guardas básicas (PII simple: email/teléfono/RUT + checkbox de confirmación), pero **no cubren identificación contextual**: topónimos, unidades vecinales, organizaciones, roles únicos, etc.

> Nota: esto es un **gate ético/metodológico**, no el auth API (X-API-Key) del sistema.

---

## 2) Objetivo
Implementar un **“AUTH gate”** para permitir guardar (y especialmente “validar”) briefings solo cuando:
1) se aplique **anonimización contextual** (o se declare explícitamente el nivel de anonimización), y
2) exista una **validación mínima** que reduzca sesgo confirmatorio (hipótesis con evidencia y búsqueda de contra-evidencia).

---

## 3) Alcance
### Frontend
- Componente: `frontend/src/components/AnalysisPanel.tsx`
- UX adicional:
  - Selector de nivel:
    - `Anonimización básica` (PII explícita)
    - `Anonimización contextual` (lugares/organizaciones/roles)
    - `Anonimización total` (para informes públicos)
  - Editor de **diccionario de reemplazos** por proyecto (mínimo: key→value).
  - Botón “**Aplicar anonimización**” con previsualización de cambios (diff simple o “antes/después” por campo).
  - Campos “Hipótesis (borrador)” con:
    - hipótesis,
    - 2 evidencias (IDs de fragmentos o referencias),
    - 1 evidencia contradictoria (o “pendiente”).
  - Checklist de validación pre-guardado.
  - Dos acciones:
    - “Guardar borrador” (permitido con gate mínimo)
    - “Guardar como validado” (requiere checklist completo)

### Backend
- Endpoint: `POST /api/analyze/persist`
- Requisito: tolerar/almacenar `analysis_result.briefing` extendido (sin romper compatibilidad con payloads antiguos).
- (Opcional, recomendado) Validación server-side “suave”:
  - si `briefing.validated=true`, exigir `briefing.anonymization_level` y checklist completo.

---

## 4) Diseño de datos (propuesta)
Se persiste dentro de `analysis_result.briefing` (JSON) para no requerir migración inmediata:

```json
{
  "briefing": {
    "draft": true,
    "validated": false,
    "anonymization_level": "contextual",
    "anonymization_confirmed": true,
    "replacements": {
      "La Florida": "Comuna_X",
      "UV 20": "Unidad_Vecinal_XX",
      "Puente Alto": "Comuna_colindante_Y"
    },
    "hypotheses": [
      {
        "text": "Desgaste comunitario por historia prolongada",
        "support_fragment_ids": ["12", "23"],
        "counter_fragment_id": "45",
        "notes": "Buscar matices en relatos de expectativa"
      }
    ],
    "checklist": {
      "contextual_anonymization_applied": true,
      "non_focal_segments_tagged": false,
      "minimal_temporality_present": false,
      "actors_generic": true,
      "each_hypothesis_has_2_support": true,
      "each_hypothesis_has_counter": false,
      "concepts_categorized": false,
      "questions_written": false
    }
  }
}
```

---

## 5) Criterios de aceptación
### A. Anonimización contextual
- Dado un briefing con topónimos/organizaciones, cuando el usuario activa `Anonimización contextual`, entonces:
  - el UI ofrece un diccionario de reemplazos editable,
  - se puede previsualizar el resultado anonimizado,
  - al guardar, se persiste **el texto anonimizado** en `briefing.*` (y no se sobreescribe el DOCX).

### B. Gate de guardado
- Si hay indicios de PII/contexto identificable y `anonimization_confirmed=false`, entonces “Guardar” se bloquea.
- “Guardar como validado” solo se habilita cuando el checklist mínimo está completo.

### C. Anti-sesgo (hipótesis con evidencia)
- Para marcar `validated=true`, cada hipótesis debe tener:
  - 2 fragmentos de apoyo y
  - 1 fragmento contradictorio (o una marca explícita “pendiente”, que impediría validación).

### D. Compatibilidad
- Payloads antiguos (sin `briefing`) siguen persistiendo sin error.

---

## 6) Notas de implementación (orden sugerido)
1) Añadir `anonymization_level` + `replacements` + “Aplicar anonimización” (solo briefing fields).
2) Añadir checklist + dos botones (guardar borrador vs validar).
3) Añadir hipótesis con evidencia (IDs manuales al inicio; automatización futura).
4) Validación server-side opcional para `validated=true`.

---

## 7) Fuera de alcance (por ahora)
- NER completo (spaCy/Presidio) y redacción automática del texto fuente.
- Reescritura/anónimo “end-to-end” del DOCX original.
- Clasificación automática de “segmentos no focales” por fragmento (requiere heurísticas + UI de etiquetado).
