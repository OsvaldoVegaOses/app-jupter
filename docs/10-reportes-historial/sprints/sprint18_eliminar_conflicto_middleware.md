# Sprint 18: Eliminar Conflicto Arquitectónico Middleware/Backend

**Fecha inicio:** 2025-12-27  
**Fecha fin:** 2025-12-27  
**Duración real:** ~30min  
**Estado:** ✅ COMPLETADO  
**Prioridad:** 🔴 CRÍTICA (Bloqueante)

---

## Problema Identificado

El archivo `frontend/vite.config.ts` contiene un middleware (`apiPlugin`) que intercepta rutas `/api/*` **ANTES** de que lleguen al proxy del backend:

```
Request → Vite Middleware (apiPlugin) → runPythonJSON(main.py) → SIN AUTH
                    ↓ (si no matchea)
         → Proxy → Backend FastAPI → CON AUTH
```

### Consecuencias

| Brecha | Impacto |
|--------|---------|
| **B1** | Proyectos creados sin `org_id` (no son de nadie) |
| **B2** | Ingesta acepta cualquier `project_id` sin validar existencia |
| **B3** | Multi-tenant roto: datos huérfanos en BD |

---

## Rutas Conflictivas Identificadas

| Ruta en Middleware | Línea | Debería ir a Backend |
|--------------------|-------|---------------------|
| `POST /api/coding/assign` | 357-404 | ✅ Ya existe en backend |
| `POST /api/coding/suggest` | 406-460 | ✅ Ya existe en backend |
| `GET /api/coding/stats` | 462-484 | ✅ Ya existe en backend |
| `GET /api/fragments/sample` | 487-513 | ✅ Ya existe en backend |
| `GET /api/interviews` | 516-543 | ✅ Ya existe en backend |
| `GET /api/coding/codes` | 546-580 | ✅ Ya existe en backend |
| `GET /api/status` | 334-351 | ⚠️ Verificar backend |

---

## Solución: Eliminar apiPlugin

### Opción A: Eliminar Completamente (RECOMENDADA)
- Remover líneas 318-733 del `apiPlugin`
- El proxy en líneas 743-763 ya redirige todo `/api/*` al backend
- **Riesgo:** Bajo (backend ya tiene todos los endpoints)

### Opción B: Bypass Selectivo
- Mantener solo rutas que NO existen en backend
- Modificar para que `/api/projects`, `/api/coding/*` vayan directo al proxy

---

## Tareas

| ID | Tarea | Archivo | Estado |
|----|-------|---------|--------|
| T1 | Remover `apiPlugin` de vite.config.ts | `frontend/vite.config.ts` | ⏳ |
| T2 | Validar proyecto en `ingest_documents()` | `app/ingestion.py` | ⏳ |
| T3 | Verificar que `/api/status` existe en backend | `backend/app.py` | ⏳ |
| T4 | Test e2e: crear proyecto → ingesta → análisis | Manual | ⏳ |

---

## Criterios de Aceptación

- [ ] Todas las rutas `/api/*` van directamente al backend
- [ ] Proyectos creados tienen `org_id` correcto
- [ ] Ingesta rechaza proyectos inexistentes
- [ ] Flujo completo funciona post-login

---

## Archivos a Modificar

| Archivo | Cambio |
|---------|--------|
| `frontend/vite.config.ts` | Eliminar apiPlugin (líneas 318-733) |
| `app/ingestion.py` | Agregar validación de proyecto |
| `backend/app.py` | Verificar /api/status endpoint |
