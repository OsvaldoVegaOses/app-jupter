"""Apply migration 017: Add epistemic_mode column to proyectos."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import psycopg2

def main():
    # Build connection string from PG* variables
    conn_params = {
        'host': os.environ.get('PGHOST'),
        'port': os.environ.get('PGPORT', '5432'),
        'user': os.environ.get('PGUSER'),
        'password': os.environ.get('PGPASSWORD'),
        'dbname': os.environ.get('PGDATABASE'),
        'sslmode': os.environ.get('PGSSLMODE', 'require'),
    }
    conn = psycopg2.connect(**conn_params)
    cur = conn.cursor()
    
    print("Applying migration 017: epistemic_mode...")
    
    # 1. Add column
    try:
        cur.execute("""
            ALTER TABLE proyectos 
            ADD COLUMN IF NOT EXISTS epistemic_mode TEXT 
            DEFAULT 'constructivist'
        """)
        conn.commit()
        print("✓ Column epistemic_mode added")
    except Exception as e:
        conn.rollback()
        print(f"Column might already exist: {e}")
    
    # 2. Add constraint
    try:
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint 
                    WHERE conname = 'chk_epistemic_mode'
                ) THEN
                    ALTER TABLE proyectos 
                    ADD CONSTRAINT chk_epistemic_mode 
                    CHECK (epistemic_mode IN ('constructivist', 'post_positivist'));
                END IF;
            END $$
        """)
        conn.commit()
        print("✓ Constraint chk_epistemic_mode added")
    except Exception as e:
        conn.rollback()
        print(f"Constraint error: {e}")
    
    # 3. Update NULL values
    try:
        cur.execute("UPDATE proyectos SET epistemic_mode = 'constructivist' WHERE epistemic_mode IS NULL")
        conn.commit()
        print(f"✓ Updated {cur.rowcount} rows with default value")
    except Exception as e:
        conn.rollback()
        print(f"Update error: {e}")
    
    # 4. Create index
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_proyectos_epistemic_mode ON proyectos(epistemic_mode)")
        conn.commit()
        print("✓ Index created")
    except Exception as e:
        conn.rollback()
        print(f"Index error: {e}")
    
    # 5. Verify
    cur.execute("SELECT id, name, epistemic_mode FROM proyectos LIMIT 5")
    print("\nVerification (first 5 projects):")
    for row in cur.fetchall():
        print(f"  {row}")
    
    cur.close()
    conn.close()
    print("\n✓ Migration 017 applied successfully!")

if __name__ == "__main__":
    main()
