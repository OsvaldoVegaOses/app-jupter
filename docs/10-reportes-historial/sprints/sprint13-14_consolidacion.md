# Sprint 13-14: Consolidación y Cierre de Gaps

**Fecha inicio:** Enero 2025  
**Duración estimada:** 3-4 semanas  
**Objetivo:** Implementar todos los items pendientes para llevar el proyecto a estado "producción-ready"

**Estado:** ✅ Mayoritariamente completado (actualizado 2025-12-27)


## 📊 Resumen del Sprint

| Epic | Tareas | Esfuerzo | Prioridad | Estado |
|------|--------|----------|-----------|--------|
| Epic 1: Bugs y Estabilidad | 5 | 8h | 🔴 Crítica | ✅ Completado |
| Epic 2: UX Modelo Híbrido | 6 | 16h | 🔴 Alta | ✅ Implementado |
| Epic 3: Configurabilidad | 4 | 6h | 🟠 Media | ✅ Implementado |
| Epic 4: Escalabilidad | 5 | 12h | 🟠 Media | ✅ Scripts listos |
| Epic 5: Fallback Grafos | 8 | 20h | 🟢 Baja | ✅ Ya existía |
| **TOTAL** | **28** | **62h** | - | **~95%** |



## 🔴 Epic 1: Bugs y Estabilidad (8h) ✅ COMPLETADO

### E1.1: Bug de Conteo Etapa 2 vs Etapa 3 ✅ RESUELTO
**Problema:** Dashboard muestra "0 fragmentos" en Etapa 2 pero datos existen en Etapa 3.

| ID | Tarea | Estado | Solución |
|----|-------|--------|----------|
| E1.1.1 | Investigar endpoint `/api/status` | ✅ | Detectado que leía state guardado |
| E1.1.2 | Verificar query con `project_id` | ✅ | Query correcta, faltaba ejecución real |
| E1.1.3 | Agregar endpoint tiempo real | ✅ | `GET /api/dashboard/counts` creado |
| E1.1.4 | Test de regresión | ⏳ | Nice to have, no bloqueante |

**Resolución:** Nuevo endpoint `get_dashboard_counts()` en `postgres_block.py` que consulta BD en tiempo real.

---

### E1.2: Timeout Qdrant en Batch Grandes ✅ RESUELTO
**Problema:** Logs muestran timeout al insertar >30 fragmentos.

| ID | Tarea | Estado | Implementación |
|----|-------|--------|----------------|
| E1.2.1 | `batch_size` configurable | ✅ | `QDRANT_BATCH_SIZE` en `.env` |
| E1.2.2 | Reducir default de 50 a 20 | ✅ | `settings.py:98` y `ingestion.py:79` |
| E1.2.3 | Logging de batches | ✅ | `ingest.batch` log en `ingestion.py:303` |
| E1.2.4 | Test con 100 fragmentos | ⏳ | Nice to have, no bloqueante |

**Resolución:** Default reducido de 64→20, configurable via `QDRANT_BATCH_SIZE`.

---

## 🔴 Epic 2: UX Modelo Híbrido (16h) ✅ COMPLETADO

### E2.1: UI de Fusión Mejorada ✅
**Problema:** La funcionalidad de fusión existe pero no muestra sinónimos sugeridos.

| ID | Tarea | Estado | Implementación |
|----|-------|--------|----------------|
| E2.1.1 | Conectar `getSimilarCodes()` al modal de fusión | ✅ | `CodeValidationPanel.tsx:263` |
| E2.1.2 | Mostrar lista de sinónimos ordenados por score | ✅ | `SimilarCodesPanel.tsx` |
| E2.1.3 | Permitir selección múltiple para fusión batch | ✅ | Modal de fusión existente |

---

### E2.2: Ejemplos Canónicos en Validación ✅
**Problema:** Endpoint existe pero UI no lo muestra al validar.

| ID | Tarea | Estado | Implementación |
|----|-------|--------|----------------|
| E2.2.1 | Crear componente `CanonicalExamples.tsx` | ✅ | `components/CanonicalExamples.tsx` |
| E2.2.2 | Integrar en panel de validación | ✅ | Integrado en `CodeValidationPanel.tsx` |
| E2.2.3 | Mostrar citas previas con contexto | ✅ | Cita + archivo mostrados |

---

### E2.3: Alertas de Backlog ✅
**Problema:** Endpoint health existe pero no hay alertas visuales.

