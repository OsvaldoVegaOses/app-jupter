# Dictamen formal — Fase 1: Consolidación y Limpieza ("El Puente")

> **Fecha:** 22 Enero 2026  
> **Estatus:** Dictamen final (defendible)  
> **Ámbito:** Códigos candidatos (deduplicación Pre‑Hoc + revisión humana + merges gobernados)

---

## 1) Dictamen

La **Fase 1 – Consolidación y Limpieza (El Puente)** se encuentra **implementada end‑to‑end**, cubriendo el flujo completo de **deduplicación Pre‑Hoc**, **revisión humana** y **merges gobernados** sobre **códigos candidatos**, con garantías de **no‑pérdida de evidencia**, **idempotencia**, **trazabilidad mínima** y **observabilidad**.

La implementación es coherente con la especificación funcional ([docs/04-arquitectura/fusion_duplicados_api_spec.md](docs/04-arquitectura/fusion_duplicados_api_spec.md)) y está respaldada por evidencia técnica en **backend**, **base de datos**, **frontend** y **pruebas E2E**.

Las divergencias identificadas respecto de la spec son **menores**, **explícitas** y **no bloqueantes**, y no afectan la **validez metodológica** ni la **completitud operativa** de la fase.

---

## 2) Evidencia técnica (resumen)

- **Backend:**
  - `POST /api/codes/check-batch` (Pre‑Hoc, sin ejecución automática).
  - `POST /api/codes/candidates/merge` (merge manual por IDs, con `dry_run` e idempotencia).
  - `POST /api/codes/candidates/auto-merge` (merge masivo por pares, con `dry_run` e idempotencia).
- **Base de datos:**
  - `codigos_candidatos` con restricción `UNIQUE(project_id, codigo, fragmento_id)`.
  - Auditoría mínima por `codigo_versiones` (best-effort) para operaciones de merge.
  - Tabla de idempotencia `api_idempotency` para reintentos seguros.
- **Frontend:**
  - Cliente API para check‑batch/merge/auto‑merge con generación automática de `idempotency_key`.
- **E2E:**
  - Test Playwright que dispara `/api/codes/check-batch` desde UI y valida el modal.

---

## 3) Mini tabla “Spec → Implementación”

| Requisito (spec) | Estado | Evidencia (archivo/endpoint) |
|---|---:|---|
| Pre‑Hoc conservador (alerta, no auto‑merge “caja negra”) | ✅ | `POST /api/codes/check-batch` (backend) + UI modal |
| Merge manual (por IDs) | ✅ | `POST /api/codes/candidates/merge` |
| Auto‑merge masivo (por pares) | ✅ | `POST /api/codes/candidates/auto-merge` |
| Semántica de no pérdida (mover evidencia al target si no existe) | ✅ | `merge_candidates*` (UPDATE con `NOT EXISTS`) |
| Deduplicación sin pérdida (si evidencia ya existe, marcar `fusionado`) | ✅ | `merge_candidates*` (UPDATE con `EXISTS`, `estado='fusionado'`) |
| Idempotencia (reintentos seguros) | ✅ | `api_idempotency` + `idempotency_key` en endpoints |
| Auditoría mínima (quién/cuándo/por qué, al menos best-effort) | ✅ | `codigo_versiones` (acciones de merge) |
| Alineación de rutas `/api/codes/*` y alias legacy `/api/coding/*` | ✅ | Alias de endpoints (deprecado) |

> Nota: esta tabla resume el cumplimiento. Para detalle de implementación, ver el informe de bitácora: [docs/06-metodologia/informe_pre_hoc_deduplicacion_codigos.md](docs/06-metodologia/informe_pre_hoc_deduplicacion_codigos.md).

---

## 4) Divergencias menores (no bloqueantes)

1) **`memo` no es obligatorio** en merges manuales.
   - La spec lo recomienda como estándar epistemológico; la implementación lo deja opcional.

2) **Nivel de auditoría por fila (hard audit) no es uniforme**.
   - Se asegura trazabilidad mínima vía `codigo_versiones` (best‑effort), pero no todas las filas “movidas” registran actor/timestamp en la propia fila (aunque sí queda rastro en versiones).

Estas divergencias no invalidan la fase: la gobernanza, la no‑pérdida y la operación end‑to‑end se mantienen.

---

## 5) Recomendaciones (no bloqueantes)

### 5.1 Endurecer `memo` obligatorio (opcional)
Recomendado si se busca elevar el estándar epistemológico:
- Requerir `memo` en `POST /api/codes/candidates/merge` (y opcional en auto‑merge).
- Mantenerlo como “no obligatorio” si se prioriza fricción mínima operativa.

### 5.2 Decidir explícitamente el nivel de auditoría por fase
Para mostrar diseño consciente:
- **Fase 1 (candidatos):** auditoría ligera (suficiente para operación + trazabilidad mínima).
- **Catálogo definitivo:** auditoría dura (eventos de merge/rename/supersede con identidad estable y reconstrucción completa).

### 5.3 Mantener la tabla Spec→Implementación como artefacto vivo
Actualizarla cuando:
- se endurezcan validaciones (memo, códigos de error),
- se amplíe auditoría (eventos),
- se migre a identidad por `code_id`.
