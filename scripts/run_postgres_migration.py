"""
Ejecuta migraciones de esquema en PostgreSQL.
Lee el archivo migrations/postgres_backfill_and_indexes.sql.
"""
import os
import sys
from pathlib import Path
import psycopg2

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from app.settings import load_settings

def run_migration():
    settings = load_settings()
    
    print(f"Connecting to Postgres at {settings.postgres.host}...")
    conn = psycopg2.connect(
        host=settings.postgres.host,
        port=settings.postgres.port,
        dbname=settings.postgres.database,
        user=settings.postgres.username,
        password=settings.postgres.password,
    )
    conn.set_client_encoding("UTF8")
    
    migration_file = Path(__file__).parent.parent / "migrations" / "postgres_backfill_and_indexes.sql"
    if not migration_file.exists():
        print(f"Migration file not found: {migration_file}")
        return

    print(f"Reading migration file: {migration_file}")
    sql = migration_file.read_text(encoding="utf-8")
    
    try:
        with conn.cursor() as cur:
            print("Executing SQL...")
            cur.execute(sql)
        conn.commit()
        print("Migration executed successfully.")
    except Exception as e:
        conn.rollback()
        print(f"Error executing migration: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()