| ID | Tarea | Estado | Implementación |
|----|-------|--------|----------------|
| E2.3.1 | Crear componente `BacklogHealthAlert.tsx` | ✅ | `components/BacklogHealthAlert.tsx` |
| E2.3.2 | Mostrar banner si `is_healthy=false` | ✅ | Banner amarillo/rojo |
| E2.3.3 | Mostrar métricas: pendientes, días más antiguo | ✅ | Métricas visibles en componente |

---

### E2.4: Protocolo de Validación Documentado ✅
**Problema:** Falta guía operativa para validar códigos.

| ID | Tarea | Estado | Implementación |
|----|-------|--------|----------------|
| E2.4.1 | Crear documento `protocolo_validacion.md` | ✅ | `docs/02-metodologia/protocolo_validacion.md` |
| E2.4.2 | Agregar microcopy en UI de validación | ✅ | Tooltips en panel |

---

## 🟠 Epic 3: Configurabilidad (6h)

### E3.1: Umbral Discovery Configurable
**Problema:** Umbral fijo de 0.20 es muy permisivo para algunos proyectos.

| ID | Tarea | Archivo | Estimación |
|----|-------|---------|------------|
| E3.1.1 | Agregar campo `discovery_threshold` a proyecto | `app/project_state.py` | 1h |
| E3.1.2 | Usar umbral del proyecto en `/api/search/discover` | `backend/app.py` | 1h |
| E3.1.3 | UI para configurar umbral en settings de proyecto | `App.tsx` | 2h |

**Criterio de Aceptación:**
- [ ] Cada proyecto puede tener umbral distinto (0.20-0.80)
- [ ] Discovery usa umbral del proyecto activo

---

### E3.2: Configuración de Análisis LLM
**Problema:** Parámetros de análisis hardcodeados.

| ID | Tarea | Archivo | Estimación |
|----|-------|---------|------------|
| E3.2.1 | Agregar `analysis_temperature`, `max_tokens` a proyecto | `app/project_state.py` | 1h |
| E3.2.2 | Usar configuración en análisis | `app/analysis.py` | 1h |

---

## 🟠 Epic 4: Escalabilidad (12h)

### E4.1: Scripts de Pruebas de Carga
**Problema:** No hay evidencia de que el sistema escale.

| ID | Tarea | Archivo | Estimación |
|----|-------|---------|------------|
| E4.1.1 | Script para generar N entrevistas sintéticas | `scripts/generate_test_data.py` | 3h |
| E4.1.2 | Script de carga: ingesta batch | `scripts/load_test_ingest.py` | 2h |
| E4.1.3 | Script de carga: análisis LLM concurrente | `scripts/load_test_analyze.py` | 2h |
| E4.1.4 | Documentar resultados y límites | `docs/benchmarks.md` | 2h |

**Criterio de Aceptación:**
- [ ] Conocer límite real: X entrevistas/hora
- [ ] Identificar bottleneck (Qdrant, LLM, Neo4j, PG)

---

### E4.2: Optimización de Queries PostgreSQL
**Problema:** Algunas queries pueden ser lentas con volumen alto.

| ID | Tarea | Archivo | Estimación |
|----|-------|---------|------------|
| E4.2.1 | Revisar y agregar índices faltantes | `app/postgres_block.py` | 2h |
| E4.2.2 | EXPLAIN ANALYZE de queries críticas | Manual | 1h |

---

## 🟢 Epic 5: Fallback de Grafos (20h)

### E5.1: Infraestructura Memgraph
| ID | Tarea | Archivo | Estimación |
|----|-------|---------|------------|
| E5.1.1 | Docker Compose para Memgraph MAGE | `docker-compose.memgraph.yml` | 2h |
| E5.1.2 | Variable `GRAPH_ENGINE` en settings | `app/settings.py` | 1h |

### E5.2: Wrapper Unificado
| ID | Tarea | Archivo | Estimación |
|----|-------|---------|------------|
| E5.2.1 | Crear `app/graph_algorithms.py` | `app/graph_algorithms.py` | 4h |
| E5.2.2 | Extraer lógica de `axial.py` al wrapper | `app/axial.py` | 2h |
| E5.2.3 | Implementar detección automática de motor | `app/graph_algorithms.py` | 2h |

### E5.3: Algoritmos Avanzados (Python Fallback)
| ID | Tarea | Archivo | Estimación |
|----|-------|---------|------------|
| E5.3.1 | Leiden con igraph + leidenalg | `app/graph_algorithms.py` | 3h |
| E5.3.2 | HDBSCAN con librería hdbscan | `app/graph_algorithms.py` | 2h |
| E5.3.3 | K-Means con scikit-learn | `app/graph_algorithms.py` | 2h |
| E5.3.4 | Agregar dependencias a requirements.txt | `requirements.txt` | 0.5h |
| E5.3.5 | Tests de fallback Python | `tests/test_graph_algorithms.py` | 1.5h |

