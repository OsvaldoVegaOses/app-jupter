# Evaluación de estado y paso siguiente

> **Fecha:** 23 Enero 2026  
> **Rol:** Contraparte lider de equipo de desarrollo  
> **Propósito:** Copiloto de investigación cualitativa basado en Teoría Fundamentada (post-positivista y constructivista)

---

## 1) Actualización teórica (debate GT traducido a producto)

### Núcleo metodológico compartido (invariante)
- Comparación constante
- Muestreo teórico
- Memoing estructurado
- Saturación teórica
- **Trazabilidad obligatoria**: toda afirmación analítica ↔ evidencia (fragmentos/citas)

### Diferencia que SÍ impacta diseño (modo epistemológico)

| Dimensión | Post-positivista (Glaser/Strauss/Corbin) | Constructivista (Charmaz) |
|-----------|------------------------------------------|---------------------------|
| Ontología | Patrones/regularidades "objetivables" | Múltiples realidades co-construidas |
| Codificación inicial | Abstracción temprana | **In-vivo + gerundios/procesos** |
| Axialidad | Paradigma relacional rígido (condiciones/acciones/consecuencias) | Categorías más fluidas, reflexivas |
| Memos | Conceptuales | **Reflexivos** (posicionamiento, interacción, contexto) |
| Validación | Validez/confiabilidad | Credibilidad, resonancia, utilidad |

### Traducción directa a producto

1. **Modo epistemológico por proyecto** (`epistemic_mode: "post_positivist" | "constructivist"`)
   - Cambia prompts/plantillas LLM
   - Cambia formato de salidas (gerundios + in-vivo en constructivista)
   - Cambia lenguaje UI (evitar que Ops parezca "análisis")

2. **Invariantes transversales** (no negociables):
   - Evidencia obligatoria para toda inferencia
   - Separación explícita OBSERVATION vs INTERPRETATION
   - Audit trail completo

**Estado actual:** La separación `OBSERVATION | INTERPRETATION | HYPOTHESIS | NORMATIVE_INFERENCE` ya existe en `app/analysis.py` (L127). **Falta:** configuración `epistemic_mode` por proyecto y prompts diferenciados.

---

## 2) Actualización de código (mapa actual)

### Lo sólido (alto valor ya ganado)

| Capa | Estado | Evidencia |
|------|--------|-----------|
| **Arquitectura source of truth** | ✅ Implementada | PostgreSQL = ledger; Neo4j = proyección |
| **Fase 1.5 (infra)** | ✅ Admin endpoints | `backend/routers/admin.py` L375-575 |
| **Migraciones code_id** | ✅ Aplicadas | `migrations/014_code_id_columns.sql` |
| **Contrato `axial_ready`** | ✅ Corregido | Solo bloquea: `missing_code_id`, `missing_canonical_code_id`, `divergences_text_vs_id`, `cycles_non_trivial` |
| **Freeze ontológico** | ✅ Implementado | `migrations/015_ontology_freeze.sql` |
| **Panel admin Fase 1.5** | ✅ UI lista | `CodeIdTransitionSection.tsx` |
| **Observabilidad Ops** | ✅ Panel + logs | JSONL estructurado + `AdminOpsPanel.tsx` |
| **Epistemic statements** | ✅ Básico | `EpistemicStatement` en API + frontend |

### Lo que FALTA (brecha bloqueante)

| Componente | Problema | Impacto |
|------------|----------|---------|
| **Core (`app/`) opera por texto** | `resolve_canonical_codigo()` es el resolver principal; no existe `resolve_canonical_code_id()` | Axialidad depende de nombres, no identidad estable |
| **`axial.py` usa texto** | L117-121: `resolve_canonical_codigo(pg, project, codigo)` | Relaciones axiales vulnerables a rename/merge |
| **`coding.py` no propaga `code_id`** | Inserciones/queries usan `codigo` | Drift texto↔ID en nuevas asignaciones |
| **Neo4j sync por texto** | Nodos `:Codigo` tienen `nombre` pero no `code_id` estable | Métricas GDS contaminadas |
| **Falta `epistemic_mode`** | No hay configuración por proyecto | Prompts únicos, no diferenciados |

---

## 3) Evaluación de estado

### Diagnóstico ejecutivo

