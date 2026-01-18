 # Recomendación para correr local:                                               
                    $env:NEO4J_API_KEY = "<your-api-key>"
# optionally point to a .env file the backend should load
$env:APP_ENV_FILE = ".env"
                    uvicorn backend.app:app --reload --port 8000

# reuse the backend API key for the frontend (the README and code use VITE_NEO4J_API_KEY)
$env:VITE_NEO4J_API_KEY = $env:NEO4J_API_KEY
# DEV recomendado: NO setear VITE_API_BASE (usa el proxy same-origin de Vite).
# Si necesitas cambiar el target del proxy:
$env:VITE_BACKEND_URL = 'http://localhost:8000'
cd frontend
npm install         # first run only
npm run dev


# Interview Ingestion and Qualitative Analysis Pipeline

This workspace reproduces the notebook `ingesta_entrevistas_qdrant_neo4j_postgres_analisis (1).ipynb` as a modular CLI application. The goal is to ingest `.docx` interview transcripts, generate Azure OpenAI embeddings, and persist every fragment in Qdrant, Neo4j, and PostgreSQL while keeping helpers for qualitative analysis.

## Features
- End-to-end ingestion from DOCX paragraphs to Qdrant, Neo4j, and PostgreSQL.
- Mini block design: each concern (settings, clients, documents, embeddings, ingestion, analysis, coding, axial, queries) lives in a dedicated module under `app/`.
- Structured logging with run IDs, batch metrics, coherence flags, and evidence of coverage.
- CLI for ingestion, semantic search, sampling, qualitative analysis, open coding, and axial relations.
- Healthcheck utility (`scripts/healthcheck.py`) to validate Azure OpenAI, Qdrant, Neo4j, and PostgreSQL connectivity.

## Repository Layout
```
app/
  analysis.py        # LLM-driven qualitative analysis helpers
  axial.py           # Axial coding helpers (Neo4j + Postgres + GDS)
  clients.py         # Connection factories for Azure OpenAI, Qdrant, Neo4j, PostgreSQL
  coding.py          # Open coding operations with Qdrant suggestions
  coherence.py       # Fragment quality heuristics
  documents.py       # DOCX reader, normalizer, batching utilities
  embeddings.py      # Embedding calls with retry/backoff and batch splitting
  ingestion.py       # Orchestrator combining all mini-blocks with metrics
  logging_utils.py   # Structured logging configuration/context helpers
  neo4j_block.py     # Neo4j constraints and merge helpers
  postgres_block.py  # PostgreSQL DDL/upsert helpers (fragments, coding, axial)
  queries.py         # Convenience queries for Qdrant, Neo4j, PostgreSQL
  settings.py        # Dataclasses for configuration loading
main.py              # CLI entry point (ingest/search/coding/axial/...)
scripts/healthcheck.py  # Service connectivity checks
scripts/gds_analysis.py # Standalone GDS runner for the axial graph
docs/data_dictionary.md # Data dictionary
```

## Prerequisites
- Python 3.12
- Azure OpenAI resource with deployed embedding/chat models
- Reachable Qdrant, Neo4j, and PostgreSQL instances
- PowerShell or bash shell to run CLI commands

## Setup
```powershell
python -m venv .venv
& ".venv\Scripts\Activate.ps1"

WLS source .venv_wsl/bin/activate

pip install --upgrade pip
pip install python-dotenv python-docx qdrant-client neo4j psycopg2-binary openai azure-identity azure-storage-blob tqdm tenacity pandas structlog

Copy-Item env.example .env
# edit .env with your credentials
```
(For bash, source `.venv/bin/activate` instead.)

