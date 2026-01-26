"""
Operaciones de base de datos PostgreSQL.

Este es el módulo más extenso del sistema, conteniendo todas las operaciones
CRUD para PostgreSQL. Gestiona el almacenamiento relacional de:

- Fragmentos de entrevistas (con embeddings)
- Códigos abiertos (etapa 3)
- Relaciones axiales (etapa 4)
- Métricas y estadísticas de codificación
- Comparaciones constantes y member checking

Tablas principales:
    - fragmentos: Textos fragmentados con embeddings y metadatos
    - open_codes: Códigos abiertos asignados por el LLM
    - axial_relationships: Relaciones categoría-código

Funciones de gestión de tablas (ensure_*):
    - ensure_fragment_table(): Tabla de fragmentos
    - ensure_open_coding_table(): Tabla de códigos abiertos
    - ensure_axial_table(): Tabla de relaciones axiales
    - ensure_comparison_table(): Tabla de comparaciones constantes
    - ensure_nucleus_notes_table(): Notas del núcleo semántico

Funciones de inserción (insert_*, upsert_*):
    - insert_fragments(): Inserta fragmentos con embeddings
    - upsert_open_codes(): Upsert de códigos abiertos
    - upsert_axial_relationships(): Upsert de relaciones axiales

Funciones de consulta (fetch_*, list_*, get_*):
    - fetch_fragment_by_id(): Obtiene fragmento por ID
    - list_interviews_summary(): Resumen de entrevistas
    - list_codes_summary(): Resumen de códigos con frecuencias
    - coding_stats(): Estadísticas generales de codificación
    - cumulative_code_curve(): Curva de saturación teórica

Type Aliases:
    - Row: Tupla de datos de fragmento
    - OpenCodeRow: Tupla de código abierto
    - AxialRow: Tupla de relación axial
"""

from __future__ import annotations

from collections import defaultdict
import threading
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from psycopg2.extensions import connection as PGConnection
from psycopg2.extras import execute_values, Json
import logging

_logger = logging.getLogger(__name__)


def ensure_unaccent(pg_conn: PGConnection) -> bool:
    """Habilita la extensión unaccent si no existe (normalización de texto)."""
    try:
        with pg_conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")
        pg_conn.commit()
        return True
    except Exception as exc:
        _logger.warning("unaccent.not_available", extra={"error": str(exc)})
        try:
            pg_conn.rollback()
        except Exception:
            pass
        return False

# Guard flags to avoid re-running heavy DDL on every request (helps prevent
# statement timeouts when PG has a low statement_timeout).
_fragment_table_ready = False
_fragment_table_lock = threading.Lock()
_open_coding_table_ready = False
_open_coding_table_lock = threading.Lock()

_codes_catalog_table_ready = False
_codes_catalog_table_lock = threading.Lock()

Row = Tuple[
    str,  # project_id
    str,  # id
    str,  # archivo
    int,  # par_idx
    str,  # fragmento
    Sequence[float],  # embedding
    int,  # char_len
    str,  # sha256
    Optional[str],  # area_tematica
    Optional[str],  # actor_principal
    Optional[bool],  # requiere_protocolo_lluvia
    Optional[Dict[str, Any]],  # metadata
    Optional[str],  # speaker
    int,  # interviewer_tokens
    int,  # interviewee_tokens
]

OpenCodeRow = Tuple[
    str,  # project_id
    str,  # fragmento_id
    str,  # codigo
    str,  # archivo
    str,  # cita
    Optional[str],  # fuente
    Optional[str],  # memo
    Optional[int],  # code_id (new)
]

AxialRow = Tuple[
    str,  # project_id
    str,  # categoria
    str,  # codigo
    str,  # relacion/tipo
    str,  # archivo
    Optional[str],  # memo
    List[str],  # evidencia fragment ids
]


# =============================================================================
# Report Jobs (Async) - Durable store
# =============================================================================


def ensure_report_jobs_table(pg: PGConnection) -> None:
    """Ensure a durable job table for long-running report generation.

    This table is used for async endpoints that return a `task_id` and later allow
    polling `status` and fetching `result`.
    """
    sql = """
    CREATE TABLE IF NOT EXISTS report_jobs (
        id SERIAL PRIMARY KEY,
        task_id TEXT NOT NULL UNIQUE,
        job_type TEXT NOT NULL,
        project_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        message TEXT,
        payload JSONB,
        auth JSONB,
        errors JSONB,
        result JSONB,
        result_path TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        started_at TIMESTAMPTZ,
        finished_at TIMESTAMPTZ,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_report_jobs_project ON report_jobs(project_id);
    CREATE INDEX IF NOT EXISTS ix_report_jobs_type ON report_jobs(job_type);
    CREATE INDEX IF NOT EXISTS ix_report_jobs_status ON report_jobs(status);
    CREATE INDEX IF NOT EXISTS ix_report_jobs_created ON report_jobs(created_at);
    """
    with pg.cursor() as cur:
        cur.execute(sql)
    pg.commit()


def create_report_job(
    pg: PGConnection,
    *,
    task_id: str,
    job_type: str,
    project_id: str,
    payload: Optional[Dict[str, Any]] = None,
    auth: Optional[Dict[str, Any]] = None,
    message: Optional[str] = None,
) -> None:
    ensure_report_jobs_table(pg)
    with pg.cursor() as cur:
        cur.execute(
            """
            INSERT INTO report_jobs (task_id, job_type, project_id, status, message, payload, auth, errors)
            VALUES (%s, %s, %s, 'pending', %s, %s, %s, %s)
            ON CONFLICT (task_id) DO NOTHING
            """,
            (
                task_id,
                job_type,
                project_id,
                message,
                Json(payload) if payload is not None else None,
                Json(auth) if auth is not None else None,
                Json([]),
            ),
        )
    pg.commit()


def update_report_job(
    pg: PGConnection,
    *,
    task_id: str,
    status: Optional[str] = None,
    message: Optional[str] = None,
    errors: Optional[List[str]] = None,
    result: Optional[Dict[str, Any]] = None,
    result_path: Optional[str] = None,
    started_at: Optional[str] = None,
    finished_at: Optional[str] = None,
) -> None:
    ensure_report_jobs_table(pg)

    fields: List[str] = ["updated_at = NOW()"]
    values: List[Any] = []
    if status is not None:
        fields.append("status = %s")
        values.append(status)
    if message is not None:
        fields.append("message = %s")
        values.append(message)
    if errors is not None:
        fields.append("errors = %s")
        values.append(Json(errors))
    if result is not None:
        fields.append("result = %s")
        values.append(Json(result))
    if result_path is not None:
        fields.append("result_path = %s")
        values.append(result_path)
    if started_at is not None:
        fields.append("started_at = %s::timestamptz")
        values.append(started_at)
    if finished_at is not None:
        fields.append("finished_at = %s::timestamptz")
        values.append(finished_at)

    if len(fields) == 1:
        return

    sql = f"UPDATE report_jobs SET {', '.join(fields)} WHERE task_id = %s"
    values.append(task_id)
    with pg.cursor() as cur:
        cur.execute(sql, tuple(values))
    pg.commit()


def get_report_job(pg: PGConnection, task_id: str) -> Optional[Dict[str, Any]]:
    ensure_report_jobs_table(pg)
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT task_id, job_type, project_id, status, message, payload, auth, errors, result, result_path,
                   created_at, started_at, finished_at, updated_at
              FROM report_jobs
             WHERE task_id = %s
            """,
            (task_id,),
        )
        row = cur.fetchone()
    if not row:
        return None

    def _json(val: Any) -> Any:
        return val

    return {
        "task_id": row[0],
        "job_type": row[1],
        "project_id": row[2],
        "status": row[3],
        "message": row[4],
        "payload": _json(row[5]),
        "auth": _json(row[6]),
        "errors": _json(row[7]),
        "result": _json(row[8]),
        "result_path": row[9],
        "created_at": row[10].isoformat() if row[10] else None,
        "started_at": row[11].isoformat() if row[11] else None,
        "finished_at": row[12].isoformat() if row[12] else None,
        "updated_at": row[13].isoformat() if row[13] else None,
    }


def list_report_jobs(
    pg: PGConnection,
    *,
    project_id: str,
    limit: int = 50,
    offset: int = 0,
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    task_id: Optional[str] = None,
    task_id_prefix: Optional[str] = None,
    q: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List recent report jobs for a project.

    Notes:
    - `user_id` filters by auth.user_id when available.
    - We intentionally return a concise payload for UI history.
    """
    ensure_report_jobs_table(pg)
    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))

    where = ["project_id = %s"]
    params: List[Any] = [project_id]

    if task_id:
        where.append("task_id = %s")
        params.append(str(task_id))

    if task_id_prefix:
        where.append("task_id LIKE %s")
        params.append(f"{str(task_id_prefix)}%")

    if user_id:
        where.append("COALESCE(auth->>'user_id','') = %s")
        params.append(str(user_id))
    if status:
        where.append("status = %s")
        params.append(str(status))
    if job_type:
        where.append("job_type = %s")
        params.append(str(job_type))

    if q:
        # Best-effort substring search for operational UX.
        # (Can be optimized later with pg_trgm if needed.)
        where.append("COALESCE(message,'') ILIKE %s")
        params.append(f"%{str(q)}%")

    sql = f"""
        SELECT task_id, job_type, project_id, status, message, auth, errors, result, result_path,
               created_at, started_at, finished_at, updated_at
          FROM report_jobs
         WHERE {' AND '.join(where)}
         ORDER BY updated_at DESC, task_id DESC
         LIMIT %s OFFSET %s
    """
    params.append(limit)
    params.append(offset)

    items: List[Dict[str, Any]] = []
    with pg.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []

    for row in rows:
        auth = row[5] if isinstance(row[5], dict) else {}
        result = row[7] if isinstance(row[7], dict) else {}
        blob_url = None
        if isinstance(result, dict):
            v = result.get("blob_url")
            if isinstance(v, str) and v.strip():
                blob_url = v.strip()
        items.append(
            {
                "task_id": row[0],
                "job_type": row[1],
                "project_id": row[2],
                "status": row[3],
                "message": row[4],
                "user_id": (auth or {}).get("user_id"),
                "errors": row[6],
                "result_path": row[8],
                "blob_url": blob_url,
                "created_at": row[9].isoformat() if row[9] else None,
                "started_at": row[10].isoformat() if row[10] else None,
                "finished_at": row[11].isoformat() if row[11] else None,
                "updated_at": row[12].isoformat() if row[12] else None,
            }
        )

    return items


