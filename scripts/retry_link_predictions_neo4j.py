"""
Retry Neo4j sync for link_predictions with failed/unknown sync status.

Usage (PowerShell):
    python scripts/retry_link_predictions_neo4j.py --project jd-007 --batch-size 200
    python scripts/retry_link_predictions_neo4j.py --all --loop --interval 60
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from neo4j import GraphDatabase

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.clients import get_pg_connection, return_pg_connection
from app.neo4j_block import merge_axial_relationship
from app.neo4j_sync import check_neo4j_connection
from app.postgres_block import ensure_link_predictions_table, ensure_project_members_table
from app.settings import load_settings


def _fetch_candidates(pg, *, project: Optional[str], limit: int, cooldown_minutes: int) -> list[Dict[str, Any]]:
    ensure_link_predictions_table(pg)
    where = ["estado = 'validado'", "(neo4j_sync_status IS NULL OR neo4j_sync_status IN ('failed'))"]
    params: list[Any] = []
    if project:
        where.append("project_id = %s")
        params.append(project)
    if cooldown_minutes > 0:
        where.append("updated_at < NOW() - (%s * INTERVAL '1 minute')")
        params.append(int(cooldown_minutes))

    sql = f"""
    SELECT id, project_id, source_code, target_code, relation_type
    FROM link_predictions
    WHERE {' AND '.join(where)}
    ORDER BY updated_at ASC
    LIMIT %s
    """
    params.append(int(limit))
    with pg.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []
    return [
        {
            "id": r[0],
            "project_id": r[1],
            "source_code": r[2],
            "target_code": r[3],
            "relation_type": r[4],
        }
        for r in rows
    ]


def _update_sync_status(pg, prediction_id: int, status: str, error: Optional[str]) -> None:
    with pg.cursor() as cur:
        cur.execute(
            """
            UPDATE link_predictions
            SET neo4j_sync_status = %s,
                neo4j_sync_error = %s,
                neo4j_synced_at = CASE WHEN %s = 'success' THEN NOW() ELSE neo4j_synced_at END,
                updated_at = NOW()
            WHERE id = %s
            """,
            (status, error, status, prediction_id),
        )
    pg.commit()


def retry_once(
    *,
    project: Optional[str],
    batch_size: int,
    cooldown_minutes: int,
) -> Dict[str, int]:
    settings = load_settings()
    pg = get_pg_connection(settings)
    driver = GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.username, settings.neo4j.password or ""),
    )

    try:
        clients = type("C", (), {"postgres": pg, "neo4j": driver})()
        if not check_neo4j_connection(clients, settings):
            return {"synced": 0, "failed": 0, "remaining": -1}

        ensure_project_members_table(pg)

        candidates = _fetch_candidates(
            pg, project=project, limit=max(1, int(batch_size)), cooldown_minutes=cooldown_minutes
        )
        if not candidates:
            return {"synced": 0, "failed": 0, "remaining": 0}

        synced = 0
        failed = 0
        for row in candidates:
            try:
                merge_axial_relationship(
                    driver=driver,
                    database=settings.neo4j.database,
                    project_id=row["project_id"],
                    source_code=row["source_code"],
                    target_code=row["target_code"],
                    relation_type=row["relation_type"] or "asociado_con",
                )
                _update_sync_status(pg, int(row["id"]), "success", None)
                synced += 1
            except Exception as exc:  # noqa: BLE001
                _update_sync_status(pg, int(row["id"]), "failed", str(exc)[:200])
                failed += 1

        remaining = -1
        try:
            remaining = len(
                _fetch_candidates(pg, project=project, limit=1, cooldown_minutes=cooldown_minutes)
            )
        except Exception:
            remaining = -1

        return {"synced": synced, "failed": failed, "remaining": remaining}
    finally:
        return_pg_connection(pg)
        driver.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=None, help="Proyecto (opcional). Si no, procesa todos.")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--cooldown-minutes", type=int, default=2)
    parser.add_argument("--loop", action="store_true", help="Reintenta en loop")
    parser.add_argument("--interval", type=int, default=60, help="Segundos entre reintentos")
    args = parser.parse_args()

    if args.loop:
        while True:
            result = retry_once(
                project=args.project,
                batch_size=args.batch_size,
                cooldown_minutes=args.cooldown_minutes,
            )
            print(result)
            time.sleep(max(10, int(args.interval)))
    else:
        result = retry_once(
            project=args.project,
            batch_size=args.batch_size,
            cooldown_minutes=args.cooldown_minutes,
        )
        print(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
