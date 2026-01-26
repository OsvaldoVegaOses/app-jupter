# Especificación Técnica — Fusión de Duplicados (Code Merge)

**Fuente conceptual:** [docs/04-arquitectura/Fusión_duplicados](docs/04-arquitectura/Fusión_duplicados)

## 0) Objetivo
Estandarizar e implementar la fusión de códigos duplicados como **operación de gobernanza del codebook** (no borrado), con:
- **Persistencia relacional** (PostgreSQL) consistente.
- **Trazabilidad/auditoría** reproducible (quién, cuándo, por qué, qué cambió).
- **Idempotencia** (reintentos seguros desde frontend).
- **Reglas de integridad** que eviten falsos positivos y efectos colaterales.

## 1) Alcance
Esta especificación cubre:
- Endpoints para **fusionar** candidatos (manual y masivo).
- Esquemas JSON de request/response.
- Mapeo del contexto lógico a **capa de datos** (PostgreSQL) y su impacto en Neo4j.

No cubre:
- Algoritmo de detección de duplicados (post-hoc). Ese proceso solo produce *pares propuestos*.

## 2) Glosario
- **Código canónico (target)**: etiqueta final que representa el concepto (p.ej. `escasez_agua`).
- **Variantes (source)**: etiquetas duplicadas o casi-duplicadas que deben consolidarse (p.ej. `escasez de agua`, `falta agua`).
- **Cita/evidencia**: vínculo a `fragmento_id` (unidad empírica).
- **Soft merge**: no se elimina registro; se marca `estado='fusionado'` y referencia a destino.