def ensure_comparison_table(pg: PGConnection) -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS analisis_comparacion_constante (
        id SERIAL PRIMARY KEY,
        run_id TEXT NOT NULL,
        proyecto TEXT,
        fragmento_semilla TEXT NOT NULL,
        filtros JSONB,
        top_k INT,
        sugerencias JSONB NOT NULL,
        llm_model TEXT,
        llm_summary TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_acc_run ON analisis_comparacion_constante(run_id);
    CREATE INDEX IF NOT EXISTS ix_acc_fragmento ON analisis_comparacion_constante(fragmento_semilla);
    """
    with pg.cursor() as cur:
        cur.execute(sql)
    pg.commit()


def log_constant_comparison(
    pg: PGConnection,
    *,
    run_id: str,
    project: Optional[str],
    fragmento_semilla: str,
    top_k: int,
    filtros: Optional[Dict[str, Any]],
    sugerencias: List[Dict[str, Any]],
    llm_model: Optional[str] = None,
    llm_summary: Optional[str] = None,
) -> int:
    ensure_comparison_table(pg)
    sql = """
    INSERT INTO analisis_comparacion_constante (
        run_id,
        proyecto,
        fragmento_semilla,
        filtros,
        top_k,
        sugerencias,
        llm_model,
        llm_summary
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    RETURNING id
    """
    with pg.cursor() as cur:
        cur.execute(
            sql,
            (
                run_id,
                project,
                fragmento_semilla,
                Json(filtros) if filtros is not None else None,
                top_k,
                Json(sugerencias),
                llm_model,
                llm_summary,
            ),
        )
        row = cur.fetchone()
    pg.commit()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


# =============================================================================
# Sprint 24: Discovery Navigation Log - Muestreo Teórico
# =============================================================================

def ensure_discovery_navigation_table(pg: PGConnection) -> None:
    """
    Crea tabla para registrar navegación de búsquedas Discovery.
    
    Permite trazar cómo evolucionó la exploración durante el muestreo teórico.
    """
    sql = """
    CREATE TABLE IF NOT EXISTS discovery_navigation_log (
        id SERIAL PRIMARY KEY,
        project_id TEXT NOT NULL,
        busqueda_id UUID DEFAULT gen_random_uuid(),
        busqueda_origen_id UUID,  -- NULL = primera búsqueda
        positivos TEXT[],
        negativos TEXT[],
        target_text TEXT,
        fragments_count INT,
        codigos_sugeridos TEXT[],
        refinamientos_aplicados JSONB,
        ai_synthesis TEXT,
        action_taken TEXT,  -- 'search', 'refine', 'send_codes'
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_dnl_project ON discovery_navigation_log(project_id);
    CREATE INDEX IF NOT EXISTS ix_dnl_busqueda ON discovery_navigation_log(busqueda_id);
    CREATE INDEX IF NOT EXISTS ix_dnl_origen ON discovery_navigation_log(busqueda_origen_id);
    CREATE INDEX IF NOT EXISTS ix_dnl_created ON discovery_navigation_log(created_at);
    """
    with pg.cursor() as cur:
        cur.execute(sql)
    pg.commit()


def log_discovery_navigation(
    pg: PGConnection,
    *,
    project: str,
    positivos: List[str],
    negativos: List[str],
    target_text: Optional[str],
    fragments_count: int,
    codigos_sugeridos: Optional[List[str]] = None,
    refinamientos_aplicados: Optional[Dict[str, Any]] = None,
    ai_synthesis: Optional[str] = None,
    action_taken: str = "search",
    busqueda_origen_id: Optional[str] = None,
    # E3-1.2: Additional fields for E3 traceability
    seed_fragmento_id: Optional[str] = None,
    scope_archivo: Optional[str] = None,
    top_k: Optional[int] = None,
    include_coded: Optional[bool] = None,
) -> str:
    """
    Registra una navegación de búsqueda Discovery para trazabilidad.
    
    Args:
        project: ID del proyecto
        positivos: Lista de conceptos positivos usados
        negativos: Lista de conceptos negativos usados
        target_text: Texto objetivo opcional
        fragments_count: Cantidad de fragmentos encontrados
        codigos_sugeridos: Códigos sugeridos por IA (si aplica)
        refinamientos_aplicados: Refinamientos aplicados desde IA
        ai_synthesis: Texto de síntesis IA
        action_taken: Acción realizada ('search', 'refine', 'send_codes', 'e3_*')
        busqueda_origen_id: UUID de búsqueda padre (si es refinamiento)
        seed_fragmento_id: E3 - Fragmento semilla para sugerencias
        scope_archivo: E3 - Filtro de scope por archivo
        top_k: E3 - Cantidad de fragmentos similares solicitados
        include_coded: E3 - Incluir fragmentos ya codificados
        
    Returns:
        UUID de la nueva entrada
    """
    ensure_discovery_navigation_table(pg)
    
    # E3-1.2: Merge E3 fields into refinamientos_aplicados for storage
    merged_refinements = dict(refinamientos_aplicados or {})
    if seed_fragmento_id is not None:
        merged_refinements["seed_fragmento_id"] = seed_fragmento_id
    if scope_archivo is not None:
        merged_refinements["scope_archivo"] = scope_archivo
    if top_k is not None:
        merged_refinements["top_k"] = top_k
    if include_coded is not None:
        merged_refinements["include_coded"] = include_coded
    
    sql = """
    INSERT INTO discovery_navigation_log (
        project_id,
        busqueda_origen_id,
        positivos,
        negativos,
        target_text,
        fragments_count,
        codigos_sugeridos,
        refinamientos_aplicados,
        ai_synthesis,
        action_taken
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    RETURNING busqueda_id::text
    """
    with pg.cursor() as cur:
        cur.execute(
            sql,
            (
                project,
                busqueda_origen_id,
                positivos,
                negativos,
                target_text,
                fragments_count,
                codigos_sugeridos or [],
                Json(merged_refinements) if merged_refinements else None,
                ai_synthesis,
                action_taken,
            ),
        )
        row = cur.fetchone()
    pg.commit()
    if row is None:
        return ""
    return row[0]


def get_discovery_navigation_history(
    pg: PGConnection,
    project: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Obtiene el historial de navegación Discovery para un proyecto.
    
    Returns:
        Lista de entradas de navegación ordenadas por fecha desc
    """
    ensure_discovery_navigation_table(pg)
    
    sql = """
    SELECT 
        id,
        busqueda_id::text,
        busqueda_origen_id::text,
        positivos,
        negativos,
        target_text,
        fragments_count,
        codigos_sugeridos,
        refinamientos_aplicados,
        ai_synthesis,
        action_taken,
        created_at
    FROM discovery_navigation_log
    WHERE project_id = %s
    ORDER BY created_at DESC
    LIMIT %s
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project, limit))
        rows = cur.fetchall()
    
    return [
        {
            "id": r[0],
            "busqueda_id": r[1],
            "busqueda_origen_id": r[2],
            "positivos": r[3] or [],
            "negativos": r[4] or [],
            "target_text": r[5],
            "fragments_count": r[6],
            "codigos_sugeridos": r[7] or [],
            "refinamientos_aplicados": r[8],
            "ai_synthesis": (r[9] or "")[:200] + "..." if r[9] and len(r[9]) > 200 else r[9],
            "action_taken": r[10],
            "created_at": r[11].isoformat().replace("+00:00", "Z") if r[11] else None,
        }
        for r in rows
    ]


# =============================================================================
# Sprint 29: Discovery Runs - Iteraciones y métricas de refinamiento
# =============================================================================

def ensure_discovery_runs_table(pg: PGConnection) -> None:
    """
    Crea tabla para registrar iteraciones de Discovery (refinamientos por concepto).
    Guarda overlap y landing_rate para evidenciar consolidación y comparación constante.
    """
    sql = """
    CREATE TABLE IF NOT EXISTS discovery_runs (
        id SERIAL PRIMARY KEY,
        project_id TEXT NOT NULL,
        concepto TEXT NOT NULL,
        scope TEXT NOT NULL, -- 'per_interview' | 'global'
        iter INT NOT NULL DEFAULT 0,
        archivo TEXT,
        query TEXT,
        positivos TEXT[],
        negativos TEXT[],
        overlap NUMERIC,
        landing_rate NUMERIC,
        top_fragments JSONB,
        memo TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_dr_project ON discovery_runs(project_id);
    CREATE INDEX IF NOT EXISTS ix_dr_project_concept ON discovery_runs(project_id, concepto);
    CREATE INDEX IF NOT EXISTS ix_dr_scope_iter ON discovery_runs(project_id, scope, iter DESC);
    """
    with pg.cursor() as cur:
        cur.execute(sql)
    pg.commit()


def insert_discovery_run(
    pg: PGConnection,
    *,
    project: str,
    concepto: str,
    scope: str,
    iter_index: int,
    archivo: Optional[str],
    query: Optional[str],
    positivos: Optional[List[str]],
    negativos: Optional[List[str]],
    overlap: Optional[float],
    landing_rate: Optional[float],
    top_fragments: Optional[List[Dict[str, Any]]],
    memo: Optional[str],
) -> Dict[str, Any]:
    """Inserta una iteración de Discovery y retorna identificador y timestamp."""
    ensure_discovery_runs_table(pg)

    sql = """
    INSERT INTO discovery_runs (
        project_id, concepto, scope, iter, archivo, query, positivos, negativos,
        overlap, landing_rate, top_fragments, memo
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    RETURNING id, created_at
    """
    with pg.cursor() as cur:
        cur.execute(
            sql,
            (
                project,
                concepto,
                scope,
                iter_index,
                archivo,
                query,
                positivos or [],
                negativos or [],
                overlap,
                landing_rate,
                Json(top_fragments) if top_fragments else None,
                memo,
            ),
        )
        row = cur.fetchone()
    pg.commit()
    if not row:
        return {"id": None, "created_at": None}
    return {
        "id": row[0],
        "created_at": row[1].isoformat().replace("+00:00", "Z") if row[1] else None,
    }


def get_discovery_runs(
    pg: PGConnection,
    *,
    project: str,
    concepto: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Obtiene iteraciones de Discovery más recientes para un proyecto (y opcionalmente un concepto)."""
    ensure_discovery_runs_table(pg)

    base_sql = """
    SELECT id, project_id, concepto, scope, iter, archivo, query, positivos, negativos,
           overlap, landing_rate, top_fragments, memo, created_at
    FROM discovery_runs
    WHERE project_id = %s
    """
    params: List[Any] = [project]

    if concepto:
        base_sql += " AND concepto = %s"
        params.append(concepto)

    base_sql += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)

    with pg.cursor() as cur:
        cur.execute(base_sql, params)
        rows = cur.fetchall()

    results: List[Dict[str, Any]] = []
    for r in rows:
        results.append(
            {
                "id": r[0],
                "project_id": r[1],
                "concepto": r[2],
                "scope": r[3],
                "iter": r[4],
                "archivo": r[5],
                "query": r[6],
                "positivos": r[7] or [],
                "negativos": r[8] or [],
                "overlap": float(r[9]) if r[9] is not None else None,
                "landing_rate": float(r[10]) if r[10] is not None else None,
                "top_fragments": r[11],
                "memo": r[12],
                "created_at": r[13].isoformat().replace("+00:00", "Z") if r[13] else None,
            }
        )
    return results


def calculate_landing_rate(
    pg: PGConnection,
    project: str,
    discovery_fragment_ids: List[str],
) -> Dict[str, Any]:
    """
    Calcula el landing rate: proporción de fragmentos de Discovery
    que ya tienen códigos axiales asignados.
    
    Landing rate alto = conceptos de Discovery coinciden con patrones ya codificados
    Landing rate bajo = Discovery encontró fragmentos nuevos (puede ser bueno para muestreo teórico)
    
    Args:
        pg: Conexión PostgreSQL
        project: ID del proyecto
        discovery_fragment_ids: IDs de fragmentos encontrados en Discovery
    
    Returns:
        Dict con landing_rate, matched_count, total_count, matched_codes
    """
    if not discovery_fragment_ids:
        return {
            "landing_rate": 0.0,
            "matched_count": 0,
            "total_count": 0,
            "matched_codes": [],
            "reason": "no_fragments",
        }

    # Diagnostic: if there is no definitive/open coding at all for this project,
    # landing rate will always be 0 regardless of Discovery results.
    with pg.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM analisis_codigos_abiertos WHERE project_id = %s",
            (project,),
        )
        row = cur.fetchone()
    project_open_code_rows = int(row[0] or 0) if row else 0
    
    sql = """
    SELECT DISTINCT aca.fragmento_id, aca.codigo
    FROM analisis_codigos_abiertos aca
    WHERE aca.project_id = %s
      AND aca.fragmento_id = ANY(%s)
    """
    
    with pg.cursor() as cur:
        cur.execute(sql, (project, discovery_fragment_ids))
        rows = cur.fetchall()
    
    matched_fragment_ids = set(r[0] for r in rows)
    matched_codes = list(set(r[1] for r in rows))
    
    landing_rate = len(matched_fragment_ids) / len(discovery_fragment_ids) if discovery_fragment_ids else 0.0

    if project_open_code_rows == 0:
        reason = "no_definitive_codes"
    elif len(matched_fragment_ids) == 0:
        reason = "no_overlap_with_definitive_codes"
    else:
        reason = "ok"
    
    return {
        "landing_rate": round(landing_rate * 100, 1),  # Porcentaje
        "matched_count": len(matched_fragment_ids),
        "total_count": len(discovery_fragment_ids),
        "matched_codes": matched_codes[:10],  # Top 10 códigos
        "project_open_code_rows": project_open_code_rows,
        "reason": reason,
    }


def get_project_axial_codes(pg: PGConnection, project: str, limit: int = 100) -> List[str]:
    """
    Obtiene lista de códigos axiales únicos para un proyecto.
    
    Útil para comparar conceptos de Discovery con códigos existentes.
    """
    sql = """
    SELECT DISTINCT codigo
    FROM analisis_codigos_abiertos
    WHERE project_id = %s
    ORDER BY codigo
    LIMIT %s
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project, limit))
        rows = cur.fetchall()
    return [r[0] for r in rows]


# =============================================================================
# Sprint 26: Doctoral Reports - Persistencia de Informes
# =============================================================================

def ensure_doctoral_reports_table(pg: PGConnection) -> None:
    """
    Crea tabla para almacenar informes doctorales generados.
    
    Permite:
    - Historial de informes por etapa
    - Recuperación para análisis comparativo
    - Trazabilidad del proceso doctoral
    """
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type, udt_name
              FROM information_schema.columns
             WHERE table_name = 'doctoral_reports'
            """
        )
        rows = cur.fetchall()
        existing_cols = {r[0] for r in rows}

        # If the table doesn't exist, create the *new* schema.
        if not existing_cols:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS doctoral_reports (
                    id SERIAL PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    stage TEXT NOT NULL,  -- 'stage3', 'stage4', 'stage5'
                    content TEXT NOT NULL,
                    stats JSONB,
                    file_path TEXT,
                    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS ix_doctoral_project ON doctoral_reports(project_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_doctoral_stage ON doctoral_reports(stage);")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_doctoral_generated ON doctoral_reports(generated_at);")
            pg.commit()
            return

        # Legacy schema detected (from scripts/init_schema.sql):
        # doctoral_reports(id, proyecto, report_type, content JSONB, metadata JSONB, created_at)
        if "proyecto" in existing_cols or "report_type" in existing_cols:
            # Ensure minimal legacy columns exist (non-destructive)
            cur.execute("ALTER TABLE doctoral_reports ADD COLUMN IF NOT EXISTS proyecto TEXT;")
            cur.execute("ALTER TABLE doctoral_reports ADD COLUMN IF NOT EXISTS report_type VARCHAR(100);")
            cur.execute("ALTER TABLE doctoral_reports ADD COLUMN IF NOT EXISTS content JSONB;")
            cur.execute("ALTER TABLE doctoral_reports ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;")
            cur.execute("ALTER TABLE doctoral_reports ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_doctoral_proyecto ON doctoral_reports(proyecto);")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_doctoral_created_at ON doctoral_reports(created_at);")
            pg.commit()
            return

        # Table exists but doesn't look legacy; try to converge to new schema without destructive changes.
        cur.execute("ALTER TABLE doctoral_reports ADD COLUMN IF NOT EXISTS project_id TEXT;")
        cur.execute("ALTER TABLE doctoral_reports ADD COLUMN IF NOT EXISTS stage TEXT;")
        cur.execute("ALTER TABLE doctoral_reports ADD COLUMN IF NOT EXISTS content TEXT;")
        cur.execute("ALTER TABLE doctoral_reports ADD COLUMN IF NOT EXISTS stats JSONB;")
        cur.execute("ALTER TABLE doctoral_reports ADD COLUMN IF NOT EXISTS file_path TEXT;")
        cur.execute("ALTER TABLE doctoral_reports ADD COLUMN IF NOT EXISTS generated_at TIMESTAMPTZ DEFAULT NOW();")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_doctoral_project ON doctoral_reports(project_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_doctoral_stage ON doctoral_reports(stage);")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_doctoral_generated ON doctoral_reports(generated_at);")
    pg.commit()


def save_doctoral_report(
    pg: PGConnection,
    *,
    project: str,
    stage: str,
    content: str,
    stats: Optional[Dict[str, Any]] = None,
    file_path: Optional[str] = None,
) -> int:
    """
    Guarda un informe doctoral en la base de datos.
    
    Args:
        project: ID del proyecto
        stage: Etapa del informe ('stage3', 'stage4', 'stage5')
        content: Contenido Markdown del informe
        stats: Estadísticas del informe (JSON)
        file_path: Ruta del archivo guardado
        
    Returns:
        ID del informe guardado
    """
    ensure_doctoral_reports_table(pg)

    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_name = 'doctoral_reports'
            """
        )
        cols = {r[0] for r in cur.fetchall()}

        # Legacy schema path
        if "proyecto" in cols or "report_type" in cols:
            payload = {
                "markdown": content,
                "stage": stage,
            }
            meta: Dict[str, Any] = {"stage": stage}
            if stats is not None:
                meta["stats"] = stats
            if file_path is not None:
                meta["file_path"] = file_path

            cur.execute(
                """
                INSERT INTO doctoral_reports (proyecto, report_type, content, metadata)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (
                    project,
                    f"doctoral_{stage}",
                    Json(payload),
                    Json(meta),
                ),
            )
            row = cur.fetchone()
            pg.commit()
            if row is None:
                return 0
            return int(row[0])

        # New schema path
        cur.execute(
            """
            INSERT INTO doctoral_reports (project_id, stage, content, stats, file_path)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                project,
                stage,
                content,
                Json(stats) if stats else None,
                file_path,
            ),
        )
        row = cur.fetchone()
    pg.commit()
    if row is None:
        return 0
    return int(row[0])


def list_doctoral_reports(
    pg: PGConnection,
    project: str,
    stage: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Lista informes doctorales de un proyecto.
    
    Args:
        project: ID del proyecto
        stage: Filtrar por etapa (opcional)
        limit: Máximo de resultados
        
    Returns:
        Lista de informes con metadatos (sin contenido completo)
    """
    ensure_doctoral_reports_table(pg)

    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_name = 'doctoral_reports'
            """
        )
        cols = {r[0] for r in cur.fetchall()}

        # Legacy schema query
        if "proyecto" in cols or "report_type" in cols:
            if stage:
                sql = """
                SELECT id,
                       COALESCE(metadata->>'stage', report_type) AS stage,
                       COALESCE(metadata->>'file_path', NULL) AS file_path,
                       metadata->'stats' AS stats,
                       created_at,
                       LENGTH(COALESCE(content->>'markdown', content::text)) AS content_length
                  FROM doctoral_reports
                 WHERE proyecto = %s
                   AND (metadata->>'stage' = %s OR report_type = %s)
                 ORDER BY created_at DESC
                 LIMIT %s
                """
                params = (project, stage, f"doctoral_{stage}", limit)
            else:
                sql = """
                SELECT id,
                       COALESCE(metadata->>'stage', report_type) AS stage,
                       COALESCE(metadata->>'file_path', NULL) AS file_path,
                       metadata->'stats' AS stats,
                       created_at,
                       LENGTH(COALESCE(content->>'markdown', content::text)) AS content_length
                  FROM doctoral_reports
                 WHERE proyecto = %s
                 ORDER BY created_at DESC
                 LIMIT %s
                """
                params = (project, limit)
            cur.execute(sql, params)
            rows = cur.fetchall()
        else:
            # New schema query
            if stage:
                sql = """
                SELECT id, stage, file_path, stats, generated_at,
                       LENGTH(content) as content_length
                FROM doctoral_reports
                WHERE project_id = %s AND stage = %s
                ORDER BY generated_at DESC
                LIMIT %s
                """
                params = (project, stage, limit)
            else:
                sql = """
                SELECT id, stage, file_path, stats, generated_at,
                       LENGTH(content) as content_length
                FROM doctoral_reports
                WHERE project_id = %s
                ORDER BY generated_at DESC
                LIMIT %s
                """
                params = (project, limit)
            cur.execute(sql, params)
            rows = cur.fetchall()
    
    return [
        {
            "id": r[0],
            "stage": r[1],
            "file_path": r[2],
            "stats": r[3],
            "generated_at": r[4].isoformat().replace("+00:00", "Z") if r[4] else None,
            "content_length": r[5],
        }
        for r in rows
    ]


def get_doctoral_report(pg: PGConnection, report_id: int) -> Optional[Dict[str, Any]]:
    """Obtiene un informe doctoral completo por ID."""
    ensure_doctoral_reports_table(pg)

    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_name = 'doctoral_reports'
            """
        )
        cols = {r[0] for r in cur.fetchall()}

        # Legacy schema
        if "proyecto" in cols or "report_type" in cols:
            cur.execute(
                """
                SELECT id,
                       proyecto,
                       COALESCE(metadata->>'stage', report_type) AS stage,
                       COALESCE(content->>'markdown', content::text) AS content,
                       metadata->'stats' AS stats,
                       COALESCE(metadata->>'file_path', NULL) AS file_path,
                       created_at
                  FROM doctoral_reports
                 WHERE id = %s
                """,
                (report_id,),
            )
            row = cur.fetchone()
        else:
            cur.execute(
                """
                SELECT id, project_id, stage, content, stats, file_path, generated_at
                FROM doctoral_reports
                WHERE id = %s
                """,
                (report_id,),
            )
            row = cur.fetchone()
    
    if row is None:
        return None
    
    return {
        "id": row[0],
        "project_id": row[1],
        "stage": row[2],
        "content": row[3],
        "stats": row[4],
        "file_path": row[5],
        "generated_at": row[6].isoformat().replace("+00:00", "Z") if row[6] else None,
    }


# =============================================================================
# Sprint 27: Analysis Insights - Muestreo Teórico Automatizado
# =============================================================================

def ensure_insights_table(pg: PGConnection) -> None:
    """
    Crea tabla para almacenar insights de análisis.
    
    Los insights son hipótesis abductivas generadas automáticamente
    que sugieren nuevas búsquedas siguiendo el muestreo teórico.
    """
    sql = """
    CREATE TABLE IF NOT EXISTS analysis_insights (
        id SERIAL PRIMARY KEY,
        project_id TEXT NOT NULL,
        source_type TEXT NOT NULL,  -- 'discovery', 'coding', 'link_prediction', 'report'
        source_id TEXT,             -- ID del análisis origen
        insight_type TEXT NOT NULL, -- 'explore', 'validate', 'saturate', 'merge'
        content TEXT NOT NULL,      -- Descripción del insight
        suggested_query JSONB,      -- Búsqueda sugerida automática
        priority FLOAT DEFAULT 0.5, -- 0-1, calculado por relevancia
        status TEXT DEFAULT 'pending', -- 'pending', 'executed', 'dismissed'
        execution_result JSONB,     -- Resultado de ejecutar la sugerencia
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_insights_project ON analysis_insights(project_id);
    CREATE INDEX IF NOT EXISTS ix_insights_status ON analysis_insights(status);
    CREATE INDEX IF NOT EXISTS ix_insights_type ON analysis_insights(insight_type);
    CREATE INDEX IF NOT EXISTS ix_insights_source ON analysis_insights(source_type);
    """
    with pg.cursor() as cur:
        cur.execute(sql)
    pg.commit()


def save_insight(
    pg: PGConnection,
    *,
    project: str,
    source_type: str,
    insight_type: str,
    content: str,
    source_id: Optional[str] = None,
    suggested_query: Optional[Dict[str, Any]] = None,
    priority: float = 0.5,
) -> int:
    """
    Guarda un insight de análisis.
    
    Args:
        project: ID del proyecto
        source_type: 'discovery', 'coding', 'link_prediction', 'report'
        insight_type: 'explore', 'validate', 'saturate', 'merge'
        content: Descripción del insight
        source_id: ID del análisis que generó el insight
        suggested_query: Búsqueda sugerida (JSONB)
        priority: Prioridad 0-1
        
    Returns:
        ID del insight guardado
    """
    ensure_insights_table(pg)
    
    sql = """
    INSERT INTO analysis_insights (
        project_id, source_type, source_id, insight_type, 
        content, suggested_query, priority
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    RETURNING id
    """
    with pg.cursor() as cur:
        cur.execute(
            sql,
            (
                project,
                source_type,
                source_id,
                insight_type,
                content,
                Json(suggested_query) if suggested_query else None,
                priority,
            ),
        )
        row = cur.fetchone()
    pg.commit()
    if row is None:
        return 0
    return int(row[0])


def list_insights(
    pg: PGConnection,
    project: str,
    status: Optional[str] = None,
    source_type: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Lista insights de un proyecto.
    
    Args:
        project: ID del proyecto
        status: Filtrar por status ('pending', 'executed', 'dismissed')
        source_type: Filtrar por fuente
        limit: Máximo de resultados
        
    Returns:
        Lista de insights
    """
    ensure_insights_table(pg)
    
    clauses = ["project_id = %s"]
    params: List[Any] = [project]
    
    if status:
        clauses.append("status = %s")
        params.append(status)
    if source_type:
        clauses.append("source_type = %s")
        params.append(source_type)
    
    where = " AND ".join(clauses)
    
    sql = f"""
    SELECT id, source_type, source_id, insight_type, content,
           suggested_query, priority, status, created_at
    FROM analysis_insights
    WHERE {where}
    ORDER BY priority DESC, created_at DESC
    LIMIT %s
    """
    params.append(limit)
    
    with pg.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    
    return [
        {
            "id": r[0],
            "source_type": r[1],
            "source_id": r[2],
            "insight_type": r[3],
            "content": r[4],
            "suggested_query": r[5],
            "priority": r[6],
            "status": r[7],
            "created_at": r[8].isoformat().replace("+00:00", "Z") if r[8] else None,
        }
        for r in rows
    ]


def update_insight_status(
    pg: PGConnection,
    insight_id: int,
    status: str,
    execution_result: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Actualiza el estado de un insight.
    
    Args:
        insight_id: ID del insight
        status: Nuevo status ('pending', 'executed', 'dismissed')
        execution_result: Resultado de la ejecución (si aplica)
        
    Returns:
        True si se actualizó correctamente
    """
    ensure_insights_table(pg)
    
    sql = """
    UPDATE analysis_insights
    SET status = %s, 
        execution_result = %s,
        updated_at = NOW()
    WHERE id = %s
    RETURNING id
    """
    with pg.cursor() as cur:
        cur.execute(
            sql,
            (
                status,
                Json(execution_result) if execution_result else None,
                insight_id,
            ),
        )
        row = cur.fetchone()
    pg.commit()
    return row is not None


def get_insight(pg: PGConnection, insight_id: int) -> Optional[Dict[str, Any]]:
    """Obtiene un insight por ID."""
    ensure_insights_table(pg)
    
    sql = """
    SELECT id, project_id, source_type, source_id, insight_type, 
           content, suggested_query, priority, status, 
           execution_result, created_at, updated_at
    FROM analysis_insights
    WHERE id = %s
    """
    with pg.cursor() as cur:
        cur.execute(sql, (insight_id,))
        row = cur.fetchone()
    
    if row is None:
        return None
    
    return {
        "id": row[0],
        "project_id": row[1],
        "source_type": row[2],
        "source_id": row[3],
        "insight_type": row[4],
        "content": row[5],
        "suggested_query": row[6],
        "priority": row[7],
        "status": row[8],
        "execution_result": row[9],
        "created_at": row[10].isoformat().replace("+00:00", "Z") if row[10] else None,
        "updated_at": row[11].isoformat().replace("+00:00", "Z") if row[11] else None,
    }


def count_insights_by_status(pg: PGConnection, project: str) -> Dict[str, int]:
    """Cuenta insights por status."""
    ensure_insights_table(pg)
    
    sql = """
    SELECT status, COUNT(*) 
    FROM analysis_insights 
    WHERE project_id = %s 
    GROUP BY status
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project,))
        rows = cur.fetchall()
    
    counts = {"pending": 0, "executed": 0, "dismissed": 0}
    for status, count in rows:
        counts[status] = count
    return counts


def ensure_nucleus_notes_table(pg: PGConnection) -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS analisis_nucleo_notas (
        categoria TEXT,
        proyecto TEXT NOT NULL DEFAULT 'default',
        run_id TEXT,
        memo TEXT,
        llm_summary TEXT,
        payload JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    ALTER TABLE analisis_nucleo_notas ADD COLUMN IF NOT EXISTS proyecto TEXT NOT NULL DEFAULT 'default';
    CREATE UNIQUE INDEX IF NOT EXISTS ux_nucleo_proyecto_categoria ON analisis_nucleo_notas(proyecto, categoria);
    CREATE INDEX IF NOT EXISTS ix_nucleo_proyecto ON analisis_nucleo_notas(proyecto);
    """
    with pg.cursor() as cur:
        cur.execute(sql)
    pg.commit()


def upsert_nucleus_memo(
    pg: PGConnection,
    *,
    categoria: str,
    project: Optional[str],
    run_id: str,
    memo: Optional[str],
    llm_summary: Optional[str],
    payload: Dict[str, Any],
) -> None:
    ensure_nucleus_notes_table(pg)
    sql = """
    INSERT INTO analisis_nucleo_notas (
        categoria,
        proyecto,
        run_id,
        memo,
        llm_summary,
        payload,
        created_at,
        updated_at
    )
    VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
    ON CONFLICT (proyecto, categoria) DO UPDATE SET
        proyecto = EXCLUDED.proyecto,
        run_id = EXCLUDED.run_id,
        memo = EXCLUDED.memo,
        llm_summary = EXCLUDED.llm_summary,
        payload = EXCLUDED.payload,
        updated_at = NOW();
    """
    with pg.cursor() as cur:
        cur.execute(
            sql,
            (
                categoria,
                project,
                run_id,
                memo,
                llm_summary,
                Json(payload),
            ),
        )
    pg.commit()


def ensure_fragment_table(pg: PGConnection) -> None:
        global _fragment_table_ready
        if _fragment_table_ready:
                return

        with _fragment_table_lock:
                if _fragment_table_ready:
                        return

                sql = """
                CREATE TABLE IF NOT EXISTS entrevista_fragmentos (
                    project_id TEXT NOT NULL,
                    id TEXT NOT NULL,
                    archivo TEXT NOT NULL,
                    par_idx INT NOT NULL,
                    fragmento TEXT NOT NULL,
                    embedding VECTOR(1536),
                    char_len INT,
                    sha256 TEXT,
                    area_tematica TEXT,
                    actor_principal TEXT,
                    requiere_protocolo_lluvia BOOLEAN,
                    metadata JSONB,
                    speaker TEXT,
                    interviewer_tokens INT,
                    interviewee_tokens INT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (project_id, id)
                );
                ALTER TABLE entrevista_fragmentos
                                ADD COLUMN IF NOT EXISTS project_id TEXT DEFAULT 'default';
                ALTER TABLE entrevista_fragmentos
                    ADD COLUMN IF NOT EXISTS metadata JSONB;
                ALTER TABLE entrevista_fragmentos
                    ADD COLUMN IF NOT EXISTS speaker TEXT;
                ALTER TABLE entrevista_fragmentos
                    ADD COLUMN IF NOT EXISTS interviewer_tokens INT DEFAULT 0;
                ALTER TABLE entrevista_fragmentos
                    ADD COLUMN IF NOT EXISTS interviewee_tokens INT DEFAULT 0;
                CREATE UNIQUE INDEX IF NOT EXISTS ux_ef_project_fragment ON entrevista_fragmentos(project_id, id);
                CREATE INDEX IF NOT EXISTS ix_ef_project_id ON entrevista_fragmentos(project_id);
                CREATE INDEX IF NOT EXISTS ix_ef_project_archivo ON entrevista_fragmentos(project_id, archivo);
                CREATE INDEX IF NOT EXISTS ix_ef_archivo ON entrevista_fragmentos(archivo);
                CREATE INDEX IF NOT EXISTS ix_ef_charlen ON entrevista_fragmentos(char_len);
                CREATE INDEX IF NOT EXISTS ix_ef_area ON entrevista_fragmentos(area_tematica);
                CREATE INDEX IF NOT EXISTS ix_ef_actor ON entrevista_fragmentos(actor_principal);
                CREATE INDEX IF NOT EXISTS ix_ef_metadata_genero ON entrevista_fragmentos((metadata->>'genero'));
                CREATE INDEX IF NOT EXISTS ix_ef_metadata_periodo ON entrevista_fragmentos((metadata->>'periodo'));
                CREATE INDEX IF NOT EXISTS ix_ef_created_at ON entrevista_fragmentos(created_at);
                CREATE INDEX IF NOT EXISTS ix_ef_speaker ON entrevista_fragmentos(speaker);
                CREATE INDEX IF NOT EXISTS ix_ef_interview_tokens ON entrevista_fragmentos(interviewee_tokens);
                CREATE INDEX IF NOT EXISTS ix_ef_fragment_tsv ON entrevista_fragmentos USING GIN (to_tsvector('spanish', fragmento));
                """
                with pg.cursor() as cur:
                        cur.execute(sql)
                pg.commit()
                _fragment_table_ready = True


def insert_fragments(pg: PGConnection, rows: Iterable[Row]) -> None:
    data = list(rows)
    if not data:
        return

    normalized: List[Tuple] = []
    for row in data:
        (
            project_id,
            fragment_id,
            archivo,
            par_idx,
            fragmento,
            embedding,
            char_len,
            sha256,
            area_tematica,
            actor_principal,
            requiere_protocolo_lluvia,
            metadata,
            speaker,
            interviewer_tokens,
            interviewee_tokens,
        ) = row
        normalized.append(
            (
                project_id,
                fragment_id,
                archivo,
                par_idx,
                fragmento,
                embedding,
                char_len,
                sha256,
                area_tematica,
                actor_principal,
                requiere_protocolo_lluvia,
                Json(metadata) if metadata is not None else None,
                speaker,
                interviewer_tokens,
                interviewee_tokens,
            )
        )

    sql = """
    INSERT INTO entrevista_fragmentos (
        project_id,
        id,
        archivo,
        par_idx,
        fragmento,
        embedding,
        char_len,
        sha256,
        area_tematica,
        actor_principal,
        requiere_protocolo_lluvia,
        metadata,
        speaker,
        interviewer_tokens,
        interviewee_tokens
    )
    VALUES %s
    ON CONFLICT (project_id, id) DO UPDATE SET
      fragmento = EXCLUDED.fragmento,
      embedding = EXCLUDED.embedding,
      char_len  = EXCLUDED.char_len,
      sha256    = EXCLUDED.sha256,
      area_tematica = EXCLUDED.area_tematica,
      actor_principal = EXCLUDED.actor_principal,
      requiere_protocolo_lluvia = EXCLUDED.requiere_protocolo_lluvia,
      metadata = COALESCE(EXCLUDED.metadata, entrevista_fragmentos.metadata),
      speaker = COALESCE(EXCLUDED.speaker, entrevista_fragmentos.speaker),
      interviewer_tokens = COALESCE(EXCLUDED.interviewer_tokens, entrevista_fragmentos.interviewer_tokens),
      interviewee_tokens = COALESCE(EXCLUDED.interviewee_tokens, entrevista_fragmentos.interviewee_tokens),
      updated_at = NOW();
    """
    try:
        with pg.cursor() as cur:
            execute_values(cur, sql, normalized, page_size=200)
        pg.commit()
    except Exception as exc:
        try:
            pg.rollback()
        except Exception:
            pass
        raise


def ensure_open_coding_table(pg: PGConnection) -> None:
    global _open_coding_table_ready
    if _open_coding_table_ready:
        return

    with _open_coding_table_lock:
        if _open_coding_table_ready:
            return

        sql = """
        CREATE TABLE IF NOT EXISTS analisis_codigos_abiertos (
          project_id TEXT NOT NULL,
          fragmento_id TEXT NOT NULL,
          codigo TEXT NOT NULL,
          archivo TEXT NOT NULL,
          cita TEXT NOT NULL,
          fuente TEXT,
                memo TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (project_id, fragmento_id, codigo)
        );
            ALTER TABLE analisis_codigos_abiertos ADD COLUMN IF NOT EXISTS project_id TEXT DEFAULT 'default';
        CREATE UNIQUE INDEX IF NOT EXISTS ux_aca_project_fragment_codigo ON analisis_codigos_abiertos(project_id, fragmento_id, codigo);
        CREATE INDEX IF NOT EXISTS ix_aca_codigo ON analisis_codigos_abiertos(codigo);
        CREATE INDEX IF NOT EXISTS ix_aca_archivo ON analisis_codigos_abiertos(archivo);
        CREATE INDEX IF NOT EXISTS ix_aca_project_codigo ON analisis_codigos_abiertos(project_id, codigo);
        CREATE INDEX IF NOT EXISTS ix_aca_project_archivo ON analisis_codigos_abiertos(project_id, archivo);
        CREATE INDEX IF NOT EXISTS ix_aca_created_at ON analisis_codigos_abiertos(created_at);
            ALTER TABLE analisis_codigos_abiertos ADD COLUMN IF NOT EXISTS memo TEXT;
            ALTER TABLE analisis_codigos_abiertos ADD COLUMN IF NOT EXISTS code_id BIGINT;
        CREATE INDEX IF NOT EXISTS ix_aca_project_code_id ON analisis_codigos_abiertos(project_id, code_id) WHERE code_id IS NOT NULL;
        """
        with pg.cursor() as cur:
            cur.execute(sql)
        pg.commit()

        _open_coding_table_ready = True


def ensure_codes_catalog_table(pg: PGConnection) -> None:
    """Catálogo ontológico de códigos (definitivos).

    Mantiene estado post-fusión (active/merged/deprecated) y un puntero canónico.
    Diseñado para coexistir con `analisis_codigos_abiertos` sin romper compatibilidad.
    """

    global _codes_catalog_table_ready
    if _codes_catalog_table_ready:
        return

    with _codes_catalog_table_lock:
        if _codes_catalog_table_ready:
            return

        sql = """
        CREATE TABLE IF NOT EXISTS catalogo_codigos (
          project_id TEXT NOT NULL,
          codigo TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active',
          canonical_codigo TEXT,
          merged_at TIMESTAMPTZ,
          merged_by TEXT,
          memo TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (project_id, codigo)
        );

                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'ck_catalogo_codigos_status'
                    ) THEN
                        ALTER TABLE catalogo_codigos
                            ADD CONSTRAINT ck_catalogo_codigos_status
                            CHECK (status IN ('active','merged','deprecated'));
                    END IF;
                END $$;

        CREATE INDEX IF NOT EXISTS ix_catalogo_project_status ON catalogo_codigos(project_id, status);
        CREATE INDEX IF NOT EXISTS ix_catalogo_project_canonical ON catalogo_codigos(project_id, canonical_codigo);

        CREATE OR REPLACE FUNCTION update_catalogo_codigos_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_catalogo_codigos_updated_at ON catalogo_codigos;
        CREATE TRIGGER trg_catalogo_codigos_updated_at
            BEFORE UPDATE ON catalogo_codigos
            FOR EACH ROW
            EXECUTE FUNCTION update_catalogo_codigos_updated_at();

        -- Backfill best-effort: asegurar entradas para códigos ya existentes (definitivos).
        INSERT INTO catalogo_codigos (project_id, codigo, status)
        SELECT DISTINCT project_id, codigo, 'active'
          FROM analisis_codigos_abiertos
         WHERE project_id IS NOT NULL AND codigo IS NOT NULL
        ON CONFLICT (project_id, codigo) DO NOTHING;
        """

        with pg.cursor() as cur:
            cur.execute(sql)
        pg.commit()

        _codes_catalog_table_ready = True


def ensure_code_catalog_entry(
    pg: PGConnection,
    project_id: str,
    codigo: str,
    *,
    status: str = "active",
) -> Optional[int]:
    """Crea (si falta) una fila en `catalogo_codigos` para un código.
    
    Returns:
        El code_id del registro (existente o creado), o None si codigo es vacío.
    """
    if not codigo or not str(codigo).strip():
        return None

    ensure_codes_catalog_table(pg)
    codigo_clean = str(codigo).strip()
    
    with pg.cursor() as cur:
        # INSERT con RETURNING para obtener code_id
        cur.execute(
            """
            INSERT INTO catalogo_codigos (project_id, codigo, status)
            VALUES (%s, %s, %s)
            ON CONFLICT (project_id, codigo) DO UPDATE SET updated_at = NOW()
            RETURNING code_id
            """,
            (project_id, codigo_clean, status),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            return int(row[0])
    
    # Fallback: consultar el code_id existente
    return get_code_id_for_codigo(pg, project_id, codigo_clean)


def resolve_canonical_codigo(
    pg: PGConnection,
    project_id: str,
    codigo: str,
    *,
    max_hops: int = 10,
) -> str:
    """Resuelve un código hacia su canónico siguiendo `catalogo_codigos`.

    Si no existe entrada, retorna el mismo código.
    """
    if not codigo or not str(codigo).strip():
        return str(codigo)

    ensure_codes_catalog_table(pg)

    current = str(codigo).strip()
    seen: set[str] = set()
    for _ in range(max_hops):
        if current in seen:
            break
        seen.add(current)

        with pg.cursor() as cur:
            cur.execute(
                """
                SELECT status, canonical_codigo
                  FROM catalogo_codigos
                 WHERE project_id = %s AND codigo = %s
                """,
                (project_id, current),
            )
            row = cur.fetchone()

        if not row:
            return current

        status, canonical_codigo = row[0], row[1]
        if status == "merged" and canonical_codigo and str(canonical_codigo).strip():
            nxt = str(canonical_codigo).strip()
            if nxt.lower() == current.lower():
                return current
            current = nxt
            continue
        return current

    return current


def resolve_canonical_codigos_bulk(
    pg: PGConnection,
    project_id: str,
    codigos: Iterable[str],
    *,
    max_hops: int = 10,
) -> Dict[str, str]:
    """Resuelve múltiples códigos a su canónico (mejor performance que per-row)."""
    ensure_codes_catalog_table(pg)

    origins: List[str] = []
    for c in codigos:
        if c is None:
            continue
        s = str(c).strip()
        if not s:
            continue
        origins.append(s)
    if not origins:
        return {}

    # Track current canonical candidate per origin.
    current: Dict[str, str] = {o: o for o in origins}

    for _ in range(int(max_hops) if max_hops and max_hops > 0 else 1):
        uniques = sorted(set(current.values()))
        if not uniques:
            break

        with pg.cursor() as cur:
            cur.execute(
                """
                SELECT codigo, status, canonical_codigo
                  FROM catalogo_codigos
                 WHERE project_id = %s
                   AND codigo = ANY(%s)
                """,
                (project_id, uniques),
            )
            rows = cur.fetchall() or []

        info: Dict[str, Tuple[Optional[str], Optional[str]]] = {
            str(r[0]): (r[1], r[2]) for r in rows if r and r[0] is not None
        }

        changed = False
        for origin, cur_code in list(current.items()):
            status, canonical = info.get(cur_code, (None, None))
            if status == "merged" and canonical and str(canonical).strip():
                nxt = str(canonical).strip()
            else:
                nxt = cur_code
            if nxt != cur_code:
                current[origin] = nxt
                changed = True

        if not changed:
            break

    return current


def resolve_canonical_code_id(
    pg: PGConnection,
    project_id: str,
    code_id: int,
    *,
    max_hops: int = 10,
) -> Optional[int]:
    """Resuelve un code_id hacia su canónico siguiendo `canonical_code_id`.

    A diferencia de resolve_canonical_codigo (que opera por texto), esta función
    usa la identidad estable por ID, que es el camino preferido para Fase 1.5+.

    Args:
        pg: Conexión PostgreSQL.
        project_id: ID del proyecto.
        code_id: ID del código a resolver.
        max_hops: Máximo de saltos para evitar loops infinitos.

    Returns:
        El code_id canónico final, o None si:
        - El code_id no existe en el catálogo.
        - Se detecta un ciclo.

    Example:
        >>> # Código canónico (sin puntero) → retorna sí mismo
        >>> resolve_canonical_code_id(pg, "jd-007", 42)
        42

        >>> # Código merged (42 → 100) → retorna canónico
        >>> resolve_canonical_code_id(pg, "jd-007", 42)
        100

        >>> # Código inexistente → None
        >>> resolve_canonical_code_id(pg, "jd-007", 99999)
        None
    """
    if code_id is None:
        return None

    ensure_codes_catalog_table(pg)

    current = int(code_id)
    seen: set[int] = set()

    for _ in range(max_hops):
        if current in seen:
            # Ciclo detectado
            _logger.warning(
                "resolve_canonical_code_id.cycle_detected project=%s code_id=%s cycle_at=%s path=%s",
                project_id, code_id, current, list(seen),
            )
            return None
        seen.add(current)

        with pg.cursor() as cur:
            cur.execute(
                """
                SELECT code_id, canonical_code_id, status
                  FROM catalogo_codigos
                 WHERE project_id = %s AND code_id = %s
                """,
                (project_id, current),
            )
            row = cur.fetchone()

        if not row:
            # code_id no existe
            if current == code_id:
                # El ID original no existe
                return None
            # Llegamos a un puntero que no existe (inconsistencia)
            _logger.warning(
                "resolve_canonical_code_id.dangling_pointer project=%s original_code_id=%s dangling_id=%s",
                project_id, code_id, current,
            )
            return None

        db_code_id, canonical_code_id, status = row[0], row[1], row[2]

        # Caso 1: Es canónico (canonical_code_id es NULL)
        if canonical_code_id is None:
            return int(db_code_id)

        # Caso 2: Self-canonical (canonical_code_id = code_id) — estado esperado
        if int(canonical_code_id) == int(db_code_id):
            return int(db_code_id)

        # Caso 3: Merged/superseded — seguir la cadena
        if status in ("merged", "superseded"):
            current = int(canonical_code_id)
            continue

        # Caso 4: Activo con canonical_code_id (inusual pero válido)
        # Podría ser un alias temporal; retornamos el target
        return int(canonical_code_id)

    # Se excedió max_hops — posible ciclo largo o cadena muy profunda
    _logger.warning(
        "resolve_canonical_code_id.max_hops_exceeded project=%s code_id=%s max_hops=%s",
        project_id, code_id, max_hops,
    )
    return None


def get_code_id_for_codigo(
    pg: PGConnection,
    project_id: str,
    codigo: str,
) -> Optional[int]:
    """Obtiene el code_id para un código por su label (texto).

    Útil para transición: cuando se recibe texto y se necesita operar por ID.

    Args:
        pg: Conexión PostgreSQL.
        project_id: ID del proyecto.
        codigo: Label del código (texto).

    Returns:
        El code_id si existe, None si no.
    """
    if not codigo or not str(codigo).strip():
        return None

    ensure_codes_catalog_table(pg)

    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT code_id
              FROM catalogo_codigos
             WHERE project_id = %s AND lower(codigo) = lower(%s)
            """,
            (project_id, str(codigo).strip()),
        )
        row = cur.fetchone()

    if row and row[0] is not None:
        return int(row[0])
    return None


def upsert_open_codes(pg: PGConnection, rows: Iterable[OpenCodeRow]) -> None:
    """
    Inserta o actualiza códigos abiertos.
    
    IMPORTANTE: Filtra automáticamente registros con fragmento_id vacío o None
    para mantener la coherencia de datos.
    
    OpenCodeRow: (project_id, fragmento_id, codigo, archivo, cita, fuente, memo, code_id)
    """
    # Filtrar registros con fragmento_id inválido
    valid_data = [
        row for row in rows 
        if row[1] is not None and row[1] != '' and len(str(row[1])) > 10
    ]
    
    if not valid_data:
        return
    
    # Si code_id no está en la tupla (compatibilidad), agregar None
    normalized = []
    for row in valid_data:
        if len(row) == 7:
            # Legacy: agregar code_id=None
            normalized.append((*row, None))
        else:
            normalized.append(row)
        
    sql = """
    INSERT INTO analisis_codigos_abiertos (
        project_id,
        fragmento_id,
        codigo,
        archivo,
        cita,
        fuente,
        memo,
        code_id
    )
    VALUES %s
    ON CONFLICT (project_id, fragmento_id, codigo) DO UPDATE SET
        cita = EXCLUDED.cita,
        fuente = EXCLUDED.fuente,
        memo = EXCLUDED.memo,
        code_id = COALESCE(EXCLUDED.code_id, analisis_codigos_abiertos.code_id),
        created_at = analisis_codigos_abiertos.created_at;
    """
    with pg.cursor() as cur:
        execute_values(cur, sql, normalized, page_size=200)


def merge_definitive_codes_by_code(
    pg: PGConnection,
    project_id: str,
    source_codigo: str,
    target_codigo: str,
    merged_by: Optional[str] = None,
    memo: Optional[str] = None,
) -> Dict[str, Any]:
    """Fusiona códigos definitivos (evidencia) y actualiza ontología en `catalogo_codigos`.

    - Mueve filas de `analisis_codigos_abiertos` desde `source_codigo` hacia `target_codigo`
      cuando no hay conflicto por (project_id, fragmento_id, codigo).
    - Elimina duplicados restantes (cuando el target ya tiene la misma evidencia).
    - Marca el source como `merged` apuntando al target canónico.
    """
    ensure_open_coding_table(pg)
    ensure_codes_catalog_table(pg)

    if not source_codigo or not target_codigo:
        raise ValueError("Se requieren source_codigo y target_codigo")

    src = str(source_codigo).strip()
    tgt_input = str(target_codigo).strip()
    if not src or not tgt_input:
        raise ValueError("Se requieren source_codigo y target_codigo")

    if src.lower() == tgt_input.lower():
        return {
            "project": project_id,
            "source": src,
            "target": tgt_input,
            "skipped": "self",
            "moved_rows": 0,
            "dedup_deleted": 0,
        }

    # Si el target ya está fusionado, apuntar al canónico final.
    tgt = resolve_canonical_codigo(pg, project_id, tgt_input)

    ensure_code_catalog_entry(pg, project_id, src)
    ensure_code_catalog_entry(pg, project_id, tgt)

    moved_rows = 0
    dedup_deleted = 0

    with pg.cursor() as cur:
        cur.execute(
            """
            WITH updated AS (
                UPDATE analisis_codigos_abiertos src
                   SET codigo = %s
                 WHERE src.project_id = %s
                   AND src.codigo = %s
                   AND NOT EXISTS (
                       SELECT 1
                         FROM analisis_codigos_abiertos tgt
                        WHERE tgt.project_id = src.project_id
                          AND tgt.fragmento_id = src.fragmento_id
                          AND tgt.codigo = %s
                   )
                 RETURNING 1
            )
            SELECT COUNT(*)::INT FROM updated
            """,
            (tgt, project_id, src, tgt),
        )
        moved_rows = int((cur.fetchone() or [0])[0] or 0)

        cur.execute(
            """
            WITH deleted AS (
                DELETE FROM analisis_codigos_abiertos src
                 WHERE src.project_id = %s
                   AND src.codigo = %s
                   AND EXISTS (
                       SELECT 1
                         FROM analisis_codigos_abiertos tgt
                        WHERE tgt.project_id = src.project_id
                          AND tgt.fragmento_id = src.fragmento_id
                          AND tgt.codigo = %s
                   )
                 RETURNING 1
            )
            SELECT COUNT(*)::INT FROM deleted
            """,
            (project_id, src, tgt),
        )
        dedup_deleted = int((cur.fetchone() or [0])[0] or 0)

        cur.execute(
            """
            UPDATE catalogo_codigos
               SET status = 'merged',
                   canonical_codigo = %s,
                   merged_at = NOW(),
                   merged_by = %s,
                   memo = COALESCE(%s, memo)
             WHERE project_id = %s AND codigo = %s
            """,
            (tgt, merged_by, memo, project_id, src),
        )

        # Asegurar que el target quede activo.
        cur.execute(
            """
            UPDATE catalogo_codigos
               SET status = 'active',
                   canonical_codigo = NULL
             WHERE project_id = %s AND codigo = %s
            """,
            (project_id, tgt),
        )

    pg.commit()

    # Best-effort audit trail
    try:
        previous_src = _get_latest_code_memo(pg, project_id, src)
        log_code_version(
            pg,
            project=project_id,
            codigo=src,
            accion="definitive_merge",
            memo_anterior=previous_src,
            memo_nuevo=(
                f"merged_into:{tgt}; moved_rows:{moved_rows}; dedup_deleted:{dedup_deleted}"
                + (f"\n{str(memo).strip()}" if memo and str(memo).strip() else "")
            ),
            changed_by=merged_by,
        )
    except Exception:
        pass

    return {
        "project": project_id,
        "source": src,
        "target": tgt,
        "moved_rows": int(moved_rows or 0),
        "dedup_deleted": int(dedup_deleted or 0),
    }
    pg.commit()


def delete_open_code(pg: PGConnection, project_id: str, fragment_id: str, codigo: str) -> int:
    """
    Elimina la asignación de un código a un fragmento.
    
    Solo elimina el registro en analisis_codigos_abiertos.
    El fragmento y la cita permanecen si están asociados a otros códigos.
    
    Args:
        pg: Conexión a PostgreSQL
        project_id: ID del proyecto
        fragment_id: ID del fragmento
        codigo: Nombre del código a desvincular
        
    Returns:
        Número de filas eliminadas (0 o 1)
    """
    sql = """
    DELETE FROM analisis_codigos_abiertos
     WHERE project_id = %s
       AND fragmento_id = %s
       AND codigo = %s
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project_id, fragment_id, codigo))
        deleted = cur.rowcount
    pg.commit()
    return deleted


def ensure_code_versions_table(pg: PGConnection) -> None:
    """Crea tabla para historial de versiones de códigos."""
    sql = """
    CREATE TABLE IF NOT EXISTS codigo_versiones (
      id SERIAL PRIMARY KEY,
      project_id TEXT NOT NULL,
      codigo TEXT NOT NULL,
      version INT NOT NULL DEFAULT 1,
      memo_anterior TEXT,
      memo_nuevo TEXT,
      accion TEXT NOT NULL DEFAULT 'create',  -- create, update, delete, merge
      changed_by TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """

    with pg.cursor() as cur:
        # Create base table (new schema) if missing
        cur.execute(sql)

        # --- Compatibilidad con esquemas legacy (p.ej. scripts/init_schema.sql) ---
        # Si la tabla ya existe con columnas distintas, CREATE TABLE IF NOT EXISTS
        # no aplica cambios. Por eso añadimos columnas nuevas y hacemos backfill.
        cur.execute(
            """
            ALTER TABLE codigo_versiones ADD COLUMN IF NOT EXISTS project_id TEXT;
            ALTER TABLE codigo_versiones ADD COLUMN IF NOT EXISTS codigo TEXT;
            ALTER TABLE codigo_versiones ADD COLUMN IF NOT EXISTS version INT;
            ALTER TABLE codigo_versiones ADD COLUMN IF NOT EXISTS memo_anterior TEXT;
            ALTER TABLE codigo_versiones ADD COLUMN IF NOT EXISTS memo_nuevo TEXT;
            ALTER TABLE codigo_versiones ADD COLUMN IF NOT EXISTS accion TEXT;
            ALTER TABLE codigo_versiones ADD COLUMN IF NOT EXISTS changed_by TEXT;
            ALTER TABLE codigo_versiones ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;
            """
        )

        # Convertir changed_by a TEXT si venía como UUID u otro tipo (best-effort)
        try:
            cur.execute(
                "ALTER TABLE codigo_versiones ALTER COLUMN changed_by TYPE TEXT USING changed_by::text"
            )
        except Exception:
            pass

        # Conocer columnas existentes para backfill seguro.
        cur.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = 'codigo_versiones'
            """
        )
        cols = {str(r[0]) for r in (cur.fetchall() or [])}

        # Backfill project_id desde columnas legacy (proyecto)
        if "proyecto" in cols:
            cur.execute(
                """
                UPDATE codigo_versiones
                   SET project_id = COALESCE(project_id, proyecto)
                 WHERE project_id IS NULL AND proyecto IS NOT NULL
                """
            )
        # Backfill created_at desde changed_at
        if "changed_at" in cols:
            cur.execute(
                """
                UPDATE codigo_versiones
                   SET created_at = COALESCE(created_at, changed_at)
                 WHERE created_at IS NULL AND changed_at IS NOT NULL
                """
            )
        # Backfill memos desde legacy definiciones/reason
        if "definicion_anterior" in cols:
            cur.execute(
                """
                UPDATE codigo_versiones
                   SET memo_anterior = COALESCE(memo_anterior, definicion_anterior)
                 WHERE memo_anterior IS NULL AND definicion_anterior IS NOT NULL
                """
            )
        if "definicion_nueva" in cols:
            cur.execute(
                """
                UPDATE codigo_versiones
                   SET memo_nuevo = COALESCE(memo_nuevo, definicion_nueva)
                 WHERE memo_nuevo IS NULL AND definicion_nueva IS NOT NULL
                """
            )
        if "reason" in cols:
            cur.execute(
                """
                UPDATE codigo_versiones
                   SET memo_nuevo = COALESCE(memo_nuevo, reason)
                 WHERE memo_nuevo IS NULL AND reason IS NOT NULL
                """
            )

        # Backfill accion si está vacío
        cur.execute(
            """
            UPDATE codigo_versiones
               SET accion = COALESCE(NULLIF(accion, ''), 'legacy')
             WHERE accion IS NULL OR accion = ''
            """
        )

        # Backfill version si falta
        cur.execute(
            """
            WITH ranked AS (
              SELECT
                id,
                ROW_NUMBER() OVER (
                  PARTITION BY COALESCE(project_id, 'default'), codigo
                  ORDER BY COALESCE(created_at, NOW()), id
                ) AS rn
              FROM codigo_versiones
              WHERE codigo IS NOT NULL AND codigo <> ''
            )
            UPDATE codigo_versiones cv
               SET version = ranked.rn
              FROM ranked
             WHERE cv.id = ranked.id
               AND (cv.version IS NULL OR cv.version <= 0)
            """
        )

        # Índices (idempotentes)
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_cv_project_codigo ON codigo_versiones(project_id, codigo);
            CREATE INDEX IF NOT EXISTS ix_cv_created_at ON codigo_versiones(created_at);
            """
        )

    pg.commit()


def log_code_version(
    pg: PGConnection,
    project: str,
    codigo: str,
    accion: str,
    memo_anterior: Optional[str] = None,
    memo_nuevo: Optional[str] = None,
    changed_by: Optional[str] = None,
) -> None:
    """Registra un cambio en el historial de versiones de un código."""
    ensure_code_versions_table(pg)
    
    # Obtener última versión
    with pg.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(MAX(version), 0) FROM codigo_versiones WHERE project_id = %s AND codigo = %s",
            (project, codigo)
        )
        row = cur.fetchone()

    last_version = row[0] if row and row[0] is not None else 0
    new_version = last_version + 1
    
    sql = """
    INSERT INTO codigo_versiones (project_id, codigo, version, memo_anterior, memo_nuevo, accion, changed_by)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project, codigo, new_version, memo_anterior, memo_nuevo, accion, changed_by))
    pg.commit()


def _get_latest_code_memo(pg: PGConnection, project: str, codigo: str) -> Optional[str]:
    """Best-effort helper to fetch the latest memo_nuevo for a code."""
    ensure_code_versions_table(pg)
    sql = """
    SELECT memo_nuevo
      FROM codigo_versiones
     WHERE project_id = %s AND codigo = %s
     ORDER BY version DESC
     LIMIT 1
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project, codigo))
        row = cur.fetchone()
    return row[0] if row else None


