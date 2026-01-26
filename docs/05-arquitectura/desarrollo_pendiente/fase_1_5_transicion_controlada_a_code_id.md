# Fase 1.5 — Transición controlada hacia `code_id` (compatibilidad dual)

> **Fecha:** 22 Enero 2026  
> **Estatus:** diseño / preparación (no implementado aún)

Esta fase propone una transición **controlada** desde identidad por texto (`codigo`, `canonical_codigo`) hacia identidad estable por ID (`code_id`, `canonical_code_id`) **sin romper** UI, API ni reportes, y manteniendo `canonical_codigo` durante todo el período de compatibilidad.

**Advertencia epistemológica (clave):** durante la Fase 1.5 el sistema opera en un **estado ontológico dual controlado** (texto ↔ ID). Esto es **transitorio** y **riesgoso por diseño**; es un **anti-pattern aceptado temporalmente** por razones de compatibilidad. Por lo tanto, **ninguna inferencia teórica** (p. ej. axialidad, centralidad, comunidad, categoría nuclear) debe basarse aún en la capa por ID.

---

## 1) Objetivo

Introducir `code_id` como **identidad interna** del concepto (y `canonical_code_id` como puntero canónico), manteniendo:

- **Compatibilidad externa**: el UI y la API pueden seguir operando con `codigo` (label).
- **Compatibilidad histórica**: `canonical_codigo` se conserva temporalmente.
- **Invariante de sistema**: todo análisis/escritura “con efectos” resuelve a canónico.

**Lo que esta fase NO promete (para evitar malentendidos):** Fase 1.5 no establece todavía una ontología única “pura”. Establece una **transición ontológica** con dos representaciones en paralelo y controles para minimizar drift.

---

## 2) Principios (disciplina fuerte)

1) **Dual-read / Dual-write (temporal)**
   - Se lee por ID cuando está disponible; si no, se cae a texto.
   - Se escribe **siempre** manteniendo consistencia entre texto e ID.

2) **Regla de precedencia (árbitro último)**
   - En caso de divergencia entre `canonical_codigo` y `canonical_code_id`, la **verdad ontológica** es `canonical_code_id`.
   - `canonical_codigo` se considera **compatibilidad degradada** mientras dure la fase.
   - Las operaciones “con efectos” (merge, promoción, sincronización, escritura analítica) deben **bloquearse** o **repararse** si se detecta divergencia.

3) **No romper contratos**
   - Endpoints existentes siguen aceptando `codigo`.
   - Se agregan campos nuevos sin quitar los antiguos.

4) **Rollback posible**
   - La fase 1.5 no debe requerir borrar columnas ni reescribir masivamente tablas de evidencia.

5) **No usar IDs como base teórica aún**
   - Durante Fase 1.5, `code_id` existe para **identidad y consistencia interna**, no como soporte de inferencia metodológica.

---

## 3) Cambios mínimos en PostgreSQL (fase 1.5)

### 3.1 En `catalogo_codigos`
Agregar columnas (sin eliminar nada):

- `code_id` (identidad estable)
- `canonical_code_id` (puntero canónico; recomendado `NULL` en canónicos)

Mantener:
- `codigo` (label)
- `canonical_codigo` (puntero legacy por texto)

**Recomendación práctica sobre tipo de ID**

- Opción A (sin extensiones, recomendado para transición): `BIGSERIAL`/`BIGINT` + secuencia, con `UNIQUE(project_id, code_id)`.
- Opción B (UUID): requiere `pgcrypto` o `uuid-ossp`.

La propuesta DDL (con UUID) está en:
- [docs/04-arquitectura/desarrollo_pendiente/propuesta_sql_migracion_code_id.sql](docs/04-arquitectura/desarrollo_pendiente/propuesta_sql_migracion_code_id.sql)

Implementación aplicada (idempotente, UUID) para este repo:
- [migrations/014_code_id_columns.sql](migrations/014_code_id_columns.sql)

