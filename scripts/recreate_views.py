"""
Script para regenerar las vistas materializadas en PostgreSQL.
Debe ejecutarse después de cambios en el esquema o para refrescar datos agregados complejos.
"""
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from app.settings import load_settings
from app.postgres_block import _TRANSVERSAL_VIEW_ORDER, _TRANSVERSAL_VIEW_DEFINITIONS
import psycopg2

def recreate_views():
    settings = load_settings()
    
    print(f"Connecting to Postgres at {settings.postgres.host}...")
    pg = psycopg2.connect(
        host=settings.postgres.host,
        port=settings.postgres.port,
        user=settings.postgres.username,
        password=settings.postgres.password,
        dbname=settings.postgres.database
    )
    
    print("Recreating materialized views...")
    with pg.cursor() as cur:
        for view_name in reversed(_TRANSVERSAL_VIEW_ORDER):
            print(f"Dropping view {view_name}...")
            cur.execute(f"DROP MATERIALIZED VIEW IF EXISTS {view_name}")
        
        for view_name in _TRANSVERSAL_VIEW_ORDER:
            print(f"Creating view {view_name}...")
            cur.execute(_TRANSVERSAL_VIEW_DEFINITIONS[view_name])
            
        print("Refreshing views...")
        for view_name in _TRANSVERSAL_VIEW_ORDER:
            cur.execute(f"REFRESH MATERIALIZED VIEW {view_name}")
            
    pg.commit()
    pg.close()
    print("Done.")

if __name__ == "__main__":
    recreate_views()