def get_code_history(pg: PGConnection, project: str, codigo: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Obtiene el historial de versiones de un código."""
    ensure_code_versions_table(pg)
    
    sql = """
    SELECT id, version, memo_anterior, memo_nuevo, accion, changed_by, created_at
      FROM codigo_versiones
     WHERE project_id = %s AND codigo = %s
     ORDER BY version DESC
     LIMIT %s
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project, codigo, limit))
        rows = cur.fetchall()
    
    return [
        {
            "id": r[0],
            "version": r[1],
            "memo_anterior": r[2],
            "memo_nuevo": r[3],
            "accion": r[4],
            "changed_by": r[5],
            "created_at": r[6].isoformat().replace("+00:00", "Z") if r[6] else None,
        }
        for r in rows
    ]


def ensure_analysis_memos_table(pg: PGConnection) -> None:
    """Persiste memos epistemológicos (memo_statements) por entrevista.

    Nota: esto es complementario a otras fuentes de memos (Discovery, candidatos, notes/*).
    """
    sql = """
    CREATE TABLE IF NOT EXISTS analysis_memos (
        id BIGSERIAL PRIMARY KEY,
        project_id TEXT NOT NULL,
        archivo TEXT NOT NULL,
        memo_text TEXT,
        memo_statements JSONB,
        structured BOOLEAN NOT NULL DEFAULT FALSE,
        schema_version INT NOT NULL DEFAULT 1,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- Cognitive/version metadata (added later; keep compatible with existing DBs)
    ALTER TABLE analysis_memos ADD COLUMN IF NOT EXISTS run_id TEXT;
    ALTER TABLE analysis_memos ADD COLUMN IF NOT EXISTS request_id TEXT;
    ALTER TABLE analysis_memos ADD COLUMN IF NOT EXISTS cognitive_metadata JSONB;

    CREATE INDEX IF NOT EXISTS ix_analysis_memos_project_file_created
        ON analysis_memos(project_id, archivo, created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_analysis_memos_created_at
        ON analysis_memos(created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_analysis_memos_run_id
        ON analysis_memos(run_id);
    CREATE INDEX IF NOT EXISTS ix_analysis_memos_request_id
        ON analysis_memos(request_id);
    """
    with pg.cursor() as cur:
        cur.execute(sql)
    pg.commit()


def insert_analysis_memo(
    pg: PGConnection,
    *,
    project_id: str,
    archivo: str,
    memo_text: Optional[str],
    memo_statements: Any,
    structured: bool,
    run_id: Optional[str] = None,
    request_id: Optional[str] = None,
    cognitive_metadata: Optional[Dict[str, Any]] = None,
    schema_version: int = 1,
) -> None:
    """Inserta una instantánea de memo epistemológico para una entrevista."""
    ensure_analysis_memos_table(pg)

    sql = """
    INSERT INTO analysis_memos (
        project_id,
        archivo,
        memo_text,
        memo_statements,
        structured,
        run_id,
        request_id,
        cognitive_metadata,
        schema_version
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    with pg.cursor() as cur:
        cur.execute(
            sql,
            (
                project_id,
                archivo,
                memo_text,
                Json(memo_statements) if memo_statements is not None else None,
                bool(structured),
                run_id,
                request_id,
                Json(cognitive_metadata) if cognitive_metadata is not None else None,
                int(schema_version),
            ),
        )
    pg.commit()


def ensure_axial_table(pg: PGConnection) -> None:
    # NOTE: There are multiple historical schemas for `analisis_axial` in the wild.
    # The preferred (newer) schema includes `archivo`, `memo` and `evidencia` as TEXT[].
    # Some existing deployments have a legacy table without those columns.
    # This function must be safe to call on every request (e.g., dashboards) without
    # hard-failing due to schema drift or duplicate legacy rows.

    create_sql = """
    CREATE TABLE IF NOT EXISTS analisis_axial (
        project_id TEXT NOT NULL,
        categoria TEXT NOT NULL,
        codigo TEXT NOT NULL,
        code_id BIGINT,
        relacion TEXT NOT NULL,
        archivo TEXT NOT NULL,
        memo TEXT,
        evidencia TEXT[] NOT NULL,
        estado TEXT NOT NULL DEFAULT 'validado',
        validado_por TEXT,
        validado_en TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (project_id, categoria, codigo, relacion)
    );
    """
    with pg.cursor() as cur:
        cur.execute(create_sql)
        # Ensure `project_id` exists even on legacy schemas.
        cur.execute("ALTER TABLE analisis_axial ADD COLUMN IF NOT EXISTS project_id TEXT DEFAULT 'default';")
        cur.execute("ALTER TABLE analisis_axial ADD COLUMN IF NOT EXISTS code_id BIGINT;")
        cur.execute("ALTER TABLE analisis_axial ADD COLUMN IF NOT EXISTS estado TEXT DEFAULT 'validado';")
        cur.execute("ALTER TABLE analisis_axial ADD COLUMN IF NOT EXISTS validado_por TEXT;")
        cur.execute("ALTER TABLE analisis_axial ADD COLUMN IF NOT EXISTS validado_en TIMESTAMPTZ;")
        cur.execute("ALTER TABLE analisis_axial ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();")
    pg.commit()

    # Best-effort: enforce allowed states (ledger). Do NOT fail the API if a legacy DB contains
    # invalid values; migrations are the authoritative way to clean those up.
    try:
        with pg.cursor() as cur:
            cur.execute(
                """
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'ck_analisis_axial_estado'
                  ) THEN
                    ALTER TABLE analisis_axial
                      ADD CONSTRAINT ck_analisis_axial_estado
                      CHECK (estado IN ('pendiente','validado','rechazado'));
                  END IF;
                END $$;
                """
            )
        pg.commit()
    except Exception:
        pg.rollback()

    index_statements = [
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_axial_project_cat_cod_rel ON analisis_axial(project_id, categoria, codigo, relacion);",
        "CREATE INDEX IF NOT EXISTS ix_axial_codigo ON analisis_axial(codigo);",
        "CREATE INDEX IF NOT EXISTS ix_axial_categoria ON analisis_axial(categoria);",
        "CREATE INDEX IF NOT EXISTS ix_axial_project_categoria ON analisis_axial(project_id, categoria);",
        "CREATE INDEX IF NOT EXISTS ix_axial_project_codigo ON analisis_axial(project_id, codigo);",
        "CREATE INDEX IF NOT EXISTS ix_axial_project_estado ON analisis_axial(project_id, estado);",
        "CREATE INDEX IF NOT EXISTS ix_axial_project_code_id ON analisis_axial(project_id, code_id) WHERE code_id IS NOT NULL;",
        "CREATE INDEX IF NOT EXISTS ix_axial_project_updated_at ON analisis_axial(project_id, updated_at);",
    ]

    for stmt in index_statements:
        try:
            with pg.cursor() as cur:
                cur.execute(stmt)
            pg.commit()
        except Exception as e:
            # If legacy rows contain duplicates, the UNIQUE index can fail.
            # We should not take the whole API down; log and continue.
            pg.rollback()
            statement_name = stmt.split("(")[0].strip()
            _logger.warning(
                "postgres.ensure_axial_table.index_failed statement=%s error=%s",
                statement_name,
                str(e)[:200],
            )


def _pg_get_table_columns(pg: PGConnection, table_name: str, schema: str = "public") -> set:
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = %s
               AND table_name = %s
            """,
            (schema, table_name),
        )
        return {r[0] for r in cur.fetchall()}


def upsert_axial_relationships(pg: PGConnection, rows: Iterable[AxialRow]) -> None:
    data = list(rows)
    if not data:
        return

    # Canonicalize codes to avoid contaminating axial/GDS with merged aliases.
    # Note: `relacion` is a relation type (not a code) in current model.
    ensure_codes_catalog_table(pg)
    by_project_codes: Dict[str, set] = {}
    for project_id, _cat, code, _rel, _archivo, _memo, _evidencia in data:
        pid = str(project_id or "default")
        if code is None:
            continue
        by_project_codes.setdefault(pid, set()).add(str(code).strip())

    by_project_map: Dict[str, Dict[str, str]] = {}
    for pid, codes in by_project_codes.items():
        by_project_map[pid] = resolve_canonical_codigos_bulk(pg, pid, codes)

    canonicalized: List[AxialRow] = []
    for project_id, cat, code, relacion, archivo, memo, evidencia in data:
        pid = str(project_id or "default")
        code_str = str(code).strip() if code is not None else ""
        canon = by_project_map.get(pid, {}).get(code_str, code_str)
        if canon:
            try:
                ensure_code_catalog_entry(pg, pid, canon)
            except Exception:
                # best-effort
                pass
        canonicalized.append((pid, cat, canon or code_str, relacion, archivo, memo, evidencia))

    data = canonicalized
    cols = _pg_get_table_columns(pg, "analisis_axial")

    # Preferred/new schema path.
    if {"archivo", "memo", "evidencia"}.issubset(cols):
        insert_cols = [
            "project_id",
            "categoria",
            "codigo",
            "relacion",
            "archivo",
            "memo",
            "evidencia",
        ]
        has_code_id = "code_id" in cols
        has_estado = "estado" in cols
        has_updated_at = "updated_at" in cols

        if has_code_id:
            # Keep stable ID for code identity (optional).
            insert_cols.insert(3, "code_id")
        if has_estado:
            insert_cols.append("estado")

        sql = f"""
        INSERT INTO analisis_axial ({', '.join(insert_cols)})
        VALUES %s
        ON CONFLICT (project_id, categoria, codigo, relacion) DO UPDATE SET
            archivo = EXCLUDED.archivo,
            memo = EXCLUDED.memo,
            evidencia = EXCLUDED.evidencia
            {', code_id = COALESCE(analisis_axial.code_id, EXCLUDED.code_id)' if has_code_id else ''}
            {', estado = COALESCE(analisis_axial.estado, EXCLUDED.estado)' if has_estado else ''}
            {', updated_at = NOW()' if has_updated_at else ''}
            , created_at = analisis_axial.created_at;
        """

        formatted = []
        for project_id, cat, code, relacion, archivo, memo, evidencia in data:
            row_values: List[Any] = [
                project_id,
                cat,
                code,
            ]
            if has_code_id:
                code_id = get_code_id_for_codigo(pg, project_id, str(code))
                row_values.append(code_id)
            row_values.extend([relacion, archivo, memo, list(evidencia)])
            if has_estado:
                row_values.append("validado")
            formatted.append(tuple(row_values))
        with pg.cursor() as cur:
            execute_values(cur, sql, formatted, page_size=100)
        pg.commit()
        return

    # Legacy schema fallback: store minimal fields needed by analytics.
    # Keep it idempotent by inserting only if an equivalent row doesn't exist.
    import json

    insert_cols = ["project_id", "categoria", "codigo", "relacion"]
    value_builders = {
        "project_id": lambda r: r[0],
        "categoria": lambda r: r[1],
        "codigo": lambda r: r[2],
        "relacion": lambda r: r[3],
        "evidencia": lambda r: json.dumps(list(r[6]) if r[6] is not None else []),
        "fragmento_id": lambda r: (list(r[6])[0] if r[6] else None),
        "tipo_relacion": lambda r: "categoria_codigo",
        "confidence": lambda r: 1.0,
        "estado": lambda r: "validado",
        "code_id": lambda r: get_code_id_for_codigo(pg, r[0], str(r[2])),
    }

    for optional in ["evidencia", "fragmento_id", "tipo_relacion", "confidence", "estado", "code_id"]:
        if optional in cols:
            insert_cols.append(optional)

    formatted = [
        tuple(value_builders[c](row) for c in insert_cols)
        for row in data
    ]

    cte_cols = ", ".join(insert_cols)
    target_cols = ", ".join(insert_cols)
    select_cols = ", ".join(f"i.{c}" for c in insert_cols)

    sql = f"""
    WITH incoming({cte_cols}) AS (VALUES %s)
    INSERT INTO analisis_axial ({target_cols})
    SELECT {select_cols}
      FROM incoming i
     WHERE NOT EXISTS (
        SELECT 1
          FROM analisis_axial a
         WHERE a.project_id = i.project_id
           AND a.categoria = i.categoria
           AND a.codigo = i.codigo
           AND a.relacion = i.relacion
     );
    """
    with pg.cursor() as cur:
        execute_values(cur, sql, formatted, page_size=100)
    pg.commit()


def fetch_fragment_by_id(pg: PGConnection, fragment_id: str, project: Optional[str] = None) -> Optional[Dict[str, Any]]:
    sql = """
    SELECT project_id, id, archivo, par_idx, fragmento, embedding, area_tematica, actor_principal, requiere_protocolo_lluvia, speaker, interviewer_tokens, interviewee_tokens
      FROM entrevista_fragmentos
     WHERE id = %s AND project_id = %s
    """
    with pg.cursor() as cur:
        cur.execute(sql, (fragment_id, project or "default"))
        row = cur.fetchone()
    if row is None:
        return None
    keys = [
        "project_id",
        "id",
        "archivo",
        "par_idx",
        "fragmento",
        "embedding",
        "area_tematica",
        "actor_principal",
        "requiere_protocolo_lluvia",
        "speaker",
        "interviewer_tokens",
        "interviewee_tokens",
    ]
    return dict(zip(keys, row))


def get_fragment_context(pg: PGConnection, fragment_id: str, project: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Obtiene el contexto completo de un fragmento, incluyendo todos sus códigos asociados.
    
    Retorna:
        - Datos completos del fragmento
        - Lista de todos los códigos asignados a este fragmento
        - Metadatos adicionales para visualización
    """
    project_id = project or "default"
    
    # 1. Obtener fragmento completo
    fragment_sql = """
    SELECT project_id, id, archivo, par_idx, fragmento, 
           area_tematica, actor_principal, requiere_protocolo_lluvia,
           speaker, metadata, created_at
      FROM entrevista_fragmentos
     WHERE id = %s AND project_id = %s
    """
    with pg.cursor() as cur:
        cur.execute(fragment_sql, (fragment_id, project_id))
        frag_row = cur.fetchone()
    
    if not frag_row:
        return None
    
    fragment = {
        "project_id": frag_row[0],
        "id": frag_row[1],
        "archivo": frag_row[2],
        "par_idx": frag_row[3],
        "fragmento": frag_row[4],
        "area_tematica": frag_row[5],
        "actor_principal": frag_row[6],
        "requiere_protocolo_lluvia": frag_row[7],
        "speaker": frag_row[8],
        "metadata": frag_row[9],
        "created_at": frag_row[10].isoformat().replace("+00:00", "Z") if frag_row[10] else None,
    }
    
    # 2. Obtener todos los códigos asociados a este fragmento
    codes_sql = """
    SELECT codigo, cita, fuente, memo, created_at
      FROM analisis_codigos_abiertos
     WHERE fragmento_id = %s AND project_id = %s
     ORDER BY created_at DESC
    """
    with pg.cursor() as cur:
        cur.execute(codes_sql, (fragment_id, project_id))
        code_rows = cur.fetchall()
    
    codes = [
        {
            "codigo": r[0],
            "cita": r[1],
            "fuente": r[2],
            "memo": r[3],
            "created_at": r[4].isoformat().replace("+00:00", "Z") if r[4] else None,
        }
        for r in code_rows
    ]
    
    # 3. Obtener fragmentos adyacentes para contexto (opcional)
    adjacent_sql = """
    SELECT id, par_idx, fragmento, speaker
      FROM entrevista_fragmentos
     WHERE archivo = %s 
       AND project_id = %s
       AND par_idx BETWEEN %s AND %s
       AND id != %s
     ORDER BY par_idx ASC
    """
    par_idx = fragment["par_idx"]
    with pg.cursor() as cur:
        cur.execute(adjacent_sql, (
            fragment["archivo"], 
            project_id, 
            max(0, par_idx - 1),  # 1 párrafo antes
            par_idx + 1,          # 1 párrafo después
            fragment_id
        ))
        adjacent_rows = cur.fetchall()
    
    adjacent = [
        {
            "id": r[0],
            "par_idx": r[1],
            "fragmento": r[2][:300] + "..." if len(r[2]) > 300 else r[2],  # Truncar
            "speaker": r[3],
            "position": "before" if r[1] < par_idx else "after"
        }
        for r in adjacent_rows
    ]
    
    return {
        "fragment": fragment,
        "codes": codes,
        "codes_count": len(codes),
        "adjacent_fragments": adjacent,
    }


def get_citations_by_code(pg: PGConnection, codigo: str, project: Optional[str] = None) -> List[Dict[str, Any]]:
    project_id = project or "default"
    sql = """
    SELECT aca.fragmento_id, aca.codigo, aca.archivo, aca.cita, aca.fuente, aca.memo, aca.created_at,
           cc.code_id
      FROM analisis_codigos_abiertos aca
      LEFT JOIN catalogo_codigos cc
        ON cc.project_id = aca.project_id AND cc.codigo = aca.codigo
     WHERE aca.codigo = %s AND aca.project_id = %s
     ORDER BY aca.created_at DESC
    """
    with pg.cursor() as cur:
        cur.execute(sql, (codigo, project_id))
        rows = cur.fetchall()
    return [
        {
            "fragmento_id": r[0],
            "codigo": r[1],
            "archivo": r[2],
            "cita": r[3],
            "fuente": r[4],
            "memo": r[5],
            "created_at": r[6].isoformat().replace("+00:00", "Z") if r[6] else None,
            "code_id": int(r[7]) if r[7] is not None else None,
        }
        for r in rows
    ]


def list_coded_fragment_ids(pg: PGConnection, project: Optional[str] = None) -> List[str]:
    sql = "SELECT DISTINCT fragmento_id FROM analisis_codigos_abiertos WHERE project_id = %s"
    with pg.cursor() as cur:
        cur.execute(sql, (project or "default",))
        return [row[0] for row in cur.fetchall()]


def coding_stats(pg: PGConnection, project: Optional[str] = None) -> Dict[str, Any]:
    stats: Dict[str, Any] = {}
    with pg.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM analisis_codigos_abiertos WHERE project_id = %s", (project or "default",))
        total_citas = cur.fetchone()
        stats["total_citas"] = (total_citas[0] if total_citas else 0) or 0
        cur.execute("SELECT COUNT(DISTINCT codigo) FROM analisis_codigos_abiertos WHERE project_id = %s", (project or "default",))
        codigos_unicos = cur.fetchone()
        stats["codigos_unicos"] = (codigos_unicos[0] if codigos_unicos else 0) or 0
        cur.execute(
            "SELECT COUNT(*) FROM entrevista_fragmentos WHERE project_id = %s AND speaker IS DISTINCT FROM 'interviewer'",
            (project or "default",),
        )
        total_fragments_row = cur.fetchone()
        total_fragments = (total_fragments_row[0] if total_fragments_row else 0) or 0
        stats["fragmentos_totales"] = total_fragments
        cur.execute(
            "SELECT COUNT(DISTINCT fragmento_id) FROM analisis_codigos_abiertos WHERE project_id = %s",
            (project or "default",),
        )
        coded_fragments_row = cur.fetchone()
        coded_fragments = (coded_fragments_row[0] if coded_fragments_row else 0) or 0
        stats["fragmentos_codificados"] = coded_fragments
        stats["fragmentos_sin_codigo"] = max(total_fragments - coded_fragments, 0)
        stats["porcentaje_cobertura"] = (
            coded_fragments / total_fragments if total_fragments else 0
        )
        cur.execute("SELECT COUNT(*) FROM analisis_axial WHERE project_id = %s", (project or "default",))
        relaciones_axiales = cur.fetchone()
        stats["relaciones_axiales"] = (relaciones_axiales[0] if relaciones_axiales else 0) or 0
    return stats


def get_dashboard_counts(pg: PGConnection, project: Optional[str] = None) -> Dict[str, Any]:
    """
    Obtiene conteos en tiempo real para el dashboard de todas las etapas.
    
    Esta función resuelve el Bug E1.1: "0 fragmentos" en Etapa 2.
    
    Returns:
        Dict con conteos por etapa:
        - ingesta: archivos, fragmentos, speaker distribution
        - codificacion: códigos, citas, cobertura
        - axial: relaciones, categorías
        - candidatos: pendientes, validados, rechazados
    """
    project_id = project or "default"
    counts: Dict[str, Any] = {}

    # Ensure required tables exist so the dashboard never 500s just because a
    # project hasn't reached later stages yet.
    ensure_open_coding_table(pg)
    ensure_axial_table(pg)
    ensure_candidate_codes_table(pg)
    ensure_familiarization_reviews_table(pg)
    
    with pg.cursor() as cur:
        # =====================================================================
        # ETAPA 1 & 2: INGESTA - Fragmentos totales
        # =====================================================================
        cur.execute("""
            SELECT 
                COUNT(*) AS total,
                COUNT(DISTINCT archivo) AS archivos,
                COUNT(*) FILTER (WHERE speaker = 'interviewer') AS interviewer_frags,
                COUNT(*) FILTER (WHERE speaker = 'interviewee') AS interviewee_frags,
                COUNT(*) FILTER (WHERE speaker IS NULL OR speaker NOT IN ('interviewer','interviewee')) AS other_frags
            FROM entrevista_fragmentos
            WHERE project_id = %s
        """, (project_id,))
        row = cur.fetchone()
        ingesta_row = row if row is not None else (0, 0, 0, 0, 0)
        counts["ingesta"] = {
            "fragmentos_totales": ingesta_row[0],
            "archivos": ingesta_row[1],
            "fragmentos_entrevistador": ingesta_row[2],
            "fragmentos_entrevistado": ingesta_row[3],
            "fragmentos_otros": ingesta_row[4],
            # Fragmentos "útiles" para análisis (sin entrevistador)
            "fragmentos_analizables": ingesta_row[3] + ingesta_row[4],
        }

        # =====================================================================
        # ETAPA 2: FAMILIARIZACIÓN - Entrevistas revisadas
        # =====================================================================
        cur.execute(
            """
            SELECT COUNT(*)
            FROM familiarization_reviews
            WHERE project_id = %s
            """,
            (project_id,),
        )
        reviewed_row = cur.fetchone()
        entrevistas_revisadas = (reviewed_row[0] if reviewed_row else 0) or 0
        entrevistas_totales = counts["ingesta"]["archivos"]
        porcentaje = (
            round((entrevistas_revisadas / entrevistas_totales) * 100, 1)
            if entrevistas_totales > 0
            else 0
        )
        counts["familiarizacion"] = {
            "entrevistas_revisadas": entrevistas_revisadas,
            "entrevistas_totales": entrevistas_totales,
            "porcentaje": porcentaje,
        }
        
        # =====================================================================
        # ETAPA 3: CODIFICACIÓN ABIERTA
        # =====================================================================
        cur.execute("""
            SELECT 
                COUNT(*) AS total_citas,
                COUNT(DISTINCT codigo) AS codigos_unicos,
                COUNT(DISTINCT fragmento_id) AS fragmentos_codificados
            FROM analisis_codigos_abiertos
            WHERE project_id = %s
        """, (project_id,))
        row = cur.fetchone()
        codificacion_row = row if row is not None else (0, 0, 0)
        codificacion = {
            "citas": codificacion_row[0],
            "codigos_unicos": codificacion_row[1],
            "fragmentos_codificados": codificacion_row[2],
        }
        
        # Calcular cobertura
        total_analizables = counts["ingesta"]["fragmentos_analizables"]
        codificacion["fragmentos_sin_codigo"] = max(total_analizables - codificacion["fragmentos_codificados"], 0)
        codificacion["porcentaje_cobertura"] = round(
            codificacion["fragmentos_codificados"] / total_analizables * 100, 1
        ) if total_analizables > 0 else 0
        
        counts["codificacion"] = codificacion
        
        # =====================================================================
        # ETAPA 4: CODIFICACIÓN AXIAL
        # =====================================================================
        cur.execute("""
            SELECT 
                COUNT(*) AS total_relaciones,
                COUNT(DISTINCT categoria) AS categorias,
                COUNT(DISTINCT codigo) AS codigos_relacionados
            FROM analisis_axial
            WHERE project_id = %s
        """, (project_id,))
        row = cur.fetchone()
        axial_row = row if row is not None else (0, 0, 0)
        counts["axial"] = {
            "relaciones": axial_row[0],
            "categorias": axial_row[1],
            "codigos_relacionados": axial_row[2],
        }
        
        # =====================================================================
        # BANDEJA DE CANDIDATOS (Modelo Híbrido)
        # =====================================================================
        cur.execute("""
            SELECT 
                estado,
                COUNT(*) AS total
            FROM codigos_candidatos
            WHERE project_id = %s
            GROUP BY estado
        """, (project_id,))
        rows = cur.fetchall()
        candidatos = {"pendientes": 0, "validados": 0, "rechazados": 0, "fusionados": 0}
        for row in rows:
            estado = row[0] or "pendiente"
            if estado in candidatos:
                candidatos[estado] = row[1]
            else:
                candidatos[estado] = row[1]
        candidatos["total"] = sum(candidatos.values())
        counts["candidatos"] = candidatos
    
    # Añadir timestamp
    from datetime import datetime
    counts["timestamp"] = datetime.utcnow().isoformat() + "Z"
    counts["project_id"] = project_id
    
    return counts


def ensure_familiarization_reviews_table(pg: PGConnection) -> None:
    """Crea tabla de reviews de familiarización por entrevista.

    Best practice: persistir un evento explícito (archivo revisado) para poder
    calcular progreso real (revisadas/total) y auditar quién/cuándo.
    """
    sql = """
    CREATE TABLE IF NOT EXISTS familiarization_reviews (
        project_id TEXT NOT NULL,
        archivo TEXT NOT NULL,
        reviewed_by TEXT,
        reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (project_id, archivo)
    );
    CREATE INDEX IF NOT EXISTS ix_fam_reviews_project ON familiarization_reviews(project_id);
    CREATE INDEX IF NOT EXISTS ix_fam_reviews_reviewed_at ON familiarization_reviews(reviewed_at DESC);
    """
    with pg.cursor() as cur:
        cur.execute(sql)
    pg.commit()


def upsert_familiarization_review(pg: PGConnection, project_id: str, archivo: str, reviewed_by: Optional[str] = None) -> None:
    ensure_familiarization_reviews_table(pg)
    with pg.cursor() as cur:
        cur.execute(
            """
            INSERT INTO familiarization_reviews (project_id, archivo, reviewed_by)
            VALUES (%s, %s, %s)
            ON CONFLICT (project_id, archivo)
            DO UPDATE SET reviewed_at = NOW(), reviewed_by = EXCLUDED.reviewed_by
            """,
            (project_id, archivo, reviewed_by),
        )
    pg.commit()


def delete_familiarization_review(pg: PGConnection, project_id: str, archivo: str) -> None:
    ensure_familiarization_reviews_table(pg)
    with pg.cursor() as cur:
        cur.execute(
            "DELETE FROM familiarization_reviews WHERE project_id = %s AND archivo = %s",
            (project_id, archivo),
        )
    pg.commit()


def list_familiarization_reviews(pg: PGConnection, project_id: str) -> List[Dict[str, Any]]:
    ensure_familiarization_reviews_table(pg)
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT archivo, reviewed_at, reviewed_by
            FROM familiarization_reviews
            WHERE project_id = %s
            ORDER BY reviewed_at DESC, archivo ASC
            """,
            (project_id,),
        )
        rows = cur.fetchall()
    return [
        {
            "archivo": r[0],
            "reviewed_at": r[1].isoformat().replace("+00:00", "Z") if r[1] else None,
            "reviewed_by": r[2],
        }
        for r in rows
    ]