```
┌────────────────────────────────────────────────────────────────────┐
│                    ESTADO ACTUAL DEL SISTEMA                       │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  FASE 1.5 (ADMIN): ████████████████████ 100% implementada          │
│                                                                    │
│  FASE 1.5 (CORE):  ██████░░░░░░░░░░░░░░  30% (solo schema)         │
│                                                                    │
│  FASE 2 (ID-FIRST): ░░░░░░░░░░░░░░░░░░░░   0% no iniciada          │
│                                                                    │
│  CAPA EPISTÉMICA:  ████░░░░░░░░░░░░░░░░  20% (solo types)          │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### El bloqueador real

**La Fase 1.5 está implementada en admin, pero el core (`app/*.py`) aún opera por texto.**

Consecuencias:
- `axial_ready=true` no garantiza estabilidad porque la axialidad sigue usando `canonical_codigo`
- Riesgo de drift silencioso: admin detecta divergencias, pero el core las ignora
- Neo4j contiene nodos sin `code_id`, invalidando métricas GDS post-axial

---

## 4) Paso siguiente propuesto

### Epic: "Identidad por ID end-to-end"

**Objetivo:** que todo el pipeline (open coding → catálogo → axial → Neo4j) opere con `code_id` como identidad, manteniendo `codigo` como label.

### Orden de ejecución (minimiza retrabajo)

#### Paso 1: Resolver canónico por ID (backend core)

**Archivos:** `app/postgres_block.py`

1. Implementar `resolve_canonical_code_id(pg, project_id, code_id) -> int | None`
2. Modificar `resolve_canonical_codigo()` para que internamente use IDs cuando existan
3. Exponer `(code_id, codigo)` en payloads donde hoy solo devuelve `codigo`

**Criterio de éxito:** test que resuelve merge por ID y retorna tanto ID como label.

#### Paso 2: Propagar `code_id` en `coding.py`

**Archivos:** `app/coding.py`

1. Al insertar código (asignación), obtener/crear `code_id` y guardarlo
2. En queries de códigos, incluir `code_id` en respuesta
3. Validación: nueva asignación crea entrada en `catalogo_codigos` con `code_id` generado

**Criterio de éxito:** `GET /api/coding/codes?project=X` devuelve `code_id` para cada código.

#### Paso 3: Axialidad por ID

**Archivos:** `app/axial.py`, `app/neo4j_block.py`

1. `assign_axial_relation()` recibe opcionalmente `code_id` y resuelve por ID
2. Relaciones en PostgreSQL (`axial_relationships`) incluyen `code_id`
3. Sync a Neo4j: nodos `:Codigo` reciben propiedad `code_id`

**Criterio de éxito:** `axial_ready=true` + relación axial creada → nodo Neo4j tiene `code_id`.

#### Paso 4: Gate real en runtime

**Archivos:** `backend/routers/*.py` (coding, axial, analysis)

1. Antes de iniciar flujo axial: check `axial_ready` vía endpoint admin
2. Si `axial_ready=false`: rechazar con 409 + mensaje específico
3. Logging: `axial.blocked` con `project_id` y `blocking_reasons`

**Criterio de éxito:** intento de crear relación axial sin `axial_ready` → 409 con razón.

#### Paso 5 (opcional, Fase 2): Capa epistemológica

**Archivos:** `app/settings.py`, `app/analysis.py`, DB `pg_proyectos`

1. Agregar columna `epistemic_mode TEXT DEFAULT 'constructivist'` a `pg_proyectos`
2. Cargar modo en `ProjectSettings`
3. Crear templates de prompts diferenciados:
   - `prompts/constructivist/open_coding.txt`
   - `prompts/post_positivist/open_coding.txt`
4. Selector en UI de proyecto

**Criterio de éxito:** proyecto con `epistemic_mode=constructivist` genera códigos con gerundios/in-vivo.

---

## 5) Recomendación de próxima acción

**Ejecutar Paso 1** (resolver canónico por ID) en esta sesión o la siguiente.

Es el punto de mayor apalancamiento:
- Desbloquea pasos 2-4
- Mínimo riesgo (no rompe contratos, solo extiende)
- Permite validar que la migración 014 está operativa

**Deliverable esperado:** función `resolve_canonical_code_id()` en `postgres_block.py` + test unitario.

---

## 6) Riesgos y mitigaciones

| Riesgo | Probabilidad | Mitigación |
|--------|--------------|------------|
| Drift texto↔ID en producción | Media | Checks periódicos + bloqueo ante divergencia |
| Merges concurrentes | Baja | Advisory locks ya implementados |
| UI muestra `code_id` a usuario | Media | Mantener `codigo` como label visible; `code_id` es infra |
| Regresión en axialidad | Media | Test E2E: crear relación → verificar Neo4j |

---

## 7) Referencias clave

- Debate teórico: `docs/fundamentos_teoria/`
- Matriz epistemológica: `docs/02-metodologia/matriz_validacion_epistemologica_metodologica.md`
- Fase 1.5 diseño: `docs/04-arquitectura/desarrollo_pendiente/fase_1_5_transicion_controlada_a_code_id.md`
- Propuesta original: `docs/01-configuracion/Documentacion_desarrollo/propuesta_avance_de_1,5_A_2`
- Migraciones: `migrations/014_code_id_columns.sql`, `migrations/015_ontology_freeze.sql`
- Admin endpoints: `backend/routers/admin.py` L375-575

---

*Documento generado: 23 Enero 2026*
