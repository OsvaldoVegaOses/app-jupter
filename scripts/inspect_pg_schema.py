"""Inspect PostgreSQL table schema via app settings.

Usage (PowerShell):
    ./.venv/Scripts/python.exe scripts/inspect_pg_schema.py --table analisis_axial
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure repo-root imports work when executed as a script.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.clients import get_pg_connection, return_pg_connection
from app.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", default="public")
    parser.add_argument("--table", default="analisis_axial")
    args = parser.parse_args()

    settings = load_settings()
    pg = get_pg_connection(settings)
    try:
        cur = pg.cursor()
        cur.execute(
            """
            SELECT
                ordinal_position,
                column_name,
                data_type,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (args.schema, args.table),
        )
        rows = cur.fetchall()
        cur.close()

        if not rows:
            print(f"No columns found for {args.schema}.{args.table}")
            return 2

        print(f"Columns for {args.schema}.{args.table}:")
        for ordinal, name, dtype, nullable, default in rows:
            print(f"- {ordinal:>2} {name:<30} {dtype:<18} nullable={nullable:<3} default={default}")

        return 0
    finally:
        return_pg_connection(pg)


if __name__ == "__main__":
    raise SystemExit(main())
