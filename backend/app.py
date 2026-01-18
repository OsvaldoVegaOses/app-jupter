"""
Aplicación principal FastAPI - API REST para análisis cualitativo.

Este es el punto de entrada del servidor HTTP que expone ~54 endpoints
para interactuar con el sistema de análisis cualitativo GraphRAG.

Grupos de endpoints:
    
    /token
        - POST: Obtener JWT token (login)
    
    /health
        - GET: Health check del servicio
    
    /api/projects
        - GET: Listar proyectos
        - POST: Crear nuevo proyecto
    
    /api/status/{project}
        - GET: Estado del proyecto (etapas completadas)
    
    /api/ingest
        - POST: Ingestar documentos DOCX
    
    /api/analyze
        - POST: Ejecutar análisis LLM
        - POST /persist: Persistir resultados de análisis
        - GET /task/{id}: Estado de tarea Celery
    
    /api/neo4j
        - POST /query: Ejecutar consulta Cypher
        - POST /export: Exportar resultados (CSV/JSON)

    /api/axial
        - POST /gds: Ejecutar algoritmos GDS (Louvain/PageRank/Betweenness)
    
    /api/coding
        - POST /assign: Asignar código a fragmento
        - POST /suggest: Sugerir fragmentos similares
        - GET /stats: Estadísticas de codificación
        - GET /codes: Lista de códigos
        - GET /fragments: Fragmentos por archivo
        - GET /citations: Citas por código

    /api/interviews
        - GET: Lista de entrevistas (archivos) por proyecto
    
    /api/search
        - POST /discover: Búsqueda conceptual con ejemplos
        - POST /similar: Fragmentos similares
    
Autenticación:
    Todos los endpoints (excepto /health y /token) requieren:
    - Authorization: Bearer <jwt_token>
    - O: X-API-Key: <api_key>

Dependencias FastAPI:
    - get_settings(): Carga configuración (cacheada)
    - get_clients(): Construye ServiceClients
    - get_neo4j_clients(): Clientes solo para Neo4j
    - require_auth(): Valida autenticación

Configuración CORS:
    Permite todos los orígenes (*) para desarrollo.
    En producción, restringir a dominios específicos.

Logging:
    - Estructlog para logging JSON
    - Eventos: api.request, api.error, etc.

Ejecución:
    uvicorn backend.app:app --reload --port 8000
"""

from __future__ import annotations

import os
import json
import uuid
import asyncio
from collections import Counter
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from functools import lru_cache
from io import StringIO
from pathlib import Path
import tempfile
from time import perf_counter
from typing import Any, Dict, List, Optional, Tuple, Union, cast, LiteralString

import structlog
from pydantic import BaseModel, ConfigDict, Field
import openai

try:
    from fastapi import Depends, FastAPI, HTTPException, Header, Query, Body, status, BackgroundTasks  # type: ignore[import]
    from fastapi.middleware.cors import CORSMiddleware  # type: ignore[import]
    from fastapi.responses import JSONResponse, PlainTextResponse, Response, FileResponse  # type: ignore[import]
except ImportError as exc:  # pragma: no cover - surface a clearer message when FastAPI is missing
    raise RuntimeError(
        "FastAPI is required to run the backend service. Install it with `pip install fastapi`."
    ) from exc

from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from datetime import datetime, timedelta
from backend.auth import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, User, get_current_user, require_role
from backend.celery_worker import task_analyze_interview, celery_app
from backend.routers.ingest import IngestRequest
from celery.result import AsyncResult

from neo4j import GraphDatabase, Driver  # type: ignore[import]
from neo4j import Query as Neo4jQuery  # Renamed to avoid collision with fastapi.Query

from app.analysis import analyze_interview_text, persist_analysis, matriz_etapa3, matriz_etapa4, modelo_ascii
from app.clients import (
    ServiceClients,
    build_service_clients,
    get_pg_connection,
    return_pg_connection,
    PGConnection,
)
from app.postgres_block import stage0_require_ready_or_override
from app.coding import (
    assign_open_code,
    citations_for_code,
    coding_statistics,
    export_codes_maxqda_csv,
    export_codes_refi_qda,
    fetch_code_history,
    fetch_fragment_context,
    find_similar_codes,
    get_saturation_data,
    list_available_interviews,
    list_available_interviews_with_ranking_debug,
    list_interview_fragments,
    list_open_codes,
    suggest_similar_fragments,
    unassign_open_code,
    CodingError,
)
from app.axial import run_gds_analysis, AxialError
from app.documents import load_fragments
from app.ingestion import ingest_documents
from app.project_state import (
    DEFAULT_PROJECT,
    create_project,
    detect_stage_status,
    list_projects,
    mark_stage,
    resolve_project,
    get_project_config,
    update_project_config,
    update_project_details,
)
from app.queries import run_cypher, sample_postgres
from app.settings import AppSettings, load_settings
from app.logging_config import configure_logging
from app.qdrant_block import discover_search, search_similar
from app.embeddings import embed_batch
from app.postgres_block import (
    ensure_candidate_codes_table,
    ensure_open_coding_table,
    ensure_axial_table,
    coding_stats,
    insert_candidate_codes,
    list_candidate_codes,
    validate_candidate,
    reject_candidate,
    merge_candidates,
    promote_to_definitive,
    get_candidate_stats_by_source,
    get_canonical_examples,
    get_backlog_health,
    get_dashboard_counts,
    add_project_member,
)

from qdrant_client.models import ContextExamplePair, FieldCondition, Filter, FilterSelector, MatchValue
from qdrant_client import models
from main import STAGE_DEFINITIONS, STAGE_ORDER

# Backend routers - ALL 7 ROUTERS
from backend.routers.admin import router as admin_router, health_router
from backend.routers.auth import router as auth_router, oauth_router, legacy_router as auth_legacy_router
from backend.routers.neo4j import router as neo4j_router
from backend.routers.discovery import router as discovery_router, qdrant_router
from backend.routers.graphrag import graphrag_router, axial_router
from backend.routers.coding import router as coding_router, codes_router
from backend.routers.dashboard import router as dashboard_router
from backend.routers.ingest import router as ingest_router
from backend.routers.interviews import router as interviews_router
from backend.routers.familiarization import router as familiarization_router
from backend.routers.agent import router as agent_router  # Autonomous Agent
from backend.routers.stage0 import router as stage0_router


# Initialize Logging (honor env override for verbosity)
configure_logging(os.getenv("LOG_LEVEL", "INFO").upper())


ALLOWED_FORMATS = {"raw", "table", "graph"}
DEFAULT_FORMATS = ["raw"]
ENV_FILE_VAR = "APP_ENV_FILE"
API_KEY_HEADER = "X-API-Key"

logger = structlog.get_logger("neo4j.api")
api_logger = structlog.get_logger("app.api")

# Load .env early so that any import-time code that reads os.getenv() sees values.
# Honor APP_ENV_FILE if set; otherwise try to locate a .env in the cwd, then fall
# back to the repo root (so reloads don't lose config due to cwd changes).
try:
    from dotenv import load_dotenv, find_dotenv

    _env_file = os.getenv(ENV_FILE_VAR) or find_dotenv(usecwd=True)
    if not _env_file:
        try:
            from pathlib import Path

            candidate = Path(__file__).resolve().parents[1] / ".env"
            if candidate.exists():
                _env_file = str(candidate)
        except Exception:
            _env_file = None
    if _env_file:
        try:
            load_dotenv(_env_file)
        except Exception:
            # best-effort: failures here shouldn't crash the API import
            logger.debug("failed_to_load_env_file", env_file=str(_env_file))
except Exception:
    # dotenv not installed or other error — proceed; load_settings will still attempt to load later
    pass


class CypherRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cypher: str = Field(..., description="Consulta Cypher a ejecutar en Neo4j.")
    project: Optional[str] = Field(
        default=None, description="Proyecto requerido para la consulta."
    )
    params: Optional[Dict[str, Any]] = Field(
        default=None, description="Diccionario de parámetros (clave->valor)."
    )
    database: Optional[str] = Field(
        default=None, description="Base de datos Neo4j opcional."
    )
    formats: Optional[List[str]] = Field(
        default=None, description="Formatos de respuesta requeridos (raw, table, graph)."
    )


class GDSRequest(BaseModel):
    algorithm: str = Field(..., pattern="^(louvain|pagerank|betweenness)$")
    persist: bool = False

    formats: Optional[List[str]] = Field(
        default=None,
        description="Lista de formatos a devolver (raw, table, graph, all).",
    )


class MaintenanceDeleteFileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: str = Field(..., description="Proyecto (nombre lógico).")
    file: str = Field(..., min_length=1, description="Nombre de archivo de entrevista (e.g. .docx).")





class CodeSuggestionRequest(BaseModel):
    fragment_text: str = Field(..., description="Texto del fragmento a analizar")
    limit: int = Field(5, ge=1, le=20)

    database: Optional[str] = Field(
        default=None, description="Base de datos Neo4j opcional."
    )


class AnalyzeHiddenRelationshipsRequest(BaseModel):
    """Request para análisis IA de relaciones ocultas."""
    model_config = ConfigDict(extra="forbid")
    project: str = Field(default="default", description="ID del proyecto")
    suggestions: List[Dict[str, Any]] = Field(..., description="Relaciones ocultas sugeridas")


class HiddenRelationshipsMetricsRequest(BaseModel):
    """Request para métricas de diversidad/overlap en relaciones ocultas."""
    model_config = ConfigDict(extra="forbid")
    project: str = Field(default="default", description="ID del proyecto")
    suggestions: List[Dict[str, Any]] = Field(..., description="Relaciones ocultas sugeridas")



class CypherResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Filas en formato raw (dict por registro)."
    )
    table: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Vista tabular con columnas y filas.",
    )
    graph: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Nodos y relaciones en formato de grafo.",
    )


app = FastAPI(title="Neo4j Query API", version="1.0.0")

# CORS NOTE:
# - Browsers will *reject* responses when `Access-Control-Allow-Origin` is missing.
# - Using `allow_origins=["*"]` together with `allow_credentials=True` is an invalid combination
#   per the CORS spec and will often cause the middleware to omit the header.
#
# Configure via `CORS_ALLOW_ORIGINS` (comma-separated). Default targets local dev frontends.
_cors_allow_origins_raw = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
if _cors_allow_origins_raw:
    _cors_allow_origins = [o.strip() for o in _cors_allow_origins_raw.split(",") if o.strip()]
    _cors_allow_origin_regex = os.getenv("CORS_ALLOW_ORIGIN_REGEX", "").strip() or None
else:
    _cors_allow_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    # Dev-friendly: allow any localhost/127.0.0.1 port (covers Vite auto-fallback 5174, 5175, etc.)
    _cors_allow_origin_regex = r"^https?://(localhost|127\.0\.0\.1)(:\\d+)?$"

_cors_allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "true").strip().lower() in {
    "1",
    "true",
    "yes",
}
if "*" in _cors_allow_origins and _cors_allow_credentials:
    # Prevent a misconfiguration that results in missing CORS headers.
    _cors_allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins,
    allow_origin_regex=_cors_allow_origin_regex,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include ALL routers - REFACTORING 100% COMPLETE
app.include_router(health_router)       # /healthz endpoint
app.include_router(admin_router)        # /api/* admin + insights
app.include_router(dashboard_router)    # /api/status, /api/dashboard/*
app.include_router(oauth_router)        # /token OAuth2 endpoint
app.include_router(auth_router)         # /api/auth/* endpoints
app.include_router(auth_legacy_router)  # /register, /refresh legacy endpoints
app.include_router(neo4j_router)        # /api/neo4j/* endpoints
app.include_router(qdrant_router)       # /api/qdrant/* endpoints  
app.include_router(discovery_router)    # /api/discovery/* endpoints
app.include_router(graphrag_router)     # /api/graphrag/* endpoints
app.include_router(axial_router)        # /api/axial/* endpoints
app.include_router(coding_router)       # /api/coding/* endpoints
app.include_router(codes_router)        # /api/codes/* endpoints
app.include_router(ingest_router)       # /api/ingest, /api/upload-and-ingest, /api/transcribe/*
app.include_router(interviews_router)   # /api/interviews/* (decoupled pipeline)
app.include_router(familiarization_router)  # /api/familiarization/reviews
app.include_router(agent_router)        # /api/agent/* (autonomous agent)
app.include_router(stage0_router)       # /api/stage0/* (Etapa 0: Preparación)


# =============================================================================
# RATE LIMITING con Redis
# =============================================================================

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import Request

# Configurar limiter con Redis (usa el mismo que Celery)
REDIS_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=REDIS_URL,
    default_limits=["100/minute"],  # Límite general
)
app.state.limiter = limiter


async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> Response:
    """Wrapper que satisface FastAPI typing y delega en slowapi."""
    if isinstance(exc, RateLimitExceeded):
        return _rate_limit_exceeded_handler(request, exc)
    raise exc


app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


# =============================================================================
# REQUEST ID MIDDLEWARE (Observability)
# =============================================================================

import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware

class RequestIdMiddleware(BaseHTTPMiddleware):
    """Adds unique request_id to each request for tracing/debugging."""
    
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        session_id = request.headers.get("X-Session-ID") or request.query_params.get("session_id")
        project_id = (
            request.headers.get("X-Project-ID")
            or request.query_params.get("project")
            or request.query_params.get("project_id")
        )
        start = perf_counter()
        
        # Bind request_id to structlog context
        structlog.contextvars.clear_contextvars()
        bind_payload = {"request_id": request_id}
        if session_id:
            bind_payload["session_id"] = session_id
        if project_id:
            bind_payload["project_id"] = project_id
        structlog.contextvars.bind_contextvars(**bind_payload)
        
        # Store in request state for endpoint access
        request.state.request_id = request_id
        if session_id:
            request.state.session_id = session_id
        if project_id:
            request.state.project_id = project_id
        
        # Log request start
        api_logger.info(
            "request.start",
            method=request.method,
            path=str(request.url.path),
            request_id=request_id,
        )
        
        response = await call_next(request)
        
        # Add request_id to response headers
        response.headers["X-Request-ID"] = request_id
        
        duration_ms = (perf_counter() - start) * 1000

        # Log request end
        api_logger.info(
            "request.end",
            method=request.method,
            path=str(request.url.path),
            status_code=response.status_code,
            request_id=request_id,
            duration_ms=round(duration_ms, 2),
        )

        if duration_ms >= 5000:
            api_logger.warning(
                "request.slow",
                method=request.method,
                path=str(request.url.path),
                request_id=request_id,
                duration_ms=round(duration_ms, 2),
            )
        
        return response

app.add_middleware(RequestIdMiddleware)


# =============================================================================
# NOTA: Los endpoints de autenticación están definidos después de get_settings
# en las líneas 700+. Ver:
# - POST /api/auth/login  (JSON)
# - POST /api/auth/register  (JSON)
# - POST /api/auth/refresh
# - POST /token (OAuth2 form-data)
# - POST /register
# =============================================================================


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    env_file = os.getenv(ENV_FILE_VAR)
    if not env_file:
        try:
            from pathlib import Path

            candidate = Path(__file__).resolve().parents[1] / ".env"
            if candidate.exists():
                env_file = str(candidate)
        except Exception:
            env_file = None
    return load_settings(env_file)


@dataclass
class Neo4jOnlyClients:
    neo4j: Driver

    def close(self) -> None:
        try:
            self.neo4j.close()
        except Exception:
            pass


def build_neo4j_only(settings: AppSettings) -> Neo4jOnlyClients:
    driver = GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.username, settings.neo4j.password or ""),
    )
    return Neo4jOnlyClients(neo4j=driver)


@dataclass
class PgOnlyClients:
    postgres: PGConnection

    def close(self) -> None:
        try:
            return_pg_connection(self.postgres)
        except Exception:
            pass


def build_pg_only(settings: AppSettings) -> PgOnlyClients:
    return PgOnlyClients(postgres=get_pg_connection(settings))


def build_clients_or_error(settings: AppSettings) -> ServiceClients:
    try:
        return build_service_clients(settings)
    except Exception as exc:  # noqa: BLE001
        from app.error_handling import api_error, ErrorCode
        raise api_error(
            status_code=502,
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Error conectando con servicios externos. Intente más tarde.",
            exc=exc,
        ) from exc


def _normalize_formats(values: Optional[List[str]]) -> List[str]:
    if not values:
        return DEFAULT_FORMATS.copy()
    normalized: List[str] = []
    for entry in values:
        fmt = (entry or "").strip().lower()
        if fmt == "all":
            return list(ALLOWED_FORMATS)
        if fmt not in ALLOWED_FORMATS:
            raise ValueError(
                f"Formato '{entry}' no soportado. Usa un formato válido: raw, table, graph o all."
            )
        if fmt not in normalized:
            normalized.append(fmt)
    if not normalized:
        raise ValueError("Debe especificar al menos un formato válido (raw, table, graph, all).")
    return normalized


async def get_clients(
    settings: AppSettings = Depends(get_settings),
) -> AsyncGenerator[ServiceClients, None]:
    clients = build_clients_or_error(settings)
    try:
        yield clients
    finally:
        clients.close()



async def require_auth(
    user: User = Depends(get_current_user),
) -> User:
    return user


