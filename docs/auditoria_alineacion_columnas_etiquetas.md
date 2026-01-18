# Auditoría de alineación de columnas y etiquetas (producción)

**Fecha:** 2026-01-17

## Alcance
- Backend: app, backend
- Frontend: frontend
- Esquemas/SQL: migrations
- Informe generado en entorno de código (análisis estático; no consulta a BD en vivo).

## Resumen ejecutivo
Se identifican discrepancias entre etiquetas de UI, endpoints y columnas reales de BD que pueden provocar errores o confusión en producción. Las principales fuentes de ruido son:
- uso de `org_id` vs `organization_id` en la tabla proyectos,
- ausencia de la columna `is_deleted` en proyectos,
- ausencia de `neo4j_synced` si no se ejecutó la migración 010,
- columnas agregadas en migraciones 008 (si no se aplicaron) para `analisis_codigos_abiertos` y `discovery_navigation_log`.

## Hallazgos de alineación (columnas vs lógica)

### 1) Proyectos: organización
- **Columna real:** `proyectos.org_id` (ver [migrations/009_projects_table.sql](migrations/009_projects_table.sql))
- **Uso esperado en lógica:** filtros por `org_id`.
- **Riesgo:** consultas que usan `organization_id` fallan.
- **Estado:** **Desalineado** (histórico). Corregido en el endpoint de limpieza, pero se recomienda revisión completa.
- **Acción recomendada:** estandarizar `org_id` en consultas a `proyectos`.

### 2) Proyectos “deleted”
- **Columna esperada por UI:** `proyectos.is_deleted` (botón “Limpiar Proyectos Deleted”).
- **Columna real:** no existe en migraciones actuales.
- **Estado:** **Desalineado**.
- **Impacto:** errores 500 o respuesta “not_supported”.
- **Acción recomendada:** o bien agregar `is_deleted` a `proyectos`, o retirar/ocultar el botón en producción.

### 3) Sincronización Neo4j
- **Columna:** `entrevista_fragmentos.neo4j_synced` (ver [migrations/010_neo4j_sync_tracking.sql](migrations/010_neo4j_sync_tracking.sql)).
- **Dependencias:** `app/neo4j_sync.py` usa esta columna para calcular `pending/synced`.
- **Estado:** **Alineado solo si la migración 010 está aplicada**.
- **Acción recomendada:** asegurar migración 010 en producción.

### 4) Códigos abiertos: `cita` y `fuente`
- **Columnas:** `analisis_codigos_abiertos.cita`, `analisis_codigos_abiertos.fuente` (ver [migrations/008_schema_alignment.sql](migrations/008_schema_alignment.sql)).
- **Estado:** **Alineado solo si migración 008 aplicada**.
- **Acción recomendada:** asegurar migración 008 en producción.

### 5) Discovery navigation log
- **Columnas agregadas:** `busqueda_id`, `positivos`, `negativos`, `target_text`, `fragments_count`, `codigos_sugeridos`, `refinamientos_aplicados`, `ai_synthesis`, `action_taken`, `busqueda_origen_id` (ver [migrations/008_schema_alignment.sql](migrations/008_schema_alignment.sql)).
- **Estado:** **Alineado solo si migración 008 aplicada**.
- **Acción recomendada:** asegurar migración 008 en producción.

### 6) Tabla de candidatos
- **Tabla:** `codigos_candidatos` (ver [migrations/007_codigos_candidatos.sql](migrations/007_codigos_candidatos.sql)).
- **UI asociada:** panel de validación de candidatos.
- **Estado:** **Alineado** si migración 007 aplicada.
- **Acción recomendada:** verificar existencia en producción.

### 7) Tabla de archivos de entrevista
- **Tabla:** `interview_files` (ver [migrations/008_interview_files.sql](migrations/008_interview_files.sql)).
- **Estado:** **Alineado** si migración 008 aplicada.
- **Acción recomendada:** verificar y documentar el uso en UI.

## Hallazgos de alineación (etiquetas UI vs comportamiento)

