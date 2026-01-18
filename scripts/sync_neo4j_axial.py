"""Sync analisis_axial from Postgres to Neo4j.

Usage (PowerShell):
    ./.venv/Scripts/python.exe scripts/sync_neo4j_axial.py --project jd-009 --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from typing import cast

from neo4j import GraphDatabase

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.clients import ServiceClients, get_pg_connection, return_pg_connection
from app.neo4j_sync import sync_axial_relationships
from app.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--all", action="store_true", help="Loop until remaining == 0")
    args = parser.parse_args()

    settings = load_settings()
    pg = get_pg_connection(settings)
    driver = GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.username, settings.neo4j.password or ""),
    )

    try:
        offset = max(0, int(args.offset))
        while True:
            clients = cast(ServiceClients, type("C", (), {"postgres": pg, "neo4j": driver})())
            result = sync_axial_relationships(
                clients=clients,
                settings=settings,
                project=args.project,
                batch_size=max(50, min(int(args.batch_size), 2000)),
                offset=offset,
            )
            print(result)
            if not args.all:
                break
            remaining = result.get("remaining", -1)
            if remaining == 0:
                break
            offset = result.get("next_offset", offset)
    finally:
        return_pg_connection(pg)
        driver.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
