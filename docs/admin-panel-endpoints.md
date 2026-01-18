# Admin Panel Endpoints Documentación

**Fecha:** Enero 16, 2026  
**Estado:** Implementado y Listo para Producción

---

## Overview

Se han implementado 6 nuevos grupos de endpoints HTTP en `backend/app.py` para soportar las operaciones de administración en la nueva consola AdminPanel. Todos los endpoints requieren autenticación vía JWT o API Key y están protegidos por roles.

---

## 1. User Management Endpoints

### GET /api/admin/users
**Rol requerido:** `admin`

Lista todos los usuarios de la organización del administrador autenticado.

**Response (200 OK):**
```json
{
  "users": [
    {
      "id": "user-123",
      "email": "admin@example.com",
      "full_name": "Admin User",
      "role": "admin",
      "organization_id": "org-001",
      "is_active": true,
      "created_at": "2026-01-10T10:00:00Z",
      "last_login": "2026-01-16T08:30:00Z"
    }
  ],
  "total": 15
}
```

---

### GET /api/admin/stats
**Rol requerido:** `admin`

Obtiene estadísticas generales de la organización.

**Response (200 OK):**
```json
{
  "organization_id": "org-001",
  "total_users": 15,
  "users_by_role": {
    "admin": 2,
    "analyst": 8,
    "viewer": 5
  },
  "total_fragments": 12450,
  "active_sessions": 7
}
```

---

### PATCH /api/admin/users/{user_id}
**Rol requerido:** `admin`

Actualiza el rol o estado activo de un usuario.

**Request Body:**
```json
{
  "role": "analyst",
  "is_active": true
}
```

**Response (200 OK):**
```json
{
  "user_id": "user-123",
  "status": "updated"
}
```

---

### DELETE /api/admin/users/{user_id}
**Rol requerido:** `admin`

Marca un usuario como inactivo (soft-delete). No permite eliminar al admin autenticado.

**Response (200 OK):**
```json
{
  "user_id": "user-123",
  "status": "deleted"
}
```

---

## 2. Data Cleanup Endpoints (⚠️ Destructive)

### POST /api/admin/cleanup/all-data
**Rol requerido:** `admin`  
**Query Parameters:**
- `project` (default: "default"): ID del proyecto

**Request Body (REQUERIDO):**
```json
{
  "confirm": true,
  "reason": "Manual cleanup due to data migration"
}
```

> ⚠️ **ADVERTENCIA:** Elimina TODOS los datos de un proyecto de PostgreSQL, Qdrant y Neo4j. Requiere `confirm: true`.

**Response (200 OK):**
```json
{
  "status": "completed",
  "project": "default",
  "message": "Limpieza completada: 5432 registros PostgreSQL, 1 Qdrant, 234 Neo4j",
  "counts": {
    "postgres": 5432,
    "qdrant": 1,
    "neo4j": 234
  }
}
```

---

### POST /api/admin/cleanup/projects
**Rol requerido:** `admin`

**Request Body (REQUERIDO):**
```json
{
  "confirm": true,
  "reason": "Cleanup after project deletion workflow"
}
```

> ⚠️ **ADVERTENCIA:** Elimina datos de proyectos marcados como `is_deleted = true`.

**Response (200 OK):**
```json
{
  "status": "completed",
  "message": "Limpieza completada: 3 proyectos eliminados",
  "cleaned_projects": [
    {
      "project_id": "old-proj-001",
      "rows_deleted": 1234
    }
  ]
}
```

---

### POST /api/admin/cleanup/duplicate-codes
**Rol requerido:** `admin`, `analyst`  
**Query Parameters:**
- `project` (default: "default"): ID del proyecto
- `threshold` (default: 0.85): Umbral de similitud (0-1)

> 📋 **NON-DESTRUCTIVE:** Solo detecta, no elimina.

**Response (200 OK):**
```json
{
  "status": "completed",
  "project": "default",
  "total_codes": 456,
  "groups_count": 12,
  "threshold": 0.85,
  "duplicate_groups": [
    ["código 1", "código 1a", "codigo 1"],
    ["test", "prueba"]
  ]
}
```

---

## 3. Integrity Analysis Endpoints (Non-Destructive)

### GET /api/admin/analysis/orphan-files
**Rol requerido:** `admin`, `analyst`  
**Query Parameters:**
- `project` (default: "default"): ID del proyecto

Detecta archivos en PostgreSQL que no existen en el filesystem o Blob Storage.

