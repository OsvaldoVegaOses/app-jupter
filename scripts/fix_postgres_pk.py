"""
Script de utilidad para corregir secuencias de claves primarias en PostgreSQL.
Útil cuando se han insertado datos manualmente o tras migraciones que desincronizan las secuencias.
"""
import os
import sys
from app.settings import load_settings
import psycopg2

def fix_primary_key():
    settings = load_settings()
    dsn = f"host={settings.postgres.host} port={settings.postgres.port} dbname={settings.postgres.database} user={settings.postgres.username} password={settings.postgres.password}"
    
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    
    tables_to_fix = [
        {
            "table": "entrevista_fragmentos",
            "constraint": "entrevista_fragmentos_pkey",
            "new_pk": "(project_id, id)"
        },
        {
            "table": "analisis_codigos_abiertos",
            "constraint": "analisis_codigos_abiertos_pkey",
            "new_pk": "(project_id, fragmento_id, codigo)"
        },
        {
            "table": "analisis_axial",
            "constraint": "analisis_axial_pkey",
            "new_pk": "(project_id, categoria, codigo, relacion)"
        }
    ]

    try:
        for item in tables_to_fix:
            table = item["table"]
            constraint = item["constraint"]
            new_pk = item["new_pk"]
            
            print(f"Checking constraint on {table}...")
            cur.execute(f"""
                SELECT pg_get_constraintdef(c.oid)
                FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE c.conname = '{constraint}'
                  AND n.nspname = 'public'
            """)
            row = cur.fetchone()
            
            if row:
                print(f"  Current PK definition: {row[0]}")
                if "project_id" not in row[0]:
                    print(f"  Dropping old PK and adding composite PK {new_pk}...")
                    cur.execute(f"ALTER TABLE {table} DROP CONSTRAINT {constraint};")
                    cur.execute(f"ALTER TABLE {table} ADD PRIMARY KEY {new_pk};")
                    print("  PK updated successfully.")
                else:
                    print("  PK already includes project_id.")
            else:
                print(f"  PK constraint '{constraint}' not found. Attempting to add composite PK...")
                try:
                    cur.execute(f"ALTER TABLE {table} ADD PRIMARY KEY {new_pk};")
                    print("  PK added successfully.")
                except Exception as e:
                    print(f"  Could not add PK: {e}")
            print("-" * 40)

        conn.commit()
        print("Migration completed.")
        
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    fix_primary_key()
