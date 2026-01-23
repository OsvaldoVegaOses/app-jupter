# Informe de oportunidades de mejora (no bloqueantes)

**Proyecto:** APP_Jupter (Backend FastAPI + Worker + Frontend React)

**Fecha:** 2026-01-21

## Alcance y criterio
Este informe lista mejoras observadas que elevan **robustez, mantenibilidad, seguridad, trazabilidad y operabilidad**.

- **No bloqueante**: ninguna recomendación es requisito inmediato para operar en desarrollo.
- Se prioriza **buena práctica** (preventiva) vs. “fix de bug” puntual.
- Se incluyen sugerencias con **impacto/beneficio** y **esfuerzo estimado**.

---

## 1) Esquema y migraciones de PostgreSQL

### 1.1 Consolidar DDL en migraciones versionadas (Alembic o equivalente)
**Observación:** existe una estrategia de `ensure_*_table()` idempotente (muy útil en dev), pero se vuelve difícil controlar drift y auditar cambios de esquema en ambientes compartidos.

**Recomendación:**
- Adoptar migraciones versionadas (p.ej. Alembic) para:
  - cambios de columnas/tipos
  - índices
  - constraints (CHECK/UNIQUE)
- Mantener `ensure_*` como “bootstrap mínimo” solo para dev o scripts de instalación rápida.

**Impacto:** alto (reduce drift y 500s por esquemas legacy)

**Esfuerzo:** medio

### 1.2 Constraints explícitas para estados y campos críticos
**Recomendación:**
- Agregar `CHECK`/`ENUM` lógica para `codigos_candidatos.estado` (pendiente/hipotesis/validado/rechazado/fusionado) y para `codigo_versiones.accion` (conjunto acotado + fallback “legacy”).
- Agregar `NOT NULL` donde aplique y backfill previo.

**Impacto:** medio/alto (calidad de datos, queries más confiables)

**Esfuerzo:** medio

### 1.3 Índices orientados a los patrones de consulta reales
**Recomendación:**
- Revisar queries típicas de bandeja e historial para proponer índices compuestos:
  - `codigos_candidatos(project_id, estado, updated_at DESC)`
  - `codigos_candidatos(project_id, codigo)`
  - `codigos_candidatos(project_id, estado, codigo)` si hay filtros combinados
  - `codigo_versiones(project_id, codigo, version DESC)` o `(project_id, codigo, created_at DESC)`

**Impacto:** medio (mejora latencia en UI y reduce timeouts)

**Esfuerzo:** bajo/medio

---

## 2) Transacciones, consistencia e idempotencia

### 2.1 Política unificada de commits (evitar commits internos opcionalmente)
**Observación:** algunas funciones helper realizan `pg.commit()` internamente (p.ej. logging/auditoría). Esto es práctico pero complica componer múltiples operaciones en una sola transacción.

**Recomendación (opcional y no bloqueante):**
- Definir una convención:
  - helpers “atómicos” (hacen commit) vs
  - helpers “transactional-friendly” (no commit; el caller controla).
- Alternativa de bajo riesgo: añadir parámetro `commit: bool = True` en helpers clave.

**Impacto:** medio (reduce “transaction aborted” en flujos encadenados)

**Esfuerzo:** medio

### 2.2 Idempotencia consistente en operaciones masivas
**Observación:** ya existe patrón de `idempotency_key` en merges; es positivo.

**Recomendación:**
- Extender idempotencia a otras operaciones con side-effects masivos:
  - `revert_validated_candidates_to_pending`
  - `promote_to_definitive` (modo masivo)
- Persistir idempotency key en una tabla de “operation_log” con `UNIQUE(project_id, idempotency_key)`.

**Impacto:** medio (evita duplicados por reintentos)

**Esfuerzo:** medio

---

## 3) Auditoría y trazabilidad (historial)

### 3.1 Estandarizar payload de auditoría
**Observación:** hay eventos de historial con `accion` + `memo_nuevo` (útil), pero el “memo” tiende a mezclar texto humano y campos técnicos.

**Recomendación:**
- Definir un mini-esquema estándar en `memo_nuevo` (o mejor: nueva columna JSONB opcional `meta`) con campos:
  - `actor`: user_id / system
  - `source`: ui / api / script / worker
  - `candidate_id` / `source_ids` / `target_codigo`
  - `counts` (reverted_rows, total, etc.)
- Mantener un `memo_text` humano opcional.

**Impacto:** alto para auditoría y analítica posterior

**Esfuerzo:** medio

### 3.2 UI: traducción de `accion` a etiquetas humanas
**Recomendación:**
- Mapear acciones como `candidate_validate`, `candidate_reject`, `candidates_revert_validated` a etiquetas del tipo:
  - “Validación de candidato”
  - “Rechazo de candidato”
  - “Revert masivo a pendiente”
- Mostrar “resumen” de campos clave del memo/meta.

**Impacto:** medio (usabilidad + auditoría legible)

**Esfuerzo:** bajo

---

## 4) Manejo de errores y contrato API

