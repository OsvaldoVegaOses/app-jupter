# Agents (Mini Blocks)

> **Última actualización:** Diciembre 2024

This document explains the responsibilities of each module that was carved out of the original notebook. Treat every module as an agent with a single responsibility that can be orchestrated from the CLI or other applications.

## Core Coordination
- `main.py`: CLI dispatcher. Parses arguments, builds the execution context, binds `run_id` + log level, and delegates to the corresponding command (`ingest`, `search`, `counts`, `sample`, `analyze`).
- `backend/app.py`: HTTP API agent (FastAPI). Exposes ~60+ endpoints for the Frontend (`/api/*`) including:
  - Project management (`/api/projects/*`)
  - Ingestion (`/api/ingest`)
  - Graph queries (`/neo4j/*`)
  - GDS calculations
  - Semantic Discovery
  - **NEW**: Candidate codes management (`/api/codes/candidates/*`)
  - **NEW**: Health checks (`/healthz`, `/api/health/full`)
  - Protected with `X-API-Key` header.
- `backend/celery_worker.py`: **Async Worker Agent**. Handles long-running tasks like LLM analysis (`analyze_interview_text`) to prevent HTTP timeouts. Connects to Redis for task queuing.
- `app/logging_config.py`: **Logging Agent**. Centralizes configuration for structured logging (JSONL) and file persistence (`logs/`).
- `app/clients.py`: Connection agent. Creates and tears down clients for Azure OpenAI, Qdrant, Neo4j, and PostgreSQL using the configuration loaded by `app/settings.py`.
- `app/settings.py`: Configuration agent. Loads environment variables (optionally from `.env`) into strongly typed dataclasses (`AzureSettings`, `QdrantSettings`, `Neo4jSettings`, `PostgresSettings`) and offers masking helpers.

## Data Preparation Agents
- `app/documents.py`: Responsible for reading DOCX files, normalizing paragraphs, coalescing small fragments, building fragment identifiers, and emitting batches.
- `app/coherence.py`: Detects textual anomalies (`placeholder_marker`, `inaudible_tag`, muletillas) and aggregates issue counters for QA dashboards.
- `app/embeddings.py`: Wraps the Azure OpenAI embeddings endpoint with retry/backoff and automatic batch splitting when necessary.

## Storage Agents
- `app/qdrant_block.py`: Semantic memory. Ensures collections/indexes and performs upserts. Implements `discover_search` (Discovery API) and `search_similar` for context-aware retrieval.
- `app/neo4j_block.py`: Topological memory. Applies constraints and merges relationships.
- `app/postgres_block.py`: Relational memory. Creates/updates tables and executes bulk upserts. **NEW**: Includes candidate codes management (`codigos_candidatos` table).

## Orchestration and Diagnostics
- `app/ingestion.py`: High level pipeline agent. Wires document reading, embeddings, and storage agents.
- `app/coding.py`: Assisted coding. Inserts records in PostgreSQL, syncs Neo4j, and queries Qdrant/LLM for suggestions.
- `app/axial.py`: Logic engine. Manages axial relationships and executes **Neo4j GDS Pipelines** (Louvain, PageRank) with **Persistence Capabilities** (write-back to graph).
- `app/queries.py`: Diagnostic agent. Provides semantic search and counts.
- `app/nucleus.py`: Selective coding agent. Triangulates centrality, coverage, and semantic probes.
- `app/transversal.py`: Transversal analysis agent. Builds cross-tabs and comparative subgraphs.
- `app/validation.py`: Validation agent. Calculates saturation curves and detects semantic outliers.
- `app/reporting.py`: Reporting agent. Generates integrated markdown reports and data manifests.

## Scripts & Utilities
- `scripts/healthcheck.py`: Connectivity agent. Ensures system health before pipelines run.
- `scripts/gds_analysis.py`: CLI tool for reproducible GDS analysis (supports persistence).
- `scripts/validate_env.ps1`: **NEW** Environment validation agent. Validates frontend/backend config before starting development.

## Qualitative Analysis & Visualization
- `app/analysis.py`: **Cognitive Agent (GraphRAG)**. Analyzes interviews using LLMs. Before analysis, queries the "Living Graph" (Neo4j) to inject global context (Centrality + Communities) into the prompt.
- `app/graphrag.py`: GraphRAG integration agent. Extracts relevant subgraphs for context.
- `app/link_prediction.py`: Relationship prediction agent. Suggests new links based on graph structure.

## Frontend Agents (React/TypeScript)

### Core Visualization
- `frontend/src/components/Neo4jExplorer.tsx`: **Graph Visualization Agent**. Renders interactive graph with GDS Calculator controls (Community Coloring, Centrality Sizing).
- `frontend/src/components/CodingPanel.tsx`: **Coding Interface Agent**. Handles code assignment, semantic suggestions, and coverage metrics.
- `frontend/src/components/DiscoveryPanel.tsx`: **Discovery Agent**. Semantic search with triplet exploration and "Propose as Code" functionality.
- `frontend/src/components/ReportsPanel.tsx`: **Reporting Agent**. Displays stage reports and analysis results.
- `frontend/src/components/LinkPredictionPanel.tsx`: **Link Prediction Agent**. Generates suggested axial relationships (algorithms + analysis).
- `frontend/src/components/LinkPredictionValidationPanel.tsx`: **Axial Validation Agent**. Validates/rejects predicted relationships and syncs them to Neo4j.