@app.post("/api/axial/analyze-hidden-relationships")
async def api_analyze_hidden_relationships(
    payload: Optional[AnalyzeHiddenRelationshipsRequest] = Body(default=None),
    payload_q: Optional[str] = Query(default=None, alias="payload"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Analiza relaciones ocultas con IA.

    Devuelve memo estructurado con estatus epistemológico.
    """
    from app.clients import build_service_clients

    if payload is None and payload_q:
        try:
            payload = AnalyzeHiddenRelationshipsRequest.model_validate_json(payload_q)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid payload JSON") from exc
    if payload is None:
        raise HTTPException(status_code=422, detail="Missing request body")

    clients = build_service_clients(settings)
    try:
        suggestions_text = []
        for i, sug in enumerate(payload.suggestions[:10], 1):
            source = sug.get("source", "?")
            target = sug.get("target", "?")
            score = sug.get("score", 0)
            reason = sug.get("reason", "")
            evidence = sug.get("evidence_ids") or []
            evid_txt = f" evidencias={len(evidence)}" if isinstance(evidence, list) else ""
            suggestions_text.append(
                f"{i}. {source} ↔ {target} (score: {score:.3f}) {reason}{evid_txt}".strip()
            )

        prompt = f"""Analiza las siguientes relaciones ocultas detectadas en un grafo de análisis cualitativo (Teoría Fundamentada).

Sugerencias de relaciones ocultas (IDs 1..{min(len(payload.suggestions), 10)}):
{chr(10).join(suggestions_text)}

Contexto: estas relaciones son hipótesis y requieren validación humana con evidencia.

IMPORTANTE: Responde ÚNICAMENTE con un JSON válido (sin markdown, sin ```).
La síntesis debe distinguir explícitamente el estatus epistemológico de cada afirmación.
El JSON debe tener esta estructura exacta:

{{
    "memo_sintesis": [
        {{"type": "OBSERVATION", "text": "...", "evidence_ids": [1, 3]}},
        {{"type": "INTERPRETATION", "text": "...", "evidence_ids": [1, 3]}},
        {{"type": "HYPOTHESIS", "text": "...", "evidence_ids": [2]}},
        {{"type": "NORMATIVE_INFERENCE", "text": "...", "evidence_ids": [4]}}
    ]
}}

REGLAS:
1. memo_sintesis: lista de 3-6 statements.
2. type: uno de OBSERVATION | INTERPRETATION | HYPOTHESIS | NORMATIVE_INFERENCE.
3. text: una oración clara (español).
4. evidence_ids: lista de enteros referidos a la numeración de las sugerencias (1..10).
5. PROHIBIDO: OBSERVATION sin evidence_ids no vacíos.
6. Sé conciso: evita listas largas o párrafos extensos."""

        response = clients.aoai.chat.completions.create(
            model=settings.azure.deployment_chat,
            messages=[
                {"role": "system", "content": "Eres un experto en análisis cualitativo y Teoría Fundamentada."},
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=600,
        )

        choice = response.choices[0] if response.choices else None
        message = getattr(choice, "message", None)
        message_content = getattr(message, "content", None)
        raw_content = message_content or ""

        import json
        import re

        parsed: Optional[Dict[str, Any]] = None
        try:
            clean_content = re.sub(r"^```json?\s*", "", raw_content.strip())
            clean_content = re.sub(r"\s*```$", "", clean_content)
            parsed = json.loads(clean_content)
        except Exception:
            parsed = None

        def _normalize_memo(value: Any) -> tuple[str, List[Dict[str, Any]]]:
            allowed = {"OBSERVATION", "INTERPRETATION", "HYPOTHESIS", "NORMATIVE_INFERENCE"}
            if isinstance(value, str):
                return value.strip(), []
            if not isinstance(value, list):
                return "", []
            out: List[Dict[str, Any]] = []
            lines: List[str] = []
            for item in value:
                if not isinstance(item, dict):
                    continue
                stype = str(item.get("type") or "").strip().upper()
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                if stype not in allowed:
                    stype = "INTERPRETATION"
                evidence_ids: List[int] = []
                raw_ids = item.get("evidence_ids")
                if isinstance(raw_ids, list):
                    for v in raw_ids:
                        try:
                            evidence_ids.append(int(v))
                        except Exception:
                            continue
                if stype == "OBSERVATION" and not evidence_ids:
                    stype = "INTERPRETATION"
                entry: Dict[str, Any] = {"type": stype, "text": text}
                if evidence_ids:
                    entry["evidence_ids"] = evidence_ids
                    lines.append(f"[{stype}] {text} (evid: {', '.join(str(i) for i in evidence_ids)})")
                else:
                    lines.append(f"[{stype}] {text}")
                out.append(entry)
            return "\n".join(lines).strip(), out

        if isinstance(parsed, dict) and parsed.get("memo_sintesis") is not None:
            memo_text, memo_statements = _normalize_memo(parsed.get("memo_sintesis"))
            analysis = memo_text
            structured = True
        else:
            analysis = raw_content
            structured = False
            memo_statements = []

        return {
            "analysis": analysis,
            "structured": structured,
            "memo_statements": memo_statements,
            "suggestions_analyzed": len(payload.suggestions[:10]),
        }
    except Exception as exc:
        api_logger.error("api.analyze_hidden_relationships.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()


@app.post("/api/axial/hidden-relationships/metrics")
async def api_hidden_relationships_metrics(
    payload: Optional[HiddenRelationshipsMetricsRequest] = Body(default=None),
    payload_q: Optional[str] = Query(default=None, alias="payload"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Calcula métricas de diversidad/overlap para relaciones ocultas."""
    try:
        if payload is None and payload_q:
            try:
                payload = HiddenRelationshipsMetricsRequest.model_validate_json(payload_q)
            except Exception as exc:
                raise HTTPException(status_code=400, detail="Invalid payload JSON") from exc
        if payload is None:
            raise HTTPException(status_code=422, detail="Missing request body")
        from backend.routers.agent import _compute_evidence_diversity_metrics

        codes_with_fragments = []
        suggestions_total = 0
        suggestions_with_direct_evidence = 0
        suggestions_with_any_evidence = 0
        for sug in payload.suggestions:
            suggestions_total += 1
            source = str(sug.get("source") or "?")
            target = str(sug.get("target") or "?")
            key = f"{source}↔{target}"
            evidence_ids = sug.get("evidence_ids") or []
            supporting_ids = sug.get("supporting_evidence_ids") or []
            has_direct = isinstance(evidence_ids, list) and len([v for v in evidence_ids if v]) > 0
            has_supporting = isinstance(supporting_ids, list) and len([v for v in supporting_ids if v]) > 0
            if has_direct:
                suggestions_with_direct_evidence += 1
            if has_direct or has_supporting:
                suggestions_with_any_evidence += 1
            fragments = [{"fragmento_id": fid} for fid in evidence_ids if fid]
            codes_with_fragments.append({"code": key, "fragments": fragments})

        metrics = _compute_evidence_diversity_metrics(codes_with_fragments)
        metrics["suggestions_total"] = suggestions_total
        metrics["suggestions_with_direct_evidence"] = suggestions_with_direct_evidence
        metrics["direct_evidence_ratio"] = (
            (suggestions_with_direct_evidence / suggestions_total) if suggestions_total else 0.0
        )
        metrics["suggestions_with_any_evidence"] = suggestions_with_any_evidence
        metrics["any_evidence_ratio"] = (
            (suggestions_with_any_evidence / suggestions_total) if suggestions_total else 0.0
        )
        return {
            "project": payload.project,
            "metrics": metrics,
        }
    except Exception as exc:
        api_logger.error("api.hidden_relationships.metrics_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_service_clients(
    settings: AppSettings = Depends(get_settings),
) -> AsyncGenerator[ServiceClients, None]:
    """
    Dependency that provides ServiceClients with automatic cleanup.
    
    Usage:
        @app.get("/api/endpoint")
        async def handler(clients: ServiceClients = Depends(get_service_clients)):
            # Use clients.postgres, clients.qdrant, etc.
            # No need to call clients.close() - FastAPI handles it!
    """
    import structlog
    _dep_logger = structlog.get_logger("app.deps")
    
    clients = build_service_clients(settings)
    _dep_logger.info("deps.get_service_clients.yield_start")
    try:
        yield clients
    finally:
        _dep_logger.info("deps.get_service_clients.finally_executing")
        clients.close()


async def get_pg_clients(
    settings: AppSettings = Depends(get_settings),
) -> AsyncGenerator[PgOnlyClients, None]:
    clients = build_pg_only(settings)
    try:
        yield clients
    finally:
        clients.close()


async def run_pg_query_with_timeout(func, *args, timeout: float = 12.0, **kwargs):
    """Execute a blocking PG helper in a worker thread with a hard timeout.

    Prevents the UI from hanging when Postgres is slow or unreachable by
    returning a 504 instead of letting the client-side 30s timeout fire.
    """
    try:
        return await asyncio.wait_for(asyncio.to_thread(func, *args, **kwargs), timeout=timeout)
    except asyncio.TimeoutError as exc:  # pragma: no cover - network timing
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="PostgreSQL query timed out",
        ) from exc


async def get_neo4j_clients(
    settings: AppSettings = Depends(get_settings),
) -> AsyncGenerator[Neo4jOnlyClients, None]:
    clients = build_neo4j_only(settings)
    try:
        yield clients
    finally:
        clients.close()



# =============================================================================
# DEPRECATED: Authentication endpoints moved to backend.routers.auth
# =============================================================================
# OLD ENDPOINTS - COMMENTED OUT
# - POST /token → oauth_router
# - POST /api/auth/login → auth_router
# - POST /api/auth/register → auth_router
# - POST /refresh → auth_legacy_router
# - POST /register → auth_legacy_router

# @app.post("/token")
# async def api_login_oauth(...
# [Lines 398-565 commented out - All auth endpoints moved to backend.routers.auth]

# async def api_login_json(
#     request: Dict[str, Any] = Body(...),
#     clients: ServiceClients = Depends(get_service_clients),
# ):
#     """
#     Login de usuario con JSON - genera access token y refresh token.
    
#     El frontend envía JSON en lugar de form-data.
#     """
#     from backend.auth_service import authenticate_user, create_tokens_for_user
    
#     email = request.get("email", "")
#     password = request.get("password", "")
    
#     if not email or not password:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Email y password son requeridos",
#         )
    
#     user, error = authenticate_user(clients.postgres, email, password)
    
#     if error:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail=error,
#             headers={"WWW-Authenticate": "Bearer"},
#         )
    
#     try:
#         tokens = create_tokens_for_user(clients.postgres, user)
#     except Exception as e:
#         api_logger.error("auth.login.token_error", error=str(e))
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Error generando tokens",
#         )
    
#     api_logger.info("auth.login.json.success", user_id=user["id"], email=user["email"])
    
#     return {
#         "access_token": tokens.access_token,
#         "refresh_token": tokens.refresh_token,
#         "token_type": tokens.token_type,
#         "expires_in": tokens.expires_in,
#         "user": {
#             "id": user["id"],
#             "email": user["email"],
#             "full_name": user.get("full_name"),
#             "organization_id": user.get("organization_id", "default_org"),
#             "role": user.get("role", "analyst"),
#         }
#     }


# @app.post("/register")
# @app.post("/api/auth/register")
# async def api_register(
#     request: Dict[str, Any] = Body(...),
#     clients: ServiceClients = Depends(get_service_clients),
# ):
#     """
#     Registro de nuevo usuario.
    
#     Campos requeridos:
#     - email: Email válido
#     - password: Mínimo 8 caracteres, debe incluir mayúscula, minúscula, número y símbolo
    
#     Campos opcionales:
#     - full_name: Nombre completo
#     - organization_id: ID de organización (default: "default_org")
#     """
#     from backend.auth_service import RegisterRequest, register_user, create_tokens_for_user
    
#     try:
#         reg_request = RegisterRequest(
#             email=request.get("email", ""),
#             password=request.get("password", ""),
#             full_name=request.get("full_name"),
#             organization_id=request.get("organization_id", "default_org"),
#         )
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail=str(e),
#         )
    
#     user, error = register_user(clients.postgres, reg_request)
    
#     if error:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail=error,
#         )
    
#     # Generar tokens automáticamente después del registro
#     try:
#         tokens = create_tokens_for_user(clients.postgres, user)
#     except Exception as e:
#         # Usuario creado pero error en tokens - retornar solo confirmación
#         api_logger.warning("auth.register.token_error", user_id=user["id"], error=str(e))
#         return {
#             "message": "Usuario registrado. Por favor inicia sesión.",
#             "user_id": user["id"],
#         }
    
#     api_logger.info("auth.register.success", user_id=user["id"], email=user["email"])
    
#     return {
#         "message": "Usuario registrado exitosamente",
#         "user_id": user["id"],
#         "access_token": tokens.access_token,
#         "refresh_token": tokens.refresh_token,
#         "token_type": tokens.token_type,
#         "user": {
#             "id": user["id"],
#             "email": user["email"],
#             "full_name": user.get("full_name"),
#             "organization_id": user.get("organization_id", "default_org"),
#             "role": user.get("role", "analyst"),
#         }
#     }


# @app.post("/refresh")
# @app.post("/api/auth/refresh")
# async def api_refresh_token(
#     request: Dict[str, Any] = Body(...),
#     clients: ServiceClients = Depends(get_service_clients),
# ):
#     """
#     Renueva access token usando refresh token.
#     """
#     from backend.auth_service import refresh_access_token
    
#     refresh_token = request.get("refresh_token")
#     if not refresh_token:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="refresh_token es requerido",
#         )
    
#     tokens, error = refresh_access_token(clients.postgres, refresh_token)
    
#     if error:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail=error,
#         )
    
#     return {
#         "access_token": tokens["access_token"],
#         "refresh_token": tokens["refresh_token"],
#         "token_type": "bearer",
#     }

# End of deprecated auth endpoints
# =============================================================================


# =============================================================================
# DEPRECATED: Neo4j endpoints moved to backend.routers.neo4j
# =============================================================================
# OLD ENDPOINTS - COMMENTED OUT
# - POST /api/neo4j/query → neo4j_router
# - POST /api/neo4j/export → neo4j_router
# - Helper functions: _execute_cypher, _table_to_csv

# [Lines 575-740 commented out - All Neo4j endpoints and helpers moved to backend.routers.neo4j]

# End of deprecated Neo4j endpoints
# =============================================================================
def _execute_cypher(
    payload: CypherRequest,
    settings: AppSettings,
    run_callable,
) -> Tuple[Dict[str, Any], float]:
    if not payload.project:
        raise HTTPException(status_code=400, detail="El proyecto es obligatorio para consultas Neo4j.")
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        formats = _normalize_formats(payload.formats)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    database = payload.database or settings.neo4j.database
    start = perf_counter()
    try:
        result = run_callable(
            payload.cypher,
            params=payload.params or {},
            database=database,
        )
    except HTTPException as exc:
        duration_ms = (perf_counter() - start) * 1000
        logger.warning(
            "neo4j.query.http_error",
            duration_ms=duration_ms,
            database=database,
            error=exc.detail,
        )
        raise
    except ValueError as exc:
        duration_ms = (perf_counter() - start) * 1000
        logger.warning(
            "neo4j.query.validation_error",
            duration_ms=duration_ms,
            database=database,
            error=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - unexpected errors
        duration_ms = (perf_counter() - start) * 1000
        logger.error(
            "neo4j.query.failure",
            duration_ms=duration_ms,
            database=database,
            error=str(exc),
        )
        raise HTTPException(status_code=502, detail="Fallo al ejecutar la consulta en Neo4j.") from exc

    filtered = {fmt: result.get(fmt) for fmt in formats if fmt in result}
    duration_ms = (perf_counter() - start) * 1000
    logger.info(
        "neo4j.query.success",
        duration_ms=duration_ms,
        database=database,
        formats=formats,
        rows=len(filtered.get("raw") or []),
    )
    return filtered, duration_ms


def _table_to_csv(table: Dict[str, Any]) -> str:
    columns = table.get("columns") or []
    rows = table.get("rows") or []
    buffer = StringIO()
    if columns:
        buffer.write(",".join(str(column) for column in columns))
        buffer.write("\n")
        for row in rows:
            buffer.write(
                ",".join(
                    '"' + str(value).replace('"', '""') + '"'
                    if isinstance(value, str)
                    else ("" if value is None else str(value))
                    for value in row
                )
            )
            buffer.write("\n")
    return buffer.getvalue()


class CypherExportRequest(CypherRequest):
    export_format: str = Field(
        default="csv",
        description="Formato de exporte (csv o json).",
        pattern="^(csv|json)$",
    )


@app.post("/api/neo4j/query", response_model=CypherResponse)
async def neo4j_query(
    payload: CypherRequest,
    settings: AppSettings = Depends(get_settings),
    clients: Neo4jOnlyClients = Depends(get_neo4j_clients),
    user: User = Depends(require_auth),
) -> Any:
    result, duration_ms = _execute_cypher(
        payload,
        settings,
        lambda cypher, params, database: run_cypher(
            cast(ServiceClients, clients),
            cypher,
            params=params,
            database=database,
        ),
    )
    response = JSONResponse(result)
    response.headers["X-Query-Duration"] = f"{duration_ms:.2f}"
    return response


@app.post("/api/neo4j/export")
async def neo4j_export(
    payload: CypherExportRequest,
    settings: AppSettings = Depends(get_settings),
    clients: Neo4jOnlyClients = Depends(get_neo4j_clients),
    user: User = Depends(require_auth),
):
    export_format = payload.export_format.lower()
    requested_formats = payload.formats
    if export_format == "csv":
        requested_formats = ["table"]
    query_payload = CypherRequest(
        cypher=payload.cypher,
        params=payload.params,
        formats=requested_formats,
        database=payload.database,
    )
    result, duration_ms = _execute_cypher(
        query_payload,
        settings,
        lambda cypher, params, database: run_cypher(
            cast(ServiceClients, clients),
            cypher,
            params=params,
            database=database,
        ),
    )
    database_name = query_payload.database or settings.neo4j.database
    if export_format == "csv":
        table = result.get("table")
        if not table:
            raise HTTPException(status_code=400, detail="La consulta no generó datos tabulares para exportar.")
        csv_body = _table_to_csv(table)
        response = PlainTextResponse(
            csv_body,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="neo4j_export.csv"'},
        )
        logger.info(
            "neo4j.export.success",
            duration_ms=duration_ms,
            database=database_name,
            export_format="csv",
        )
    else:
        response = JSONResponse(result)
        logger.info(
            "neo4j.export.success",
            duration_ms=duration_ms,
            database=database_name,
            export_format="json",
        )
    response.headers["X-Query-Duration"] = f"{duration_ms:.2f}"
    return response


# DEPRECATED: Moved to backend.routers.admin.health_router
# @app.get("/healthz")
# async def healthcheck() -> Dict[str, str]:
#     return {"status": "ok"}


# ---------- Project & Status ----------


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: Optional[str] = None


# =============================================================================
# Registration Endpoints
# =============================================================================

# NOTA: El endpoint /register antiguo fue removido.
# El registro de usuarios se hace via /api/auth/register que usa PostgreSQL.



@app.get("/api/organizations")
async def api_list_organizations(
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Lista organizaciones (admin only)."""
    organizations: List[Dict[str, Any]] = []
    with clients.postgres.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT organization_id
            FROM app_users
            WHERE organization_id IS NOT NULL AND organization_id <> ''
            ORDER BY organization_id
            """
        )
        organizations = [
            {"id": row[0], "name": row[0]}
            for row in cur.fetchall()
            if row and row[0]
        ]
    return {"organizations": organizations}


# =============================================================================
# Project Endpoints (filtered by org_id)
# =============================================================================

@app.get("/api/projects")
async def api_projects(
    user: User = Depends(require_auth),
    settings: AppSettings = Depends(get_settings),
) -> Dict[str, Any]:
    """
    Lista proyectos filtrados por usuario/organización.
    
    - Admin: Ve todos los proyectos
    - Otros: Ve proyectos propios + proyectos de su org + proyectos legacy (sin owner)
    """
    from app.project_state import list_projects_for_user

    clients = build_clients_or_error(settings)
    
    try:
        # Usar función de filtrado que respeta owner_id y org_id
        filtered = list_projects_for_user(
            clients.postgres,
            user_id=user.user_id,
            org_id=user.organization_id,
            role=user.roles[0] if user.roles else "analyst",
        )
        return {"projects": filtered}
    finally:
        clients.close()



@app.post("/api/projects")
async def api_create_project(
    payload: ProjectCreateRequest,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Crea un proyecto asociado al usuario y su organización.
    
    El owner_id se asigna automáticamente al usuario que lo crea.
    """
    try:
        entry = create_project(
            clients.postgres,
            payload.name,
            payload.description,
            org_id=user.organization_id,
            owner_id=user.user_id,  # Asignar al usuario creador
        )
        # En multi-tenant estricto, el creador debe quedar como admin del proyecto.
        add_project_member(
            clients.postgres,
            entry.get("id"),
            user.user_id,
            "admin",
            added_by=user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    api_logger.info(
        "project.created",
        project_id=entry.get("id"),
        project_name=payload.name,
        user=user.user_id,
        org_id=user.organization_id,
    )
    return entry



@app.get("/api/projects/{project_id}/export")
async def api_export_project(
    project_id: str,
    settings: AppSettings = Depends(get_settings),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
):
    """
    Exporta un proyecto completo como archivo ZIP para backup.
    Incluye: config, fragmentos, códigos, reportes, notas.
    """
    import io
    import zipfile
    from fastapi.responses import StreamingResponse
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        export_data: Dict[str, Any] = {
            "project_id": project_id,
            "exported_at": datetime.now().isoformat(),
        }
        
        # 1. Project config (cloud-only: PostgreSQL)
        try:
            export_data["config"] = get_project_config(clients.postgres, project_id)
            zip_file.writestr(
                "project_config.json",
                json.dumps(export_data["config"], ensure_ascii=False, indent=2),
            )
        except Exception:
            pass
        
        # 2. PostgreSQL data
        try:
            with clients.postgres.cursor() as cur:
                # Fragments
                cur.execute(
                    "SELECT * FROM entrevista_fragmentos WHERE project_id = %s",
                    (project_id,)
                )
                columns = [desc[0] for desc in (cur.description or [])]
                fragments = [dict(zip(columns, row)) for row in cur.fetchall()]
                zip_file.writestr("fragments.json", json.dumps(fragments, default=str, ensure_ascii=False, indent=2))
                export_data["fragments_count"] = len(fragments)
                
                # Open codes
                cur.execute(
                    "SELECT * FROM analisis_codigos_abiertos WHERE project_id = %s",
                    (project_id,)
                )
                columns = [desc[0] for desc in (cur.description or [])]
                codes = [dict(zip(columns, row)) for row in cur.fetchall()]
                zip_file.writestr("open_codes.json", json.dumps(codes, default=str, ensure_ascii=False, indent=2))
                export_data["codes_count"] = len(codes)
                
                # Candidate codes
                try:
                    cur.execute(
                        "SELECT * FROM codigos_candidatos WHERE project_id = %s",
                        (project_id,)
                    )
                    columns = [desc[0] for desc in (cur.description or [])]
                    candidates = [dict(zip(columns, row)) for row in cur.fetchall()]
                    zip_file.writestr("candidate_codes.json", json.dumps(candidates, default=str, ensure_ascii=False, indent=2))
                except Exception:
                    pass
                
                # Interview reports
                try:
                    cur.execute(
                        "SELECT * FROM interview_reports WHERE project_id = %s",
                        (project_id,)
                    )
                    columns = [desc[0] for desc in (cur.description or [])]
                    reports = [dict(zip(columns, row)) for row in cur.fetchall()]
                    zip_file.writestr("interview_reports.json", json.dumps(reports, default=str, ensure_ascii=False, indent=2))
                except Exception:
                    pass
        except Exception as e:
            export_data["postgres_error"] = str(e)
        
        # 3. Neo4j graph data
        try:
            with clients.neo4j.session(database=settings.neo4j.database) as session:
                query = Neo4jQuery(
                    """
                    MATCH (n {project_id: $pid})
                    OPTIONAL MATCH (n)-[r]->(m {project_id: $pid})
                    RETURN labels(n) as labels, properties(n) as props,
                           type(r) as rel_type, properties(m) as target_props
                    """
                )
                result = session.run(query, pid=project_id)
                graph_data = [dict(record) for record in result]
                zip_file.writestr("neo4j_graph.json", json.dumps(graph_data, default=str, ensure_ascii=False, indent=2))
                export_data["neo4j_nodes"] = len(graph_data)
        except Exception as e:
            export_data["neo4j_error"] = str(e)
        
        # 4. Notes directory
        notes_dir = Path(f"notes/{project_id}")
        if notes_dir.exists():
            for file_path in notes_dir.rglob("*"):
                if file_path.is_file():
                    arcname = f"notes/{file_path.relative_to(notes_dir)}"
                    zip_file.write(file_path, arcname)
        
        # 5. Reports directory
        reports_dir = Path(f"reports/{project_id}")
        if reports_dir.exists():
            for file_path in reports_dir.rglob("*"):
                if file_path.is_file():
                    arcname = f"reports/{file_path.relative_to(reports_dir)}"
                    zip_file.write(file_path, arcname)
        
        # Write export manifest
        zip_file.writestr("_export_manifest.json", json.dumps(export_data, default=str, ensure_ascii=False, indent=2))
    
    zip_buffer.seek(0)
    
    api_logger.info("project.exported", project_id=project_id, user=user.user_id)
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{project_id}_backup.zip"'}
    )


@app.delete("/api/projects/{project_id}")
async def api_delete_project(
    project_id: str,
    settings: AppSettings = Depends(get_settings),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Elimina un proyecto y todos sus datos asociados:
    - Neo4j: nodos Fragmento, Entrevista, Codigo, Categoria
    - Qdrant: puntos con project_id
    - PostgreSQL: filas en tablas de análisis
    - Archivos: directorio del proyecto en data/projects/
    - Registry: (deshabilitado en modo cloud-only)
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    import shutil
    
    results = {"project_id": project_id, "deleted": {}}
    
    try:
        # 1. Neo4j cleanup
        try:
            with clients.neo4j.session(database=settings.neo4j.database) as session:
                delete_jobs = [
                    (
                        "fragmento",
                        Neo4jQuery(
                            cast(
                                LiteralString,
                                "MATCH (n:Fragmento {project_id: $pid}) DETACH DELETE n RETURN count(n) as deleted",
                            )
                        ),
                    ),
                    (
                        "entrevista",
                        Neo4jQuery(
                            cast(
                                LiteralString,
                                "MATCH (n:Entrevista {project_id: $pid}) DETACH DELETE n RETURN count(n) as deleted",
                            )
                        ),
                    ),
                    (
                        "codigo",
                        Neo4jQuery(
                            cast(
                                LiteralString,
                                "MATCH (n:Codigo {project_id: $pid}) DETACH DELETE n RETURN count(n) as deleted",
                            )
                        ),
                    ),
                    (
                        "categoria",
                        Neo4jQuery(
                            cast(
                                LiteralString,
                                "MATCH (n:Categoria {project_id: $pid}) DETACH DELETE n RETURN count(n) as deleted",
                            )
                        ),
                    ),
                ]
                for label_key, delete_query in delete_jobs:
                    result = session.run(delete_query, pid=project_id)
                    record = result.single()
                    deleted_count = record["deleted"] if record is not None else 0
                    results["deleted"][f"neo4j_{label_key}"] = deleted_count
        except Exception as e:
            results["deleted"]["neo4j_error"] = str(e)
        
        # 2. Qdrant cleanup
        try:
            clients.qdrant.delete(
                collection_name=settings.qdrant.collection,
                points_selector=Filter(
                    must=[FieldCondition(key="project_id", match=MatchValue(value=project_id))]
                ),
            )
            results["deleted"]["qdrant"] = "success"
        except Exception as e:
            results["deleted"]["qdrant_error"] = str(e)
        
        # 3. PostgreSQL cleanup
        try:
            tables = [
                "entrevista_fragmentos",
                "analisis_codigos_abiertos", 
                "analisis_axial",
                "analisis_comparacion_constante",
                "analisis_nucleo_notas",
                "interview_reports",
                "interview_files",  # New decoupled ingestion table
                "codigos_candidatos",  # Candidate codes validation table
            ]
            with clients.postgres.cursor() as cur:
                for table in tables:
                    try:
                        cur.execute(
                            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)",
                            (table,)
                        )
                        row = cur.fetchone()
                        if not row or not row[0]:
                            continue
                        cur.execute(f"DELETE FROM {table} WHERE project_id = %s", (project_id,))
                        results["deleted"][f"pg_{table}"] = cur.rowcount
                    except Exception:
                        clients.postgres.rollback()
                
                # IMPORTANT: Delete from proyectos table itself (this is why projects stay in list!)
                try:
                    cur.execute("DELETE FROM proyectos WHERE id = %s", (project_id,))
                    results["deleted"]["pg_proyectos"] = cur.rowcount
                except Exception as e:
                    results["deleted"]["pg_proyectos_error"] = str(e)
                    
            clients.postgres.commit()
        except Exception as e:
            results["deleted"]["postgres_error"] = str(e)
        
        # 4. Delete project files
        project_dir = Path(f"data/projects/{project_id}")
        if project_dir.exists():
            try:
                shutil.rmtree(project_dir)
                results["deleted"]["files"] = "success"
            except Exception as e:
                results["deleted"]["files_error"] = str(e)
        else:
            results["deleted"]["files"] = "not_found"
        
        # 5-6. Registry/metadata config: deshabilitado en modo cloud-only
        
        # 7. Delete notes/{project}/ and reports/{project}/ directories
        for dir_name in ["notes", "reports"]:
            dir_path = Path(dir_name) / project_id
            try:
                if dir_path.exists():
                    shutil.rmtree(dir_path)
                    results["deleted"][dir_name] = "success"
                else:
                    results["deleted"][dir_name] = "not_found"
            except Exception as e:
                results["deleted"][f"{dir_name}_error"] = str(e)
        
        # 8. Backups locales: deshabilitado en modo cloud-only
        
        # 9. Update metadata/entrevistas.json (remove project entries)
        try:
            entrevistas_path = Path("metadata/entrevistas.json")
            if entrevistas_path.exists():
                with open(entrevistas_path, "r", encoding="utf-8") as f:
                    entrevistas = json.load(f)
                if isinstance(entrevistas, list):
                    original_len = len(entrevistas)
                    entrevistas = [e for e in entrevistas if e.get("project_id") != project_id]
                    with open(entrevistas_path, "w", encoding="utf-8") as f:
                        json.dump(entrevistas, f, indent=2, ensure_ascii=False)
                    results["deleted"]["entrevistas_json"] = original_len - len(entrevistas)
        except Exception as e:
            results["deleted"]["entrevistas_json_error"] = str(e)
        
        api_logger.info("project.deleted", project_id=project_id, user=user.user_id, results=results)
        return {"status": "deleted", **results}
        
    except Exception as e:
        api_logger.exception("project.delete.error", project_id=project_id)
        raise HTTPException(status_code=500, detail=f"Error eliminando proyecto: {str(e)}")


@app.get("/healthz")
async def healthz() -> Dict[str, Any]:
    """
    Health check endpoint for frontend BackendStatus component.
    Does not require authentication to allow simple connectivity checks.
    """
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }


@app.get("/api/storage/check")
async def api_storage_check(
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Safe diagnostic endpoint for Azure Blob Storage.

    Returns whether storage is configured and reachable, without returning secrets.
    """
    try:
        from app.blob_storage import check_blob_storage_health

        storage = check_blob_storage_health()
        return {
            "timestamp": datetime.now().isoformat(),
            "storage": storage,
        }
    except Exception as e:
        return {
            "timestamp": datetime.now().isoformat(),
            "storage": {
                "configured": False,
                "status": "error",
                "message": str(e)[:200],
            },
        }


# Track server start time for uptime calculation
_SERVER_START_TIME = datetime.now()


@app.get("/api/health/full")
async def api_health_full(
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Comprehensive health check for all services.
    Returns status, latency, and details for each service.
    """
    import time
    
    services = []
    overall_healthy = True
    
    # 1. Check PostgreSQL
    pg_status = {"name": "PostgreSQL", "status": "checking"}
    try:
        start = time.perf_counter()
        clients = build_service_clients(settings)
        if clients.postgres:
            with clients.postgres.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            latency = int((time.perf_counter() - start) * 1000)
            pg_status = {
                "name": "PostgreSQL",
                "status": "online",
                "latency_ms": latency,
                "message": f"Conectado a {settings.postgres.host}:{settings.postgres.port}",
                "details": {
                    "database": settings.postgres.database,
                    "host": settings.postgres.host,
                }
            }
            clients.close()
        else:
            pg_status = {
                "name": "PostgreSQL",
                "status": "offline",
                "message": "No configurado"
            }
            overall_healthy = False
    except Exception as e:
        pg_status = {
            "name": "PostgreSQL",
            "status": "offline",
            "message": str(e)[:100]
        }
        overall_healthy = False
    services.append(pg_status)
    
    # 2. Check Neo4j
    neo4j_status = {"name": "Neo4j", "status": "checking"}
    try:
        start = time.perf_counter()
        clients = build_service_clients(settings)
        if clients.neo4j:
            with clients.neo4j.session() as session:
                result = session.run("RETURN 1 AS n")
                result.single()
            latency = int((time.perf_counter() - start) * 1000)
            neo4j_uri = settings.neo4j.uri
            neo4j_status = {
                "name": "Neo4j",
                "status": "online",
                "latency_ms": latency,
                "message": "Conexión establecida",
                "details": {
                    "uri": neo4j_uri[:30] + "..." if len(neo4j_uri) > 30 else neo4j_uri,
                    "database": settings.neo4j.database or "neo4j",
                }
            }
            clients.close()
        else:
            neo4j_status = {
                "name": "Neo4j",
                "status": "offline",
                "message": "No configurado"
            }
    except Exception as e:
        neo4j_status = {
            "name": "Neo4j",
            "status": "degraded",
            "message": str(e)[:100]
        }
    services.append(neo4j_status)
    
    # 3. Check Qdrant
    qdrant_status = {"name": "Qdrant", "status": "checking"}
    try:
        start = time.perf_counter()
        clients = build_service_clients(settings)
        if clients.qdrant:
            # Try to get collections list
            collections = clients.qdrant.get_collections()
            latency = int((time.perf_counter() - start) * 1000)
            collection_names = [c.name for c in collections.collections]
            qdrant_status = {
                "name": "Qdrant",
                "status": "online",
                "latency_ms": latency,
                "message": f"{len(collection_names)} colecciones",
                "details": {
                    "collections": collection_names[:5],  # Limit to 5
                    "collection_target": settings.qdrant.collection,
                }
            }
            clients.close()
        else:
            qdrant_status = {
                "name": "Qdrant",
                "status": "offline",
                "message": "No configurado"
            }
    except Exception as e:
        qdrant_status = {
            "name": "Qdrant",
            "status": "degraded",
            "message": str(e)[:100]
        }
    services.append(qdrant_status)
    
    # 4. Check Azure OpenAI
    azure_status = {"name": "Azure OpenAI", "status": "checking"}
    if settings.azure.api_key:
        azure_endpoint = settings.azure.endpoint or ""
        azure_status = {
            "name": "Azure OpenAI",
            "status": "online",
            "message": "API Key configurada",
            "details": {
                "endpoint": azure_endpoint[:40] + "..." if len(azure_endpoint) > 40 else azure_endpoint,
                "chat_deployment": settings.azure.deployment_chat,
                "embed_deployment": settings.azure.deployment_embed,
            }
        }
    else:
        azure_status = {
            "name": "Azure OpenAI",
            "status": "degraded",
            "message": "API Key no configurada"
        }
    services.append(azure_status)

    # 5. Check Azure Blob Storage (optional)
    storage_status = {"name": "Azure Blob Storage", "status": "checking"}
    try:
        from app.blob_storage import check_blob_storage_health

        storage = check_blob_storage_health()
        if storage.get("configured") and storage.get("status") == "ok":
            storage_status = {
                "name": "Azure Blob Storage",
                "status": "online",
                "latency_ms": storage.get("latency_ms"),
                "message": "Conectado",
                "details": {
                    "account_name": storage.get("account_name"),
                    "interviews_container": storage.get("interviews_container"),
                },
            }
        else:
            storage_status = {
                "name": "Azure Blob Storage",
                "status": "degraded",
                "message": storage.get("message") or "No configurado",
                "details": {"configured": bool(storage.get("configured"))},
            }
    except Exception as e:
        storage_status = {
            "name": "Azure Blob Storage",
            "status": "degraded",
            "message": str(e)[:100],
        }
    services.append(storage_status)
    
    # Calculate overall status
    statuses = [s["status"] for s in services]
    if all(s == "online" for s in statuses):
        overall = "healthy"
    elif "offline" in statuses:
        overall = "unhealthy"
    else:
        overall = "degraded"
    
    # Calculate uptime
    uptime = (datetime.now() - _SERVER_START_TIME).total_seconds()
    
    return {
        "timestamp": datetime.now().isoformat(),
        "services": services,
        "overall_status": overall,
        "uptime_seconds": int(uptime),
    }


@app.get("/api/status")
async def api_status(
    project: str = Query(..., description="Proyecto requerido"),
    update_state: bool = False,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if update_state:
        api_logger.info("api.status.update_state_flag", project=project_id)
    snapshot = detect_stage_status(
        clients.postgres,
        project_id,
        stages=STAGE_DEFINITIONS,
        stage_order=STAGE_ORDER,
    )
    return snapshot


@app.get("/api/dashboard/counts")
async def api_dashboard_counts(
    project: str = Query(..., description="Proyecto requerido"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Obtiene conteos en tiempo real para el dashboard.
    
    Este endpoint resuelve el Bug E1.1: "0 fragmentos" en Etapa 2.
    A diferencia de /api/status que lee el state guardado, este endpoint
    consulta directamente la base de datos para obtener conteos actualizados.
    
    Returns:
        Dict con conteos por etapa:
        - ingesta: archivos, fragmentos, speaker distribution
        - codificacion: códigos, citas, cobertura
        - axial: relaciones, categorías
        - candidatos: pendientes, validados, rechazados
    """
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        try:
            counts = get_dashboard_counts(clients.postgres, project_id)
            return counts
        except Exception as exc:
            from app.error_handling import api_error, ErrorCode
            raise api_error(
                status_code=500,
                code=ErrorCode.DATABASE_ERROR,
                message="Error calculando conteos del dashboard.",
                exc=exc,
            ) from exc
    finally:
        clients.close()


@app.get("/api/research/overview")
async def api_research_overview(
    project: str = Query(..., description="Proyecto requerido"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Resumen unificado del proyecto para UI.

    Retorna dos capas explícitas:
    - `validated`: checklist de etapas (lo que fue marcado/validado por workflow)
    - `observed`: métricas observadas directamente en BD (lo que existe en datos)

    Si PostgreSQL no está disponible, devuelve `availability.postgres=false` y
    degrada a un payload parcial con `warnings` (sin inventar ceros).
    """
    from datetime import datetime, timezone

    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    clients = build_clients_or_error(settings)
    try:
        overview: Dict[str, Any] = {
            "project": project_id,
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "availability": {"postgres": True},
            "validated": None,
            "observed": None,
            "discovery": None,
            "warnings": [],
        }

        # Layer 1: validated checklist
        try:
            overview["validated"] = detect_stage_status(
                clients.postgres,
                project_id,
                stages=STAGE_DEFINITIONS,
                stage_order=STAGE_ORDER,
            )
        except Exception as exc:
            api_logger.warning(
                "api.research.overview.validated_failed",
                project=project_id,
                error=str(exc),
            )
            overview["availability"]["postgres"] = False
            overview["warnings"].append(
                "No fue posible cargar el checklist de etapas (PostgreSQL no disponible o error interno)."
            )

        # Layer 2: observed counts
        try:
            overview["observed"] = get_dashboard_counts(clients.postgres, project_id)
        except Exception as exc:
            api_logger.warning(
                "api.research.overview.observed_failed",
                project=project_id,
                error=str(exc),
            )
            overview["availability"]["postgres"] = False
            overview["warnings"].append(
                "No fue posible calcular conteos observados (PostgreSQL no disponible o error interno)."
            )

        # Layer 3: small Discovery summary (best-effort)
        try:
            from app.postgres_block import get_discovery_runs

            runs = get_discovery_runs(clients.postgres, project=project_id, limit=30)
            landing_rates = [r["landing_rate"] for r in runs if r.get("landing_rate") is not None]
            avg_landing = (sum(landing_rates) / len(landing_rates)) if landing_rates else None
            overview["discovery"] = {
                "recent_runs": len(runs),
                "avg_landing_rate": round(float(avg_landing), 2) if avg_landing is not None else None,
                "latest": runs[0] if runs else None,
            }
        except Exception as exc:
            api_logger.info(
                "api.research.overview.discovery_summary_skipped",
                project=project_id,
                error=str(exc),
            )

        # Cross-layer warnings (only if both are present)
        try:
            validated = overview.get("validated") or {}
            observed = overview.get("observed") or {}
            stages = (validated.get("stages") or {}) if isinstance(validated, dict) else {}

            def _stage_completed(key: str) -> bool:
                entry = stages.get(key) or {}
                return bool(entry.get("completed"))

            ingesta_frag = (((observed.get("ingesta") or {}).get("fragmentos")) if isinstance(observed, dict) else None)
            open_codes = (((observed.get("codificacion") or {}).get("codigos")) if isinstance(observed, dict) else None)
            axial_rel = (((observed.get("axial") or {}).get("relaciones")) if isinstance(observed, dict) else None)

            if isinstance(ingesta_frag, int) and ingesta_frag > 0 and not _stage_completed("ingesta"):
                overview["warnings"].append(
                    "Hay fragmentos ingeridos, pero la Etapa 'Ingesta' no está marcada como completada (checklist)."
                )
            if isinstance(open_codes, int) and open_codes > 0 and not _stage_completed("codificacion"):
                overview["warnings"].append(
                    "Hay códigos definitivos, pero la Etapa 'Codificación abierta' no está marcada como completada (checklist)."
                )
            if isinstance(axial_rel, int) and axial_rel > 0 and not _stage_completed("axial"):
                overview["warnings"].append(
                    "Hay relaciones axiales, pero la Etapa 'Codificación axial' no está marcada como completada (checklist)."
                )
        except Exception:
            # Never fail the endpoint because of warning computation.
            pass

        # Layer 4: Panorama (CTA + gating), best-effort
        try:
            from app.home_panorama import build_panorama
            from app.project_state import get_project_config
            from app.postgres_block import select_next_uncoded_fragment, get_open_coding_pending_counts
            from app.coding import get_saturation_data

            if overview.get("availability", {}).get("postgres") is True:
                config = get_project_config(clients.postgres, project_id)
                window = int(config.get("axial_min_saturation_window") or 3)
                threshold = int(config.get("axial_min_saturation_threshold") or 2)

                saturation = None
                try:
                    saturation = get_saturation_data(clients, project_id, window=window, threshold=threshold)
                except Exception:
                    saturation = None

                total_counts = get_open_coding_pending_counts(clients.postgres, project_id=project_id, archivo=None)
                pending_total = int(total_counts.get("pending_total") or 0)

                frag = select_next_uncoded_fragment(
                    clients.postgres,
                    project_id=project_id,
                    archivo=None,
                    exclude_fragment_ids=[],
                    strategy="recent",
                )
                recommended_archivo = None
                if frag and frag.get("archivo"):
                    recommended_archivo = str(frag.get("archivo") or "").strip() or None

                pending_in_recommended = None
                if recommended_archivo:
                    c = get_open_coding_pending_counts(
                        clients.postgres,
                        project_id=project_id,
                        archivo=recommended_archivo,
                    )
                    pending_in_recommended = c.get("pending_in_archivo")

                overview["panorama"] = build_panorama(
                    project=project_id,
                    validated=overview.get("validated"),
                    observed=overview.get("observed"),
                    stage_order=STAGE_ORDER,
                    pending_total=pending_total,
                    recommended_archivo=recommended_archivo,
                    pending_in_recommended=pending_in_recommended,
                    saturation=saturation,
                    config=config,
                )
        except Exception as exc:
            api_logger.info(
                "api.research.overview.panorama_skipped",
                project=project_id,
                error=str(exc),
            )

        return overview
    finally:
        clients.close()


@app.post("/api/projects/{project_id}/stages/{stage}/complete")
async def api_complete_stage(
    project_id: str,
    stage: str,
    run_id: Optional[str] = None,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    if stage not in STAGE_DEFINITIONS:
        raise HTTPException(status_code=400, detail=f"Etapa desconocida: {stage}")
    try:
        resolved_project = resolve_project(project_id, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = mark_stage(
        clients.postgres,
        resolved_project,
        stage,
        run_id=run_id or "-",
        command="workflow",
        subcommand="complete",
        extras=None,
    )
    return payload


# ---------- Ingestion ----------
# NOTE: All ingestion and transcription endpoints have been moved to:
#       backend/routers/ingest.py
#
# Endpoints moved:
#   - POST /api/upload-and-ingest (NEW)
#   - POST /api/ingest
#   - POST /api/transcribe
#   - POST /api/transcribe/stream
#   - POST /api/transcribe/batch
#   - POST /api/transcribe/merge
#   - GET  /api/jobs/{task_id}/status
#   - GET  /api/jobs/batch/{batch_id}/status


def _expand_inputs(raw_inputs: List[str]) -> List[str]:
    """Expande patrones glob y normaliza rutas para compatibilidad Docker."""
    expanded: List[str] = []
    seen = set()
    for item in raw_inputs:
        if not item:
            continue
        # Normalizar backslashes de Windows a forward slashes para Linux
        item = item.replace("\\", "/")
        if any(ch in item for ch in ("*", "?", "[", "]")):
            for match in sorted(Path().glob(item)):
                if match.exists():
                    path = str(match)
                    if path not in seen:
                        expanded.append(path)
                        seen.add(path)
        else:
            if item not in seen:
                expanded.append(item)
                seen.add(item)
    return expanded


@app.post("/api/ingest")
async def api_ingest(
    payload: IngestRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    inputs = _expand_inputs(payload.inputs)
    if not inputs:
        raise HTTPException(status_code=400, detail="Debe especificar al menos un archivo o patrón.")

    meta = None
    if payload.meta_json:
        meta_path = Path(payload.meta_json)
        if not meta_path.exists():
            raise HTTPException(status_code=400, detail="Archivo meta_json no encontrado.")
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"No se pudo leer meta_json: {exc}") from exc

    clients = build_clients_or_error(settings)
    log = api_logger.bind(endpoint="ingest", project=project_id)
    try:
        result = ingest_documents(
            clients,
            settings,
            inputs,
            batch_size=payload.batch_size,
            min_chars=payload.min_chars,
            max_chars=payload.max_chars,
            metadata=meta,
            run_id=payload.run_id,
            logger=log,
            project=project_id,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("api.ingest.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()

    return {
        "project": project_id,
        "files": inputs,
        "result": result,
    }


# ---------- Transcription ----------


class TranscribeRequest(BaseModel):
    """Request para transcripción de audio con diarización."""
    model_config = ConfigDict(extra="forbid")

    project: str = Field(..., description="Proyecto donde se ingesta (si aplica)")
    audio_base64: str = Field(..., description="Archivo de audio codificado en base64")
    filename: str = Field(..., description="Nombre original del archivo (con extensión)")
    diarize: bool = Field(True, description="Usar diarización para separar speakers")
    language: str = Field("es", description="Código de idioma")
    ingest: bool = Field(False, description="Ingestar directamente al pipeline")
    save_to_folder: bool = Field(True, description="Guardar DOCX en carpeta del proyecto")
    min_chars: int = Field(200, description="Mínimo de caracteres por fragmento")
    max_chars: int = Field(1200, description="Máximo de caracteres por fragmento")


class TranscribeSegmentResponse(BaseModel):
    speaker: str
    text: str
    start: float
    end: float


class TranscribeResponse(BaseModel):
    """Respuesta de transcripción con segmentos y metadata."""
    text: str = Field(..., description="Transcripción completa")
    segments: List[TranscribeSegmentResponse] = Field(default_factory=list)
    speaker_count: int = Field(0, description="Número de speakers detectados")
    duration_seconds: float = Field(0.0, description="Duración del audio")
    fragments_ingested: Optional[int] = Field(None, description="Fragmentos creados si ingest=True")
    saved_path: Optional[str] = Field(None, description="Ruta donde se guardó el DOCX")


# ---------- Batch Transcription (Parallel Processing) ----------

class BatchTranscribeFileItem(BaseModel):
    """Un archivo en el batch de transcripción."""
    audio_base64: str = Field(..., description="Audio codificado en base64")
    filename: str = Field(..., description="Nombre del archivo")

class BatchTranscribeRequest(BaseModel):
    """Request para transcripción paralela de múltiples archivos."""
    model_config = ConfigDict(extra="forbid")
    
    project: str = Field(..., description="Proyecto destino")
    files: List[BatchTranscribeFileItem] = Field(..., description="Lista de archivos (max 20)")
    diarize: bool = Field(True, description="Usar diarización")
    language: str = Field("es", description="Código de idioma")
    ingest: bool = Field(True, description="Ingestar al pipeline")
    min_chars: int = Field(200)
    max_chars: int = Field(1200)

class BatchJobInfo(BaseModel):
    """Info de un job en el batch."""
    task_id: str
    filename: str

class BatchTranscribeResponse(BaseModel):
    """Respuesta de batch: IDs de jobs para tracking."""
    batch_id: str
    jobs: List[BatchJobInfo]
    message: str

class JobStatusResponse(BaseModel):
    """Estado de un job individual con soporte para progreso incremental."""
    task_id: str
    status: str  # PENDING, PROCESSING, SUCCESS, FAILURE
    filename: Optional[str] = None
    stage: Optional[str] = None  # transcribing, ingesting
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    # Campos para progreso de transcripción incremental
    chunk_index: Optional[int] = None
    total_chunks: Optional[int] = None
    chunks_completed: Optional[int] = None
    text_preview: Optional[str] = None
    segments_count: Optional[int] = None
    speakers_count: Optional[int] = None



@app.post("/api/transcribe", response_model=TranscribeResponse)
async def api_transcribe(
    payload: TranscribeRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Transcribe archivo de audio con diarización automática.
    
    Soporta formatos: MP3, MP4, M4A, WAV, WebM, MPEG, FLAC, OGG
    """
    import base64
    import tempfile
    from app.transcription import (
        transcribe_audio_chunked,
        audio_to_fragments,
        save_transcription_docx,
        SUPPORTED_AUDIO_FORMATS,
    )
    
    # Validar proyecto
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    # Validar extensión
    suffix = Path(payload.filename).suffix.lower()
    if suffix not in SUPPORTED_AUDIO_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado: {suffix}. Formatos válidos: {', '.join(SUPPORTED_AUDIO_FORMATS)}"
        )
    
    log = api_logger.bind(endpoint="transcribe", project=project_id)
    
    # Decodificar audio
    try:
        audio_bytes = base64.b64decode(payload.audio_base64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="No se pudo decodificar audio_base64") from exc
    
    # Guardar archivo temporal
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)
    
    try:
        # Transcribir usando chunked (divide automáticamente archivos grandes con ffmpeg)
        result = transcribe_audio_chunked(
            tmp_path,
            settings,
            diarize=payload.diarize,
            language=payload.language,
        )
        
        log.info(
            "api.transcribe.complete",
            speakers=result.speaker_count,
            segments=len(result.segments),
            duration=result.duration_seconds,
        )
        
        response_data = {
            "text": result.text,
            "segments": [
                {
                    "speaker": seg.speaker,
                    "text": seg.text,
                    "start": seg.start,
                    "end": seg.end,
                }
                for seg in result.segments
            ],
            "speaker_count": result.speaker_count,
            "duration_seconds": result.duration_seconds,
            "fragments_ingested": None,
            "saved_path": None,
        }
        
        # PASO 1: SIEMPRE guardar en carpeta del proyecto con nombre descriptivo
        # Esto asegura que nunca tengamos archivos temporales referenciados
        from datetime import datetime
        
        # Estructura unificada: data/projects/{project_id}/audio/transcriptions/
        project_audio_dir = Path(f"data/projects/{project_id}/audio/transcriptions")
        project_audio_dir.mkdir(parents=True, exist_ok=True)
        
        # Nombre basado en archivo de audio original + timestamp
        base_name = Path(payload.filename).stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_filename = f"{base_name}_{timestamp}.docx"
        saved_path = project_audio_dir / saved_filename
        
        save_transcription_docx(result, saved_path)
        response_data["saved_path"] = str(saved_path)
        
        log.info(
            "api.transcribe.saved",
            path=str(saved_path),
            project=project_id,
            filename=saved_filename,
        )

        # PASO 2: Ingestar al pipeline si se solicita (usando el archivo guardado)
        if payload.ingest:
            from app.ingestion import ingest_documents
            
            clients = build_clients_or_error(settings)
            try:
                # Usar el archivo guardado con nombre descriptivo
                ingest_result = ingest_documents(
                    clients,
                    settings,
                    files=[saved_path],
                    batch_size=20,
                    min_chars=payload.min_chars,
                    max_chars=payload.max_chars,
                    logger=log,
                    project=project_id,
                )
                totals = ingest_result.get("totals", {})
                response_data["fragments_ingested"] = totals.get("fragments_total", 0)
                log.info(
                    "api.transcribe.ingested",
                    fragments=response_data["fragments_ingested"],
                    docx_path=str(saved_path),
                    project=project_id,
                )
            finally:
                clients.close()
        
        return response_data
        
    except ValueError as exc:
        log.error("api.transcribe.error", error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("api.transcribe.error")
        raise HTTPException(status_code=500, detail=f"Error en transcripción: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)


# =============================================================================
# BATCH TRANSCRIPTION (PARALLEL PROCESSING)
# =============================================================================

from backend.celery_worker import task_transcribe_audio
import uuid

MAX_BATCH_SIZE = 20


class StreamTranscribeRequest(BaseModel):
    """Request para transcripción asíncrona con entregas incrementales."""
    model_config = ConfigDict(extra="forbid")

    project: str = Field(..., description="Proyecto destino")
    audio_base64: str = Field(..., description="Audio codificado en base64")
    filename: str = Field(..., description="Nombre del archivo")
    diarize: bool = Field(True, description="Usar diarización")
    language: str = Field("es", description="Código de idioma")
    ingest: bool = Field(True, description="Ingestar al pipeline")
    min_chars: int = Field(200)
    max_chars: int = Field(1200)


class StreamTranscribeResponse(BaseModel):
    """Respuesta de transcripción stream: task_id para polling."""
    task_id: str
    filename: str
    message: str


@app.post("/api/transcribe/stream", response_model=StreamTranscribeResponse)
async def api_transcribe_stream(
    payload: StreamTranscribeRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Inicia transcripción asíncrona con entregas incrementales.
    
    A diferencia de /api/transcribe (síncrono), este endpoint:
    1. Retorna inmediatamente con un task_id
    2. Procesa en background con Celery worker
    3. Guarda DOCX parcial después de cada chunk (5 min de audio)
    4. Ingesta fragmentos incrementalmente si ingest=True
    
    Usa GET /api/jobs/{task_id}/status para consultar progreso:
    - chunk_index: Chunk actual en proceso
    - total_chunks: Total de chunks
    - chunks_completed: Chunks ya completados
    - text_preview: Preview del texto transcrito hasta ahora
    
    Cuando status="SUCCESS", el resultado completo está en result.
    """
    log = api_logger.bind(endpoint="transcribe_stream", project=payload.project)
    
    # Validar proyecto
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    # Validar extensión
    suffix = Path(payload.filename).suffix.lower()
    from app.transcription import SUPPORTED_AUDIO_FORMATS
    if suffix not in SUPPORTED_AUDIO_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado: {suffix}. Formatos válidos: {', '.join(SUPPORTED_AUDIO_FORMATS)}"
        )
    
    # Encolar tarea con incremental=True
    task = cast(Any, task_transcribe_audio).delay(
        audio_base64=payload.audio_base64,
        filename=payload.filename,
        project_id=project_id,
        diarize=payload.diarize,
        language=payload.language,
        ingest=payload.ingest,
        min_chars=payload.min_chars,
        max_chars=payload.max_chars,
        incremental=True,  # Habilitar procesamiento incremental
    )
    
    log.info(
        "api.transcribe_stream.started",
        task_id=task.id,
        filename=payload.filename,
    )
    
    return {
        "task_id": task.id,
        "filename": payload.filename,
        "message": "Transcripción iniciada. Usa GET /api/jobs/{task_id}/status para consultar progreso.",
    }


@app.post("/api/transcribe/batch", response_model=BatchTranscribeResponse)
async def api_transcribe_batch(
    payload: BatchTranscribeRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Inicia transcripción paralela de múltiples archivos.
    
    Los archivos se procesan en background por workers Celery.
    Retorna IDs de jobs para tracking del progreso.
    
    Límite: 20 archivos por batch.
    """
    log = api_logger.bind(endpoint="transcribe_batch", project=payload.project)
    
    # Validar proyecto
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    # Validar tamaño del batch
    if len(payload.files) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Máximo {MAX_BATCH_SIZE} archivos por batch. Recibidos: {len(payload.files)}"
        )
    
    if len(payload.files) == 0:
        raise HTTPException(status_code=400, detail="Debe incluir al menos un archivo")
    
    # Generar batch ID
    batch_id = f"batch_{uuid.uuid4().hex[:12]}"
    
    # Encolar cada archivo como job independiente
    jobs = []
    for file_item in payload.files:
        task = cast(Any, task_transcribe_audio).delay(
            audio_base64=file_item.audio_base64,
            filename=file_item.filename,
            project_id=project_id,
            diarize=payload.diarize,
            language=payload.language,
            ingest=payload.ingest,
            min_chars=payload.min_chars,
            max_chars=payload.max_chars,
        )
        jobs.append({
            "task_id": task.id,
            "filename": file_item.filename,
        })
    
    log.info(
        "api.transcribe_batch.started",
        batch_id=batch_id,
        job_count=len(jobs),
        project=project_id,
    )
    
    return {
        "batch_id": batch_id,
        "jobs": jobs,
        "message": f"Iniciados {len(jobs)} jobs de transcripción en paralelo",
    }


@app.get("/api/jobs/{task_id}/status", response_model=JobStatusResponse)
async def api_job_status(
    task_id: str,
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Consulta el estado de un job de transcripción.
    
    Estados posibles:
    - PENDING: En cola, esperando worker
    - PROCESSING: En ejecución (transcribiendo o ingesting)
    - SUCCESS: Completado exitosamente
    - FAILURE: Falló
    
    Para transcripciones con incremental=True, el meta incluye:
    - chunk_index: Chunk actual siendo procesado
    - total_chunks: Total de chunks a procesar
    - chunks_completed: Número de chunks ya completados
    - text_preview: Preview del texto transcrito hasta ahora (500 chars)
    - segments_count: Número de segmentos transcritos
    - speakers_count: Número de speakers detectados
    """
    result = AsyncResult(task_id, app=celery_app)
    
    status = result.status
    response = {
        "task_id": task_id,
        "status": status,
        "filename": None,
        "stage": None,
        "result": None,
        "error": None,
    }
    
    if status == "PROCESSING":
        # Get meta info (stage, filename, chunk progress)
        meta = result.info or {}
        response["stage"] = meta.get("stage")
        response["filename"] = meta.get("filename")
        # Agregar info de chunks para transcripción incremental
        response["chunk_index"] = meta.get("chunk_index")
        response["total_chunks"] = meta.get("total_chunks")
        response["chunks_completed"] = meta.get("chunks_completed", 0)
        response["text_preview"] = meta.get("text_preview")
        response["segments_count"] = meta.get("segments_count")
        response["speakers_count"] = meta.get("speakers_count")
    
    elif status == "SUCCESS":
        task_result = result.result or {}
        response["result"] = task_result
        response["filename"] = task_result.get("filename")
    
    elif status == "FAILURE":
        response["error"] = str(result.result) if result.result else "Error desconocido"
    
    return response



@app.get("/api/jobs/batch/{batch_id}/status")
async def api_batch_status(
    batch_id: str,
    task_ids: str,  # Comma-separated list of task IDs
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Consulta el estado de múltiples jobs de un batch.
    """
    ids = [tid.strip() for tid in task_ids.split(",") if tid.strip()]
    
    statuses = []
    completed = 0
    failed = 0
    processing = 0
    pending = 0
    
    for tid in ids:
        result = AsyncResult(tid, app=celery_app)
        status = result.status
        
        if status == "SUCCESS":
            completed += 1
        elif status == "FAILURE":
            failed += 1
        elif status == "PROCESSING":
            processing += 1
        else:
            pending += 1
        
        statuses.append({
            "task_id": tid,
            "status": status,
        })
    
    return {
        "batch_id": batch_id,
        "total": len(ids),
        "completed": completed,
        "failed": failed,
        "processing": processing,
        "pending": pending,
        "all_done": (completed + failed) == len(ids),
        "jobs": statuses,
    }


class TranscribeMergeSegment(BaseModel):
    speaker: str
    text: str
    start: float
    end: float


class TranscribeMergeItem(BaseModel):
    filename: str
    text: str
    segments: List[TranscribeMergeSegment] = []


class TranscribeMergeRequest(BaseModel):
    """Request para combinar múltiples transcripciones en un DOCX."""
    model_config = ConfigDict(extra="forbid")
    
    project: str
    transcriptions: List[TranscribeMergeItem]


class TranscribeMergeResponse(BaseModel):
    docx_base64: str
    filename: str


@app.post("/api/transcribe/merge", response_model=TranscribeMergeResponse)
async def api_transcribe_merge(
    payload: TranscribeMergeRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Combina múltiples transcripciones en un único archivo DOCX.
    Retorna el archivo como base64 para descarga directa.
    """
    import base64
    import tempfile
    from datetime import datetime
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    
    # Validar proyecto
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    log = api_logger.bind(endpoint="transcribe_merge", project=project_id)
    
    if not payload.transcriptions:
        raise HTTPException(status_code=400, detail="No hay transcripciones para combinar")
    
    # Validar que al menos una transcripción tenga contenido real
    valid_count = sum(
        1 for t in payload.transcriptions
        if (t.text and t.text.strip()) or (t.segments and len(t.segments) > 0)
    )
    
    if valid_count == 0:
        log.warning(
            "api.transcribe_merge.empty_content",
            total=len(payload.transcriptions),
            filenames=[t.filename for t in payload.transcriptions],
        )
        raise HTTPException(
            status_code=400,
            detail="Las transcripciones no tienen contenido. Espera a que las transcripciones terminen de procesarse."
        )
    
    try:
        # Crear documento
        doc = Document()
        
        # Título
        title = doc.add_heading(f"Transcripción Combinada - {project_id}", 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Metadata
        doc.add_paragraph(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        doc.add_paragraph(f"Archivos: {len(payload.transcriptions)}")
        doc.add_paragraph("")
        
        # Agregar cada transcripción
        for item in payload.transcriptions:
            # Header del archivo
            doc.add_heading(f"📁 {item.filename}", level=1)
            
            if item.segments:
                # Con segmentos/speakers
                for seg in item.segments:
                    para = doc.add_paragraph()
                    # Speaker en bold
                    speaker_run = para.add_run(f"[{seg.speaker}] ")
                    speaker_run.bold = True
                    speaker_run.font.color.rgb = RGBColor(0, 100, 180)
                    # Texto
                    para.add_run(seg.text)
            else:
                # Solo texto
                doc.add_paragraph(item.text)
            
            doc.add_paragraph("")  # Separador
        
        # Guardar a temp file
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        
        doc.save(str(tmp_path))
        
        # También guardar en carpeta del proyecto (estructura unificada)
        project_audio_dir = Path(f"data/projects/{project_id}/audio/transcriptions")
        project_audio_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        permanent_path = project_audio_dir / f"combined_{timestamp}.docx"
        doc.save(str(permanent_path))
        
        log.info("api.transcribe_merge.saved", path=str(permanent_path))
        
        # Leer como base64
        with open(tmp_path, "rb") as f:
            docx_bytes = f.read()
        docx_base64 = base64.b64encode(docx_bytes).decode("utf-8")
        
        # Limpiar temp
        tmp_path.unlink(missing_ok=True)
        
        return {
            "docx_base64": docx_base64,
            "filename": f"transcripciones_{project_id}_{timestamp}.docx",
        }
        
    except Exception as exc:
        log.exception("api.transcribe_merge.error")
        raise HTTPException(status_code=500, detail=f"Error generando DOCX: {exc}") from exc


# ---------- Coding ----------


class CodingAssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: str
    fragment_id: str
    codigo: str
    cita: str
    fuente: Optional[str] = None
    memo: Optional[str] = None


@app.post("/api/coding/assign")
async def api_coding_assign(
    payload: CodingAssignRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    clients = build_clients_or_error(settings)
    log = api_logger.bind(endpoint="coding.assign", project=project_id)
    try:
        result = assign_open_code(
            clients,
            settings,
            fragment_id=payload.fragment_id,
            codigo=payload.codigo,
            cita=payload.cita,
            fuente=payload.fuente,
            memo=payload.memo,
            project=project_id,
            logger=log,
        )
    except CodingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        clients.close()
    return result


class CodingUnassignRequest(BaseModel):
    """Request para desvincular un código de un fragmento."""
    model_config = ConfigDict(extra="forbid")

    project: str
    fragment_id: str
    codigo: str


@app.delete("/api/coding/unassign")
async def api_coding_unassign(
    payload: CodingUnassignRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Desvincula un código de un fragmento.
    
    - Elimina la relación código-fragmento en PostgreSQL y Neo4j
    - NO elimina el fragmento ni el código (pueden tener otras asociaciones)
    - Útil para corregir asignaciones erróneas sin perder datos
    """
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    clients = build_clients_or_error(settings)
    log = api_logger.bind(endpoint="coding.unassign", project=project_id)
    try:
        result = unassign_open_code(
            clients,
            settings,
            fragment_id=payload.fragment_id,
            codigo=payload.codigo,
            project=project_id,
            changed_by=user.user_id if user else None,
            logger=log,
        )
    except CodingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        clients.close()
    return result


class CodingSuggestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: str
    fragment_id: str
    top_k: int = 5
    archivo: Optional[str] = None
    area_tematica: Optional[str] = None
    actor_principal: Optional[str] = None
    requiere_protocolo_lluvia: Optional[bool] = None
    include_coded: bool = False
    run_id: Optional[str] = None
    persist: bool = False
    llm_model: Optional[str] = None


@app.post("/api/coding/suggest")
async def api_coding_suggest(
    payload: CodingSuggestRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    clients = build_clients_or_error(settings)
    filters = {
        "archivo": payload.archivo,
        "area_tematica": payload.area_tematica,
        "actor_principal": payload.actor_principal,
        "requiere_protocolo_lluvia": payload.requiere_protocolo_lluvia,
    }
    filters = {k: v for k, v in filters.items() if v is not None}
    try:
        result = suggest_similar_fragments(
            clients,
            settings,
            fragment_id=payload.fragment_id,
            top_k=payload.top_k,
            filters=filters,
            exclude_coded=not payload.include_coded,
            run_id=payload.run_id,
            project=project_id,
            persist=payload.persist,
            llm_model=payload.llm_model,
            logger=api_logger.bind(endpoint="coding.suggest", project=project_id),
        )
    except CodingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        clients.close()
    return result


@app.get("/api/coding/stats")
async def api_coding_stats(
    project: str = Query(..., description="Proyecto requerido"),
    clients: PgOnlyClients = Depends(get_pg_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Get coding stats with a hard PG timeout to avoid UI 30s hangs."""
    import structlog
    _logger = structlog.get_logger("app.api.coding")

    try:
        project_id = await run_pg_query_with_timeout(
            resolve_project, project, allow_create=False, pg=clients.postgres
        )

        def _coding_stats_pg_only() -> Dict[str, Any]:
            # Keep everything inside the worker thread to honor the timeout.
            ensure_open_coding_table(clients.postgres)
            ensure_axial_table(clients.postgres)
            return coding_stats(clients.postgres, project_id)

        return await run_pg_query_with_timeout(_coding_stats_pg_only)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        # run_pg_query_with_timeout already returns 504 on timeout
        raise
    except Exception as exc:
        _logger.warning("api.coding.stats.timeout_or_error", error=str(exc), project=project)
        return {
            "total_codes": 0,
            "total_fragments": 0,
            "coded_fragments": 0,
            "coverage_percent": 0.0,
            "codes_per_fragment_avg": 0.0,
            "error": "Stats temporarily unavailable",
        }


@app.get("/api/coding/gate")
async def api_coding_gate(
    project: str = Query(..., description="Proyecto requerido"),
    threshold_count: int = Query(50, description="Máximo de pendientes permitidos"),
    threshold_days: int = Query(3, description="Días máximos sin resolver"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Verifica si es seguro ejecutar un nuevo análisis LLM.
    
    El gate bloquea nuevos análisis si:
    - Hay demasiados candidatos pendientes (> threshold_count)
    - Hay candidatos sin resolver por muchos días (> threshold_days)
    
    Esto evita que el backlog crezca sin control.
    
    Returns:
        - can_proceed: True si puede ejecutar análisis, False si debe validar primero
        - reason: Explicación si está bloqueado
        - health: Métricas completas del backlog
    """
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        health = get_backlog_health(
            clients.postgres,
            project_id,
            threshold_days=threshold_days,
            threshold_count=threshold_count,
        )
        
        can_proceed = health["is_healthy"]
        reason = None
        
        if not can_proceed:
            if health["pending_count"] >= threshold_count:
                reason = f"Backlog saturado: {health['pending_count']} pendientes (máx: {threshold_count})"
            elif health["oldest_pending_days"] >= threshold_days:
                reason = f"Hay candidatos sin validar desde hace {health['oldest_pending_days']} días"
        
        return {
            "can_proceed": can_proceed,
            "reason": reason,
            "health": health,
            "recommendation": (
                "Valide los candidatos pendientes antes de ejecutar nuevo análisis"
                if not can_proceed else None
            ),
        }
    finally:
        clients.close()


@app.get("/api/coding/fragment-context")
async def api_coding_fragment_context(
    project: str = Query(..., description="Proyecto requerido"),
    fragment_id: str = Query(..., description="ID del fragmento"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Obtiene el contexto completo de un fragmento para visualización en modal.
    
    Retorna:
        - fragment: Datos completos del fragmento (texto, metadatos)
        - codes: Lista de códigos asignados a este fragmento
        - codes_count: Total de códigos
        - adjacent_fragments: Fragmentos anteriores/posteriores para contexto
    """
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    clients = build_clients_or_error(settings)
    try:
        context = fetch_fragment_context(clients, project_id, fragment_id)
        if not context:
            raise HTTPException(status_code=404, detail=f"Fragmento '{fragment_id}' no encontrado")
    finally:
        clients.close()
    return context


@app.get("/api/interviews")
async def api_interviews(
    limit: int = 25,
    order: str = Query(
        default="ingest-desc",
        description="Orden de entrevistas: ingest-desc|ingest-asc|alpha|fragments-desc|fragments-asc|max-variation|theoretical-sampling",
    ),
    include_analyzed: bool = Query(
        default=False,
        description="Solo aplica a order=theoretical-sampling. Si true, incluye entrevistas ya analizadas al final del listado.",
    ),
    focus_codes: Optional[str] = Query(
        default=None,
        description="Solo aplica a order=theoretical-sampling. CSV de códigos foco (ej: 'Dificultad de pago,Acceso a subsidio').",
    ),
    recent_window: int = Query(
        default=3,
        ge=1,
        le=20,
        description="Solo aplica a order=theoretical-sampling. Ventana de últimos N informes para detectar saturación.",
    ),
    saturation_new_codes_threshold: int = Query(
        default=2,
        ge=0,
        le=50,
        description="Solo aplica a order=theoretical-sampling. Umbral de suma de codigos_nuevos en recent_window.",
    ),
    project: str = Query(..., description="Proyecto requerido"),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    try:
        project_id = resolve_project(project, allow_create=False, pg=clients.postgres)
        normalized_order = (order or "").strip().lower()
        if normalized_order == "theoretical-sampling":
            interviews, ranking_debug = list_available_interviews_with_ranking_debug(
                clients,
                project_id,
                limit=limit,
                order=order,
                include_analyzed=include_analyzed,
                focus_codes=focus_codes,
                recent_window=recent_window,
                saturation_new_codes_threshold=saturation_new_codes_threshold,
            )
            return {
                "interviews": interviews,
                "order": order,
                "ranking_debug": ranking_debug,
            }

        return {
            "interviews": list_available_interviews(
                clients,
                project_id,
                limit=limit,
                order=order,
                include_analyzed=include_analyzed,
                focus_codes=focus_codes,
                recent_window=recent_window,
                saturation_new_codes_threshold=saturation_new_codes_threshold,
            ),
            "order": order,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

# =============================================================================
# CÓDIGOS CANDIDATOS - Sistema de Consolidación
# =============================================================================

class CandidateCodeRequest(BaseModel):
    """Request para crear un código candidato."""
    model_config = ConfigDict(extra="forbid")

    project: str
    codigo: str
    cita: Optional[str] = None
    fragmento_id: Optional[str] = None
    archivo: Optional[str] = None
    fuente_origen: str = "manual"  # 'llm', 'manual', 'discovery', 'semantic_suggestion'
    fuente_detalle: Optional[str] = None
    score_confianza: Optional[float] = None
    memo: Optional[str] = None


class ValidateCandidateRequest(BaseModel):
    """Request para validar/rechazar un candidato."""
    model_config = ConfigDict(extra="forbid")

    project: str
    memo: Optional[str] = None


class MergeCandidatesRequest(BaseModel):
    """Request para fusionar códigos candidatos."""
    model_config = ConfigDict(extra="forbid")

    project: str
    source_ids: List[int]
    target_codigo: str


class PromoteCandidatesRequest(BaseModel):
    """Request para promover candidatos a definitivos."""
    model_config = ConfigDict(extra="forbid")

    project: str
    candidate_ids: List[int]


@app.get("/api/codes/candidates")
async def api_list_candidates(
    project: Optional[str] = Query(None, description="Proyecto requerido"),
    project_id: Optional[str] = Query(None, description="Alias de 'project' (compatibilidad)"),
    estado: Optional[str] = Query(None, description="Filtrar por estado: pendiente, validado, rechazado, fusionado"),
    fuente_origen: Optional[str] = Query(None, description="Filtrar por origen: llm, manual, discovery, semantic_suggestion"),
    archivo: Optional[str] = Query(None, description="Filtrar por archivo"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort_order: str = Query("desc", description="Ordenamiento: 'desc' (recientes primero) o 'asc' (antiguos primero)"),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Lista códigos candidatos con filtros opcionales."""
    try:
        effective_project = project or project_id
        if not effective_project:
            raise HTTPException(status_code=400, detail="Missing required query param: project")
        project_id = resolve_project(effective_project, allow_create=False, pg=clients.postgres)
        candidates = list_candidate_codes(
            clients.postgres,
            project=project_id,
            estado=estado,
            fuente_origen=fuente_origen,
            archivo=archivo,
            limit=limit,
            offset=offset,
            sort_order=sort_order,
        )
        return {"candidates": candidates, "count": len(candidates)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/codes/candidates/pending_count")
async def api_candidate_pending_count(
    project: Optional[str] = Query(None, description="Proyecto requerido"),
    project_id: Optional[str] = Query(None, description="Alias de 'project' (compatibilidad)"),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Retorna el total de candidatos pendientes (sin depender de limit/offset)."""
    try:
        effective_project = project or project_id
        if not effective_project:
            raise HTTPException(status_code=400, detail="Missing required query param: project")
        resolved = resolve_project(effective_project, allow_create=False, pg=clients.postgres)
        from app.postgres_block import count_pending_candidates

        pending_count = count_pending_candidates(clients.postgres, resolved)
        return {"project": resolved, "pending_count": pending_count}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/notes/{project}/download")
async def api_download_note(
    project: str,
    rel: str = Query(..., description="Ruta relativa bajo notes/<project>/"),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> FileResponse:
    """Descarga segura de un memo dentro de notes/<project>/ (previene path traversal)."""
    try:
        project_id = resolve_project(project, allow_create=False, pg=clients.postgres)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not rel or not rel.strip():
        raise HTTPException(status_code=400, detail="Missing required query param: rel")

    base_dir = (Path("notes") / project_id).resolve()
    rel_norm = rel.replace("\\", "/").lstrip("/")
    target = (base_dir / rel_norm).resolve()
    if base_dir not in target.parents and target != base_dir:
        raise HTTPException(status_code=400, detail="Invalid rel path")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Memo not found")

    media_type = "text/markdown" if target.suffix.lower() in {".md", ".markdown"} else "text/plain"
    return FileResponse(path=str(target), media_type=media_type, filename=target.name)


@app.post("/api/codes/candidates")
async def api_create_candidate(
    payload: CandidateCodeRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Crea un nuevo código candidato."""
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        count = insert_candidate_codes(
            clients.postgres,
            candidates=[{
                "project_id": project_id,
                "codigo": payload.codigo,
                "cita": payload.cita,
                "fragmento_id": payload.fragmento_id,
                "archivo": payload.archivo,
                "fuente_origen": payload.fuente_origen,
                "fuente_detalle": payload.fuente_detalle,
                "score_confianza": payload.score_confianza,
                "estado": "pendiente",
                "memo": payload.memo,
            }],
        )
    finally:
        clients.close()
    
    return {"success": count > 0, "inserted": count}


@app.put("/api/codes/candidates/{candidate_id}/validate")
async def api_validate_candidate(
    candidate_id: int,
    payload: ValidateCandidateRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Marca un código candidato como validado."""
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        success = validate_candidate(
            clients.postgres,
            project_id=project_id,
            candidate_id=candidate_id,
            validated_by=user.user_id if user else None,
            memo=payload.memo,
        )

        # UX fix: once validated, make it visible in Etapa 3 immediately.
        # The Coding panel reads from the definitive open-codes table via /api/coding/codes.
        promoted_count = (
            promote_to_definitive(
                clients.postgres,
                project_id=project_id,
                candidate_ids=[candidate_id],
                promoted_by=user.user_id if user else None,
            )
            if success
            else 0
        )
    finally:
        clients.close()
    
    if not success:
        raise HTTPException(status_code=404, detail="Candidato no encontrado o ya procesado")

    api_logger.info(
        "codes.candidates.validated",
        project_id=project_id,
        candidate_id=candidate_id,
        promoted_count=promoted_count,
    )

    return {
        "success": True,
        "candidate_id": candidate_id,
        "estado": "validado",
        "promoted_count": promoted_count,
    }


@app.put("/api/codes/candidates/{candidate_id}/reject")
async def api_reject_candidate(
    candidate_id: int,
    payload: ValidateCandidateRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Marca un código candidato como rechazado."""
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        success = reject_candidate(
            clients.postgres,
            project_id=project_id,
            candidate_id=candidate_id,
            rejected_by=user.user_id if user else None,
            memo=payload.memo,
        )
    finally:
        clients.close()
    
    if not success:
        raise HTTPException(status_code=404, detail="Candidato no encontrado o ya procesado")
    
    return {"success": True, "candidate_id": candidate_id, "estado": "rechazado"}


@app.post("/api/codes/candidates/merge")
async def api_merge_candidates(
    payload: MergeCandidatesRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Fusiona múltiples códigos candidatos en uno."""
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    if not payload.source_ids:
        raise HTTPException(status_code=400, detail="source_ids no puede estar vacío")
    
    clients = build_clients_or_error(settings)
    try:
        count = merge_candidates(
            clients.postgres,
            project_id=project_id,
            source_ids=payload.source_ids,
            target_codigo=payload.target_codigo,
            merged_by=user.user_id if user else None,
        )
    finally:
        clients.close()
    
    return {"success": count > 0, "merged_count": count, "target_codigo": payload.target_codigo}


# =============================================================================
# DUPLICATE DETECTION - Limpieza Post-Hoc de códigos
# =============================================================================

class DetectDuplicatesRequest(BaseModel):
    """Request para detectar códigos duplicados."""
    model_config = ConfigDict(extra="forbid")
    
    project: str = Field(..., description="Proyecto")
    threshold: float = Field(0.80, ge=0.5, le=1.0, description="Umbral de similitud")


def ensure_fuzzystrmatch(pg_conn) -> bool:
    """Habilita la extensión fuzzystrmatch si no existe."""
    try:
        with pg_conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;")
        pg_conn.commit()
        return True
    except Exception as exc:
        api_logger.warning("fuzzystrmatch.not_available", error=str(exc))
        # Try to rollback the failed transaction
        try:
            pg_conn.rollback()
        except Exception:
            pass
        return False


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Calcula distancia de Levenshtein en Python puro."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def find_similar_codes_python_fallback(
    pg_conn,
    project_id: str,
    threshold: float = 0.80,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Fallback: Encuentra códigos similares usando Python puro.
    
    Usado cuando la extensión fuzzystrmatch no está disponible.
    """
    # Get unique codes from database
    sql = """
    SELECT DISTINCT codigo
    FROM codigos_candidatos
    WHERE project_id = %s AND estado IN ('pendiente', 'validado')
    """
    with pg_conn.cursor() as cur:
        cur.execute(sql, (project_id,))
        rows = cur.fetchall()
    
    codes = [row[0] for row in rows if row[0]]
    
    # Find duplicates using Python
    duplicates = []
    
    # Check exact duplicates (same code with different entries)
    sql_count = """
    SELECT MIN(codigo) AS codigo, COUNT(*) as count
    FROM codigos_candidatos
    WHERE project_id = %s AND estado IN ('pendiente', 'validado')
    GROUP BY LOWER(codigo)
    HAVING COUNT(*) > 1
    ORDER BY count DESC
    LIMIT %s
    """
    with pg_conn.cursor() as cur:
        cur.execute(sql_count, (project_id, limit))
        exact_rows = cur.fetchall()
    
    for row in exact_rows:
        duplicates.append({
            "code1": row[0],
            "code2": row[0],
            "distance": 0,
            "similarity": 1.0,
            "is_exact_duplicate": True,
            "duplicate_count": row[1],
        })
    
    # Calculate Levenshtein similarity for unique codes
    unique_codes = list(set(c.lower() for c in codes))
    
    for i, c1 in enumerate(unique_codes):
        for c2 in unique_codes[i+1:]:
            max_len = max(len(c1), len(c2))
            if max_len == 0:
                continue
            # Pre-filter by length difference
            if abs(len(c1) - len(c2)) > int((1 - threshold) * max_len):
                continue
            
            distance = _levenshtein_distance(c1, c2)
            similarity = 1 - (distance / max_len)
            
            if similarity >= threshold and distance > 0:
                duplicates.append({
                    "code1": c1,
                    "code2": c2,
                    "distance": distance,
                    "similarity": round(similarity, 3),
                    "is_exact_duplicate": False,
                })
                
                if len(duplicates) >= limit:
                    break
        
        if len(duplicates) >= limit:
            break
    
    # Sort by similarity
    duplicates.sort(key=lambda x: x["similarity"], reverse=True)
    return duplicates[:limit]


def find_similar_codes_posthoc(
    pg_conn,
    project_id: str,
    threshold: float = 0.80,
    limit: int = 50,
    include_exact: bool = True,
) -> List[Dict[str, Any]]:
    """
    Encuentra pares de códigos candidatos similares usando Levenshtein.
    
    Args:
        include_exact: Si True, incluye duplicados exactos (distancia=0)
    """
    max_distance = int((1 - threshold) * 15)
    
    # Query para duplicados exactos (mismo código, diferentes entradas)
    exact_duplicates = []
    if include_exact:
        sql_exact = """
        SELECT 
            MIN(codigo) AS codigo,
            COUNT(*) as count,
            array_agg(DISTINCT fuente_origen) as sources,
            array_agg(DISTINCT archivo) FILTER (WHERE archivo IS NOT NULL) as files
        FROM codigos_candidatos
        WHERE project_id = %s AND estado IN ('pendiente', 'validado')
        GROUP BY LOWER(codigo)
        HAVING COUNT(*) > 1
        ORDER BY count DESC
        LIMIT %s
        """
        
        with pg_conn.cursor() as cur:
            cur.execute(sql_exact, (project_id, limit))
            rows = cur.fetchall()
        
        for row in rows:
            exact_duplicates.append({
                "code1": row[0],
                "code2": row[0],  # Mismo código
                "distance": 0,
                "similarity": 1.0,
                "is_exact_duplicate": True,
                "duplicate_count": row[1],
                "sources": row[2] if row[2] else [],
                "files": row[3][:5] if row[3] else [],  # Max 5 archivos
            })
    
    # Query para similares (distancia > 0)
    # OPTIMIZACIÓN: Filtro de longitud para reducir O(N²) a O(N*k)
    # Solo comparamos códigos cuya diferencia de longitud sea <= max_distance
    # Esto evita comparar "Organización" (12 chars) con "Si" (2 chars)
    sql_similar = """
    WITH unique_codes AS (
        SELECT DISTINCT codigo, LENGTH(codigo) AS len
        FROM codigos_candidatos
        WHERE project_id = %s AND estado IN ('pendiente', 'validado')
    )
    SELECT 
        c1.codigo AS code1,
        c2.codigo AS code2,
        levenshtein(LOWER(c1.codigo), LOWER(c2.codigo)) AS distance,
        GREATEST(c1.len, c2.len) AS max_len,
        1.0 - (levenshtein(LOWER(c1.codigo), LOWER(c2.codigo))::float / 
               GREATEST(c1.len, c2.len)::float) AS similarity
    FROM unique_codes c1, unique_codes c2
    WHERE c1.codigo < c2.codigo
      -- OPTIMIZACIÓN: Pre-filtro por longitud (evita Levenshtein innecesario)
      AND ABS(c1.len - c2.len) <= %s
      -- Solo calcular Levenshtein si pasa el filtro de longitud
      AND levenshtein(LOWER(c1.codigo), LOWER(c2.codigo)) <= %s
      AND levenshtein(LOWER(c1.codigo), LOWER(c2.codigo)) > 0
    ORDER BY similarity DESC
    LIMIT %s
    """
    

    with pg_conn.cursor() as cur:
        # Parámetros: project_id, max_len_diff, max_distance, limit
        cur.execute(sql_similar, (project_id, max_distance, max_distance, limit))
        rows = cur.fetchall()

    
    similar_codes = [
        {
            "code1": row[0],
            "code2": row[1],
            "distance": row[2],
            "similarity": round(row[4], 3),
            "is_exact_duplicate": False,
        }
        for row in rows
        if row[4] >= threshold
    ]
    
    # Combinar: exactos primero, luego similares
    return exact_duplicates + similar_codes




@app.post("/api/codes/detect-duplicates")
async def api_detect_duplicates(
    payload: DetectDuplicatesRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Detecta códigos duplicados usando similitud de Levenshtein (Post-Hoc).
    
    Útil para limpiar datos históricos que no pasaron por normalización Pre-Hoc.
    """
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        # Asegurar que la tabla existe
        from app.postgres_block import ensure_candidate_codes_table
        ensure_candidate_codes_table(clients.postgres)
        
        use_sql_levenshtein = ensure_fuzzystrmatch(clients.postgres)
        
        if use_sql_levenshtein:
            duplicates = find_similar_codes_posthoc(
                clients.postgres,
                project_id,
                threshold=payload.threshold,
            )
        else:
            # Fallback: Use Python Levenshtein when extension not available
            duplicates = find_similar_codes_python_fallback(
                clients.postgres,
                project_id,
                threshold=payload.threshold,
            )
        
        return {
            "success": True,
            "project": project_id,
            "threshold": payload.threshold,
            "duplicates": duplicates,
            "count": len(duplicates),
            "method": "sql" if use_sql_levenshtein else "python_fallback",
        }
    except HTTPException:
        raise
    except Exception as exc:
        api_logger.error("api.detect_duplicates.error", error=str(exc), project=payload.project)
        raise HTTPException(status_code=500, detail=f"Error detectando duplicados: {str(exc)}") from exc
    finally:
        clients.close()


# =============================================================================
# POST-HOC DUPLICATE DETECTION FOR NEO4J - Códigos en el grafo
# =============================================================================

class DetectDuplicatesNeo4jRequest(BaseModel):
    """Request para detectar códigos duplicados en Neo4j."""
    model_config = ConfigDict(extra="forbid")
    
    project: str = Field(..., description="Proyecto")
    threshold: float = Field(0.80, ge=0.5, le=1.0, description="Umbral de similitud")


@app.post("/api/codes/detect-duplicates-neo4j")
async def api_detect_duplicates_neo4j(
    payload: DetectDuplicatesNeo4jRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Detecta códigos duplicados en Neo4j usando similitud de Levenshtein (Post-Hoc).
    
    Busca duplicados en los nodos :Codigo del grafo (códigos ya promocionados).
    """
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        # Get all code names from Neo4j
        cypher = """
        MATCH (c:Codigo)
        WHERE c.project_id = $project_id
        RETURN c.nombre AS nombre
        ORDER BY nombre
        """
        with clients.neo4j.session() as session:
            result = session.run(cypher, project_id=project_id)
            codes = [record["nombre"] for record in result if record["nombre"]]
        
        if len(codes) < 2:
            return {
                "success": True,
                "project": project_id,
                "threshold": payload.threshold,
                "duplicates": [],
                "count": 0,
                "source": "neo4j",
                "total_codes": len(codes),
            }
        
        # Find duplicates using Python Levenshtein
        duplicates = []
        unique_codes = list(set(codes))
        
        for i, c1 in enumerate(unique_codes):
            for c2 in unique_codes[i+1:]:
                c1_lower = c1.lower()
                c2_lower = c2.lower()
                max_len = max(len(c1_lower), len(c2_lower))
                
                if max_len == 0:
                    continue
                    
                # Pre-filter by length difference
                if abs(len(c1_lower) - len(c2_lower)) > int((1 - payload.threshold) * max_len):
                    continue
                
                distance = _levenshtein_distance(c1_lower, c2_lower)
                similarity = 1 - (distance / max_len)
                
                if similarity >= payload.threshold:
                    duplicates.append({
                        "code1": c1,
                        "code2": c2,
                        "distance": distance,
                        "similarity": round(similarity, 3),
                        "source": "neo4j",
                    })
                    
                    if len(duplicates) >= 50:
                        break
            
            if len(duplicates) >= 50:
                break
        
        # Sort by similarity
        duplicates.sort(key=lambda x: x["similarity"], reverse=True)
        
        return {
            "success": True,
            "project": project_id,
            "threshold": payload.threshold,
            "duplicates": duplicates,
            "count": len(duplicates),
            "source": "neo4j",
            "total_codes": len(unique_codes),
        }
    except HTTPException:
        raise
    except Exception as exc:
        api_logger.error("api.detect_duplicates_neo4j.error", error=str(exc), project=payload.project)
        raise HTTPException(status_code=500, detail=f"Error detectando duplicados en Neo4j: {str(exc)}") from exc
    finally:
        clients.close()


# =============================================================================
# QDRANT GROUPED SEARCH - Evitar sesgo de fuente
# =============================================================================

class GroupedSearchRequest(BaseModel):
    """Request para búsqueda semántica agrupada con filtros avanzados."""
    model_config = ConfigDict(extra="forbid")
    
    project: str = Field(..., description="Proyecto")
    query: str = Field(..., min_length=3, description="Texto de búsqueda")
    limit: int = Field(10, ge=1, le=50, description="Máximo de grupos")
    group_by: str = Field("archivo", description="Campo para agrupar")
    group_size: int = Field(2, ge=1, le=5, description="Resultados por grupo")
    score_threshold: float = Field(0.3, ge=0.0, le=1.0, description="Umbral de score")
    
    # Filtros avanzados (Payload Filtering - Comparación Constante)
    genero: Optional[str] = Field(None, description="Filtrar por género (mujer/hombre)")
    actor_principal: Optional[str] = Field(None, description="Filtrar por rol/actor")
    area_tematica: Optional[str] = Field(None, description="Filtrar por área temática")
    periodo: Optional[str] = Field(None, description="Filtrar por periodo temporal")
    archivo: Optional[str] = Field(None, description="Filtrar por archivo específico")


@app.post("/api/qdrant/search-grouped")
async def api_qdrant_search_grouped(
    payload: GroupedSearchRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Búsqueda semántica agrupada para evitar sesgo de fuente.
    
    Garantiza diversidad en resultados: máximo N fragmentos por entrevista/speaker.
    Útil para muestreo teórico sin que una fuente domine.
    """
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        # Generar embedding del query
        from app.embeddings import embed_batch
        embeddings = embed_batch(clients.aoai, settings.azure.deployment_embed, [payload.query])
        if not embeddings or not embeddings[0]:
            raise HTTPException(status_code=500, detail="Error generando embedding")
        
        query_vector = embeddings[0]
        
        # Usar búsqueda agrupada con filtros
        from app.qdrant_block import search_similar_grouped
        groups = search_similar_grouped(
            clients.qdrant,
            settings.qdrant.collection,
            query_vector,
            limit=payload.limit,
            group_by=payload.group_by,
            group_size=payload.group_size,
            score_threshold=payload.score_threshold,
            project_id=project_id,
            exclude_interviewer=True,
            # Filtros avanzados
            genero=payload.genero or "",
            actor_principal=payload.actor_principal or "",
            area_tematica=payload.area_tematica or "",
            periodo=payload.periodo or "",
            archivo_filter=payload.archivo or "",
        )
        
        # Formatear resultados
        results = []
        for group in groups:
            group_key = group.id if hasattr(group, 'id') else str(group)
            hits = []
            for hit in (group.hits if hasattr(group, 'hits') else []):
                hits.append({
                    "id": hit.id,
                    "score": hit.score,
                    "fragmento": hit.payload.get("fragmento", "")[:200],
                    "archivo": hit.payload.get("archivo"),
                    "speaker": hit.payload.get("speaker"),
                    "actor_principal": hit.payload.get("actor_principal"),
                })
            results.append({
                "group_key": group_key,
                "hits": hits,
            })
        
        return {
            "success": True,
            "query": payload.query,
            "group_by": payload.group_by,
            "results": results,
            "total_groups": len(results),
        }
    except Exception as e:
        api_logger.error("qdrant.search_grouped.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        clients.close()


class HybridSearchRequest(BaseModel):
    """Request para búsqueda híbrida (semántica + keyword)."""
    model_config = ConfigDict(extra="forbid")
    
    project: str = Field(..., description="Proyecto")
    query: str = Field(..., min_length=2, description="Texto de búsqueda")
    limit: int = Field(10, ge=1, le=50, description="Máximo de resultados")
    score_threshold: float = Field(0.3, ge=0.0, le=1.0, description="Umbral de score")
    keyword_boost: float = Field(0.3, ge=0.0, le=1.0, description="Boost para matches exactos")


@app.post("/api/qdrant/search-hybrid")
async def api_qdrant_search_hybrid(
    payload: HybridSearchRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Búsqueda híbrida: semántica + texto exacto.
    
    Útil para capturar acrónimos (CESFAM, PAC) que embeddings pierden.
    - Dense: encuentra conceptos relacionados
    - Keyword: garantiza palabras exactas
    """
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        # Generar embedding
        from app.embeddings import embed_batch
        embeddings = embed_batch(clients.aoai, settings.azure.deployment_embed, [payload.query])
        if not embeddings or not embeddings[0]:
            raise HTTPException(status_code=500, detail="Error generando embedding")
        
        query_vector = embeddings[0]
        
        # Búsqueda híbrida
        from app.qdrant_block import search_hybrid
        results = search_hybrid(
            clients.qdrant,
            settings.qdrant.collection,
            payload.query,
            query_vector,
            limit=payload.limit,
            score_threshold=payload.score_threshold,
            project_id=project_id,
            keyword_boost=payload.keyword_boost,
        )
        
        # Formatear resultados
        formatted = [
            {
                "id": str(r.id),
                "score": r.score,
                "fragmento": r.payload.get("fragmento", "")[:300] if r.payload else "",
                "archivo": r.payload.get("archivo") if r.payload else None,
                "keyword_match": r.score > payload.score_threshold + payload.keyword_boost * 0.5,
            }
            for r in results
        ]
        
        return {
            "success": True,
            "query": payload.query,
            "results": formatted,
            "count": len(formatted),
        }
    except Exception as e:
        api_logger.error("qdrant.search_hybrid.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        clients.close()


@app.post("/api/codes/candidates/promote")
async def api_promote_candidates(
    payload: PromoteCandidatesRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Promueve códigos candidatos validados a la lista definitiva."""
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    if not payload.candidate_ids:
        raise HTTPException(status_code=400, detail="candidate_ids no puede estar vacío")
    
    clients = build_clients_or_error(settings)
    try:
        count = promote_to_definitive(
            clients.postgres,
            project_id=project_id,
            candidate_ids=payload.candidate_ids,
            promoted_by=user.user_id if user else None,
        )
    finally:
        clients.close()
    
    return {"success": count > 0, "promoted_count": count}


# =============================================================================
# LINK PREDICTION - Guardar sugerencias en Bandeja de Candidatos
# =============================================================================

class LinkPredictionSaveRequest(BaseModel):
    """Request para guardar sugerencias de Link Prediction como candidatos."""
    model_config = ConfigDict(extra="forbid")
    
    project: str = Field(..., description="Proyecto")
    suggestions: List[Dict[str, Any]] = Field(
        ..., 
        description="Lista de sugerencias: [{source, target, score, algorithm, reason}]"
    )


@app.post("/api/link-prediction/save")
async def api_save_link_predictions(
    payload: LinkPredictionSaveRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Guarda sugerencias de Link Prediction en la Bandeja de Candidatos.
    
    Las sugerencias se insertan como códigos candidatos con fuente_origen="link_prediction"
    para ser validadas por el investigador.
    """
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    if not payload.suggestions:
        raise HTTPException(status_code=400, detail="suggestions no puede estar vacío")
    
    # Convertir sugerencias a formato de candidatos
    candidates = []
    for suggestion in payload.suggestions:
        # Usar target como código (la relación sugerida)
        codigo = suggestion.get("target", "")
        source = suggestion.get("source", "")
        score = suggestion.get("score", 0.0)
        algorithm = suggestion.get("algorithm", "unknown")
        reason = suggestion.get("reason", "")
        
        if not codigo:
            continue
            
        candidates.append({
            "project_id": project_id,
            "codigo": codigo,
            "cita": f"Relación sugerida: {source} → {codigo}",
            "fragmento_id": None,  # Link Prediction no tiene fragmento específico
            "archivo": None,
            "fuente_origen": "link_prediction",
            "fuente_detalle": f"Algoritmo: {algorithm}. {reason}",
            "score_confianza": min(max(score, 0.0), 1.0),  # Normalizar entre 0 y 1
            "memo": f"Sugerido por Link Prediction ({algorithm})",
        })
    
    if not candidates:
        raise HTTPException(status_code=400, detail="No se encontraron sugerencias válidas")
    
    clients = build_clients_or_error(settings)
    try:
        insert_candidate_codes(clients.postgres, candidates)
    finally:
        clients.close()
    
    api_logger.info(
        "link_prediction.saved",
        project=project_id,
        count=len(candidates),
        user=user.user_id,
    )
    
    return {"success": True, "saved_count": len(candidates)}


# =============================================================================
# ANALYSIS REPORTS - Guardar análisis IA en la base de datos
# =============================================================================

class SaveAnalysisReportRequest(BaseModel):
    """Request para guardar un informe de análisis IA."""
    model_config = ConfigDict(extra="forbid")
    
    project: str = Field(..., description="Proyecto")
    report_type: str = Field(..., description="Tipo: link_prediction, discovery, axial, etc.")
    title: str = Field(..., description="Título del informe")
    content: str = Field(..., description="Contenido del análisis")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadatos adicionales")


def ensure_analysis_reports_table(pg_conn) -> None:
    """Crea tabla analysis_reports si no existe."""
    with pg_conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS analysis_reports (
                id SERIAL PRIMARY KEY,
                project_id VARCHAR(100) NOT NULL,
                report_type VARCHAR(50) NOT NULL,
                title VARCHAR(500) NOT NULL,
                content TEXT NOT NULL,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_analysis_reports_project 
            ON analysis_reports(project_id)
        """)
    pg_conn.commit()


@app.post("/api/analysis/save-report")
async def api_save_analysis_report(
    payload: SaveAnalysisReportRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Guarda un informe de análisis IA en la base de datos.
    
    Soporta múltiples tipos de análisis: link_prediction, discovery, etc.
    """
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        ensure_analysis_reports_table(clients.postgres)
        
        with clients.postgres.cursor() as cur:
            cur.execute("""
                INSERT INTO analysis_reports (project_id, report_type, title, content, metadata)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (
                project_id,
                payload.report_type,
                payload.title,
                payload.content,
                json.dumps(payload.metadata, default=str),
            ))
            result = cur.fetchone()
            report_id = result[0] if result else 0
        
        clients.postgres.commit()
    finally:
        clients.close()
    
    api_logger.info(
        "analysis_report.saved",
        project=project_id,
        report_type=payload.report_type,
        report_id=report_id,
        user=user.user_id,
    )
    
    return {"success": True, "report_id": report_id}


@app.get("/api/analysis/reports")
async def api_list_analysis_reports(
    project: str = Query(..., description="Proyecto requerido"),
    report_type: Optional[str] = Query(None, description="Filtrar por tipo"),
    limit: int = Query(50, ge=1, le=200),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Lista informes de análisis IA guardados."""
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        ensure_analysis_reports_table(clients.postgres)
        
        with clients.postgres.cursor() as cur:
            if report_type:
                cur.execute("""
                    SELECT id, report_type, title, content, metadata, created_at
                    FROM analysis_reports
                    WHERE project_id = %s AND report_type = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (project_id, report_type, limit))
            else:
                cur.execute("""
                    SELECT id, report_type, title, content, metadata, created_at
                    FROM analysis_reports
                    WHERE project_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (project_id, limit))
            
            rows = cur.fetchall()
    finally:
        clients.close()
    
    reports = [
        {
            "id": row[0],
            "report_type": row[1],
            "title": row[2],
            "content": row[3],
            "metadata": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
        }
        for row in rows
    ]
    
    return {"reports": reports, "count": len(reports)}


# =============================================================================
# INTERVIEW REPORTS - Informes por Entrevista
# =============================================================================

@app.get("/api/reports/interview")
async def api_list_interview_reports(
    project: str = Query(..., description="Proyecto requerido"),
    limit: int = Query(50, ge=1, le=200),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Lista informes de análisis por entrevista.
    
    Retorna los informes generados por el análisis LLM de cada entrevista.
    """
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        from app.reports import get_interview_reports
        reports = get_interview_reports(clients.postgres, project_id, limit)
        
        return {
            "reports": [r.to_dict() for r in reports],
            "count": len(reports),
        }
    except Exception as e:
        api_logger.error("interview_reports.list_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        clients.close()


@app.get("/api/reports/interview/{archivo}")
async def api_get_interview_report(
    archivo: str,
    project: str = Query(..., description="Proyecto requerido"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Obtiene el informe de análisis para una entrevista específica.
    """
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        from app.reports import get_interview_report
        report = get_interview_report(clients.postgres, project_id, archivo)
        
        if not report:
            raise HTTPException(
                status_code=404, 
                detail=f"No se encontró informe para: {archivo}"
            )
        
        return {"report": report.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        api_logger.error("interview_report.get_error", error=str(e), archivo=archivo)
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        clients.close()


@app.get("/api/codes/definitive")
async def api_definitive_codes(
    project: str = Query(..., description="Proyecto requerido"),
    limit: int = Query(100, ge=1, le=500),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Lista solo códigos validados (lista definitiva)."""
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        candidates = list_candidate_codes(
            clients.postgres,
            project=project_id,
            estado="validado",
            limit=limit,
        )
    finally:
        clients.close()
    
    return {"definitive_codes": candidates, "count": len(candidates)}


@app.get("/api/codes/stats/sources")
async def api_candidate_stats_by_source(
    project: str = Query(..., description="Proyecto requerido"),
    clients: PgOnlyClients = Depends(get_pg_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Obtiene estadísticas de códigos candidatos por origen."""
    try:
        # Run resolve_project in a thread to avoid blocking the event loop with sync DB I/O
        project_id = await asyncio.to_thread(resolve_project, project, allow_create=False, pg=clients.postgres)
        return await run_pg_query_with_timeout(get_candidate_stats_by_source, clients.postgres, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc




@app.get("/api/codes/candidates/{candidate_id}/examples")
async def api_candidate_examples(
    candidate_id: int,
    project: str = Query(..., description="Proyecto requerido"),
    limit: int = Query(3, ge=1, le=10, description="Cantidad de ejemplos canónicos"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Obtiene ejemplos canónicos (citas validadas previas) del mismo código.
    
    Usado para comparación constante al validar nuevos candidatos.
    """
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        # Buscar el candidato para obtener su código
        all_candidates = list_candidate_codes(
            clients.postgres,
            project=project_id,
            limit=500,
        )
        candidate = next((c for c in all_candidates if c["id"] == candidate_id), None)
        
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidato no encontrado")
        
        codigo = candidate["codigo"]
        
        # Obtener ejemplos canónicos
        examples = get_canonical_examples(
            clients.postgres,
            codigo=codigo,
            project=project_id,
            limit=limit,
        )
    finally:
        clients.close()
    
    return {
        "candidate_id": candidate_id,
        "codigo": codigo,
        "examples": examples,
        "examples_count": len(examples),
    }


@app.get("/api/codes/candidates/health")
async def api_candidates_health(
    project: str = Query(..., description="Proyecto requerido"),
    threshold_days: int = Query(3, ge=1, le=30, description="Días máximos sin resolver"),
    threshold_count: int = Query(50, ge=10, le=500, description="Máximos pendientes antes de alerta"),
    clients: PgOnlyClients = Depends(get_pg_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Verifica la salud del backlog de candidatos pendientes."""
    try:
        # Run resolve_project in a thread to avoid blocking the event loop with sync DB I/O
        project_id = await asyncio.to_thread(resolve_project, project, allow_create=False, pg=clients.postgres)
        return await run_pg_query_with_timeout(
            get_backlog_health,
            clients.postgres,
            project_id,
            threshold_days,
            threshold_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/codes/similar")
async def api_similar_codes(
    codigo: str = Query(..., description="Código a buscar similares"),
    project: str = Query(..., description="Proyecto requerido"),
    top_k: int = Query(5, ge=1, le=20, description="Máximo de códigos similares"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Encuentra códigos semánticamente similares para sugerir sinónimos o fusiones.
    """
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        similar = find_similar_codes(
            clients,
            settings,
            codigo=codigo,
            project=project_id,
            top_k=top_k,
        )
    finally:
        clients.close()
    
    return {
        "codigo": codigo,
        "similar_codes": similar,
        "count": len(similar),
    }


# Sprint 23: Pre-Hoc Check for Batch Codes
class CheckBatchCodesRequest(BaseModel):
    project: str = Field(..., description="Project ID")
    codigos: List[str] = Field(..., description="List of code names to check")
    threshold: float = Field(default=0.85, ge=0.5, le=1.0, description="Similarity threshold")


@app.post("/api/codes/check-batch")
async def api_check_batch_codes(
    payload: CheckBatchCodesRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Sprint 23: Pre-hoc check for batch of codes.
    
    Checks each proposed code against existing codes and returns
    similarity matches for deduplication UI.
    """
    from app.code_normalization import find_similar_codes, get_existing_codes_for_project
    
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        # Get existing codes from DB
        existing_codes = get_existing_codes_for_project(clients.postgres, project_id)
        
        results = []
        for codigo in payload.codigos:
            similar = find_similar_codes(
                codigo,
                existing_codes,
                threshold=payload.threshold,
                limit=3,
            )
            
            if similar:
                results.append({
                    "codigo": codigo,
                    "has_similar": True,
                    "similar": [
                        {"existing": s[0], "similarity": round(s[1], 2)}
                        for s in similar
                    ],
                })
            else:
                results.append({
                    "codigo": codigo,
                    "has_similar": False,
                    "similar": [],
                })
        
        has_any_similar = any(r["has_similar"] for r in results)
        
        return {
            "project": project_id,
            "threshold": payload.threshold,
            "results": results,
            "has_any_similar": has_any_similar,
            "checked_count": len(payload.codigos),
            "existing_count": len(existing_codes),
        }
    finally:
        clients.close()

@app.post("/api/maintenance/delete_file")
async def api_maintenance_delete_file(
    payload: MaintenanceDeleteFileRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Elimina todos los datos asociados a un archivo dentro de un proyecto.

    Nota: Esta operación es destructiva. Borra:
    - PostgreSQL: fragmentos, códigos abiertos, relaciones axiales por archivo, reportes por entrevista
    - Qdrant: puntos (fragmentos) filtrados por project_id + archivo
    - Neo4j: (:Entrevista {nombre=archivo, project_id}) y sus (:Fragmento) relacionados del proyecto
    """
    if not payload.file.strip():
        raise HTTPException(status_code=400, detail="file es obligatorio")

    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    clients = build_clients_or_error(settings)
    deleted: Dict[str, Any] = {"project_id": project_id, "file": payload.file}

    # 1) PostgreSQL deletions
    pg_counts: Dict[str, int] = {}
    try:
        with clients.postgres.cursor() as cur:
            # counts (best-effort)
            for table, where_sql in (
                (
                    "entrevista_fragmentos",
                    "project_id = %s AND archivo = %s",
                ),
                (
                    "analisis_codigos_abiertos",
                    "project_id = %s AND archivo = %s",
                ),
                (
                    "analisis_axial",
                    "project_id = %s AND archivo = %s",
                ),
                (
                    "interview_reports",
                    "project_id = %s AND archivo = %s",
                ),
            ):
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {where_sql}", (project_id, payload.file))
                    row = cur.fetchone()
                    pg_counts[table] = int(row[0] or 0) if row else 0
                except Exception:
                    # Table might not exist yet in fresh installs; treat as 0
                    pg_counts[table] = 0

            # deletes
            for table, where_sql in (
                ("analisis_codigos_abiertos", "project_id = %s AND archivo = %s"),
                ("analisis_axial", "project_id = %s AND archivo = %s"),
                ("entrevista_fragmentos", "project_id = %s AND archivo = %s"),
                ("interview_reports", "project_id = %s AND archivo = %s"),
            ):
                try:
                    cur.execute(f"DELETE FROM {table} WHERE {where_sql}", (project_id, payload.file))
                except Exception:
                    # Same reasoning: if table doesn't exist, ignore
                    continue
        clients.postgres.commit()
    except Exception as exc:
        clients.postgres.rollback()
        clients.close()
        raise HTTPException(status_code=500, detail=f"Error eliminando en PostgreSQL: {exc}") from exc
    deleted["postgres"] = {"counts": pg_counts}

    # 2) Qdrant deletions
    try:
        qdrant_filter = Filter(
            must=cast(
                List[Any],
                [
                    FieldCondition(key="project_id", match=MatchValue(value=project_id)),
                    FieldCondition(key="archivo", match=MatchValue(value=payload.file)),
                ],
            )
        )
        clients.qdrant.delete(
            collection_name=settings.qdrant.collection,
            points_selector=FilterSelector(filter=qdrant_filter),
        )
        deleted["qdrant"] = {"collection": settings.qdrant.collection, "filter": {"project_id": project_id, "archivo": payload.file}}
    except Exception as exc:
        clients.close()
        raise HTTPException(status_code=500, detail=f"Error eliminando en Qdrant: {exc}") from exc

    # 3) Neo4j deletions
    try:
        database = settings.neo4j.database
        cypher = """
        MATCH (e:Entrevista {nombre: $archivo})
        WHERE e.project_id = $project_id
        OPTIONAL MATCH (e)-[:TIENE_FRAGMENTO]->(f:Fragmento)
        WHERE f.project_id = $project_id
        DETACH DELETE f
        DETACH DELETE e
        """
        with clients.neo4j.session(database=database) as session:
            result = session.run(cypher, archivo=payload.file, project_id=project_id)
            summary = result.consume()
        deleted["neo4j"] = {
            "database": database,
            "nodes_deleted": summary.counters.nodes_deleted,
            "relationships_deleted": summary.counters.relationships_deleted,
        }
    except Exception as exc:
        clients.close()
        raise HTTPException(status_code=500, detail=f"Error eliminando en Neo4j: {exc}") from exc
    finally:
        clients.close()

    api_logger.info("maintenance.delete_file", **deleted)
    return {"status": "ok", "deleted": deleted}


@app.get("/api/coding/codes")
async def api_coding_codes(
    limit: int = 50,
    search: Optional[str] = None,
    archivo: Optional[str] = Query(default=None, description="Filtrar por archivo de entrevista"),
    project: str = Query(..., description="Proyecto requerido"),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    try:
        project_id = resolve_project(project, allow_create=False, pg=clients.postgres)
        return {"codes": list_open_codes(clients, project_id, limit=limit, search=search, archivo=archivo)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@app.get("/api/coding/fragments")
async def api_coding_fragments(
    archivo: str,
    limit: int = 25,
    project: str = Query(..., description="Proyecto requerido"),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    try:
        project_id = resolve_project(project, allow_create=False, pg=clients.postgres)
        return {"fragments": list_interview_fragments(clients, project_id, archivo=archivo, limit=limit)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/coding/citations")
async def api_coding_citations(
    codigo: str,
    project: str = Query(..., description="Proyecto requerido"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    clients = build_clients_or_error(settings)
    try:
        rows = citations_for_code(clients, codigo, project_id)
    finally:
        clients.close()
    return {"citations": rows}


@app.get("/api/coding/saturation")
async def api_coding_saturation(
    project: str = Query(..., description="Proyecto requerido"),
    window: int = Query(default=3, ge=1, le=10, description="Ventana de entrevistas para detectar plateau"),
    threshold: int = Query(default=2, ge=0, le=10, description="Máximo de códigos nuevos para considerar plateau"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Obtiene datos de saturación teórica para el indicador visual.
    
    Retorna:
    - curve: Lista de entrevistas con códigos nuevos y acumulados
    - plateau: Si se alcanzó saturación (las últimas N entrevistas tienen ≤threshold códigos nuevos)
    - summary: Estadísticas de resumen
    """
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    clients = build_clients_or_error(settings)
    try:
        data = get_saturation_data(clients, project_id, window=window, threshold=threshold)
    finally:
        clients.close()
    return data


@app.get("/api/export/refi-qda")
async def api_export_refi_qda(
    project: str = Query(..., description="Proyecto requerido"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> PlainTextResponse:
    """
    Exporta códigos en formato REFI-QDA XML (compatible con Atlas.ti 9+).
    """
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    clients = build_clients_or_error(settings)
    try:
        xml_content = export_codes_refi_qda(clients, project_id)
    finally:
        clients.close()
    return PlainTextResponse(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{project_id}_codes.qdpx"'}
    )


@app.get("/api/export/maxqda")
async def api_export_maxqda(
    project: str = Query(..., description="Proyecto requerido"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> PlainTextResponse:
    """
    Exporta códigos en formato CSV compatible con MAXQDA.
    """
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    clients = build_clients_or_error(settings)
    try:
        csv_content = export_codes_maxqda_csv(clients, project_id)
    finally:
        clients.close()
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{project_id}_codes.csv"'}
    )


@app.get("/api/coding/codes/{codigo}/history")
async def api_code_history(
    codigo: str,
    project: str = Query(..., description="Proyecto requerido"),
    limit: int = Query(default=20, ge=1, le=100),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Obtiene el historial de versiones de un código.
    
    Retorna lista de cambios con versión, acción, memos y timestamp.
    """
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    clients = build_clients_or_error(settings)
    try:
        history = fetch_code_history(clients, project_id, codigo, limit=limit)
    finally:
        clients.close()
    return {"codigo": codigo, "history": history, "total": len(history)}


@app.get("/api/fragments/sample")
async def api_fragments_sample(
    limit: int = 8,
    project: str = Query(..., description="Proyecto requerido"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    clients = build_service_clients(settings)
    try:
        rows = sample_postgres(clients, project_id, limit=limit)
    finally:
        clients.close()
    return {"samples": rows}


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: str
    docx_path: str
    persist: bool = False
    sync: bool = True  # Default to sync execution (Celery worker not processing tasks)
    run_id: Optional[str] = None


@app.post("/api/analyze", status_code=202)
async def api_analyze(
    payload: AnalyzeRequest,
    request: Request,
    settings: AppSettings = Depends(get_settings),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    try:
        project_id = resolve_project(payload.project, allow_create=False, pg=clients.postgres)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Etapa 0 gate: requiere preparación o override aprobado.
    try:
        stage0_require_ready_or_override(
            clients.postgres,
            project=project_id,
            scope="analyze",
            user_id=user.user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


    # Sprint 20: Gate de backlog - bloquear análisis si hay demasiados pendientes
    BACKLOG_THRESHOLD = int(os.getenv("CANDIDATE_BACKLOG_THRESHOLD", "100"))
    try:
        from app.postgres_block import count_pending_candidates
        pending_count = count_pending_candidates(clients.postgres, project_id)
        if pending_count > BACKLOG_THRESHOLD:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "BACKLOG_LIMIT_EXCEEDED",
                    "message": f"Hay {pending_count} códigos pendientes de validar. "
                               f"Valida al menos {pending_count - BACKLOG_THRESHOLD} "
                               "antes de ejecutar más análisis.",
                    "pending_count": pending_count,
                    "threshold": BACKLOG_THRESHOLD,
                }
            )
    except ImportError:
        pass  # Función no disponible, continuar sin validación
    except Exception as e:
        api_logger.warning("analyze.backlog_check_failed", error=str(e))

    request_id = getattr(getattr(request, "state", None), "request_id", None)
    run_id = payload.run_id or str(uuid.uuid4())

    docx_path = Path(payload.docx_path)
    downloaded_temp_path: Optional[Path] = None
    # Preserve original filename BEFORE any temp file download
    original_filename = docx_path.name
    # Security check: prevent traversing up
    if ".." in str(docx_path):
         raise HTTPException(status_code=400, detail="Ruta de archivo invalida.")

    if not docx_path.exists():
         # Try looking in project structure (unified paths)
         candidates = [
             Path(f"data/projects/{project_id}/interviews") / docx_path.name,
             Path(f"data/projects/{project_id}/audio/transcriptions") / docx_path.name,
             # Legacy paths
             Path("data/test_interviews/transcription_interviews") / docx_path.name,
             Path("data/interviews") / docx_path.name,
         ]
         found = False
         for candidate in candidates:
             if candidate.exists():
                 docx_path = candidate
                 found = True
                 break

         if not found:
             # Attempt to download from Azure Blob Storage (ingested files live there now)
             try:
                 from app.blob_storage import download_file, CONTAINER_INTERVIEWS

                 blob_path = f"{project_id}/{original_filename}"
                 file_bytes = download_file(CONTAINER_INTERVIEWS, blob_path)
                 with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_file:
                     tmp_file.write(file_bytes)
                     downloaded_temp_path = Path(tmp_file.name)
                 docx_path = downloaded_temp_path
                 found = True
                 api_logger.info("analyze.downloaded_blob", blob_path=blob_path, original_name=original_filename)
             except Exception as blob_error:
                 api_logger.warning(
                     "analyze.download_blob_failed",
                     file=docx_path.name,
                     project=project_id,
                     error=str(blob_error),
                 )

         if not found:
              raise HTTPException(status_code=404, detail=f"Archivo no encontrado: {payload.docx_path}")

    # Load fragments immediately (fast I/O)
    fragments = load_fragments(docx_path)

    # Clean up temporary download once fragments are loaded
    if downloaded_temp_path and downloaded_temp_path.exists():
        try:
            downloaded_temp_path.unlink()
        except OSError:
            pass
    
    # Synchronous execution (default - Celery worker not processing tasks)
    if payload.sync:
        from app.analysis import analyze_interview_text, persist_analysis
        from app.reports import generate_interview_report, save_interview_report
        from app.coding import get_all_codes_for_project
        
        api_logger.info("analyze.sync.start", file=docx_path.name, project=project_id)
        
        try:
            # Clear any aborted transaction state from previous operations
            try:
                clients.postgres.rollback()
            except Exception:
                pass  # Ignore if no transaction to rollback
            
            # Get existing codes for novelty calculation
            try:
                existing_codes = get_all_codes_for_project(clients.postgres, project_id)
            except Exception:
                clients.postgres.rollback()  # Clear failed transaction state
                existing_codes = []
            
            # Execute LLM analysis (stages 0-4)
            result = analyze_interview_text(
                clients,
                settings,
                fragments,
                fuente=original_filename,
                project_id=project_id,
                run_id=run_id,
                request_id=request_id,
            )
            
            # Persist if requested
            if payload.persist:
                persist_analysis(
                    clients,
                    settings,
                    original_filename,
                    result,
                    project_id=project_id,
                    run_id=run_id,
                    request_id=request_id,
                )
                api_logger.info("analyze.sync.persisted", file=original_filename)
            
            # Generate interview report
            try:
                report = generate_interview_report(
                    archivo=original_filename,
                    project_id=project_id,
                    analysis_result=result,
                    existing_codes=existing_codes,
                    fragments_total=len(fragments),
                    llm_model=settings.azure.deployment_chat,
                )
                save_interview_report(clients.postgres, report)
                api_logger.info("analyze.sync.report_saved", file=original_filename)
                result["interview_report"] = report.to_dict()
            except Exception as report_error:
                api_logger.warning("analyze.sync.report_error", error=str(report_error))
                result["interview_report"] = None
            
            api_logger.info("analyze.sync.complete", file=original_filename, project=project_id)
            return {"status": "success", "result": result}
            
        except Exception as e:
            api_logger.exception("analyze.sync.error", file=original_filename)
            raise HTTPException(status_code=500, detail=f"Error en análisis: {str(e)}")
    
    # Async execution (Celery - currently not working)
    task = cast(Any, task_analyze_interview).delay(
        project_id=project_id,
        docx_path=str(docx_path),
        fragments=fragments,
        persist=payload.persist,
        file_name=original_filename,
        run_id=run_id,
        request_id=request_id,
    )
    
    api_logger.info("analyze.queued", task_id=task.id, file=original_filename)
    
    return {"task_id": task.id, "status": "queued", "run_id": run_id, "request_id": request_id}


@app.get("/api/tasks/{task_id}")
async def get_task_status(
    task_id: str,
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    try:
        task_result = AsyncResult(task_id, app=celery_app)
        
        # Handle different task states
        if task_result.failed():
            # Task failed - get the exception info
            error_info = str(task_result.result) if task_result.result else "Unknown error"
            return {
                "task_id": task_id,
                "status": "FAILURE",
                "result": None,
                "error": error_info,
            }
        
        result = {
            "task_id": task_id,
            "status": task_result.status,
            "result": task_result.result if task_result.ready() and task_result.successful() else None,
        }
        return result
    except Exception as e:
        api_logger.error("task_status.error", task_id=task_id, error=str(e))
        return {
            "task_id": task_id,
            "status": "ERROR",
            "result": None,
            "error": str(e),
        }


class PersistAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project: str
    archivo: str
    analysis_result: Dict[str, Any]


@app.post("/api/analyze/persist")
async def api_analyze_persist(
    payload: PersistAnalysisRequest,
    request: Request,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    try:
        project_id = resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    clients = build_clients_or_error(settings)
    log = api_logger.bind(endpoint="analyze.persist", project=project_id, file=payload.archivo)

    try:
        # Etapa 0 gate: persistir análisis también requiere preparación o override aprobado.
        try:
            stage0_require_ready_or_override(
                clients.postgres,
                project=project_id,
                scope="analyze",
                user_id=user.user_id,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        request_id = getattr(getattr(request, "state", None), "request_id", None)
        cm = payload.analysis_result.get("cognitive_metadata") if isinstance(payload.analysis_result, dict) else None
        run_id = cm.get("run_id") if isinstance(cm, dict) else None

        persist_analysis(
            clients,
            settings,
            payload.archivo,
            payload.analysis_result,
            project_id=project_id,
            run_id=run_id,
            request_id=request_id,
        )
        log.info("analyze.persisted_manual")
        return {"status": "ok", "message": "Analisis persistido correctamente."}
    except Exception as exc:
        log.error("api.analyze.persist.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()


@app.post("/api/axial/gds")
async def api_run_gds_analysis(
    payload: GDSRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> List[Dict[str, Any]]:
    clients = build_neo4j_only(settings)
    try:
        results = run_gds_analysis(
            cast(ServiceClients, clients),
            settings,
            payload.algorithm,
            persist=payload.persist,
        )
        return results
    except AxialError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        api_logger.error("api.gds.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()


@app.post("/api/coding/suggestions")
async def api_coding_suggestions(
    payload: CodeSuggestionRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    clients = build_clients_or_error(settings)
    try:
        # Embed fragment
        vectors = embed_batch(clients.aoai, settings.azure.deployment_embed, [payload.fragment_text])
        vector = vectors[0] if vectors else []
        
        # Search Similar
        points = search_similar(
            clients.qdrant,
            settings.qdrant.collection,
            vector=vector,
            limit=payload.limit * 2, # Fetch more to aggregate
        )
        
        # Aggregate Codes
        # Assuming payload has 'codigos_ancla' or we can fetch from Neo4j given the ID.
        # For speed, let's rely on Qdrant payload 'codigos_ancla' if it exists.
        
        suggested_codes = Counter()
        evidence_map = {}
        
        for point in points:
            codes = point.payload.get("codigos_ancla", [])
            if isinstance(codes, list):
                for code in codes:
                    suggested_codes[code] += 1
                    if code not in evidence_map:
                         evidence_map[code] = point.payload.get("fragmento")
            elif isinstance(codes, str): # Legacy single code
                 suggested_codes[codes] += 1
                 if codes not in evidence_map:
                     evidence_map[codes] = point.payload.get("fragmento")

        top_suggestions = []
        for code, count in suggested_codes.most_common(5):
            top_suggestions.append({
                "code": code,
                "confidence": count / len(points), # Naive confidence
                "example": evidence_map.get(code)
            })
            
        return {"suggestions": top_suggestions}

    except Exception as exc:
        api_logger.error("api.suggestions.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()


# =============================================================================
# Sprint 9: GraphRAG, Discovery API, Link Prediction
# =============================================================================

class GraphRAGRequest(BaseModel):
    """Request for GraphRAG query."""
    query: str = Field(..., description="Pregunta del usuario")
    project: str = Field(default="default", description="ID del proyecto")
    include_fragments: bool = Field(default=True, description="Incluir fragmentos en contexto")
    chain_of_thought: bool = Field(default=False, description="Usar razonamiento paso a paso")


class DiscoverRequest(BaseModel):
    """Request for Discovery API search."""
    positive_texts: List[str] = Field(..., description="Textos/conceptos positivos")
    negative_texts: Optional[List[str]] = Field(default=None, description="Textos a evitar")
    target_text: Optional[str] = Field(default=None, description="Texto objetivo")
    top_k: int = Field(default=10, ge=1, le=50)
    project: str = Field(default="default")


class LinkPredictionRequest(BaseModel):
    """Request for Link Prediction."""
    source_type: str = Field(default="Categoria", description="Tipo de nodo fuente")
    target_type: str = Field(default="Codigo", description="Tipo de nodo destino")
    algorithm: str = Field(default="common_neighbors", description="Algoritmo a usar")
    top_k: int = Field(default=10, ge=1, le=50)
    project: str = Field(default="default")
    categoria: Optional[str] = Field(default=None, description="Filtrar por categoria")


@app.post("/api/graphrag/query")
async def api_graphrag_query(
    payload: GraphRAGRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Ejecuta una consulta GraphRAG con contexto de grafo.
    
    Combina busqueda semantica + estructura del grafo + LLM para respuestas
    contextualizadas sobre la investigacion cualitativa.
    """
    from app.graphrag import graphrag_query, graphrag_chain_of_thought
    
    clients = build_clients_or_error(settings)
    try:
        api_logger.info("api.graphrag.start", query=payload.query[:50], project=payload.project)
        
        if payload.chain_of_thought:
            result = graphrag_chain_of_thought(
                clients, settings,
                query=payload.query,
                project=payload.project,
            )
        else:
            result = graphrag_query(
                clients, settings,
                query=payload.query,
                project=payload.project,
                include_fragments=payload.include_fragments,
            )
        
        api_logger.info(
            "api.graphrag.complete",
            query=payload.query[:50],
            nodes=len(result.get("nodes") or []),
            answer_len=len(result.get("answer") or ""),
        )
        
        return result
        
    except Exception as exc:
        api_logger.error("api.graphrag.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()

class GraphRAGSaveRequest(BaseModel):
    query: str
    answer: str
    context: Optional[str] = ""
    nodes: List[Dict[str, Any]] = []
    relationships: List[Dict[str, Any]] = []
    fragments: List[Dict[str, Any]] = []
    project: str = "default"


@app.post("/api/graphrag/save_report")
async def api_save_report(
    payload: GraphRAGSaveRequest,
    user: User = Depends(require_auth),
) -> Dict[str, str]:
    """Guarda el reporte de GraphRAG como archivo Markdown."""
    try:
        # Create directory
        base_dir = Path("reports") / payload.project
        base_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        
        # Safe slug from query (first 30 chars, alphanumeric only)
        safe_query = "".join(c if c.isalnum() else "_" for c in payload.query[:30]).strip("_")
        filename = f"{timestamp}_{safe_query}.md"
        file_path = base_dir / filename
        
        # Format Content
        lines = [
            f"# Reporte de Investigación: {payload.query}",
            f"**Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Proyecto:** {payload.project}",
            "\n## Respuesta",
            payload.answer,
            "\n## Contexto del Grafo",
            payload.context or "(Sin contexto)",
            f"\n## Evidencia ({len(payload.fragments)} fragmentos)",
        ]
        
        for idx, frag in enumerate(payload.fragments):
            source = frag.get("archivo", "Desconocido")
            text = frag.get("fragmento", "")
            lines.append(f"\n### Fragmento {idx+1} ({source})")
            lines.append(f"> {text}")
            
        # Write file
        file_path.write_text("\n".join(lines), encoding="utf-8")
        
        api_logger.info("report.saved", path=str(file_path))
        return {"status": "ok", "path": str(file_path), "filename": filename}
        
    except Exception as exc:
        api_logger.error("report.save.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class DoctoralReportRequest(BaseModel):
    """Request para generar informe doctoral."""
    stage: str  # "stage3" o "stage4"
    project: str = "default"


# -----------------------------------------------------------------------------
# Doctoral report jobs (async)
# -----------------------------------------------------------------------------

def _user_is_admin(user: User) -> bool:
    roles = user.roles or []
    return "admin" in {str(r).strip().lower() for r in roles if r}


def _assert_doctoral_task_access(*, task_id: str, task: Dict[str, Any], user: User) -> None:
    auth = task.get("auth") or {}
    owner_user_id = str(auth.get("user_id") or "").strip()
    if not owner_user_id:
        # Legacy/backward-compat: if task has no auth metadata, allow only admins.
        if _user_is_admin(user):
            return
        raise HTTPException(status_code=403, detail="Forbidden: task has no owner metadata")

    if owner_user_id != str(user.user_id):
        if _user_is_admin(user):
            return
        raise HTTPException(status_code=403, detail="Forbidden: task belongs to another user")


def _run_doctoral_report_task(*, task_id: str, payload: DoctoralReportRequest, settings: AppSettings) -> None:
    """Background worker for doctoral report generation."""
    from app.doctoral_reports import generate_stage3_report, generate_stage4_report
    from app.postgres_block import save_doctoral_report, update_report_job
    from app.blob_storage import CONTAINER_REPORTS, upload_local_path

    clients = build_clients_or_error(settings)
    try:
        # Mark running
        try:
            update_report_job(
                clients.postgres,
                task_id=task_id,
                status="running",
                message="Generando informe...",
                started_at=datetime.now().isoformat(),
            )
        except Exception:
            pass

        if payload.stage == "stage3":
            result = generate_stage3_report(clients, settings, payload.project)
        elif payload.stage == "stage4":
            result = generate_stage4_report(clients, settings, payload.project)
        else:
            update_report_job(
                clients.postgres,
                task_id=task_id,
                status="error",
                message=f"Etapa no válida: {payload.stage}. Use 'stage3' o 'stage4'.",
                errors=[f"Etapa no válida: {payload.stage}"],
                finished_at=datetime.now().isoformat(),
            )
            return

        base_dir = Path("reports") / payload.project / "doctoral"
        base_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        filename = f"{timestamp}_doctoral_{payload.stage}.md"
        file_path = base_dir / filename
        file_path.write_text(result.get("content") or "", encoding="utf-8")

        blob_url: Optional[str] = None
        try:
            blob_name = f"{payload.project}/doctoral/{filename}"
            blob_url = upload_local_path(
                container=CONTAINER_REPORTS,
                blob_name=blob_name,
                file_path=str(file_path),
                content_type="text/markdown",
            )
        except Exception as exc:
            api_logger.warning("doctoral.report.blob_upload_failed", error=str(exc)[:200], task_id=task_id)

        # Persist DB record for history
        report_id = save_doctoral_report(
            clients.postgres,
            project=payload.project,
            stage=payload.stage,
            content=result.get("content") or "",
            stats=result.get("stats"),
            file_path=str(file_path),
        )

        final_result = {
            **(result or {}),
            "stage": payload.stage,
            "project": payload.project,
            "path": str(file_path),
            "filename": filename,
            "report_id": report_id,
            "blob_url": blob_url,
        }

        update_report_job(
            clients.postgres,
            task_id=task_id,
            status="completed",
            message="Informe doctoral generado",
            result=final_result,
            result_path=str(file_path),
            finished_at=datetime.now().isoformat(),
        )
    except Exception as exc:
        try:
            update_report_job(
                clients.postgres,
                task_id=task_id,
                status="error",
                message=str(exc),
                errors=[str(exc)],
                finished_at=datetime.now().isoformat(),
            )
        except Exception:
            pass
        api_logger.error("doctoral.report.job_error", error=str(exc), task_id=task_id)
    finally:
        clients.close()


class DoctoralReportJobStatusResponse(BaseModel):
    task_id: str
    status: str
    project: str
    stage: str
    message: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    errors: Optional[List[str]] = None


class DoctoralReportJobResultResponse(BaseModel):
    task_id: str
    status: str
    result: Dict[str, Any]


@app.post("/api/reports/doctoral/execute")
async def api_execute_doctoral_report_job(
    payload: DoctoralReportRequest,
    background_tasks: BackgroundTasks,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_role(["admin", "analyst"])),
) -> Dict[str, Any]:
    """Start an async doctoral report generation job."""
    task_id = f"doctoral_{payload.project}_{payload.stage}_{uuid.uuid4().hex[:12]}"
    auth = {
        "user_id": str(user.user_id),
        "org": str(user.organization_id),
        "roles": list(user.roles or []),
    }
    # Persist job row (durable)
    try:
        from app.postgres_block import create_report_job

        clients = build_clients_or_error(settings)
        try:
            create_report_job(
                clients.postgres,
                task_id=task_id,
                job_type="doctoral",
                project_id=payload.project,
                payload=payload.model_dump(),
                auth=auth,
                message="Inicializando...",
            )
        finally:
            clients.close()
    except Exception as exc:
        api_logger.warning("doctoral.report.job_persist_failed", error=str(exc), task_id=task_id)

    api_logger.info("doctoral.report.job_started", task_id=task_id, project=payload.project, stage=payload.stage)

    # FastAPI injects BackgroundTasks, but we keep it typed loosely to avoid extra imports.
    background_tasks.add_task(_run_doctoral_report_task, task_id=task_id, payload=payload, settings=settings)
    return {"task_id": task_id, "status": "started"}


@app.get("/api/reports/doctoral/status/{task_id}", response_model=DoctoralReportJobStatusResponse)
async def api_get_doctoral_report_job_status(
    task_id: str,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> DoctoralReportJobStatusResponse:
    # Load from durable store
    clients = build_clients_or_error(settings)
    try:
        from app.postgres_block import get_report_job

        task = get_report_job(clients.postgres, task_id)
    finally:
        clients.close()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    _assert_doctoral_task_access(task_id=task_id, task=task, user=user)
    return DoctoralReportJobStatusResponse(
        task_id=task_id,
        status=str(task.get("status") or "pending"),
        project=str(task.get("project_id") or "default"),
        stage=str(((task.get("payload") or {}) if isinstance(task.get("payload"), dict) else {}).get("stage") or ""),
        message=task.get("message"),
        started_at=task.get("started_at") or task.get("created_at"),
        finished_at=task.get("finished_at"),
        errors=task.get("errors") or None,
    )


@app.get("/api/reports/doctoral/result/{task_id}", response_model=DoctoralReportJobResultResponse)
async def api_get_doctoral_report_job_result(
    task_id: str,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> DoctoralReportJobResultResponse:
    clients = build_clients_or_error(settings)
    try:
        from app.postgres_block import get_report_job

        task = get_report_job(clients.postgres, task_id)
    finally:
        clients.close()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    _assert_doctoral_task_access(task_id=task_id, task=task, user=user)
    if task.get("status") != "completed":
        raise HTTPException(status_code=400, detail=f"Task not completed: {task.get('status')}")
    return DoctoralReportJobResultResponse(task_id=task_id, status="completed", result=task.get("result") or {})


@app.post("/api/reports/generate-doctoral")
async def api_generate_doctoral_report(
    payload: DoctoralReportRequest,
    settings: AppSettings = Depends(get_settings),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Genera informe doctoral formal para Etapa 3 o Etapa 4.
    
    - stage3: Codificación Abierta (códigos, saturación, memos)
    - stage4: Codificación Axial (categorías, comunidades, núcleo)
    
    El informe se guarda tanto en archivo como en la base de datos para
    trazabilidad y análisis histórico.
    """
    from app.doctoral_reports import generate_stage3_report, generate_stage4_report
    from app.postgres_block import save_doctoral_report
    
    try:
        if payload.stage == "stage3":
            result = generate_stage3_report(clients, settings, payload.project)
        elif payload.stage == "stage4":
            result = generate_stage4_report(clients, settings, payload.project)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Etapa no válida: {payload.stage}. Use 'stage3' o 'stage4'."
            )
        
        # Guardar como archivo
        base_dir = Path("reports") / payload.project / "doctoral"
        base_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        filename = f"{timestamp}_doctoral_{payload.stage}.md"
        file_path = base_dir / filename
        
        file_path.write_text(result["content"], encoding="utf-8")
        
        result["path"] = str(file_path)
        result["filename"] = filename
        
        # Sprint 26: Guardar en base de datos para persistencia
        report_id = save_doctoral_report(
            clients.postgres,
            project=payload.project,
            stage=payload.stage,
            content=result["content"],
            stats=result.get("stats"),
            file_path=str(file_path),
        )
        result["report_id"] = report_id
        
        api_logger.info(
            "doctoral.report.generated",
            stage=payload.stage,
            project=payload.project,
            path=str(file_path),
            report_id=report_id
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as exc:
        api_logger.error("doctoral.report.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class DiscoverySaveMemoRequest(BaseModel):
    positive_texts: List[str]
    negative_texts: Optional[List[str]] = None
    target_text: Optional[str] = None
    fragments: List[Dict[str, Any]] = []
    project: str = "default"
    memo_title: Optional[str] = None
    ai_synthesis: Optional[str] = None  # Síntesis generada por IA



@app.post("/api/discovery/save_memo")
async def api_save_discovery_memo(
    payload: DiscoverySaveMemoRequest,
    user: User = Depends(require_auth),
) -> Dict[str, str]:
    """Guarda los resultados de Discovery como memo Markdown."""
    try:
        # Create directory
        base_dir = Path("notes") / payload.project
        base_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        title = payload.memo_title or "_".join(payload.positive_texts[:2])
        safe_title = "".join(c if c.isalnum() else "_" for c in title[:30]).strip("_")
        filename = f"{timestamp}_discovery_{safe_title}.md"
        file_path = base_dir / filename
        
        # Format Content
        lines = [
            f"# Memo de Exploración: {payload.memo_title or ', '.join(payload.positive_texts)}",
            f"**Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Proyecto:** {payload.project}",
            "",
            "## Criterios de Búsqueda",
            f"**Conceptos Positivos:** {', '.join(payload.positive_texts)}",
            f"**Conceptos Negativos:** {', '.join(payload.negative_texts or ['(ninguno)'])}",
            f"**Texto Objetivo:** {payload.target_text or '(ninguno)'}",
            "",
            f"## Fragmentos Encontrados ({len(payload.fragments)})",
        ]
        
        for idx, frag in enumerate(payload.fragments):
            source = frag.get("archivo", "Desconocido")
            text = frag.get("fragmento", "")
            score = frag.get("score", 0)
            lines.append(f"\n### [{idx+1}] {source} (relevancia: {score:.1%})")
            lines.append(f"> {text}")
        
        # Agregar síntesis IA si existe
        if payload.ai_synthesis:
            lines.append("")
            lines.append("## 🧠 Síntesis y Sugerencias (IA)")
            lines.append("")
            for line in payload.ai_synthesis.split('\n'):
                lines.append(line)
            
        lines.append("\n---")
        lines.append("*Generado automáticamente por Discovery Search*")
            
        # Write file
        file_path.write_text("\n".join(lines), encoding="utf-8")
        
        api_logger.info("discovery.memo.saved", path=str(file_path), has_synthesis=bool(payload.ai_synthesis))
        return {"status": "ok", "path": str(file_path), "filename": filename}
        
    except Exception as exc:
        api_logger.error("discovery.memo.save.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/search/discover")
async def api_discover_search(
    payload: DiscoverRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Busqueda exploratoria con triplete (positivo, negativo, target).
    
    Encuentra fragmentos similares a los conceptos positivos pero
    diferentes de los negativos.
    """
    from app.queries import discover_search
    
    clients = build_clients_or_error(settings)
    try:
        api_logger.info(
            "api.discover.start",
            positive_count=len(payload.positive_texts),
            negative_count=len(payload.negative_texts or []),
        )
        
        results = discover_search(
            clients, settings,
            positive_texts=payload.positive_texts,
            negative_texts=payload.negative_texts,
            target_text=payload.target_text,
            top_k=payload.top_k,
            project=payload.project,
        )
        
        api_logger.info("api.discover.complete", results=len(results))
        
        return {"fragments": results, "count": len(results)}
        
    except Exception as exc:
        api_logger.error("api.discover.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()


@app.get("/api/axial/predict")
async def api_axial_predict(
    source_type: str = Query(default="Categoria"),
    target_type: str = Query(default="Codigo"),
    algorithm: str = Query(default="common_neighbors"),
    top_k: int = Query(default=10, ge=1, le=50),
    project: str = Query(default="default"),
    categoria: Optional[str] = Query(default=None),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Predice enlaces faltantes en el grafo axial.
    
    Usa algoritmos de link prediction para sugerir relaciones
    que podrian estar faltando entre categorias y codigos.
    """
    from app.link_prediction import suggest_links, suggest_axial_relations
    
    clients = build_clients_or_error(settings)
    try:
        api_logger.info(
            "api.predict.start",
            algorithm=algorithm,
            source_type=source_type,
            target_type=target_type,
        )
        
        if categoria:
            # Sugerencias especificas para una categoria
            suggestions = suggest_axial_relations(
                clients, settings,
                categoria=categoria,
                project=project,
                top_k=top_k,
            )
        else:
            # Sugerencias generales
            suggestions = suggest_links(
                clients, settings,
                source_type=source_type,
                target_type=target_type,
                algorithm=algorithm,
                top_k=top_k,
                project=project,
            )
        
        api_logger.info("api.predict.complete", suggestions=len(suggestions))
        
        return {"suggestions": suggestions, "algorithm": algorithm}
        
    except Exception as exc:
        api_logger.error("api.predict.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()


@app.get("/api/axial/community-links")
async def api_axial_community_links(
    project: str = Query(default="default"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Detecta enlaces faltantes basandose en comunidades.
    
    Nodos en la misma comunidad (Louvain) que no estan conectados
    son candidatos para nuevas relaciones.
    """
    from app.link_prediction import detect_missing_links_by_community
    
    clients = build_clients_or_error(settings)
    try:
        suggestions = detect_missing_links_by_community(clients, settings, project)
        return {"suggestions": suggestions, "method": "community_based"}
    except Exception as exc:
        api_logger.error("api.community_links.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()


class AnalyzePredictionsRequest(BaseModel):
    """Request para análisis IA de predicciones de enlaces."""
    model_config = ConfigDict(extra="forbid")
    project: str = Field(default="default", description="ID del proyecto")
    algorithm: str = Field(..., description="Algoritmo usado para la predicción")
    suggestions: List[Dict[str, Any]] = Field(..., description="Sugerencias de enlaces")


@app.post("/api/axial/analyze-predictions")
async def api_analyze_predictions(
    payload: AnalyzePredictionsRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Analiza predicciones de enlaces con IA.
    
    Envía las sugerencias de link prediction al LLM para obtener
    una interpretación cualitativa y recomendaciones.
    """
    from app.clients import build_service_clients
    
    ALGORITHM_DESCRIPTIONS = {
        "common_neighbors": "Vecinos Comunes - cuenta nodos compartidos entre dos códigos",
        "jaccard": "Coeficiente Jaccard - mide similitud entre conjuntos de vecinos",
        "adamic_adar": "Adamic-Adar - pondera vecinos comunes por su exclusividad",
        "preferential_attachment": "Preferential Attachment - favorece códigos populares",
        "community_based": "Basado en Comunidades - detecta enlaces intra-comunidad faltantes",
    }
    
    clients = build_service_clients(settings)
    try:
        algorithm_desc = ALGORITHM_DESCRIPTIONS.get(
            payload.algorithm, 
            f"Algoritmo: {payload.algorithm}"
        )
        
        # Preparar contexto de sugerencias
        suggestions_text = []
        for i, sug in enumerate(payload.suggestions[:10], 1):  # Max 10 para el prompt
            source = sug.get("source", "?")
            target = sug.get("target", "?")
            score = sug.get("score", 0)
            suggestions_text.append(f"{i}. {source} → {target} (score: {score:.3f})")
        
        # Sprint 29+: Contrato JSON estructurado con etiquetas epistemológicas (compatible con legacy texto).
        prompt = f"""Analiza las siguientes predicciones de enlaces en un grafo de análisis cualitativo (Teoría Fundamentada).

Algoritmo utilizado: {algorithm_desc}

Sugerencias de relaciones axiales faltantes (IDs 1..{min(len(payload.suggestions), 10)}):
{chr(10).join(suggestions_text)}

Contexto: Estas son relaciones potenciales entre códigos/categorías detectadas algorítmicamente.

IMPORTANTE: Responde ÚNICAMENTE con un JSON válido (sin markdown, sin ```).
La síntesis debe distinguir explícitamente el estatus epistemológico de cada afirmación.
El JSON debe tener esta estructura exacta:

{{
    "memo_sintesis": [
        {{"type": "OBSERVATION", "text": "...", "evidence_ids": [1, 3]}},
        {{"type": "INTERPRETATION", "text": "...", "evidence_ids": [1, 3]}},
        {{"type": "HYPOTHESIS", "text": "...", "evidence_ids": [2]}},
        {{"type": "NORMATIVE_INFERENCE", "text": "...", "evidence_ids": [4]}}
    ]
}}

REGLAS:
1. memo_sintesis: lista de 3-6 statements.
2. type: uno de OBSERVATION | INTERPRETATION | HYPOTHESIS | NORMATIVE_INFERENCE.
3. text: una oración clara (español).
4. evidence_ids: lista de enteros referidos a la numeración de las sugerencias (1..10).
5. PROHIBIDO: OBSERVATION sin evidence_ids no vacíos.
6. Sé conciso: evita listas largas o párrafos extensos."""

        # gpt-5.x models no soportan temperature != 1, omitir el parámetro
        response = clients.aoai.chat.completions.create(
            model=settings.azure.deployment_chat,
            messages=[
                {"role": "system", "content": "Eres un experto en análisis cualitativo y Teoría Fundamentada."},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=600,
            # temperature omitido: gpt-5.x usa default=1
        )
        
        choice = response.choices[0] if response.choices else None
        message = getattr(choice, "message", None)
        message_content = getattr(message, "content", None)
        raw_content = message_content or ""

        # Parsear JSON estructurado (con fallback al texto)
        import json
        import re

        parsed: Optional[Dict[str, Any]] = None
        try:
            clean_content = re.sub(r"^```json?\s*", "", raw_content.strip())
            clean_content = re.sub(r"\s*```$", "", clean_content)
            parsed = json.loads(clean_content)
        except Exception:
            parsed = None

        def _normalize_memo(value: Any) -> tuple[str, List[Dict[str, Any]]]:
            allowed = {"OBSERVATION", "INTERPRETATION", "HYPOTHESIS", "NORMATIVE_INFERENCE"}
            if isinstance(value, str):
                return value.strip(), []
            if not isinstance(value, list):
                return "", []
            out: List[Dict[str, Any]] = []
            lines: List[str] = []
            for item in value:
                if not isinstance(item, dict):
                    continue
                stype = str(item.get("type") or "").strip().upper()
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                if stype not in allowed:
                    stype = "INTERPRETATION"
                evidence_ids: List[int] = []
                raw_ids = item.get("evidence_ids")
                if isinstance(raw_ids, list):
                    for v in raw_ids:
                        try:
                            evidence_ids.append(int(v))
                        except Exception:
                            continue
                # Regla de seguridad: OBSERVATION requiere evidencia.
                if stype == "OBSERVATION" and not evidence_ids:
                    stype = "INTERPRETATION"
                entry: Dict[str, Any] = {"type": stype, "text": text}
                if evidence_ids:
                    entry["evidence_ids"] = evidence_ids
                    lines.append(f"[{stype}] {text} (evid: {', '.join(str(i) for i in evidence_ids)})")
                else:
                    lines.append(f"[{stype}] {text}")
                out.append(entry)
            return "\n".join(lines).strip(), out
        
        api_logger.info(
            "api.analyze_predictions.complete",
            algorithm=payload.algorithm,
            suggestions_count=len(payload.suggestions),
        )
        
        if isinstance(parsed, dict) and parsed.get("memo_sintesis") is not None:
            memo_text, memo_statements = _normalize_memo(parsed.get("memo_sintesis"))
            analysis = memo_text
            structured = True
        else:
            analysis = raw_content
            structured = False
            memo_statements = []

        return {
            # Compatibilidad: se mantiene el texto plano.
            "analysis": analysis,
            # Nuevo: campos estructurados (opcionales para el frontend).
            "structured": structured,
            "memo_statements": memo_statements,
            "algorithm": payload.algorithm,
            "algorithm_description": algorithm_desc,
            "suggestions_analyzed": len(payload.suggestions[:10]),
        }
        
    except Exception as exc:
        api_logger.error("api.analyze_predictions.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()


class AnalyzeDiscoveryRequest(BaseModel):
    """Request para análisis IA de resultados de Discovery."""
    model_config = ConfigDict(extra="forbid")
    project: str = Field(default="default", description="ID del proyecto")
    positive_texts: List[str] = Field(..., description="Conceptos positivos usados")
    negative_texts: List[str] = Field(default=[], description="Conceptos negativos usados")
    target_text: Optional[str] = Field(default=None, description="Texto objetivo opcional")
    fragments: List[Dict[str, Any]] = Field(..., description="Fragmentos encontrados")


@app.post("/api/discovery/analyze")
async def api_discovery_analyze(
    payload: AnalyzeDiscoveryRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Analiza resultados de Discovery con IA.
    
    Genera síntesis temática, códigos sugeridos, memo de descubrimiento
    y sugerencias de conceptos para refinar la búsqueda.
    """
    from app.clients import build_service_clients
    
    clients = build_service_clients(settings)
    try:
        # Preparar fragmentos para el prompt
        fragment_sample = payload.fragments[:8] if payload.fragments else []
        fragments_text = []
        for i, frag in enumerate(fragment_sample, 1):  # Max 8 para el prompt
            fragmento = frag.get("fragmento", "")[:400]
            archivo = frag.get("archivo", "?")
            score = frag.get("score", 0)
            fragments_text.append(f"{i}. [{archivo}] (sim: {score:.1%}) {fragmento}")
        
        positives_str = ", ".join(payload.positive_texts)
        negatives_str = ", ".join(payload.negative_texts) if payload.negative_texts else "ninguno"
        target_str = payload.target_text or "no especificado"
        
        # Sprint 22+: Prompt para JSON estructurado con etiquetas epistemológicas
        prompt = f"""Analiza los resultados de una búsqueda exploratoria (Discovery) en un proyecto de análisis cualitativo.

**Parámetros de búsqueda:**
- Conceptos positivos: {positives_str}
- Conceptos negativos: {negatives_str}
- Texto objetivo: {target_str}

**Fragmentos encontrados:**
{chr(10).join(fragments_text)}

IMPORTANTE: Responde ÚNICAMENTE con un JSON válido (sin markdown, sin ```).
La síntesis debe distinguir explícitamente el estatus epistemológico de cada afirmación.
El JSON debe tener esta estructura exacta:

{{
    "memo_sintesis": [
        {"type": "OBSERVATION", "text": "...", "evidence_ids": [1, 3]},
        {"type": "INTERPRETATION", "text": "...", "evidence_ids": [1, 3]},
        {"type": "HYPOTHESIS", "text": "...", "evidence_ids": [2]}
    ],
  "codigos_sugeridos": ["codigo_uno", "codigo_dos", "codigo_tres"],
  "refinamiento_busqueda": {{
    "positivos": ["término1", "término2"],
    "negativos": ["término_excluir"],
    "target": "término_focalizar"
  }}
}}

REGLAS:
1. memo_sintesis: lista de 3-6 statements. Cada statement incluye:
    - type: uno de OBSERVATION | INTERPRETATION | HYPOTHESIS | NORMATIVE_INFERENCE
    - text: una oración clara (español)
    - evidence_ids: lista de enteros referidos a la numeración de "Fragmentos encontrados" (1..8)
2. PROHIBIDO: OBSERVATION sin evidence_ids no vacíos.
2. codigos_sugeridos: 3-5 códigos en snake_case (ej: identidad_cultural_amenazada)
3. refinamiento_busqueda: sugerencias para próxima búsqueda"""

        # gpt-5.x models no soportan temperature != 1, omitir el parámetro
        response = clients.aoai.chat.completions.create(
            model=settings.azure.deployment_chat,
            messages=[
                {"role": "system", "content": "Eres un experto en análisis cualitativo. Respondes SOLO con JSON válido, sin markdown ni explicaciones adicionales."},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=700,
        )
        
        choice = response.choices[0] if response.choices else None
        message = getattr(choice, "message", None)
        message_content = getattr(message, "content", None)
        raw_content = message_content or ""
        
        # Sprint 22: Parsear JSON estructurado
        import json
        import re
        
        parsed_synthesis = None
        try:
            # Limpiar posibles bloques de código markdown
            clean_content = re.sub(r'^```json?\s*', '', raw_content.strip())
            clean_content = re.sub(r'\s*```$', '', clean_content)
            parsed_synthesis = json.loads(clean_content)
        except json.JSONDecodeError:
            api_logger.warning("api.discovery_analyze.json_parse_failed", raw=raw_content[:200])
            # Fallback: devolver texto sin parsear
            parsed_synthesis = None

        def _normalize_memo(value: Any) -> tuple[str, List[Dict[str, Any]]]:
            allowed = {"OBSERVATION", "INTERPRETATION", "HYPOTHESIS", "NORMATIVE_INFERENCE"}
            if isinstance(value, str):
                return value.strip(), []
            if not isinstance(value, list):
                return "", []
            out: List[Dict[str, Any]] = []
            lines: List[str] = []
            for item in value:
                if not isinstance(item, dict):
                    continue
                stype = str(item.get("type") or "").strip().upper()
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                if stype not in allowed:
                    stype = "INTERPRETATION"
                evidence_ids: List[int] = []
                raw_ids = item.get("evidence_ids")
                if isinstance(raw_ids, list):
                    for v in raw_ids:
                        try:
                            evidence_ids.append(int(v))
                        except Exception:
                            continue
                if stype == "OBSERVATION" and not evidence_ids:
                    stype = "INTERPRETATION"
                entry: Dict[str, Any] = {"type": stype, "text": text}
                if evidence_ids:
                    entry["evidence_ids"] = evidence_ids
                    lines.append(f"[{stype}] {text} (evid: {', '.join(str(i) for i in evidence_ids)})")
                else:
                    lines.append(f"[{stype}] {text}")
                out.append(entry)
            return "\n".join(lines).strip(), out
        
        api_logger.info(
            "api.discovery_analyze.complete",
            positive_count=len(payload.positive_texts),
            fragment_count=len(payload.fragments),
            parsed=parsed_synthesis is not None,
        )
        
        # Sprint 22: Respuesta estructurada con fallback
        if parsed_synthesis:
            memo_text, memo_statements = _normalize_memo(parsed_synthesis.get("memo_sintesis"))
            return {
                # Compatibilidad: el campo "analysis" se mantiene como texto.
                "analysis": memo_text,
                "structured": True,
                # Nuevo: lista de statements etiquetados.
                "memo_statements": memo_statements,
                "codigos_sugeridos": parsed_synthesis.get("codigos_sugeridos", []),
                "refinamiento_busqueda": parsed_synthesis.get("refinamiento_busqueda", {}),
                "positive_texts": payload.positive_texts,
                "negative_texts": payload.negative_texts,
                "target_text": payload.target_text,
                "fragments_analyzed": len(fragment_sample),
            }
        else:
            return {
                "analysis": raw_content,
                "structured": False,
                "memo_statements": [],
                "codigos_sugeridos": [],
                "refinamiento_busqueda": {},
                "positive_texts": payload.positive_texts,
                "negative_texts": payload.negative_texts,
                "target_text": payload.target_text,
                "fragments_analyzed": len(fragment_sample),
            }
        
    except Exception as exc:
        api_logger.error("api.discovery_analyze.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()


# =============================================================================
# Sprint 24: Discovery Navigation Log - Muestreo Teórico
# =============================================================================

class LogNavigationRequest(BaseModel):
    project: str = Field(..., description="Project ID")
    positivos: List[str] = Field(..., description="Positive concepts used")
    negativos: List[str] = Field(default=[], description="Negative concepts used")
    target_text: Optional[str] = Field(default=None, description="Target text")
    fragments_count: int = Field(..., description="Number of fragments found")
    codigos_sugeridos: Optional[List[str]] = Field(default=None, description="AI suggested codes")
    refinamientos_aplicados: Optional[Dict[str, Any]] = Field(default=None, description="Applied refinements")
    ai_synthesis: Optional[str] = Field(default=None, description="AI synthesis text")
    action_taken: str = Field(default="search", description="Action: search, refine, send_codes")
    busqueda_origen_id: Optional[str] = Field(default=None, description="Parent search UUID")


@app.post("/api/discovery/log-navigation")
async def api_log_discovery_navigation(
    payload: LogNavigationRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Sprint 24: Log a discovery navigation step for theoretical sampling traceability.
    """
    from app.postgres_block import log_discovery_navigation
    
    clients = build_clients_or_error(settings)
    try:
        busqueda_id = log_discovery_navigation(
            clients.postgres,
            project=payload.project,
            positivos=payload.positivos,
            negativos=payload.negativos,
            target_text=payload.target_text,
            fragments_count=payload.fragments_count,
            codigos_sugeridos=payload.codigos_sugeridos,
            refinamientos_aplicados=payload.refinamientos_aplicados,
            ai_synthesis=payload.ai_synthesis,
            action_taken=payload.action_taken,
            busqueda_origen_id=payload.busqueda_origen_id,
        )
        
        api_logger.info(
            "api.discovery.navigation_logged",
            project=payload.project,
            action=payload.action_taken,
            busqueda_id=busqueda_id,
        )
        
        return {
            "success": True,
            "busqueda_id": busqueda_id,
            "action_taken": payload.action_taken,
        }
    except Exception as exc:
        api_logger.error("api.discovery.navigation_log_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()


@app.get("/api/discovery/navigation-history")
async def api_get_discovery_navigation_history(
    project: str = Query(..., description="Project ID"),
    limit: int = Query(default=50, ge=1, le=200, description="Max entries"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Sprint 24: Get discovery navigation history for a project.
    
    Returns chronological list of searches with their refinements.
    """
    from app.postgres_block import get_discovery_navigation_history
    
    clients = build_clients_or_error(settings)
    try:
        history = get_discovery_navigation_history(
            clients.postgres,
            project=project,
            limit=limit,
        )
        
        return {
            "project": project,
            "history": history,
            "count": len(history),
        }
    except Exception as exc:
        api_logger.error("api.discovery.navigation_history_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()


# =============================================================================
# Etapa 2: Familiarización - Review fragments before coding
# =============================================================================

@app.get("/api/familiarization/fragments")
async def api_get_familiarization_fragments(
    project: str = Query(default="default"),
    file_filter: Optional[str] = Query(default=None, description="Filter by archivo name"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Obtiene fragmentos ingestados para revisión/familiarización.
    
    Retorna fragmentos con información de hablante para que el investigador
    pueda revisar las transcripciones antes de codificar.
    """
    from app.clients import build_service_clients
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    from typing import Any, List, cast
    
    clients = build_service_clients(settings)
    try:
        # Build filter for project (stored as project_id in Qdrant)
        filter_conditions = [
            FieldCondition(key="project_id", match=MatchValue(value=project))
        ]
        if file_filter:
            filter_conditions.append(
                FieldCondition(key="archivo", match=MatchValue(value=file_filter))
            )
        
        points_filter = Filter(must=cast(List[Any], filter_conditions))
        
        # Fetch from Qdrant
        points, _ = clients.qdrant.scroll(
            collection_name=settings.qdrant.collection,
            scroll_filter=points_filter,
            limit=500,  # Max fragments to return
            with_payload=True,
            with_vectors=False,
        )
        
        # Process fragments
        fragments = []
        files_set = set()
        
        for point in points:
            payload = point.payload or {}
            archivo = payload.get("archivo", "unknown")
            files_set.add(archivo)
            
            fragments.append({
                "id": str(point.id),
                "text": payload.get("fragmento", ""),
                "speaker": payload.get("speaker", "interviewee"),
                "archivo": archivo,
                "fragmento_idx": payload.get("fragmento_idx", 0),
                "char_count": len(payload.get("fragmento", "")),
                "interviewee_tokens": payload.get("interviewee_tokens", 0),
                "interviewer_tokens": payload.get("interviewer_tokens", 0),
            })
        
        # Sort by archivo and index
        fragments.sort(key=lambda x: (x["archivo"], x["fragmento_idx"]))
        
        api_logger.info(
            "api.familiarization.fragments",
            project=project,
            count=len(fragments),
        )
        
        return {
            "fragments": fragments,
            "total": len(fragments),
            "files": sorted(list(files_set)),
            "project": project,
        }
        
    except Exception as exc:
        api_logger.error("api.familiarization.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()


class ConfirmRelationshipRequest(BaseModel):
    source: str
    target: str
    relation_type: str = "partede"
    project: str = "default"


@app.get("/api/axial/hidden-relationships")
async def api_hidden_relationships(
    project: str = Query(default="default"),
    top_k: int = Query(default=20, ge=1, le=50),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Descubre relaciones ocultas/latentes entre códigos.
    
    Combina 3 métodos de descubrimiento:
    1. Co-ocurrencia en fragmentos
    2. Categoría compartida
    3. Misma comunidad (Louvain)
    
    Retorna sugerencias con score y razón.
    """
    from app.link_prediction import discover_hidden_relationships
    
    clients = build_clients_or_error(settings)
    try:
        api_logger.info("api.hidden_relationships.start", project=project)
        suggestions = discover_hidden_relationships(clients, settings, project, top_k)
        
        # Agrupar por método
        by_method = {}
        for s in suggestions:
            method = s.get("method", "unknown")
            if method not in by_method:
                by_method[method] = []
            by_method[method].append(s)
        
        return {
            "suggestions": suggestions,
            "by_method": by_method,
            "total": len(suggestions),
        }
    except Exception as exc:
        api_logger.error("api.hidden_relationships.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()


@app.post("/api/axial/confirm-relationship")
async def api_confirm_relationship(
    payload: ConfirmRelationshipRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Confirma una relación oculta descubierta.
    
    Crea la relación en Neo4j con origen='descubierta' para
    distinguirla de las relaciones creadas manualmente.
    """
    from app.link_prediction import confirm_hidden_relationship
    
    clients = build_clients_or_error(settings)
    try:
        api_logger.info(
            "api.confirm_relationship.start",
            source=payload.source,
            target=payload.target,
            tipo=payload.relation_type,
        )
        result = confirm_hidden_relationship(
            clients, settings,
            source=payload.source,
            target=payload.target,
            relation_type=payload.relation_type,
            project=payload.project,
        )
        
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("message"))
            
        return result
    except HTTPException:
        raise
    except Exception as exc:
        api_logger.error("api.confirm_relationship.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()


# =============================================================================
# MULTI-USER COLLABORATION (E3)
# =============================================================================

from app.postgres_block import (
    add_project_member,
    assign_org_users_to_project,
    get_project_members,
    get_project_db,
    get_user_project_role,
    check_project_permission,
    get_user_projects,
    log_project_action,
    get_project_audit_log,
    PROJECT_ROLES,
)


class AddMemberRequest(BaseModel):
    """Request para agregar miembro a proyecto."""
    user_id: str = Field(..., description="ID del usuario a agregar")
    role: str = Field(default="lector", description="Rol: admin, codificador, lector")


class SyncOrgMembersRequest(BaseModel):
    """Request para sincronizar miembros por organización."""
    org_id: Optional[str] = Field(default=None, description="Organización a sincronizar")
    default_role: str = Field(default="codificador", description="Rol por defecto si no se usa rol del usuario")
    use_user_role: bool = Field(default=True, description="Usar rol del usuario para el rol de proyecto")
    include_inactive: bool = Field(default=False, description="Incluir usuarios inactivos")


@app.get("/api/projects/{project_id}/members")
async def api_get_project_members(
    project_id: str,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Obtiene los miembros de un proyecto."""
    try:
        project = resolve_project(project_id, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        members = get_project_members(clients.postgres, project)
    finally:
        clients.close()
    
    return {"project": project, "members": members, "roles_available": list(PROJECT_ROLES)}


@app.post("/api/projects/{project_id}/members")
async def api_add_project_member(
    project_id: str,
    payload: AddMemberRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Agrega un miembro al proyecto (requiere rol admin)."""
    try:
        project = resolve_project(project_id, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        # Verificar que el usuario actual es admin
        if not check_project_permission(clients.postgres, project, user.user_id, "admin"):
            # Si no hay miembros, permitir que el primero sea admin automáticamente
            existing = get_project_members(clients.postgres, project)
            if len(existing) == 0:
                # Auto-agregar al creador como admin
                add_project_member(clients.postgres, project, user.user_id, "admin", added_by="system")
            else:
                raise HTTPException(status_code=403, detail="Solo administradores pueden agregar miembros")
        
        # Agregar el nuevo miembro
        member = add_project_member(
            clients.postgres, project, payload.user_id, payload.role, added_by=user.user_id
        )
        
        # Registrar en audit log
        log_project_action(
            clients.postgres, project, user.user_id, "add_member",
            entity_type="member", entity_id=payload.user_id,
            details={"role": payload.role}
        )
    finally:
        clients.close()
    
    return {"status": "ok", "member": member}


@app.post("/api/projects/{project_id}/members/sync-org")
async def api_sync_project_org_members(
    project_id: str,
    payload: SyncOrgMembersRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Sincroniza miembros del proyecto según organización (admin)."""
    try:
        project = resolve_project(project_id, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    org_id = payload.org_id or user.organization_id
    if org_id != user.organization_id:
        raise HTTPException(status_code=403, detail="No autorizado para sincronizar otra organización")

    clients = build_clients_or_error(settings)
    try:
        project_entry = get_project_db(clients.postgres, project)
        if project_entry and project_entry.get("org_id") and project_entry.get("org_id") != org_id:
            raise HTTPException(status_code=403, detail="Proyecto fuera de la organización")

        if not check_project_permission(clients.postgres, project, user.user_id, "admin"):
            if "admin" not in {r.lower() for r in (user.roles or [])}:
                raise HTTPException(status_code=403, detail="Solo administradores pueden sincronizar miembros")

        result = assign_org_users_to_project(
            clients.postgres,
            project,
            org_id,
            default_role=payload.default_role,
            use_user_role=payload.use_user_role,
            include_inactive=payload.include_inactive,
            added_by=user.user_id,
        )

        log_project_action(
            clients.postgres,
            project,
            user.user_id,
            "sync_org_members",
            entity_type="organization",
            entity_id=org_id,
            details={
                "members_assigned": result.get("members_assigned"),
                "users_total": result.get("users_total"),
                "use_user_role": payload.use_user_role,
                "default_role": payload.default_role,
                "include_inactive": payload.include_inactive,
            },
        )
    finally:
        clients.close()

    return {"status": "ok", "result": result}


@app.delete("/api/projects/{project_id}/members/{member_user_id}")
async def api_remove_project_member(
    project_id: str,
    member_user_id: str,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Elimina un miembro del proyecto (requiere rol admin)."""
    try:
        project = resolve_project(project_id, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        # Verificar permisos
        if not check_project_permission(clients.postgres, project, user.user_id, "admin"):
            raise HTTPException(status_code=403, detail="Solo administradores pueden eliminar miembros")
        
        # No permitir eliminarse a sí mismo
        if member_user_id == user.user_id:
            raise HTTPException(status_code=400, detail="No puedes eliminarte a ti mismo del proyecto")
        
        # Eliminar
        sql = "DELETE FROM project_members WHERE project_id = %s AND user_id = %s"
        with clients.postgres.cursor() as cur:
            cur.execute(sql, (project, member_user_id))
        clients.postgres.commit()
        
        # Audit log
        log_project_action(
            clients.postgres, project, user.user_id, "remove_member",
            entity_type="member", entity_id=member_user_id
        )
    finally:
        clients.close()
    
    return {"status": "ok", "removed": member_user_id}


@app.get("/api/users/me/projects")
async def api_get_my_projects(
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Obtiene los proyectos a los que el usuario tiene acceso."""
    clients = build_clients_or_error(settings)
    try:
        projects = get_user_projects(clients.postgres, user.user_id)
    finally:
        clients.close()
    
    return {"user_id": user.user_id, "projects": projects}


@app.get("/api/projects/{project_id}/audit")
async def api_get_project_audit(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    action: Optional[str] = Query(default=None),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Obtiene el historial de acciones del proyecto."""
    try:
        project = resolve_project(project_id, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        # Verificar acceso al proyecto
        if not check_project_permission(clients.postgres, project, user.user_id, "lector"):
            raise HTTPException(status_code=403, detail="No tienes acceso a este proyecto")
        
        log = get_project_audit_log(clients.postgres, project, limit=limit, action_filter=action)
    finally:
        clients.close()
    
    return {"project": project, "audit_log": log, "total": len(log)}


# =============================================================================
# ENDPOINTS DE INFORMES (Sprint B)
# =============================================================================

@app.get("/api/reports/interviews")
async def api_get_interview_reports(
    project: str = Query(default="default", description="ID del proyecto"),
    limit: int = Query(default=50, ge=1, le=100),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Lista informes de análisis por entrevista.
    
    Retorna métricas de codificación para cada entrevista analizada,
    incluyendo: códigos nuevos/reutilizados, categorías, saturación.
    """
    from app.reports import get_interview_reports
    
    clients = build_clients_or_error(settings)
    try:
        reports = get_interview_reports(clients.postgres, project, limit=limit)
        return {
            "project": project,
            "reports": [r.to_dict() for r in reports],
            "total": len(reports),
        }
    finally:
        clients.close()


@app.get("/api/reports/stage4-summary")
async def api_get_stage4_summary(
    project: str = Query(default="default", description="ID del proyecto"),
    clients: PgOnlyClients = Depends(get_pg_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Genera resumen consolidado de Etapa 4 para transición a Etapa 5.
    
    Incluye:
    - Total de entrevistas, códigos, categorías
    - Score de saturación
    - Informes por entrevista resumidos
    - Candidatos a núcleo selectivo (si disponibles)
    """
    from app.reports import generate_stage4_summary
    
    summary = await run_pg_query_with_timeout(generate_stage4_summary, clients.postgres, project)
    return summary.to_dict()


@app.post("/api/reports/stage4-final")
async def api_generate_stage4_final_report(
    project: str = Query(default="default", description="ID del proyecto"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Genera informe final de Etapa 4 con análisis IA.
    
    Este endpoint genera un informe completo para la transición a Etapa 5:
    - Métricas consolidadas
    - Candidatos a núcleo selectivo (basado en densidad de relaciones)
    - Análisis IA de patrones emergentes
    - Recomendaciones para selección del núcleo
    
    El informe se puede exportar como Markdown para documentación.
    """
    from app.reports import generate_stage4_final_report
    
    clients = build_clients_or_error(settings)
    try:
        report = generate_stage4_final_report(
            pg_conn=clients.postgres,
            neo4j_driver=clients.neo4j,
            database=settings.neo4j.database,
            aoai_client=clients.aoai,
            deployment_chat=settings.azure.deployment_chat,
            project_id=project,
        )
        return report
    except Exception as exc:
        api_logger.error("api.stage4_final.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()


# -----------------------------------------------------------------------------
# Stage4 final report jobs (async)
# -----------------------------------------------------------------------------

def _run_stage4_final_report_task(*, task_id: str, project: str, settings: AppSettings) -> None:
    from app.reports import generate_stage4_final_report
    from app.postgres_block import update_report_job
    from app.blob_storage import CONTAINER_REPORTS, upload_local_path

    clients = build_clients_or_error(settings)
    try:
        try:
            update_report_job(
                clients.postgres,
                task_id=task_id,
                status="running",
                message="Generando informe final Etapa 4...",
                started_at=datetime.now().isoformat(),
            )
        except Exception:
            pass

        report = generate_stage4_final_report(
            pg_conn=clients.postgres,
            neo4j_driver=clients.neo4j,
            database=settings.neo4j.database,
            aoai_client=clients.aoai,
            deployment_chat=settings.azure.deployment_chat,
            project_id=project,
        )

        base_dir = Path("reports") / project
        base_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        filename = f"{timestamp}_stage4_final.json"
        file_path = base_dir / filename
        file_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        blob_url: Optional[str] = None
        try:
            blob_name = f"{project}/{filename}"
            blob_url = upload_local_path(
                container=CONTAINER_REPORTS,
                blob_name=blob_name,
                file_path=str(file_path),
                content_type="application/json",
            )
        except Exception as exc:
            api_logger.warning("stage4_final.blob_upload_failed", error=str(exc)[:200], task_id=task_id)

        result = {
            "project": project,
            "path": str(file_path),
            "filename": filename,
            "report": report,
            "blob_url": blob_url,
        }

        update_report_job(
            clients.postgres,
            task_id=task_id,
            status="completed",
            message="Informe final Etapa 4 generado",
            result=result,
            result_path=str(file_path),
            finished_at=datetime.now().isoformat(),
        )
    except Exception as exc:
        try:
            update_report_job(
                clients.postgres,
                task_id=task_id,
                status="error",
                message=str(exc),
                errors=[str(exc)],
                finished_at=datetime.now().isoformat(),
            )
        except Exception:
            pass
        api_logger.error("stage4_final.job_error", error=str(exc), task_id=task_id)
    finally:
        clients.close()


@app.post("/api/reports/stage4-final/execute")
async def api_execute_stage4_final_report_job(
    background_tasks: BackgroundTasks,
    project: str = Query(default="default", description="ID del proyecto"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_role(["admin", "analyst"])),
) -> Dict[str, Any]:
    task_id = f"stage4final_{project}_{uuid.uuid4().hex[:12]}"
    auth = {
        "user_id": str(user.user_id),
        "org": str(user.organization_id),
        "roles": list(user.roles or []),
    }
    # Persist job row (durable)
    try:
        from app.postgres_block import create_report_job

        clients = build_clients_or_error(settings)
        try:
            create_report_job(
                clients.postgres,
                task_id=task_id,
                job_type="stage4_final",
                project_id=project,
                payload={"project": project},
                auth=auth,
                message="Inicializando...",
            )
        finally:
            clients.close()
    except Exception as exc:
        api_logger.warning("stage4_final.job_persist_failed", error=str(exc), task_id=task_id)

    api_logger.info("stage4_final.job_started", task_id=task_id, project=project)
    background_tasks.add_task(_run_stage4_final_report_task, task_id=task_id, project=project, settings=settings)
    return {"task_id": task_id, "status": "started"}


@app.get("/api/reports/stage4-final/status/{task_id}")
async def api_get_stage4_final_report_job_status(
    task_id: str,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    clients = build_clients_or_error(settings)
    try:
        from app.postgres_block import get_report_job

        task = get_report_job(clients.postgres, task_id)
    finally:
        clients.close()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    _assert_doctoral_task_access(task_id=task_id, task=task, user=user)
    return {
        "task_id": task_id,
        "status": task.get("status") or "pending",
        "project": task.get("project_id") or "default",
        "message": task.get("message"),
        "started_at": task.get("started_at") or task.get("created_at"),
        "finished_at": task.get("finished_at"),
        "errors": task.get("errors") or None,
    }


@app.get("/api/reports/stage4-final/result/{task_id}")
async def api_get_stage4_final_report_job_result(
    task_id: str,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    clients = build_clients_or_error(settings)
    try:
        from app.postgres_block import get_report_job

        task = get_report_job(clients.postgres, task_id)
    finally:
        clients.close()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    _assert_doctoral_task_access(task_id=task_id, task=task, user=user)
    if task.get("status") != "completed":
        raise HTTPException(status_code=400, detail=f"Task not completed: {task.get('status')}")
    return {"task_id": task_id, "status": "completed", "result": task.get("result") or {}}


@app.get("/api/reports/nucleus-candidates")
async def api_get_nucleus_candidates(
    project: str = Query(default="default", description="ID del proyecto"),
    top_k: int = Query(default=5, ge=1, le=20),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Lista candidatas a categoría núcleo selectivo.
    
    Identifica las categorías con mayor densidad de relaciones y centralidad
    como candidatas para la Etapa 5.
    """
    from app.reports import identify_nucleus_candidates
    
    clients = build_clients_or_error(settings)
    try:
        candidates = identify_nucleus_candidates(
            clients.neo4j,
            settings.neo4j.database,
            project,
            top_k=top_k,
        )
        return {
            "project": project,
            "candidates": candidates,
            "total": len(candidates),
        }
    finally:
        clients.close()


@app.get("/api/reports/artifacts")
async def api_list_report_artifacts(
    project: str = Query(..., description="ID del proyecto"),
    limit: int = Query(default=50, ge=1, le=200),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Lista artefactos recientes (FS + DB) para la vista Reportes.

    Incluye (best-effort): GraphRAG reports, discovery/runner memos, runner post-mortems,
    reportes por entrevista (DB) y reportes doctorales.
    """
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    clients = build_clients_or_error(settings)
    try:
        from app.report_artifacts import list_recent_report_artifacts

        artifacts = list_recent_report_artifacts(clients.postgres, project_id, limit=limit)
        return {
            "project": project_id,
            "artifacts": artifacts,
            "count": len(artifacts),
        }
    finally:
        clients.close()


@app.get("/api/reports/artifacts/download")
async def api_download_report_artifact(
    project: str = Query(..., description="ID del proyecto"),
    path: str = Query(..., description="Ruta relativa del artefacto (ej: reports/<project>/x.md)"),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_role(["admin", "analyst"])),
) -> Any:
    """Descarga segura de un artefacto (previene path traversal).

    Permitido únicamente bajo roots conocidos del proyecto:
    - reports/<project>/
    - reports/runner/<project>/
    - logs/runner_reports/<project>/
    - logs/runner_checkpoints/<project>/
    """
    try:
        project_id = resolve_project(project, allow_create=False, pg=clients.postgres)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="Missing required query param: path")

    rel_norm = path.replace("\\", "/").lstrip("/")
    target_rel = Path(rel_norm)

    if target_rel.is_absolute():
        raise HTTPException(status_code=400, detail="Absolute paths are not allowed")

    target = target_rel.resolve()
    allowed_roots = [
        (Path("reports") / project_id).resolve(),
        (Path("reports") / "runner" / project_id).resolve(),
        (Path("logs") / "runner_reports" / project_id).resolve(),
        (Path("logs") / "runner_checkpoints" / project_id).resolve(),
    ]

    def _is_under_allowed_root(candidate: Path) -> bool:
        for root in allowed_roots:
            if root == candidate or root in candidate.parents:
                return True
        return False

    if not _is_under_allowed_root(target):
        raise HTTPException(status_code=400, detail="Invalid artifact path")

    # Prefer Azure Blob when a matching report job provides blob_url.
    # This allows secure downloads even when the container is private.
    try:
        from app.blob_storage import download_by_url

        with clients.postgres.cursor() as cur:
            cur.execute(
                """
                SELECT result->>'blob_url'
                  FROM report_jobs
                 WHERE project_id = %s
                   AND replace(COALESCE(result_path,''),'\\\\','/') = %s
                 ORDER BY updated_at DESC
                 LIMIT 1
                """,
                (project_id, rel_norm),
            )
            row = cur.fetchone()
        blob_url = (row[0] if row else None)
        if isinstance(blob_url, str) and blob_url.strip():
            data = download_by_url(blob_url)
            suffix = target.suffix.lower()
            if suffix in {".md", ".markdown"}:
                media_type = "text/markdown"
            elif suffix == ".json":
                media_type = "application/json"
            elif suffix == ".csv":
                media_type = "text/csv"
            else:
                media_type = "application/octet-stream"
            headers = {"Content-Disposition": f'attachment; filename="{target.name}"'}
            return Response(content=data, media_type=media_type, headers=headers)
    except Exception as exc:
        api_logger.debug("reports.artifact.blob_fallback", error=str(exc)[:200], project=project_id)

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")

    suffix = target.suffix.lower()
    if suffix in {".md", ".markdown"}:
        media_type = "text/markdown"
    elif suffix == ".json":
        media_type = "application/json"
    elif suffix == ".csv":
        media_type = "text/csv"
    else:
        media_type = "application/octet-stream"

    return FileResponse(path=str(target), media_type=media_type, filename=target.name)


@app.post("/api/reports/product/generate")
async def api_generate_product_artifacts(
    project: str = Query(..., description="ID del proyecto"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Genera artefactos 'producto' de alto nivel.

    Archivos generados bajo reports/<project>/:
    - executive_summary.md
    - top_10_insights.json
    - open_questions.md
    - product_manifest.json

    Nota: Los artefactos también aparecerán en /api/reports/artifacts.
    """
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    clients = build_clients_or_error(settings)
    try:
        from app.product_artifacts import generate_and_write_product_artifacts
        try:
            return generate_and_write_product_artifacts(
                clients,
                settings,
                project_id,
                changed_by=getattr(user, "user_id", None),
            )
        except Exception as exc:
            # If the new product contracts fail hard validation, surface a user-friendly message.
            try:
                from pydantic import ValidationError

                if isinstance(exc, (ValidationError, ValueError)):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid product artifact payload: {str(exc)}",
                    ) from exc
            except Exception:
                # If pydantic isn't available for some reason, fall through.
                pass
            raise
    finally:
        clients.close()


@app.get("/api/reports/product/latest")
async def api_get_latest_product_artifacts(
    project: str = Query(..., description="ID del proyecto"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Devuelve contenido de los artefactos producto si existen (best-effort)."""
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    base = Path("reports") / project_id
    exec_path = base / "executive_summary.md"
    top_path = base / "top_10_insights.json"
    open_path = base / "open_questions.md"
    manifest_path = base / "product_manifest.json"

    def _read_text(p: Path) -> Optional[str]:
        try:
            if not p.exists():
                return None
            return p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None

    def _read_json(p: Path) -> Optional[Any]:
        try:
            if not p.exists():
                return None
            return json.loads(p.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            return None

    return {
        "project": project_id,
        "executive_summary": _read_text(exec_path),
        "top_10_insights": _read_json(top_path),
        "open_questions": _read_text(open_path),
        "manifest": _read_json(manifest_path),
        "paths": {
            "executive_summary": str(exec_path.as_posix()),
            "top_10_insights": str(top_path.as_posix()),
            "open_questions": str(open_path.as_posix()),
            "manifest": str(manifest_path.as_posix()),
        },
    }


@app.get("/api/reports/jobs")
async def api_list_report_jobs(
    project: str = Query(..., description="ID del proyecto"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100000),
    status: Optional[str] = Query(default=None, description="Opcional: filtrar por status (pending|running|completed|error)"),
    job_type: Optional[str] = Query(default=None, description="Opcional: filtrar por tipo de job"),
    task_id: Optional[str] = Query(default=None, description="Opcional: filtrar por task_id exacto"),
    task_id_prefix: Optional[str] = Query(default=None, description="Opcional: filtrar por task_id (prefijo)"),
    q: Optional[str] = Query(default=None, description="Opcional: búsqueda de texto en message"),
    user_id: Optional[str] = Query(default=None, description="Opcional: filtrar por user_id (solo admin o mismo usuario)"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_role(["admin", "analyst"])),
) -> Dict[str, Any]:
    """List async report jobs (durable) for Reportes v2 history."""
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Analysts can list project jobs, but cannot explicitly filter to other users.
    if user_id and str(user_id) != str(user.user_id) and not _user_is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: cannot query other users")

    svc = build_clients_or_error(settings)
    try:
        from app.postgres_block import list_report_jobs

        jobs = list_report_jobs(
            svc.postgres,
            project_id=project_id,
            limit=int(limit),
            offset=int(offset),
            user_id=str(user_id) if user_id else None,
            status=str(status) if status else None,
            job_type=str(job_type) if job_type else None,
            task_id=str(task_id) if task_id else None,
            task_id_prefix=str(task_id_prefix) if task_id_prefix else None,
            q=str(q) if q else None,
        )
        next_offset = int(offset) + len(jobs)
        has_more = len(jobs) == int(limit)
        return {
            "project": project_id,
            "jobs": jobs,
            "count": len(jobs),
            "limit": int(limit),
            "offset": int(offset),
            "next_offset": next_offset,
            "has_more": has_more,
            "filters": {
                "status": status,
                "job_type": job_type,
                "user_id": user_id,
                "task_id": task_id,
                "task_id_prefix": task_id_prefix,
                "q": q,
            },
        }
    finally:
        svc.close()


@app.get("/api/reports/blob/download")
async def api_download_report_blob_by_url(
    url: str = Query(..., description="Full Azure Blob URL (used to locate container/blob)."),
    filename: Optional[str] = Query(default=None, description="Optional filename override for Content-Disposition"),
    user: User = Depends(require_role(["admin", "analyst"])),
) -> Response:
    """Proxy-download a blob by its URL.

    Uses the server-side storage connection string, so it works for private containers.
    This is intended for Reportes v2 job history downloads when only blob_url is known.
    """
    try:
        from urllib.parse import urlparse

        from app.blob_storage import download_by_url

        data = download_by_url(url)

        inferred = Path(urlparse(url).path or "").name
        name = filename or inferred or "report_blob.bin"

        suffix = Path(name).suffix.lower()
        if suffix in {".md", ".markdown"}:
            media_type = "text/markdown"
        elif suffix == ".json":
            media_type = "application/json"
        elif suffix == ".csv":
            media_type = "text/csv"
        else:
            media_type = "application/octet-stream"

        headers = {"Content-Disposition": f'attachment; filename="{name}"'}
        return Response(content=data, media_type=media_type, headers=headers)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        api_logger.warning("reports.blob_download_failed", error=str(exc)[:200])
        raise HTTPException(status_code=502, detail="Failed to download blob") from exc


# ---------- Analytics ----------


class AnalyticsEvent(BaseModel):
    """Evento de analytics de frontend."""
    event_type: str = Field(..., pattern="^(click|navigation|action|error)$")
    element_id: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None
    page: Optional[str] = None
    session_id: Optional[str] = None


class AnalyticsTrackRequest(BaseModel):
    """Batch de eventos de analytics."""
    model_config = ConfigDict(extra="forbid")
    events: List[AnalyticsEvent]


def _ensure_analytics_table(pg_conn) -> None:
    """Crea tabla de analytics si no existe."""
    with pg_conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ui_analytics (
                id SERIAL PRIMARY KEY,
                event_type VARCHAR(50) NOT NULL,
                element_id VARCHAR(255) NOT NULL,
                event_timestamp TIMESTAMPTZ NOT NULL,
                session_id VARCHAR(100),
                page VARCHAR(255),
                metadata JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        # Index for querying by time and event type
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_analytics_event_type 
            ON ui_analytics (event_type, event_timestamp DESC)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_analytics_session 
            ON ui_analytics (session_id, event_timestamp DESC)
        """)
    pg_conn.commit()


@app.post("/api/analytics/track")
async def api_analytics_track(
    payload: AnalyticsTrackRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Recibe batch de eventos de analytics desde el frontend.
    
    Los eventos se almacenan en PostgreSQL para análisis posterior.
    """
    if not payload.events:
        return {"tracked": 0}
    
    clients = build_clients_or_error(settings)
    try:
        _ensure_analytics_table(clients.postgres)
        
        with clients.postgres.cursor() as cur:
            for event in payload.events:
                cur.execute(
                    """
                    INSERT INTO ui_analytics 
                    (event_type, element_id, event_timestamp, session_id, page, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        event.event_type,
                        event.element_id,
                        event.timestamp,
                        event.session_id,
                        event.page,
                        json.dumps(event.metadata) if event.metadata else None,
                    )
                )
        clients.postgres.commit()
        
        api_logger.info(
            "analytics.track",
            events=len(payload.events),
            session_id=payload.events[0].session_id if payload.events else None,
        )
        
        return {"tracked": len(payload.events)}
    except Exception as exc:
        api_logger.warning("analytics.track.error", error=str(exc))
        # Don't fail the request - analytics should be fire-and-forget
        return {"tracked": 0, "error": "failed_to_persist"}
    finally:
        clients.close()


@app.get("/api/analytics/summary")
async def api_analytics_summary(
    project: Optional[str] = None,
    days: int = Query(7, ge=1, le=90),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Resumen de analytics de los últimos N días.
    """
    clients = build_clients_or_error(settings)
    try:
        _ensure_analytics_table(clients.postgres)
        
        with clients.postgres.cursor() as cur:
            # Event counts by type
            cur.execute("""
                SELECT event_type, COUNT(*) as count
                FROM ui_analytics
                WHERE event_timestamp > NOW() - INTERVAL '%s days'
                GROUP BY event_type
                ORDER BY count DESC
            """, (days,))
            by_type = [{"type": row[0], "count": row[1]} for row in cur.fetchall()]
            
            # Top clicked elements
            cur.execute("""
                SELECT element_id, COUNT(*) as count
                FROM ui_analytics
                WHERE event_type = 'click'
                  AND event_timestamp > NOW() - INTERVAL '%s days'
                GROUP BY element_id
                ORDER BY count DESC
                LIMIT 20
            """, (days,))
            top_clicks = [{"element": row[0], "count": row[1]} for row in cur.fetchall()]
            
            # Unique sessions
            cur.execute("""
                SELECT COUNT(DISTINCT session_id)
                FROM ui_analytics
                WHERE event_timestamp > NOW() - INTERVAL '%s days'
            """, (days,))
            session_row = cur.fetchone()
            unique_sessions = (session_row[0] if session_row else 0) or 0
        
        return {
            "period_days": days,
            "by_event_type": by_type,
            "top_clicks": top_clicks,
            "unique_sessions": unique_sessions,
        }
    finally:
        clients.close()


# NOTE: Candidate code endpoints are defined above (lines ~2492-2622)
# Removed duplicate definitions that were causing argument mismatch errors




# =============================================================================
# GRAPHRAG METRICS - Sprint 15 Anti-Alucinaciones
# =============================================================================

@app.get("/api/graphrag/metrics")
async def api_get_graphrag_metrics(
    project: str = Query(..., description="ID del proyecto"),
    days: int = Query(30, ge=1, le=365, description="Días a analizar"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Obtiene métricas de calidad de respuestas GraphRAG.
    
    Incluye:
    - Tasa de respuestas grounded vs rechazadas
    - Score promedio de evidencia
    - Distribución de niveles de confianza
    """
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        from app.graphrag_metrics import ensure_metrics_table, get_metrics_summary, get_recent_rejections
        
        ensure_metrics_table(clients.postgres)
        
        summary = get_metrics_summary(clients.postgres, project_id, days=days)
        rejections = get_recent_rejections(clients.postgres, project_id, limit=10)
        
        return {
            "project": project_id,
            "period_days": days,
            "summary": summary,
            "recent_rejections": rejections,
        }
    finally:
        clients.close()


@app.get("/api/codes/similar")
async def api_get_similar_codes(
    codigo: str = Query(..., description="Código a buscar similares"),
    project: str = Query(..., description="ID del proyecto"),
    top_k: int = Query(5, ge=1, le=20, description="Máximo de resultados"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Busca códigos semánticamente similares (posibles sinónimos o duplicados).
    
    Usa distancia de Levenshtein para encontrar códigos con nombres parecidos.
    Útil para sugerir fusiones durante la validación.
    """
    from difflib import SequenceMatcher
    
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        # Obtener todos los códigos únicos del proyecto
        with clients.postgres.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT codigo, COUNT(*) as occurrences
                FROM codigos_candidatos
                WHERE project_id = %s AND estado IN ('validado', 'pendiente')
                GROUP BY codigo
                ORDER BY occurrences DESC
            """, (project_id,))
            rows = cur.fetchall()
        
        codigo_lower = codigo.lower().strip()
        similar_codes = []
        
        for row in rows:
            other_codigo = row[0]
            occurrences = row[1]
            
            if other_codigo.lower().strip() == codigo_lower:
                continue  # Skip self
            
            # Calcular similitud
            score = SequenceMatcher(
                None, 
                codigo_lower, 
                other_codigo.lower().strip()
            ).ratio()
            
            if score >= 0.5:  # Umbral mínimo de similitud
                similar_codes.append({
                    "codigo": other_codigo,
                    "score": round(score, 3),
                    "occurrences": occurrences,
                })
        
        # Ordenar por score descendente y limitar
        similar_codes.sort(key=lambda x: x["score"], reverse=True)
        similar_codes = similar_codes[:top_k]
        
        return {
            "codigo": codigo,
            "similar_codes": similar_codes,
            "count": len(similar_codes),
        }
    finally:
        clients.close()


# =============================================================================
# CONFIGURACIÓN DE PROYECTO
# =============================================================================

@app.get("/api/projects/{project_id}/config")
async def api_get_project_config(
    project_id: str,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Obtiene la configuración de un proyecto.
    
    Incluye:
    - discovery_threshold: Umbral de similitud para Discovery (0.0-1.0)
    - analysis_temperature: Temperatura LLM para análisis
    - analysis_max_tokens: Max tokens para respuesta LLM
    """
    try:
        resolved = resolve_project(project_id, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    
    config = get_project_config(clients.postgres, resolved)
    return {
        "project_id": resolved,
        "config": config,
    }


class ProjectConfigUpdate(BaseModel):
    """Request para actualizar configuración de proyecto."""
    model_config = ConfigDict(extra="forbid")
    
    discovery_threshold: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Umbral de Discovery (0.0-1.0)"
    )
    analysis_temperature: Optional[float] = Field(
        None, ge=0.0, le=2.0, description="Temperatura LLM para análisis"
    )
    analysis_max_tokens: Optional[int] = Field(
        None, ge=100, le=8000, description="Max tokens para respuesta LLM"
    )


class ProjectDetailsUpdate(BaseModel):
    """Request para actualizar nombre/descripcion de proyecto."""
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=500)


@app.put("/api/projects/{project_id}/config")
async def api_update_project_config(
    project_id: str,
    payload: ProjectConfigUpdate,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Actualiza la configuración de un proyecto.
    
    Solo actualiza los campos proporcionados en el payload.
    """
    try:
        resolved = resolve_project(project_id, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    
    # Construir dict con solo los campos proporcionados
    updates = {}
    if payload.discovery_threshold is not None:
        updates["discovery_threshold"] = payload.discovery_threshold
    if payload.analysis_temperature is not None:
        updates["analysis_temperature"] = payload.analysis_temperature
    if payload.analysis_max_tokens is not None:
        updates["analysis_max_tokens"] = payload.analysis_max_tokens
    
    if not updates:
        raise HTTPException(status_code=400, detail="No se proporcionaron campos para actualizar")
    
    try:
        config = update_project_config(clients.postgres, resolved, updates)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    
    api_logger.info(
        "project.config.updated",
        project_id=resolved,
        user=user.user_id,
        updates=list(updates.keys()),
    )
    
    return {
        "project_id": resolved,
        "config": config,
        "updated": list(updates.keys()),
    }


@app.patch("/api/projects/{project_id}")
async def api_update_project_details(
    project_id: str,
    payload: ProjectDetailsUpdate,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Actualiza nombre/descripcion de proyecto (requiere rol codificador/admin)."""
    try:
        resolved = resolve_project(project_id, allow_create=False, pg=clients.postgres)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if payload.name is None and payload.description is None:
        raise HTTPException(status_code=400, detail="No se proporcionaron campos para actualizar")

    is_admin = "admin" in {str(r).strip().lower() for r in (user.roles or [])}
    if not is_admin and not check_project_permission(clients.postgres, resolved, user.user_id, "codificador"):
        raise HTTPException(status_code=403, detail="Permiso insuficiente para editar el proyecto")

    try:
        updated = update_project_details(
            clients.postgres,
            resolved,
            name=payload.name,
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    api_logger.info(
        "project.updated",
        project_id=resolved,
        user=user.user_id,
        updates=[k for k in ("name", "description") if getattr(payload, k) is not None],
    )

    return updated


# =============================================================================
# SPRINT 17: SUGERENCIA DE ACCIÓN CON IA
# =============================================================================

class FragmentSelection(BaseModel):
    """Fragmento seleccionado para batch."""
    fragmento_id: str
    archivo: str
    cita: str
    score: float = 0.0


class BatchCandidateRequest(BaseModel):
    """Request para enviar múltiples fragmentos a bandeja de candidatos."""
    project: str
    codigo: str
    memo: Optional[str] = None
    fragments: List[FragmentSelection]


@app.post("/api/codes/candidates/batch")
async def api_submit_candidates_batch(
    payload: BatchCandidateRequest,
    user: User = Depends(require_auth),
    settings: AppSettings = Depends(get_settings),
) -> Dict[str, Any]:
    """
    Envía múltiples fragmentos a la bandeja de candidatos.
    
    Sprint 17 - E1: Sugerencia de Acción con selección múltiple.
    
    Todos los fragmentos se agrupan bajo el mismo código y memo.
    Los códigos pasan a validación antes de ser definitivos.
    """
    if not payload.fragments:
        raise HTTPException(status_code=400, detail="No hay fragmentos para procesar")
    
    clients = build_clients_or_error(settings)
    try:
        ensure_candidate_codes_table(clients.postgres)
        
        candidates = [
            {
                "project_id": payload.project,
                "codigo": payload.codigo,
                "cita": frag.cita[:500] if frag.cita else "",
                "fragmento_id": frag.fragmento_id,
                "archivo": frag.archivo,
                "fuente_origen": "semantic_suggestion",
                "fuente_detalle": "Sugerencia de Acción IA",
                "memo": payload.memo,
                "score_confianza": frag.score,
            }
            for frag in payload.fragments
        ]
        
        count = insert_candidate_codes(clients.postgres, candidates)
        
        api_logger.info(
            "candidates.batch.submitted",
            project=payload.project,
            codigo=payload.codigo,
            count=count,
            user=user.user_id,
        )
        
        return {
            "submitted": count,
            "codigo": payload.codigo,
            "project": payload.project,
            "fragments_count": len(payload.fragments),
        }
    finally:
        clients.close()


class SuggestCodeRequest(BaseModel):
    """Request para sugerencia de código IA."""
    project: str
    fragments: List[Dict[str, Any]]  # Lista de fragmentos con texto
    llm_model: Optional[str] = None


@app.post("/api/coding/suggest-code")
async def api_suggest_code_from_fragments(
    payload: SuggestCodeRequest,
    user: User = Depends(require_auth),
    settings: AppSettings = Depends(get_settings),
) -> Dict[str, Any]:
    """
    Sugiere nombre de código y memo basado en fragmentos.
    
    Sprint 17 - E2: IA que propone código y justificación.
    
    Returns:
        - suggested_code: Nombre propuesto en snake_case
        - memo: Justificación del agrupamiento
        - confidence: alta/media/baja
    """
    if not payload.fragments:
        raise HTTPException(status_code=400, detail="No hay fragmentos para analizar")
    
    clients = build_clients_or_error(settings)
    try:
        from app.coding import suggest_code_from_fragments, list_open_codes
        
        # Obtener códigos existentes para evitar duplicados
        existing_codes = [c["codigo"] for c in list_open_codes(clients, payload.project, limit=100)]
        
        result = suggest_code_from_fragments(
            clients=clients,
            settings=settings,
            fragments=payload.fragments,
            existing_codes=existing_codes,
            llm_model=payload.llm_model,
            project=payload.project,
        )
        
        api_logger.info(
            "coding.suggest_code.completed",
            project=payload.project,
            suggested_code=result.get("suggested_code"),
            confidence=result.get("confidence"),
            user=user.user_id,
        )
        
        return result
    finally:
        clients.close()


# =============================================================================
# Sprint 27: Analysis Insights - Muestreo Teórico Automatizado
# =============================================================================

class InsightsListRequest(BaseModel):
    project: str
    status: Optional[str] = None  # 'pending', 'executed', 'dismissed'
    source_type: Optional[str] = None  # 'discovery', 'coding', 'link_prediction', 'report'
    limit: int = 20


@app.post("/api/insights/list")
async def api_list_insights(
    payload: InsightsListRequest,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Lista insights de un proyecto con filtros opcionales."""
    from app.postgres_block import list_insights, count_insights_by_status
    
    insights = list_insights(
        clients.postgres,
        payload.project,
        status=payload.status,
        source_type=payload.source_type,
        limit=payload.limit,
    )
    
    counts = count_insights_by_status(clients.postgres, payload.project)
    
    return {
        "insights": insights,
        "counts": counts,
        "total": len(insights),
    }


class InsightActionRequest(BaseModel):
    insight_id: int
    project: str


@app.post("/api/insights/dismiss")
async def api_dismiss_insight(
    payload: InsightActionRequest,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Descarta un insight (no ejecutar)."""
    from app.postgres_block import update_insight_status
    
    success = update_insight_status(
        clients.postgres,
        payload.insight_id,
        status="dismissed",
    )
    
    api_logger.info(
        "insights.dismissed",
        insight_id=payload.insight_id,
        project=payload.project,
        user=user.user_id,
    )
    
    return {"success": success, "insight_id": payload.insight_id}


@app.post("/api/insights/execute")
async def api_execute_insight(
    payload: InsightActionRequest,
    settings: AppSettings = Depends(get_settings),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Ejecuta la sugerencia de un insight.
    
    Dependiendo del tipo de sugerencia, ejecuta:
    - search: Búsqueda Discovery
    - analyze: Análisis de codificación
    - link_prediction: Predicción de enlaces
    """
    from app.postgres_block import get_insight, update_insight_status
    
    insight = get_insight(clients.postgres, payload.insight_id)
    if not insight:
        raise HTTPException(status_code=404, detail="Insight no encontrado")
    
    suggested_query = insight.get("suggested_query", {})
    action = suggested_query.get("action", "search")
    
    result = {
        "insight_id": payload.insight_id,
        "action": action,
        "executed": False,
        "message": "",
    }
    
    try:
        if action == "search" and suggested_query.get("positivos"):
            # Ejecutar búsqueda semántica usando embeddings
            from app.qdrant_block import search_similar
            
            positivos = suggested_query.get("positivos", [])
            query_text = " ".join(positivos)
            
            api_logger.info(
                "insights.execute.search.start",
                insight_id=payload.insight_id,
                query_text=query_text,
                project=payload.project,
            )
            
            try:
                # Generar embedding del término de búsqueda
                embedding_response = clients.aoai.embeddings.create(
                    model=settings.azure.deployment_embed,
                    input=query_text,
                )
                vector = embedding_response.data[0].embedding
                
                api_logger.info(
                    "insights.execute.embedding.created",
                    insight_id=payload.insight_id,
                    vector_dim=len(vector),
                )
                
                # Usar el nombre de colección correcto desde settings
                collection_name = settings.qdrant.collection
                
                api_logger.info(
                    "insights.execute.search.query",
                    insight_id=payload.insight_id,
                    collection=collection_name,
                    project=payload.project,
                )
                
                search_results = search_similar(
                    clients.qdrant,
                    collection=collection_name,
                    vector=vector,
                    limit=10,
                    score_threshold=0.4,  # Umbral más permisivo
                    project_id=payload.project,
                )
                
                result["executed"] = True
                result["message"] = f"Búsqueda ejecutada: {len(search_results)} fragmentos encontrados para '{query_text}'"
                result["fragments_count"] = len(search_results)
                
                # Formatear resultados para preview
                result["fragments"] = [
                    {
                        "id": str(r.id), 
                        "score": round(r.score, 3), 
                        "fragmento": (r.payload.get("fragmento", "") or "")[:200] + "..."
                    }
                    for r in search_results[:5]
                ]
                
                api_logger.info(
                    "insights.execute.search.complete",
                    insight_id=payload.insight_id,
                    fragments_found=len(search_results),
                    top_score=round(search_results[0].score, 3) if search_results else 0,
                )
                
            except Exception as search_err:
                result["message"] = f"Error en búsqueda: {str(search_err)}"
                api_logger.error(
                    "insights.execute.search.error",
                    insight_id=payload.insight_id,
                    error=str(search_err),
                    error_type=type(search_err).__name__,
                )
            
        elif action == "compare":
            # Comparar códigos para posible merge
            codes = suggested_query.get("codes", [])
            result["executed"] = True
            result["message"] = f"Comparar códigos: {codes}. Revisar manualmente para confirmar fusión."
            result["codes"] = codes
            
            api_logger.info(
                "insights.execute.compare",
                insight_id=payload.insight_id,
                codes=codes,
            )
            
        else:
            result["message"] = f"Acción '{action}' requiere implementación manual."
            api_logger.warning(
                "insights.execute.unsupported_action",
                insight_id=payload.insight_id,
                action=action,
            )
        
        # Actualizar status del insight
        update_insight_status(
            clients.postgres,
            payload.insight_id,
            status="executed",
            execution_result=result,
        )
        
        api_logger.info(
            "insights.executed",
            insight_id=payload.insight_id,
            action=action,
            project=payload.project,
            user=user.user_id,
        )
        
    except Exception as e:
        result["message"] = f"Error ejecutando: {str(e)}"
        api_logger.error("insights.execute.error", error=str(e))
    
    return result


class GenerateInsightsRequest(BaseModel):
    project: str
    source: str = "coding"  # 'coding', 'report'


@app.post("/api/insights/generate")
async def api_generate_insights(
    payload: GenerateInsightsRequest,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Genera insights manualmente desde una fuente.
    
    Útil para trigger manual de análisis de códigos poco frecuentes.
    """
    from app.insights import extract_insights_from_coding
    
    if payload.source == "coding":
        insight_ids = extract_insights_from_coding(
            clients.postgres,
            project=payload.project,
        )
        
        return {
            "source": "coding",
            "insights_created": len(insight_ids),
            "insight_ids": insight_ids,
        }
    
    return {"source": payload.source, "insights_created": 0, "message": "Fuente no soportada"}


# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# ADMIN PANEL ENDPOINTS - Gestión de usuarios, limpieza y análisis
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
# 1. USERS MANAGEMENT ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

@app.get("/api/admin/users")
async def api_admin_list_users(
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Lista todos los usuarios de la organización del admin autenticado."""
    clients = build_clients_or_error(settings)
    try:
        with clients.postgres.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, full_name, role, organization_id, is_active, created_at, last_login
                  FROM app_users
                 WHERE organization_id = %s
                 ORDER BY created_at DESC
                """,
                (user.organization_id,),
            )
            rows = cur.fetchall()
        
        users = [
            {
                "id": row[0],
                "email": row[1],
                "full_name": row[2],
                "role": row[3],
                "organization_id": row[4],
                "is_active": row[5],
                "created_at": row[6].isoformat() if row[6] else None,
                "last_login": row[7].isoformat() if row[7] else None,
            }
            for row in rows
        ]
        
        return {"users": users, "total": len(users)}
    finally:
        clients.close()


@app.get("/api/admin/stats")
async def api_admin_get_stats(
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Obtiene estadísticas generales de la organización."""
    clients = build_clients_or_error(settings)
    try:
        with clients.postgres.cursor() as cur:
            # Contar usuarios por rol
            cur.execute(
                """
                SELECT role, COUNT(*) as count
                  FROM app_users
                 WHERE organization_id = %s AND is_active = true
                 GROUP BY role
                """,
                (user.organization_id,),
            )
            role_counts = {row[0]: row[1] for row in cur.fetchall()}
            
            # Total de usuarios
            cur.execute(
                "SELECT COUNT(*) FROM app_users WHERE organization_id = %s",
                (user.organization_id,),
            )
            total_users = cur.fetchone()[0] or 0
            
            # Total de fragmentos
            cur.execute(
                """
                SELECT COUNT(DISTINCT ef.id) FROM entrevista_fragmentos ef
                 JOIN proyectos p ON ef.project_id = p.id
                 WHERE p.org_id = %s
                """,
                (user.organization_id,),
            )
            total_fragments = cur.fetchone()[0] or 0
            
            # Sesiones activas (últimos 30 minutos)
            cur.execute(
                """
                SELECT COUNT(DISTINCT user_id) FROM app_user_sessions
                 WHERE organization_id = %s AND last_activity > NOW() - INTERVAL '30 minutes'
                """,
                (user.organization_id,),
            )
            active_sessions = cur.fetchone()[0] or 0
        
        return {
            "organization_id": user.organization_id,
            "total_users": total_users,
            "users_by_role": role_counts,
            "total_fragments": total_fragments,
            "active_sessions": active_sessions,
        }
    finally:
        clients.close()


class UserUpdateRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None


@app.patch("/api/admin/users/{user_id}")
async def api_admin_update_user(
    user_id: str,
    payload: UserUpdateRequest,
    settings: AppSettings = Depends(get_settings),
    admin: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Actualiza el rol o estado de un usuario."""
    clients = build_clients_or_error(settings)
    try:
        # Verificar que el usuario a actualizar pertenece a la misma organización
        with clients.postgres.cursor() as cur:
            cur.execute(
                "SELECT organization_id FROM app_users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if not row or row[0] != admin.org_id:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Actualizar
            updates = []
            values = []
            if payload.role:
                updates.append("role = %s")
                values.append(payload.role)
            if payload.is_active is not None:
                updates.append("is_active = %s")
                values.append(payload.is_active)
            
            if not updates:
                raise HTTPException(status_code=400, detail="No updates provided")
            
            values.append(user_id)
            cur.execute(
                f"UPDATE app_users SET {', '.join(updates)}, updated_at = NOW() WHERE id = %s",
                values,
            )
            clients.postgres.commit()
        
        api_logger.info("admin.user_updated", user_id=user_id, admin_id=admin.user_id, org_id=admin.org_id)
        return {"user_id": user_id, "status": "updated"}
    finally:
        clients.close()


@app.delete("/api/admin/users/{user_id}")
async def api_admin_delete_user(
    user_id: str,
    settings: AppSettings = Depends(get_settings),
    admin: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Elimina un usuario (soft-delete o hard-delete según config)."""
    clients = build_clients_or_error(settings)
    try:
        # Verificar que el usuario a eliminar pertenece a la misma organización y no es el admin
        if user_id == admin.user_id:
            raise HTTPException(status_code=400, detail="No puedes eliminarte a ti mismo")
        
        with clients.postgres.cursor() as cur:
            cur.execute(
                "SELECT organization_id FROM app_users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if not row or row[0] != admin.org_id:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Soft delete (marcar como inactivo)
            cur.execute(
                "UPDATE app_users SET is_active = false, updated_at = NOW() WHERE id = %s",
                (user_id,),
            )
            clients.postgres.commit()
        
        api_logger.info("admin.user_deleted", user_id=user_id, admin_id=admin.user_id, org_id=admin.org_id)
        return {"user_id": user_id, "status": "deleted"}
    finally:
        clients.close()


# ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
# 2. DATA CLEANUP ENDPOINTS (Destructive - Admin Only)
# ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

class CleanupConfirmRequest(BaseModel):
    """Solicitud de confirmación para operaciones destructivas."""
    confirm: bool = Field(default=False, description="Debe ser true para ejecutar")
    reason: str = Field(default="", description="Razón o comentario (logging)")


@app.post("/api/admin/cleanup/all-data")
async def api_admin_cleanup_all_data(
    payload: CleanupConfirmRequest,
    project: str = Query(default="default", description="Proyecto a limpiar"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """
    DESTRUCTIVE: Elimina todos los datos de un proyecto (PostgreSQL, Qdrant, Neo4j).
    Requiere confirm=true.
    """
    if not payload.confirm:
        return {
            "status": "not_confirmed",
            "message": "Operación requiere confirm=true. Esta acción es irreversible.",
            "project": project,
        }
    
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    counts: Dict[str, int] = {"postgres": 0, "qdrant": 0, "neo4j": 0}
    
    try:
        # 1. PostgreSQL cleanup
        with clients.postgres.cursor() as cur:
            tables = [
                "entrevista_fragmentos",
                "analisis_codigos_abiertos",
                "analisis_relacion_axial",
                "reporte_entrevista_staging",
                "report_jobs",
            ]
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = ANY(%s)
                """,
                (tables,),
            )
            existing_tables = {row[0] for row in cur.fetchall()}
            for table in tables:
                if table not in existing_tables:
                    api_logger.warning("admin.cleanup.table_missing", table=table, project=project_id)
                    continue
                cur.execute(f"DELETE FROM {table} WHERE project_id = %s", (project_id,))
                counts["postgres"] += cur.rowcount
            if "proyectos" in existing_tables:
                cur.execute("DELETE FROM proyectos WHERE id = %s", (project_id,))
                counts["postgres"] += cur.rowcount
            clients.postgres.commit()
        
        # 2. Qdrant cleanup
        try:
            collection = f"project_{project_id}".replace("-", "_")
            clients.qdrant.delete(
                collection_name=collection,
                points_selector=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="metadata.project_id",
                            match=models.MatchValue(value=project_id),
                        )
                    ]
                ),
            )
            counts["qdrant"] = 1  # Marker
        except Exception as qd_err:
            api_logger.warning("admin.cleanup.qdrant_error", error=str(qd_err), project=project_id)
        
        # 3. Neo4j cleanup
        try:
            with clients.neo4j.session(database=settings.neo4j.database) as session:
                result = session.run(
                    "MATCH (n {project_id: $project}) DETACH DELETE n",
                    project=project_id,
                )
                counts["neo4j"] = result.consume().counters.nodes_deleted
        except Exception as neo_err:
            api_logger.warning("admin.cleanup.neo4j_error", error=str(neo_err), project=project_id)
        
        api_logger.info(
            "admin.cleanup_all_data",
            project=project_id,
            admin_id=user.user_id,
            counts=counts,
            reason=payload.reason,
        )
        
        return {
            "status": "completed",
            "project": project_id,
            "counts": counts,
            "message": f"Limpieza completada: {counts['postgres']} registros PostgreSQL, {counts['qdrant']} Qdrant, {counts['neo4j']} Neo4j",
        }
    except Exception as exc:
        api_logger.error("admin.cleanup_all_data.error", error=str(exc), project=project_id)
        raise HTTPException(status_code=500, detail=f"Error limpiando: {str(exc)}") from exc
    finally:
        clients.close()


@app.post("/api/admin/cleanup/projects")
async def api_admin_cleanup_projects(
    payload: CleanupConfirmRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """
    DESTRUCTIVE: Elimina datos de proyectos marcados como deleted.
    Requiere confirm=true.
    """
    if not payload.confirm:
        return {
            "status": "not_confirmed",
            "message": "Operación requiere confirm=true.",
        }
    
    clients = build_clients_or_error(settings)
    try:
        with clients.postgres.cursor() as cur:
            # Validar que la columna is_deleted exista (compatibilidad con esquemas antiguos)
            cur.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'proyectos'
                  AND column_name = 'is_deleted'
                LIMIT 1
                """
            )
            has_is_deleted = cur.fetchone() is not None
            if not has_is_deleted:
                api_logger.warning(
                    "admin.cleanup_projects.missing_column",
                    column="is_deleted",
                    table="proyectos",
                )
                return {
                    "status": "not_supported",
                    "message": "La columna is_deleted no existe en proyectos. No hay proyectos marcados como deleted.",
                    "cleaned_projects": [],
                }

            # Obtener proyectos deleted
            cur.execute(
                "SELECT id FROM proyectos WHERE org_id = %s AND is_deleted = true",
                (user.organization_id,),
            )
            deleted_projects = [row[0] for row in cur.fetchall()]
            
            if not deleted_projects:
                return {
                    "status": "no_action_needed",
                    "message": "No hay proyectos marcados como deleted",
                    "cleaned_projects": [],
                }
            
            cleaned = []
            for project_id in deleted_projects:
                # Limpiar datos del proyecto
                tables = [
                    "entrevista_fragmentos",
                    "analisis_codigos_abiertos",
                    "analisis_relacion_axial",
                ]
                cur.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = ANY(%s)
                    """,
                    (tables,),
                )
                existing_tables = {row[0] for row in cur.fetchall()}
                for table in tables:
                    if table not in existing_tables:
                        api_logger.warning("admin.cleanup.table_missing", table=table, project=project_id)
                        continue
                    cur.execute(f"DELETE FROM {table} WHERE project_id = %s", (project_id,))
                cleaned.append({"project_id": project_id, "rows_deleted": cur.rowcount})
            
            # Eliminar registros de proyectos
            cur.execute(
                "DELETE FROM proyectos WHERE org_id = %s AND is_deleted = true",
                (user.organization_id,),
            )
            clients.postgres.commit()
        
        api_logger.info(
            "admin.cleanup_projects",
            org_id=user.organization_id,
            admin_id=user.user_id,
            projects_cleaned=len(deleted_projects),
        )
        
        return {
            "status": "completed",
            "cleaned_projects": cleaned,
            "message": f"Limpieza completada: {len(deleted_projects)} proyectos eliminados",
        }
    except Exception as exc:
        api_logger.error("admin.cleanup_projects.error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Error limpiando proyectos: {str(exc)}") from exc
    finally:
        clients.close()


@app.post("/api/admin/cleanup/orphans")
async def api_admin_cleanup_orphans(
    payload: CleanupConfirmRequest,
    project: str = Query(default="default", description="Proyecto a limpiar"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """
    DESTRUCTIVE: Elimina archivos huérfanos del proyecto (PostgreSQL + Neo4j).
    Un archivo huérfano existe en DB pero no existe en filesystem local.
    Requiere confirm=true.
    """
    if not payload.confirm:
        return {
            "status": "not_confirmed",
            "message": "Operación requiere confirm=true.",
            "project": project,
        }

    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    clients = build_clients_or_error(settings)
    try:
        with clients.postgres.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT archivo FROM entrevista_fragmentos
                 WHERE project_id = %s
                 ORDER BY archivo
                """,
                (project_id,),
            )
            files_in_db = [row[0] for row in cur.fetchall() if row and row[0]]

        blob_enabled = False
        blob_check_failed = False
        try:
            from app import blob_storage

            conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
            blob_enabled = bool(conn_str) and bool(getattr(blob_storage, "_AZURE_BLOB_AVAILABLE", False))
        except Exception:
            blob_enabled = False

        orphans: list[str] = []
        for filename in files_in_db:
            file_path = Path("data") / project_id / filename
            exists_in_fs = file_path.exists()
            exists_in_blob = None
            if blob_enabled:
                try:
                    from app.blob_storage import CONTAINER_INTERVIEWS, file_exists

                    blob_name = f"{project_id}/{filename}"
                    exists_in_blob = bool(file_exists(CONTAINER_INTERVIEWS, blob_name))
                except Exception:
                    blob_check_failed = True
                    exists_in_blob = None

            if blob_enabled:
                is_orphan = (not exists_in_fs) and (exists_in_blob is False)
            else:
                is_orphan = not exists_in_fs

            if is_orphan:
                orphans.append(filename)

        if not orphans:
            return {
                "status": "no_action_needed",
                "project": project_id,
                "message": "No hay archivos huérfanos para limpiar",
                "cleaned": [],
                "deleted_codes": 0,
                "deleted_fragments": 0,
                "deleted_neo4j_nodes": 0,
            }

        deleted_codes = 0
        deleted_fragments = 0
        deleted_neo4j_nodes = 0
        cleaned: list[Dict[str, Any]] = []

        for filename in orphans:
            file_deleted_codes = 0
            file_deleted_fragments = 0
            file_deleted_neo4j = 0
            with clients.postgres.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM analisis_codigos_abiertos
                     WHERE project_id = %s AND archivo = %s
                    """,
                    (project_id, filename),
                )
                file_deleted_codes = cur.rowcount

                cur.execute(
                    """
                    DELETE FROM entrevista_fragmentos
                     WHERE project_id = %s AND archivo = %s
                    """,
                    (project_id, filename),
                )
                file_deleted_fragments = cur.rowcount
            clients.postgres.commit()

            try:
                with clients.neo4j.session(database=settings.neo4j.database) as session:
                    result = session.run(
                        """
                        MATCH (e:Entrevista {nombre: $archivo, project_id: $project})
                        OPTIONAL MATCH (e)-[:TIENE_FRAGMENTO]->(f:Fragmento)
                        DETACH DELETE e, f
                        RETURN count(e) AS deleted
                        """,
                        archivo=filename,
                        project=project_id,
                    )
                    record = result.single()
                    file_deleted_neo4j = int(record["deleted"]) if record and record.get("deleted") else 0
            except Exception as neo_err:
                api_logger.warning(
                    "admin.cleanup_orphans.neo4j_error",
                    error=str(neo_err),
                    project=project_id,
                    archivo=filename,
                )

            deleted_codes += file_deleted_codes
            deleted_fragments += file_deleted_fragments
            deleted_neo4j_nodes += file_deleted_neo4j
            cleaned.append(
                {
                    "archivo": filename,
                    "deleted_codes": file_deleted_codes,
                    "deleted_fragments": file_deleted_fragments,
                    "deleted_neo4j_nodes": file_deleted_neo4j,
                }
            )

        api_logger.info(
            "admin.cleanup_orphans",
            project=project_id,
            admin_id=user.user_id,
            orphans=len(orphans),
            deleted_codes=deleted_codes,
            deleted_fragments=deleted_fragments,
            deleted_neo4j_nodes=deleted_neo4j_nodes,
            reason=payload.reason,
            blob_enabled=blob_enabled,
            blob_check_failed=blob_check_failed,
        )

        return {
            "status": "completed",
            "project": project_id,
            "orphans_cleaned": len(orphans),
            "deleted_codes": deleted_codes,
            "deleted_fragments": deleted_fragments,
            "deleted_neo4j_nodes": deleted_neo4j_nodes,
            "cleaned": cleaned,
            "message": f"Huérfanos eliminados: {len(orphans)}",
            "blob_enabled": blob_enabled,
        }
    except Exception as exc:
        api_logger.error("admin.cleanup_orphans.error", error=str(exc), project=project_id)
        raise HTTPException(status_code=500, detail=f"Error limpiando huérfanos: {str(exc)}") from exc
    finally:
        clients.close()


@app.post("/api/admin/cleanup/neo4j-orphans")
async def api_admin_cleanup_neo4j_orphans(
    payload: CleanupConfirmRequest,
    project: str = Query(default="default", description="Proyecto a limpiar"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """
    DESTRUCTIVE: Elimina nodos huérfanos en Neo4j comparando con PostgreSQL.
    Huérfanos:
      - Fragmentos que no existen en entrevista_fragmentos
      - Entrevistas cuyo archivo no existe en entrevista_fragmentos
    Requiere confirm=true.
    """
    if not payload.confirm:
        return {
            "status": "not_confirmed",
            "message": "Operación requiere confirm=true. Esta acción es irreversible.",
            "project": project,
        }

    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    clients = build_clients_or_error(settings)
    try:
        # PostgreSQL: ids válidos
        with clients.postgres.cursor() as cur:
            cur.execute(
                "SELECT id FROM entrevista_fragmentos WHERE project_id = %s",
                (project_id,),
            )
            pg_fragments = {str(row[0]) for row in cur.fetchall() if row and row[0] is not None}

            cur.execute(
                "SELECT DISTINCT archivo FROM entrevista_fragmentos WHERE project_id = %s",
                (project_id,),
            )
            pg_archivos = {str(row[0]) for row in cur.fetchall() if row and row[0] is not None}

        # Neo4j: ids actuales
        neo_fragments: list[str] = []
        neo_archivos: list[str] = []
        with clients.neo4j.session(database=settings.neo4j.database) as session:
            result = session.run(
                "MATCH (f:Fragmento {project_id: $project}) RETURN f.id AS id",
                project=project_id,
            )
            for record in result:
                frag_id = record.get("id")
                if frag_id is not None:
                    neo_fragments.append(str(frag_id))

            result = session.run(
                "MATCH (e:Entrevista {project_id: $project}) RETURN e.nombre AS nombre",
                project=project_id,
            )
            for record in result:
                nombre = record.get("nombre")
                if nombre is not None:
                    neo_archivos.append(str(nombre))

        orphan_fragments = [fid for fid in neo_fragments if fid not in pg_fragments]
        orphan_archivos = [a for a in neo_archivos if a not in pg_archivos]

        deleted_fragments = 0
        deleted_entrevistas = 0
        batch = 500

        if orphan_fragments:
            for i in range(0, len(orphan_fragments), batch):
                batch_ids = orphan_fragments[i : i + batch]
                with clients.neo4j.session(database=settings.neo4j.database) as session:
                    result = session.run(
                        """
                        UNWIND $ids AS id
                        MATCH (f:Fragmento {project_id: $project, id: id})
                        DETACH DELETE f
                        RETURN count(f) AS deleted
                        """,
                        project=project_id,
                        ids=batch_ids,
                    )
                    record = result.single()
                    if record and record.get("deleted") is not None:
                        deleted_fragments += int(record["deleted"])

        if orphan_archivos:
            for i in range(0, len(orphan_archivos), batch):
                batch_names = orphan_archivos[i : i + batch]
                with clients.neo4j.session(database=settings.neo4j.database) as session:
                    result = session.run(
                        """
                        UNWIND $nombres AS nombre
                        MATCH (e:Entrevista {project_id: $project, nombre: nombre})
                        OPTIONAL MATCH (e)-[:TIENE_FRAGMENTO]->(f:Fragmento)
                        DETACH DELETE e, f
                        RETURN count(e) AS deleted
                        """,
                        project=project_id,
                        nombres=batch_names,
                    )
                    record = result.single()
                    if record and record.get("deleted") is not None:
                        deleted_entrevistas += int(record["deleted"])

        api_logger.info(
            "admin.cleanup_neo4j_orphans",
            project=project_id,
            admin_id=user.user_id,
            orphan_fragments=len(orphan_fragments),
            orphan_entrevistas=len(orphan_archivos),
            deleted_fragments=deleted_fragments,
            deleted_entrevistas=deleted_entrevistas,
            reason=payload.reason,
        )

        return {
            "status": "completed",
            "project": project_id,
            "orphan_fragments": len(orphan_fragments),
            "orphan_entrevistas": len(orphan_archivos),
            "deleted_fragments": deleted_fragments,
            "deleted_entrevistas": deleted_entrevistas,
            "message": (
                f"Neo4j huérfanos eliminados: {deleted_fragments} fragmentos, "
                f"{deleted_entrevistas} entrevistas."
            ),
        }
    except Exception as exc:
        api_logger.error("admin.cleanup_neo4j_orphans.error", error=str(exc), project=project_id)
        raise HTTPException(status_code=500, detail=f"Error limpiando Neo4j: {str(exc)}") from exc
    finally:
        clients.close()


@app.post("/api/admin/cleanup/neo4j-unscoped")
async def api_admin_cleanup_neo4j_unscoped(
    payload: CleanupConfirmRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """
    DESTRUCTIVE: Elimina nodos Neo4j que no tienen project_id.
    Útil para limpiar datos antiguos creados sin scope de proyecto.
    Requiere confirm=true.
    """
    if not payload.confirm:
        return {
            "status": "not_confirmed",
            "message": "Operación requiere confirm=true. Esta acción es irreversible.",
        }

    clients = build_clients_or_error(settings)
    labels = ["Fragmento", "Entrevista", "Codigo", "Categoria"]
    counts: Dict[str, int] = {"nodes_deleted": 0}

    try:
        with clients.neo4j.session(database=settings.neo4j.database) as session:
            for label in labels:
                result = session.run(
                    f"MATCH (n:{label}) WHERE n.project_id IS NULL DETACH DELETE n",
                )
                counts["nodes_deleted"] += result.consume().counters.nodes_deleted

        api_logger.info(
            "admin.cleanup_neo4j_unscoped",
            admin_id=user.user_id,
            labels=labels,
            counts=counts,
            reason=payload.reason,
        )

        return {
            "status": "completed",
            "counts": counts,
            "message": f"Neo4j sin project_id eliminado: {counts['nodes_deleted']} nodos.",
        }
    except Exception as exc:
        api_logger.error("admin.cleanup_neo4j_unscoped.error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Error limpiando Neo4j: {str(exc)}") from exc
    finally:
        clients.close()


@app.post("/api/admin/cleanup/neo4j-unscoped-relationships")
async def api_admin_cleanup_neo4j_unscoped_relationships(
    payload: CleanupConfirmRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """
    DESTRUCTIVE: Elimina relaciones Neo4j cuyo origen o destino no tienen project_id
    (o la propia relación carece de project_id). Útil para limpiar datos antiguos.
    Requiere confirm=true.
    """
    if not payload.confirm:
        return {
            "status": "not_confirmed",
            "message": "Operación requiere confirm=true. Esta acción es irreversible.",
        }

    clients = build_clients_or_error(settings)
    counts: Dict[str, int] = {"relationships_deleted": 0}

    try:
        with clients.neo4j.session(database=settings.neo4j.database) as session:
            result = session.run(
                """
                MATCH (a)-[r]->(b)
                WHERE a.project_id IS NULL OR b.project_id IS NULL OR r.project_id IS NULL
                DELETE r
                RETURN count(r) AS deleted
                """
            )
            record = result.single()
            if record and record.get("deleted") is not None:
                counts["relationships_deleted"] = int(record["deleted"])

        api_logger.info(
            "admin.cleanup_neo4j_unscoped_relationships",
            admin_id=user.user_id,
            counts=counts,
            reason=payload.reason,
        )

        return {
            "status": "completed",
            "counts": counts,
            "message": f"Relaciones Neo4j sin project_id eliminadas: {counts['relationships_deleted']}.",
        }
    except Exception as exc:
        api_logger.error("admin.cleanup_neo4j_unscoped_relationships.error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Error limpiando Neo4j: {str(exc)}") from exc
    finally:
        clients.close()


@app.post("/api/admin/cleanup/duplicate-codes")
async def api_admin_cleanup_duplicate_codes(
    project: str = Query(default="default", description="Proyecto a analizar"),
    threshold: float = Query(default=0.85, description="Umbral de similitud (0-1)"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_role(["admin", "analyst"])),
) -> Dict[str, Any]:
    """
    Detecta códigos posiblemente duplicados usando similitud de strings.
    No es destructiva, solo reporta candidatos.
    """
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        from difflib import SequenceMatcher
        
        with clients.postgres.cursor() as cur:
            cur.execute(
                "SELECT codigo, COUNT(*) FROM analisis_codigos_abiertos WHERE project_id = %s GROUP BY codigo",
                (project_id,),
            )
            codes = {row[0]: row[1] for row in cur.fetchall()}
        
        # Encontrar similares
        similar_groups = []
        checked = set()
        
        for code1 in codes.keys():
            if code1 in checked:
                continue
            group = [code1]
            for code2 in codes.keys():
                if code1 != code2 and code2 not in checked:
                    sim = SequenceMatcher(None, code1, code2).ratio()
                    if sim >= threshold:
                        group.append(code2)
                        checked.add(code2)
            if len(group) > 1:
                similar_groups.append(group)
                checked.add(code1)
        
        api_logger.info(
            "admin.duplicate_codes_detection",
            project=project_id,
            total_codes=len(codes),
            duplicate_groups=len(similar_groups),
            threshold=threshold,
        )
        
        return {
            "status": "completed",
            "project": project_id,
            "total_codes": len(codes),
            "duplicate_groups": similar_groups,
            "groups_count": len(similar_groups),
            "threshold": threshold,
        }
    except Exception as exc:
        api_logger.error("admin.duplicate_codes.error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Error detectando duplicados: {str(exc)}") from exc
    finally:
        clients.close()


# ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
# 3. INTEGRITY ANALYSIS ENDPOINTS (Non-destructive - Analyst+)
# ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

@app.get("/api/admin/analysis/orphan-files")
async def api_admin_find_orphan_files(
    project: str = Query(default="default", description="Proyecto a analizar"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_role(["admin", "analyst"])),
) -> Dict[str, Any]:
    """
    Detecta archivos en PostgreSQL que no existen en Blob Storage o filesystem.
    """
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        with clients.postgres.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT archivo FROM entrevista_fragmentos
                 WHERE project_id = %s
                 ORDER BY archivo
                """,
                (project_id,),
            )
            files_in_db = {row[0] for row in cur.fetchall()}

        # Validar contra filesystem local y Blob Storage cuando esté disponible
        orphans = []
        blob_enabled = False
        blob_check_failed = False
        try:
            from app import blob_storage

            conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
            blob_enabled = bool(conn_str) and bool(getattr(blob_storage, "_AZURE_BLOB_AVAILABLE", False))
        except Exception:
            blob_enabled = False

        for filename in files_in_db:
            file_path = Path("data") / project_id / filename
            exists_in_fs = file_path.exists()
            exists_in_blob = None
            if blob_enabled:
                try:
                    from app.blob_storage import CONTAINER_INTERVIEWS, file_exists

                    blob_name = f"{project_id}/{filename}"
                    exists_in_blob = bool(file_exists(CONTAINER_INTERVIEWS, blob_name))
                except Exception:
                    blob_check_failed = True
                    exists_in_blob = None

            if blob_enabled:
                is_orphan = (not exists_in_fs) and (exists_in_blob is False)
            else:
                is_orphan = not exists_in_fs

            if is_orphan:
                orphans.append(
                    {
                        "filename": filename,
                        "exists_in_db": True,
                        "exists_in_fs": exists_in_fs,
                        "exists_in_blob": exists_in_blob,
                    }
                )
        
        api_logger.info(
            "admin.orphan_files_detection",
            project=project_id,
            total_files=len(files_in_db),
            orphans_found=len(orphans),
            blob_enabled=blob_enabled,
            blob_check_failed=blob_check_failed,
        )
        
        return {
            "status": "completed",
            "project": project_id,
            "total_files": len(files_in_db),
            "orphans": orphans,
            "orphans_count": len(orphans),
            "blob_enabled": blob_enabled,
        }
    except Exception as exc:
        api_logger.error("admin.orphan_files.error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Error analizando archivos: {str(exc)}") from exc
    finally:
        clients.close()


@app.get("/api/admin/analysis/integrity")
async def api_admin_integrity_check(
    project: str = Query(default="default", description="Proyecto a verificar"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_role(["admin", "analyst"])),
) -> Dict[str, Any]:
    """
    Chequeo de integridad general: fragmentos sin códigos, códigos sin fragmentos, etc.
    """
    try:
        project_id = resolve_project(project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    clients = build_clients_or_error(settings)
    try:
        checks = {}
        
        with clients.postgres.cursor() as cur:
            # 1. Fragmentos sin códigos
            cur.execute(
                """
                SELECT COUNT(DISTINCT ef.id) FROM entrevista_fragmentos ef
                 LEFT JOIN analisis_codigos_abiertos ac ON ef.id = ac.fragmento_id
                 WHERE ef.project_id = %s AND ac.id IS NULL
                """,
                (project_id,),
            )
            checks["fragments_without_codes"] = cur.fetchone()[0] or 0
            
            # 2. Total de fragmentos
            cur.execute(
                "SELECT COUNT(*) FROM entrevista_fragmentos WHERE project_id = %s",
                (project_id,),
            )
            checks["total_fragments"] = cur.fetchone()[0] or 0
            
            # 3. Total de códigos
            cur.execute(
                "SELECT COUNT(DISTINCT codigo) FROM analisis_codigos_abiertos WHERE project_id = %s",
                (project_id,),
            )
            checks["unique_codes"] = cur.fetchone()[0] or 0
            
            # 4. Total de asignaciones de código
            cur.execute(
                "SELECT COUNT(*) FROM analisis_codigos_abiertos WHERE project_id = %s",
                (project_id,),
            )
            checks["total_code_assignments"] = cur.fetchone()[0] or 0
        
        api_logger.info(
            "admin.integrity_check",
            project=project_id,
            checks=checks,
        )
        
        return {
            "status": "completed",
            "project": project_id,
            "checks": checks,
        }
    except Exception as exc:
        api_logger.error("admin.integrity_check.error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Error verificando integridad: {str(exc)}") from exc
    finally:
        clients.close()


# Force reload