Runner recomendado (ordenado):
- [scripts/apply_migrations_production.py](scripts/apply_migrations_production.py)

### 3.2 Constraints/índices
- `UNIQUE(project_id, code_id)`
- FK compuesta (si se usa `canonical_code_id`): `(project_id, canonical_code_id) -> (project_id, code_id)`
- Índice: `(project_id, canonical_code_id)`
- Índice parcial recomendado (intención ontológica): “un solo canónico por label”:
  - `UNIQUE(project_id, lower(codigo)) WHERE canonical_code_id IS NULL`

---

## 4) Backend: estrategia de implementación (fase 1.5)

### 4.1 Resolver dual
Agregar (sin romper lo existente):

- `resolve_canonical_code_id(pg, project_id, code_id)`
- `resolve_canonical_codigo(pg, project_id, codigo)` (ya existe)

Regla:
- Si la operación entra por `codigo`: resolver a `code_id` cuando exista (lookup), luego resolver canónico por `canonical_code_id`.
- Si la operación entra por `code_id`: resolver canónico por `canonical_code_id`.

Fallback (degradado):
- Si `code_id` aún no existe (fila legacy): fallback a resolución por `canonical_codigo` **solo para lectura sin efectos** (listados, UI, debugging).
- El fallback por texto **no debe** usarse para: merges definitivos, promoción, creación de relaciones, sincronización a grafo, ni escritura de resultados analíticos.
- Si una operación con efectos recibe una fila sin `code_id`, se debe **forzar backfill** (asignar `code_id`) o **rechazar** la operación.

### 4.1.1 Detección y manejo de divergencia (texto ↔ ID)
Durante Fase 1.5 es esperable que exista riesgo de drift. Por lo tanto:

- Si `canonical_code_id` existe pero no corresponde al `canonical_codigo` (o viceversa), se debe tratar como **incidente de consistencia**.
- Regla operativa: **ID manda**. Se re-deriva `canonical_codigo` desde `canonical_code_id` (compatibilidad) o se bloquea hasta reparar.

### 4.2 Mantener contratos API/UI
En respuestas donde hoy se devuelve:

- `codigo`
- `canonical_codigo`
- `status`

Agregar (opcional) en fase 1.5:

- `code_id`
- `canonical_code_id`

Sin quitar nada.

### 4.2.1 Advertencia de uso en análisis
Aunque la API exponga `code_id`, durante Fase 1.5 ese campo es **infraestructura**, no “semántica teórica”. No usarlo como pivote para inferencias estructurales.

### 4.3 Doble escritura en operaciones de merge
Cuando se hace un merge (definitivos o candidatos con impacto ontológico):

- Actualizar `canonical_codigo` (compatibilidad)
- Actualizar `canonical_code_id` (nuevo camino)

Si la fila target aún no tiene `code_id`, debe generarse/backfillearse antes.

### 4.4 Estado `superseded` (delimitación)
`superseded` es un estado **teórico-evolutivo** (una categoría reemplazada por otra). Por consistencia metodológica:

- Durante Fase 1.5, `superseded` **no debe usarse operativamente** (no debe disparar lógica analítica, axial o de teoría).
- Su inclusión aquí es **solo para compatibilidad futura** y para permitir checks/validaciones del esquema.

---

## 5) Backfill y verificación (operación)

### 5.1 Backfill incremental
Estrategia recomendada:

1) Backfill de `code_id` para todos los registros de `catalogo_codigos`.
2) Backfill de `canonical_code_id` a partir de `canonical_codigo` (match por `(project_id, codigo)` → `code_id`).
3) Auditoría de consistencia:
   - No deben existir ciclos.
   - `canonical_code_id IS NULL` en canónicos.
   - Si `status IN ('merged','superseded')` entonces `canonical_code_id` no debería ser NULL.
   - No debe existir divergencia entre puntero legacy (`canonical_codigo`) y puntero por ID (`canonical_code_id`) para filas ya backfilleadas.

