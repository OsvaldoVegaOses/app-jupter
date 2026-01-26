from __future__ import annotations

from pathlib import Path
import sys

# Ensure project root is importable when running as a script.
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.clients import get_pg_connection, return_pg_connection
from app.settings import load_settings


MIGRATIONS = [
    "migrations/007_codigos_candidatos.sql",
    "migrations/008_schema_alignment.sql",
    "migrations/008_interview_files.sql",
    "migrations/010_neo4j_sync_tracking.sql",
    "migrations/012_add_is_deleted_to_proyectos.sql",
    "migrations/013_codes_catalog_ontology.sql",
    "migrations/014_code_id_columns.sql",
    "migrations/015_ontology_freeze.sql",
    "migrations/017_epistemic_mode.sql",
    "migrations/018_code_id_propagation.sql",
    "migrations/019_axial_ledger_states_code_id.sql",
    "migrations/020_axial_ai_analyses.sql",
    "migrations/021_axial_ai_evidence.sql",
    "migrations/022_link_predictions_neo4j_sync_status.sql",
    "migrations/023_link_predictions_reopen.sql",
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
                print("OK")
            except Exception as exc:
                conn.rollback()
                print(f"FAILED: {rel_path} -> {exc}")
                raise
    finally:
        return_pg_connection(conn)


if __name__ == "__main__":
    run_migrations()
