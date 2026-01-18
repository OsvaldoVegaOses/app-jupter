-- Complete schema alignment for Azure PostgreSQL
-- Use psql or any PostgreSQL client with Azure connection
-- Connection: appjupter.postgres.database.azure.com / Osvaldo / entrevistas

-- 1. Add project_id to entrevista_fragmentos (CRITICAL)
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT 'default';
CREATE INDEX IF NOT EXISTS ix_fragmentos_project ON entrevista_fragmentos(project_id);

-- 2. Add all missing columns to entrevista_fragmentos
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS area_tematica TEXT;
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS actor_principal TEXT;
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS metadata JSONB;
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS speaker TEXT;
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS interviewer_tokens INTEGER DEFAULT 0;
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS interviewee_tokens INTEGER DEFAULT 0;
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS requiere_protocolo_lluvia BOOLEAN DEFAULT FALSE;
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS char_len INTEGER;

-- 3. Fix analysis_insights table - add missing columns
ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'llm';
ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS insight_type TEXT DEFAULT 'suggestion';
ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS source_id TEXT;
ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS suggested_query JSONB;
ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS priority FLOAT DEFAULT 0.5;
ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';
ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS execution_result JSONB;
ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS content TEXT;
ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Create indexes for analysis_insights
CREATE INDEX IF NOT EXISTS ix_insights_project ON analysis_insights(project_id);
CREATE INDEX IF NOT EXISTS ix_insights_status ON analysis_insights(status);
CREATE INDEX IF NOT EXISTS ix_insights_type ON analysis_insights(insight_type);
CREATE INDEX IF NOT EXISTS ix_insights_source ON analysis_insights(source_type);

-- 4. App sessions table updates
ALTER TABLE app_sessions ADD COLUMN IF NOT EXISTS is_revoked BOOLEAN DEFAULT FALSE;
ALTER TABLE app_sessions ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ DEFAULT NOW();

-- Verify
SELECT table_name, column_name FROM information_schema.columns 
WHERE table_name IN ('entrevista_fragmentos', 'analysis_insights', 'app_sessions')
AND column_name IN ('project_id', 'source_type', 'status', 'area_tematica', 'is_revoked')
ORDER BY table_name, column_name;