### 4.1 Unificar formato de error (Problem Details)
**Observación:** hay mezcla de `HTTPException(detail=str)` y `api_error(...)` (centralizado). Esto puede producir respuestas heterogéneas y dificultar el manejo consistente en frontend.

**Recomendación:**
- Adoptar un contrato de error único (p.ej. RFC 7807 Problem Details):
  - `type`, `title`, `status`, `detail`, `instance`, `code`, `request_id`
- Asegurar que todas las rutas “atrapen” excepciones y las normalicen.

**Impacto:** alto (DX/UX, debugging, integraciones)

**Esfuerzo:** medio

### 4.2 Timeouts: política explícita por tipo de endpoint
**Observación:** existen helpers para timeout de consultas PG en hilo (`run_pg_query_with_timeout`).

**Recomendación:**
- Definir una tabla de timeouts por endpoint (p.ej. 5s dashboard, 15s queries complejas, 60s runners) y aplicarla de forma consistente.

**Impacto:** medio

**Esfuerzo:** bajo

---

## 5) Observabilidad (logging, métricas, tracing)

### 5.1 Métricas /metrics (Prometheus) y latencias por dependencia
**Observación:** hay request_id middleware y health checks; muy buen punto de partida.

**Recomendación:**
- Añadir métricas:
  - latencia por endpoint
  - rate de 4xx/5xx
  - latencia y errores por dependencia (PG/Neo4j/Qdrant/AOAI)
- Exportar `/metrics` (Prometheus) y/o logs agregables.

**Impacto:** alto (operación estable, detectar degradación temprano)

**Esfuerzo:** medio

### 5.2 Propagación de `request_id` hacia Celery
**Recomendación:**
- Incluir `request_id`, `session_id`, `project_id` en payload de tareas Celery y bindearlos a logs del worker.

**Impacto:** medio/alto (trazabilidad end-to-end)

**Esfuerzo:** bajo/medio

---

## 6) Seguridad y multi-tenant

### 6.1 Separación explícita “DEV vs PROD”
**Recomendación:**
- Asegurar que configuraciones de desarrollo (CORS amplio, allow_origin_regex, API keys de demo) estén protegidas por variables `ENV=dev`.
- Tener un checklist de hardening:
  - CORS restringido
  - rate limiting acorde
  - headers de seguridad

**Impacto:** alto

**Esfuerzo:** bajo/medio

### 6.2 Auditoría de autorización (org/project)
**Observación:** ya existen controles por organización; se han visto errores de “organización no coincide” en flujos.

**Recomendación:**
- Tests dedicados para:
  - usuario de otra org no lista/valida/mergea
  - admin sí puede
- Mensajes de error uniformes con `request_id`.

**Impacto:** alto (previene leaks de datos)

**Esfuerzo:** medio

---

## 7) Frontend: resiliencia y DX

### 7.1 Parsing consistente de errores del backend
**Observación:** el cliente `api.ts` dispara eventos `api-error`, pero usualmente lee `response.text()`; si el backend devuelve JSON con `detail`/`code`, se pierde estructuración.

**Recomendación:**
- Intentar parsear JSON (si `content-type` indica JSON) y extraer `detail`, `code`, `request_id`.

**Impacto:** medio

**Esfuerzo:** bajo

### 7.2 Health checks: diferenciar “frontend ok” vs “backend ok”
**Observación:** se usa `/healthz` para conectividad (bien).

**Recomendación:**
- En UI, distinguir:
  - “Frontend servido” (Vite)
  - “Backend reachable”
  - “Servicios downstream” (health/full)

**Impacto:** bajo/medio

**Esfuerzo:** bajo

---

## 8) Calidad: pruebas y CI

### 8.1 Pruebas mínimas automatizadas para regresiones críticas
**Recomendación:**
- Agregar tests (unit/integration) para:
  - compatibilidad `ensure_code_versions_table`
  - creación de eventos de historial en validate/reject/revert/promote/merge
  - flujos de multi-tenant

**Impacto:** alto

**Esfuerzo:** medio

### 8.2 CI: “smoke test” rápido
**Recomendación:**
- Pipeline con:
  - `pytest -q` backend
  - `npm run build` frontend
  - (opcional) Playwright básico

**Impacto:** medio

**Esfuerzo:** bajo/medio

---

## 9) Prioridad sugerida (no bloqueante)

1) **Migraciones + constraints + índices** (reduce drift y 500s)
2) **Contrato de error unificado** (mejora UX y debugging)
3) **Métricas + propagación request_id a Celery** (operabilidad)
4) **Tests focalizados** (evita regresiones)
5) **UI: etiquetas de acciones de historial** (mejora auditoría humana)

---

## Anexo: checklist rápido de buena práctica (implementación gradual)

- [ ] Migraciones versionadas (Alembic)
- [ ] Índices compuestos según queries reales
- [ ] `CHECK` para estados y acciones
- [ ] Normalización de respuestas de error con `request_id`
- [ ] Métricas `/metrics` y dashboards
- [ ] Propagación `request_id`/`session_id` a worker
- [ ] Tests de multi-tenant y auditoría/historial
- [ ] Mapeo UI de acciones a etiquetas
