"""List project_ids present in core tables (PostgreSQL).

Usage:
  ./.venv/Scripts/python.exe scripts/list_project_ids.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.clients import get_pg_connection, return_pg_connection
from app.settings import load_settings


def _print_table_counts(pg, table: str, limit: int = 20) -> None:
    with pg.cursor() as cur:
        cur.execute(
            f"""
            SELECT project_id, COUNT(*) AS cnt
            FROM {table}
            GROUP BY project_id
            ORDER BY COUNT(*) DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()

    print(f"\n{table} (top {limit}):")
    if not rows:
        print("  (no rows)")
        return
    for project_id, cnt in rows:
        print(f"  - {project_id}: {cnt}")


def main() -> int:
    settings = load_settings()
    pg = get_pg_connection(settings)
    try:
        _print_table_counts(pg, "entrevista_fragmentos")
        _print_table_counts(pg, "analisis_codigos_abiertos")
        _print_table_counts(pg, "analisis_axial")
        return 0
    finally:
        return_pg_connection(pg)


if __name__ == "__main__":
    raise SystemExit(main())