## Environment Variables
Set the following keys in `.env` or your secret manager:
- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT_EMBED`, `AZURE_OPENAI_DEPLOYMENT_CHAT`
- `AZURE_STORAGE_CONNECTION_STRING` (optional): enables archiving interview DOCX files to Azure Blob Storage and linking them from printable reports
- `QDRANT_URI`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`
- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`
- `NEO4J_API_KEY` (obligatorio para consumir `/api/*` y `/neo4j/*`; si falta se usa `dev-key` solo para desarrollo)
- `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`
- Optional: `EMBED_DIMS` to override automatic dimension detection

## CLI Usage
Run commands from the project root with the virtual environment activated:
```powershell
# Adjust --log-level (DEBUG|INFO|WARNING|ERROR) and --run-id per sprint
python main.py --env .env --log-level INFO ingest data/Entrevista1.docx data/Entrevista2.docx
python main.py --env .env --log-level DEBUG --run-id sprint1 ingest data/Entrevista1.docx --meta-json metadata/entrevistas.json
python main.py --env .env search "conflictos de drenaje urbano"
python main.py --env .env counts
python main.py --env .env neo4j query --cypher "MATCH (c:Categoria) RETURN c.nombre AS categoria, size((c)--()) AS relaciones" --format table --json
python main.py --env .env sample --limit 5
python main.py --env .env analyze data/Entrevista1.docx --table --table-axial --persist
python main.py --env .env coding assign --fragment-id <fragment_uuid> --codigo "Participacion" --cita "La dirigente barrial..."
python main.py --env .env coding suggest --fragment-id <fragment_uuid> --area-tematica drenaje
python main.py --env .env coding stats
python main.py --env .env coding citations --codigo "Participacion"
python main.py --env .env axial relate --categoria "Confianza" --codigo "Participacion" --tipo causa --evidencia <frag1> <frag2> --memo "Participacion debil causa desconfianza"
python main.py --env .env axial gds --algorithm louvain
python main.py --env .env transversal pg --dimension genero --refresh
python main.py --env .env transversal qdrant --prompt "falta de areas verdes" --segment "Mujeres|genero=F" --segment "Hombres|genero=M"
python main.py --env .env transversal neo4j --attribute genero --values F M
python main.py --env .env transversal dashboard --prompt "participacion ciudadana" --attribute genero --values F M --segment "Mujeres|genero=F" --segment "Hombres|genero=M"
python main.py --env .env report outline
python main.py --env .env report build --output informes/informe_integrado.md --annex-dir informes/anexos --manifest informes/report_manifest.json
python main.py --env .env validation curve --window 3 --threshold 0
python main.py --env .env validation outliers --archivo "Entrevista_Final.docx" --limit 30 --threshold 0.8
python main.py --env .env validation overlap --limit 20
python main.py --env .env validation member --actor "dirigente vecinal" --limit 10
```

Command overview:
- `ingest`: Reads DOCX files, batches fragments, generates embeddings, and writes to all backends (metadata optional via `--meta-json`).
- `search`: Runs semantic similarity in Qdrant and prints the top matches.
- `counts`: Aggregates fragment counts per interview in Neo4j.
- `neo4j query`: Ejecuta consultas Cypher desde la CLI y devuelve salidas `raw`, `table` o `graph` (repetibles, con parámetros `--param clave=valor`).
- `sample`: Lists recent rows from PostgreSQL for quick inspection.
- `analyze`: Executes the qualitative LLM prompt and optionally persists matrices.
- `coding assign|suggest|stats|citations`: Manages open codes (registration, semantic suggestions, metrics, queries).
- `axial relate|gds`: Registers Categoria->Codigo relations with evidence/memo and runs GDS pipelines for prioritisation.
- `transversal pg|qdrant|neo4j|dashboard`: Etapa 6 toolkit — cross-tabs en PostgreSQL, probes segmentadas en Qdrant, subgrafos comparativos en Neo4j y payload integrado para dashboards.
- `report outline|build`: Etapa 9 toolkit — extrae estructura Categoria→Codigo y genera `informe_integrado.md` con anexos y manifiesto reproducible.
- `validation curve|outliers|overlap|member`: Etapa 8 toolkit — analiza saturación (curva de nuevos códigos), detecta outliers semánticos, triangula fuentes en Neo4j y arma paquetes de member checking desde PostgreSQL.

All commands accept `--log-level` (default `INFO`) and optionally `--run-id` for consistent structured logging.

## HTTP API – Backend unificado

Además de la CLI, puedes exponer consultas Cypher y los flujos de proyectos/ingesta/codificación mediante FastAPI.

```powershell
# (opcional) define la ruta al .env que usará el backend
$env:APP_ENV_FILE = ".env"

# levanta el servicio (FastAPI)
uvicorn backend.app:app --reload --port 8000
# Requiere que NEO4J_API_KEY esté definido; opcional APP_ENV_FILE para el .env
```

### Endpoints Neo4j (`/neo4j/query` y `/neo4j/export`)

```bash
curl -X POST http://localhost:8000/neo4j/query \
  -H "Content-Type: application/json" \
  -d '{
        "cypher": "MATCH (c:Categoria)-[r:REL]->(k:Codigo) RETURN c.nombre AS categoria, k.nombre AS codigo, size(r.evidencia) AS evidencia",
        "formats": ["table","raw"]
      }'
```

Campos soportados:
- `cypher` (obligatorio): sentencia Cypher.
- `params` (opcional): diccionario clave→valor para parámetros Cypher.
- `formats` (opcional): `raw`, `table`, `graph` o `all` (múltiples).
- `database` (opcional): base de datos Neo4j; por defecto usa `NEO4J_DATABASE`.

La respuesta refleja el mismo contrato que la CLI (`raw/table/graph`). Al finalizar la consulta los clientes (Neo4j/Qdrant/Postgres) se cierran automáticamente e incluye el header `X-Query-Duration` con la latencia en milisegundos. Todas las peticiones deben incluir el header `X-API-Key` definido en la variable `NEO4J_API_KEY`.

### Exportar resultados (`/neo4j/export`)

```bash
curl -X POST http://localhost:8000/neo4j/export \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $NEO4J_API_KEY" \
  -d '{
        "cypher": "MATCH (c:Categoria) RETURN c.nombre AS categoria LIMIT 20",
        "export_format": "csv"
      }' -o neo4j_export.csv
```

- `export_format`: `csv` o `json` (por defecto `csv`).
- Respeta el mismo payload que `/neo4j/query` (`cypher`, `params`, `database`).
- El CSV se genera a partir de la vista `table`; si la consulta no produce columnas, se devuelve error 400.
- Respuesta incluye `X-Query-Duration` para observabilidad básica.

### Endpoints de proyecto/ingesta/codificación (`/api/*`)
- `/api/projects` `GET|POST`: listar y crear proyectos (requiere `X-API-Key`).
- `/api/status?project=<id>`: snapshot de etapas reutilizando las definiciones del CLI.
- `/api/projects/{id}/stages/{stage}/complete`: marcar manualmente una etapa.
- `/api/ingest`: dispara ingesta de archivos DOCX con parámetros `batch_size/min_chars/max_chars/meta_json/run_id`.
- `/api/coding/*`: assign, suggest, stats, codes, fragments, citations, interviews, fragments/sample.

Todas las rutas requieren el header `X-API-Key` (`NEO4J_API_KEY`).

### Explorer web (React)

El dashboard React consume `/api/*` y `/neo4j/*` del backend FastAPI (vía proxy de Vite). Arranque:
```powershell
# Terminal 1 (backend)
uvicorn backend.app:app --reload --port 8000

# Terminal 2 (frontend)
  cd frontend
  npm install  # primera vez
  # Windows PowerShell (set the env vars for the dev process):
  $env:VITE_NEO4J_API_KEY = $env:NEO4J_API_KEY; $env:VITE_API_BASE = 'http://localhost:8000'; npm run dev
  # Or on bash / WSL:
  # VITE_NEO4J_API_KEY="$NEO4J_API_KEY" VITE_API_BASE=http://localhost:8000 npm run dev
```

Define `VITE_API_BASE` (por defecto http://127.0.0.1:8000). El proxy de Vite redirige `/api` y `/neo4j` al backend.

## Coding & Axial Assistance
- `coding assign` registers open codes backed by literal evidence and synchronises Neo4j (`Fragmento`-[:TIENE_CODIGO]->`Codigo`).
- `coding suggest` queries Qdrant with payload filters to propose similar fragments (excluding coded ones by default).
- `coding stats` summarises coverage (coded vs total fragments) and `coding citations` lists evidence per code.
- `axial relate` creates relations `Categoria`-[:REL {tipo,memo,evidencia}]->`Codigo` (requires >=2 coded fragment IDs) and persists to Neo4j/PostgreSQL.
- `axial gds` or `python -m scripts.gds_analysis --algorithm <algo>` runs Louvain/PageRank/Betweenness on the axial graph to highlight communities and key nodes (human-in-the-loop review).

## Logging & Quality Metrics
- Structured JSON logs (structlog) include `run_id`, batch metrics, and command-specific context (`coding_command`, `axial_command`, `nucleus_command`, `transversal_command`, `report_command`, `validation_command`).
- Ingestion surfaces coherence flags (`placeholder_marker`, `inaudible_tag`, `filler_repetition`, etc.) per fragment and aggregates counts per archivo.
- Post-run summaries report percentages for `char_len == 0`, duplicates via `sha256`, and totals per archivo to validate the DoD (>99% fragmentos validos).
- Use `--run-id` to group logs, metrics, and reflexive notes per sprint.

## Health Checks
```powershell
python -m scripts.healthcheck --env .env
```
This confirms Azure OpenAI connectivity, Qdrant dimensionality/payload indexes, PostgreSQL availability, and Neo4j constraints. Errors are reported with `ERROR` lines in the console.

## Continuous Integration
- GitHub Actions workflow `.github/workflows/ci.yml` ejecuta `npm run test` y `python -m pytest -q` en cada push/PR.
- El job usa caché para `npm` y `pip` y fija la API key de prueba mediante `NEO4J_API_KEY=test-key`. Para entornos productivos, define `NEO4J_API_KEY` como secreto en el repositorio.
- Si ejecutas `npm run test` en WSL y aparece el error de `@rollup/rollup-linux-x64-gnu`, elimina `frontend/node_modules` y `package-lock.json` antes de reinstalar (`npm install`).

## Load Testing & Monitoring

### Prueba de carga básica

```bash
python scripts/load_test.py \
  --endpoint http://localhost:8000/neo4j/query \
  --api-key $NEO4J_API_KEY \
  --duration 60 \
  --concurrency 8
```

La salida es un JSON con totales, duración media y percentiles (p95/p99). Para exportes:

```bash
python scripts/load_test.py \
  --endpoint http://localhost:8000/neo4j/query \
  --api-key $NEO4J_API_KEY \
  --export csv
```

### Alertas mínimas

Los logs estructurados registran eventos `neo4j.query.success`, `neo4j.query.failure` y `neo4j.export.success`. Puedes levantar una alerta básica revisando los últimos mensajes:

```bash
python - <<'PY'
import json, pathlib
path = pathlib.Path("logs/neo4j_api.log")
failures = 0
for line in path.read_text().splitlines()[-200:]:
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        continue
    if record.get("event") == "neo4j.query.failure":
        failures += 1
if failures:
    print(f"⚠️  {failures} fallos recientes en neo4j.query.failure")
PY
```

Integra este script (ajustando la ruta del log según tu despliegue) en cron/CI para recibir notificaciones básicas cuando se acumulen errores consecutivos.

## Typical Workflow
1. Configure credentials in `.env` (or environment variables).
2. Activate the virtual environment and install dependencies.
3. Run `python -m scripts.healthcheck --env .env` to ensure services are reachable.
4. Ingest DOCX files with `python main.py --env .env ingest ...`.
5. Validate data via `search`, `counts`, `sample`.
6. Use `analyze`, `coding`, and `axial` commands to populate matrices and grafo.
7. Document findings and decisions in `docs/reflexividad.md` (evidence positiva y negativa).

## Documentation
- `docs/data_dictionary.md`: Data dictionary for tables/payloads.
- `docs/reflexividad.md`: Template for the reflexivity diary and governance notes.

## Relationship to the Notebook
Each notebook section (`Configuracion`, `Lectura DOCX`, `Embeddings`, `Upserts`, `Analisis cualitativo`) maps directly to a module inside `app/`, making the pipeline reusable outside Jupyter. The CLI mirrors the execution order while keeping credentials/effects outside the notebook.

## Next Steps
- Add automated tests (unit and integration) with mocked services.
- Package dependencies with `pyproject.toml` or `setup.cfg`.
- Provide Docker Compose recipes for the supporting services.
- Extend reflexive documentation with sprint-specific memos and evidence negativa.
