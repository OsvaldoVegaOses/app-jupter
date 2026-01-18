# Documento de Trabajo · Ajustes Pendientes

> **Actualizado: Diciembre 2024** - Revisado contra estado actual del código

## 1. Contexto y objetivo
- **Situación actual.** El comando `nucleus report` confirma que *Participación Ciudadana* es candidata sólida a núcleo, pero evidencia brechas (cobertura, citas, diversidad de fuentes) que impiden cerrar la etapa 5.
- **Objetivo del documento.** Registrar los cambios técnicos y funcionales necesarios para que la aplicación soporte un cierre robusto de la etapa 5 y exponga feedback accionable.
- **Alcance.** Higienización de datos, mejoras en Qdrant/Neo4j/PostgreSQL y automatización del seguimiento dentro de la UI.

## 2. Hallazgos relevantes - ESTADO ACTUAL

| Hallazgo | Estado Dic 2024 | Ubicación |
|----------|-----------------|-----------|
| **Índices de Qdrant** | ✅ RESUELTO | `qdrant_block.py:ensure_payload_indexes()` |
| **Campos indexados** | ✅ COMPLETO | `project_id`, `archivo`, `speaker`, `area_tematica`, `actor_principal`, `genero`, `periodo`, `codigos_ancla`, `fragmento` |
| **Persistencia nucleus** | ✅ IMPLEMENTADO | `nucleus.py:nucleus_report(persist=True)` → `analisis_nucleo_notas` |
| **Apply coding plan** | ✅ IMPLEMENTADO | `scripts/apply_coding_plan.py` |
| **Datos `Automatica_Test`** | ⚠️ PENDIENTE | Requiere limpieza manual |
| **UI acciones sugeridas** | ⚠️ PENDIENTE | Panel no existe aún |

## 3. Backlog de acciones - ESTADO

### 3.1 Higiene y consistencia de datos
| Acción | Estado |
|--------|--------|
| Remover `Automatica_Test` de PostgreSQL y Neo4j | ⚠️ Pendiente |
| Completar metadatos (`actor_principal`, etc.) | ⚠️ Pendiente |
| Validar `metadata/open_codes.json` | ⚠️ Pendiente |

### 3.2 Mejoras en Qdrant / pipeline de ingesta
| Acción | Estado | Evidencia |
|--------|--------|-----------|
| `ensure_payload_indexes` con todos los campos | ✅ Hecho | `qdrant_block.py:90-114` |
| Normalización de payloads | ✅ Hecho | `ingestion.py` |
| Documentar post-healthcheck | ✅ Hecho | `scripts/README.md` |

### 3.3 Automatización del feedback de núcleo
| Acción | Estado | Evidencia |
|--------|--------|-----------|
| Persistir `nucleus report --persist` | ✅ Hecho | `upsert_nucleus_memo()` en PostgreSQL |
| Tabla `analisis_nucleo_notas` | ✅ Creada | `postgres_block.py` |
| Endpoint `/api/actions` | ⚠️ Pendiente | - |
| Panel UI "Acciones sugeridas" | ⚠️ Pendiente | - |
| Marcar acciones como completadas | ⚠️ Pendiente | - |

### 3.4 Refuerzos para cerrar la etapa 5
| Acción | Estado | Evidencia |
|--------|--------|-----------|
| Script `apply_coding_plan.py` | ✅ Hecho | `scripts/apply_coding_plan.py` |
| Reportes automáticos PostgreSQL | ✅ Hecho | `transversal.py`, vistas SQL |
| Scripts de verificación | ✅ Hecho | `verify_ingestion.py`, `run_e2e.ps1` |

## 4. Criterios de aceptación - ESTADO

| Criterio | Estado |
|----------|--------|
| `Automatica_Test` eliminado | ⚠️ Pendiente |
| Índices Qdrant verificados | ✅ Completado |
| Nucleus report persistido | ✅ Completado |
| Acciones visibles en UI | ⚠️ Pendiente |
| Scripts de validación | ✅ Completado |

## 5. Pasos inmediatos (Actualizado)

### ✅ Completados:
1. ~~Índices de Qdrant~~ → `ensure_payload_indexes()` implementado
2. ~~Persistir nucleus report~~ → Tabla `analisis_nucleo_notas` creada
3. ~~Scripts de aplicación~~ → `apply_coding_plan.py` listo
4. ~~Scripts de verificación~~ → `verify_ingestion.py`, `run_e2e.ps1`

### ⚠️ Pendientes:
1. **Limpiar `Automatica_Test`** de bases de datos
2. **Crear endpoint `/api/actions`** para exponer acciones sugeridas
3. **Panel UI** para visualizar y marcar acciones
4. **Completar metadatos** en fragmentos existentes

## 6. Riesgos y dependencias

| Riesgo | Mitigación |
|--------|------------|
| Cobertura insuficiente | Load testing implementado |
| Cambios en payload | `ensure_payload_indexes` idempotente |
| Panel de acciones inexistente | Priorizar en siguiente sprint |

## 7. Propuesta metodológica para extender la codificación IA

### 7.1 Estrategia general - IMPLEMENTADA
| Paso | Estado | Cómo |
|------|--------|------|
| Semilla IA balanceada | ✅ | `analysis.analyze_interview_text` |
| Extensión semiautomática | ✅ | `main.py coding suggest` + Qdrant |
| Consolidación | ✅ | `scripts/apply_coding_plan.py` |
| Validación final | ✅ | `nucleus report --persist` |

### 7.2 Opciones implementadas

| Opción | Estado | Ubicación |
|--------|--------|-----------|
| **Filtro estructurado para IA** | ⚠️ Parcial | Requiere CLI `--sample structural` |
| **Modo todas entrevistas** | ✅ Disponible | `--all-interviews` en CLI |
| **UI con acciones sugeridas** | ⚠️ Pendiente | - |
| **Scripts de control** | ✅ Hecho | `scripts/` con 34 utilidades |

---

## Resumen de Estado

| Categoría | Completado | Pendiente |
|-----------|------------|-----------|
| Qdrant/Índices | 100% | - |
| Persistencia nucleus | 100% | - |
| Scripts operacionales | 100% | - |
| Higiene de datos | 0% | `Automatica_Test` |
| UI Acciones | 0% | Panel completo |

---

*Última verificación: 13 Diciembre 2024*
