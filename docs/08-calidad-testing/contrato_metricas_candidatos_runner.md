# Contrato único de métricas: Códigos Candidatos (Bandeja) vs Runner Semántico

**Última actualización:** 2026-01-13

Este documento define **un único contrato** para evitar confusiones entre:
- métricas **canónicas** del backlog (Bandeja de Códigos Candidatos, en PostgreSQL), y
- métricas **por corrida** del Runner Semántico (lo que el runner intentó/registró en una ejecución).

---

## 1) Fuente canónica (PostgreSQL)

La fuente de verdad del backlog es la tabla:
- `codigos_candidatos` (PostgreSQL)

Definiciones canónicas:
- **Pendientes (DB)**: `COUNT(*) WHERE project_id = <proyecto> AND estado = 'pendiente'`
  - Implementación: `count_pending_candidates(pg, project_id)` en `app/postgres_block.py`.
  - Endpoint: `GET /api/codes/candidates/pending_count?project=<proyecto>`.

- **Totales por estado (DB)**: conteos por `estado` (`pendiente`, `validado`, `rechazado`, `fusionado`).
  - Implementación típica: summary/stats de candidatos (según endpoint de stats/listado).

> Regla: cualquier UI que muestre “Pendientes” sin calificador debe apuntar al conteo canónico de DB.

---

## 2) Métricas del Runner (por corrida)

El runner expone contadores que son **por ejecución**:
- **`candidates_submitted` (runner)**: cantidad de filas que el runner intentó insertar/actualizar en `codigos_candidatos` durante la corrida.
  - Semántica: es un contador “de envío” del runner (no necesariamente “nuevas filas netas” si hubo upserts/duplicados).
  - Uso recomendado en UI: rotular como **“Candidatos enviados (runner)”**.

- **`memos_saved` (runner)**: cantidad de memos persistidos en disco durante la corrida.

- **`llm_calls`, `llm_failures` (runner)**: telemetría de llamadas al LLM y fallos.

---

## 3) Campos recomendados en `runner/status`

Para alinear runner y bandeja sin cargar Postgres en cada poll:
- **`candidates_pending_before_db`**: pendientes (DB) medido al inicio de la corrida.
- **`candidates_pending_after_db`**: pendientes (DB) medido al finalizar (solo disponible cuando status es `completed`/`error`).

Esto permite:
- mostrar en UI el “antes/después” y
- explicar por qué `candidates_submitted` (runner) **no coincide** con `pending_count` (DB).

---

## 4) Trazabilidad del Runner (artefactos)

Cada corrida se puede auditar con `task_id`.

Artefactos en disco:
- **Checkpoint (estado reanudable):** `logs/runner_checkpoints/<project>/<task_id>.json`
  - contiene cursor, seeds visitadas, iteraciones y contadores.
- **Report (resumen post-mortem):** `logs/runner_reports/<project>/<task_id>.json`
  - resumen de la corrida (status, steps, contadores, pendientes before/after, errores).
- **Memos (markdown):** `notes/<project>/runner_semantic/*.md`
  - descargables vía endpoint seguro `/api/notes/{project}/download?rel=<ruta_relativa>`.

Trazabilidad en DB:
- `codigos_candidatos.fuente_origen = 'semantic_suggestion'` para inserciones del runner.
- `codigos_candidatos.fuente_detalle` incluye `task_id=...` (y archivo/step/seed) para correlación.

---

## 5) Reglas UX (nomenclatura)

- “**Pendientes**” → siempre DB canónico (bandeja).
- “**Candidatos enviados (runner)**” → contador por corrida.
- Si se muestran ambos, preferir:
  - “Pendientes (Bandeja, total)” y
  - “Enviados (Runner, esta corrida)”.

---

## 6) Notas de interpretación (casos comunes)

- `candidates_submitted` > 0 pero “Pendientes (DB)” no sube:
  - puede haber colisiones por `UNIQUE(project_id, codigo, fragmento_id)` (upsert),
  - el candidato pudo insertarse pero luego fusionarse/validarse,
  - o el runner estaba configurado sin `submit_candidates`.

- “Pendientes (DB)” baja durante el runner:
  - normal si hay otro usuario (o proceso) validando/fusionando en paralelo.
