"""
Execute schema alignment against Azure PostgreSQL.
Run: python scripts/run_azure_migration.py
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

# Azure PostgreSQL connection
conn_params = {
    "host": os.getenv("PGHOST", "appjupter.postgres.database.azure.com"),
    "port": int(os.getenv("PGPORT", 5432)),
    "user": os.getenv("PGUSER", "Osvaldo"),
    "password": os.getenv("PGPASSWORD", "A51b91c5!"),
    "dbname": os.getenv("PGDATABASE", "entrevistas"),
    "sslmode": os.getenv("PGSSLMODE", "require"),
}

print(f"Connecting to: {conn_params['host']}:{conn_params['port']}/{conn_params['dbname']}")

conn = psycopg2.connect(**conn_params)
conn.autocommit = True
cur = conn.cursor()

# List of ALTER statements to execute
statements = [
    # 1. entrevista_fragmentos - add project_id (CRITICAL)
    "ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS project_id TEXT DEFAULT 'default'",
    "CREATE INDEX IF NOT EXISTS ix_fragmentos_project ON entrevista_fragmentos(project_id)",
    
    # 2. entrevista_fragmentos - other columns
    "ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS area_tematica TEXT",
    "ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS actor_principal TEXT",
    "ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS metadata JSONB",
    "ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
    "ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS speaker TEXT",
    "ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS interviewer_tokens INTEGER DEFAULT 0",
    "ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS interviewee_tokens INTEGER DEFAULT 0",
    "ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS requiere_protocolo_lluvia BOOLEAN DEFAULT FALSE",
    "ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS char_len INTEGER",
    
    # 3. analysis_insights - add all columns
    "ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'llm'",
    "ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS insight_type TEXT DEFAULT 'suggestion'",
    "ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS source_id TEXT",
    "ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS suggested_query JSONB",
    "ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS priority FLOAT DEFAULT 0.5",
    "ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'",
    "ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS execution_result JSONB",
    "ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS content TEXT",
    "ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS project_id TEXT DEFAULT 'default'",
    "ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
    "ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
    
    # 3b. Indexes for analysis_insights
    "CREATE INDEX IF NOT EXISTS ix_insights_project ON analysis_insights(project_id)",
    "CREATE INDEX IF NOT EXISTS ix_insights_status ON analysis_insights(status)",
    "CREATE INDEX IF NOT EXISTS ix_insights_type ON analysis_insights(insight_type)",
    "CREATE INDEX IF NOT EXISTS ix_insights_source ON analysis_insights(source_type)",
    
    # 4. app_sessions
    "ALTER TABLE app_sessions ADD COLUMN IF NOT EXISTS is_revoked BOOLEAN DEFAULT FALSE",
    "ALTER TABLE app_sessions ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ DEFAULT NOW()",
]

print(f"\nExecuting {len(statements)} statements...")

for i, sql in enumerate(statements, 1):
    try:
        cur.execute(sql)
        print(f"  [{i:02d}] ✅ {sql[:60]}...")
    except Exception as e:
        print(f"  [{i:02d}] ⚠️  {sql[:60]}... - {e}")

# Verify critical columns
print("\n=== Verification ===")
cur.execute("""
    SELECT table_name, column_name FROM information_schema.columns 
    WHERE table_name IN ('entrevista_fragmentos', 'analysis_insights', 'app_sessions')
    AND column_name IN ('project_id', 'source_type', 'status', 'area_tematica', 'is_revoked')
    ORDER BY table_name, column_name
""")
for row in cur.fetchall():
    print(f"  ✅ {row[0]}.{row[1]}")

cur.close()
conn.close()
print("\n=== DONE ===")
