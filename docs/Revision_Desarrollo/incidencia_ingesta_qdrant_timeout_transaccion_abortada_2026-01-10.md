# Incidencia: error de ingesta con Qdrant timeout → transacción PG abortada (500)

**Fecha:** 2026-01-10  
**Componente:** `/api/upload-and-ingest` (backend) + pipeline `app.ingestion`  
**Proyecto afectado (ejemplo):** `jd-009`  
**Archivo observado (ejemplo):** `Entrevista_Dirigentas_UV_20_La_Florida_20260110_164758.docx`

## Resumen
Durante la ingesta vía `POST /api/upload-and-ingest` el sistema registró un **timeout de escritura en Qdrant**, que gatilló el **split de batch**. Posteriormente la operación falló con:

- `current transaction is aborted, commands ignored until end of transaction block`

El endpoint respondió **HTTP 500**, pero el documento quedó **parcialmente persistido** (principalmente en Qdrant), lo que explica que el frontend mostrara la entrevista “ingerida” pero con un **número distinto de fragmentos** (p. ej. 96 detectados vs 64 visibles).

## Evidencia en logs
Referencias relevantes en [logs/app.jsonl](../../logs/app.jsonl):

- Inicio de ingesta y total de fragmentos detectados (`fragments: 96`).
- Timeout y split en Qdrant: evento `qdrant.upsert.split` con razón `The write operation timed out`.
- Después del split, se observan `qdrant.upsert.success` para sub-batches.
- Falla final del endpoint: `api.upload_and_ingest.ingest_error` con `current transaction is aborted...` y `status_code: 500`.

> Nota: el mensaje “current transaction is aborted …” normalmente **no es el error raíz**, sino la consecuencia de que una sentencia anterior en la misma conexión/transacción falló y no se hizo rollback.

## Impacto
- **Ingesta no atómica**: se puede grabar parcialmente en Qdrant, pero fallar en Postgres (o quedar a medias).
- **Inconsistencia entre stores**:
  - Qdrant puede contener vectores de algunos batches.
  - Postgres puede contener solo parte de `entrevista_fragmentos`.
- **UX confusa**: el usuario ve la entrevista listada, pero con conteos distintos (p. ej. 64 fragmentos) y/o metadata incompleta.

## Causa raíz (probable)
1. Batch grande (default `batch_size=64` desde el endpoint) aumenta probabilidad de timeout en Qdrant.
2. Cuando ocurre el timeout:
   - El `upsert()` hace split y reintenta por mitades.
3. En el flujo previo, si Postgres queda con una sentencia fallida sin `ROLLBACK`, la conexión queda en estado **aborted**.
4. Luego, cualquier comando adicional en ese bloque devuelve el error genérico `current transaction is aborted ...`.

## Corrección aplicada (2026-01-10)
Se aplicaron tres cambios para **evitar 500 falsos** y **prevenir inconsistencias**:

### 1) Rollback defensivo en Postgres al fallar insert de fragmentos
Archivo: [app/postgres_block.py](../../app/postgres_block.py)

- En `insert_fragments()` se envolvió el `execute_values(...)` con `try/except`.
- Ante excepción:
  - Se ejecuta `pg.rollback()`.
  - Se vuelve a lanzar la excepción original.

**Efecto:** evita que la conexión vuelva al pool en estado “aborted”, y el log/HTTP reflejan el error raíz.

### 2) Orden de persistencia: Postgres primero, Qdrant después
Archivo: [app/ingestion.py](../../app/ingestion.py)

- Se cambió el orden por batch a:
  1) `insert_fragments()` (Postgres)
  2) `upsert()` (Qdrant)

**Efecto:** si Postgres falla, no se escriben vectores nuevos (reduce huérfanos en Qdrant). Si Qdrant falla, al menos el “dato maestro” queda en PG y se puede reintentar la indexación vectorial.

### 3) Default y sanitización de `batch_size` para evitar timeouts
Archivo: [backend/routers/ingest.py](../../backend/routers/ingest.py)

- Default de `batch_size` del endpoint bajado de **64 → 20**.
- Sanitización: `batch_size` clamped a `1..32`.

**Efecto:** reduce significativamente la probabilidad de `qdrant.upsert.split` por timeouts y evita que valores extremos (por formulario) degraden el sistema.

## Verificación recomendada
1) Reingestar el mismo DOCX con configuración por defecto del endpoint (sin forzar `batch_size=64`).
2) Confirmar en logs:
   - No aparece `qdrant.upsert.split`.
   - No aparece `api.upload_and_ingest.ingest_error`.
   - Se observan todos los `ingest.batch` hasta completar la cuenta esperada.
3) Validar en UI que el conteo de fragmentos sea consistente con lo detectado.

## Workarounds operativos
- Si se detecta una entrevista con conteo inconsistente (Qdrant vs PG), el enfoque correcto es:
  1) **Eliminar** los registros del archivo en PG y Qdrant (por `project_id` + `archivo`).
  2) Reingestar con batch pequeño.

## Notas adicionales
- El sistema ya tiene mitigaciones de pool (rollback before return) y rollback defensivo en `_mark_fragments_sync_status()`, pero faltaba esta protección específica en `insert_fragments()`.
- A futuro, si se requiere consistencia estricta multi-store, se recomienda un mecanismo de “job state” (PG) + reconciliación (reindex Qdrant) en segundo plano.
