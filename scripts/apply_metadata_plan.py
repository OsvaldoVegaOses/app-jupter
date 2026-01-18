"""Aplicar metadatos a entrevistas desde un plan JSON."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.clients import build_service_clients
from app.metadata_ops import apply_metadata_entries, load_plan_from_json
from app.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Actualiza metadatos (genero, actor, etc.) en PG/Qdrant/Neo4j"
    )
    parser.add_argument("--env", default=None, help="Ruta al archivo .env")
    parser.add_argument("--plan", type=Path, required=True, help="Archivo JSON con metadatos por entrevista")
    args = parser.parse_args()

    entries = load_plan_from_json(args.plan)
    settings = load_settings(args.env)
    clients = build_service_clients(settings)

    try:
        summary = apply_metadata_entries(clients, settings, entries)
    finally:
        clients.close()

    total_files = summary["total_files"]
    total_fragments = summary["total_fragments"]
    print(f"Metadatos aplicados a {total_fragments} fragmentos en {total_files} entrevistas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
