# App Review Findings (Deep Dive)

## 1. Critical Security & Architecture Risks
### 🚨 Remote Execution Vulnerability in Frontend
- **File**: `frontend/vite.config.ts`
- **Issue**: The custom `apiPlugin` intercepts `/api/*` requests and executes `python main.py` via `child_process.spawn`.
- **Risk**: This middleware has **NO authentication**. Anyone with network access to the Vite dev server (default port 5173) can trigger these commands. This is a **Remote Code Execution (RCE)** vector.
- **Production Failure**: This plugin only works in the Vite dev server (`configureServer`). In a production build (`npm run build`), these API endpoints **will not exist**, rendering the application non-functional.

### 🚨 Backend Service Coupling
- **File**: `backend/app.py`
- **Issue**: The `get_clients` dependency calls `build_service_clients`, which initializes connections to Azure, Qdrant, Neo4j, and Postgres *simultaneously*.
- **Risk**: If **ANY** single service (e.g., Azure OpenAI or Qdrant) is down or unreachable, the entire backend fails to start or serve requests, even for operations that only need Neo4j. The health check (`/healthz`) does not check these, but any endpoint using `clients` will crash.

### ⚠️ Code Duplication & Drift
- **Files**: `main.py` vs `frontend/vite.config.ts`
- **Issue**: The `STAGE_DEFINITIONS` dictionary is duplicated in both files.
- **Risk**: High probability of **drift**. If a stage is changed or added in the Python CLI, the frontend will not know about it (and vice versa), leading to UI bugs or broken workflows.

## 2. Corrections & Clarifications
- **Postgres Safety**: The `sample_postgres` function uses parameterized queries (`LIMIT %s`) and is safe from SQL injection, contrary to the initial review.
- **Missing API**: **Correction** — `/api/projects`, `/api/status`, and other `/api/*` endpoints **are implemented** in `backend/app.py`. The original observation is outdated.

## 2.1 Status Update (2026-01-15)
### ✅ Backend API Coverage Confirmed
- The FastAPI backend now includes endpoints for `/api/projects`, `/api/status`, `/api/ingest`, `/api/health/full`, `/api/neo4j/*`, and additional routes for coding, discovery, and auth.
- The frontend `api.ts` is aligned with these endpoints and handles JWT/API-key auth.

### ⚠️ Vite Dev Middleware Still Executes Python
- **File**: `frontend/vite.config.ts`
- **Current Behavior**: The dev/preview middleware still calls `python main.py ... status` when `/api/status` is hit.
- **Risk**: Although the command is fixed, it is still **remote-triggered command execution** on the dev server without auth and should be removed to eliminate attack surface and to avoid behavior differences between dev and prod.

## 3. Immediate Recommendations
### 1. Security & Architecture
- **Kill the Vite Plugin**: Remove the `apiPlugin` from `vite.config.ts` entirely. It is insecure and incompatible with production.
- **Implement Endpoints in FastAPI**: Port all logic from the Vite plugin (project creation, status, ingestion wrappers) directly into `backend/app.py`.
- **Add Authentication**: Implement proper authentication (e.g., OAuth2 or at least a validated API Key) for all sensitive endpoints in FastAPI.

### 2. Reliability
- **Lazy Loading / Graceful Degradation**: Refactor `build_service_clients` in `backend/app.py` to initialize clients lazily or handle connection failures gracefully, so the API remains available even if one service is down.

### 3. Maintenance
- **Single Source of Truth**: Expose `STAGE_DEFINITIONS` via a new API endpoint (e.g., `/api/config/stages`) so the frontend can fetch it dynamically, eliminating code duplication.