**Response (200 OK):**
```json
{
  "status": "completed",
  "project": "default",
  "total_files": 45,
  "orphans_count": 3,
  "orphans": [
    {
      "filename": "deleted_interview_001.docx",
      "exists_in_db": true,
      "exists_in_fs": false
    }
  ]
}
```

---

### GET /api/admin/analysis/integrity
**Rol requerido:** `admin`, `analyst`  
**Query Parameters:**
- `project` (default: "default"): ID del proyecto

Chequeo de integridad general: fragmentos sin códigos, códigos huérfanos, etc.

**Response (200 OK):**
```json
{
  "status": "completed",
  "project": "default",
  "checks": {
    "fragments_without_codes": 23,
    "total_fragments": 12450,
    "unique_codes": 156,
    "total_code_assignments": 5432
  }
}
```

---

## 4. Error Handling

Todos los endpoints siguen el estándar FastAPI HTTPException:

**400 Bad Request:**
```json
{
  "detail": "Project not found or access denied"
}
```

**401 Unauthorized:**
```json
{
  "detail": "Not authenticated"
}
```

**403 Forbidden:**
```json
{
  "detail": "Insufficient permissions (requires admin role)"
}
```

**500 Internal Server Error:**
```json
{
  "detail": "Error limpiando datos: connection timeout"
}
```

---

## 5. Frontend Integration

### Components Actualizados

#### AdminPanel.tsx
- **CleanupSection**: Collapsible panel para operaciones destructivas
  - Botón "Eliminar Todo" (limpia todos los datos)
  - Botón "Limpiar Proyectos Deleted" (limpia proyectos marcados)
  - Requiere confirmación mediante `confirm()` dialog
  - Input para seleccionar proyecto

- **AnalysisSection**: Collapsible panel para análisis no-destructivos
  - Botón "Detectar Duplicados" (similarity detection)
  - Botón "Encontrar Huérfanos" (orphan file detection)
  - Botón "Integridad" (check overall integrity)
  - Control de umbral para duplicados (threshold slider)
  - Result cards con detalles colapsibles

#### AdminPanel.css
- Nuevos estilos para `.admin-panel__cleanup` (gradiente warning)
- Nuevos estilos para `.admin-panel__analysis` (gradiente teal/info)
- `.cleanup-button--danger` (rojo, gradient)
- `.cleanup-button--warning` (naranja, gradient)
- `.analysis-button` (teal, gradient)
- `.result-card` con soporte para details/summary
- Animaciones hover y transitions

---

## 6. Security Considerations

✅ **Protecciones Implementadas:**
1. **Role-based Access Control (RBAC):**
   - Solo `admin` puede ejecutar cleanup destructivos
   - `admin` y `analyst` pueden ejecutar análisis
   
2. **Organization Scoping:**
   - Los usuarios solo ven datos de su organización
   - Las operaciones están limitadas al contexto org_id del user

3. **Confirmation Dialogs:**
   - Frontend muestra confirmación para operaciones destructivas
   - Backend requiere `confirm: true` en request body
   - Doble protección: UI + API

4. **Logging:**
   - Todos los cambios se registran en `logs/app.jsonl` con contexto completo
   - Eventos loguean: user_id, admin_id, org_id, action, timestamps

---

## 7. Testing Checklist

- [ ] Login como admin
- [ ] Navegar a AdminPanel
- [ ] Verificar que las 3 nuevas secciones aparecen (Neo4j Sync, Cleanup, Analysis, Users)
- [ ] En Cleanup: click en "Eliminar Todo", confirmar, verificar resultado
- [ ] En Analysis: click en "Detectar Duplicados", verificar result card
- [ ] En Analysis: click en "Encontrar Huérfanos", verificar orphans list
- [ ] Verificar logs en `logs/app.jsonl` con eventos admin.cleanup_all_data, admin.duplicate_codes_detection, etc.
- [ ] Login como analyst: verificar que NO ve botones destructivos, solo análisis
- [ ] Verificar que no puede acceder a /api/admin/cleanup/* (403)

---

## 8. Roadmap Futuro

**Próximas fases:**
1. **Progress Indicators:** Mostrar progreso en tiempo real para operaciones largas
2. **Async Background Jobs:** Usar Celery para cleanup de datasets muy grandes
3. **Approval Workflow:** Requerir aprobación de otro admin antes de cleanup
4. **Audit Trail UI:** Vista detallada de todas las acciones de admin
5. **Metrics Dashboard:** Gráficos de integridad históricos

---

*Documento creado:** 16 de enero de 2026  
*Última actualización:* 16 de enero de 2026
