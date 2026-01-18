# AI Development Agent Guidelines

> **IMPORTANT**: This file must be read BEFORE making any changes to the codebase.
> AI agents should treat these as hard constraints.

---

## 🚨 Critical Rules (Non-Negotiable)

### 1. DO NOT Break Existing Functionality
- **Never remove or modify** existing API endpoints without explicit user approval
- **Never change function signatures** of exported functions in `app/*.py` or `frontend/src/services/*.ts`
- **Always preserve backward compatibility** with existing data structures

### 2. Port Configuration (CURRENT)
```
Backend:  http://localhost:8000  (FastAPI + Uvicorn)
Frontend: http://localhost:5174  (Vite dev)
```
- The port configuration is set in `frontend/.env` as `VITE_API_BASE=http://127.0.0.1:8000`
- Backend runs via `scripts/start_all.bat`

### 3. Authentication Pattern
- All `/api/*` endpoints require `X-API-Key` header
- Exception: `/healthz` is unauthenticated (for health checks)
- API key comes from `VITE_NEO4J_API_KEY` environment variable

---

## 📋 Before Making Changes

### Step 1: Read Core Documentation
1. Read `agents.md` to understand module responsibilities
2. Check `docs/01-configuracion/run_local.md` for setup
3. Review `docs/05-calidad/plan_mejora_ux_ui.md` for UX patterns

### Step 2: Verify Impact
Before editing any file, ask:
- [ ] Does this change affect any API endpoint?
- [ ] Does this change affect any function used by other modules?
- [ ] Does this change require database migrations?
- [ ] Does this change require environment variable updates?

### Step 3: Follow the Checklist
For **Backend Changes** (`backend/app.py`):
- [ ] Check if endpoint exists using `grep_search`
- [ ] Verify imports from `app/*.py` are correct
- [ ] Test with `curl` or browser before completing

For **Frontend Changes**:
- [ ] Verify API functions in `frontend/src/services/api.ts`
- [ ] Add error handling with `try/catch`
- [ ] Use existing components from `frontend/src/components/`

---

## 🔒 Protected Files (Ask Before Modifying)

| File | Reason |
|------|--------|
| `app/settings.py` | Core configuration - changes break all modules |
| `app/clients.py` | Service connections - changes break everything |
| `backend/app.py` (imports) | Module loading - wrong imports = 500 errors |
| `frontend/.env` | Port configuration - changes break frontend |

---

## ✅ Preferred Patterns

### Adding New API Endpoints
```python
# 1. Add endpoint AFTER existing ones (don't insert in middle)
# 2. Use existing Depends() patterns:
@app.get("/api/new-endpoint")
async def new_endpoint(
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),  # For protected endpoints
) -> Dict[str, Any]:
    ...
```

### Adding New Frontend Components
```typescript
// 1. Create in frontend/src/components/
// 2. Export from the file
// 3. Import in App.tsx
// 4. Add CSS in App.css (at the end of file)
```

### Error Handling
```typescript
// Frontend: Use the global error system
try {
  const data = await apiFetch('/api/endpoint');
} catch (err) {
  // ApiErrorToast handles this automatically
}
```

---

## 🧪 Testing Requirements

Before completing any task:
1. **Backend**: Verify endpoint with `curl http://localhost:8000/healthz`
2. **Frontend**: Check browser console for errors
3. **Integration**: Confirm UI displays expected data

---

## 📁 Module Responsibilities (Quick Reference)

| Module | Owner | Purpose |
|--------|-------|---------|
| `app/settings.py` | Configuration | Load `.env` into dataclasses |
| `app/clients.py` | Connections | Build service clients |
| `app/postgres_block.py` | Storage | PostgreSQL operations |
| `app/qdrant_block.py` | Storage | Vector search |
| `app/neo4j_block.py` | Storage | Graph operations |
| `backend/app.py` | API | HTTP endpoints |
| `frontend/src/services/api.ts` | API Client | Fetch wrapper |

---

## 🚫 Common Mistakes to Avoid

1. **Wrong function name**: `build_clients` vs `build_service_clients` - use the latter
2. **Wrong settings access**: Use `settings.postgres.host` not `settings.pghost`
3. **Wrong port**: Prefer 8000 (canonical). Some legacy docs used 5000/8080.
4. **Missing imports**: Check line ~100-150 of `backend/app.py` for import patterns
5. **Forgetting API key**: All `/api/*` calls need `X-API-Key` header

---

---

## 🔧 Troubleshooting (CRITICAL - READ FIRST)

### When System Fails:
1. **FIRST**: Check `docs/05-troubleshooting/connection_pool_issues.md`
2. **Check logs**: `logs/app.jsonl` for errors
3. **Pool status**: Look for `pool.nearly_exhausted` or `pool.getconn.FAILED`

### Archivos Huérfanos (Orphaned Files)
**Síntoma:** Error "Archivo no encontrado" en Etapa 3 (Codificación)
```json
{"detail": "Archivo no encontrado: Entrevista_Encargada_Emergencia_La_Florida.docx"}
```

**Causa:** Archivos registrados en PostgreSQL pero sin correspondencia en Blob Storage/local
- ❌ PostgreSQL tiene `entrevista_fragmentos` para el archivo
- ❌ Azure Blob Storage no tiene el archivo
- ❌ Almacenamiento local no tiene el archivo

**Diagnóstico:**
```powershell
python scripts/clean_orphan_files.py --project [project_id] --diagnose
```

**Solución:**
```powershell
# Limpiar todos los huérfanos
python scripts/clean_orphan_files.py --project [project_id] --clean

# O limpiar un archivo específico
python scripts/clean_orphan_files.py --project [project_id] --clean --file "archivo.docx"
```

**Qué elimina:**
- PostgreSQL: `entrevista_fragmentos` registros
- PostgreSQL: `analisis_codigos_abiertos` códigos asociados
- Neo4j: Nodos `:Entrevista` y `:Fragmento` huérfanos

**Ejemplo histórico:** 16 archivos huérfanos identificados en `jose-domingo-vg` el 2026-01-16, eliminados exitosamente.

### Common Issues:
| Síntoma | Probable Causa | Solución |
|---------|----------------|----------|
| Backend no responde | Pool exhausted | Reiniciar backend |
| "Credenciales inválidas" | Tabla users perdida | Ejecutar `create_admin.py` |
| Proyecto no se elimina | Falta DELETE en proyectos | Ya corregido en app.py |
| "Archivo no encontrado" en Etapa 3 | Archivos huérfanos en PostgreSQL | Ejecutar `clean_orphan_files.py --clean` |

### Diagnóstico de Pool:
```powershell
# Verificar leaks de conexiones
$get = (Select-String -Path logs\app.jsonl -Pattern "pool.getconn.success").Count
$put = (Select-String -Path logs\app.jsonl -Pattern "pool.putconn.success").Count
Write-Host "getconn: $get, putconn: $put, LEAK: $($get - $put)"
```

---

*Last updated: January 2026*