def list_interviews_summary(pg: PGConnection, project: Optional[str] = None, limit: int = 25) -> List[Dict[str, Any]]:
    sql = """
    SELECT archivo,
           COUNT(*) AS fragmentos,
           COALESCE(MAX(actor_principal) FILTER (WHERE actor_principal IS NOT NULL), '') AS actor_principal,
           COALESCE(MAX(area_tematica) FILTER (WHERE area_tematica IS NOT NULL), '') AS area_tematica,
                     COALESCE(MAX((metadata->>'blob_url')) FILTER (WHERE metadata IS NOT NULL AND (metadata ? 'blob_url')), '') AS blob_url,
           MAX(updated_at) AS actualizado
      FROM entrevista_fragmentos
     WHERE project_id = %s
       AND (speaker IS NULL OR speaker <> 'interviewer')
     GROUP BY archivo
     ORDER BY MAX(updated_at) DESC, archivo ASC
     LIMIT %s
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project or "default", max(limit, 1)))
        rows = cur.fetchall()
    return [
        {
            "archivo": row[0],
            "fragmentos": row[1],
            "actor_principal": row[2] or None,
            "area_tematica": row[3] or None,
            "blob_url": row[4] or None,
            "actualizado": row[5].isoformat().replace("+00:00", "Z") if row[5] else None,
        }
        for row in rows
    ]


def list_codes_summary(pg: PGConnection, project: Optional[str] = None, limit: int = 50, search: Optional[str] = None, archivo: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Lista códigos con estadísticas agregadas.
    
    Args:
        pg: Conexión a PostgreSQL
        project: ID del proyecto
        limit: Máximo de códigos a retornar
        search: Búsqueda por nombre de código (ILIKE)
        archivo: Filtrar códigos que aparecen en este archivo de entrevista
        
    Returns:
        Lista de códigos con citas, fragmentos, fechas y code_id
    """
    clauses: List[str] = []
    params: List[Any] = []
    clauses.append("aca.project_id = %s")
    params.append(project or "default")
    if search and search.strip():
        clauses.append("aca.codigo ILIKE %s")
        params.append(f"%{search.strip()}%")
    if archivo and archivo.strip():
        clauses.append("aca.archivo = %s")
        params.append(archivo.strip())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
    SELECT aca.codigo,
           COUNT(*) AS citas,
                     COUNT(DISTINCT aca.fragmento_id) AS fragmentos,
                     MIN(aca.created_at) AS primera_cita,
                     MAX(aca.created_at) AS ultima_cita,
           COALESCE(cc.status, 'active') AS status,
           cc.canonical_codigo,
           cc.code_id
      FROM analisis_codigos_abiertos aca
      LEFT JOIN catalogo_codigos cc
        ON cc.project_id = aca.project_id AND cc.codigo = aca.codigo
      {where}
     GROUP BY aca.codigo, cc.status, cc.canonical_codigo, cc.code_id
         ORDER BY MAX(aca.created_at) DESC NULLS LAST, aca.codigo ASC
     LIMIT %s
    """
    params.append(max(limit, 1))
    with pg.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [
        {
            "codigo": row[0],
            "citas": row[1],
            "fragmentos": row[2],
            "primera_cita": row[3].isoformat().replace("+00:00", "Z") if row[3] else None,
            "ultima_cita": row[4].isoformat().replace("+00:00", "Z") if row[4] else None,
            "status": row[5],
            "canonical_codigo": row[6],
            "code_id": int(row[7]) if row[7] is not None else None,
        }
        for row in rows
    ]


def list_fragments_for_file(pg: PGConnection, project: Optional[str], archivo: str, limit: int = 25) -> List[Dict[str, Any]]:
    sql = """
    SELECT id, archivo, par_idx, char_len, fragmento
      FROM entrevista_fragmentos
     WHERE archivo = %s
       AND project_id = %s
       AND (speaker IS NULL OR speaker <> 'interviewer')
     ORDER BY par_idx ASC
     LIMIT %s
    """
    with pg.cursor() as cur:
        cur.execute(sql, (archivo, project or "default", max(limit, 1)))
        rows = cur.fetchall()
    return [
        {
            "fragmento_id": row[0],
            "archivo": row[1],
            "par_idx": row[2],
            "char_len": row[3],
            "fragmento": row[4],
        }
        for row in rows
    ]


# =============================================================================
# CODIFICACIÓN ABIERTA - Inteligencia v1 (feedback + next fragment)
# =============================================================================


def ensure_coding_feedback_table(pg: PGConnection) -> None:
    """Tabla de eventos de feedback sobre sugerencias de codificación.

    Best practice: registrar explícitamente accept/reject/edit para aprender
    ranking y trazabilidad (sin acoplarlo a LLM).
    """
    sql = """
    CREATE TABLE IF NOT EXISTS coding_feedback_events (
        id SERIAL PRIMARY KEY,
        project_id TEXT NOT NULL,
        fragmento_id TEXT NOT NULL,
        archivo TEXT,
        action TEXT NOT NULL, -- accept | reject | edit
        suggested_code TEXT,
        final_code TEXT,
        source TEXT, -- next | manual | semantic | llm | runner
        meta JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_cfe_project_created ON coding_feedback_events(project_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_cfe_project_action ON coding_feedback_events(project_id, action);
    CREATE INDEX IF NOT EXISTS ix_cfe_project_suggested ON coding_feedback_events(project_id, suggested_code);
    """
    with pg.cursor() as cur:
        cur.execute(sql)
    pg.commit()


def insert_coding_feedback_event(
    pg: PGConnection,
    *,
    project_id: str,
    fragmento_id: str,
    archivo: Optional[str],
    action: str,
    suggested_code: Optional[str] = None,
    final_code: Optional[str] = None,
    source: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    ensure_coding_feedback_table(pg)
    with pg.cursor() as cur:
        cur.execute(
            """
            INSERT INTO coding_feedback_events (
                project_id, fragmento_id, archivo, action, suggested_code, final_code, source, meta
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                project_id,
                fragmento_id,
                archivo,
                action,
                suggested_code,
                final_code,
                source,
                Json(meta) if meta is not None else None,
            ),
        )
    pg.commit()


def get_top_open_codes(
    pg: PGConnection,
    *,
    project_id: str,
    archivo: Optional[str] = None,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    ensure_open_coding_table(pg)
    where = "WHERE project_id = %s"
    params: List[Any] = [project_id]
    if archivo:
        where += " AND archivo = %s"
        params.append(archivo)
    sql = f"""
    SELECT codigo, COUNT(*) AS citas
      FROM analisis_codigos_abiertos
      {where}
     GROUP BY codigo
     ORDER BY COUNT(*) DESC, codigo ASC
     LIMIT %s
    """
    params.append(max(1, int(limit)))
    with pg.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []
    return [{"codigo": r[0], "citas": int(r[1] or 0)} for r in rows]


def select_next_uncoded_fragment(
    pg: PGConnection,
    *,
    project_id: str,
    archivo: Optional[str] = None,
    exclude_fragment_ids: Optional[List[str]] = None,
    strategy: str = "recent",
) -> Optional[Dict[str, Any]]:
    """Elige el próximo fragmento no codificado (heurística v1, Postgres-only)."""
    ensure_fragment_table(pg)
    ensure_open_coding_table(pg)

    params: List[Any] = [project_id, project_id]
    archivo_filter = ""
    if archivo:
        archivo_filter = "AND ef.archivo = %s"
        params.append(archivo)

    exclude_filter = ""
    exclude_ids = [str(x).strip() for x in (exclude_fragment_ids or []) if str(x).strip()]
    if exclude_ids:
        exclude_filter = "AND NOT (ef.id = ANY(%s))"
        params.append(exclude_ids)

    strategy_key = (strategy or "recent").strip().lower()
    if strategy_key not in {"recent", "oldest", "random"}:
        strategy_key = "recent"

    if strategy_key == "oldest":
        order_by = "ef.updated_at ASC, ef.archivo ASC, ef.par_idx ASC"
    elif strategy_key == "random":
        order_by = "random()"
    else:
        # Prefer fragments from recently updated interviews, then earliest par_idx.
        order_by = "ef.updated_at DESC, ef.archivo ASC, ef.par_idx ASC"

    sql = f"""
    WITH coded AS (
        SELECT DISTINCT fragmento_id
          FROM analisis_codigos_abiertos
         WHERE project_id = %s
    )
    SELECT ef.id, ef.archivo, ef.par_idx, ef.fragmento, ef.area_tematica, ef.actor_principal, ef.requiere_protocolo_lluvia
      FROM entrevista_fragmentos ef
      LEFT JOIN coded c ON c.fragmento_id = ef.id
     WHERE ef.project_id = %s
       AND (ef.speaker IS NULL OR ef.speaker <> 'interviewer')
       AND c.fragmento_id IS NULL
       {archivo_filter}
             {exclude_filter}
         ORDER BY {order_by}
     LIMIT 1
    """
    with pg.cursor() as cur:
        cur.execute(sql, tuple(params))
        row = cur.fetchone()

    if not row:
        return None
    return {
        "fragmento_id": row[0],
        "archivo": row[1],
        "par_idx": row[2],
        "fragmento": row[3],
        "area_tematica": row[4],
        "actor_principal": row[5],
        "requiere_protocolo_lluvia": row[6],
    }


def get_open_coding_pending_counts(
    pg: PGConnection,
    *,
    project_id: str,
    archivo: Optional[str] = None,
) -> Dict[str, Optional[int]]:
    """Cuenta fragmentos pendientes (sin código) para codificación abierta.

    Returns:
        {
          "pending_total": int,
          "pending_in_archivo": Optional[int]
        }
    """
    ensure_fragment_table(pg)
    ensure_open_coding_table(pg)

    archivo_clean = (archivo or "").strip() or None

    sql = """
    WITH coded AS (
        SELECT DISTINCT fragmento_id
          FROM analisis_codigos_abiertos
         WHERE project_id = %s
    )
    SELECT
        COUNT(*) FILTER (WHERE c.fragmento_id IS NULL) AS pending_total,
        COUNT(*) FILTER (WHERE c.fragmento_id IS NULL AND ef.archivo = %s) AS pending_in_archivo
      FROM entrevista_fragmentos ef
      LEFT JOIN coded c ON c.fragmento_id = ef.id
     WHERE ef.project_id = %s
       AND (ef.speaker IS NULL OR ef.speaker <> 'interviewer')
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project_id, archivo_clean, project_id))
        row = cur.fetchone()

    pending_total = int((row[0] if row else 0) or 0)
    pending_in_archivo = int((row[1] if row else 0) or 0) if archivo_clean else None

    return {"pending_total": pending_total, "pending_in_archivo": pending_in_archivo}


def coded_fragments_for_code(pg: PGConnection, codigo: str, fragment_ids: Iterable[str], project: Optional[str] = None) -> Dict[str, bool]:
    ids = list(dict.fromkeys(fragment_ids))
    if not ids:
        return {}
    sql = """SELECT fragmento_id FROM analisis_codigos_abiertos WHERE codigo = %s AND fragmento_id = ANY(%s) AND project_id = %s"""
    with pg.cursor() as cur:
        cur.execute(sql, (codigo, ids, project or "default"))
        present = {row[0] for row in cur.fetchall()}
    return {fid: (fid in present) for fid in ids}


def total_interviews(pg: PGConnection, project: Optional[str] = None) -> int:
    with pg.cursor() as cur:
        cur.execute("SELECT COUNT(DISTINCT archivo) FROM entrevista_fragmentos WHERE project_id = %s", (project or "default",))
        row = cur.fetchone()
    return row[0] if row and row[0] is not None else 0


def coverage_for_category(pg: PGConnection, categoria: str, project: Optional[str] = None) -> Dict[str, Any]:
    """Return evidence distribution for a category across interviews and roles."""

    sql_evidence = """
    SELECT DISTINCT evid.fragmento_id,
                    ef.archivo,
                    ef.actor_principal,
                    ef.area_tematica,
                    ef.requiere_protocolo_lluvia
      FROM analisis_axial aa
      CROSS JOIN UNNEST(aa.evidencia) AS evid(fragmento_id)
      JOIN entrevista_fragmentos ef ON ef.id = evid.fragmento_id
     WHERE aa.categoria = %s
       AND aa.project_id = %s
       AND ef.project_id = aa.project_id
    """

    with pg.cursor() as cur:
        cur.execute(sql_evidence, (categoria, project or "default"))
        evidence_rows = cur.fetchall()

    evidencia_ids: List[str] = []
    entrevistas_map: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"fragmentos": 0, "lluvia": 0})
    roles_map: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"fragmentos": 0, "entrevistas": set()})
    areas_map: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"fragmentos": 0, "entrevistas": set()})

    for fragmento_id, archivo, actor, area, lluvia in evidence_rows:
        evidencia_ids.append(fragmento_id)

        if archivo:
            entrevistas_entry = entrevistas_map[archivo]
            entrevistas_entry["fragmentos"] += 1
            if lluvia:
                entrevistas_entry["lluvia"] += 1

        actor_key = actor or "(sin dato)"
        role_entry = roles_map[actor_key]
        role_entry["fragmentos"] += 1
        if archivo:
            role_entry.setdefault("entrevistas", set()).add(archivo)

        area_key = area or "(sin dato)"
        area_entry = areas_map[area_key]
        area_entry["fragmentos"] += 1
        if archivo:
            area_entry.setdefault("entrevistas", set()).add(archivo)

    entrevistas = [
        {
            "archivo": archivo,
            "fragmentos": data["fragmentos"],
            "requiere_protocolo_lluvia": data["lluvia"] > 0,
        }
        for archivo, data in sorted(
            entrevistas_map.items(), key=lambda item: item[1]["fragmentos"], reverse=True
        )
    ]

    roles = [
        {
            "actor_principal": actor if actor != "(sin dato)" else None,
            "fragmentos": data["fragmentos"],
            "entrevistas": len(data.get("entrevistas", set())),
        }
        for actor, data in sorted(
            roles_map.items(), key=lambda item: item[1]["fragmentos"], reverse=True
        )
    ]

    areas = [
        {
            "area_tematica": area if area != "(sin dato)" else None,
            "fragmentos": data["fragmentos"],
            "entrevistas": len(data.get("entrevistas", set())),
        }
        for area, data in sorted(
            areas_map.items(), key=lambda item: item[1]["fragmentos"], reverse=True
        )
    ]

    archivos = [entry["archivo"] for entry in entrevistas]
    total = total_interviews(pg, project)
    cobertura = len(archivos) / total if total else 0.0

    return {
        "archivos": archivos,
        "total_entrevistas": total,
        "cobertura": cobertura,
        "entrevistas": entrevistas,
        "roles": roles,
        "areas": areas,
        "fragmentos_total": len(evidencia_ids),
        "fragmentos_lluvia": sum(1 for _, _, _, _, lluvia in evidence_rows if lluvia),
        "evidencia_ids": evidencia_ids,
        "roles_cubiertos": sum(1 for role in roles if role["actor_principal"]),
        "entrevistas_cubiertas": len(archivos),
    }


def quotes_for_category(pg: PGConnection, categoria: str, project: Optional[str] = None, limite: int = 5) -> List[Dict[str, Any]]:
        sql = """
        SELECT fragmento_id,
               codigo,
               archivo,
               cita,
               fuente
          FROM (
            SELECT DISTINCT ON (aca.fragmento_id, aca.codigo)
                   aca.fragmento_id,
                   aca.codigo,
                   aca.archivo,
                   aca.cita,
                   aca.fuente,
                   aca.created_at
              FROM analisis_axial aa
              CROSS JOIN UNNEST(aa.evidencia) AS evid(fragmento_id)
              JOIN analisis_codigos_abiertos aca
                ON aca.fragmento_id = evid.fragmento_id
               AND aca.codigo = aa.codigo
             WHERE aa.categoria = %s
               AND aa.project_id = %s
               AND aca.project_id = aa.project_id
             ORDER BY aca.fragmento_id, aca.codigo, aca.created_at DESC
          ) AS ordered
         ORDER BY ordered.created_at DESC
         LIMIT %s
        """
        with pg.cursor() as cur:
            cur.execute(sql, (categoria, project or "default", limite))
            rows = cur.fetchall()

        return [
            {
                "fragmento_id": r[0],
                "codigo": r[1],
                "archivo": r[2],
                "cita": r[3],
                "fuente": r[4],
            }
            for r in rows
        ]



def quote_count_for_category(pg: PGConnection, categoria: str, project: Optional[str] = None) -> int:
    sql = """
    SELECT COUNT(DISTINCT aca.fragmento_id)
      FROM analisis_axial aa
      CROSS JOIN UNNEST(aa.evidencia) AS evid(fragmento_id)
      JOIN analisis_codigos_abiertos aca
        ON aca.fragmento_id = evid.fragmento_id
       AND aca.codigo = aa.codigo
     WHERE aa.categoria = %s
       AND aa.project_id = %s
       AND aca.project_id = aa.project_id
    """
    with pg.cursor() as cur:
        cur.execute(sql, (categoria, project or "default"))
        row = cur.fetchone()
    return row[0] if row and row[0] is not None else 0


def cumulative_code_curve(pg: PGConnection, project: Optional[str] = None) -> List[Dict[str, Any]]:
    sql = """
    WITH interview_order AS (
        SELECT
            archivo,
            MIN(created_at) AS first_seen,
            ROW_NUMBER() OVER (ORDER BY MIN(created_at), archivo) AS interview_idx
        FROM analisis_codigos_abiertos
        WHERE project_id = %s
        GROUP BY archivo
    ),
    first_code AS (
        SELECT DISTINCT ON (codigo)
            codigo,
            archivo AS first_archivo
        FROM analisis_codigos_abiertos
        WHERE project_id = %s
        ORDER BY codigo, created_at, archivo
    ),
    per_interview AS (
        SELECT
            io.interview_idx,
            io.archivo,
            COUNT(DISTINCT aca.codigo) AS codigos_totales,
            COUNT(DISTINCT CASE WHEN fc.first_archivo = io.archivo THEN aca.codigo END) AS nuevos_codigos
        FROM interview_order io
        LEFT JOIN analisis_codigos_abiertos aca
          ON aca.archivo = io.archivo
         AND aca.project_id = %s
        LEFT JOIN first_code fc
          ON fc.codigo = aca.codigo
        GROUP BY io.interview_idx, io.archivo
    )
    SELECT
        interview_idx,
        archivo,
        codigos_totales,
        nuevos_codigos,
        SUM(nuevos_codigos) OVER (ORDER BY interview_idx) AS codigos_acumulados
    FROM per_interview
    ORDER BY interview_idx
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project or "default", project or "default", project or "default"))
        rows = cur.fetchall()

    keys = [
        "interview_idx",
        "archivo",
        "codigos_totales",
        "nuevos_codigos",
        "codigos_acumulados",
    ]
    curve = [dict(zip(keys, row)) for row in rows]
    total_codigos = curve[-1]["codigos_acumulados"] if curve else 0
    for item in curve:
        total = item.get("codigos_totales") or 0
        nuevos = item.get("nuevos_codigos") or 0
        acumulados = item.get("codigos_acumulados") or 0
        item["porcentaje_nuevos"] = (nuevos / total) if total else 0.0
        item["porcentaje_cobertura"] = (acumulados / total_codigos) if total_codigos else 0.0
    return curve


def evaluate_curve_plateau(
    curve: List[Dict[str, Any]],
    *,
    window: int = 3,
    threshold: int = 0,
) -> Dict[str, Any]:
    if not curve:
        return {"window": window, "threshold": threshold, "plateau": False, "nuevos_codigos": []}
    window = max(window, 1)
    tail = curve[-window:]
    nuevos = [item.get("nuevos_codigos", 0) for item in tail]
    plateau = all(value <= threshold for value in nuevos) if len(tail) == window else False
    return {
        "window": window,
        "threshold": threshold,
        "plateau": plateau,
        "nuevos_codigos": nuevos,
    }


def fetch_recent_fragments(
    pg: PGConnection,
    *,
    project: Optional[str] = None,
    archivo: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    sql = """
        SELECT id, archivo, embedding, metadata, updated_at
          FROM entrevista_fragmentos
         WHERE project_id = %s
           AND (%s IS NULL OR archivo = %s)
           AND (speaker IS NULL OR speaker <> 'interviewer')
         ORDER BY updated_at DESC
         LIMIT %s
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project or "default", archivo, archivo, limit))
        rows = cur.fetchall()
    keys = ["fragmento_id", "archivo", "embedding", "metadata", "updated_at"]
    return [dict(zip(keys, row)) for row in rows]


def member_checking_packets(
    pg: PGConnection,
    *,
    project: Optional[str] = None,
    actor_principal: Optional[str] = None,
    archivo: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    sql = """
    WITH base AS (
        SELECT
            aca.archivo,
            COALESCE(NULLIF(aca.fuente, ''), ef.metadata->>'participante', '(sin fuente)') AS participante,
            ef.actor_principal,
            aca.codigo,
            ARRAY_REMOVE(ARRAY_AGG(DISTINCT aa.categoria), NULL) AS categorias,
            JSON_AGG(DISTINCT JSONB_BUILD_OBJECT(
                'fragmento_id', aca.fragmento_id,
                'cita', aca.cita
            )) FILTER (WHERE aca.cita IS NOT NULL) AS citas
        FROM analisis_codigos_abiertos aca
        JOIN entrevista_fragmentos ef ON ef.id = aca.fragmento_id AND ef.project_id = aca.project_id
        LEFT JOIN analisis_axial aa ON aa.codigo = aca.codigo AND aa.project_id = aca.project_id
        WHERE (%s IS NULL OR ef.actor_principal = %s)
          AND (%s IS NULL OR aca.archivo = %s)
          AND aca.project_id = %s
        GROUP BY aca.archivo, participante, ef.actor_principal, aca.codigo
    ),
    grouped AS (
        SELECT
            archivo,
            participante,
            actor_principal,
            COUNT(DISTINCT codigo) AS codigos_distintos,
            ARRAY_AGG(JSONB_BUILD_OBJECT(
                'codigo', codigo,
                'categorias', categorias,
                'citas', COALESCE(citas, '[]'::JSON)::JSONB
            ) ORDER BY codigo) AS detalle
        FROM base
        GROUP BY archivo, participante, actor_principal
        ORDER BY archivo, participante
        LIMIT %s
    )
    SELECT archivo, participante, actor_principal, codigos_distintos, detalle
    FROM grouped
    """
    with pg.cursor() as cur:
        cur.execute(sql, (actor_principal, actor_principal, archivo, archivo, project or "default", limit))
        rows = cur.fetchall()
    packets: List[Dict[str, Any]] = []
    for row in rows:
        archivo_val, participante, actor, codigos_distintos, detalle = row
        packets.append(
            {
                "archivo": archivo_val,
                "participante": participante,
                "actor_principal": actor,
                "codigos_distintos": codigos_distintos,
                "detalle": detalle,
            }
        )
    return packets


_TRANSVERSAL_VIEW_DEFINITIONS = {
    "mv_categoria_por_rol": """
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_categoria_por_rol AS
        SELECT
            aa.project_id AS project_id,
            aa.categoria AS categoria,
            COALESCE(NULLIF(ef.actor_principal, ''), '(sin rol)') AS grupo,
            COUNT(DISTINCT ef.archivo) AS entrevistas,
            COUNT(DISTINCT aa.codigo) AS codigos,
            COUNT(*) AS relaciones
        FROM analisis_axial aa
        CROSS JOIN UNNEST(aa.evidencia) AS evid(fragmento_id)
        JOIN entrevista_fragmentos ef ON ef.id = evid.fragmento_id AND ef.project_id = aa.project_id
        GROUP BY aa.project_id, aa.categoria, grupo
    """,
    "mv_categoria_por_genero": """
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_categoria_por_genero AS
        SELECT
            aa.project_id AS project_id,
            aa.categoria AS categoria,
            COALESCE(NULLIF(TRIM(ef.metadata->>'genero'), ''), '(sin genero)') AS grupo,
            COUNT(DISTINCT ef.archivo) AS entrevistas,
            COUNT(DISTINCT aa.codigo) AS codigos,
            COUNT(*) AS relaciones
        FROM analisis_axial aa
        CROSS JOIN UNNEST(aa.evidencia) AS evid(fragmento_id)
        JOIN entrevista_fragmentos ef ON ef.id = evid.fragmento_id AND ef.project_id = aa.project_id
        GROUP BY aa.project_id, aa.categoria, grupo
    """,
    "mv_categoria_por_periodo": """
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_categoria_por_periodo AS
        SELECT
            aa.project_id AS project_id,
            aa.categoria AS categoria,
            COALESCE(NULLIF(TRIM(ef.metadata->>'periodo'), ''), '(sin periodo)') AS grupo,
            COUNT(DISTINCT ef.archivo) AS entrevistas,
            COUNT(DISTINCT aa.codigo) AS codigos,
            COUNT(*) AS relaciones
        FROM analisis_axial aa
        CROSS JOIN UNNEST(aa.evidencia) AS evid(fragmento_id)
        JOIN entrevista_fragmentos ef ON ef.id = evid.fragmento_id AND ef.project_id = aa.project_id
        GROUP BY aa.project_id, aa.categoria, grupo
    """,
}

_TRANSVERSAL_VIEW_ORDER = [
    "mv_categoria_por_rol",
    "mv_categoria_por_genero",
    "mv_categoria_por_periodo",
]

_DIMENSION_VIEW_MAP = {
    "rol": "mv_categoria_por_rol",
    "genero": "mv_categoria_por_genero",
    "periodo": "mv_categoria_por_periodo",
}


def ensure_transversal_views(pg: PGConnection, project: Optional[str] = None) -> None:
    with pg.cursor() as cur:
        for view_name in _TRANSVERSAL_VIEW_ORDER:
            cur.execute(_TRANSVERSAL_VIEW_DEFINITIONS[view_name])
    pg.commit()


def refresh_transversal_views(pg: PGConnection) -> None:
    with pg.cursor() as cur:
        for view_name in _TRANSVERSAL_VIEW_ORDER:
            cur.execute(f"REFRESH MATERIALIZED VIEW {view_name}")
    pg.commit()


def fetch_cross_tab(
    pg: PGConnection,
    dimension: str,
    categoria: Optional[str] = None,
    limit: int = 50,
    project: Optional[str] = None,
) -> List[Dict[str, Any]]:
    dim = dimension.lower()
    if dim not in _DIMENSION_VIEW_MAP:
        raise ValueError(f"Dimension no soportada: {dimension}")
    view_name = _DIMENSION_VIEW_MAP[dim]
    sql = f"""
        SELECT categoria, grupo, entrevistas, codigos, relaciones
          FROM {view_name}
         WHERE project_id = %s
           AND (%s IS NULL OR categoria = %s)
         ORDER BY entrevistas DESC, relaciones DESC
         LIMIT %s
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project or "default", categoria, categoria, limit))
        rows = cur.fetchall()
    keys = ["categoria", "grupo", "entrevistas", "codigos", "relaciones"]
    return [dict(zip(keys, row)) for row in rows]


# =============================================================================
# MULTI-USER COLLABORATION (E3)
# =============================================================================

# Roles permitidos: admin (full), codificador (read+write codes), lector (read-only)
PROJECT_ROLES = {"admin", "codificador", "lector"}


def ensure_project_members_table(pg: PGConnection) -> None:
    """Crea tabla para gestión de miembros de proyecto."""
    sql = """
    CREATE TABLE IF NOT EXISTS project_members (
      id SERIAL PRIMARY KEY,
      project_id TEXT NOT NULL,
      user_id TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'lector',
      added_by TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE(project_id, user_id)
    );
    CREATE INDEX IF NOT EXISTS ix_pm_project ON project_members(project_id);
    CREATE INDEX IF NOT EXISTS ix_pm_user ON project_members(user_id);
    
    -- Tabla para audit log de cambios
    CREATE TABLE IF NOT EXISTS project_audit_log (
      id SERIAL PRIMARY KEY,
      project_id TEXT NOT NULL,
      user_id TEXT NOT NULL,
      action TEXT NOT NULL,
            entity_type TEXT,
            entity_id TEXT,
            details JSONB,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

        -- Backward compatible: older DBs had user_id as UUID in these tables
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                    FROM information_schema.columns
                 WHERE table_schema = 'public'
                     AND table_name = 'project_members'
                     AND column_name = 'user_id'
                     AND udt_name = 'uuid'
            ) THEN
                ALTER TABLE project_members ALTER COLUMN user_id TYPE TEXT USING user_id::text;
            END IF;

            IF EXISTS (
                SELECT 1
                    FROM information_schema.columns
                 WHERE table_schema = 'public'
                     AND table_name = 'project_members'
                     AND column_name = 'added_by'
                     AND udt_name = 'uuid'
            ) THEN
                ALTER TABLE project_members ALTER COLUMN added_by TYPE TEXT USING added_by::text;
            END IF;

            IF EXISTS (
                SELECT 1
                    FROM information_schema.columns
                 WHERE table_schema = 'public'
                     AND table_name = 'project_audit_log'
                     AND column_name = 'user_id'
                     AND udt_name = 'uuid'
            ) THEN
                ALTER TABLE project_audit_log ALTER COLUMN user_id TYPE TEXT USING user_id::text;
            END IF;
        END $$;

        -- Backward compatible: DBs created before these columns existed
        ALTER TABLE project_audit_log ADD COLUMN IF NOT EXISTS entity_type TEXT;
        ALTER TABLE project_audit_log ADD COLUMN IF NOT EXISTS entity_id TEXT;
        ALTER TABLE project_audit_log ADD COLUMN IF NOT EXISTS details JSONB;

    CREATE INDEX IF NOT EXISTS ix_pal_project ON project_audit_log(project_id);
    CREATE INDEX IF NOT EXISTS ix_pal_created ON project_audit_log(created_at);
    """
    with pg.cursor() as cur:
        cur.execute(sql)
    pg.commit()


def add_project_member(
    pg: PGConnection,
    project: str,
    user_id: str,
    role: str,
    added_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Agrega un miembro al proyecto con un rol específico."""
    ensure_project_members_table(pg)
    
    if role not in PROJECT_ROLES:
        raise ValueError(f"Rol inválido: {role}. Debe ser uno de: {PROJECT_ROLES}")
    
    sql = """
    INSERT INTO project_members (project_id, user_id, role, added_by)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (project_id, user_id) DO UPDATE SET
        role = EXCLUDED.role,
        added_by = EXCLUDED.added_by
    RETURNING id, project_id, user_id, role, created_at
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project, user_id, role, added_by))
        row = cur.fetchone()
    pg.commit()
    if row is None:
        raise RuntimeError("No se pudo registrar el miembro del proyecto")
    
    return {
        "id": row[0],
        "project_id": row[1],
        "user_id": row[2],
        "role": row[3],
        "created_at": row[4].isoformat() if row[4] else None,
    }


