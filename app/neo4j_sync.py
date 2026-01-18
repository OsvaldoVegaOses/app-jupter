"""
Sincronización diferida de fragmentos a Neo4j.

Este módulo permite sincronizar fragmentos que fueron ingestados
mientras Neo4j estaba no disponible.

Uso desde Admin Panel:
    POST /api/admin/sync-neo4j?project=<project_id>
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import structlog

from .clients import ServiceClients
from .settings import AppSettings
from .neo4j_block import (
    ALLOWED_REL_TYPES,
    ensure_category_constraints,
    ensure_code_constraints,
    merge_category_code_relationships,
    merge_fragments,
)
from .postgres_block import _pg_get_table_columns

_logger = structlog.get_logger()


def _pg_has_column(pg, table: str, column: str, schema: str = "public") -> bool:
    try:
        with pg.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = %s
                  AND column_name = %s
                LIMIT 1
                """,
                (schema, table, column),
            )
            return cur.fetchone() is not None
    except Exception:
        return False


def get_sync_status(
    pg,
    project: str,
) -> Dict[str, int]:
    """
    Obtiene el estado de sincronización para un proyecto.
    
    Returns:
        Dict con pending, synced, total counts
    """
    try:
        has_flag = _pg_has_column(pg, "entrevista_fragmentos", "neo4j_synced")
        with pg.cursor() as cur:
            if has_flag:
                cur.execute(
                    """
                    SELECT
                        COALESCE(SUM(CASE WHEN neo4j_synced = FALSE THEN 1 ELSE 0 END), 0) as pending,
                        COALESCE(SUM(CASE WHEN neo4j_synced = TRUE THEN 1 ELSE 0 END), 0) as synced,
                        COUNT(*) as total
                    FROM entrevista_fragmentos
                    WHERE project_id = %s
                    """,
                    (project,),
                )
                row = cur.fetchone()
                if row:
                    return {
                        "pending": int(row[0]),
                        "synced": int(row[1]),
                        "total": int(row[2]),
                    }

            cur.execute(
                "SELECT COUNT(*) FROM entrevista_fragmentos WHERE project_id = %s",
                (project,),
            )
            total = int(cur.fetchone()[0])
            # When the tracking column is missing, assume everything is pending.
            return {"pending": total, "synced": 0, "total": total}
    except Exception as e:
        _logger.debug("sync_status.failed", error=str(e)[:120])
        return {"pending": 0, "synced": 0, "total": 0}


def check_neo4j_connection(clients: ServiceClients, settings: AppSettings) -> bool:
    """Verifica si Neo4j está disponible."""
    try:
        with clients.neo4j.session(database=settings.neo4j.database) as session:
            result = session.run("RETURN 1 as ok")
            return result.single() is not None
    except Exception:
        return False


