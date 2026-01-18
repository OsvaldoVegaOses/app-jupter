"""
Script temporal para ejecutar migraciones de PostgreSQL.
"""
import psycopg2
import os

def main():
    conn = psycopg2.connect(
        host='appjupter.postgres.database.azure.com',
        port=5432,
        user='Osvaldo',
        password='A51b91c5!',
        dbname='entrevistas',
        sslmode='require'
    )
    cur = conn.cursor()
    
    # 1. Check existing tables
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    tables = [r[0] for r in cur.fetchall()]
    print("=== Existing tables ===")
    for t in tables:
        print(f"  - {t}")
    
    # 2. Check if codigos_candidatos exists
    cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'codigos_candidatos'")
    cols = cur.fetchall()
    print("\n=== codigos_candidatos columns ===")
    if cols:
        for c in cols:
            print(f"  {c[0]}: {c[1]}")
    else:
        print("  TABLE DOES NOT EXIST - Will create!")
        
    # 3. Check if discovery_navigation_log exists
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'discovery_navigation_log'")
    discovery_cols = cur.fetchall()
    print("\n=== discovery_navigation_log columns ===")
    if discovery_cols:
        for c in discovery_cols:
            print(f"  {c[0]}")
    else:
        print("  TABLE DOES NOT EXIST - Will create!")
    
    # 4. Execute migration 007_codigos_candidatos.sql
    print("\n=== Executing 007_codigos_candidatos.sql ===")
    try:
        with open('migrations/007_codigos_candidatos.sql', 'r', encoding='utf-8') as f:
            sql = f.read()
        cur.execute(sql)
        conn.commit()
        print("  SUCCESS!")
    except Exception as e:
        print(f"  Error: {e}")
        conn.rollback()
    
    # 5. Execute postgres_backfill_and_indexes.sql
    print("\n=== Executing postgres_backfill_and_indexes.sql ===")
    try:
        with open('migrations/postgres_backfill_and_indexes.sql', 'r', encoding='utf-8') as f:
            sql = f.read()
        cur.execute(sql)
        conn.commit()
        print("  SUCCESS!")
    except Exception as e:
        print(f"  Error: {e}")
        conn.rollback()
    
    # 6. Create discovery_navigation_log if not exists
    print("\n=== Creating discovery_navigation_log table ===")
    try:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS discovery_navigation_log (
            id SERIAL PRIMARY KEY,
            project_id TEXT NOT NULL,
            busqueda_id UUID DEFAULT gen_random_uuid(),
            busqueda_origen_id UUID,
            positivos TEXT[],
            negativos TEXT[],
            target_text TEXT,
            fragments_count INT,
            codigos_sugeridos TEXT[],
            refinamientos_aplicados JSONB,
            ai_synthesis TEXT,
            action_taken TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_dnl_project ON discovery_navigation_log(project_id);
        CREATE INDEX IF NOT EXISTS ix_dnl_busqueda ON discovery_navigation_log(busqueda_id);
        CREATE INDEX IF NOT EXISTS ix_dnl_origen ON discovery_navigation_log(busqueda_origen_id);
        CREATE INDEX IF NOT EXISTS ix_dnl_created ON discovery_navigation_log(created_at);
        """)
        conn.commit()
        print("  SUCCESS!")
    except Exception as e:
        print(f"  Error: {e}")
        conn.rollback()
    
    # 7. Verify final state
    print("\n=== Final verification ===")
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'codigos_candidatos'")
    cols = cur.fetchall()
    print(f"codigos_candidatos has {len(cols)} columns: {[c[0] for c in cols]}")
    
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'discovery_navigation_log'")
    cols = cur.fetchall()
    print(f"discovery_navigation_log has {len(cols)} columns: {[c[0] for c in cols]}")
    
    conn.close()
    print("\nDone!")

if __name__ == "__main__":
    main()