def get_project_members(pg: PGConnection, project: str) -> List[Dict[str, Any]]:
    """Obtiene todos los miembros de un proyecto."""
    ensure_project_members_table(pg)
    
    sql = """
    SELECT id, user_id, role, added_by, created_at
      FROM project_members
     WHERE project_id = %s
     ORDER BY created_at
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project,))
        rows = cur.fetchall()
    
    return [
        {
            "id": r[0],
            "user_id": r[1],
            "role": r[2],
            "added_by": r[3],
            "created_at": r[4].isoformat() if r[4] else None,
        }
        for r in rows
    ]


def get_user_project_role(pg: PGConnection, project: str, user_id: str) -> Optional[str]:
    """Obtiene el rol de un usuario en un proyecto específico."""
    ensure_project_members_table(pg)
    
    sql = "SELECT role FROM project_members WHERE project_id = %s AND user_id = %s"
    with pg.cursor() as cur:
        cur.execute(sql, (project, user_id))
        row = cur.fetchone()
    
    return row[0] if row is not None else None


def check_project_permission(
    pg: PGConnection,
    project: str,
    user_id: str,
    required_role: str,
) -> bool:
    """
    Verifica si un usuario tiene permiso para una acción en un proyecto.
    
    Jerarquía de roles:
    - admin: puede todo
    - codificador: puede leer y escribir códigos
    - lector: solo puede leer
    """
    role = get_user_project_role(pg, project, user_id)
    
    if role is None:
        return False
    
    # Jerarquía de permisos
    role_hierarchy = {"admin": 3, "codificador": 2, "lector": 1}
    required_level = role_hierarchy.get(required_role, 0)
    user_level = role_hierarchy.get(role, 0)
    
    return user_level >= required_level


def get_user_projects(pg: PGConnection, user_id: str) -> List[Dict[str, Any]]:
    """Obtiene todos los proyectos a los que un usuario tiene acceso."""
    ensure_project_members_table(pg)
    
    sql = """
    SELECT project_id, role, created_at
      FROM project_members
     WHERE user_id = %s
     ORDER BY created_at DESC
    """
    with pg.cursor() as cur:
        cur.execute(sql, (user_id,))
        rows = cur.fetchall()
    
    return [
        {
            "project_id": r[0],
            "role": r[1],
            "created_at": r[2].isoformat() if r[2] else None,
        }
        for r in rows
    ]


def assign_org_users_to_project(
    pg: PGConnection,
    project: str,
    org_id: str,
    default_role: str = "codificador",
    use_user_role: bool = True,
    include_inactive: bool = False,
    added_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Asigna usuarios existentes de una organización a un proyecto."""
    ensure_users_table(pg)
    ensure_project_members_table(pg)

    if not use_user_role and default_role not in PROJECT_ROLES:
        raise ValueError(f"Rol inválido: {default_role}. Debe ser uno de: {PROJECT_ROLES}")

    status_filter = "" if include_inactive else "AND is_active = true"
    count_sql = f"SELECT COUNT(*) FROM app_users WHERE organization_id = %s {status_filter}"
    with pg.cursor() as cur:
        cur.execute(count_sql, (org_id,))
        total_users = cur.fetchone()[0]

    if use_user_role:
        role_expr = "CASE app_users.role WHEN 'admin' THEN 'admin' WHEN 'analyst' THEN 'codificador' ELSE 'lector' END"
        sql = f"""
        INSERT INTO project_members (project_id, user_id, role, added_by)
        SELECT %s, id::text, {role_expr}, %s
          FROM app_users
         WHERE organization_id = %s {status_filter}
        ON CONFLICT (project_id, user_id) DO UPDATE SET
            role = EXCLUDED.role,
            added_by = EXCLUDED.added_by
        """
        params = (project, added_by, org_id)
    else:
        sql = f"""
        INSERT INTO project_members (project_id, user_id, role, added_by)
        SELECT %s, id::text, %s, %s
          FROM app_users
         WHERE organization_id = %s {status_filter}
        ON CONFLICT (project_id, user_id) DO UPDATE SET
            role = EXCLUDED.role,
            added_by = EXCLUDED.added_by
        """
        params = (project, default_role, added_by, org_id)

    with pg.cursor() as cur:
        cur.execute(sql, params)
        affected = cur.rowcount
    pg.commit()

    return {
        "project": project,
        "org_id": org_id,
        "users_total": total_users,
        "members_assigned": affected,
        "use_user_role": use_user_role,
        "default_role": default_role,
        "include_inactive": include_inactive,
    }


def log_project_action(
    pg: PGConnection,
    project: str,
    user_id: str,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Registra una acción en el audit log del proyecto."""
    ensure_project_members_table(pg)
    
    sql = """
    INSERT INTO project_audit_log (project_id, user_id, action, entity_type, entity_id, details)
    VALUES (%s, %s, %s, %s, %s, %s)
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project, user_id, action, entity_type, entity_id, Json(details) if details else None))
    pg.commit()


def get_project_audit_log(
    pg: PGConnection,
    project: str,
    limit: int = 50,
    action_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Obtiene el historial de acciones de un proyecto."""
    ensure_project_members_table(pg)
    
    sql = """
    SELECT id, user_id, action, entity_type, entity_id, details, created_at
      FROM project_audit_log
     WHERE project_id = %s
       AND (%s IS NULL OR action = %s)
     ORDER BY created_at DESC
     LIMIT %s
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project, action_filter, action_filter, limit))
        rows = cur.fetchall()
    
    return [
        {
            "id": r[0],
            "user_id": r[1],
            "action": r[2],
            "entity_type": r[3],
            "entity_id": r[4],
            "details": r[5],
            "created_at": r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]


# =============================================================================
# ETAPA 0 (PREPARACIÓN) - GATING HELPERS
# =============================================================================

Stage0Scope = str  # 'ingest' | 'analyze' | 'both'


def stage0_get_status(pg: PGConnection, project: str) -> Dict[str, Any]:
    """Retorna checklist de Etapa 0 basado en tablas stage0_*.

    Nota: PII no se considera aquí (solo actores anonimizados + consentimientos).
    """
    with pg.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM stage0_protocols WHERE project_id = %s", (project,))
        row = cur.fetchone()
        protocols = int(row[0]) if row else 0

        cur.execute("SELECT COUNT(*) FROM stage0_actors WHERE project_id = %s", (project,))
        row = cur.fetchone()
        actors = int(row[0]) if row else 0

        cur.execute(
            """
            SELECT COUNT(*)
              FROM stage0_actors a
             WHERE a.project_id = %s
               AND NOT EXISTS (
                 SELECT 1
                   FROM stage0_consents c
                  WHERE c.project_id = a.project_id
                    AND c.actor_id = a.actor_id
                    AND c.revoked_at IS NULL
               )
            """,
            (project,),
        )
        row = cur.fetchone()
        actors_missing_consent = int(row[0]) if row else 0

        cur.execute("SELECT COUNT(*) FROM stage0_sampling_criteria WHERE project_id = %s", (project,))
        row = cur.fetchone()
        sampling = int(row[0]) if row else 0

        cur.execute("SELECT COUNT(*) FROM stage0_analysis_plans WHERE project_id = %s", (project,))
        row = cur.fetchone()
        plans = int(row[0]) if row else 0

    protocol_ok = protocols > 0
    actors_ok = actors > 0
    consents_ok = actors > 0 and actors_missing_consent == 0
    sampling_ok = sampling > 0
    plan_ok = plans > 0

    ready = protocol_ok and actors_ok and consents_ok and sampling_ok and plan_ok

    return {
        "ready": ready,
        "checks": {
            "protocol": protocol_ok,
            "actors": actors_ok,
            "consents": consents_ok,
            "sampling": sampling_ok,
            "analysis_plan": plan_ok,
        },
        "counters": {
            "protocols": protocols,
            "actors": actors,
            "actors_missing_consent": actors_missing_consent,
            "sampling_versions": sampling,
            "plan_versions": plans,
        },
    }


def stage0_get_active_override(
    pg: PGConnection,
    project: str,
    scope: str,
) -> Optional[Dict[str, Any]]:
    """Retorna override aprobado y vigente (si existe) para el scope solicitado."""
    allowed_scopes = {"ingest", "analyze", "both"}
    if scope not in allowed_scopes:
        raise ValueError(f"Invalid stage0 scope: {scope}")

    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT override_id, scope, reason_category, reason_details, requested_by, decided_by, decided_at, expires_at
              FROM stage0_override_requests
             WHERE project_id = %s
               AND status = 'approved'
               AND (expires_at IS NULL OR expires_at > NOW())
               AND (scope = %s OR scope = 'both')
             ORDER BY decided_at DESC NULLS LAST
             LIMIT 1
            """,
            (project, scope),
        )
        row = cur.fetchone()

    if row is None:
        return None

    return {
        "override_id": row[0],
        "scope": row[1],
        "reason_category": row[2],
        "reason_details": row[3],
        "requested_by": row[4],
        "approved_by": row[5],
        "approved_at": row[6].isoformat() if row[6] else None,
        "expires_at": row[7].isoformat() if row[7] else None,
    }


def stage0_require_ready_or_override(
    pg: PGConnection,
    project: str,
    scope: str,
    user_id: str,
    *,
    log_override_use: bool = True,
) -> Dict[str, Any]:
    """Enforce Etapa 0 readiness, otherwise require an approved override.

    Returns dict with keys: allowed(bool), ready(bool), override(optional), status.
    Raises PermissionError when blocked.
    """
    status = stage0_get_status(pg, project)
    if status.get("ready"):
        return {"allowed": True, "ready": True, "override": None, "status": status}

    override = stage0_get_active_override(pg, project, scope)
    if override is None:
        raise PermissionError(
            "Etapa 0 no está completa para este proyecto. "
            "Completa protocolo/actores/consentimientos/muestreo/plan o solicita override (doble validación)."
        )

    if log_override_use:
        try:
            log_project_action(
                pg,
                project=project,
                user_id=user_id,
                action="stage0.override.used",
                entity_type="stage0_override_requests",
                entity_id=str(override.get("override_id")),
                details={"scope": scope, "reason_category": override.get("reason_category")},
            )
        except Exception:
            # Never block the primary operation due to audit logging failure.
            pass

    return {"allowed": True, "ready": False, "override": override, "status": status}


# =============================================================================
# CÓDIGOS CANDIDATOS - Sistema de Consolidación de Códigos
# =============================================================================

CandidateCodeRow = Tuple[
    str,  # project_id
    str,  # codigo
    Optional[str],  # cita
    Optional[str],  # fragmento_id
    Optional[str],  # archivo
    str,  # fuente_origen: 'llm', 'manual', 'discovery', 'semantic_suggestion'
    Optional[str],  # fuente_detalle
    Optional[float],  # score_confianza
    str,  # estado: 'pendiente', 'validado', 'rechazado', 'fusionado'
    Optional[str],  # memo
]


_candidate_codes_table_ensured = False
_candidate_codes_table_lock = threading.Lock()
_candidate_codes_table_promote_migrated = False


# =============================================================================
# AI Runner: Merge Plans (audit by run_id)
# =============================================================================

_ai_merge_plans_table_ensured = False
_ai_merge_plans_table_lock = threading.Lock()


def ensure_ai_merge_plans_table(pg: PGConnection) -> None:
    """Tabla durable para planes/propuestas de auto-merge (runner IA).

    Objetivo: auditoría reproducible por `run_id`.
    Nota: UUIDs se generan en Python (compat Azure PG).
    """
    global _ai_merge_plans_table_ensured
    if _ai_merge_plans_table_ensured:
        return

    with _ai_merge_plans_table_lock:
        if _ai_merge_plans_table_ensured:
            return

        sql = """
        CREATE TABLE IF NOT EXISTS ai_merge_plans (
            run_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            created_by TEXT,
            source TEXT NOT NULL DEFAULT 'ui',
            threshold FLOAT,
            input_count INT,
            pairs_count INT,
            input_codigos JSONB,
            pairs JSONB,
            meta JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_amp_project_created ON ai_merge_plans(project_id, created_at DESC);
        """
        with pg.cursor() as cur:
            cur.execute(sql)
        pg.commit()

        _ai_merge_plans_table_ensured = True


def insert_ai_merge_plan(
    pg: PGConnection,
    *,
    run_id: str,
    project_id: str,
    created_by: Optional[str],
    source: str,
    threshold: float,
    input_codigos: List[str],
    pairs: List[Dict[str, Any]],
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """Inserta un plan de merge IA (propuesta) para auditoría."""
    ensure_ai_merge_plans_table(pg)

    with pg.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ai_merge_plans (
                run_id, project_id, created_by, source, threshold,
                input_count, pairs_count, input_codigos, pairs, meta
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                project_id,
                created_by,
                (source or "ui"),
                float(threshold),
                int(len(input_codigos)),
                int(len(pairs)),
                Json(input_codigos),
                Json(pairs),
                Json(meta) if meta is not None else None,
            ),
        )
    pg.commit()


def get_ai_merge_plan(
    pg: PGConnection,
    *,
    project_id: str,
    run_id: str,
) -> Optional[Dict[str, Any]]:
    """Obtiene un plan por run_id."""
    ensure_ai_merge_plans_table(pg)
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT run_id, project_id, created_by, source, threshold,
                   input_count, pairs_count, input_codigos, pairs, meta, created_at
              FROM ai_merge_plans
             WHERE project_id = %s AND run_id = %s
            """,
            (project_id, run_id),
        )
        row = cur.fetchone()
    pg.commit()
    if not row:
        return None

    created_at = row[10]
    return {
        "run_id": row[0],
        "project": row[1],
        "created_by": row[2],
        "source": row[3],
        "threshold": float(row[4]) if row[4] is not None else None,
        "input_count": int(row[5] or 0),
        "pairs_count": int(row[6] or 0),
        "input_codigos": row[7] or [],
        "pairs": row[8] or [],
        "meta": row[9],
        "created_at": created_at.isoformat().replace("+00:00", "Z") if created_at else None,
    }


def list_ai_merge_plans(
    pg: PGConnection,
    *,
    project_id: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Lista planes recientes (resumen) para un proyecto."""
    ensure_ai_merge_plans_table(pg)
    safe_limit = max(1, min(200, int(limit)))
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT run_id, created_by, source, threshold, input_count, pairs_count, created_at
              FROM ai_merge_plans
             WHERE project_id = %s
             ORDER BY created_at DESC
             LIMIT %s
            """,
            (project_id, safe_limit),
        )
        rows = cur.fetchall()
    pg.commit()
    out: List[Dict[str, Any]] = []
    for r in rows:
        created_at = r[6]
        out.append(
            {
                "run_id": r[0],
                "created_by": r[1],
                "source": r[2],
                "threshold": float(r[3]) if r[3] is not None else None,
                "input_count": int(r[4] or 0),
                "pairs_count": int(r[5] or 0),
                "created_at": created_at.isoformat().replace("+00:00", "Z") if created_at else None,
            }
        )
    return out


def ensure_api_idempotency_table(pg: PGConnection) -> None:
    """Tabla mínima para idempotencia de requests (reintentos seguros desde frontend)."""
    sql = """
    CREATE TABLE IF NOT EXISTS api_idempotency (
        project_id TEXT NOT NULL,
        endpoint TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        response_json JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (project_id, endpoint, idempotency_key)
    );
    """
    with pg.cursor() as cur:
        cur.execute(sql)
    pg.commit()


def get_idempotency_response(
    pg: PGConnection,
    project_id: str,
    endpoint: str,
    idempotency_key: str,
) -> Optional[Dict[str, Any]]:
    if not idempotency_key:
        return None
    ensure_api_idempotency_table(pg)
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT response_json
            FROM api_idempotency
            WHERE project_id = %s AND endpoint = %s AND idempotency_key = %s
            """,
            (project_id, endpoint, idempotency_key),
        )
        row = cur.fetchone()
    if not row:
        return None
    return row[0]


def store_idempotency_response(
    pg: PGConnection,
    project_id: str,
    endpoint: str,
    idempotency_key: str,
    response: Dict[str, Any],
) -> None:
    if not idempotency_key:
        return
    import json

    ensure_api_idempotency_table(pg)
    payload = json.dumps(response, ensure_ascii=False)
    with pg.cursor() as cur:
        cur.execute(
            """
            INSERT INTO api_idempotency(project_id, endpoint, idempotency_key, response_json)
            VALUES (%s, %s, %s, %s::jsonb)
            ON CONFLICT (project_id, endpoint, idempotency_key)
            DO NOTHING
            """,
            (project_id, endpoint, idempotency_key, payload),
        )
    pg.commit()


def ensure_candidate_codes_table(pg: PGConnection) -> None:
    """Crea la tabla de códigos candidatos si no existe."""
    global _candidate_codes_table_ensured
    global _candidate_codes_table_promote_migrated
    if _candidate_codes_table_ensured:
        # Even if table exists, ensure we apply schema migrations (idempotent).
        if not _candidate_codes_table_promote_migrated:
            with _candidate_codes_table_lock:
                if not _candidate_codes_table_promote_migrated:
                    with pg.cursor() as cur:
                        cur.execute(
                            """
                            ALTER TABLE codigos_candidatos ADD COLUMN IF NOT EXISTS promovido_por TEXT;
                            ALTER TABLE codigos_candidatos ADD COLUMN IF NOT EXISTS promovido_en TIMESTAMPTZ;
                            CREATE INDEX IF NOT EXISTS ix_cc_project_promovido_en ON codigos_candidatos(project_id, promovido_en);
                            """
                        )
                    pg.commit()
                    _candidate_codes_table_promote_migrated = True
        return

    with _candidate_codes_table_lock:
        if _candidate_codes_table_ensured:
            return

    sql = """
    CREATE TABLE IF NOT EXISTS codigos_candidatos (
        id SERIAL PRIMARY KEY,
        project_id TEXT NOT NULL,
        codigo TEXT NOT NULL,
        cita TEXT,
        fragmento_id TEXT,
        archivo TEXT,
        fuente_origen TEXT NOT NULL,
        fuente_detalle TEXT,
        score_confianza FLOAT,
        estado TEXT NOT NULL DEFAULT 'pendiente',
        validado_por TEXT,
        validado_en TIMESTAMPTZ,
        fusionado_a TEXT,
        memo TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(project_id, codigo, fragmento_id)
    );
    CREATE INDEX IF NOT EXISTS ix_cc_project_estado ON codigos_candidatos(project_id, estado);
    CREATE INDEX IF NOT EXISTS ix_cc_project_fuente ON codigos_candidatos(project_id, fuente_origen);
    CREATE INDEX IF NOT EXISTS ix_cc_score ON codigos_candidatos(score_confianza DESC NULLS LAST);
    CREATE INDEX IF NOT EXISTS ix_cc_created_at ON codigos_candidatos(created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_cc_archivo ON codigos_candidatos(archivo);
    CREATE INDEX IF NOT EXISTS ix_cc_codigo ON codigos_candidatos(codigo);
    ALTER TABLE codigos_candidatos ADD COLUMN IF NOT EXISTS code_id BIGINT;
    CREATE INDEX IF NOT EXISTS ix_cc_project_code_id ON codigos_candidatos(project_id, code_id) WHERE code_id IS NOT NULL;
    """
    with pg.cursor() as cur:
        cur.execute(sql)
    pg.commit()

    _candidate_codes_table_ensured = True

    # Apply schema migrations (idempotent)
    if not _candidate_codes_table_promote_migrated:
        with _candidate_codes_table_lock:
            if not _candidate_codes_table_promote_migrated:
                with pg.cursor() as cur:
                    cur.execute(
                        """
                        ALTER TABLE codigos_candidatos ADD COLUMN IF NOT EXISTS promovido_por TEXT;
                        ALTER TABLE codigos_candidatos ADD COLUMN IF NOT EXISTS promovido_en TIMESTAMPTZ;
                        CREATE INDEX IF NOT EXISTS ix_cc_project_promovido_en ON codigos_candidatos(project_id, promovido_en);
                        """
                    )
                pg.commit()
                _candidate_codes_table_promote_migrated = True


# =============================================================================
# LINK PREDICTIONS TABLE (Codificación Axial)
# =============================================================================

_link_predictions_table_created = False


def ensure_link_predictions_table(pg: PGConnection) -> None:
    """
    Crea la tabla link_predictions para almacenar predicciones de relaciones axiales.
    
    Las predicciones de Link Prediction son hipótesis de relaciones entre códigos,
    no códigos con citas. Pertenecen metodológicamente a la Codificación Axial.
    
    Estados: pendiente, validado, rechazado
    Al validar: se crea la relación axial en Neo4j
    """
    global _link_predictions_table_created
    if _link_predictions_table_created:
        return
    
    with pg.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS link_predictions (
                id SERIAL PRIMARY KEY,
                project_id TEXT NOT NULL,
                source_code TEXT NOT NULL,
                target_code TEXT NOT NULL,
                relation_type TEXT NOT NULL DEFAULT 'asociado_con',
                algorithm TEXT NOT NULL DEFAULT 'common_neighbors',
                score FLOAT NOT NULL DEFAULT 0.0,
                rank INTEGER,
                estado TEXT NOT NULL DEFAULT 'pendiente',
                validado_por TEXT,
                validado_en TIMESTAMPTZ,
                memo TEXT,
                neo4j_sync_status TEXT,
                neo4j_sync_error TEXT,
                neo4j_synced_at TIMESTAMPTZ,
                reopened_at TIMESTAMPTZ,
                reopened_by TEXT,
                reopen_reason TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                
                CONSTRAINT uq_lp_project_codes UNIQUE (project_id, source_code, target_code, algorithm)
            );

            ALTER TABLE link_predictions ADD COLUMN IF NOT EXISTS neo4j_sync_status TEXT;
            ALTER TABLE link_predictions ADD COLUMN IF NOT EXISTS neo4j_sync_error TEXT;
            ALTER TABLE link_predictions ADD COLUMN IF NOT EXISTS neo4j_synced_at TIMESTAMPTZ;
            ALTER TABLE link_predictions ADD COLUMN IF NOT EXISTS reopened_at TIMESTAMPTZ;
            ALTER TABLE link_predictions ADD COLUMN IF NOT EXISTS reopened_by TEXT;
            ALTER TABLE link_predictions ADD COLUMN IF NOT EXISTS reopen_reason TEXT;
            
            CREATE INDEX IF NOT EXISTS ix_lp_project_estado 
                ON link_predictions(project_id, estado);
            CREATE INDEX IF NOT EXISTS ix_lp_project_source 
                ON link_predictions(project_id, source_code);
            CREATE INDEX IF NOT EXISTS ix_lp_project_target 
                ON link_predictions(project_id, target_code);
            CREATE INDEX IF NOT EXISTS ix_lp_project_sync_status
                ON link_predictions(project_id, neo4j_sync_status);
            """
        )
    pg.commit()
    _link_predictions_table_created = True


def insert_link_predictions(
    pg: PGConnection,
    predictions: List[Dict[str, Any]],
) -> int:
    """
    Inserta predicciones de relaciones en la tabla link_predictions.
    
    Args:
        pg: Conexión PostgreSQL
        predictions: Lista de dicts con:
            - project_id, source_code, target_code
            - relation_type (default: 'asociado_con')
            - algorithm (ej: 'common_neighbors', 'adamic_adar')
            - score, rank (opcionales)
            - memo (opcional)
    
    Returns:
        Número de predicciones insertadas
    """
    ensure_link_predictions_table(pg)
    if not predictions:
        return 0
    
    sql = """
    INSERT INTO link_predictions (
        project_id, source_code, target_code, relation_type,
        algorithm, score, rank, memo
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (project_id, source_code, target_code, algorithm) DO UPDATE SET
        score = EXCLUDED.score,
        rank = EXCLUDED.rank,
        memo = COALESCE(EXCLUDED.memo, link_predictions.memo),
        updated_at = NOW()
    """
    
    count = 0
    with pg.cursor() as cur:
        for p in predictions:
            source = str(p.get("source_code") or "").strip()
            target = str(p.get("target_code") or "").strip()
            if not source or not target or source == target:
                continue
            # Canonicalize as undirected pair to avoid A→B vs B→A duplicates.
            if source > target:
                source, target = target, source
            cur.execute(
                sql,
                (
                    str(p.get("project_id", "default") or "default").strip() or "default",
                    source,
                    target,
                    str(p.get("relation_type", "asociado_con") or "asociado_con").strip()
                    or "asociado_con",
                    str(p.get("algorithm", "common_neighbors") or "common_neighbors").strip()
                    or "common_neighbors",
                    p.get("score", 0.0),
                    p.get("rank"),
                    p.get("memo"),
                ),
            )
            count += 1
    pg.commit()
    return count


def get_link_predictions(
    pg: PGConnection,
    project_id: str,
    estado: Optional[str] = None,
    algorithm: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Obtiene predicciones de relaciones para un proyecto.
    
    Args:
        pg: Conexión PostgreSQL
        project_id: ID del proyecto
        estado: Filtrar por estado (pendiente, validado, rechazado)
        limit: Máximo de resultados
        offset: Desplazamiento para paginación
    
    Returns:
        Lista de predicciones
    """
    ensure_link_predictions_table(pg)
    
    sql = """
    SELECT id, project_id, source_code, target_code, relation_type,
           algorithm, score, rank, estado, validado_por, validado_en,
           memo, created_at, updated_at
    FROM link_predictions
    WHERE project_id = %s
    """
    params: List[Any] = [project_id]
    
    if estado:
        sql += " AND estado = %s"
        params.append(estado)

    if algorithm:
        sql += " AND algorithm = %s"
        params.append(algorithm)

    sql += " ORDER BY score DESC, created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    
    with pg.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    
    return [
        {
            "id": r[0],
            "project_id": r[1],
            "source_code": r[2],
            "target_code": r[3],
            "relation_type": r[4],
            "algorithm": r[5],
            "score": r[6],
            "rank": r[7],
            "estado": r[8],
            "validado_por": r[9],
            "validado_en": r[10].isoformat() if r[10] else None,
            "memo": r[11],
            "created_at": r[12].isoformat() if r[12] else None,
            "updated_at": r[13].isoformat() if r[13] else None,
        }
        for r in rows
    ]


def count_link_predictions(
    pg: PGConnection,
    project_id: str,
    estado: Optional[str] = None,
    algorithm: Optional[str] = None,
) -> int:
    """
    Cuenta predicciones de relaciones para un proyecto (con filtros opcionales).
    """
    ensure_link_predictions_table(pg)

    sql = "SELECT COUNT(*) FROM link_predictions WHERE project_id = %s"
    params: List[Any] = [project_id]

    if estado:
        sql += " AND estado = %s"
        params.append(estado)

    if algorithm:
        sql += " AND algorithm = %s"
        params.append(algorithm)

    with pg.cursor() as cur:
        cur.execute(sql, tuple(params))
        r = cur.fetchone()
        return int(r[0] or 0) if r else 0


def get_link_predictions_stats(
    pg: PGConnection,
    project_id: str,
) -> Dict[str, Any]:
    """
    Obtiene estadísticas de predicciones de relaciones.
    """
    ensure_link_predictions_table(pg)
    
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT estado, COUNT(*) 
            FROM link_predictions 
            WHERE project_id = %s 
            GROUP BY estado
            """,
            (project_id,),
        )
        totals = {r[0]: r[1] for r in cur.fetchall()}
        
        cur.execute(
            """
            SELECT algorithm, COUNT(*) 
            FROM link_predictions 
            WHERE project_id = %s 
            GROUP BY algorithm
            """,
            (project_id,),
        )
        by_algorithm = {r[0]: r[1] for r in cur.fetchall()}
    
    return {
        "totals": totals,
        "by_algorithm": by_algorithm,
        "total": sum(totals.values()),
    }


def get_closed_link_prediction_pairs(
    pg: PGConnection,
    *,
    project_id: str,
    estados: Sequence[str] = ("validado", "rechazado"),
) -> set[tuple[str, str]]:
    """Devuelve pares (Codigo↔Codigo) cerrados para filtrar sugerencias repetidas.

    Nota: se normaliza como par no dirigido (A,B) ordenado lexicográficamente.
    """
    ensure_link_predictions_table(pg)
    estados_clean = [str(s).strip() for s in (estados or []) if str(s).strip()]
    if not estados_clean:
        return set()

    sql = """
    SELECT source_code, target_code
      FROM link_predictions
     WHERE project_id = %s
       AND estado = ANY(%s)
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project_id, estados_clean))
        rows = cur.fetchall() or []

    out: set[tuple[str, str]] = set()
    for a, b in rows:
        sa = str(a or "").strip()
        sb = str(b or "").strip()
        if not sa or not sb:
            continue
        if sa <= sb:
            out.add((sa, sb))
        else:
            out.add((sb, sa))
    return out


def update_link_prediction_estado(
    pg: PGConnection,
    prediction_id: int,
    estado: str,
    validado_por: Optional[str] = None,
    memo: Optional[str] = None,
    relation_type: Optional[str] = None,
) -> bool:
    """
    Actualiza el estado de una predicción.
    
    Args:
        pg: Conexión PostgreSQL
        prediction_id: ID de la predicción
        estado: Nuevo estado (pendiente, validado, rechazado)
        validado_por: Usuario que valida
        memo: Nota opcional
    
    Returns:
        True si se actualizó
    """
    ensure_link_predictions_table(pg)
    
    with pg.cursor() as cur:
        cur.execute(
            """
            UPDATE link_predictions
            SET estado = %s,
                relation_type = COALESCE(%s, relation_type),
                validado_por = COALESCE(%s, validado_por),
                validado_en = CASE WHEN %s IN ('validado', 'rechazado') THEN NOW() ELSE validado_en END,
                memo = COALESCE(%s, memo),
                updated_at = NOW()
            WHERE id = %s
            RETURNING id
            """,
            (estado, relation_type, validado_por, estado, memo, prediction_id),
        )
        result = cur.fetchone()
    pg.commit()
    return result is not None


def batch_update_link_predictions_estado(
    pg: PGConnection,
    project_id: str,
    prediction_ids: List[int],
    estado: str,
    validado_por: Optional[str] = None,
) -> int:
    """
    Actualiza el estado de múltiples predicciones.
    """
    ensure_link_predictions_table(pg)
    if not prediction_ids:
        return 0
    
    with pg.cursor() as cur:
        cur.execute(
            """
            UPDATE link_predictions
            SET estado = %s,
                validado_por = COALESCE(%s, validado_por),
                validado_en = CASE WHEN %s IN ('validado', 'rechazado') THEN NOW() ELSE validado_en END,
                updated_at = NOW()
            WHERE project_id = %s AND id = ANY(%s)
            """,
            (estado, validado_por, estado, project_id, prediction_ids),
        )
        count = cur.rowcount
    pg.commit()
    return count


def get_link_predictions_by_ids(
    pg: PGConnection,
    project_id: str,
    prediction_ids: List[int],
) -> List[Dict[str, Any]]:
    """
    Obtiene predicciones por IDs (filtradas por proyecto).
    """
    ensure_link_predictions_table(pg)
    if not prediction_ids:
        return []

    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT id, project_id, source_code, target_code, relation_type,
                   algorithm, score, rank, estado, validado_por, validado_en,
                   memo, created_at, updated_at
            FROM link_predictions
            WHERE project_id = %s AND id = ANY(%s)
            """,
            (project_id, prediction_ids),
        )
        rows = cur.fetchall()

    return [
        {
            "id": r[0],
            "project_id": r[1],
            "source_code": r[2],
            "target_code": r[3],
            "relation_type": r[4],
            "algorithm": r[5],
            "score": r[6],
            "rank": r[7],
            "estado": r[8],
            "validado_por": r[9],
            "validado_en": r[10].isoformat() if r[10] else None,
            "memo": r[11],
            "created_at": r[12].isoformat() if r[12] else None,
            "updated_at": r[13].isoformat() if r[13] else None,
        }
        for r in rows
    ]