def sync_pending_fragments(
    clients: ServiceClients,
    settings: AppSettings,
    project: str,
    batch_size: int = 100,
    after_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sincroniza fragmentos pendientes a Neo4j.
    
    Args:
        clients: Clientes de servicios
        settings: Configuración
        project: ID del proyecto
        batch_size: Tamaño del batch
        
    Returns:
        Dict con synced, failed, remaining counts
    """
    _logger.info("neo4j_sync.start", project=project, batch_size=batch_size)
    
    # Verificar conexión Neo4j
    if not check_neo4j_connection(clients, settings):
        _logger.error("neo4j_sync.neo4j_unavailable")
        return {"synced": 0, "failed": 0, "remaining": -1, "error": "Neo4j no disponible"}
    
    has_flag = _pg_has_column(clients.postgres, "entrevista_fragmentos", "neo4j_synced")

    # Obtener fragmentos pendientes (o el siguiente batch cuando no hay flag)
    try:
        with clients.postgres.cursor() as cur:
            where_parts = ["project_id = %s"]
            params: list[Any] = [project]

            if has_flag:
                where_parts.append("neo4j_synced IS DISTINCT FROM TRUE")
            if after_id:
                where_parts.append("id > %s")
                params.append(after_id)

            where_sql = " AND ".join(where_parts)
            cur.execute(
                f"""
                SELECT id, archivo, speaker, fragmento,
                       char_len, actor_principal, metadata, par_idx,
                       interviewer_tokens, interviewee_tokens
                FROM entrevista_fragmentos
                WHERE {where_sql}
                ORDER BY id
                LIMIT %s
                """,
                (*params, batch_size),
            )
            rows = cur.fetchall()
    except Exception as e:
        _logger.error("neo4j_sync.fetch_error", error=str(e))
        return {"synced": 0, "failed": 0, "remaining": -1, "error": str(e)}
    
    if not rows:
        return {"synced": 0, "failed": 0, "remaining": 0}
    
    # Preparar datos para Neo4j
    neo_rows = []
    last_seen_id: Optional[str] = None
    for (
        frag_id,
        archivo,
        speaker,
        fragmento,
        char_len,
        actor_principal,
        metadata,
        par_idx,
        interviewer_tokens,
        interviewee_tokens,
    ) in rows:
        last_seen_id = frag_id
        if isinstance(metadata, (dict, list)):
            metadata_value = json.dumps(metadata, ensure_ascii=False)
        else:
            metadata_value = metadata

        neo_rows.append(
            {
                "project_id": project,
                "id": frag_id,
                "archivo": archivo,
                "par_idx": par_idx,
                "speaker": speaker,
                "fragmento": (fragmento or "")[:500],
                "char_len": char_len,
                "actor_principal": actor_principal,
                "metadata": metadata_value,
                "interviewer_tokens": interviewer_tokens,
                "interviewee_tokens": interviewee_tokens,
            }
        )
    
    synced = 0
    failed = 0
    
    try:
        merge_fragments(clients.neo4j, settings.neo4j.database, neo_rows)

        # Best-effort: marcar como sincronizados si la columna existe.
        if has_flag:
            db_ids = [row[0] for row in rows]
            with clients.postgres.cursor() as cur:
                cur.execute(
                    """
                    UPDATE entrevista_fragmentos
                    SET neo4j_synced = TRUE
                    WHERE id = ANY(%s)
                    """,
                    (db_ids,),
                )
            clients.postgres.commit()
        
        synced = len(rows)
        _logger.info("neo4j_sync.batch_complete", synced=synced)
        
    except Exception as e:
        _logger.error("neo4j_sync.merge_failed", error=str(e))
        failed = len(rows)
    
    # Contar restantes de forma consistente con el selector usado.
    remaining = -1
    try:
        with clients.postgres.cursor() as cur:
            where_parts = ["project_id = %s"]
            params2: list[Any] = [project]
            if has_flag:
                where_parts.append("neo4j_synced IS DISTINCT FROM TRUE")
            if last_seen_id:
                where_parts.append("id > %s")
                params2.append(last_seen_id)
            elif after_id:
                where_parts.append("id > %s")
                params2.append(after_id)
            where_sql = " AND ".join(where_parts)
            cur.execute(f"SELECT COUNT(*) FROM entrevista_fragmentos WHERE {where_sql}", tuple(params2))
            remaining = int(cur.fetchone()[0])
    except Exception:
        remaining = -1

    return {
        "synced": synced,
        "failed": failed,
        "remaining": remaining,
        "next_after_id": last_seen_id or after_id,
    }


def _parse_evidencia(value: Any, fragmento_id: Any | None = None) -> list[str]:
    if value is None:
        return [str(fragmento_id)] if fragmento_id else []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v is not None]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return [str(fragmento_id)] if fragmento_id else []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(v) for v in parsed if v is not None]
        except Exception:
            pass
        if "," in text:
            return [seg.strip() for seg in text.split(",") if seg.strip()]
        return [text]
    return [str(value)]


def sync_axial_relationships(
    clients: ServiceClients,
    settings: AppSettings,
    project: str,
    batch_size: int = 500,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Sincroniza analisis_axial (PG) hacia Neo4j creando Categoria/Codigo/REL.

    Args:
        project: ID del proyecto
        batch_size: Tamaño del batch
        offset: Offset para paginación simple

    Returns:
        Dict con synced, skipped, remaining counts
    """
    _logger.info("neo4j_sync.axial.start", project=project, batch_size=batch_size, offset=offset)

    if not check_neo4j_connection(clients, settings):
        _logger.error("neo4j_sync.axial.neo4j_unavailable")
        return {"synced": 0, "skipped": 0, "remaining": -1, "error": "Neo4j no disponible"}

    # Ensure constraints for Categoria/Codigo
    try:
        ensure_category_constraints(clients.neo4j, settings.neo4j.database)
        ensure_code_constraints(clients.neo4j, settings.neo4j.database)
    except Exception as e:
        _logger.warning("neo4j_sync.axial.constraints_failed", error=str(e)[:120])

    cols = _pg_get_table_columns(clients.postgres, "analisis_axial")
    project_col = "project_id" if "project_id" in cols else "proyecto"
    has_evidencia = "evidencia" in cols
    has_fragmento_id = "fragmento_id" in cols
    has_memo = "memo" in cols
    has_relacion = "relacion" in cols
    has_tipo_relacion = "tipo_relacion" in cols

    select_fields = [
        f"{project_col} AS project_id",
        "categoria",
        "codigo",
    ]
    if has_relacion:
        select_fields.append("relacion")
    if has_tipo_relacion:
        select_fields.append("tipo_relacion")
    if has_evidencia:
        select_fields.append("evidencia")
    if has_fragmento_id:
        select_fields.append("fragmento_id")
    if has_memo:
        select_fields.append("memo")

    order_by = "created_at" if "created_at" in cols else "categoria"

    try:
        with clients.postgres.cursor() as cur:
            cur.execute(
                f"""
                SELECT {', '.join(select_fields)}
                  FROM analisis_axial
                 WHERE {project_col} = %s
                 ORDER BY {order_by}, categoria, codigo
                 LIMIT %s OFFSET %s
                """,
                (project, batch_size, offset),
            )
            rows = cur.fetchall()
    except Exception as e:
        _logger.error("neo4j_sync.axial.fetch_error", error=str(e)[:200])
        return {"synced": 0, "skipped": 0, "remaining": -1, "error": str(e)}

    if not rows:
        return {"synced": 0, "skipped": 0, "remaining": 0, "offset": offset}

    def _get_idx(name: str) -> Optional[int]:
        return select_fields.index(name) if name in select_fields else None

    idx_project = _get_idx("project_id")
    idx_categoria = _get_idx("categoria")
    idx_codigo = _get_idx("codigo")
    idx_relacion = _get_idx("relacion")
    idx_tipo_relacion = _get_idx("tipo_relacion")
    idx_evidencia = _get_idx("evidencia")
    idx_fragmento_id = _get_idx("fragmento_id")
    idx_memo = _get_idx("memo")

    prepared = []
    skipped = 0
    for row in rows:
        project_id = row[idx_project] if idx_project is not None else project
        categoria = row[idx_categoria]
        codigo = row[idx_codigo]
        relacion = None
        if idx_relacion is not None:
            relacion = row[idx_relacion]
        if not relacion and idx_tipo_relacion is not None:
            relacion = row[idx_tipo_relacion]
        if not relacion or str(relacion) not in ALLOWED_REL_TYPES:
            skipped += 1
            continue

        evidencia = _parse_evidencia(
            row[idx_evidencia] if idx_evidencia is not None else None,
            row[idx_fragmento_id] if idx_fragmento_id is not None else None,
        )
        memo = row[idx_memo] if idx_memo is not None else None

        prepared.append(
            {
                "project_id": project_id,
                "categoria": categoria,
                "codigo": codigo,
                "relacion": str(relacion),
                "evidencia": evidencia,
                "memo": memo,
            }
        )

    try:
        merge_category_code_relationships(clients.neo4j, settings.neo4j.database, prepared)
    except Exception as e:
        _logger.error("neo4j_sync.axial.merge_failed", error=str(e)[:200])
        return {"synced": 0, "skipped": skipped, "remaining": -1, "error": str(e)}

    remaining = -1
    try:
        with clients.postgres.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM analisis_axial WHERE {project_col} = %s",
                (project,),
            )
            total = int(cur.fetchone()[0])
            remaining = max(0, total - (offset + len(rows)))
    except Exception:
        pass

    return {
        "synced": len(prepared),
        "skipped": skipped,
        "remaining": remaining,
        "offset": offset,
        "next_offset": offset + len(rows),
    }