### Admin Panel: Limpiezas
- **Etiqueta:** “🗑️ Limpiar Proyectos Deleted”
  - **Backend:** depende de `proyectos.is_deleted`.
  - **Estado:** **Desalineado** si no existe la columna.
- **Etiqueta:** “🧹 Limpiar Huérfanos”
  - **Backend:** elimina registros donde el archivo no existe en FS local ni en Blob Storage (si está configurado).
  - **Estado:** **Alineado** con Blob Storage habilitado.
  - **Riesgo:** en producción sin Blob Storage configurado, se valida solo FS local.

### Admin Panel: Sincronización Neo4j
- **Etiqueta:** “Pendientes / Sincronizados / Total”
  - **Backend:** `app/neo4j_sync.py`.
  - **Estado:** **Alineado** si `neo4j_synced` está presente.

## Riesgos de producción
- Errores 500 o UX confuso por columnas no existentes (`is_deleted`, `organization_id` en proyectos).
- Reportes de sincronización Neo4j incorrectos si no se aplicó migración 010.
- Detección de huérfanos basada solo en filesystem local (puede ser falso positivo en despliegues con Blob Storage).

## Recomendaciones prioritarias
1. **Aplicar migraciones 007/008/010** en producción.
2. **Estandarizar `org_id` en `proyectos`** y evitar `organization_id` en ese contexto.
3. **Definir estrategia oficial para “deleted projects”** (agregar `is_deleted` o eliminar el botón).
4. **Ajustar limpieza de huérfanos** para contemplar Blob Storage en producción.

## Implementado (enero 2026)
- Migración agregada: [migrations/012_add_is_deleted_to_proyectos.sql](migrations/012_add_is_deleted_to_proyectos.sql).
- Script de aplicación: [scripts/apply_migrations_production.py](scripts/apply_migrations_production.py).
- Alineación de `org_id` en estadísticas admin (join con `proyectos`).
- Limpieza y detección de huérfanos ahora considera Blob Storage si hay configuración de Azure.

## Prueba End-to-End con datos reales (sin mocks)

### Objetivo
Validar flujo completo con servicios reales (PostgreSQL, Neo4j, Qdrant, Azure OpenAI, Azure Blob Storage) y confirmar alineación de columnas/etiquetas y salud de endpoints críticos.

### Prerrequisitos
- Servicios reales disponibles y credenciales válidas en `.env`.
- Migraciones 007/008/010/012 aplicadas en BD productiva.
- Backend y frontend corriendo sin `--reload`.

### Flujo de prueba
1. **Auth + Projects**
  - Login real desde frontend.
  - Verificar carga de proyectos y `organization_id`.
2. **Ingesta real**
  - Subir 1-2 DOCX reales.
  - Confirmar creación de fragmentos en PostgreSQL y nodos en Neo4j.
  - Verificar que `neo4j_synced = TRUE` o ejecutar sync.
3. **Neo4j Sync**
  - Ejecutar “Sincronizar” desde Admin Panel.
  - Verificar conteos `pending/synced/total`.
4. **Códigos candidatos**
  - Generar candidatos (Discovery o Runner).
  - Validar en panel de candidatos y confirmar persistencia.
5. **Limpieza huérfanos**
  - Eliminar manualmente un archivo local (conservar blob).
  - Ejecutar “Encontrar Huérfanos” y confirmar que no se marca si el blob existe.
6. **Cleanup projects deleted**
  - Marcar un proyecto como `is_deleted = true` y ejecutar limpieza.

### Evidencias mínimas esperadas en logs
- `admin.cleanup_*` y `admin.orphan_files_detection` en `logs/app.jsonl`.
- `neo4j_sync.*` en logs del backend.
- `qdrant.*` y `ingest.*` durante ingesta.
- `blob.uploaded` y `blob.deleted` cuando aplique.

### Validación final
- Frontend sin timeouts en `/api/projects`, `/api/status`, `/api/admin/*`.
- Conteos coherentes en panel admin.
- No existen huérfanos falsos positivos con Blob Storage habilitado.

## Notas
Este informe se basa en análisis estático del código fuente y scripts de migración. Para validación completa, ejecutar el flujo E2E real y verificar endpoints críticos.
