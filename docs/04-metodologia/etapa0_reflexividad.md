# Etapa 0 – Preparación, Reflexividad y Configuración

> **Actualizado: Diciembre 2024** - Revisado contra estado actual del sistema

## 1. Alineación metodológica
- Define objetivo del sprint, preguntas orientadoras y alcance (entrevistas, periodo, segmentos). Versionalo en `docs/reflexividad.md`.
- Registra supuestos, sesgos potenciales y estrategias de mitigación (p.ej. pares de cotejo, sesiones de debrief) usando un `run_id` inicial.
- Documenta criterios de inclusión/exclusión de fuentes: lista DOCX, fecha de obtención, responsable y hash (usa `sha256sum archivo.docx`).

## 2. Variables de entorno y llaves

### ✅ Configuración mínima requerida

```bash
cp env.example .env
```

Variables principales:
```bash
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://<tu-endpoint>.openai.azure.com/
AZURE_OPENAI_API_KEY=<clave_primaria>
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Modelos (verificar nombres de deployment)
AZURE_OPENAI_DEPLOYMENT_CHAT=gpt-5-chat
AZURE_DEPLOYMENT_GPT5_MINI=gpt-5-mini
AZURE_DEPLOYMENT_EMBED=text-embedding-3-large

# Bases de datos
POSTGRES_HOST=localhost
NEO4J_URI=bolt://localhost:7687
QDRANT_URI=http://localhost:6333
```

## 3. Checklist técnico

| Servicio | Variable | Comando de verificación | Estado |
|----------|----------|------------------------|--------|
| **PostgreSQL** | `POSTGRES_*` o `PG*` | `psql -c '\dt'` | ✅ Ambos formatos soportados |
| **Neo4j** | `NEO4J_URI`, `NEO4J_USERNAME` | `cypher-shell "CALL dbms.components()"` | ✅ GDS disponible |
| **Qdrant** | `QDRANT_URI`, `QDRANT_API_KEY` | `python scripts/healthcheck.py` | ✅ 9 índices creados |

## 4. Salud de infraestructura

```bash
python scripts/healthcheck.py --env .env
```

**Verificaciones automáticas:**
- ✅ Dimensiones de embeddings (`EMBED_DIMS`)
- ✅ Colección Qdrant con 9 payload indexes
- ✅ Constraints en Neo4j
- ✅ Latencia < 1s a cada servicio

**Alternativa con inicio completo:**
```bash
cmd /c scripts\start_all.bat
```

## 5. Instrumentación y trazabilidad

```bash
# Crear proyecto
python main.py project create --name "MiProyecto" --description "Análisis cualitativo"

# Verificar estado
python main.py status --project mi-proyecto
```

**Estructura de archivos:**
```
metadata/
├── projects/
│   └── mi-proyecto.json    # Estado del proyecto
└── projects_registry.json   # Registro de proyectos
```

## 6. Checklist ético y legal
- Confirma consentimientos informados
- Política de anonimato documentada
- Tiempo máximo de retención definido

## 7. Documentación disponible

| Documento | Propósito |
|-----------|-----------|
| `app/README.md` | Arquitectura módulo core (22 archivos) |
| `backend/README.md` | API REST (54 endpoints) |
| `frontend/README.md` | Dashboard React |
| `scripts/README.md` | 34 utilidades categorizadas |

## 8. Salida esperada

- [x] `.env` completo con todas las variables
- [x] Proyecto creado en `metadata/projects/`
- [x] Healthcheck exitoso
- [x] Log inicial en `logs/`

## 9. Operacionalización en el sistema

Esta etapa no es solo “documentación”: está operacionalizada y **bloquea** operaciones críticas (ingesta/análisis) hasta que el proyecto cumpla los mínimos o exista un override aprobado.

### UI (Frontend)
- **VISTA 2: Flujo de trabajo** incluye un panel ejecutable para Etapa 0.
- Panel: `Stage0PreparationPanel` (protocolo, actores/consentimientos, muestreo, plan, overrides).

### API (Backend)
- Checklist/estado: `GET /api/stage0/status?project=<id>`
- Protocolo (versionado): `POST /api/stage0/protocol`, `GET /api/stage0/protocol/latest`
- Actores anonimizados: `POST /api/stage0/actors`, `GET /api/stage0/actors`
- Consentimientos: `POST /api/stage0/actors/{actor_id}/consents`
- Muestreo (versionado): `POST /api/stage0/sampling`, `GET /api/stage0/sampling/latest`
- Plan de análisis (versionado): `POST /api/stage0/analysis-plan`, `GET /api/stage0/analysis-plan/latest`
- Overrides (doble validación): `POST /api/stage0/overrides`, `GET /api/stage0/overrides`, `POST /api/stage0/overrides/{override_id}/approve|reject`

### Gating (bloqueo/permiso)
- Si `ready=false` y no hay override aprobado vigente, el backend responde **409** en operaciones como análisis.
- Con override aprobado, la operación se permite y se registra uso de override en auditoría.

### Auditoría y privacidad
- Diseño explícito: **no PII** (solo alias + demographics_anon) y eventos auditados en `project_audit_log`.

---

*Última verificación: 13 Diciembre 2024*