## 3) Mapeo a capa de datos (PostgreSQL)
### 3.1 Modelo actual (implementación vigente)
El sistema persiste candidatos en la tabla `codigos_candidatos` (creada si no existe por `ensure_candidate_codes_table()` en [app/postgres_block.py](app/postgres_block.py#L3737)).

Campos relevantes (actuales):
- `id SERIAL PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `codigo TEXT NOT NULL`  ← **label operativo** del candidato
- `fragmento_id TEXT`     ← evidencia empírica (puede ser NULL en algunos flujos)
- `estado TEXT NOT NULL DEFAULT 'pendiente'` con valores usados: `pendiente`, `validado`, `rechazado`, `fusionado`
- `fusionado_a TEXT`      ← **destino de fusión** (hoy: nombre/código canónico como string)
- `validado_por TEXT`, `validado_en TIMESTAMPTZ`
- `memo TEXT`
- `UNIQUE(project_id, codigo, fragmento_id)`

### 3.2 Semántica de fusión en datos (best practice)
Para respetar el documento base:
1) **No borrar** filas fuente.
2) Mantener trazabilidad y permitir auditoría forense.

Semántica operacional recomendada:
- Si la fila fuente representa evidencia única que aún no existe bajo el target, se **reasigna** `codigo := target_codigo` y se setea `fusionado_a := target_codigo` (esto consolida evidencia y densifica topología).
- Si la misma evidencia (mismo `fragmento_id`) ya existe bajo el target, la fila fuente se marca `estado='fusionado'`, `fusionado_a := target_codigo` (deduplicación sin pérdida).

Esto es consistente con la intención metodológica (densidad teórica) y con la restricción `UNIQUE(project_id, codigo, fragmento_id)`.

### 3.3 Brecha a concretar: “fusionado_a = ID” vs “fusionado_a = nombre”
El documento conceptual menciona “ID del destino”. La implementación actual usa `fusionado_a TEXT` (nombre).

Opciones (decisión de arquitectura):
- **Opción A (mínima, compatible):** mantener `fusionado_a` como nombre canónico (string). Recomendado si el “código canónico” se identifica por su texto.
- **Opción B (más robusta):** agregar `fusionado_a_id` (FK) y mantener `fusionado_a` como snapshot textual. Recomendado si se quiere integridad referencial dura.

Migración sugerida (si Opción B):
- `ALTER TABLE codigos_candidatos ADD COLUMN fusionado_a_id INT NULL;`
- (Opcional) tabla `codebook_codes(id, project_id, nombre, created_at, updated_at, UNIQUE(project_id, nombre))` para representar entidades canónicas reales.

## 4) API: Endpoints

### 4.1 Reglas comunes (para todos los endpoints)
- **Auth:** `X-API-Key` (o mecanismo actual de `require_auth`).
- **Idempotencia:** aceptar `idempotency_key` (string) para que reintentos no dupliquen trabajo.
- **Auditoría:** aceptar `memo` (justificación) y persistirla (en `codigo_versiones` idealmente).
- **Validaciones mínimas:**
  - `project` requerido.
  - `target_codigo` no vacío.
  - Prohibir `source == target` (no-op).
  - Rechazar operaciones sobre proyectos inexistentes.

### 4.2 Endpoint: Fusión manual (por IDs)
**Método/Ruta:** `POST /api/codes/candidates/merge`

**Uso:** UI (selección manual) cuando el investigador decide explícitamente consolidar un conjunto de candidatos.

#### Request JSON Schema — `MergeCandidatesRequest`
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "MergeCandidatesRequest",
  "type": "object",
  "additionalProperties": false,
  "required": ["project", "source_ids", "target_codigo"],
  "properties": {
    "project": { "type": "string", "minLength": 1 },
    "source_ids": {
      "type": "array",
      "minItems": 1,
      "items": { "type": "integer", "minimum": 1 }
    },
    "target_codigo": { "type": "string", "minLength": 1 },
    "memo": { "type": ["string", "null"], "maxLength": 2000 },
    "dry_run": { "type": "boolean", "default": false },
    "idempotency_key": { "type": ["string", "null"], "maxLength": 128 }
  }
}
```

#### Response (contrato recomendado)
```json
{
  "success": true,
  "merged_count": 12,
  "target_codigo": "escasez_agua",
  "dry_run": false,
  "warnings": []
}
```

#### Errores
- `400`: request inválida (source_ids vacío, target vacío)
- `404`: candidato(s) no encontrado(s) o no procesable(s)
- `409`: conflicto de negocio (p.ej., fusión prohibida por regla de pre-validación)

### 4.3 Endpoint: Fusión masiva (por pares source/target)
**Método/Ruta:** `POST /api/codes/candidates/auto-merge`

**Uso:** ejecución batch (post-hoc) a partir de pares propuestos por detección.

#### Request JSON Schema — `AutoMergeRequest`
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "AutoMergeRequest",
  "type": "object",
  "additionalProperties": false,
  "required": ["project", "pairs"],
  "properties": {
    "project": { "type": "string", "minLength": 1 },
    "pairs": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["source_codigo", "target_codigo"],
        "properties": {
          "source_codigo": { "type": "string", "minLength": 1 },
          "target_codigo": { "type": "string", "minLength": 1 }
        }
      }
    },
    "memo": { "type": ["string", "null"], "maxLength": 2000 },
    "dry_run": { "type": "boolean", "default": false },
    "idempotency_key": { "type": ["string", "null"], "maxLength": 128 }
  }
}
```

#### Response (contrato recomendado)
```json
{
  "success": true,
  "total_merged": 38,
  "dry_run": false,
  "details": [
    { "source": "escasez de agua", "target": "escasez_agua", "merged_count": 12 },
    { "source": "falta agua", "target": "escasez_agua", "merged_count": 26 }
  ],
  "warnings": []
}
```

#### Regla anti-falsos-positivos (best practice)
Este endpoint **no debe inventar** pares a partir de similitud; debe ejecutar pares ya revisados o generados con guardrails.
Si se agrega un modo “proponer y ejecutar”, debe existir:
- `mode: "preview" | "execute"`
- `threshold`, `token_overlap_min`
- límite de pares (para UX y seguridad)

## 5) Alineación de rutas (best practice)
Existe documentación histórica con `/api/coding/candidates/merge` (ver [docs/01-arquitectura/paneles_frontend.md](docs/01-arquitectura/paneles_frontend.md#L552-L585)) y el backend actual expone `/api/codes/candidates/merge`.

Decisión recomendada:
- **Canon:** `/api/codes/*`.
- Mantener temporalmente alias `/api/coding/*` (si existe en frontend legacy) con deprecación documentada.

## 6) Auditoría y trazabilidad (mínimo viable)
Recomendación:
- Hacer `memo` obligatorio para merges manuales (UI), opcional para auto-merge (batch) pero recomendado.
- Persistir:
  - actor (`merged_by` / `user_id`)
  - timestamp (`updated_at` y/o `validado_en`)
  - destino (`fusionado_a`)
  - (ideal) `merge_run_id` y `idempotency_key`

## 7) Checklist de aceptación
- Fusión no borra registros.
- El target conserva/absorbe evidencia sin duplicar `fragmento_id`.
- Los sources quedan trazables (`estado='fusionado'`, `fusionado_a` seteado).
- Endpoints validan inputs y devuelven conteos consistentes.
- Documentación usa una sola familia de rutas (`/api/codes/...`).

## Dictamen formal (fase implementada)

Para un dictamen defendible (con evidencia y divergencias no bloqueantes), ver:

- [docs/06-metodologia/dictamen_fase1_consolidacion_y_limpieza_el_puente.md](docs/06-metodologia/dictamen_fase1_consolidacion_y_limpieza_el_puente.md)
- [docs/06-metodologia/codificacion_abierta/Transición_A_Cod_Axial/dictamen_fase1_consolidacion_y_limpieza_el_puente.md](docs/06-metodologia/codificacion_abierta/Transición_A_Cod_Axial/dictamen_fase1_consolidacion_y_limpieza_el_puente.md)
