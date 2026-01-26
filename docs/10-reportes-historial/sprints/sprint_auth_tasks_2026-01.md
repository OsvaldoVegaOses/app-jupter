# Sprint: Auth Task Scope (Runner / Reportes)

> Fecha: 2026-01-13

## Objetivo
Evitar fuga de información y acciones cruzadas entre usuarios en endpoints que operan por `task_id` (runner) y en descargas/listados de artefactos. En particular: garantizar que **solo el creador** de una tarea (o un **admin**) puede consultar `status/result` o reanudar (`resume`) una ejecución.

## Contexto
- Hay tareas in-memory (`_coding_suggest_runner_tasks`) accesibles por `task_id`.
- En un ambiente multiusuario, un `task_id` puede filtrarse (logs, UI, soporte) y permitir que otro usuario consulte resultados.
- Los checkpoints persistidos en `logs/runner_checkpoints/<project>/<task_id>.json` habilitan `resume`, por lo que deben incluir metadata de auth y verificarse.

## Alcance (este sprint)
### 1) Task ownership (Runner)
- Guardar metadata de auth al crear una tarea: `auth = { user_id, org, roles }`.
- Persistir `auth` dentro de cada checkpoint y dentro del report JSON (`logs/runner_reports/...`).
- Enforzar acceso:
  - `GET /api/coding/suggest/runner/status/{task_id}`
  - `GET /api/coding/suggest/runner/result/{task_id}`
  - `POST /api/coding/suggest/runner/resume`
  - Regla: solo `auth.user_id` o rol `admin`.
- Compatibilidad:
  - Checkpoints/tareas sin `auth` (legacy): permitir solo a `admin`.

### 2) Artefactos (Reportes)
- Mantener `Depends(require_auth)` en:
  - `GET /api/reports/artifacts`
  - `GET /api/reports/artifacts/download`
- Implementado: restringir descargas a `require_role(["admin","analyst"])`.

### 3) Reportes largos como Jobs (Async)
- Objetivo: evitar timeouts y mantener trazabilidad/ownership en reportes costosos (LLM).
- Implementado:
  - Doctoral: `POST /api/reports/doctoral/execute` + `GET /api/reports/doctoral/status/{task_id}` + `GET /api/reports/doctoral/result/{task_id}`
  - Stage4 final: `POST /api/reports/stage4-final/execute` + `GET /api/reports/stage4-final/status/{task_id}` + `GET /api/reports/stage4-final/result/{task_id}`
- Seguridad:
  - `execute`: `require_role(["admin","analyst"])`
  - `status/result`: owner-only (admin override), con fallback legacy admin-only si faltase `auth`.
- Persistencia:
  - Doctoral guarda `.md` en `reports/<project>/doctoral/` y crea registro DB.
  - Stage4 final guarda `.json` en `reports/<project>/` para aparecer en Artefactos.

## Criterios de aceptación
- Un usuario A puede ejecutar runner y consultar su `status/result`.
- Un usuario B (no admin) recibe `403` al consultar el `task_id` de A.
- Un admin puede consultar/diagnosticar tareas de otros usuarios.
- `resume` falla con `403` si el checkpoint pertenece a otro usuario.
- Los checkpoints nuevos guardan `auth`.

## Implementación (referencias)
- Backend: [backend/routers/coding.py](backend/routers/coding.py)
  - `_assert_task_access`, `_assert_checkpoint_access`
  - Persistencia de `auth` en checkpoint/report

## Riesgos / Notas
- El store in-memory no es multi-worker; en futuro (Celery/Redis) replicar este patrón con ownership en storage compartido.
