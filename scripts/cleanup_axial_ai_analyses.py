from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Ensure project root is importable when running as a script.
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.clients import get_pg_connection, return_pg_connection
from app.postgres_block import cleanup_axial_ai_analyses
from app.settings import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AX-AI-05: Retención de axial_ai_analyses (por proyecto, por antigüedad)."
    )
    parser.add_argument("--project", required=True, help="ID del proyecto (ej: jd-007)")
    parser.add_argument(
        "--older-than-days",
        type=int,
        default=180,
        help="Eliminar artefactos con created_at anterior a N días (default: 180).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Ejecuta el borrado. Si no se indica, corre en dry-run (solo cuenta).",
    )
    parser.add_argument(
        "--env",
        default=None,
        help="Ruta a .env (opcional). Si no se especifica, usa APP_ENV_FILE o .env.",
    )

    args = parser.parse_args()

    settings = load_settings(args.env)
    conn = get_pg_connection(settings)
    try:
        result = cleanup_axial_ai_analyses(
            conn,
            project_id=args.project,
            older_than_days=int(args.older_than_days),
            dry_run=not bool(args.execute),
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
    finally:
        return_pg_connection(conn)


if __name__ == "__main__":
    main()