### 5.2 Métricas de control
- `% registros con code_id` (target 100%)
- `% registros no-canónicos con canonical_code_id` (target ~100%)
- Conteo de inconsistencias (target 0)

---

## 5.3 Riesgos conocidos (y por qué esta fase es la más frágil)

La Fase 1.5 suele ser el momento de mayor probabilidad de drift silencioso porque introduce dual-read/dual-write.

Riesgos típicos:

- Inconsistencias texto ↔ ID (bugs, rollback parcial, drift por escrituras laterales).
- Backfill incompleto (filas legacy que fuerzan fallback y crean “ilusiones de unicidad”).
- Merges concurrentes (carreras entre actualizaciones de punteros).
- Queries/índices parciales mal aplicados (permiten duplicidad canónica).

Mitigación mínima recomendada:

- Checks periódicos de consistencia + bloqueo en operaciones con efectos si hay divergencias.
- Operar merges/promociones **solo** sobre filas con `code_id` presente.
- Idempotencia y auditoría reforzada en merges.

Nota de contención: estos riesgos son aceptados **solo** porque el impacto epistemológico se mitiga con las **prohibiciones metodológicas** (no teoría/axialidad/GDS por ID durante 1.5) y con la **regla de precedencia** (ID manda) + bloqueo ante drift.

---

## 6) Alcance deliberadamente NO incluido en 1.5

Para mantener disciplina y reducir riesgo, se recomienda **no** abordar aún:

- Migrar evidencia (p. ej. `analisis_codigos_abiertos`) a referenciar `code_id`.
   - Motivo: evitar reinterpretar/reescribir evidencia antes de estabilizar identidad.
- Cambiar el grafo/Neo4j a IDs.
   - Motivo: evitar contaminar métricas estructurales (centralidad/comunidades) durante ontología dual.
- Eliminar `canonical_codigo`.
   - Motivo: mantener rollback y compatibilidad mientras se estabiliza el arbitraje por ID.

La fase 1.5 prepara el terreno y estabiliza el resolver.

---

## 6.1 Prohibiciones metodológicas explícitas (protección del proyecto)

Durante Fase 1.5:

- No ejecutar GDS / centralidad / comunidades basándose en `code_id`.
- No usar IDs como base de axialidad o teoría (categoría nuclear, saturación, etc.).

Si se requiere análisis exploratorio, debe basarse en la capa estable anterior (texto + resolver canónico legacy) y tratar los IDs como “infraestructura en prueba”.

---

## 7.1 Temporalidad y caducidad (cuánto puede vivir la ontología dual)

Fase 1.5 no debe convertirse en un “estado estacionario”. Recomendación:

- Establecer una ventana máxima de permanencia (p. ej. **1–2 releases** o **4–8 semanas**), o un número fijo de sprints.
- Si se excede, aplicar “freeze” parcial: permitir lectura/UI, pero **congelar operaciones con efectos** hasta completar Fase 2.

La salida de Fase 1.5 está definida por los criterios del apartado 7) y por la eliminación práctica del fallback por texto en operaciones con efectos.

---

## 9) Protocolo de Incidente Ontológico (texto ↔ ID)

Este protocolo aplica cuando se detecta drift, rollback parcial, o divergencias entre `canonical_codigo` y `canonical_code_id`.

### 9.1 Señales de alarma (stop-the-line)

- Operaciones con efectos detectan divergencia y se bloquean.
- Aumentan inconsistencias en checks periódicos.
- Se observa comportamiento “no determinista” (mismo `codigo` resuelve a canónicos distintos según endpoint).

### 9.2 Acciones inmediatas

1) **Congelar operaciones con efectos** (merges/promoción/sync/grafo). Mantener solo lectura.
2) Ejecutar diagnóstico SQL (abajo) por `project_id`.
3) Reparar con la regla: **ID manda**. Re-derivar texto desde ID o completar backfill.
4) Registrar evento de incidente (log + auditoría si aplica) con conteos y acción tomada.

