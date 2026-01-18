from __future__ import annotations

from pathlib import Path

from app.clients import get_pg_connection, return_pg_connection
from app.settings import load_settings


MIGRATIONS = [
    "migrations/007_codigos_candidatos.sql",
    "migrations/008_schema_alignment.sql",
    "migrations/008_interview_files.sql",
    "migrations/010_neo4j_sync_tracking.sql",
    "migrations/012_add_is_deleted_to_proyectos.sql",
]


def run_migrations() -> None:
    settings = load_settings()
    conn = get_pg_connection(settings)

    try:
        for rel_path in MIGRATIONS:
            path = Path(rel_path)
            if not path.exists():
                raise FileNotFoundError(f"No existe: {rel_path}")
            print(f"Running {rel_path}...")
            sql = path.read_text(encoding="utf-8")
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                conn.commit()
                print("✅ OK")
            except Exception as exc:
                conn.rollback()
                print(f"❌ Failed: {rel_path} -> {exc}")
                raise
    finally:
        return_pg_connection(conn)


if __name__ == "__main__":
    run_migrations()
