# Sprint 31: Cobertura 100% - Codificación de Fragmentos Pendientes

> **Fecha:** 2026-01-18  
> **Proyecto:** jd-007  
> **Estado actual:** 73.6% cobertura (218/296 fragmentos codificados)  
> **Objetivo:** Alcanzar 100% de cobertura (78 fragmentos pendientes)

---

## 📊 Situación Actual

| Métrica | Valor Actual | Objetivo |
|---------|--------------|----------|
| Fragmentos codificados | 218 | 296 |
| Fragmentos sin código | 78 | 0 |
| Cobertura | 73.6% | **100%** |
| Códigos únicos | 298 | ~320 (controlado) |
| Total de citas | 326 | ~400+ |

---

## 🎯 Plan de Implementación

### Fase 1: Propagación Semántica (Prioridad Alta)
**Duración estimada:** 10-15 minutos

**Objetivo:** Reutilizar los 298 códigos existentes para fragmentos similares, minimizando la fragmentación conceptual.

#### Pasos:
1. **Ir a:** Codificación Abierta → Sugerencias Semánticas
2. **Configurar:**
   - Fragmento semilla: *dejar vacío* (el sistema seleccionará automáticamente)
   - Top-K: 10
   - Pasos: 78 (cubrir todos los pendientes)
   - ☑️ "Incluir fragmentos ya codificados": **DESACTIVADO**
3. **Ejecutar:** Clic en 🚀 Runner
4. **Monitorear:** Observar progreso en el panel de status

**Resultado esperado:**
- ~40-50 fragmentos codificados con códigos existentes
- Reducción de fragmentos pendientes: 78 → ~30-40

#### Validación:
```
POST /api/coding/suggest/runner/execute
{
  "project": "jd-007",
  "steps": 78,
  "top_k": 10,
  "include_coded": false,
  "sweep_all_interviews": true,
  "llm_suggest": true,
  "submit_candidates": true
}
```

---

### Fase 2: Análisis LLM de Fragmentos Únicos (Prioridad Alta)
**Duración estimada:** 15-20 minutos

**Objetivo:** Generar códigos *de novo* para fragmentos que no tienen similares en el corpus.

#### Pasos:
1. **Ir a:** Codificación Abierta → Análisis con IA
2. **Verificar:** El contador de "Pendientes" debe mostrar ~30-40 (los que quedaron de Fase 1)
3. **Ejecutar:** Clic en 🚀 Runner
4. **Monitorear:** El runner procesará solo fragmentos sin código

**Resultado esperado:**
- 30-40 memos analíticos generados
- 30-40 códigos candidatos nuevos en bandeja
- Cobertura: ~85% → 100%

#### API Call:
```
POST /api/coding/open/runner/execute
{
  "project": "jd-007",
  "max_interviews": 20,
  "strategy": "recent"
}
```

---

### Fase 3: Validación de Códigos Candidatos (Prioridad Media)
**Duración estimada:** 10-15 minutos

**Objetivo:** Revisar y aprobar los códigos generados en Fases 1 y 2.

#### Pasos:
1. **Ir a:** Codificación Abierta → Bandeja de Validación
2. **Refrescar:** Clic en "Refrescar bandeja"
3. **Revisar:** Códigos candidatos (~70-80 nuevos)
4. **Opciones:**
   - ✅ **Validar todos** (si confías en el LLM)
   - 🔍 **Revisar uno por uno** (más control)
   - 🔀 **Fusionar similares** (reducir redundancia)

**Criterios de validación:**
- ✅ El código refleja el contenido del fragmento
- ✅ No es redundante con códigos existentes
- ✅ Es suficientemente específico (no demasiado genérico)

---

### Fase 4: Discovery Exploratorio (Opcional)
**Duración estimada:** 15-30 minutos

**Objetivo:** Identificar temas emergentes no cubiertos por el proceso automático.