### 9.3 Diagnóstico SQL recomendado (PostgreSQL)

> Estas queries asumen que ya existen las columnas propuestas: `code_id`, `canonical_code_id` además de `canonical_codigo`.

**A) Filas sin `code_id` (no deben participar en efectos)**

```sql
SELECT project_id, COUNT(*) AS missing_code_id
   FROM catalogo_codigos
 WHERE code_id IS NULL
 GROUP BY project_id
 ORDER BY missing_code_id DESC;
```

### 5.3 Freeze ontológico (condición pre-axial)

Para evitar sesgo retrospectivo y cambios ontológicos durante axialidad, se recomienda un **freeze explícito por `project_id`**:

- Antes de iniciar axial: ejecutar diagnóstico + backfill/repair hasta que `axial_ready=true` (bloqueos hard: identidad incompleta, canonicidad incompleta, divergencias texto↔ID, ciclos no triviales).
- Al iniciar axial: **activar freeze** (bloquea operaciones con efectos de Fase 1.5).
- Si se requiere intervenir: romper freeze solo con acción explícita y registrada.

Nota semántica:

- `canonical_code_id = code_id` (self-canonical) es estado esperado de códigos canónicos; no es inconsistencia.
- “Ciclo” bloqueante se entiende como ciclo **no trivial** (longitud > 1), no self-loop (A→A).

Implementación en este repo:
- Migración: [migrations/015_ontology_freeze.sql](migrations/015_ontology_freeze.sql)
- Endpoints admin:
   - `GET /api/admin/ontology/freeze?project=...`
   - `POST /api/admin/ontology/freeze/freeze?project=...`
   - `POST /api/admin/ontology/freeze/break?project=...` (requiere `confirm=true` y `phrase=BREAK_FREEZE`)

Enforcement:
- `POST /api/admin/code-id/backfill` y `POST /api/admin/code-id/repair` quedan **bloqueados (423)** cuando `dry_run=false` y el proyecto está en freeze.

**B) No-canónicos sin puntero por ID (inconsistencia)**

```sql
SELECT project_id, codigo, status
   FROM catalogo_codigos
 WHERE status IN ('merged','superseded')
    AND canonical_code_id IS NULL
 ORDER BY project_id, codigo;
```

**C) Divergencia entre puntero textual y puntero por ID**

```sql
SELECT src.project_id,
          src.codigo AS source_codigo,
          src.status,
          src.canonical_codigo AS canonical_text,
          tgt.codigo AS canonical_by_id
   FROM catalogo_codigos src
   JOIN catalogo_codigos tgt
      ON tgt.project_id = src.project_id
    AND tgt.code_id = src.canonical_code_id
 WHERE src.canonical_code_id IS NOT NULL
    AND src.canonical_codigo IS NOT NULL
    AND lower(src.canonical_codigo) <> lower(tgt.codigo)
 ORDER BY src.project_id, src.codigo;
```

**D) Cadenas largas / posible ciclo (inspección)**

```sql
WITH RECURSIVE chain AS (
   SELECT project_id,
             codigo,
             code_id,
             canonical_code_id,
             ARRAY[code_id] AS path,
             0 AS depth
      FROM catalogo_codigos
    WHERE canonical_code_id IS NOT NULL
   UNION ALL
   SELECT c.project_id,
             c.codigo,
             c.code_id,
             c.canonical_code_id,
             chain.path || c.code_id,
             chain.depth + 1
      FROM chain
      JOIN catalogo_codigos c
         ON c.project_id = chain.project_id
       AND c.code_id = chain.canonical_code_id
    WHERE chain.depth < 25
)
SELECT project_id, codigo, depth, path
   FROM chain
 WHERE depth >= 10
      OR (canonical_code_id = ANY(path))
 ORDER BY depth DESC;
```

