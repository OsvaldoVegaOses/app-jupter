# Protocolo de Validación de Códigos Candidatos

**Versión:** 1.0  
**Fecha:** 2025-12-27

---

## 1. Propósito

Este protocolo establece criterios claros para validar códigos candidatos generados por:
- 🤖 **LLM**: Análisis automático de entrevistas
- 🔍 **Discovery**: Triangulación semántica
- 🔗 **Link Prediction**: Sugerencias por estructura de grafo
- ✋ **Manual**: Propuestas del investigador

---

## 2. Flujo de Validación

```
Código Candidato → Bandeja Pendiente → Validador
                                           │
              ┌────────────────────────────┼────────────────────────────┐
              │                            │                            │
              ▼                            ▼                            ▼
         ✅ VALIDAR                   🔄 FUSIONAR                   ❌ RECHAZAR
    (Código es nuevo y            (Es sinónimo de             (No aporta valor o
     tiene evidencia)              código existente)           es error de IA)
```

---

## 3. Criterios de Decisión

### 3.1 ¿Cuándo VALIDAR?

| Criterio | Condición |
|----------|-----------|
| **Evidencia** | La cita asociada respalda claramente el concepto |
| **Novedad** | No existe código similar (Levenshtein < 0.85) |
| **Relevancia** | El código aporta a la teoría emergente |
| **Consistencia** | Compatible con el sistema de códigos existente |

### 3.2 ¿Cuándo FUSIONAR?

| Criterio | Condición |
|----------|-----------|
| **Similitud alta** | Levenshtein ≥ 0.85 con código existente |
| **Mismo concepto** | Representa la misma idea con diferente nombre |
| **Ejemplos similares** | Las citas previas del código similar son relacionadas |

**Ejemplos de fusión:**
- `organizacion` → `organización` (tildes)
- `participacion_ciudadana` → `participacion_comunitaria` (sinónimos)
- `falta_de_recursos` → `escasez_recursos` (variantes)

### 3.3 ¿Cuándo RECHAZAR?

| Criterio | Condición |
|----------|-----------|
| **Sin evidencia** | La cita no respalda el código propuesto |
| **Alucinación IA** | El código menciona conceptos no presentes en el texto |
| **Demasiado genérico** | Código como "tema" o "idea" sin especificidad |
| **Demasiado específico** | Código que solo aplica a una cita |

---

## 4. Evidencia Mínima Requerida

| Fuente | Evidencia Mínima |
|--------|------------------|
| LLM | 1 cita textual del fragmento analizado |
| Discovery | 1 fragmento + score ≥ 0.55 |
| Link Prediction | Relación estructural + 1 ejemplo similar |
| Manual | 1 cita + memo justificativo |

---

## 5. Gestión del Backlog

### 5.1 Indicadores de Salud

| Indicador | Verde | Amarillo | Rojo |
|-----------|-------|----------|------|
| Pendientes | < 25 | 25-50 | > 50 |
| Días sin resolver | < 2 | 2-3 | > 3 |
| Tiempo medio resolución | < 24h | 24-48h | > 48h |

### 5.2 Gate de Análisis

El sistema bloquea nuevos análisis LLM si:
- Pendientes > 50
- Días sin resolver > 3

**Endpoint:** `GET /api/coding/gate`

```json
{
  "can_proceed": false,
  "reason": "Backlog saturado: 67 pendientes (máx: 50)",
  "recommendation": "Valide los candidatos pendientes antes de ejecutar nuevo análisis"
}
```

---

## 6. Registro de Decisiones

Cada validación debe incluir un **memo** que documente:

1. **Razón de la decisión** (1 línea)
2. **Relación con teoría emergente** (opcional)

**Ejemplo de memo:**
```
Validado: Concepto central en relatos de conflicto institucional. 
Se relaciona con categoría axial "Desconfianza en autoridades".
```

---

## 7. Doble Validación (Opcional)

Para códigos que emergen como nucleares (alta centralidad en grafo):

1. Primer validador: Revisa criterios básicos
2. Segundo validador: Confirma relevancia teórica
3. Discrepancia: Discusión en equipo

**Activar para:** Códigos con PageRank > 0.1 o betweenness > 0.15

---

*Documento generado como parte del cierre de Fase 1*
