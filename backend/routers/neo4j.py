"""
Neo4j router - Graph database query and export endpoints.
"""
from io import StringIO
from time import perf_counter
from typing import Dict, Any, Tuple, cast
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
import structlog
from functools import lru_cache
import os
import json
import re

from app.clients import ServiceClients
from app.settings import AppSettings, load_settings
from app.queries import run_cypher
from app.project_state import resolve_project
from backend.auth import User, get_current_user

# Logger
logger = structlog.get_logger("neo4j.api")

# Dependencies
@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    env_file = os.getenv("APP_ENV_FILE")
    return load_settings(env_file)

async def require_auth(user: User = Depends(get_current_user)) -> User:
    return user

# Request/Response Models
class CypherRequest(BaseModel):
    cypher: str = Field(..., description="Consulta Cypher a ejecutar en Neo4j.")
    project: str | None = Field(default=None, description="Proyecto requerido para la consulta.")
    params: Dict[str, Any] | None = Field(default=None, description="Diccionario de parámetros (clave->valor).")
    database: str | None = Field(default=None, description="Base de datos Neo4j opcional.")
    formats: list[str] | None = Field(default=None, description="Formatos de respuesta requeridos (raw, table, graph).")

class CypherExportRequest(CypherRequest):
    export_format: str = Field(
        default="csv",
        description="Formato de exporte (csv o json).",
        pattern="^(csv|json)$",
    )

class CypherResponse(BaseModel):
    raw: list[Dict[str, Any]] | None = Field(default=None, description="Filas en formato raw (dict por registro).")
    table: Dict[str, Any] | None = Field(default=None, description="Vista tabular con columnas y filas.")
    graph: Dict[str, Any] | None = Field(default=None, description="Nodos y relaciones en formato de grafo.")


class Neo4jAnalyzeRequest(BaseModel):
    """Request para analizar un subgrafo 'visible' con IA y devolver evidencia mapeada a IDs."""

    project: str = Field(..., description="ID del proyecto")
    node_ids: list[str | int] = Field(default_factory=list, description="IDs internos de nodos Neo4j (id(n))")
    relationship_ids: list[str | int] = Field(default_factory=list, description="IDs internos de relaciones Neo4j (id(r))")
    max_nodes: int = Field(default=300, ge=1, le=2000)
    max_relationships: int = Field(default=600, ge=1, le=5000)


class Neo4jAnalyzeResponse(BaseModel):
    analysis: str
    structured: bool
    memo_statements: list[Dict[str, Any]]
    limits: Dict[str, Any]

# Helper functions
ALLOWED_FORMATS = {"raw", "table", "graph"}
DEFAULT_FORMATS = ["raw"]

def _normalize_formats(values: list[str] | None) -> list[str]:
    if not values:
        return DEFAULT_FORMATS.copy()
    normalized: list[str] = []
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
    except Exception as exc:
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
        buffer.write("\\n")
        for row in rows:
            buffer.write(
                ",".join(
                    '"' + str(value).replace('"', '""') + '"'
                    if isinstance(value, str)
                    else ("" if value is None else str(value))
                    for value in row
                )
            )
            buffer.write("\\n")
    return buffer.getvalue()

# Create router
router = APIRouter(prefix="/api/neo4j", tags=["Neo4j"])

# Endpoints
@router.post("/query", response_model=CypherResponse)
async def neo4j_query(
    payload: CypherRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
):
    """Execute Cypher query against Neo4j database."""
    # Import here to avoid circular dependencies
    from app.clients import build_service_clients
    
    clients = build_service_clients(settings)
    try:
        result, duration_ms = _execute_cypher(
            payload,
            settings,
            lambda cypher, params, database: run_cypher(
                clients,
                cypher,
                params=params,
                database=database,
            ),
        )
        response = JSONResponse(result)
        response.headers["X-Query-Duration"] = f"{duration_ms:.2f}"
        return response
    finally:
        clients.close()

