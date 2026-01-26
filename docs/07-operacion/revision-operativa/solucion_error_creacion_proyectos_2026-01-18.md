# Solución: Error al Crear Proyectos (Falsos Positivos de Duplicados)

> **Fecha:** 18 de Enero de 2026  
> **Severidad:** Alta  
> **Estado:** ✅ Resuelto  
> **Componentes afectados:** Backend (`backend/app.py`, `app/project_state.py`), Frontend (`useProjects.ts`)

---

## 1. Descripción del Problema

### Síntomas Reportados
- Usuario crea un proyecto → ve mensaje de error
- Al intentar crear el mismo proyecto de nuevo → "Ya existe un proyecto..."
- Proyectos con nombres completamente nuevos también mostraban error 400
- La UI no se actualizaba después de crear proyectos

### Impacto
- Usuarios no podían crear proyectos de forma confiable
- Confusión: los proyectos SÍ se creaban pero el usuario no lo veía
- Múltiples intentos fallidos generaban frustración

---

## 2. Diagnóstico

### Hallazgos en la Base de Datos
```sql
-- Se encontraron 8 proyectos creados correctamente
SELECT id, name, created_at FROM proyectos 
WHERE org_id = '6fc75e26-c0f4-4559-a2ef-10e508467661';

-- Resultado: iquique, taliban, madrid, chicago, la-florida, jd-007aa, jd-007, default-...
```

**Conclusión:** Los proyectos SÍ se estaban creando en la BD, pero algo fallaba en el flujo de respuesta.

### Causas Raíz Identificadas

#### Causa 1: Fallo Silencioso en `add_project_member`
```python
# backend/app.py - Código ANTES (problemático)
try:
    entry = create_project(...)  # ✅ Esto funcionaba
    add_project_member(...)      # ❌ Si fallaba aquí, se perdía todo
except ValueError as exc:
    raise HTTPException(status_code=400, ...)
```

**Problema:** Si `add_project_member` fallaba (ej: constraint violation, timeout), se lanzaba una excepción que NO era `ValueError`, causando un error 500. El proyecto ya estaba creado pero el usuario veía error.

#### Causa 2: Sin Logging de Inicio de Operación
No había logs al **inicio** del proceso de creación, solo al final. Esto dificultaba el diagnóstico.

#### Causa 3: Frontend No Recargaba Lista en Caso de Error
```typescript
// useProjects.ts - Código ANTES
catch (error) {
    setState((prev) => ({ ...prev, error: ... }));
    throw error;
    // ❌ No recargaba la lista, el proyecto existía pero no se mostraba
}
```

---

## 3. Solución Implementada

### 3.1 Backend: Manejo Robusto de Errores

**Archivo:** `backend/app.py` (líneas ~1295-1360)

```python
@app.post("/api/projects")
async def api_create_project(
    payload: ProjectCreateRequest,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    # 1. Log al INICIO
    api_logger.info(
        "project.create.start",
        project_name=payload.name,
        user=user.user_id,
        org_id=user.organization_id,
    )
    try:
        entry = create_project(
            clients.postgres,
            payload.name,
            payload.description,
            org_id=user.organization_id,
            owner_id=user.user_id,
        )
        api_logger.info(
            "project.create.db_success",
            project_id=entry.get("id"),
            project_name=payload.name,
        )
        
        # 2. Manejo separado de add_project_member
        try:
            add_project_member(
                clients.postgres,
                entry.get("id"),
                user.user_id,
                "admin",
                added_by=user.user_id,
            )
        except Exception as member_exc:
            # Log pero NO fallar - el proyecto ya fue creado
            api_logger.warning(
                "project.create.member_add_warning",
                project_id=entry.get("id"),
                error=str(member_exc),
            )
            
    except ValueError as exc:
        api_logger.warning(
            "project.create.validation_error",
            project_name=payload.name,
            error=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # 3. Captura de errores inesperados
        api_logger.error(
            "project.create.unexpected_error",
            project_name=payload.name,
            error=str(exc),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Error interno: {exc}") from exc
        
    api_logger.info("project.created", project_id=entry.get("id"), ...)
    return entry
```

### 3.2 Frontend: Recarga Automática en Error de Duplicado

**Archivo:** `frontend/src/hooks/useProjects.ts` (líneas ~96-120)

```typescript
catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    logClient("projects.create.error", { name: trimmedName, message: errorMsg }, "error");
    
    // NUEVO: Si el error menciona "Ya existe", recargar lista
    // El proyecto pudo haberse creado pero la respuesta falló
    if (errorMsg.includes("Ya existe") || errorMsg.includes("already exists")) {
        logClient("projects.create.reloading_after_duplicate_error");
        await load();  // Recargar para mostrar el proyecto que sí existe
    }
    
    setState((prev) => ({ ...prev, error: errorMsg }));
    throw error;
}
```

---

## 4. Patrón de Diseño Aplicado

### "Operación Atómica con Degradación Graceful"

```
┌─────────────────────────────────────────────────────────────┐
│                    PATRÓN RECOMENDADO                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. LOG al inicio de la operación                           │
│     └── Permite rastrear requests que nunca terminan        │
│                                                             │
│  2. Operación PRINCIPAL en try/except                       │
│     └── create_project() - DEBE funcionar                   │
│                                                             │
│  3. Operaciones SECUNDARIAS en try/except INTERNO           │
│     └── add_project_member() - PUEDE fallar sin abortar     │
│     └── Log warning, NO exception                           │
│                                                             │
│  4. LOG al final (éxito)                                    │
│     └── Confirma que todo terminó                           │
│                                                             │
│  5. Frontend: RECARGAR si error de duplicado                │
│     └── El recurso pudo crearse aunque la respuesta falló   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Verificación

### Pruebas Exitosas
```
✅ Proyecto "Salomon" creado exitosamente
✅ Proyecto "JD 007" creado exitosamente
✅ UI se actualiza correctamente después de crear
✅ Logs muestran todo el flujo: start → db_success → created
```

### Comando de Verificación
```bash
# Verificar proyectos en BD
python -c "
from app.clients import build_service_clients
from app.settings import load_settings
clients = build_service_clients(load_settings())
cur = clients.postgres.cursor()
cur.execute('SELECT name, created_at FROM proyectos ORDER BY created_at DESC LIMIT 5')
for r in cur.fetchall(): print(f'{r[0]} - {r[1]}')
clients.close()
"
```

---

## 6. Lecciones Aprendidas

| # | Lección | Aplicación |
|---|---------|------------|
| 1 | **Log al inicio Y al final** | Permite detectar operaciones que "desaparecen" |
| 2 | **Operaciones secundarias no deben abortar la principal** | `add_project_member` falla → log warning, no exception |
| 3 | **Frontend debe ser resiliente a errores de red** | Si error de duplicado, recargar lista |
| 4 | **Los proyectos se crean aunque el usuario vea error** | Siempre verificar BD antes de asumir que falló |

---

## 7. Archivos Modificados

| Archivo | Cambio |
|---------|--------|
| `backend/app.py` | Logging mejorado + manejo de errores en `add_project_member` |
| `frontend/src/hooks/useProjects.ts` | Recarga automática si error de duplicado |
| `app/project_state.py` | (Previo) Verificación de duplicados scoped a org_id |

---

## 8. Referencias

- [Troubleshooting Database](../05-troubleshooting/connection_pool_issues.md)
- [CLAUDE.md](../../CLAUDE.md) - Guía de desarrollo
- [agents.md](../../agents.md) - Descripción de agentes del sistema

---

*Documentado: 18 de Enero de 2026*