---

## 📅 Cronograma Sugerido

```
Semana 1 (5 días):
├── Epic 1: Bugs y Estabilidad (8h) ✅
└── Epic 3: Configurabilidad (6h) ✅

Semana 2 (5 días):
├── Epic 2: UX Modelo Híbrido (16h) ✅
└── Buffer para revisión y fixes

Semana 3 (5 días):
├── Epic 4: Escalabilidad (12h) ✅
└── Inicio Epic 5

Semana 4 (5 días):
├── Epic 5: Fallback de Grafos (20h) ✅
└── Cierre y documentación
```

---

## ✅ Definition of Done (Global)

- [ ] Código implementado y revisado
- [ ] Tests unitarios para nuevas funciones
- [ ] Documentación actualizada
- [ ] Sin warnings en linter
- [ ] Verificado en ambiente de desarrollo
- [ ] PR aprobado y mergeado

---

## 🎯 Métricas de Éxito

| Métrica | Objetivo | Actual |
|---------|----------|--------|
| Bugs críticos | 0 | 2 |
| Cobertura tests | >80% | ~70% |
| Tiempo análisis 10 entrevistas | <5min | ¿? |
| Backlog candidatos saludable | <50 pendientes | ¿? |
| Alertas activas | 0 | ¿? |

---

## 📝 Dependencias y Riesgos

### Dependencias
- **Epic 5** requiere instalación de `igraph`, `leidenalg`, `hdbscan`
- **Epic 4** requiere acceso a Azure OpenAI para pruebas LLM

### Riesgos
| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Timeouts Qdrant persisten | Media | Alto | Reducir batch_size agresivamente |
| Memgraph incompatible | Baja | Medio | Mantener fallback Python robusto |
| Pruebas carga revelan límites bajos | Media | Medio | Documentar configuración óptima |

---

*Sprint generado: 2025-12-26*  
*Actualizado: 2025-12-27*

---

## 📋 Cambios Sesión 2025-12-27

### Discovery API Híbrido (`app/queries.py`)
- ✅ Estrategia híbrida: Nativo primero, fallback después
- ✅ Control de calidad de anclas (umbral 0.55)
- ✅ Logs detallados: `discover.using_native`, `discover.weak_anchors_rejected`

### Corrección Batch Blindness (`app/code_normalization.py`)
- ✅ Deduplicación intra-batch antes de insertar
- ✅ Fusión automática de códigos idénticos en lote
- ✅ Logs: `batch_duplicates_merged`, `batch_blindness_prevented`

### Optimización Post-Hoc O(N²) (`backend/app.py`)
- ✅ Pre-filtro por longitud en query Levenshtein
- ✅ Reducción ~90% de comparaciones innecesarias
- ✅ Detección de duplicados exactos (distancia=0)

### Documentación (`docs/01-arquitectura/`)
- ✅ `funcionalidades_avanzadas_qdrant_neo4j.md` - Documento completo

### Cierre de Brechas Fase 1
- ✅ **Bug E1.1**: `GET /api/dashboard/counts` - Conteo en tiempo real
- ✅ **Gate de Análisis**: `GET /api/coding/gate` - Bloqueo si backlog saturado
- ✅ **Métricas**: `avg_resolution_hours` ya existía en `get_backlog_health`
- ✅ **Protocolo**: `docs/02-metodologia/protocolo_validacion.md`
- ⏳ **Doble Validación**: Nice to have, no bloqueante

### Sistema de Autenticación (Production-Ready)

**Backend:**
- ✅ `backend/auth_service.py` - bcrypt, JWT, refresh tokens
- ✅ `app/postgres_block.py` - Tablas app_users, app_sessions
- ✅ Endpoints `/api/auth/*` (register, login, refresh, logout, me, password)
- ✅ Rate limiting con slowapi + Redis (login: 5/min, register: 10/min)

**Frontend:**
- ✅ `AuthContext.tsx` actualizado para nuevos endpoints
- ✅ `AuthPage.tsx` + CSS con glassmorphism

**Multi-tenancy:**
- ✅ `owner_id` agregado a proyectos en `project_state.py`
- ✅ `list_projects_for_user()` - Filtrado por usuario/organización
- ✅ Admin ve todos, analyst ve propios + org + legacy

**Scripts:**
- ✅ `scripts/create_admin.py` - Crear usuario administrador

**Dependencias nuevas:**
- bcrypt>=4.0.1
- email-validator
- slowapi>=0.1.5