def get_link_prediction_by_id(
    pg: PGConnection,
    prediction_id: int,
) -> Optional[Dict[str, Any]]:
    """
    Obtiene una predicción por ID.
    """
    ensure_link_predictions_table(pg)
    
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT id, project_id, source_code, target_code, relation_type,
                   algorithm, score, rank, estado, validado_por, validado_en,
                   memo, created_at, updated_at
            FROM link_predictions
            WHERE id = %s
            """,
            (prediction_id,),
        )
        r = cur.fetchone()
    
    if not r:
        return None
    
    return {
        "id": r[0],
        "project_id": r[1],
        "source_code": r[2],
        "target_code": r[3],
        "relation_type": r[4],
        "algorithm": r[5],
        "score": r[6],
        "rank": r[7],
        "estado": r[8],
        "validado_por": r[9],
        "validado_en": r[10].isoformat() if r[10] else None,
        "memo": r[11],
        "created_at": r[12].isoformat() if r[12] else None,
        "updated_at": r[13].isoformat() if r[13] else None,
    }


def get_link_prediction_id_by_key(
    pg: PGConnection,
    *,
    project_id: str,
    source_code: str,
    target_code: str,
    algorithm: str,
) -> Optional[int]:
    """Obtiene prediction_id por clave única (project_id, source_code, target_code, algorithm).

    Nota: se normaliza el par (Codigo↔Codigo) como no dirigido (A,B) ordenado lexicográficamente.
    """
    ensure_link_predictions_table(pg)
    a = str(source_code or "").strip()
    b = str(target_code or "").strip()
    if not a or not b:
        return None
    if a > b:
        a, b = b, a
    algo = str(algorithm or "common_neighbors").strip() or "common_neighbors"

    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM link_predictions
            WHERE project_id = %s AND source_code = %s AND target_code = %s AND algorithm = %s
            """,
            (project_id, a, b, algo),
        )
        row = cur.fetchone()
    return int(row[0]) if row else None


# =============================================================================
# AXIAL AI ANALYSES TABLE (Auditable artifacts)
# =============================================================================

_axial_ai_analyses_table_created = False


def ensure_axial_ai_analyses_table(pg: PGConnection) -> None:
    """Crea tabla `axial_ai_analyses` para persistir análisis IA (axial) como artefactos auditables.

    Nota: esto NO crea relaciones en Neo4j; solo persiste el memo/artefacto y su provenance.
    El flujo humano de validación/promoción ocurre en endpoints separados.
    """
    global _axial_ai_analyses_table_created
    if _axial_ai_analyses_table_created:
        return

    with pg.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS axial_ai_analyses (
                id BIGSERIAL PRIMARY KEY,
                project_id TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'analyze_predictions',
                algorithm TEXT,
                algorithm_description TEXT,
                suggestions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                analysis_text TEXT,
                memo_statements JSONB,
                structured BOOLEAN NOT NULL DEFAULT FALSE,
                estado TEXT NOT NULL DEFAULT 'pendiente',
                created_by TEXT,
                reviewed_by TEXT,
                reviewed_en TIMESTAMPTZ,
                review_memo TEXT,
                epistemic_mode TEXT,
                prompt_version TEXT,
                llm_deployment TEXT,
                llm_api_version TEXT,
                evidence_schema_version INT NOT NULL DEFAULT 1,
                evidence_json JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            ALTER TABLE axial_ai_analyses ADD COLUMN IF NOT EXISTS evidence_schema_version INT NOT NULL DEFAULT 1;
            ALTER TABLE axial_ai_analyses ADD COLUMN IF NOT EXISTS evidence_json JSONB;

            CREATE INDEX IF NOT EXISTS ix_axial_ai_project_created
                ON axial_ai_analyses(project_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS ix_axial_ai_project_estado
                ON axial_ai_analyses(project_id, estado);
            """
        )
    pg.commit()

    # Best-effort: enforce allowed states without breaking legacy DBs.
    try:
        with pg.cursor() as cur:
            cur.execute(
                """
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'ck_axial_ai_analyses_estado'
                  ) THEN
                    ALTER TABLE axial_ai_analyses
                      ADD CONSTRAINT ck_axial_ai_analyses_estado
                      CHECK (estado IN ('pendiente','validado','rechazado'));
                  END IF;
                END $$;
                """
            )
        pg.commit()
    except Exception:
        pg.rollback()

    _axial_ai_analyses_table_created = True


def insert_axial_ai_analysis(
    pg: PGConnection,
    *,
    project_id: str,
    source_type: str,
    algorithm: Optional[str],
    algorithm_description: Optional[str],
    suggestions_json: Any,
    analysis_text: Optional[str],
    memo_statements: Any,
    structured: bool,
    estado: str = "pendiente",
    created_by: Optional[str] = None,
    reviewed_by: Optional[str] = None,
    review_memo: Optional[str] = None,
    epistemic_mode: Optional[str] = None,
    prompt_version: Optional[str] = None,
    llm_deployment: Optional[str] = None,
    llm_api_version: Optional[str] = None,
    evidence_schema_version: int = 1,
    evidence_json: Any = None,
) -> int:
    """Inserta un artefacto de análisis IA axial y retorna su ID."""
    ensure_axial_ai_analyses_table(pg)

    sql = """
    INSERT INTO axial_ai_analyses (
        project_id,
        source_type,
        algorithm,
        algorithm_description,
        suggestions_json,
        analysis_text,
        memo_statements,
        structured,
        estado,
        created_by,
        reviewed_by,
        review_memo,
        epistemic_mode,
        prompt_version,
        llm_deployment,
        llm_api_version,
        evidence_schema_version,
        evidence_json
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    RETURNING id
    """
    with pg.cursor() as cur:
        cur.execute(
            sql,
            (
                project_id,
                source_type,
                algorithm,
                algorithm_description,
                Json(suggestions_json) if suggestions_json is not None else Json([]),
                analysis_text,
                Json(memo_statements) if memo_statements is not None else None,
                bool(structured),
                estado,
                created_by,
                reviewed_by,
                review_memo,
                epistemic_mode,
                prompt_version,
                llm_deployment,
                llm_api_version,
                int(evidence_schema_version),
                Json(evidence_json) if evidence_json is not None else None,
            ),
        )
        row = cur.fetchone()
    pg.commit()
    return int(row[0]) if row else 0


def get_axial_ai_analysis_by_id(
    pg: PGConnection,
    *,
    project_id: str,
    analysis_id: int,
) -> Optional[Dict[str, Any]]:
    """Obtiene un artefacto por ID (scoped por proyecto)."""
    ensure_axial_ai_analyses_table(pg)

    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT id, project_id, source_type, algorithm, algorithm_description,
                   suggestions_json, analysis_text, memo_statements, structured,
                   estado, created_by, reviewed_by, reviewed_en, review_memo,
                   epistemic_mode, prompt_version, llm_deployment, llm_api_version,
                   evidence_schema_version, evidence_json,
                   created_at, updated_at
            FROM axial_ai_analyses
            WHERE project_id = %s AND id = %s
            """,
            (project_id, analysis_id),
        )
        r = cur.fetchone()

    if not r:
        return None

    return {
        "id": r[0],
        "project_id": r[1],
        "source_type": r[2],
        "algorithm": r[3],
        "algorithm_description": r[4],
        "suggestions_json": r[5],
        "analysis_text": r[6],
        "memo_statements": r[7],
        "structured": bool(r[8]),
        "estado": r[9],
        "created_by": r[10],
        "reviewed_by": r[11],
        "reviewed_en": r[12].isoformat() if r[12] else None,
        "review_memo": r[13],
        "epistemic_mode": r[14],
        "prompt_version": r[15],
        "llm_deployment": r[16],
        "llm_api_version": r[17],
        "evidence_schema_version": int(r[18]) if r[18] is not None else 1,
        "evidence_json": r[19],
        "created_at": r[20].isoformat() if r[20] else None,
        "updated_at": r[21].isoformat() if r[21] else None,
    }


def list_axial_ai_analyses(
    pg: PGConnection,
    *,
    project_id: str,
    estado: Optional[str] = None,
    source_type: Optional[str] = None,
    algorithm: Optional[str] = None,
    epistemic_mode: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    min_score: Optional[float] = None,
    has_evidence: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Lista artefactos IA (scoped por proyecto)."""
    ensure_axial_ai_analyses_table(pg)

    where = ["project_id = %s"]
    params: List[Any] = [project_id]
    if estado:
        where.append("estado = %s")
        params.append(estado)
    if source_type:
        where.append("source_type = %s")
        params.append(source_type)
    if algorithm:
        where.append("algorithm = %s")
        params.append(algorithm)
    if epistemic_mode:
        where.append("epistemic_mode = %s")
        params.append(epistemic_mode)
    if created_from:
        where.append("created_at >= %s")
        params.append(created_from)
    if created_to:
        where.append("created_at <= %s")
        params.append(created_to)
    if has_evidence is True:
        where.append("evidence_json IS NOT NULL")
    if has_evidence is False:
        where.append("evidence_json IS NULL")
    if min_score is not None:
        where.append(
            """
            COALESCE((
              SELECT MAX((x->>'score')::double precision)
              FROM jsonb_array_elements(suggestions_json) AS x
            ), 0) >= %s
            """.strip()
        )
        params.append(float(min_score))

    sql = f"""
    SELECT id, project_id, source_type, algorithm, algorithm_description,
           structured, estado, created_by, reviewed_by, reviewed_en,
           created_at, updated_at,
           epistemic_mode, prompt_version,
           evidence_schema_version,
           (evidence_json IS NOT NULL) AS has_evidence,
           COALESCE((evidence_json->'totals'->>'positive')::int, 0) AS evidence_positive,
           COALESCE((evidence_json->'totals'->>'negative')::int, 0) AS evidence_negative,
           COALESCE((
             SELECT MAX((x->>'score')::double precision)
             FROM jsonb_array_elements(suggestions_json) AS x
           ), 0) AS max_score
    FROM axial_ai_analyses
    WHERE {' AND '.join(where)}
    ORDER BY created_at DESC
    LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    with pg.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []

    return [
        {
            "id": r[0],
            "project_id": r[1],
            "source_type": r[2],
            "algorithm": r[3],
            "algorithm_description": r[4],
            "structured": bool(r[5]),
            "estado": r[6],
            "created_by": r[7],
            "reviewed_by": r[8],
            "reviewed_en": r[9].isoformat() if r[9] else None,
            "created_at": r[10].isoformat() if r[10] else None,
            "updated_at": r[11].isoformat() if r[11] else None,
            "epistemic_mode": r[12],
            "prompt_version": r[13],
            "evidence_schema_version": int(r[14]) if r[14] is not None else 1,
            "has_evidence": bool(r[15]),
            "evidence_positive": int(r[16] or 0),
            "evidence_negative": int(r[17] or 0),
            "max_score": float(r[18] or 0.0),
        }
        for r in rows
    ]


def count_axial_ai_analyses(
    pg: PGConnection,
    *,
    project_id: str,
    estado: Optional[str] = None,
    source_type: Optional[str] = None,
    algorithm: Optional[str] = None,
    epistemic_mode: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    min_score: Optional[float] = None,
    has_evidence: Optional[bool] = None,
) -> int:
    """Cuenta artefactos IA por proyecto/estado."""
    ensure_axial_ai_analyses_table(pg)

    where = ["project_id = %s"]
    params: List[Any] = [project_id]
    if estado:
        where.append("estado = %s")
        params.append(estado)
    if source_type:
        where.append("source_type = %s")
        params.append(source_type)
    if algorithm:
        where.append("algorithm = %s")
        params.append(algorithm)
    if epistemic_mode:
        where.append("epistemic_mode = %s")
        params.append(epistemic_mode)
    if created_from:
        where.append("created_at >= %s")
        params.append(created_from)
    if created_to:
        where.append("created_at <= %s")
        params.append(created_to)
    if has_evidence is True:
        where.append("evidence_json IS NOT NULL")
    if has_evidence is False:
        where.append("evidence_json IS NULL")
    if min_score is not None:
        where.append(
            """
            COALESCE((
              SELECT MAX((x->>'score')::double precision)
              FROM jsonb_array_elements(suggestions_json) AS x
            ), 0) >= %s
            """.strip()
        )
        params.append(float(min_score))

    with pg.cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) FROM axial_ai_analyses WHERE {' AND '.join(where)}",
            tuple(params),
        )
        row = cur.fetchone()
    return int(row[0]) if row else 0


def update_axial_ai_analysis_estado(
    pg: PGConnection,
    *,
    project_id: str,
    analysis_id: int,
    estado: str,
    reviewed_by: Optional[str] = None,
    review_memo: Optional[str] = None,
) -> bool:
    """Actualiza estado del artefacto IA (scoped por proyecto)."""
    ensure_axial_ai_analyses_table(pg)

    with pg.cursor() as cur:
        cur.execute(
            """
            UPDATE axial_ai_analyses
            SET estado = %s,
                reviewed_by = COALESCE(%s, reviewed_by),
                reviewed_en = CASE WHEN %s IS NULL THEN reviewed_en ELSE NOW() END,
                review_memo = COALESCE(%s, review_memo),
                updated_at = NOW()
            WHERE project_id = %s AND id = %s
            """,
            (estado, reviewed_by, reviewed_by, review_memo, project_id, analysis_id),
        )
        updated = cur.rowcount > 0
    pg.commit()
    return updated


def cleanup_axial_ai_analyses(
    pg: PGConnection,
    *,
    project_id: str,
    older_than_days: int,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Limpia artefactos IA axiales antiguos (retención).

    AX-AI-05: la tabla `axial_ai_analyses` puede crecer rápido; esta función
    permite aplicar retención por proyecto, por fecha de creación.
    """
    ensure_axial_ai_analyses_table(pg)

    from datetime import datetime, timedelta, timezone

    days = int(older_than_days)
    if days <= 0:
        raise ValueError("older_than_days debe ser > 0")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    with pg.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM axial_ai_analyses WHERE project_id = %s AND created_at < %s",
            (project_id, cutoff),
        )
        row = cur.fetchone()
        would_delete = int(row[0] or 0) if row else 0

        if dry_run:
            return {
                "project_id": project_id,
                "dry_run": True,
                "older_than_days": days,
                "cutoff": cutoff.isoformat(),
                "would_delete": would_delete,
            }

        cur.execute(
            "DELETE FROM axial_ai_analyses WHERE project_id = %s AND created_at < %s",
            (project_id, cutoff),
        )
        deleted = int(cur.rowcount or 0)
    pg.commit()

    return {
        "project_id": project_id,
        "dry_run": False,
        "older_than_days": days,
        "cutoff": cutoff.isoformat(),
        "deleted": deleted,
    }


def count_pending_candidates(pg: PGConnection, project_id: str) -> int:
    """
    Cuenta códigos candidatos pendientes de validación para un proyecto.
    
    Sprint 20: Gate de backlog para prevenir análisis con demasiados pendientes.
    
    Args:
        pg: Conexión PostgreSQL
        project_id: ID del proyecto
        
    Returns:
        Número de códigos candidatos con estado 'pendiente'
    """
    ensure_candidate_codes_table(pg)
    
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) 
            FROM codigos_candidatos 
            WHERE project_id = %s AND estado = 'pendiente'
            """,
            (project_id,),
        )
        result = cur.fetchone()
        return result[0] if result else 0


def insert_candidate_codes(
    pg: PGConnection,
    candidates: List[Dict[str, Any]],
    check_similar: bool = True,
    similarity_threshold: float = 0.85,
) -> int:
    """
    Inserta códigos candidatos en la bandeja de validación.
    
    Incluye normalización Pre-Hoc para detectar códigos similares existentes.
    
    Args:
        pg: Conexión PostgreSQL
        candidates: Lista de dicts con:
            - project_id, codigo, cita, fragmento_id, archivo
            - fuente_origen: 'llm', 'manual', 'discovery', 'semantic_suggestion'
            - fuente_detalle, score_confianza, estado, memo (opcionales)
        check_similar: Si True, busca códigos similares y marca en memo
        similarity_threshold: Umbral de similitud (default 0.85)
    
    Returns:
        Número de códigos insertados
    """
    ensure_candidate_codes_table(pg)
    if not candidates:
        return 0
    
    # Pre-Hoc: Normalización y detección de similares
    processed_candidates = candidates
    if check_similar and candidates:
        try:
            from .code_normalization import suggest_code_merge, get_existing_codes_for_project
            
            # Obtener proyecto del primer candidato
            project_id = candidates[0].get("project_id", "default")
            existing_codes = get_existing_codes_for_project(pg, project_id)
            
            if existing_codes:
                processed_candidates = suggest_code_merge(
                    candidates,
                    existing_codes,
                    threshold=similarity_threshold,
                )
        except ImportError:
            # Si code_normalization no está disponible, continuar sin normalización
            pass
        except Exception as e:
            # Log pero no fallar la inserción
            import structlog
            structlog.get_logger().warning(
                "insert_candidate_codes.normalization_error",
                error=str(e),
            )
    
    # Lookup code_id desde catalogo_codigos para cada candidato
    ensure_codes_catalog_table(pg)
    
    sql = """
    INSERT INTO codigos_candidatos (
        project_id, codigo, cita, fragmento_id, archivo,
        fuente_origen, fuente_detalle, score_confianza, estado, memo, code_id
    )
    VALUES %s
    ON CONFLICT (project_id, codigo, fragmento_id) DO UPDATE SET
        cita = EXCLUDED.cita,
        fuente_detalle = COALESCE(EXCLUDED.fuente_detalle, codigos_candidatos.fuente_detalle),
        score_confianza = COALESCE(EXCLUDED.score_confianza, codigos_candidatos.score_confianza),
        memo = COALESCE(EXCLUDED.memo, codigos_candidatos.memo),
        code_id = COALESCE(EXCLUDED.code_id, codigos_candidatos.code_id),
        updated_at = NOW()
    """
    
    rows = []
    for c in processed_candidates:
        if not c.get("codigo"):
            continue
        project_id = c.get("project_id", "default")
        codigo = c.get("codigo", "")
        # Lookup code_id if not provided
        code_id = c.get("code_id")
        if code_id is None:
            code_id = get_code_id_for_codigo(pg, project_id, codigo)
        rows.append((
            project_id,
            codigo,
            c.get("cita"),
            c.get("fragmento_id"),
            c.get("archivo"),
            c.get("fuente_origen", "manual"),
            c.get("fuente_detalle"),
            c.get("score_confianza"),
            c.get("estado", "pendiente"),
            c.get("memo"),
            code_id,
        ))
    
    with pg.cursor() as cur:
        execute_values(cur, sql, rows, page_size=100)
    pg.commit()
    return len(rows)


def list_candidate_codes(
    pg: PGConnection,
    project: str,
    estado: Optional[str] = None,
    fuente_origen: Optional[str] = None,
    archivo: Optional[str] = None,
    promovido: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
    sort_order: str = "desc",
) -> List[Dict[str, Any]]:
    """
    Lista códigos candidatos con filtros opcionales.
    
    Args:
        pg: Conexión PostgreSQL
        project: ID del proyecto
        estado: Filtrar por estado ('pendiente', 'validado', 'rechazado', 'fusionado')
        fuente_origen: Filtrar por origen ('llm', 'manual', 'discovery', 'semantic_suggestion')
        archivo: Filtrar por archivo de entrevista
        limit: Máximo de resultados
        offset: Offset para paginación
        sort_order: Orden de resultados ('asc' más antiguos primero, 'desc' más recientes primero)
    
    Returns:
        Lista de códigos candidatos
    """
    ensure_candidate_codes_table(pg)
    
    clauses = ["project_id = %s"]
    params: List[Any] = [project]
    
    if estado:
        clauses.append("estado = %s")
        params.append(estado)
    if fuente_origen:
        clauses.append("fuente_origen = %s")
        params.append(fuente_origen)
    if archivo:
        clauses.append("archivo = %s")
        params.append(archivo)

    # Filtro de promoción (útil para UX: validados por promover vs ya promovidos)
    if promovido is True:
        clauses.append("promovido_en IS NOT NULL")
    elif promovido is False:
        clauses.append("promovido_en IS NULL")
    
    where = " AND ".join(clauses)
    params.extend([limit, offset])
    
    order = "ASC" if sort_order.lower() == "asc" else "DESC"

    sql = f"""
    SELECT id, project_id, codigo, cita, fragmento_id, archivo,
           fuente_origen, fuente_detalle, score_confianza, estado,
           validado_por, validado_en, fusionado_a, memo,
           promovido_por, promovido_en,
           created_at
      FROM codigos_candidatos
     WHERE {where}
     ORDER BY created_at {order}
     LIMIT %s OFFSET %s
    """
    
    with pg.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    
    return [
        {
            "id": r[0],
            "project_id": r[1],
            "codigo": r[2],
            "cita": r[3],
            "fragmento_id": r[4],
            "archivo": r[5],
            "fuente_origen": r[6],
            "fuente_detalle": r[7],
            "score_confianza": r[8],
            "estado": r[9],
            "validado_por": r[10],
            "validado_en": r[11].isoformat() if r[11] else None,
            "fusionado_a": r[12],
            "memo": r[13],
            "promovido_por": r[14],
            "promovido_en": r[15].isoformat() if r[15] else None,
            "created_at": r[16].isoformat() if r[16] else None,
        }
        for r in rows
    ]


def list_candidate_codes_summary(
    pg: PGConnection,
    project: str,
    *,
    limit: int = 50,
    archivo: Optional[str] = None,
    include_states: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Resumen agregado de códigos candidatos (para muestreo teórico/insights).

    Nota: esto NO reemplaza el flujo de validación. Es un fallback para cuando
    aún no hay registros en analisis_codigos_abiertos.
    """
    ensure_candidate_codes_table(pg)

    states = include_states or ["pendiente", "validado"]
    if not states:
        states = ["pendiente", "validado"]

    clauses: List[str] = ["project_id = %s", "estado = ANY(%s)"]
    params: List[Any] = [project, states]
    if archivo and archivo.strip():
        clauses.append("archivo = %s")
        params.append(archivo.strip())
    where = " AND ".join(clauses)

    sql = f"""
    SELECT codigo,
           COUNT(*) AS citas,
           COUNT(DISTINCT fragmento_id) AS fragmentos,
           MIN(created_at) AS primera_cita,
           MAX(created_at) AS ultima_cita
      FROM codigos_candidatos
     WHERE {where}
       AND codigo IS NOT NULL
       AND codigo <> ''
     GROUP BY codigo
     ORDER BY MAX(created_at) DESC NULLS LAST, codigo ASC
     LIMIT %s
    """
    params.append(max(limit, 1))
    with pg.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [
        {
            "codigo": row[0],
            "citas": row[1],
            "fragmentos": row[2],
            "primera_cita": row[3].isoformat().replace("+00:00", "Z") if row[3] else None,
            "ultima_cita": row[4].isoformat().replace("+00:00", "Z") if row[4] else None,
        }
        for row in rows
    ]


def validate_candidate(
    pg: PGConnection,
    project_id: str,
    candidate_id: int,
    validated_by: Optional[str] = None,
    memo: Optional[str] = None,
) -> bool:
    """
    Marca un código candidato como validado.
    
    Args:
        pg: Conexión PostgreSQL
        candidate_id: ID del candidato
        validated_by: Usuario que validó
    
    Returns:
        True si se actualizó, False si no existe
    """

    def _candidate_audit_memo(estado: str, candidate_id: int, user_memo: Optional[str]) -> str:
        base = f"candidate_estado:{estado}; candidate_id:{candidate_id}"
        if user_memo is None or not str(user_memo).strip():
            return base
        return f"{base}\n{str(user_memo).strip()}"

    ensure_candidate_codes_table(pg)
    
    with pg.cursor() as cur:
        cur.execute(
            "SELECT codigo, memo FROM codigos_candidatos WHERE project_id = %s AND id = %s",
            (project_id, candidate_id),
        )
        before_row = cur.fetchone()

    if not before_row:
        pg.commit()
        return False

    before_codigo, before_memo = before_row[0], before_row[1]
    sql = """
    UPDATE codigos_candidatos
       SET estado = 'validado',
           validado_por = %s,
           validado_en = NOW(),
           memo = COALESCE(%s, memo),
           updated_at = NOW()
     WHERE project_id = %s AND id = %s
    """
    with pg.cursor() as cur:
        cur.execute(sql, (validated_by, memo, project_id, candidate_id))
        affected = cur.rowcount

    # If it was already validated, treat as success (idempotent).
    # This prevents UX dead-ends where a user validated earlier but never promoted.
    if affected <= 0:
        with pg.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM codigos_candidatos WHERE project_id = %s AND id = %s AND estado = 'validado'",
                (project_id, candidate_id),
            )
            exists_validated = cur.fetchone() is not None
        pg.commit()
        return exists_validated

    # Persist the state change before best-effort audit logging to avoid
    # rolling back a successful validation if logging fails.
    pg.commit()

    try:
        log_code_version(
            pg,
            project=project_id,
            codigo=str(before_codigo),
            accion="candidate_validate",
            memo_anterior=before_memo,
            memo_nuevo=_candidate_audit_memo("validado", candidate_id, memo),
            changed_by=validated_by,
        )
    except Exception:
        # Never break the UX flow if auditing fails; reset transaction state.
        try:
            pg.rollback()
        except Exception:
            pass
        return True
    return True


def reject_candidate(
    pg: PGConnection,
    project_id: str,
    candidate_id: int,
    rejected_by: Optional[str] = None,
    memo: Optional[str] = None,
) -> bool:
    """
    Marca un código candidato como rechazado.
    
    Args:
        pg: Conexión PostgreSQL
        candidate_id: ID del candidato
        rejected_by: Usuario que rechazó
        memo: Razón del rechazo
    
    Returns:
        True si se actualizó, False si no existe
    """

    def _candidate_audit_memo(estado: str, candidate_id: int, user_memo: Optional[str]) -> str:
        base = f"candidate_estado:{estado}; candidate_id:{candidate_id}"
        if user_memo is None or not str(user_memo).strip():
            return base
        return f"{base}\n{str(user_memo).strip()}"

    ensure_candidate_codes_table(pg)
    
    with pg.cursor() as cur:
        cur.execute(
            "SELECT codigo, memo FROM codigos_candidatos WHERE project_id = %s AND id = %s",
            (project_id, candidate_id),
        )
        before_row = cur.fetchone()

    if not before_row:
        pg.commit()
        return False

    before_codigo, before_memo = before_row[0], before_row[1]
    sql = """
    UPDATE codigos_candidatos
       SET estado = 'rechazado',
           validado_por = %s,
           validado_en = NOW(),
           memo = COALESCE(%s, memo),
           updated_at = NOW()
     WHERE project_id = %s AND id = %s AND estado = 'pendiente'
    """
    with pg.cursor() as cur:
        cur.execute(sql, (rejected_by, memo, project_id, candidate_id))
        affected = cur.rowcount

    # Persist state change first; audit logging is best-effort.
    pg.commit()

    if affected > 0:
        try:
            log_code_version(
                pg,
                project=project_id,
                codigo=str(before_codigo),
                accion="candidate_reject",
                memo_anterior=before_memo,
                memo_nuevo=_candidate_audit_memo("rechazado", candidate_id, memo),
                changed_by=rejected_by,
            )
        except Exception:
            try:
                pg.rollback()
            except Exception:
                pass
    return affected > 0


def revert_validated_candidates_to_pending(
    pg: PGConnection,
    project_id: str,
    reverted_by: Optional[str] = None,
    memo: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Revierte candidatos validados a pendientes.

    Operación masiva para un proyecto específico.

    Nota: Esto solo modifica la tabla `codigos_candidatos`. No elimina/retrocede
    códigos ya promovidos a tablas definitivas.
    """
    ensure_candidate_codes_table(pg)

    if dry_run:
        with pg.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM codigos_candidatos WHERE project_id = %s AND estado = 'validado'",
                (project_id,),
            )
            row = cur.fetchone()
        pg.commit()
        return {
            "project": project_id,
            "dry_run": True,
            "would_revert": int(row[0] if row else 0),
        }

    def _bulk_revert_audit_memo(
        *,
        per_code_reverted: int,
        total_reverted: int,
        user_memo: Optional[str],
    ) -> str:
        base = (
            "candidate_estado:pendiente; revert_from:validado; "
            f"reverted_rows:{int(per_code_reverted)}; reverted_total:{int(total_reverted)}"
        )
        if user_memo is None or not str(user_memo).strip():
            return base
        return f"{base}\n{str(user_memo).strip()}"

    sql = """
    WITH updated AS (
        UPDATE codigos_candidatos
           SET estado = 'pendiente',
               validado_por = NULL,
               validado_en = NULL,
               memo = COALESCE(%s, memo),
               updated_at = NOW()
         WHERE project_id = %s
           AND estado = 'validado'
         RETURNING codigo
    )
    SELECT codigo, COUNT(*)::INT AS reverted_rows
      FROM updated
     GROUP BY codigo
    """

    with pg.cursor() as cur:
        cur.execute(sql, (memo, project_id))
        per_code_rows = cur.fetchall() or []

    total_reverted = sum(int(r[1] or 0) for r in per_code_rows)

    # Persist state change before best-effort audit logging.
    pg.commit()

    if total_reverted > 0:
        # Best-effort: register one history entry per affected code.
        try:
            ensure_code_versions_table(pg)
        except Exception:
            try:
                pg.rollback()
            except Exception:
                pass
        else:
            for codigo, per_code_reverted in per_code_rows:
                if not codigo:
                    continue
                try:
                    log_code_version(
                        pg,
                        project=project_id,
                        codigo=str(codigo),
                        accion="candidates_revert_validated",
                        memo_anterior=None,
                        memo_nuevo=_bulk_revert_audit_memo(
                            per_code_reverted=int(per_code_reverted or 0),
                            total_reverted=int(total_reverted),
                            user_memo=memo,
                        ),
                        changed_by=reverted_by,
                    )
                except Exception:
                    try:
                        pg.rollback()
                    except Exception:
                        pass

    return {
        "project": project_id,
        "dry_run": False,
        "reverted_count": int(total_reverted or 0),
        "reverted_by": reverted_by,
    }


def merge_candidates(
    pg: PGConnection,
    project_id: str,
    source_ids: List[int],
    target_codigo: str,
    merged_by: Optional[str] = None,
    memo: Optional[str] = None,
) -> int:
    """
    Fusiona múltiples códigos candidatos en uno.
    
    Args:
        pg: Conexión PostgreSQL
        source_ids: IDs de candidatos a fusionar
        target_codigo: Nombre del código destino
        merged_by: Usuario que realizó la fusión
    
    Returns:
        Número de candidatos fusionados
    """
    ensure_candidate_codes_table(pg)
    
    if not source_ids:
        return 0
    
    # Semántica recomendada (alineada a Fusión_duplicados):
    # 1) mover evidencia al target cuando no existe ya (mantiene estado)
    # 2) si la evidencia ya existe bajo el target, marcar como fusionado (dedupe)
    sql_move = """
    UPDATE codigos_candidatos src
       SET codigo = %s,
           fusionado_a = %s,
           updated_at = NOW()
     WHERE src.project_id = %s
       AND src.id = ANY(%s)
       AND src.estado IN ('pendiente', 'validado')
       AND lower(trim(src.codigo)) <> lower(trim(%s))
       AND NOT EXISTS (
           SELECT 1
             FROM codigos_candidatos tgt
            WHERE tgt.project_id = src.project_id
              AND tgt.codigo = %s
              AND tgt.fragmento_id = src.fragmento_id
       )
     RETURNING src.id, src.codigo, src.memo
    """

    sql_dedupe = """
    UPDATE codigos_candidatos src
       SET estado = 'fusionado',
           fusionado_a = %s,
           validado_por = %s,
           validado_en = NOW(),
           updated_at = NOW()
     WHERE src.project_id = %s
       AND src.id = ANY(%s)
       AND src.estado IN ('pendiente', 'validado')
       AND lower(trim(src.codigo)) <> lower(trim(%s))
       AND EXISTS (
           SELECT 1
             FROM codigos_candidatos tgt
            WHERE tgt.project_id = src.project_id
              AND tgt.codigo = %s
              AND tgt.fragmento_id = src.fragmento_id
       )
     RETURNING src.id, src.codigo, src.memo
    """

    with pg.cursor() as cur:
        cur.execute(
            sql_move,
            (target_codigo, target_codigo, project_id, source_ids, target_codigo, target_codigo),
        )
        moved_rows = cur.fetchall()

        cur.execute(
            sql_dedupe,
            (target_codigo, merged_by, project_id, source_ids, target_codigo, target_codigo),
        )
        dedup_rows = cur.fetchall()

    affected = len(moved_rows) + len(dedup_rows)

    if affected > 0:
        memo_suffix = ""
        if memo and str(memo).strip():
            memo_suffix = f"\nmerge_memo: {str(memo).strip()}"

        for _id, codigo, before_memo in moved_rows:
            try:
                log_code_version(
                    pg,
                    project=project_id,
                    codigo=str(codigo),
                    accion="candidate_merge_move",
                    memo_anterior=before_memo,
                    memo_nuevo=f"fusionado_a:{target_codigo}{memo_suffix}",
                    changed_by=merged_by,
                )
            except Exception:
                pass

        for _id, codigo, before_memo in dedup_rows:
            try:
                log_code_version(
                    pg,
                    project=project_id,
                    codigo=str(codigo),
                    accion="candidate_merge_dedupe",
                    memo_anterior=before_memo,
                    memo_nuevo=f"fusionado_a:{target_codigo}{memo_suffix}",
                    changed_by=merged_by,
                )
            except Exception:
                pass

    pg.commit()
    return affected


