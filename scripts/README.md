# Scripts - Utilidades y Automatización

Este directorio contiene scripts para operaciones, pruebas y mantenimiento del sistema.

---

## Categorías de Scripts

### 🚀 Startup (Iniciar Servicios)

| Script | Descripción |
|--------|-------------|
| `start_all.bat` | Inicia todo: Docker + Worker + Backend + Frontend |
| `start_backend.bat` | Solo FastAPI backend |
| `start_frontend.bat` | Solo Vite frontend |
| `start_worker.bat` | Solo Celery worker |
| `run_local.ps1` | Modo desarrollo local (PowerShell) |

Uso rápido:
```bash
cmd /c scripts\start_all.bat
```

---

### 🧪 Testing y Verificación

| Script | Descripción |
|--------|-------------|
| `run_e2e.ps1` | Orquestador de pruebas E2E completas |
| `verify_ingestion.py` | Verificación cross-database (Neo4j, Qdrant, PG) |
| `healthcheck.py` | Verificar conectividad a todos los servicios |
| `verify_sprint_5.py` | Validar features de Sprint 5 |
| `test_import_backend.py` | Test de imports del backend |

Uso:
```powershell
# E2E completo
powershell -ExecutionPolicy Bypass -File scripts/run_e2e.ps1

# Solo health check
python scripts/healthcheck.py --env .env
```

---

### 📊 Load Testing

| Script | Descripción |
|--------|-------------|
| `load_test.py` | Pruebas de carga genéricas |
| `load_test_ingest.py` | Load test específico de ingesta |
| `generate_test_data.py` | Generador de datos sintéticos |

---

### 🔧 Migraciones

| Script | Descripción |
|--------|-------------|
| `run_neo4j_migration.py` | Migraciones de esquema Neo4j |
| `run_postgres_migration.py` | Migraciones PostgreSQL |
| `run_qdrant_migration.py` | Reconfiguración de colecciones Qdrant |
| `qdrant_reindex.py` | Reindexar vectores en Qdrant |
| `recreate_views.py` | Recrear vistas SQL |
| `fix_postgres_pk.py` | Corregir primary keys de PostgreSQL |

---

### 🧹 Limpieza y Mantenimiento

| Script | Descripción |
|--------|-------------|
| `cleanup_projects.py` | Limpieza de proyectos |
| `cleanup_axial_ai_analyses.py` | Retención de artefactos IA axial (`axial_ai_analyses`) |
| `retry_link_predictions_neo4j.py` | Reintentos automáticos de sync Neo4j para link predictions |
| `clear_projects.py` | Borrar datos de proyectos |
| `delete_file_data.py` | Eliminar datos de archivo específico |
| `remap_ghost_codes.py` | Corregir códigos huérfanos |
| `normalize_taxonomy.py` | Normalizar taxonomía de códigos |

⚠️ **IMPORTANTE**: Estos scripts son destructivos. Requieren `CLEANUP_CONFIRM=true`.

---

### 🔍 Inspección y Diagnóstico

| Script | Descripción |
|--------|-------------|
| `check_db_count.py` | Contar registros en bases de datos |
| `check_neo4j.py` | Inspeccionar nodos Neo4j |
| `inspect_data.py` | Inspección general de datos |
| `show_prompt_example.py` | Mostrar ejemplos de prompts LLM |
| `gds_analysis.py` | Ejecutar algoritmos GDS |

---

### ⬇️ Aplicación de Planes

| Script | Descripción |
|--------|-------------|
| `apply_coding_plan.py` | Aplicar plan de codificación desde JSON/CSV |
| `apply_metadata_plan.py` | Aplicar metadatos desde plan |

---

### 📝 Documentación

| Script | Descripción |
|--------|-------------|
| `createDoc.ps1` | Generar documentación automática |
| `run_manual.ps1` | Referencia de comandos manuales |

---

## Variables de Entorno Comunes

```env
# Archivo .env requerido
CLEANUP_CONFIRM=true       # Para scripts destructivos
ENVIRONMENT=development    # O test, production
```

---

## Exit Codes (verify_ingestion.py)

| Código | Significado |
|--------|-------------|
| 0 | Éxito |
| 2 | Verificación fallida |
| 3 | Violación de seguridad |
| 4 | Timeout |

---

### 👤 Autenticación (Nuevo)

| Script | Descripción |
|--------|-------------|
| `create_admin.py` | Crear usuario administrador inicial |

Uso:
```bash
# Interactivo
python scripts/create_admin.py

# Con argumentos
python scripts/create_admin.py --email admin@example.com --password "SecurePass123!"
```

Requisitos de password:
- Mínimo 8 caracteres
- 1 mayúscula, 1 minúscula, 1 número, 1 especial (@$!%*?&#)

---

*Documento actualizado: 2025-12-27*
