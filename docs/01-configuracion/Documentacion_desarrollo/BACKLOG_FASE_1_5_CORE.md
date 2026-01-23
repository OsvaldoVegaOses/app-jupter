# Backlog: Fase 1.5 Core — Identidad por ID end-to-end

> **Fecha creación:** 23 Enero 2026  
> **Epic:** Cerrar Fase 1.5 en el core para que `axial_ready` sea un gate real  
> **Objetivo:** Todo el pipeline (open coding → catálogo → axial → Neo4j) opera con `code_id` como identidad estable

---

## Reglas del backlog

- **Orden estricto:** no iniciar ticket N+1 hasta que N esté `DONE`
- **Cada ticket:** implementación + test + validación manual
- **Definition of Done (DoD):** todos los items del checklist marcados + test pasa + sin regresiones

---

## TICKET-001: Implementar `resolve_canonical_code_id()`

**Prioridad:** P0 (crítico, bloquea todo lo demás)  
**Estimación:** 2-4 horas  
**Archivo principal:** `app/postgres_block.py`

### Descripción

Crear función que resuelve la cadena canónica por `code_id` (no por texto), siguiendo `canonical_code_id` hasta llegar al canónico final.

### Checklist de implementación

- [x] Crear función `resolve_canonical_code_id(pg, project_id, code_id, max_hops=10) -> Optional[int]`
- [x] Implementar lógica recursiva/iterativa similar a `resolve_canonical_codigo()` pero por ID
- [x] Manejar casos:
  - [x] `code_id` no existe → retorna `None`
  - [x] `canonical_code_id IS NULL` (es canónico) → retorna el mismo `code_id`
  - [x] `canonical_code_id = code_id` (self-canonical) → retorna el mismo `code_id`
  - [x] Cadena de merges → sigue hasta el final
  - [x] Ciclo detectado → retorna `None` + log warning
- [x] Agregar docstring con ejemplo de uso
- [x] Exportar en `__all__` si existe
- [x] **BONUS:** Crear `get_code_id_for_codigo()` helper para transición texto→ID

### Checklist de test

- [x] Crear `tests/test_resolve_canonical_code_id.py`
- [x] Test: código canónico (sin puntero) → retorna sí mismo
- [x] Test: código merged → retorna canónico final
- [x] Test: cadena de 3 niveles → retorna canónico final
- [x] Test: `code_id` inexistente → retorna `None`
- [x] Test: ciclo artificial → retorna `None` sin loop infinito

### Validación manual

- [x] Ejecutar contra proyecto real: `python -c "from app.postgres_block import resolve_canonical_code_id; ..."`
- [x] Verificar que retorna IDs correctos para códigos conocidos

### Definition of Done

- [x] Función implementada y documentada
- [x] Tests pasan: `pytest tests/test_resolve_canonical_code_id.py -v` (11/11 passed)
- [x] No hay regresiones en tests relacionados
- [ ] Código commiteado con mensaje: `feat(core): add resolve_canonical_code_id for ID-based resolution`

---

## TICKET-002: Propagar `code_id` en `coding.py`

**Prioridad:** P0  
**Estimación:** 3-5 horas  
**Dependencia:** TICKET-001 completado  
**Archivos:** `app/coding.py`, `app/postgres_block.py`, `backend/routers/coding.py`

### Descripción

Modificar el flujo de codificación abierta para que:
1. Al asignar código, se obtenga/cree `code_id` y se incluya en la respuesta
2. Queries de códigos devuelvan `(code_id, codigo)` en payloads

### Checklist de implementación

- [ ] En `ensure_code_catalog_entry()`: retornar `code_id` del registro creado/existente
- [x] Crear helper `get_code_id_for_codigo(pg, project_id, codigo) -> Optional[int]` *(completado en TICKET-001)*
- [ ] En `assign_open_code()` (o equivalente):
  - [ ] Después de insertar, obtener `code_id` del catálogo
  - [ ] Incluir `code_id` en el dict de retorno
- [ ] En funciones de query (`get_codes_for_project`, `get_codes_for_fragment`, etc.):
  - [ ] JOIN con `catalogo_codigos` para obtener `code_id`
  - [ ] Incluir `code_id` en cada item del resultado
- [ ] Actualizar tipos/schemas en `backend/routers/coding.py` si hay Pydantic models

### Checklist de test

- [ ] Test: asignar código nuevo → respuesta incluye `code_id`
- [ ] Test: asignar código existente → respuesta incluye el mismo `code_id`
- [ ] Test: listar códigos de proyecto → cada item tiene `code_id`
- [ ] Test: listar códigos de fragmento → cada item tiene `code_id`

### Validación manual

- [ ] Desde UI: asignar código → inspeccionar Network → verificar `code_id` en response
- [ ] `GET /api/coding/codes?project=jd-007` → cada código tiene `code_id`

### Definition of Done

- [ ] Todas las funciones de asignación/query devuelven `code_id`
- [ ] Tests pasan
- [ ] API backward-compatible (campo `codigo` sigue existiendo)
- [ ] Commit: `feat(coding): propagate code_id in assignment and queries`

---

## TICKET-003: Axialidad por ID + sync Neo4j

**Prioridad:** P0  
**Estimación:** 4-6 horas  
**Dependencia:** TICKET-002 completado  
**Archivos:** `app/axial.py`, `app/neo4j_block.py`, `app/postgres_block.py`

### Descripción

Modificar `assign_axial_relation()` y la sincronización a Neo4j para usar `code_id` como identidad estable.

### Checklist de implementación — axial.py