### 9.4 Reparación (ID manda)

**Caso 1: existe `canonical_code_id` correcto, texto drifted**

Re-derivar `canonical_codigo` desde el target por ID:

```sql
UPDATE catalogo_codigos src
    SET canonical_codigo = tgt.codigo
   FROM catalogo_codigos tgt
 WHERE tgt.project_id = src.project_id
    AND tgt.code_id = src.canonical_code_id
    AND (src.canonical_codigo IS NULL OR lower(src.canonical_codigo) <> lower(tgt.codigo));
```

**Caso 2: existe texto, falta `canonical_code_id` (best-effort)**

```sql
UPDATE catalogo_codigos src
    SET canonical_code_id = tgt.code_id
   FROM catalogo_codigos tgt
 WHERE tgt.project_id = src.project_id
    AND src.canonical_codigo IS NOT NULL
    AND src.canonical_code_id IS NULL
    AND lower(tgt.codigo) = lower(src.canonical_codigo);
```

Si tras esto persisten inconsistencias, mantener freeze y resolver manualmente (o completar backfill de IDs / reparar merges concurrentes).

---

## 10) Panel de transición a `code_id` (frontend) — rol, límites y prohibiciones

El sistema debe poder operarse desde el frontend **sin** contaminar el flujo investigativo.

### 10.1 Rol

- Es una **herramienta de mantenimiento de identidad conceptual (Fase 1.5)**, no un panel analítico.
- Su función es: **observabilidad + backfill + repair** bajo guardas.

### 10.2 Ubicación y permisos (condición no negociable)

- Debe vivir en una sección tipo **Administración / Sistema / Mantenimiento**.
- Acceso restringido: **solo admin** y preferentemente con **feature flag**.
- No debe aparecer en **Codificación abierta/axial/selectiva**, ni en el flujo normal del investigador.

### 10.3 Qué puede mostrar (observabilidad, no inferencia)

- %/conteos: `missing_code_id`, `missing_canonical_code_id`, `divergences_text_vs_id`.
- Listas de inconsistencias **en muestra** (no ranking, no recomendaciones).
- Última ejecución (quién/cuándo) si se decide auditar.

### 10.4 Acciones permitidas (con guardas)

- Backfill controlado:
   - `dry-run` obligatorio por defecto.
   - Preview de impacto (conteos), luego ejecución en batches.
- Repair controlado:
   - Solo habilitado cuando hay drift.
   - Confirmaciones explícitas.
   - Regla: **ID manda**.

### 10.5 Acciones explícitamente prohibidas

- Visualizaciones relacionales o métricas interpretables.
- Rankings de códigos, sugerencias semánticas, “parecidos”, propuestas automáticas.
- Cualquier copy/UX que sugiera significado, teoría, importancia o estructura.

### 10.6 Reglas de seguridad mínimas

- Separar endpoints: diagnóstico (GET) vs operaciones (POST).
- `dry-run` por defecto, `confirm=true` para ejecutar.
- Bloqueo concurrente de operaciones de mantenimiento (advisory lock).
- Logging fuerte: quién, proyecto, operación, filas afectadas.

---

## 7) Criterios de salida (Definition of Done)

Se considera completada la Fase 1.5 cuando:

- `catalogo_codigos` tiene `code_id` completo (100% backfill).
- `canonical_code_id` está backfilleado para no-canónicos.
- Existe resolver dual (IDs preferidos, fallback texto) y está usado en puntos críticos.
- No se rompe el UI ni endpoints existentes.
- Se documenta el plan de fase 2 (migrar consumo interno a ID) y rollback.

---

## 8) Próximo paso (Fase 2 — migración interna real)

Una vez estabilizada 1.5:

- Migrar escrituras/consumos internos a operar primariamente por `code_id`.
- Introducir `code_merge_events` (auditoría dura) si se requiere defendibilidad fuerte.
- Evaluar migración de evidencia a IDs (solo si hay ROI claro).
