# Desarrollo pendiente — Modelo ontológico por ID (canonical_code_id) + estado `superseded`

> **Fecha:** 22 Enero 2026  
> **Estatus:** reflexión / diseño futuro (no implementado aún)  
> **Contexto:** El sistema ya aplica ontología con `status` y resolución canónica (hoy basada en `canonical_codigo` en `catalogo_codigos`). Este documento captura la reflexión completa para evaluar el salto a identidad estable por ID (`code_id`) y la introducción opcional del estado `superseded`.

---

## 1) Problema que resuelve (por qué existe esta propuesta)

Hoy la ontología funciona, pero está apoyada en el **texto del código** (`codigo`) como identidad práctica (y en un puntero canónico también textual, `canonical_codigo`). Eso es suficiente mientras:

- los merges sean pocos,
- los renombres (label changes) sean raros,
- y el sistema no necesite “historia fuerte” (reconstrucción metodológica detallada).

A medida que crece el uso, aparecen límites típicos del enfoque “texto como identidad”:

- **Renombre ≠ nuevo concepto**: cambiar el label debería ser un cambio cosmético, no una mutación de identidad.
- **Merges frecuentes**: si hay muchos merges/duplicados, la gestión por texto se vuelve frágil (colisiones, normalización, tildes, mayúsculas, etc.).
- **Auditoría científica**: reconstruir “qué pasó” es más defendible si existe una identidad de concepto independiente del label y un registro explícito de eventos.

---

## 2) Qué se propone exactamente

### 2.1 Modelo por identidad estable
Introducir una identidad estable del concepto:

- `code_id`: identificador estable (UUID/int) del concepto.
- `canonical_code_id`: puntero al concepto canónico.
  - Regla recomendada: **`canonical_code_id IS NULL` si el registro ya es canónico**.

Mantener `codigo` como **label** (texto visible) y permitir renombres sin romper referencias.

### 2.2 Estados ontológicos
Estados mínimos:

- `active`: vigente.
- `merged`: fue fusionado (sinónimo/duplicado absorbido por un canónico).
- `rejected` (o `deprecated`): descartado/no usar.

**Sugerencia avanzada (opcional):**

- `superseded`: fue **reemplazado por evolución** del esquema (p. ej., una categoría axial más madura reemplaza una anterior).

Diferencia clave:
- `merged` ≈ equivalencia/sinonimia (eran “lo mismo”).
- `superseded` ≈ sucesión temporal/teórica (no necesariamente “lo mismo”; es “lo reemplazamos”).

---

## 3) Valor real (cuándo aporta ROI alto vs bajo)

### 3.1 ROI alto (vale la pena priorizar)
Implementar `code_id + canonical_code_id` aporta valor claro si:

- hay **renombres** frecuentes y no quieres que el sistema los trate como cambios de identidad,
- hay **muchos merges** (o se prevé escalamiento) y necesitas consistencia fuerte,
- el producto se orienta a **auditabilidad** (entregables defendibles) y trazabilidad metodológica,
- hay multi-proyecto/multi-org donde el mismo `codigo` textual podría colisionar semánticamente,
- quieres endurecer integridad con **FKs y constraints** (más limpio/rápido que joins por texto).

### 3.2 ROI bajo (puede postergarse)
No es urgente si:

- el volumen de merges es bajo,
- la ontología actual ya evita contaminación (`merged` excluidos de análisis),
- el equipo no necesita aún “historia fuerte” por evento,
- el costo de migración y de cambio de contratos internos no compensa todavía.

---

## 4) Invariantes que deben mantenerse (independiente de implementación)

1) **Resolver canónico obligatorio**: todo consumo/escritura “con efectos” (axial, proyección, algoritmos, sync) debe resolver al canónico.
2) **`merged` no entra a análisis**: excluir de proyecciones/algoritmos para evitar sesgo y duplicidad.
3) **PostgreSQL es el ledger**: Neo4j es proyección analítica mutable (reconstruible).

Estas reglas ya existen en la arquitectura actual; el salto a `code_id` busca hacerlas más robustas.

---

## 5) Diseño propuesto (esquema mínimo orientativo)

> Nota: nombres a ajustar al estilo actual del repo.

### 5.1 Tabla base de conceptos
`catalogo_codigos` (o nueva `codes`) incluiría:

- `code_id` (PK)
- `codigo` (label visible)
- `status` (`active|merged|rejected|superseded|...`)
- `canonical_code_id` (nullable FK a `code_id`)
- `created_at`, `updated_at`