def preview_merge_candidates_by_ids(
    pg: PGConnection,
    project_id: str,
    source_ids: List[int],
    target_codigo: str,
) -> Dict[str, Any]:
    """Dry-run: estima cuántas filas se moverían vs deduplicarían (sin UPDATE)."""
    ensure_candidate_codes_table(pg)
    if not source_ids:
        return {"would_move": 0, "would_dedupe": 0, "would_merge": 0}

    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM codigos_candidatos src
            WHERE src.project_id = %s
              AND src.id = ANY(%s)
              AND src.estado IN ('pendiente','validado')
              AND lower(trim(src.codigo)) <> lower(trim(%s))
              AND NOT EXISTS (
                SELECT 1 FROM codigos_candidatos tgt
                WHERE tgt.project_id = src.project_id
                  AND tgt.codigo = %s
                  AND tgt.fragmento_id = src.fragmento_id
              )
            """,
            (project_id, source_ids, target_codigo, target_codigo),
        )
        would_move = int(cur.fetchone()[0] or 0)

        cur.execute(
            """
            SELECT COUNT(*)
            FROM codigos_candidatos src
            WHERE src.project_id = %s
              AND src.id = ANY(%s)
              AND src.estado IN ('pendiente','validado')
              AND lower(trim(src.codigo)) <> lower(trim(%s))
              AND EXISTS (
                SELECT 1 FROM codigos_candidatos tgt
                WHERE tgt.project_id = src.project_id
                  AND tgt.codigo = %s
                  AND tgt.fragmento_id = src.fragmento_id
              )
            """,
            (project_id, source_ids, target_codigo, target_codigo),
        )
        would_dedupe = int(cur.fetchone()[0] or 0)

    return {
        "would_move": would_move,
        "would_dedupe": would_dedupe,
        "would_merge": (would_move + would_dedupe),
    }


def merge_candidates_by_code(
    pg: PGConnection,
    project_id: str,
    source_codigo: str,
    target_codigo: str,
    merged_by: Optional[str] = None,
    memo: Optional[str] = None,
) -> int:
    """
    Fusiona todos los candidatos con un código específico hacia otro código.
    
    A diferencia de merge_candidates que usa IDs, esta función busca por nombre
    de código, lo que es más robusto para el auto-merge de duplicados.
    
    Args:
        pg: Conexión PostgreSQL
        project_id: ID del proyecto
        source_codigo: Nombre del código a fusionar (se busca case-insensitive)
        target_codigo: Nombre del código destino
        merged_by: Usuario que realizó la fusión
    
    Returns:
        Número de candidatos fusionados
    """
    ensure_candidate_codes_table(pg)
    
    _logger.info(
        "merge_candidates_by_code.start",
        extra={
            "project": project_id,
            "source": source_codigo,
            "target": target_codigo,
            "merged_by": merged_by,
        },
    )

    if not source_codigo or not target_codigo:
        _logger.warning(
            "merge_candidates_by_code.skipped_missing",
            extra={
                "project": project_id,
                "source": source_codigo,
                "target": target_codigo,
            },
        )
        return 0
    
    # Don't merge a code into itself
    if source_codigo.strip().lower() == target_codigo.strip().lower():
        _logger.warning(
            "merge_candidates_by_code.skipped_self",
            extra={
                "project": project_id,
                "source": source_codigo,
                "target": target_codigo,
            },
        )
        return 0
    
    use_unaccent = ensure_unaccent(pg)
    _logger.info(
        "merge_candidates_by_code.normalize",
        extra={
            "project": project_id,
            "use_unaccent": use_unaccent,
        },
    )
    # IMPORTANT: qualify with src. to avoid any ambiguity in UPDATE scope.
    normalize_col = "unaccent(lower(trim(src.codigo)))" if use_unaccent else "lower(trim(src.codigo))"
    normalize_param = "unaccent(lower(trim(%s)))" if use_unaccent else "lower(trim(%s))"

    # Paso 1: Reasignar citas al código destino (mantener estado)
    sql_move = f"""
    UPDATE codigos_candidatos src
       SET codigo = %s,
           fusionado_a = %s,
           updated_at = NOW()
     WHERE src.project_id = %s
       AND (src.codigo = %s OR {normalize_col} = {normalize_param})
       AND src.estado IN ('pendiente', 'validado')
       AND NOT EXISTS (
           SELECT 1
             FROM codigos_candidatos tgt
            WHERE tgt.project_id = src.project_id
              AND tgt.codigo = %s
              AND tgt.fragmento_id = src.fragmento_id
       )
     RETURNING src.id, src.codigo, src.memo
    """

    # Paso 2: Si ya existe la misma cita bajo el destino, marcar como fusionado
    sql_dedupe = f"""
    UPDATE codigos_candidatos src
       SET estado = 'fusionado',
           fusionado_a = %s,
           validado_por = %s,
           validado_en = NOW(),
           updated_at = NOW()
     WHERE src.project_id = %s
       AND (src.codigo = %s OR {normalize_col} = {normalize_param})
       AND src.estado IN ('pendiente', 'validado')
       AND EXISTS (
           SELECT 1
             FROM codigos_candidatos tgt
            WHERE tgt.project_id = src.project_id
              AND tgt.codigo = %s
              AND tgt.fragmento_id = src.fragmento_id
       )
     RETURNING src.id, src.codigo, src.memo
    """

    with pg.cursor() as cur:
        cur.execute(
            sql_move,
            (
                target_codigo,
                target_codigo,
                project_id,
                source_codigo,
                source_codigo,
                target_codigo,
            ),
        )
        moved_rows = cur.fetchall()
        moved_count = len(moved_rows)

        cur.execute(
            sql_dedupe,
            (
                target_codigo,
                merged_by,
                project_id,
                source_codigo,
                source_codigo,
                target_codigo,
            ),
        )
        dedup_rows = cur.fetchall()
        dedup_count = len(dedup_rows)

    affected = moved_count + dedup_count

    if affected > 0:
        memo_suffix = ""
        if memo and str(memo).strip():
            memo_suffix = f"\nmerge_memo: {str(memo).strip()}"

        for _id, codigo, before_memo in moved_rows:
            try:
                log_code_version(
                    pg,
                    project=project_id,
                    codigo=str(codigo),
                    accion="candidate_merge_move",
                    memo_anterior=before_memo,
                    memo_nuevo=f"fusionado_a:{target_codigo}{memo_suffix}",
                    changed_by=merged_by,
                )
            except Exception:
                pass

        for _id, codigo, before_memo in dedup_rows:
            try:
                log_code_version(
                    pg,
                    project=project_id,
                    codigo=str(codigo),
                    accion="candidate_merge_dedupe",
                    memo_anterior=before_memo,
                    memo_nuevo=f"fusionado_a:{target_codigo}{memo_suffix}",
                    changed_by=merged_by,
                )
            except Exception:
                pass

    pg.commit()
    return affected


def preview_merge_candidates_by_code(
    pg: PGConnection,
    project_id: str,
    source_codigo: str,
    target_codigo: str,
) -> Dict[str, Any]:
    """Dry-run: estima cuántas filas se moverían vs deduplicarían (sin UPDATE)."""
    ensure_candidate_codes_table(pg)
    if not source_codigo or not target_codigo:
        return {"would_move": 0, "would_dedupe": 0, "would_merge": 0}
    if source_codigo.strip().lower() == target_codigo.strip().lower():
        return {"would_move": 0, "would_dedupe": 0, "would_merge": 0, "skipped": "self"}

    use_unaccent = ensure_unaccent(pg)
    # IMPORTANT: qualify with src. to avoid any ambiguity in query scope.
    normalize_col = "unaccent(lower(trim(src.codigo)))" if use_unaccent else "lower(trim(src.codigo))"
    normalize_param = "unaccent(lower(trim(%s)))" if use_unaccent else "lower(trim(%s))"

    with pg.cursor() as cur:
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM codigos_candidatos src
            WHERE src.project_id = %s
              AND (src.codigo = %s OR {normalize_col} = {normalize_param})
              AND src.estado IN ('pendiente','validado')
              AND NOT EXISTS (
                SELECT 1 FROM codigos_candidatos tgt
                WHERE tgt.project_id = src.project_id
                  AND tgt.codigo = %s
                  AND tgt.fragmento_id = src.fragmento_id
              )
            """,
            (project_id, source_codigo, source_codigo, target_codigo),
        )
        would_move = int(cur.fetchone()[0] or 0)

        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM codigos_candidatos src
            WHERE src.project_id = %s
              AND (src.codigo = %s OR {normalize_col} = {normalize_param})
              AND src.estado IN ('pendiente','validado')
              AND EXISTS (
                SELECT 1 FROM codigos_candidatos tgt
                WHERE tgt.project_id = src.project_id
                  AND tgt.codigo = %s
                  AND tgt.fragmento_id = src.fragmento_id
              )
            """,
            (project_id, source_codigo, source_codigo, target_codigo),
        )
        would_dedupe = int(cur.fetchone()[0] or 0)

    return {
        "would_move": would_move,
        "would_dedupe": would_dedupe,
        "would_merge": (would_move + would_dedupe),
        "use_unaccent": bool(use_unaccent),
    }

    if affected > 0:
        for row_id, codigo, before_memo in moved_rows:
            try:
                log_code_version(
                    pg,
                    project=project_id,
                    codigo=str(codigo),
                    accion="candidate_merge_by_code",
                    memo_anterior=before_memo,
                    memo_nuevo=f"reassigned_to:{target_codigo}",
                    changed_by=merged_by,
                )
            except Exception:
                pass
        for row_id, codigo, before_memo in dedup_rows:
            try:
                log_code_version(
                    pg,
                    project=project_id,
                    codigo=str(codigo),
                    accion="candidate_merge_by_code",
                    memo_anterior=before_memo,
                    memo_nuevo=f"dedup_fusionado_a:{target_codigo}",
                    changed_by=merged_by,
                )
            except Exception:
                pass
    pg.commit()
    _logger.info(
        "merge_candidates_by_code.summary",
        extra={
            "project": project_id,
            "source": source_codigo,
            "target": target_codigo,
            "moved_count": moved_count,
            "dedup_count": dedup_count,
        },
    )
    if affected == 0:
        _logger.warning(
            "merge_candidates_by_code.no_rows",
            extra={
                "project": project_id,
                "source": source_codigo,
                "target": target_codigo,
            },
        )
    _logger.info(
        "merge_candidates_by_code.completed project=%s source=%s target=%s affected=%d",
        project_id,
        source_codigo,
        target_codigo,
        affected,
    )
    return affected


# =============================================================================
# HIPÓTESIS Y MUESTREO TEÓRICO (Grounded Theory)
# =============================================================================


def list_hypothesis_codes(
    pg: PGConnection,
    project: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Lista códigos en estado 'hipotesis' que requieren muestreo teórico.
    
    En Grounded Theory, estas son proposiciones emergentes que necesitan
    validación empírica antes de ser aceptadas como códigos definitivos.
    
    Según Charmaz (2014): "Theoretical sampling means sampling to develop 
    or refine emerging theoretical categories... keeps them grounded in data."
    
    Args:
        pg: Conexión PostgreSQL
        project: ID del proyecto
        limit: Máximo de resultados
        
    Returns:
        Lista de hipótesis pendientes de validación empírica
    """
    ensure_candidate_codes_table(pg)
    
    sql = """
    SELECT id, codigo, cita, fuente_detalle, score_confianza, 
           memo, created_at, fuente_origen, requiere_muestreo,
           muestreo_notas, codigo_origen_hipotesis
    FROM codigos_candidatos
    WHERE project_id = %s 
      AND estado = 'hipotesis'
    ORDER BY score_confianza DESC NULLS LAST, created_at DESC
    LIMIT %s
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project, limit))
        rows = cur.fetchall()
    
    return [
        {
            "id": r[0],
            "codigo": r[1],
            "cita": r[2],
            "fuente_detalle": r[3],
            "score_confianza": r[4],
            "memo": r[5],
            "created_at": r[6].isoformat() if r[6] else None,
            "fuente_origen": r[7],
            "requiere_muestreo": r[8],
            "muestreo_notas": r[9],
            "codigo_origen_hipotesis": r[10],
        }
        for r in rows
    ]


def count_hypothesis_codes(
    pg: PGConnection,
    project: str,
) -> int:
    """Cuenta hipótesis pendientes de validación empírica."""
    ensure_candidate_codes_table(pg)
    
    sql = """
    SELECT COUNT(*) FROM codigos_candidatos
    WHERE project_id = %s AND estado = 'hipotesis'
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project,))
        result = cur.fetchone()
    return result[0] if result else 0


def validate_hypothesis_with_evidence(
    pg: PGConnection,
    hypothesis_id: int,
    project: str,
    fragmento_id: str,
    cita: str,
    validado_por: str = "investigador",
) -> Dict[str, Any]:
    """
    Valida una hipótesis vinculándola a evidencia empírica.
    
    Este es el paso final del muestreo teórico: la hipótesis
    se convierte en código validado al encontrar un fragmento
    que la respalda.
    
    Según Glaser & Strauss (1967): "Grounded theory is defined as 
    the discovery of theory from data."
    
    Args:
        pg: Conexión PostgreSQL
        hypothesis_id: ID del candidato en estado 'hipotesis'
        project: ID del proyecto
        fragmento_id: ID del fragmento que respalda la hipótesis
        cita: Cita textual del fragmento
        validado_por: Usuario que realiza la validación
    
    Returns:
        Dict con resultado de la operación
        
    Raises:
        ValueError: Si fragmento_id es inválido o hipótesis no existe
    """
    if not fragmento_id or len(fragmento_id) < 10:
        raise ValueError("Se requiere un fragmento_id válido para validar la hipótesis")
    
    sql = """
    UPDATE codigos_candidatos
    SET estado = 'validado',
        fragmento_id = %s,
        cita = %s,
        validado_por = %s,
        validado_en = NOW(),
        memo = COALESCE(memo, '') || ' [VALIDADO via muestreo teórico: evidencia encontrada]',
        updated_at = NOW()
    WHERE id = %s 
      AND project_id = %s 
      AND estado = 'hipotesis'
    RETURNING id, codigo, fragmento_id
    """
    with pg.cursor() as cur:
        cur.execute(sql, (fragmento_id, cita, validado_por, hypothesis_id, project))
        result = cur.fetchone()
    pg.commit()
    
    if not result:
        raise ValueError(f"Hipótesis {hypothesis_id} no encontrada o no está en estado 'hipotesis'")
    
    log.info(
        "hypothesis.validated",
        hypothesis_id=hypothesis_id,
        codigo=result[1],
        fragmento_id=fragmento_id,
        project=project,
    )
    
    return {
        "success": True,
        "id": result[0],
        "codigo": result[1],
        "fragmento_id": result[2],
        "message": "Hipótesis validada con evidencia empírica"
    }


def reject_hypothesis(
    pg: PGConnection,
    hypothesis_id: int,
    project: str,
    razon: str,
    rechazado_por: str = "investigador",
) -> Dict[str, Any]:
    """
    Rechaza una hipótesis después de muestreo teórico fallido.
    
    Se debe proporcionar una razón metodológica del rechazo.
    En Grounded Theory, las hipótesis que no encuentran evidencia
    deben ser descartadas para mantener el rigor metodológico.
    
    Args:
        pg: Conexión PostgreSQL
        hypothesis_id: ID de la hipótesis a rechazar
        project: ID del proyecto
        razon: Razón metodológica del rechazo
        rechazado_por: Usuario que rechaza
        
    Returns:
        Dict con resultado
    """
    sql = """
    UPDATE codigos_candidatos
    SET estado = 'rechazado',
        validado_por = %s,
        validado_en = NOW(),
        memo = COALESCE(memo, '') || ' [RECHAZADO - Muestreo teórico: ' || %s || ']',
        updated_at = NOW()
    WHERE id = %s 
      AND project_id = %s 
      AND estado = 'hipotesis'
    RETURNING id, codigo
    """
    with pg.cursor() as cur:
        cur.execute(sql, (rechazado_por, razon, hypothesis_id, project))
        result = cur.fetchone()
    pg.commit()
    
    if not result:
        raise ValueError(f"Hipótesis {hypothesis_id} no encontrada o no está en estado 'hipotesis'")
    
    log.info(
        "hypothesis.rejected",
        hypothesis_id=hypothesis_id,
        codigo=result[1],
        razon=razon,
        project=project,
    )
    
    return {
        "success": True,
        "id": result[0],
        "codigo": result[1],
        "message": f"Hipótesis rechazada: {razon}"
    }


def search_evidence_for_hypothesis(
    pg: PGConnection,
    project: str,
    hypothesis_codigo: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Busca fragmentos que podrían servir como evidencia para una hipótesis.
    
    Realiza búsqueda en analisis_codigos_abiertos para encontrar fragmentos
    que contengan códigos relacionados semánticamente.
    
    Args:
        pg: Conexión PostgreSQL
        project: ID del proyecto
        hypothesis_codigo: Nombre del código hipotético
        limit: Máximo de resultados
        
    Returns:
        Lista de fragmentos potencialmente relacionados
    """
    # Extraer palabras clave del código para búsqueda
    keywords = hypothesis_codigo.replace("_", " ").replace("-", " ").split()
    
    # Buscar fragmentos que contengan términos relacionados en su cita
    sql = """
    SELECT DISTINCT fragmento_id, archivo, cita, codigo
    FROM analisis_codigos_abiertos
    WHERE project_id = %s
      AND fragmento_id IS NOT NULL
      AND fragmento_id != ''
      AND (
        LOWER(cita) LIKE ANY(%s)
        OR LOWER(codigo) LIKE ANY(%s)
      )
    ORDER BY fragmento_id
    LIMIT %s
    """
    
    like_patterns = [f"%{kw.lower()}%" for kw in keywords if len(kw) > 3]
    
    if not like_patterns:
        return []
    
    with pg.cursor() as cur:
        cur.execute(sql, (project, like_patterns, like_patterns, limit))
        rows = cur.fetchall()
    
    return [
        {
            "fragmento_id": r[0],
            "archivo": r[1],
            "cita": r[2],
            "codigo_existente": r[3],
        }
        for r in rows
    ]


def promote_to_definitive(
    pg: PGConnection,
    project_id: str,
    candidate_ids: List[int],
    promote_all_validated: bool = False,
    promoted_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Promueve códigos candidatos validados a la tabla definitiva (analisis_codigos_abiertos).
    
    Args:
        pg: Conexión PostgreSQL
        candidate_ids: IDs de candidatos validados a promover
    
    Returns:
        Dict con métricas:
        - promoted_count: filas promovidas a analisis_codigos_abiertos
        - validated_total: total de candidatos validados en bandeja (filas)
        - eligible_total: validados elegibles (con fragmento_id usable)
        - skipped_total: validados omitidos por falta de evidencia
        - mode: 'ids' | 'all_validated'
    """
    ensure_candidate_codes_table(pg)
    ensure_open_coding_table(pg)
    ensure_codes_catalog_table(pg)
    
    if not candidate_ids and not promote_all_validated:
        return {
            "mode": "ids",
            "validated_total": 0,
            "eligible_total": 0,
            "promoted_count": 0,
            "skipped_total": 0,
        }

    # Totales para UX (independientes de candidate_ids)
    with pg.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM codigos_candidatos WHERE project_id = %s AND estado = 'validado'",
            (project_id,),
        )
        validated_total = int((cur.fetchone() or [0])[0] or 0)

    # Obtener candidatos validados
    # IMPORTANTE: Excluir fragmento_id NULL o vacío para mantener coherencia
    # Selección: por IDs o por 'todos los validados'
    # Incluye code_id para propagación end-to-end (migration 018)
    if promote_all_validated:
        sql_select = """
        SELECT id, project_id, fragmento_id, codigo, archivo, cita, fuente_detalle, memo, code_id
          FROM codigos_candidatos
         WHERE project_id = %s
           AND estado = 'validado'
           AND fragmento_id IS NOT NULL
           AND fragmento_id != ''
           AND LENGTH(fragmento_id) > 10
        """
        select_params: Tuple[Any, ...] = (project_id,)
        mode = "all_validated"
    else:
        sql_select = """
        SELECT id, project_id, fragmento_id, codigo, archivo, cita, fuente_detalle, memo, code_id
          FROM codigos_candidatos
         WHERE project_id = %s
           AND id = ANY(%s)
           AND estado = 'validado'
           AND fragmento_id IS NOT NULL
           AND fragmento_id != ''
           AND LENGTH(fragmento_id) > 10
        """
        select_params = (project_id, candidate_ids)
        mode = "ids"

    with pg.cursor() as cur:
        cur.execute(sql_select, select_params)
        rows = cur.fetchall()
    
    if not rows:
        return {
            "mode": mode,
            "validated_total": validated_total,
            "eligible_total": 0,
            "promoted_count": 0,
            "skipped_total": max(validated_total - 0, 0) if promote_all_validated else 0,
        }
    
    # Insertar en tabla definitiva, resolviendo a código canónico si corresponde.
    # rows: (id, project_id, fragmento_id, codigo, archivo, cita, fuente_detalle, memo, code_id)
    open_rows: List[OpenCodeRow] = []
    for r in rows:
        original_codigo = str(r[3]) if r[3] is not None else ""
        canonical_codigo = resolve_canonical_codigo(pg, project_id, original_codigo)
        ensure_code_catalog_entry(pg, project_id, canonical_codigo)

        final_memo = r[7]
        if canonical_codigo and original_codigo and canonical_codigo.lower() != original_codigo.strip().lower():
            prefix = f"[CANON:{canonical_codigo}; ORIG:{original_codigo.strip()}] "
            if not final_memo:
                final_memo = prefix.strip()
            else:
                final_memo = f"{prefix}{final_memo}"

        # Resolver code_id: usar el del candidato, o buscar el canónico
        candidate_code_id = r[8] if len(r) > 8 else None
        resolved_code_id = candidate_code_id
        if resolved_code_id is None and canonical_codigo:
            resolved_code_id = get_code_id_for_codigo(pg, project_id, canonical_codigo)

        open_rows.append((r[1], r[2], canonical_codigo or original_codigo, r[4], r[5], r[6], final_memo, resolved_code_id))
    upsert_open_codes(pg, open_rows)

    # Marcar candidatos como promovidos (best-effort, idempotente)
    promoted_ids = [int(r[0]) for r in rows if r and r[0] is not None]
    if promoted_ids:
        with pg.cursor() as cur:
            cur.execute(
                """
                UPDATE codigos_candidatos
                   SET promovido_por = COALESCE(%s, promovido_por),
                       promovido_en = COALESCE(promovido_en, NOW()),
                       updated_at = NOW()
                 WHERE project_id = %s
                   AND id = ANY(%s)
                """,
                (promoted_by, project_id, promoted_ids),
            )
        pg.commit()

    # Audit promotion per codigo (grouped), best-effort.
    grouped: Dict[str, List[Tuple[Any, ...]]] = {}
    for row in rows:
        codigo = str(row[3])
        grouped.setdefault(codigo, []).append(row)

    for codigo, group_rows in grouped.items():
        try:
            previous = _get_latest_code_memo(pg, project_id, codigo)
            sample_memo = None
            for r in group_rows:
                if r[7]:
                    sample_memo = r[7]
                    break
            if not sample_memo:
                sample_memo = group_rows[0][5] if group_rows and group_rows[0][5] else None
            summary = (
                f"promote_to_definitive: {len(group_rows)} cita(s). {sample_memo}"
                if sample_memo
                else f"promote_to_definitive: {len(group_rows)} cita(s)"
            )
            log_code_version(
                pg,
                project=project_id,
                codigo=codigo,
                accion="promote_to_definitive",
                memo_anterior=previous,
                memo_nuevo=summary,
                changed_by=promoted_by,
            )
        except Exception:
            pass

    promoted_count = len(open_rows)

    # Elegibles (aprox. == filas seleccionadas); omitidos solo se reportan en modo masivo.
    eligible_total = promoted_count
    skipped_total = max(validated_total - eligible_total, 0) if promote_all_validated else 0

    # Construir lista de pares (fragment_id, canonical_codigo) para sync Neo4j
    # open_rows: (project_id, fragmento_id, codigo, archivo, cita, fuente, memo, code_id)
    neo4j_sync_rows = [
        {"fragment_id": r[1], "codigo": r[2]}
        for r in open_rows
        if r[1] and r[2]
    ]

    return {
        "mode": mode,
        "validated_total": validated_total,
        "eligible_total": eligible_total,
        "promoted_count": promoted_count,
        "skipped_total": skipped_total,
        "neo4j_sync_rows": neo4j_sync_rows,
    }


def get_candidate_stats_by_source(
    pg: PGConnection,
    project: str,
) -> Dict[str, Any]:
    """
    Obtiene estadísticas de códigos candidatos agrupadas por origen y estado.
    
    Returns:
        Dict con distribución por origen y estado
    """
    ensure_candidate_codes_table(pg)
    
    sql = """
    SELECT fuente_origen, estado, COUNT(*) as cantidad, COUNT(DISTINCT codigo) as codigos_unicos
      FROM codigos_candidatos
     WHERE project_id = %s
     GROUP BY fuente_origen, estado
     ORDER BY fuente_origen, estado
    """
    with pg.cursor() as cur:
        # Best-effort: avoid UI timeouts if the table is large or the DB is slow.
        cur.execute("SET LOCAL statement_timeout = 10000")
        cur.execute(sql, (project,))
        rows = cur.fetchall()
    
    # Organizar por origen (conteo de filas) + (conteo de códigos únicos por fuente)
    by_source: Dict[str, Dict[str, int]] = {}
    by_source_unique: Dict[str, Dict[str, int]] = {}
    totals = {"pendiente": 0, "validado": 0, "rechazado": 0, "fusionado": 0, "hipotesis": 0}

    for origen, estado, cantidad, unicos in rows:
        if origen not in by_source:
            by_source[origen] = {
                "pendiente": 0,
                "validado": 0,
                "rechazado": 0,
                "fusionado": 0,
                "hipotesis": 0,
                "total": 0,
            }
            by_source_unique[origen] = {
                "pendiente": 0,
                "validado": 0,
                "rechazado": 0,
                "fusionado": 0,
                "hipotesis": 0,
                "total": 0,
            }

        # Manejar estados desconocidos (robustez)
        if estado not in by_source[origen]:
            by_source[origen][estado] = 0
        if estado not in by_source_unique[origen]:
            by_source_unique[origen][estado] = 0
        if estado not in totals:
            totals[estado] = 0

        by_source[origen][estado] = int(cantidad or 0)
        by_source[origen]["total"] += int(cantidad or 0)
        totals[estado] += int(cantidad or 0)

        by_source_unique[origen][estado] = int(unicos or 0)
        by_source_unique[origen]["total"] += int(unicos or 0)

    # Códigos únicos reales por estado (a nivel proyecto), sin duplicar entre fuentes.
    unique_totals = {"pendiente": 0, "validado": 0, "rechazado": 0, "fusionado": 0, "hipotesis": 0}
    unique_total_codigos = 0
    with pg.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout = 10000")
        cur.execute(
            """
            SELECT estado, COUNT(DISTINCT codigo) AS codigos_unicos
              FROM codigos_candidatos
             WHERE project_id = %s
             GROUP BY estado
            """,
            (project,),
        )
        uniq_rows = cur.fetchall()

    for estado, unicos in uniq_rows:
        if estado not in unique_totals:
            unique_totals[estado] = 0
        unique_totals[estado] = int(unicos or 0)

    # Total de códigos únicos a nivel proyecto (sin duplicar entre estados)
    with pg.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout = 10000")
        cur.execute(
            """
            SELECT COUNT(DISTINCT codigo)
              FROM codigos_candidatos
             WHERE project_id = %s
            """,
            (project,),
        )
        row_total = cur.fetchone()
        unique_total_codigos = int(row_total[0] or 0) if row_total else 0

    # Sub-métricas UX: distinguir 'validados' que ya fueron promovidos vs pendientes por promover.
    # Nota: esto es por FILA; también retornamos versión por código único.
    promoted_validated_total = 0
    unpromoted_validated_total = 0
    promoted_validated_unique = 0
    unpromoted_validated_unique = 0
    with pg.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout = 10000")
        cur.execute(
            """
            SELECT
              SUM(CASE WHEN estado = 'validado' AND promovido_en IS NOT NULL THEN 1 ELSE 0 END) AS promoted_rows,
              SUM(CASE WHEN estado = 'validado' AND (promovido_en IS NULL) THEN 1 ELSE 0 END) AS unpromoted_rows,
              COUNT(DISTINCT CASE WHEN estado = 'validado' AND promovido_en IS NOT NULL THEN codigo END) AS promoted_unique,
              COUNT(DISTINCT CASE WHEN estado = 'validado' AND (promovido_en IS NULL) THEN codigo END) AS unpromoted_unique
            FROM codigos_candidatos
            WHERE project_id = %s
            """,
            (project,),
        )
        r = cur.fetchone() or (0, 0, 0, 0)
        promoted_validated_total = int(r[0] or 0)
        unpromoted_validated_total = int(r[1] or 0)
        promoted_validated_unique = int(r[2] or 0)
        unpromoted_validated_unique = int(r[3] or 0)

    # Total general de filas
    total_candidatos = int(sum(int(v or 0) for v in totals.values()))

    return {
        "by_source": by_source,
        "by_source_unique": by_source_unique,
        "totals": totals,
        "total_candidatos": total_candidatos,
        "unique_totals": unique_totals,
        "unique_total_codigos": unique_total_codigos,
        "validated_promoted_total": promoted_validated_total,
        "validated_unpromoted_total": unpromoted_validated_total,
        "validated_promoted_unique": promoted_validated_unique,
        "validated_unpromoted_unique": unpromoted_validated_unique,
    }