### Candidate Codes Workflow (NEW)
- `frontend/src/components/CodeValidationPanel.tsx`: **Validation Agent**. Bandeja for validating, rejecting, and merging candidate codes from all sources. Supports batch operations and promotion to definitive codes.

### UX Enhancement Agents (NEW)
- `frontend/src/components/BackendStatus.tsx`: **Connection Monitor Agent**. Real-time backend connectivity indicator with latency measurement. Polls `/healthz` every 30 seconds.
- `frontend/src/components/SystemHealthDashboard.tsx`: **Health Dashboard Agent**. Collapsible panel showing status of all services (PostgreSQL, Neo4j, Qdrant, Azure OpenAI) with latency metrics.
- `frontend/src/components/ApiErrorToast.tsx`: **Error Notification Agent**. Global toast system that listens for `api-error` events and displays user-friendly messages.
- `frontend/src/components/PanelErrorBoundary.tsx`: **Error Boundary Agent**. React Error Boundary that catches rendering errors and provides recovery UI.
- `frontend/src/components/Skeleton.tsx`: **Loading State Agent**. Provides animated skeleton components for improved loading UX.

### API Service Layer
- `frontend/src/services/api.ts`: **API Client Agent**. Centralized fetch wrapper with:
  - Automatic `X-API-Key` header injection
  - Retry logic with exponential backoff
  - Global error event dispatching
  - Type-safe response handling

## Testing Agents (NEW)

### E2E Testing (Playwright)
- `frontend/tests/e2e/navigation.spec.ts`: Basic navigation and page load tests.
- `frontend/tests/e2e/code-validation.spec.ts`: CodeValidationPanel functionality tests.
- `frontend/tests/e2e/error-handling.spec.ts`: Error resilience and accessibility tests.
- `frontend/playwright.config.ts`: Playwright configuration with auto dev server.

---

## How the Agents Collaborate

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AGENT COLLABORATION FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. USER interacts with FRONTEND                                             │
│     └── BackendStatus monitors connection (healthz)                          │
│                                                                              │
│  2. FRONTEND triggers analysis (/api/analyze)                                │
│     └── ApiErrorToast catches any errors                                     │
│                                                                              │
│  3. CELERY WORKER starts app/analysis.py (async)                             │
│     └── analysis.py asks app/axial.py for GraphRAG context                   │
│                                                                              │
│  4. LLM processes text with graph context                                    │
│     └── Results stored via app/ingestion.py                                  │
│                                                                              │
│  5. USER proposes codes from Discovery/Suggestions                           │
│     └── Stored as candidates via /api/codes/candidates                       │
│                                                                              │
│  6. USER validates candidates in CodeValidationPanel                         │
│     └── Approved codes promoted to definitive                                │
│                                                                              │
│  7. USER clicks "Calculate GDS" in Neo4jExplorer                             │
│     └── backend/app.py calls app/axial.py                                    │
│     └── Graph updated with Communities/Scores                                │
│                                                                              │
│  8. SystemHealthDashboard shows all service status                           │
│     └── Queries /api/health/full for detailed metrics                        │
│                                                                              │
│  🔄 The cycle repeats, with the system getting smarter every iteration       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Troubleshooting Agents (NEW - January 2026)

### Documentation
- `docs/09-troubleshooting-incidentes/connection_pool_issues.md`: **Troubleshooting Database**. Central registry of all known issues, root causes, and solutions. **READ THIS FIRST when debugging**.

### Diagnostic Flow
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SYSTEMATIC DEBUGGING WORKFLOW                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. SYMPTOM OBSERVED (e.g., backend stops responding)                        │
│     └── Document in troubleshooting doc                                      │
│                                                                              │
│  2. CHECK LOGS                                                               │
│     └── logs/app.jsonl for errors                                            │
│     └── Look for: pool.nearly_exhausted, error levels                        │
│                                                                              │
│  3. IDENTIFY ROOT CAUSE                                                      │
│     └── Pool exhaustion? → check getconn vs putconn count                    │
│     └── Connection error? → check Azure PostgreSQL firewall                  │
│     └── Missing table? → check ensure_*_table functions                      │
│                                                                              │
│  4. APPLY FIX                                                                │
│     └── Document in troubleshooting doc                                      │
│     └── Add to CLAUDE.md common issues table                                 │
│                                                                              │
│  5. VERIFY FIX                                                               │
│     └── Restart backend                                                      │
│     └── Reproduce original issue                                             │
│     └── Confirm resolved                                                     │
│                                                                              │
│  6. UPDATE DOCUMENTATION                                                     │
│     └── Add to troubleshooting doc with date                                 │
│     └── Update CLAUDE.md if needed                                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Monitoring Points
| Component | Log Pattern | Action if Critical |
|-----------|-------------|-------------------|
| Connection Pool | `pool.nearly_exhausted` | Restart backend |
| Auth | `auth.login` errors | Check users table |
| Projects | `project.deleted` | Verify pg_proyectos count |
| Queries | `statement timeout` | Optimize slow queries |

---

*Documento actualizado: Enero 2026*
