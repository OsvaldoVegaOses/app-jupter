# Plan Consolidado: Infraestructura + Migración

**Fecha:** 2026-01-02  
**Enfoque:** Completar infraestructura primero, luego migración gradual

---

## 🎯 Secuencia de Prioridades

```
┌─────────────────────────────────────────────────────────┐
│  FASE 0: Infraestructura (plan_cambios_2026-01-02.md)   │
│  ════════════════════════════════════════════════════   │
│  1. PostgreSQL - Alineación de esquema                  │
│  2. Qdrant - Índice por proyecto                        │
│  3. Neo4j - Labels/relaciones mínimas                   │
│  4. Health/Observabilidad                               │
│  5. Valor de negocio (búsqueda asistida)                │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  FASE 1-4: Migración a Routers (post-infraestructura)   │
│  ════════════════════════════════════════════════════   │
│  Solo después de completar Fase 0                       │
│  Ver: Revision_Desarrollo/implementation_plan.md         │
└─────────────────────────────────────────────────────────┘
```

---

## FASE 0: Infraestructura ✅ COMPLETADA (2026-01-03)

### 0.1 PostgreSQL – Alineación de esquema
**Estado:** ✅ Completado

```sql
-- Script: scripts/phase0_schema_alignment.sql (v2)
-- Tabla: app_sessions (no sessions)
ALTER TABLE app_sessions ADD COLUMN IF NOT EXISTS is_revoked BOOLEAN DEFAULT FALSE;
ALTER TABLE app_sessions ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ DEFAULT NOW();

-- analysis_insights.project_id con NOT NULL y default
ALTER TABLE analysis_insights ADD COLUMN project_id TEXT NOT NULL DEFAULT 'default';
CREATE INDEX IF NOT EXISTS idx_insights_project ON analysis_insights(project_id);

-- entrevista_fragmentos.actor_principal
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS actor_principal TEXT;

-- analisis_axial.relacion + índice único NUEVO patrón
ALTER TABLE analisis_axial ADD COLUMN IF NOT EXISTS relacion TEXT;
CREATE UNIQUE INDEX idx_axial_composite_unique ON analisis_axial(project_id, categoria, codigo, relacion);
```

### 0.2 Qdrant – Índice por proyecto
**Estado:** ✅ Completado

Índice keyword creado en colección `fragments` campo `project`.

### 0.3 Neo4j – Labels/relaciones mínimas
**Estado:** ✅ Completado

- Labels verificados: `Categoria`, `Codigo`, `Entrevista`, `Fragmento` ✅
- GDS disponible: versión 2.24.0 ✅

### 0.4 Health/Observabilidad
**Estado:** ✅ Completado

- `RequestIdMiddleware` añadido en `backend/app.py:320-358`
- Genera UUID, vincula a structlog, retorna header `X-Request-ID`

### 0.5 Valor de negocio (búsqueda asistida)
**Estado:** ✅ Completado

- Smart action badge implementado en `DiscoveryPanel.tsx:430-470`
- Umbrales: ≥80% → Codificar, 60-80% → Proponer, <60% → Explorar
- Null coalescing añadido: `(frag.score ?? 0)`

---

## FASES 1-4: Migración a Routers (POST-INFRAESTRUCTURA)

> **Nota:** Estas fases se ejecutarán SOLO después de completar Fase 0.  
> Mientras tanto, `app.py` permanece monolítico según decisión documentada.

### Criterios para iniciar migración:
- [ ] Fase 0 completada al 100%
- [ ] Tests de integración pasando
- [ ] Despliegue Azure estable
- [ ] Revisión de la decisión de mantener monolítico

### Plan de migración (cuando se active):
Ver archivo: [implementation_plan.md](./implementation_plan.md)

| Fase | Contenido | Estimado |
|------|-----------|----------|
| 1 | Projects, Ingestion, Analysis routers | 1 semana |
| 2 | Coding, Candidates routers | 1 semana |
| 3 | Transcription, Interviews routers | 1 semana |
| 4 | Reports, Insights, cleanup | 1 semana |

---

## ✅ Decisiones Documentadas

| Decisión | Justificación |
|----------|---------------|
| Mantener `app.py` monolítico (temporalmente) | Minimizar riesgo durante estabilización |
| No añadir scipy | Evitar dependencias pesadas |
| Redis solo para Azure | No habilitar localmente aún |
| Migración gradual post-Fase 0 | Estabilidad primero |

---

## 🔄 Actualización (2026-01-13)

- Panorama/NBA: `GET /api/research/overview` computa `overview.panorama` server-side para mantener UX estable en Inicio.
- Runner Semántico: checkpoints en `logs/runner_checkpoints/<project>/<task_id>.json` y reportes en `logs/runner_reports/<project>/<task_id>.json`.
- Contrato único de métricas Runner/Bandeja: ver [docs/05-calidad/contrato_metricas_candidatos_runner.md](../05-calidad/contrato_metricas_candidatos_runner.md).

---

## 📊 Tracking de Progreso

### Fase 0 (Infraestructura) - ✅ COMPLETADA
- [x] 0.1 PostgreSQL schema (app_sessions, entrevista_fragmentos, analisis_axial)
- [x] 0.2 Qdrant índice keyword en `project`
- [x] 0.3 Neo4j labels verificados (GDS 2.24.0 disponible)
- [x] 0.4 Health/Observabilidad (request_id middleware añadido)
- [x] 0.5 Búsqueda asistida (smart action indicators implementados)

### Fases 1-4 (Migración) - PENDIENTE
- [ ] *Disponible para iniciar*

---

## 📁 Archivos Relacionados

- [plan_cambios_2026-01-02.md](./plan_cambios_2026-01-02.md) - Plan original de infraestructura
- [auditoria_estado_app_py_2026-01-02.md](./auditoria_estado_app_py_2026-01-02.md) - Auditoría del monolito
- [implementation_plan.md](./implementation_plan.md) - Plan detallado de routers

---

*Plan consolidado: 2026-01-02 23:43 UTC-3*