def get_canonical_examples(
    pg: PGConnection,
    codigo: str,
    project: str,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """
    Obtiene ejemplos canónicos (citas validadas previas) de un código.
    
    Usado para comparación constante al validar nuevos candidatos.
    
    Args:
        pg: Conexión PostgreSQL
        codigo: Nombre del código
        project: ID del proyecto
        limit: Máximo de ejemplos (default 3)
    
    Returns:
        Lista de citas validadas del código
    """
    ensure_open_coding_table(pg)
    
    sql = """
    SELECT cita, fragmento_id, archivo, fuente, memo, created_at
      FROM analisis_codigos_abiertos
     WHERE codigo = %s AND project_id = %s
     ORDER BY created_at DESC
     LIMIT %s
    """
    with pg.cursor() as cur:
        cur.execute(sql, (codigo, project, limit))
        rows = cur.fetchall()
    
    return [
        {
            "cita": r[0],
            "fragmento_id": r[1],
            "archivo": r[2],
            "fuente": r[3],
            "memo": r[4],
            "created_at": r[5].isoformat() if r[5] else None,
        }
        for r in rows
    ]


def get_backlog_health(
    pg: PGConnection,
    project: str,
    threshold_days: int = 3,
    threshold_count: int = 50,
) -> Dict[str, Any]:
    """
    Verifica la salud del backlog de candidatos pendientes.
    
    Retorna métricas de salud y alertas si hay problemas.
    
    Args:
        pg: Conexión PostgreSQL
        project: ID del proyecto
        threshold_days: Días máximos sin resolver candidato antes de alerta
        threshold_count: Cantidad máxima de pendientes antes de alerta
    
    Returns:
        Dict con métricas de salud y estado is_healthy
    """
    ensure_candidate_codes_table(pg)
    
    sql_pending = """
    SELECT 
        COUNT(*) as pending_count,
        MIN(created_at) as oldest_pending,
        AVG(EXTRACT(EPOCH FROM (NOW() - created_at))/3600) as avg_age_hours
      FROM codigos_candidatos
     WHERE project_id = %s AND estado = 'pendiente'
    """
    
    sql_resolution = """
    SELECT 
        AVG(EXTRACT(EPOCH FROM (validado_en - created_at))/3600) as avg_resolution_hours
      FROM codigos_candidatos
     WHERE project_id = %s 
       AND estado IN ('validado', 'rechazado')
       AND validado_en IS NOT NULL
       AND created_at > NOW() - INTERVAL '30 days'
    """
    
    with pg.cursor() as cur:
        # Best-effort: keep this endpoint responsive for UI health checks.
        cur.execute("SET LOCAL statement_timeout = 10000")
        cur.execute(sql_pending, (project,))
        pending = cur.fetchone()
        
        cur.execute("SET LOCAL statement_timeout = 10000")
        cur.execute(sql_resolution, (project,))
        resolution = cur.fetchone()
    
    pending_count = pending[0] if pending and pending[0] else 0
    oldest_pending = pending[1] if pending and pending[1] else None
    avg_age_hours = pending[2] if pending and pending[2] else 0
    avg_resolution_hours = resolution[0] if resolution and resolution[0] else None
    
    # Calcular días desde el candidato más antiguo
    oldest_pending_days = 0
    if oldest_pending:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        oldest_pending_days = (now - oldest_pending).days
    
    # Determinar si está saludable
    is_healthy = (
        pending_count < threshold_count and
        oldest_pending_days < threshold_days
    )
    
    alerts = []
    if pending_count >= threshold_count:
        alerts.append(f"Backlog alto: {pending_count} candidatos pendientes")
    if oldest_pending_days >= threshold_days:
        alerts.append(f"Candidato sin resolver desde hace {oldest_pending_days} días")
    
    return {
        "is_healthy": is_healthy,
        "pending_count": pending_count,
        "oldest_pending_days": oldest_pending_days,
        "avg_pending_age_hours": round(avg_age_hours, 1) if avg_age_hours else 0,
        "avg_resolution_hours": round(avg_resolution_hours, 1) if avg_resolution_hours else None,
        "alerts": alerts,
        "thresholds": {
            "max_days": threshold_days,
            "max_count": threshold_count,
        }
    }


# =============================================================================
# SISTEMA DE USUARIOS Y AUTENTICACIÓN
# =============================================================================

def ensure_users_table(pg: PGConnection) -> None:
    """
    Crea las tablas de usuarios y sesiones si no existen.
    
    Nota: No usa pgcrypto ni gen_random_uuid() para compatibilidad con Azure PostgreSQL.
    Los UUIDs se generan desde Python.
    """
    sql = """
    CREATE TABLE IF NOT EXISTS app_users (
        id UUID PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT,
        organization_id TEXT DEFAULT 'default_org',
        role TEXT DEFAULT 'analyst',
        is_active BOOLEAN DEFAULT true,
        is_verified BOOLEAN DEFAULT false,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_login_at TIMESTAMPTZ
    );
    
    CREATE TABLE IF NOT EXISTS app_sessions (
        id UUID PRIMARY KEY,
        user_id UUID REFERENCES app_users(id) ON DELETE CASCADE,
        refresh_token_hash TEXT NOT NULL,
        user_agent TEXT,
        ip_address TEXT,
        expires_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        is_revoked BOOLEAN DEFAULT false,
        last_active_at TIMESTAMPTZ DEFAULT NOW()
    );
    
    CREATE INDEX IF NOT EXISTS ix_users_email ON app_users(email);
    CREATE INDEX IF NOT EXISTS ix_users_org ON app_users(organization_id);
    CREATE INDEX IF NOT EXISTS ix_sessions_user ON app_sessions(user_id);
    CREATE INDEX IF NOT EXISTS ix_sessions_token ON app_sessions(refresh_token_hash);
    """
    with pg.cursor() as cur:
        cur.execute(sql)
    pg.commit()


def create_user(
    pg: PGConnection,
    email: str,
    password_hash: str,
    full_name: Optional[str] = None,
    organization_id: str = "default_org",
    role: str = "analyst",
) -> Dict[str, Any]:
    """
    Crea un nuevo usuario.
    
    Args:
        email: Email único del usuario
        password_hash: Hash bcrypt del password (NO el password plano)
        full_name: Nombre completo opcional
        organization_id: Organización del usuario
        role: Rol del usuario (admin, analyst, viewer)
    
    Returns:
        Dict con datos del usuario creado (sin password_hash)
    
    Raises:
        Exception si el email ya existe
    """
    ensure_users_table(pg)
    
    import uuid
    user_id = str(uuid.uuid4())
    
    sql = """
    INSERT INTO app_users (id, email, password_hash, full_name, organization_id, role)
    VALUES (%s, %s, %s, %s, %s, %s)
    RETURNING id, email, full_name, organization_id, role, is_active, is_verified, created_at
    """
    
    with pg.cursor() as cur:
        cur.execute(sql, (user_id, email, password_hash, full_name, organization_id, role))
        row = cur.fetchone()
    pg.commit()
    if row is None:
        raise RuntimeError("No se pudo crear el usuario")
    
    return {
        "id": str(row[0]),
        "email": row[1],
        "full_name": row[2],
        "organization_id": row[3],
        "role": row[4],
        "is_active": row[5],
        "is_verified": row[6],
        "created_at": row[7].isoformat() if row[7] else None,
    }


def get_user_by_email(pg: PGConnection, email: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene usuario por email.
    
    Incluye password_hash para verificación de login.
    """
    ensure_users_table(pg)
    
    sql = """
    SELECT id, email, password_hash, full_name, organization_id, role, 
           is_active, is_verified, created_at, last_login_at
    FROM app_users
    WHERE email = %s
    """
    
    with pg.cursor() as cur:
        cur.execute(sql, (email,))
        row = cur.fetchone()
    
    if row is None:
        return None
    
    return {
        "id": str(row[0]),
        "email": row[1],
        "password_hash": row[2],
        "full_name": row[3],
        "organization_id": row[4],
        "role": row[5],
        "is_active": row[6],
        "is_verified": row[7],
        "created_at": row[8].isoformat() if row[8] else None,
        "last_login_at": row[9].isoformat() if row[9] else None,
    }


def get_user_by_id(pg: PGConnection, user_id: str) -> Optional[Dict[str, Any]]:
    """Obtiene usuario por ID (sin password_hash)."""
    ensure_users_table(pg)
    
    sql = """
    SELECT id, email, full_name, organization_id, role, 
           is_active, is_verified, created_at, last_login_at
    FROM app_users
    WHERE id = %s
    """
    
    with pg.cursor() as cur:
        cur.execute(sql, (user_id,))
        row = cur.fetchone()
    
    if row is None:
        return None
    
    return {
        "id": str(row[0]),
        "email": row[1],
        "full_name": row[2],
        "organization_id": row[3],
        "role": row[4],
        "is_active": row[5],
        "is_verified": row[6],
        "created_at": row[7].isoformat() if row[7] else None,
        "last_login_at": row[8].isoformat() if row[8] else None,
    }


def update_user_password(pg: PGConnection, user_id: str, new_password_hash: str) -> bool:
    """Actualiza el password de un usuario."""
    sql = """
    UPDATE app_users 
    SET password_hash = %s, updated_at = NOW()
    WHERE id = %s
    """
    with pg.cursor() as cur:
        cur.execute(sql, (new_password_hash, user_id))
        affected = cur.rowcount
    pg.commit()
    return affected > 0


def update_last_login(pg: PGConnection, user_id: str) -> None:
    """Actualiza timestamp de último login."""
    sql = "UPDATE app_users SET last_login_at = NOW() WHERE id = %s"
    with pg.cursor() as cur:
        cur.execute(sql, (user_id,))
    pg.commit()


def list_users(
    pg: PGConnection, 
    organization_id: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Lista usuarios, opcionalmente filtrados por organización."""
    ensure_users_table(pg)
    
    if organization_id:
        sql = """
        SELECT id, email, full_name, organization_id, role, is_active, created_at
        FROM app_users
        WHERE organization_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """
        params = (organization_id, limit)
    else:
        sql = """
        SELECT id, email, full_name, organization_id, role, is_active, created_at
        FROM app_users
        ORDER BY created_at DESC
        LIMIT %s
        """
        params = (limit,)
    
    with pg.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    
    return [
        {
            "id": str(r[0]),
            "email": r[1],
            "full_name": r[2],
            "organization_id": r[3],
            "role": r[4],
            "is_active": r[5],
            "created_at": r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]


def count_users(pg: PGConnection, organization_id: Optional[str] = None) -> int:
    """Cuenta usuarios totales o por organización."""
    ensure_users_table(pg)
    
    if organization_id:
        sql = "SELECT COUNT(*) FROM app_users WHERE organization_id = %s"
        params = (organization_id,)
    else:
        sql = "SELECT COUNT(*) FROM app_users"
        params = ()
    
    with pg.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    
    if row is None:
        return 0
    return row[0]


# =============================================================================
# SESIONES DE USUARIO
# =============================================================================

def create_session(
    pg: PGConnection,
    user_id: str,
    refresh_token_hash: str,
    expires_at: str,  # ISO format
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> Dict[str, Any]:
    """Crea una nueva sesión de usuario."""
    import uuid
    session_id = str(uuid.uuid4())
    
    ensure_users_table(pg)
    
    sql = """
    INSERT INTO app_sessions (id, user_id, refresh_token_hash, expires_at, user_agent, ip_address)
    VALUES (%s, %s, %s, %s, %s, %s)
    RETURNING id, created_at
    """
    
    with pg.cursor() as cur:
        cur.execute(sql, (session_id, user_id, refresh_token_hash, expires_at, user_agent, ip_address))
        row = cur.fetchone()
    pg.commit()
    if row is None:
        raise RuntimeError("No se pudo crear la sesión")
    
    return {
        "session_id": str(row[0]),
        "created_at": row[1].isoformat() if row[1] else None,
    }


def get_session_by_token(pg: PGConnection, refresh_token_hash: str) -> Optional[Dict[str, Any]]:
    """Obtiene sesión por hash del refresh token."""
    sql = """
    SELECT s.id, s.user_id, s.expires_at, s.is_revoked, s.last_active_at,
           u.email, u.role, u.organization_id, u.is_active
    FROM app_sessions s
    JOIN app_users u ON s.user_id = u.id
    WHERE s.refresh_token_hash = %s
    """
    
    with pg.cursor() as cur:
        cur.execute(sql, (refresh_token_hash,))
        row = cur.fetchone()
    
    if row is None:
        return None
    
    return {
        "session_id": str(row[0]),
        "user_id": str(row[1]),
        "expires_at": row[2].isoformat() if row[2] else None,
        "is_revoked": row[3],
        "last_active_at": row[4].isoformat() if row[4] else None,
        "email": row[5],
        "role": row[6],
        "organization_id": row[7],
        "user_is_active": row[8],
    }


def revoke_session(pg: PGConnection, session_id: str) -> bool:
    """Revoca una sesión (logout)."""
    sql = "UPDATE app_sessions SET is_revoked = true WHERE id = %s"
    with pg.cursor() as cur:
        cur.execute(sql, (session_id,))
        affected = cur.rowcount
    pg.commit()
    return affected > 0


def revoke_all_user_sessions(pg: PGConnection, user_id: str) -> int:
    """Revoca todas las sesiones de un usuario."""
    sql = "UPDATE app_sessions SET is_revoked = true WHERE user_id = %s AND is_revoked = false"
    with pg.cursor() as cur:
        cur.execute(sql, (user_id,))
        affected = cur.rowcount
    pg.commit()
    return affected


def update_session_activity(pg: PGConnection, session_id: str) -> None:
    """Actualiza timestamp de última actividad de sesión."""
    sql = "UPDATE app_sessions SET last_active_at = NOW() WHERE id = %s"
    with pg.cursor() as cur:
        cur.execute(sql, (session_id,))
    pg.commit()


def cleanup_expired_sessions(pg: PGConnection) -> int:
    """Elimina sesiones expiradas (mantenimiento)."""
    sql = "DELETE FROM app_sessions WHERE expires_at < NOW() OR is_revoked = true"
    with pg.cursor() as cur:
        cur.execute(sql)
        affected = cur.rowcount
    pg.commit()
    return affected


# =============================================================================
# Project Management (Cloud-ready - replaces local JSON files)
# =============================================================================

def ensure_projects_table(pg: PGConnection) -> None:
    """Asegura que la tabla proyectos exista."""
    sql = """
    CREATE TABLE IF NOT EXISTS proyectos (
        id VARCHAR(100) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        org_id VARCHAR(100),
        owner_id VARCHAR(100),
        config JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_proyectos_org ON proyectos(org_id);
    CREATE INDEX IF NOT EXISTS idx_proyectos_owner ON proyectos(owner_id);
    """
    with pg.cursor() as cur:
        cur.execute(sql)
    pg.commit()


def list_projects_db(pg: PGConnection, org_id: Optional[str] = None, owner_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista proyectos desde PostgreSQL."""
    base_sql = """
    SELECT id, name, description, org_id, owner_id, config, created_at, updated_at, epistemic_mode
    FROM proyectos
    """
    conditions = []
    params: List[Any] = []
    
    if org_id:
        conditions.append("org_id = %s")
        params.append(org_id)
    if owner_id:
        conditions.append("owner_id = %s")
        params.append(owner_id)
    
    if conditions:
        base_sql += " WHERE " + " AND ".join(conditions)
    
    base_sql += " ORDER BY created_at DESC"
    
    with pg.cursor() as cur:
        cur.execute(base_sql, params)
        rows = cur.fetchall()
    
    return [
        {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "org_id": row[3],
            "owner_id": row[4],
            "config": row[5] or {},
            "created_at": row[6].isoformat() if row[6] else None,
            "updated_at": row[7].isoformat() if row[7] else None,
            "epistemic_mode": row[8] or "constructivist",
        }
        for row in rows
    ]


def get_project_db(pg: PGConnection, project_id: str, org_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Obtiene un proyecto por ID desde PostgreSQL.
    
    Args:
        pg: Conexión PostgreSQL
        project_id: ID del proyecto a buscar
        org_id: Si se provee, solo busca proyectos de esta organización
                (para verificación de duplicados scoped a org)
    """
    if org_id:
        sql = """
        SELECT id, name, description, org_id, owner_id, config, created_at, updated_at, epistemic_mode
        FROM proyectos WHERE id = %s AND org_id = %s
        """
        params = (project_id, org_id)
    else:
        sql = """
        SELECT id, name, description, org_id, owner_id, config, created_at, updated_at, epistemic_mode
        FROM proyectos WHERE id = %s
        """
        params = (project_id,)
    with pg.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    
    if row is None:
        return None
    
    return {
        "id": row[0],
        "name": row[1],
        "description": row[2],
        "org_id": row[3],
        "owner_id": row[4],
        "config": row[5] or {},
        "created_at": row[6].isoformat() if row[6] else None,
        "updated_at": row[7].isoformat() if row[7] else None,
        "epistemic_mode": row[8] or "constructivist",
    }


def resolve_project_db(pg: PGConnection, identifier: str) -> Optional[str]:
    """
    Resuelve un identificador de proyecto a su ID.
    Busca por ID exacto o por nombre (case-insensitive).
    """
    sql = """
    SELECT id FROM proyectos 
    WHERE id = %s OR LOWER(name) = LOWER(%s)
    LIMIT 1
    """
    with pg.cursor() as cur:
        cur.execute(sql, (identifier, identifier))
        row = cur.fetchone()
    
    if row is None:
        return None
    return row[0]


def create_project_db(
    pg: PGConnection,
    project_id: str,
    name: str,
    description: Optional[str] = None,
    org_id: Optional[str] = None,
    owner_id: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    epistemic_mode: str = "constructivist",
) -> Dict[str, Any]:
    """Crea un nuevo proyecto en PostgreSQL."""
    # Validar epistemic_mode
    if epistemic_mode not in ("constructivist", "post_positivist"):
        epistemic_mode = "constructivist"
    
    default_config = {
        "discovery_threshold": 0.30,
        "analysis_temperature": 0.3,
        "analysis_max_tokens": 2000,
    }
    final_config = {**default_config, **(config or {})}
    
    sql = """
    INSERT INTO proyectos (id, name, description, org_id, owner_id, config, epistemic_mode)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    RETURNING id, name, description, org_id, owner_id, config, created_at, updated_at, epistemic_mode
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project_id, name, description, org_id, owner_id, Json(final_config), epistemic_mode))
        row = cur.fetchone()
    pg.commit()
    if row is None:
        raise RuntimeError("No se pudo crear el proyecto")
    
    return {
        "id": row[0],
        "name": row[1],
        "description": row[2],
        "org_id": row[3],
        "owner_id": row[4],
        "config": row[5],
        "created_at": row[6].isoformat() if row[6] else None,
        "updated_at": row[7].isoformat() if row[7] else None,
        "epistemic_mode": row[8] if len(row) > 8 else "constructivist",
    }


def update_project_config_db(
    pg: PGConnection, project_id: str, config_updates: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Actualiza la configuración de un proyecto."""
    # First get current config
    current = get_project_db(pg, project_id)
    if not current:
        return None
    
    # Merge configs
    new_config = {**current.get("config", {}), **config_updates}
    
    sql = """
    UPDATE proyectos SET config = %s, updated_at = NOW()
    WHERE id = %s
    RETURNING config
    """
    with pg.cursor() as cur:
        cur.execute(sql, (Json(new_config), project_id))
        row = cur.fetchone()
    pg.commit()
    
    if row is None:
        return None
    return row[0]


def update_project_db(
    pg: PGConnection,
    project_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Actualiza el nombre/descripcion de un proyecto."""
    if name is None and description is None:
        return get_project_db(pg, project_id)

    fields = []
    params: List[Any] = []

    if name is not None:
        fields.append("name = %s")
        params.append(name)
    if description is not None:
        fields.append("description = %s")
        params.append(description)

    params.append(project_id)
    sql = f"""
    UPDATE proyectos
       SET {', '.join(fields)}, updated_at = NOW()
     WHERE id = %s
     RETURNING id, name, description, org_id, owner_id, config, created_at, updated_at
    """
    with pg.cursor() as cur:
        cur.execute(sql, tuple(params))
        row = cur.fetchone()
    pg.commit()

    if row is None:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "description": row[2],
        "org_id": row[3],
        "owner_id": row[4],
        "config": row[5],
        "created_at": row[6].isoformat() if row[6] else None,
        "updated_at": row[7].isoformat() if row[7] else None,
    }


def ensure_default_project_db(pg: PGConnection) -> None:
    """Asegura que el proyecto 'default' exista en la BD."""
    sql = """
    INSERT INTO proyectos (id, name, description, org_id)
    VALUES ('default', 'Proyecto default', 'Proyecto base inicial', 'default_org')
    ON CONFLICT (id) DO NOTHING
    """
    with pg.cursor() as cur:
        cur.execute(sql)
        cur.execute(
            "UPDATE proyectos SET org_id = 'default_org' WHERE id = 'default' AND (org_id IS NULL OR org_id = '')"
        )
    pg.commit()


# =============================================================================
# Epistemic Mode (per-project methodology configuration)
# =============================================================================

def get_project_epistemic_mode(pg: PGConnection, project_id: str) -> "EpistemicMode":
    """Get the epistemic mode configured for a project.
    
    Args:
        pg: PostgreSQL connection
        project_id: Project identifier
        
    Returns:
        EpistemicMode (defaults to CONSTRUCTIVIST if not set or invalid)
    """
    from app.settings import EpistemicMode
    
    query = "SELECT epistemic_mode FROM proyectos WHERE id = %s"
    with pg.cursor() as cur:
        cur.execute(query, (project_id,))
        row = cur.fetchone()
        if row and row[0]:
            return EpistemicMode.from_string(row[0])
    return EpistemicMode.CONSTRUCTIVIST


def set_project_epistemic_mode(
    pg: PGConnection, 
    project_id: str, 
    mode: "EpistemicMode"
) -> Tuple[bool, str]:
    """Set epistemic mode for a project.
    
    Guardrails (mode lock enforcement):
    - Do not allow changing epistemic_mode once open coding has started.
    - Do not allow changing epistemic_mode once there are validated axial relations.
    
    Args:
        pg: PostgreSQL connection
        project_id: Project identifier
        mode: EpistemicMode to set
        
    Returns:
        Tuple[success: bool, message: str]
    """
    from app.settings import EpistemicMode
    
    with pg.cursor() as cur:
        # Normalize/validate input.
        normalized = EpistemicMode.from_string(getattr(mode, "value", None))

        # Project must exist.
        cur.execute("SELECT 1 FROM proyectos WHERE id = %s", (project_id,))
        if cur.fetchone() is None:
            return False, f"Project {project_id} not found"

        # Open coding has started? (lock)
        open_started = False
        open_sources: List[str] = []
        try:
            if _pg_get_table_columns(pg, "analisis_codigos_abiertos"):
                cur.execute(
                    "SELECT 1 FROM analisis_codigos_abiertos WHERE project_id = %s LIMIT 1",
                    (project_id,),
                )
                if cur.fetchone() is not None:
                    open_started = True
                    open_sources.append("analisis_codigos_abiertos")
        except Exception:
            # best-effort guard; do not crash mode update
            open_started = open_started

        try:
            if _pg_get_table_columns(pg, "codigos_candidatos"):
                cur.execute(
                    "SELECT 1 FROM codigos_candidatos WHERE project_id = %s LIMIT 1",
                    (project_id,),
                )
                if cur.fetchone() is not None:
                    open_started = True
                    open_sources.append("codigos_candidatos")
        except Exception:
            open_started = open_started

        if open_started:
            _logger.warning(
                "epistemic_mode.change_blocked",
                project_id=project_id,
                reason="open_coding_started",
                sources=open_sources,
            )
            return False, "Cannot change epistemic_mode: open coding already started"

        # Any validated axial relations? (lock)
        axial_sources: List[str] = []
        axial_validated = False

        try:
            axial_cols = _pg_get_table_columns(pg, "analisis_axial")
            if axial_cols:
                if "estado" in axial_cols:
                    cur.execute(
                        """
                        SELECT 1
                        FROM analisis_axial
                        WHERE project_id = %s
                          AND COALESCE(NULLIF(estado, ''), 'validado') = 'validado'
                        LIMIT 1
                        """,
                        (project_id,),
                    )
                else:
                    # Legacy deployments: without `estado`, assume existing rows are validated.
                    cur.execute(
                        "SELECT 1 FROM analisis_axial WHERE project_id = %s LIMIT 1",
                        (project_id,),
                    )
                if cur.fetchone() is not None:
                    axial_validated = True
                    axial_sources.append("analisis_axial")
        except Exception:
            axial_validated = axial_validated

        try:
            if _pg_get_table_columns(pg, "link_predictions"):
                cur.execute(
                    """
                    SELECT 1
                    FROM link_predictions
                    WHERE project_id = %s AND estado = 'validado'
                    LIMIT 1
                    """,
                    (project_id,),
                )
                if cur.fetchone() is not None:
                    axial_validated = True
                    axial_sources.append("link_predictions")
        except Exception:
            axial_validated = axial_validated

        if axial_validated:
            _logger.warning(
                "epistemic_mode.change_blocked",
                project_id=project_id,
                reason="axial_validated",
                sources=axial_sources,
            )
            return False, "Cannot change epistemic_mode: project has validated axial relations"
        
        # Safe to update
        update = """
            UPDATE proyectos 
            SET epistemic_mode = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING epistemic_mode
        """
        cur.execute(update, (normalized.value, project_id))
        updated = cur.fetchone()
        
        if updated is None:
            return False, f"Project {project_id} not found"
        
        pg.commit()
        
        _logger.info(
            "epistemic_mode.updated",
            project_id=project_id,
            mode=normalized.value,
        )
        return True, f"epistemic_mode set to {normalized.value}"


def has_axial_relations(pg: PGConnection, project_id: str) -> bool:
    """Check if a project has any validated axial relations (for mode lock check).
    
    Args:
        pg: PostgreSQL connection
        project_id: Project identifier
        
    Returns:
        True if project has at least one validated axial relation
    """
    cols = _pg_get_table_columns(pg, "analisis_axial")
    if cols:
        with pg.cursor() as cur:
            if "estado" in cols:
                cur.execute(
                    """
                    SELECT 1
                    FROM analisis_axial
                    WHERE project_id = %s
                      AND COALESCE(NULLIF(estado, ''), 'validado') = 'validado'
                    LIMIT 1
                    """,
                    (project_id,),
                )
            else:
                cur.execute("SELECT 1 FROM analisis_axial WHERE project_id = %s LIMIT 1", (project_id,))
            if cur.fetchone() is not None:
                return True

    cols = _pg_get_table_columns(pg, "link_predictions")
    if cols:
        with pg.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM link_predictions WHERE project_id = %s AND estado = 'validado' LIMIT 1",
                (project_id,),
            )
            if cur.fetchone() is not None:
                return True

    return False


# =============================================================================
# Project State (Cloud-ready - replaces projects/{id}.json)
# =============================================================================

def ensure_project_state_table(pg: PGConnection) -> None:
    """Asegura que la tabla proyecto_estado exista."""
    sql = """
    CREATE TABLE IF NOT EXISTS proyecto_estado (
        id SERIAL PRIMARY KEY,
        project_id VARCHAR(100) NOT NULL,
        stage VARCHAR(50) NOT NULL,
        completed BOOLEAN DEFAULT FALSE,
        last_run_id VARCHAR(100),
        command VARCHAR(100),
        subcommand VARCHAR(100),
        extras JSONB,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(project_id, stage)
    );
    CREATE INDEX IF NOT EXISTS idx_proyecto_estado_project ON proyecto_estado(project_id);
    """
    with pg.cursor() as cur:
        cur.execute(sql)
    pg.commit()


def load_project_state_db(pg: PGConnection, project_id: str) -> Dict[str, Any]:
    """Carga el estado de un proyecto desde PostgreSQL."""
    sql = """
    SELECT stage, completed, last_run_id, command, subcommand, extras, updated_at
    FROM proyecto_estado WHERE project_id = %s
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project_id,))
        rows = cur.fetchall()
    
    state: Dict[str, Any] = {}
    for row in rows:
        stage = row[0]
        state[stage] = {
            "completed": row[1],
            "last_run_id": row[2],
            "command": row[3],
            "subcommand": row[4],
            "extras": row[5] or {},
            "updated_at": row[6].isoformat() if row[6] else None,
        }
    return state


def save_project_stage_db(
    pg: PGConnection,
    project_id: str,
    stage: str,
    *,
    completed: bool = True,
    run_id: Optional[str] = None,
    command: Optional[str] = None,
    subcommand: Optional[str] = None,
    extras: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Guarda/actualiza el estado de una etapa de proyecto."""
    sql = """
    INSERT INTO proyecto_estado (project_id, stage, completed, last_run_id, command, subcommand, extras)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (project_id, stage) DO UPDATE SET
        completed = EXCLUDED.completed,
        last_run_id = EXCLUDED.last_run_id,
        command = EXCLUDED.command,
        subcommand = EXCLUDED.subcommand,
        extras = EXCLUDED.extras,
        updated_at = NOW()
    RETURNING stage, completed, last_run_id, command, subcommand, extras, updated_at
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project_id, stage, completed, run_id, command, subcommand, Json(extras or {})))
        row = cur.fetchone()
    pg.commit()
    if row is None:
        raise RuntimeError("No se pudo guardar el estado del proyecto")
    
    return {
        "stage": row[0],
        "completed": row[1],
        "last_run_id": row[2],
        "command": row[3],
        "subcommand": row[4],
        "extras": row[5] or {},
        "updated_at": row[6].isoformat() if row[6] else None,
    }


def check_axial_ready(pg: PGConnection, project_id: str) -> Tuple[bool, List[str]]:
    """
    Verifica si la infraestructura ontológica está lista para operaciones axiales.
    
    Ejecuta las mismas validaciones que `/api/admin/code-id/status`:
    - Columnas requeridas existen
    - No hay `code_id` faltantes
    - No hay `canonical_code_id` faltantes para códigos no canónicos
    - No hay divergencias entre texto y ID
    - No hay ciclos no triviales en la cadena canónica
    
    Args:
        pg: Conexión PostgreSQL
        project_id: ID del proyecto a validar
        
    Returns:
        Tuple[bool, List[str]]: (axial_ready, blocking_reasons)
        - axial_ready: True si puede proceder con operaciones axiales
        - blocking_reasons: Lista de razones de bloqueo (vacía si ready)
        
    Example:
        >>> ready, reasons = check_axial_ready(pg, "jd-007")
        >>> if not ready:
        ...     raise HTTPException(409, detail={"blocking_reasons": reasons})
    """
    blocking_reasons: List[str] = []
    
    # 1. Verificar que las columnas requeridas existen
    with pg.cursor() as cur:
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'catalogo_codigos'
        """)
        columns = {row[0] for row in cur.fetchall()}
    
    has_code_id = "code_id" in columns
    has_canonical_code_id = "canonical_code_id" in columns
    supported = has_code_id and has_canonical_code_id
    
    if not supported:
        blocking_reasons.append("supported=false")
        return False, blocking_reasons
    
    # 2. Verificar missing_code_id
    with pg.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM catalogo_codigos 
            WHERE project_id = %s AND code_id IS NULL
        """, (project_id,))
        missing_code_id = int((cur.fetchone() or [0])[0] or 0)
    
    if missing_code_id > 0:
        blocking_reasons.append("missing_code_id")
    
    # 3. Verificar missing_canonical_code_id para no-canónicos
    with pg.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM catalogo_codigos 
            WHERE project_id = %s 
              AND canonical_codigo IS NOT NULL 
              AND canonical_codigo != codigo
              AND canonical_code_id IS NULL
        """, (project_id,))
        missing_canonical = int((cur.fetchone() or [0])[0] or 0)
    
    if missing_canonical > 0:
        blocking_reasons.append("missing_canonical_code_id")
    
    # 4. Verificar divergencias texto vs ID
    with pg.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM catalogo_codigos c
            WHERE c.project_id = %s
              AND c.canonical_code_id IS NOT NULL
              AND c.canonical_codigo IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM catalogo_codigos t
                  WHERE t.project_id = c.project_id
                    AND t.code_id = c.canonical_code_id
                    AND LOWER(TRIM(t.codigo)) = LOWER(TRIM(c.canonical_codigo))
              )
        """, (project_id,))
        divergences = int((cur.fetchone() or [0])[0] or 0)
    
    if divergences > 0:
        blocking_reasons.append("divergences_text_vs_id")
    
    # 5. Detectar ciclos no triviales (profundidad > 2)
    with pg.cursor() as cur:
        cur.execute("""
            WITH RECURSIVE walk AS (
              SELECT project_id,
                     code_id,
                     canonical_code_id,
                     ARRAY[code_id] AS path,
                     FALSE AS cycle
                FROM catalogo_codigos
               WHERE project_id = %s
                 AND code_id IS NOT NULL
                 AND canonical_code_id IS NOT NULL
              UNION ALL
              SELECT w.project_id,
                     c.code_id,
                     c.canonical_code_id,
                     w.path || c.code_id,
                     (c.code_id = ANY(w.path)) AS cycle
                FROM walk w
                JOIN catalogo_codigos c
                  ON c.project_id = w.project_id
                 AND c.code_id = w.canonical_code_id
               WHERE w.cycle = FALSE
                 AND array_length(w.path, 1) < 25
                 AND c.code_id IS NOT NULL
            )
            SELECT COUNT(DISTINCT n)::INT
              FROM (
                  SELECT unnest(path) AS n
                    FROM walk
                   WHERE cycle = TRUE
                     AND array_length(path, 1) > 2
              ) s
        """, (project_id,))
        cycle_nodes = int((cur.fetchone() or [0])[0] or 0)
    
    if cycle_nodes > 0:
        blocking_reasons.append("cycles_non_trivial")
    
    axial_ready = len(blocking_reasons) == 0
    return axial_ready, blocking_reasons