@router.post("/export")
async def neo4j_export(
    payload: CypherExportRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
):
    """Export Cypher query results to CSV or JSON."""
    from app.clients import build_service_clients
    
    export_format = payload.export_format.lower()
    requested_formats = payload.formats
    if export_format == "csv":
        requested_formats = ["table"]
    query_payload = CypherRequest(
        cypher=payload.cypher,
        project=payload.project,
        params=payload.params,
        formats=requested_formats,
        database=payload.database,
    )
    
    clients = build_service_clients(settings)
    try:
        result, duration_ms = _execute_cypher(
            query_payload,
            settings,
            lambda cypher, params, database: run_cypher(
                clients,
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
    finally:
        clients.close()


def _to_int_ids(values: list[str | int], limit: int) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for v in values:
        if len(out) >= limit:
            break
        try:
            iv = int(str(v).strip())
        except Exception:
            continue
        if iv < 0 or iv in seen:
            continue
        out.append(iv)
        seen.add(iv)
    return out


def _truncate_json(value: Any, max_chars: int = 800) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


@router.post("/analyze", response_model=Neo4jAnalyzeResponse)
async def neo4j_analyze(
    payload: Neo4jAnalyzeRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
):
    """Analyze a visible subgraph (nodes+relationships) using the epistemic memo contract."""

    from app.clients import build_service_clients

    if not payload.project:
        raise HTTPException(status_code=400, detail="El proyecto es obligatorio.")

    try:
        resolve_project(payload.project, allow_create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    node_ids = _to_int_ids(payload.node_ids, limit=payload.max_nodes)
    rel_ids = _to_int_ids(payload.relationship_ids, limit=payload.max_relationships)

    clients = build_service_clients(settings)
    try:
        database = settings.neo4j.database

        # Fetch nodes (project isolation)
        nodes: list[Dict[str, Any]] = []
        if node_ids:
            cypher_nodes = """
            MATCH (n)
            WHERE id(n) IN $node_ids
              AND n.project_id = $project_id
            RETURN id(n) AS id, labels(n) AS labels, properties(n) AS props
            LIMIT $limit
            """
            with clients.neo4j.session(database=database) as session:
                res = session.run(
                    cypher_nodes,
                    node_ids=node_ids,
                    project_id=payload.project,
                    limit=payload.max_nodes,
                )
                for r in res:
                    nodes.append({"id": r.get("id"), "labels": r.get("labels") or [], "properties": r.get("props") or {}})

        node_id_set = {int(n["id"]) for n in nodes if n.get("id") is not None}

        # Fetch relationships (if none provided, infer intra-view relationships)
        relationships: list[Dict[str, Any]] = []
        with clients.neo4j.session(database=database) as session:
            if rel_ids:
                cypher_rels = """
                MATCH (a)-[r]->(b)
                WHERE id(r) IN $rel_ids
                  AND a.project_id = $project_id
                  AND b.project_id = $project_id
                RETURN id(r) AS id, type(r) AS type, id(a) AS start, id(b) AS end, properties(r) AS props
                LIMIT $limit
                """
                res = session.run(
                    cypher_rels,
                    rel_ids=rel_ids,
                    project_id=payload.project,
                    limit=payload.max_relationships,
                )
                for r in res:
                    relationships.append(
                        {
                            "id": r.get("id"),
                            "type": r.get("type"),
                            "start": r.get("start"),
                            "end": r.get("end"),
                            "properties": r.get("props") or {},
                        }
                    )
            elif node_id_set:
                cypher_inferred = """
                MATCH (a)-[r]->(b)
                WHERE id(a) IN $node_ids AND id(b) IN $node_ids
                  AND a.project_id = $project_id
                  AND b.project_id = $project_id
                RETURN id(r) AS id, type(r) AS type, id(a) AS start, id(b) AS end, properties(r) AS props
                LIMIT $limit
                """
                res = session.run(
                    cypher_inferred,
                    node_ids=list(node_id_set),
                    project_id=payload.project,
                    limit=payload.max_relationships,
                )
                for r in res:
                    relationships.append(
                        {
                            "id": r.get("id"),
                            "type": r.get("type"),
                            "start": r.get("start"),
                            "end": r.get("end"),
                            "properties": r.get("props") or {},
                        }
                    )

        rel_id_set = {int(rel["id"]) for rel in relationships if rel.get("id") is not None}

        if not nodes:
            raise HTTPException(status_code=400, detail="No hay nodos válidos para analizar (verifica project_id e ids).")

        # Build prompt summary (bounded)
        node_lines: list[str] = []
        for n in nodes[: min(len(nodes), 200)]:
            props = n.get("properties") or {}
            name = props.get("nombre") or props.get("name") or props.get("id")
            key_props = {
                "nombre": name,
                "community_id": props.get("community_id"),
                "score_centralidad": props.get("score_centralidad"),
            }
            node_lines.append(
                f"- node_id={n.get('id')} labels={n.get('labels')} key_props={_truncate_json(key_props, 220)}"
            )

        rel_lines: list[str] = []
        for rel in relationships[: min(len(relationships), 250)]:
            props = rel.get("properties") or {}
            key_props = {"tipo": props.get("tipo"), "evidencia": ("<list>" if isinstance(props.get("evidencia"), list) else props.get("evidencia"))}
            rel_lines.append(
                f"- rel_id={rel.get('id')} {rel.get('start')} -[:{rel.get('type')}]→ {rel.get('end')} props={_truncate_json(key_props, 220)}"
            )

        prompt = f"""Analiza el siguiente subgrafo visible de Neo4j para un proyecto de análisis cualitativo.

PROYECTO: {payload.project}

NODOS (muestra acotada):
{chr(10).join(node_lines)}

RELACIONES (muestra acotada):
{chr(10).join(rel_lines) if rel_lines else '(sin relaciones incluidas)'}

IMPORTANTE: Responde ÚNICAMENTE con un JSON válido (sin markdown, sin ```).
La síntesis debe distinguir explícitamente el estatus epistemológico de cada afirmación.
Cada item debe incluir evidencia explícita mediante IDs del grafo.

Estructura exacta requerida:
{{
  "memo_sintesis": [
    {{
      "id": "obs_1",
      "type": "OBSERVATION",
      "text": "...",
      "evidence": {{ "node_ids": [123], "relationship_ids": [456] }}
    }}
  ]
}}

REGLAS:
1) memo_sintesis: lista de 3-6 items.
2) type: uno de OBSERVATION | INTERPRETATION | HYPOTHESIS | NORMATIVE_INFERENCE.
3) text: una oración clara (español).
4) evidence.node_ids y evidence.relationship_ids deben referir IDs presentes en la vista.
5) PROHIBIDO: OBSERVATION sin evidencia (debe tener al menos 1 node_id o 1 relationship_id).
6) Sé conciso y útil para auditoría: evita párrafos largos."""

        response = clients.aoai.chat.completions.create(
            model=settings.azure.deployment_chat,
            messages=[
                {"role": "system", "content": "Eres un experto en análisis cualitativo y grafos. Respondes solo JSON válido."},
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=700,
        )

        choice = response.choices[0] if response.choices else None
        message = getattr(choice, "message", None)
        raw_content = getattr(message, "content", None) or ""

        parsed: Dict[str, Any] | None = None
        try:
            clean = re.sub(r"^```json?\s*", "", raw_content.strip())
            clean = re.sub(r"\s*```$", "", clean)
            parsed = cast(Dict[str, Any], json.loads(clean))
        except Exception:
            parsed = None

        allowed = {"OBSERVATION", "INTERPRETATION", "HYPOTHESIS", "NORMATIVE_INFERENCE"}
        memo_statements: list[Dict[str, Any]] = []
        lines: list[str] = []

        if isinstance(parsed, dict) and isinstance(parsed.get("memo_sintesis"), list):
            for idx, item in enumerate(cast(list[Any], parsed.get("memo_sintesis"))):
                if not isinstance(item, dict):
                    continue
                stype = str(item.get("type") or "").strip().upper()
                text = str(item.get("text") or "").strip()
                sid = str(item.get("id") or f"item_{idx+1}").strip()
                if not text:
                    continue
                if stype not in allowed:
                    stype = "INTERPRETATION"

                evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
                raw_node_ids = evidence.get("node_ids") if isinstance(evidence, dict) else None
                raw_rel_ids = evidence.get("relationship_ids") if isinstance(evidence, dict) else None
                ev_nodes = _to_int_ids(cast(list[Any], raw_node_ids) if isinstance(raw_node_ids, list) else [], limit=50)
                ev_rels = _to_int_ids(cast(list[Any], raw_rel_ids) if isinstance(raw_rel_ids, list) else [], limit=50)

                # Keep only IDs actually present
                ev_nodes = [n for n in ev_nodes if n in node_id_set]
                ev_rels = [r for r in ev_rels if r in rel_id_set]

                # Rule: OBSERVATION requires evidence
                if stype == "OBSERVATION" and not (ev_nodes or ev_rels):
                    stype = "INTERPRETATION"

                entry: Dict[str, Any] = {"id": sid, "type": stype, "text": text}
                entry["evidence"] = {"node_ids": ev_nodes, "relationship_ids": ev_rels}
                memo_statements.append(entry)

                if ev_nodes or ev_rels:
                    lines.append(f"[{stype}] {text} (nodes={len(ev_nodes)}, rels={len(ev_rels)})")
                else:
                    lines.append(f"[{stype}] {text}")

            analysis_text = "\n".join(lines).strip()
            structured = True
        else:
            analysis_text = raw_content.strip()
            structured = False

        return {
            "analysis": analysis_text,
            "structured": structured,
            "memo_statements": memo_statements,
            "limits": {
                "max_nodes": payload.max_nodes,
                "max_relationships": payload.max_relationships,
                "nodes_analyzed": len(nodes),
                "relationships_analyzed": len(relationships),
            },
        }
    finally:
        clients.close()
