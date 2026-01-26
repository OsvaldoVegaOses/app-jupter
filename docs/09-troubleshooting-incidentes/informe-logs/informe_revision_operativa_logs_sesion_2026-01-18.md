# Informe de Revisión Operativa — Logs por sesión/proyecto

**Fecha:** 2026-01-18  
**Alcance:** Clasificación y encarpetado de logs por sesión y proyecto.

## Objetivo
Separar los logs por sesión (y proyecto cuando esté disponible) para mejorar trazabilidad, aislamiento de incidentes y análisis de eventos sin ruido cruzado.

## Implementación

### 1) Ruteo de logs por sesión/proyecto
**Archivo:** [app/logging_config.py](../../app/logging_config.py)

Se añadió un handler contextual que escribe en:

```
logs/{project_id}/{session_id}/app.jsonl
```

Si no existe `session_id`, se mantiene el comportamiento clásico:

```
logs/app.jsonl
```

**Comportamiento clave:**
- Sanitiza `project_id` y `session_id` para nombres de carpeta seguros.
- Crea handlers por combinación `(project_id, session_id)` con rotación diaria.
- Respeta el formato JSONL existente.

### 2) Contexto por request
**Archivo:** [backend/app.py](../../backend/app.py)

Se vinculan estas claves al contexto estructurado por request:
- `request_id` (existente)
- `session_id` (nuevo)
- `project_id` (nuevo)

**Fuentes:**
- `X-Session-ID` (header)
- `X-Project-ID` (header, opcional)
- `project` / `project_id` (query params)

Esto permite que el ruteo de logs sepa la sesión y el proyecto de cada request.

### 3) Envío automático de X-Session-ID
**Archivo:** [frontend/src/services/api.ts](../../frontend/src/services/api.ts)

Se genera un `SESSION_ID` por sesión de navegador y se envía automáticamente en cada request al backend:
- Header: `X-Session-ID`

## Resultado
- Logs separados por sesión y proyecto.
- Aislamiento rápido de incidentes por usuario/sesión.
- Mejor trazabilidad multi-tenant.

## Validación operativa
1. Levantar backend y frontend.
2. Realizar llamadas desde la UI.
3. Verificar carpeta generada:

```
logs/default/<session_id>/app.jsonl
```

Si hay `project_id`, debe aparecer el nombre del proyecto.

## Consideraciones
- Si se requieren logs por organización, se puede extender el contexto con `organization_id`.
- La rotación diaria se mantiene (30 días).

## Estado
✅ Implementado y documentado.