#### Conceptos sugeridos para explorar:
```
- participación social
- desarrollo comunitario
- organización vecinal
- gestión territorial
- conflictos urbanos
- infraestructura pública
- servicios básicos
- identidad barrial
```

#### Proceso:
1. **Ir a:** Discovery
2. **Buscar:** Cada concepto de la lista
3. **Evaluar:** ¿Hay fragmentos relevantes sin código?
4. **Proponer:** Usar "Proponer como código" para conceptos valiosos

---

## 📈 Métricas de Éxito

| Fase | Métrica | Valor Esperado |
|------|---------|----------------|
| Fase 1 | Fragmentos codificados (semántico) | +40-50 |
| Fase 2 | Fragmentos codificados (LLM) | +30-40 |
| Fase 3 | Códigos validados | 70-80 |
| **Total** | **Cobertura final** | **100%** |

---

## ⚠️ Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Error LLM (JSON inválido) | Media | Bajo | Reanudar runner, ya implementado retry |
| Timeout en runner largo | Baja | Bajo | Timeout 60s ya implementado (Sprint 31) |
| Códigos muy fragmentados | Media | Medio | Usar fusión en bandeja de validación |
| Token expirado | Baja | Bajo | Singleton refresh implementado |

---

## 🔧 Configuración Técnica

### Timeouts (ya configurados)
```typescript
// api.ts - Sprint 31
apiFetchJson(..., 60000)  // 60s para operaciones runner
```

### Umbrales Discovery
```python
# queries.py - Sprint 31
ANCHOR_QUALITY_THRESHOLD = 0.40  # (era 0.55)
```

### LLM Settings
```python
# coding.py
max_completion_tokens = 400  # (era 300)
```

---

## 📋 Checklist de Ejecución

### Pre-ejecución
- [ ] Backend corriendo (`curl http://127.0.0.1:8000/healthz`)
- [ ] Frontend compilado (Vite sin errores)
- [ ] Usuario autenticado en frontend
- [ ] Proyecto jd-007 seleccionado

### Fase 1: Semántico
- [ ] Runner ejecutado
- [ ] Sin errores timeout
- [ ] Candidatos en bandeja

### Fase 2: LLM
- [ ] Runner ejecutado
- [ ] Memos generados
- [ ] Candidatos en bandeja

### Fase 3: Validación
- [ ] Bandeja refrescada
- [ ] Códigos revisados/validados
- [ ] Estadísticas actualizadas

### Post-ejecución
- [ ] Cobertura = 100%
- [ ] Informe LOG_MONITORING_REPORT.md actualizado

---

## 📊 Dashboard de Seguimiento

```
┌─────────────────────────────────────────────────────────────┐
│              PROGRESO HACIA COBERTURA 100%                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Actual:    ████████████████████████░░░░░░░  73.6%          │
│  Fase 1:    ████████████████████████████░░░  ~85%           │
│  Fase 2:    ██████████████████████████████  100%            │
│                                                             │
│  Fragmentos: 218/296 → 250/296 → 296/296                    │
│  Códigos:    298 → ~310 → ~320                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 📝 Notas Adicionales

### Orden de ejecución recomendado
1. **Semántico primero** → Reutiliza códigos existentes (menos fragmentación)
2. **LLM segundo** → Solo para fragmentos verdaderamente únicos
3. **Validación al final** → Batch review más eficiente

### Tiempo total estimado
- **Ejecución automática:** 25-35 minutos
- **Validación manual:** 10-15 minutos
- **Total:** ~45-50 minutos

### Beneficios esperados
- ✅ Cobertura completa para análisis axial
- ✅ Base sólida para codificación selectiva
- ✅ Curva de saturación verificable
- ✅ Exportación REFI-QDA/MAXQDA completa

---

*Documento creado: 2026-01-18*  
*Sprint: 31 - Cobertura 100%*  
*Autor: Sistema de Análisis Cualitativo*
