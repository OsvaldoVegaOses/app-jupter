from app.clients import get_pg_connection
from app.settings import load_settings

def run_migration():
    print("Running migration 008_interview_files.sql...")
    s = load_settings()
    c = get_pg_connection(s)
    
    with open("migrations/008_interview_files.sql", "r", encoding="utf-8") as f:
        sql = f.read()
        
    try:
        cur = c.cursor()
        cur.execute(sql)
        c.commit()
        print("✅ Migration successful!")
    except Exception as e:
        c.rollback()
        print(f"❌ Migration failed: {e}")
    finally:
        c.close()

if __name__ == "__main__":
    run_migration()
