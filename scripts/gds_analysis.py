"""Ejecuta algoritmos GDS sobre el grafo axial desde la línea de comandos."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a script from the repo root or from the scripts/ folder.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.axial import run_gds_analysis, AxialError
from app.clients import build_service_clients
from app.logging_utils import configure_logging
from app.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecuta algoritmos GDS sobre el grafo axial")
    parser.add_argument("--env", default=None, help="Ruta al archivo .env")
    parser.add_argument("--project", default="default", help="Project ID (project_id)")
    parser.add_argument("--algorithm", required=True, choices=["louvain", "pagerank", "betweenness"], help="Algoritmo de GDS a ejecutar")
    parser.add_argument("--persist", action="store_true", help="Si se indica, persiste resultados como propiedades")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logger = configure_logging(args.log_level)
    settings = load_settings(args.env)
    clients = build_service_clients(settings)

    try:
        try:
            results = run_gds_analysis(clients, settings, args.algorithm, persist=bool(args.persist), project=args.project)
        except AxialError as exc:
            logger.error("gds.analysis.error", algorithm=args.algorithm, error=str(exc))
            print(f"Error: {exc}")
            return 1
    finally:
        clients.close()

    for row in results:
        etiquetas = ",".join(row.get("etiquetas", []))
        if "community_id" in row:
            print(f"{row['nombre']} [{etiquetas}] -> comunidad {row['community_id']}")
        else:
            print(f"{row['nombre']} [{etiquetas}] -> score {row['score']:.4f}")
    logger.info("gds.analysis.complete", algorithm=args.algorithm, resultados=len(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
