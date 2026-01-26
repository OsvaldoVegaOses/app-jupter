# App Review Findings

## 1. General Observations
- The project structure is clear, separating core logic (`app/`), CLI (`main.py`), backend (`backend/`), and frontend (`frontend/`).
- `main.py` serves as a comprehensive CLI for managing the pipeline.

## 2. Potential Errors & Issues
### Backend
- [x] Check `backend/app.py` for error handling and API design.
    - **Observation**: Uses FastAPI with `structlog`. Error handling is present.
    - **Warning**: CORS `allow_origins=["*"]` is very permissive.
    - **Note**: API Key is required via `X-API-Key` header.

### Core Logic (`app/`)
- [x] Review `app/settings.py` for configuration management.
    - **Observation**: Uses `dotenv` and dataclasses. `mask` function used for security.
    - **Note**: `embed_dims` parsing logic is safe but relies on env var being correct.
- [x] Review `app/ingestion.py` and `app/queries.py`.
    - **Observation**: `ingest_documents` is complex and handles multiple stores (Qdrant, Neo4j, Postgres).
    - **Warning**: `sample_postgres` uses raw SQL. `run_cypher` uses raw Cypher. Parameterization is used, which is good.
    - **Suggestion**: Consider splitting `ingest_documents` into smaller functions.

### Frontend & Architecture
- [x] Check `frontend/src` for structure and best practices.
    - **Observation**: `App.tsx` makes calls to `/api/projects/...`.
    - **Discovery**: `vite.config.ts` contains a custom `apiPlugin` that intercepts `/api/*` requests and spawns `python main.py` subprocesses.
    - **CRITICAL**: This architecture (spawning a process per request) is inefficient and fragile for production.
    - **Disconnect**: `backend/app.py` (FastAPI) is not currently used by the frontend for these project operations. It only handles Neo4j queries.
    - **Risk**: `runCommand` in `vite.config.ts` relies on the local python environment and CLI availability.

## 3. Improvement Proposals
### Architecture (High Priority)
- [ ] **Migrate Logic to FastAPI**: Move the CLI logic (project creation, status, ingestion) from `vite.config.ts` (and `main.py` CLI wrappers) into `backend/app.py`.
- [ ] **Unified Backend**: Have the frontend talk exclusively to the FastAPI backend (`backend/app.py`), avoiding the "Vite plugin as backend" pattern.
- [ ] **Proxy Setup**: Configure Vite to proxy `/api` requests to the FastAPI server (e.g., running on port 8000) during development.

### Code Quality
- [ ] **Refactor `ingest_documents`**: Break down the large ingestion function in `app/ingestion.py` into smaller, testable components.
- [ ] **Security**: Ensure `backend/app.py` properly validates `X-API-Key` and consider more robust auth if needed.
- [ ] **Type Safety**: Add more strict type checking in the frontend (some `any` usage in `vite.config.ts`).

### Performance
- [ ] **Async Database**: Consider using `asyncpg` or similar for Postgres in FastAPI to avoid blocking the event loop (currently `backend/app.py` calls synchronous `run_cypher` in a lambda, which might block if not careful, though FastAPI handles def endpoints in threadpool).

### Reliability
- [ ] **Error Handling**: Improve error parsing in the frontend. The current manual JSON parsing in `vite.config.ts` is brittle.