Índices/constraints recomendados:

- `CHECK (canonical_code_id IS NULL OR canonical_code_id <> code_id)`
- `INDEX (canonical_code_id)`
- `INDEX (status)`
- (Opcional) `UNIQUE (codigo)` si el negocio lo exige; si no, `UNIQUE (org_id, project_id, codigo)`.

### 5.2 Eventos de merge/sucesión (auditabilidad fuerte)
Tabla `code_merge_events` (o `catalogo_codigos_eventos`):

- `event_id`
- `from_code_id`
- `to_code_id`
- `event_type` (`merge`, `supersede`, `rename`, etc.)
- `actor_user_id`
- `reason` / `memo`
- `created_at`

Esto habilita reconstrucción temporal (“cómo llegamos aquí”).

### 5.3 Artefacto SQL (para pensar la migración)

Se incluye un DDL propuesto (diseño futuro) para evolucionar `catalogo_codigos` hacia `code_id`/`canonical_code_id` manteniendo compatibilidad temporal:

- [docs/04-arquitectura/desarrollo_pendiente/propuesta_sql_migracion_code_id.sql](docs/04-arquitectura/desarrollo_pendiente/propuesta_sql_migracion_code_id.sql)

---

## 6) Cómo encaja `superseded` sin romper el sistema

Recomendación:

- El **resolver canónico** puede tratar `superseded` como redirección (igual que `merged`) si existe `canonical_code_id`.
- La diferencia queda para:
  - reporting temporal,
  - auditoría metodológica,
  - UI (mostrar “reemplazado por…” en lugar de “fusionado”).

**Decisión de modelado importante**
- Si “categorías axiales” son una entidad distinta a “códigos”, considerar un catálogo separado para categorías/relaciones. Si comparten catálogo, `superseded` aplica directo.

---

## 7) Ruta de migración incremental (sin ruptura)

Enfoque recomendado: **faseado**, manteniendo el UI en `codigo` (label) mientras el backend migra internamente.

### Fase 0 — Documentación y contratos
- Definir qué endpoints internos aceptan `code_id` vs `codigo`.
- Decidir compatibilidad: UI sigue enviando `codigo`, backend resuelve a `code_id`.

### Fase 1 — Backfill de IDs
- Agregar `code_id` y `canonical_code_id` al catálogo.
- Backfill: asignar `code_id` a cada código existente.
- Mapear `canonical_codigo` → `canonical_code_id`.

Diseño detallado recomendado (transición controlada / compatibilidad dual):
- [docs/04-arquitectura/desarrollo_pendiente/fase_1_5_transicion_controlada_a_code_id.md](docs/04-arquitectura/desarrollo_pendiente/fase_1_5_transicion_controlada_a_code_id.md)

### Fase 2 — Resolver por ID
- Introducir `resolve_canonical_code_id(...)` y `resolve_bulk(...)`.
- Ajustar puntos críticos (promoción, axial, algoritmos) para operar con IDs.

### Fase 3 — Eventos
- Escribir `code_merge_events` al fusionar/sustituir.
- Exponer endpoint de historial (si se requiere).

### Fase 4 — Limpieza
- (Opcional) dejar `canonical_codigo` como columna derivada o eliminarla cuando todo use ID.

---

## 8) Riesgos y mitigaciones

- **Riesgo:** migración rompe joins existentes por texto.
  - **Mitigación:** compatibilidad dual temporal (seguir aceptando `codigo` en API/UI), resolver internamente.

- **Riesgo:** duplicidad de labels (`codigo`) en distintos contextos.
  - **Mitigación:** definir unicidad por scope (org/proyecto) o aceptar duplicidad y operar por `code_id`.

- **Riesgo:** Neo4j queda desincronizado.
  - **Mitigación:** tratar Neo4j como proyección reconstruible; priorizar PG; re-sync por `code_id`.

---

## 9) Criterios de “listo para implementar”

Antes de ejecutar este cambio, idealmente:

- Hay evidencia de dolor: merges/renombres frecuentes, errores por normalización, necesidad de auditoría fuerte.
- Existe un plan claro de compatibilidad API/UI.
- Están identificados los puntos de escritura/consumo que deben pasar por resolver.

---

## 10) Decisión recomendada (hoy)

- Mantener el diseño actual (status + resolver canónico) como base estable.
- Documentar `code_id + canonical_code_id` y `code_merge_events` como fase futura.
- Considerar `superseded` si el equipo quiere auditar evolución teórica (especialmente categorías axiales). Si no hay esa necesidad, puede postergarse.