- [ ] Importar `resolve_canonical_code_id` y `get_code_id_for_codigo`
- [ ] En `assign_axial_relation()`:
  - [ ] Si se recibe `codigo` (texto): obtener `code_id` primero
  - [ ] Resolver canónico por ID: `canonical_code_id = resolve_canonical_code_id(...)`
  - [ ] Usar `code_id` canónico para persistencia
  - [ ] Mantener `codigo` como label para logging/memo
- [ ] Actualizar `upsert_axial_relationships()` para incluir `code_id` en la tabla
- [ ] Verificar que evidencia se asocia al `code_id` canónico

### Checklist de implementación — neo4j_block.py

- [ ] En `merge_category_code_relationship()`:
  - [ ] Aceptar parámetro `code_id: Optional[int]`
  - [ ] MERGE de nodo `:Codigo` incluye propiedad `code_id`
  - [ ] Si `code_id` existe, usarlo como parte del match (más estable que `nombre`)
- [ ] Crear/actualizar `sync_code_to_neo4j(neo4j, db, project_id, code_id, codigo, ...)`:
  - [ ] Nodo con `{code_id: $code_id, nombre: $codigo, project_id: $project_id}`

### Checklist de migración (opcional pero recomendado)

- [ ] Script para backfill `code_id` en nodos Neo4j existentes:
  ```cypher
  MATCH (c:Codigo {project_id: $project})
  WHERE c.code_id IS NULL
  SET c.code_id = $code_id
  ```

### Checklist de test

- [ ] Test: crear relación axial → nodo Neo4j tiene `code_id`
- [ ] Test: código merged → relación apunta al canónico (por `code_id`)
- [ ] Test: query Neo4j por `code_id` → encuentra el nodo correcto

### Validación manual

- [ ] Crear relación axial desde UI
- [ ] Query Neo4j: `MATCH (c:Codigo {project_id: 'jd-007'}) RETURN c.nombre, c.code_id LIMIT 10`
- [ ] Verificar que `code_id` está presente

### Definition of Done

- [ ] Relaciones axiales persistidas con `code_id`
- [ ] Nodos Neo4j tienen propiedad `code_id`
- [ ] Tests pasan
- [ ] Commit: `feat(axial): use code_id for stable identity in axial relations and Neo4j sync`

---

## TICKET-004: Gate runtime — bloqueo 409 si `axial_ready=false`

**Prioridad:** P0  
**Estimación:** 2-3 horas  
**Dependencia:** TICKET-003 completado  
**Archivos:** `backend/routers/axial.py`, `backend/routers/coding.py` (si aplica)

### Descripción

Implementar gate que rechaza operaciones axiales cuando la infraestructura ontológica no está lista.

### Checklist de implementación

- [ ] Crear helper `check_axial_ready(pg, project_id) -> Tuple[bool, List[str]]`:
  - [ ] Ejecuta la misma lógica que `/api/admin/code-id/status`
  - [ ] Retorna `(ready: bool, blocking_reasons: List[str])`
- [ ] En endpoints de axialidad (`POST /api/axial/*`):
  - [ ] Llamar `check_axial_ready()` antes de procesar
  - [ ] Si `ready=False`: retornar `HTTPException(status_code=409, detail={...})`
  - [ ] Detail incluye: `{"error": "axial_not_ready", "blocking_reasons": [...], "message": "..."}`
- [ ] Logging: `axial.blocked` con `project_id`, `blocking_reasons`, `endpoint`
- [ ] Opcional: agregar header `X-Axial-Ready: false` en respuesta

### Checklist de test

- [ ] Test: proyecto con `axial_ready=true` → operación procede (200/201)
- [ ] Test: proyecto con `missing_code_id > 0` → 409 con `blocking_reasons`
- [ ] Test: proyecto con `cycles_non_trivial > 0` → 409
- [ ] Test: response body incluye `blocking_reasons` array

### Validación manual

- [ ] Crear proyecto de prueba con inconsistencia intencional
- [ ] Intentar crear relación axial → verificar 409
- [ ] Reparar inconsistencia → verificar que ahora permite (200)

### Definition of Done

- [ ] Gate implementado en todos los endpoints axiales
- [ ] Response 409 incluye información útil para debugging
- [ ] Tests pasan
- [ ] Documentar en `docs/05-troubleshooting/` el error 409 axial
- [ ] Commit: `feat(axial): add runtime gate blocking axial ops when axial_ready=false`

---

## Resumen de dependencias

```
TICKET-001 ──┐
             │
             ▼
         TICKET-002 ──┐
                      │
                      ▼
                  TICKET-003 ──┐
                               │
                               ▼
                           TICKET-004
```

---

## Tracking de progreso

| Ticket | Estado | Inicio | Fin | Notas |
|--------|--------|--------|-----|-------|
| TICKET-001 | ✅ DONE | 2026-01-23 | 2026-01-23 | `resolve_canonical_code_id()` + `get_code_id_for_codigo()` + 11 tests |
| TICKET-002 | ⬜ NOT STARTED | — | — | Depende de 001 |
| TICKET-003 | ⬜ NOT STARTED | — | — | Depende de 002 |
| TICKET-004 | ⬜ NOT STARTED | — | — | Depende de 003 |

**Leyenda:**
- ⬜ NOT STARTED
- 🔄 IN PROGRESS
- ✅ DONE
- ❌ BLOCKED

---

## Criterio de cierre del Epic

El Epic "Fase 1.5 Core" se considera **DONE** cuando:

1. Los 4 tickets están en estado ✅ DONE
2. Pipeline completo funciona:
   - Asignar código → tiene `code_id`
   - Crear relación axial → usa `code_id` canónico
   - Sync Neo4j → nodos tienen `code_id`
   - `axial_ready=false` → bloquea operaciones axiales
3. No hay regresiones en UI ni API existente
4. Documentación actualizada (este backlog + troubleshooting)

---

*Backlog creado: 23 Enero 2026*
