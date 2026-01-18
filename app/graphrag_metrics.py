"""
Métricas para GraphRAG Anti-Alucinaciones.

Sprint 15 - E4: Sistema de métricas para tracking de calidad de respuestas.

Este módulo proporciona:
    - Modelo de datos para métricas de consultas
    - Funciones de persistencia en PostgreSQL
    - Funciones de agregación para reportes
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

import structlog

_logger = structlog.get_logger()


@dataclass
class GraphRAGMetric:
    """Registro de métrica para una consulta GraphRAG."""
    
    query_id: str
    project_id: str
    timestamp: datetime
    query: str
    is_grounded: bool
    rejection_reason: Optional[str]
    fragments_count: int
    top_score: float
    confidence: str
    confidence_reason: str
    answer_length: int
    model: str
    
    @classmethod
    def from_response(
        cls,
        project_id: str,
        query: str,
        response: Dict[str, Any],
    ) -> "GraphRAGMetric":
        """Crea métricas desde una respuesta de graphrag_query()."""
        rejection = response.get("rejection", {})
        
        return cls(
            query_id=str(uuid.uuid4()),
            project_id=project_id,
            timestamp=datetime.utcnow(),
            query=query[:500],  # Truncar queries largas
            is_grounded=response.get("is_grounded", False),
            rejection_reason=rejection.get("reason") if rejection else None,
            fragments_count=len(response.get("evidence", [])),
            top_score=rejection.get("top_score", 0) if rejection else (
                response.get("evidence", [{}])[0].get("score", 0) if response.get("evidence") else 0
            ),
            confidence=response.get("confidence", "desconocido"),
            confidence_reason=response.get("confidence_reason", ""),
            answer_length=len(response.get("answer") or ""),
            model=response.get("model", "unknown"),
        )


def ensure_metrics_table(conn) -> None:
    """Crea tabla de métricas si no existe."""
    create_sql = """
    CREATE TABLE IF NOT EXISTS graphrag_metrics (
        id SERIAL PRIMARY KEY,
        query_id VARCHAR(64) UNIQUE NOT NULL,
        project_id VARCHAR(128) NOT NULL,
        timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        query TEXT NOT NULL,
        is_grounded BOOLEAN NOT NULL,
        rejection_reason TEXT,
        fragments_count INTEGER NOT NULL DEFAULT 0,
        top_score FLOAT NOT NULL DEFAULT 0,
        confidence VARCHAR(32) NOT NULL,
        confidence_reason TEXT,
        answer_length INTEGER NOT NULL DEFAULT 0,
        model VARCHAR(64) NOT NULL
    );
    
    CREATE INDEX IF NOT EXISTS idx_graphrag_metrics_project 
        ON graphrag_metrics(project_id);
    CREATE INDEX IF NOT EXISTS idx_graphrag_metrics_timestamp 
        ON graphrag_metrics(timestamp);
    CREATE INDEX IF NOT EXISTS idx_graphrag_metrics_grounded 
        ON graphrag_metrics(is_grounded);
    """
    
    try:
        with conn.cursor() as cur:
            cur.execute(create_sql)
        conn.commit()
        _logger.info("graphrag_metrics.table_ensured")
    except Exception as e:
        _logger.error("graphrag_metrics.table_error", error=str(e))
        conn.rollback()


def persist_metric(conn, metric: GraphRAGMetric) -> bool:
    """Persiste una métrica en la base de datos."""
    insert_sql = """
    INSERT INTO graphrag_metrics (
        query_id, project_id, timestamp, query, is_grounded,
        rejection_reason, fragments_count, top_score,
        confidence, confidence_reason, answer_length, model
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    )
    ON CONFLICT (query_id) DO NOTHING
    """
    
    try:
        with conn.cursor() as cur:
            cur.execute(insert_sql, (
                metric.query_id,
                metric.project_id,
                metric.timestamp,
                metric.query,
                metric.is_grounded,
                metric.rejection_reason,
                metric.fragments_count,
                metric.top_score,
                metric.confidence,
                metric.confidence_reason,
                metric.answer_length,
                metric.model,
            ))
        conn.commit()
        _logger.debug("graphrag_metrics.persisted", query_id=metric.query_id)
        return True
    except Exception as e:
        _logger.error("graphrag_metrics.persist_error", error=str(e))
        conn.rollback()
        return False


def get_metrics_summary(
    conn,
    project_id: str,
    days: int = 30,
) -> Dict[str, Any]:
    """
    Obtiene resumen de métricas para un proyecto.
    
    Returns:
        Dict con estadísticas agregadas
    """
    summary_sql = """
    SELECT 
        COUNT(*) as total_queries,
        SUM(CASE WHEN is_grounded THEN 1 ELSE 0 END) as grounded_count,
        SUM(CASE WHEN NOT is_grounded THEN 1 ELSE 0 END) as rejected_count,
        AVG(top_score) as avg_top_score,
        AVG(fragments_count) as avg_fragments,
        AVG(answer_length) as avg_answer_length,
        COUNT(DISTINCT confidence) as confidence_levels
    FROM graphrag_metrics
    WHERE project_id = %s
      AND timestamp > NOW() - INTERVAL '%s days'
    """
    
    confidence_sql = """
    SELECT confidence, COUNT(*) as count
    FROM graphrag_metrics
    WHERE project_id = %s
      AND timestamp > NOW() - INTERVAL '%s days'
    GROUP BY confidence
    """
    
    try:
        with conn.cursor() as cur:
            cur.execute(summary_sql, (project_id, days))
            row = cur.fetchone()
            
            if not row or row[0] == 0:
                return {
                    "total_queries": 0,
                    "grounded_rate": 0,
                    "rejection_rate": 0,
                    "avg_top_score": 0,
                    "avg_fragments": 0,
                    "confidence_distribution": {},
                    "period_days": days,
                }
            
            cur.execute(confidence_sql, (project_id, days))
            confidence_rows = cur.fetchall()
            confidence_dist = {r[0]: r[1] for r in confidence_rows}
            
            total = row[0]
            return {
                "total_queries": total,
                "grounded_count": row[1] or 0,
                "rejected_count": row[2] or 0,
                "grounded_rate": round((row[1] or 0) / total * 100, 1),
                "rejection_rate": round((row[2] or 0) / total * 100, 1),
                "avg_top_score": round(row[3] or 0, 3),
                "avg_fragments": round(row[4] or 0, 1),
                "avg_answer_length": round(row[5] or 0, 0),
                "confidence_distribution": confidence_dist,
                "period_days": days,
            }
            
    except Exception as e:
        _logger.error("graphrag_metrics.summary_error", error=str(e))
        return {"error": str(e)}


def get_recent_rejections(
    conn,
    project_id: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Obtiene rechazos recientes para análisis."""
    sql = """
    SELECT query_id, timestamp, query, rejection_reason, top_score, fragments_count
    FROM graphrag_metrics
    WHERE project_id = %s AND NOT is_grounded
    ORDER BY timestamp DESC
    LIMIT %s
    """
    
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (project_id, limit))
            rows = cur.fetchall()
            
            return [
                {
                    "query_id": r[0],
                    "timestamp": r[1].isoformat() if r[1] else None,
                    "query": r[2],
                    "rejection_reason": r[3],
                    "top_score": r[4],
                    "fragments_count": r[5],
                }
                for r in rows
            ]
    except Exception as e:
        _logger.error("graphrag_metrics.rejections_error", error=str(e))
        return []
