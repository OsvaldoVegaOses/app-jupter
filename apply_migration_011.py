from __future__ import annotations

from app.clients import get_pg_connection, return_pg_connection
from app.settings import load_settings


def run_migration() -> None:
    print("Running migration 011_stage0_preparacion.sql...")
    s = load_settings()
    c = get_pg_connection(s)

    with open("migrations/011_stage0_preparacion.sql", "r", encoding="utf-8") as f:
        sql = f.read()

    try:
        cur = c.cursor()
        cur.execute(sql)
        c.commit()
        print("✅ Migration successful!")
    except Exception as e:  # noqa: BLE001
        c.rollback()
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        return_pg_connection(c)


if __name__ == "__main__":
    run_migration()
