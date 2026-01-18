"""
Validación y verificación de calidad del análisis cualitativo.

Este módulo implementa técnicas de validación propias de investigación cualitativa:

1. Saturación teórica:
   - saturation_curve(): Curva de códigos nuevos por entrevista
   - Detecta plateau que indica saturación (no aparecen códigos nuevos)

2. Outliers semánticos:
   - semantic_outliers(): Fragmentos atípicos que no encajan con el corpus
   - Útil para identificar temas emergentes o errores de codificación

3. Member checking:
   - member_checking(): Prepara paquetes para validar con participantes
   - Agrupa fragmentos y códigos por actor/entrevista

4. Triangulación de fuentes:
   - neo4j_source_overlap(): Verifica códigos desde múltiples fuentes
   - Aumenta credibilidad del análisis

Funciones:
    - saturation_curve(): Curva de saturación teórica
    - semantic_outliers(): Detecta fragmentos atípicos
    - member_checking(): Paquetes para validación con participantes
    - neo4j_source_overlap(): Triangulación de fuentes
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

import structlog
from qdrant_client.models import Filter, FieldCondition, MatchValue

from .clients import ServiceClients
from .postgres_block import (
    cumulative_code_curve,
    evaluate_curve_plateau,
    fetch_recent_fragments,
    member_checking_packets,
)
from .settings import AppSettings

_logger = structlog.get_logger()


def saturation_curve(pg_conn, *, project: Optional[str] = None, window: int = 3, threshold: int = 0) -> Dict[str, Any]:
    curve = cumulative_code_curve(pg_conn, project)
    plateau = evaluate_curve_plateau(curve, window=window, threshold=threshold)
    return {
        "curve": curve,
        "plateau": plateau,
        "total_codigos": curve[-1]["codigos_acumulados"] if curve else 0,
    }


def _build_exclusion_filter(fragment_id: str, project_id: str, speaker: Optional[str]) -> Filter:
    must = [FieldCondition(key="project_id", match=MatchValue(value=project_id))]
    must_not = [FieldCondition(key="id", match=MatchValue(value=fragment_id))]
    if speaker:
        must.append(FieldCondition(key="speaker", match=MatchValue(value=speaker)))
    else:
        must_not.append(FieldCondition(key="speaker", match=MatchValue(value="interviewer")))
    return Filter(must=must, must_not=must_not)


def semantic_outliers(
    clients: ServiceClients,
    settings: AppSettings,
    *,
    project: Optional[str] = None,
    fragment_ids: Optional[Sequence[str]] = None,
    archivo: Optional[str] = None,
    limit: int = 25,
    neighbor_k: int = 2,
    threshold: float = 0.8,
) -> Dict[str, Any]:
    pg_conn = clients.postgres
    project_id = project or "default"
    speaker_filter = "interviewee"
    if fragment_ids:
        rows = []
        for fid in fragment_ids:
            sql = "SELECT id, archivo, embedding, metadata, updated_at FROM entrevista_fragmentos WHERE id = %s AND project_id = %s"
            with pg_conn.cursor() as cur:
                cur.execute(sql, (fid, project_id))
                row = cur.fetchone()
            if row:
                rows.append({
                    "fragmento_id": row[0],
                    "archivo": row[1],
                    "embedding": row[2],
                    "metadata": row[3],
                    "updated_at": row[4],
                })
    else:
        rows = fetch_recent_fragments(pg_conn, project=project, archivo=archivo, limit=limit)

    results: List[Dict[str, Any]] = []
    outliers = 0

    for row in rows:
        embedding = row.get("embedding")
        fragment_id = row.get("fragmento_id")
        if not embedding or fragment_id is None:
            continue

        search_filter = _build_exclusion_filter(fragment_id, project_id, speaker_filter)
        response = clients.qdrant.query_points(
            collection_name=settings.qdrant.collection,
            query=embedding,
            limit=neighbor_k,
            with_payload=True,
            query_filter=search_filter,
        )
        neighbors = [
            {
                "fragmento_id": str(point.id),
                "score": point.score,
                "archivo": (point.payload or {}).get("archivo"),
            }
            for point in response.points
        ]
        best_score = neighbors[0]["score"] if neighbors else 0.0
        is_outlier = best_score < threshold
        if is_outlier:
            outliers += 1
        results.append(
            {
                "fragmento_id": fragment_id,
                "archivo": row.get("archivo"),
                "metadata": row.get("metadata"),
                "updated_at": row.get("updated_at"),
                "best_score": best_score,
                "threshold": threshold,
                "outlier": is_outlier,
                "neighbors": neighbors,
            }
        )

    return {
        "total_fragmentos": len(results),
        "outliers": outliers,
        "threshold": threshold,
        "detalles": results,
    }


def member_checking(
    clients: ServiceClients,
    *,
    project: Optional[str] = None,
    actor_principal: Optional[str] = None,
    archivo: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    packets = member_checking_packets(
        clients.postgres,
        project=project,
        actor_principal=actor_principal,
        archivo=archivo,
        limit=limit,
    )
    return {
        "actor_principal": actor_principal,
        "archivo": archivo,
        "total_paquetes": len(packets),
        "paquetes": packets,
    }


def neo4j_source_overlap(
    clients: ServiceClients,
    settings: AppSettings,
    *,
    project: Optional[str] = None,
    limit: int = 25,
) -> Dict[str, Any]:
    project_id = project or "default"
    query = """
        MATCH (s)-[:TIENE_FRAGMENTO]->(f:Fragmento {project_id: $project_id})-[:TIENE_CODIGO]->(cod:Codigo {project_id: $project_id})
        OPTIONAL MATCH (cat:Categoria {project_id: $project_id})-[:REL]->(cod)
        WITH labels(s) AS labels, cat.nombre AS categoria
        UNWIND labels AS etiqueta
        WITH etiqueta, categoria
        WHERE etiqueta IN ['Entrevista', 'Documento']
        RETURN etiqueta AS fuente, categoria, COUNT(*) AS conteo
        ORDER BY conteo DESC
        LIMIT $limit
    """
    with clients.neo4j.session(database=settings.neo4j.database) as session:
        data = session.run(query, limit=limit, project_id=project_id).data()

    resumen: Dict[str, Dict[str, int]] = {}
    for row in data:
        fuente = row.get("fuente")
        categoria = row.get("categoria")
        conteo = row.get("conteo")
        resumen.setdefault(fuente, {})[categoria] = conteo
    return {
        "limit": limit,
        "categorias_por_fuente": resumen,
    }
