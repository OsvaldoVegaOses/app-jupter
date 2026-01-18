-- Phase 0.1: PostgreSQL Schema Alignment (CORRECTED - v2)
-- Date: 2026-01-02/03
-- IMPORTANT: This script is idempotent and safe to re-run

-- 1. App Sessions table - add is_revoked and last_active_at WITH DEFAULTS
ALTER TABLE app_sessions ADD COLUMN IF NOT EXISTS is_revoked BOOLEAN DEFAULT FALSE;
ALTER TABLE app_sessions ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ DEFAULT NOW();

-- 2. Analysis insights - add project_id with NOT NULL and default
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'analysis_insights' AND column_name = 'project_id') THEN
        ALTER TABLE analysis_insights ADD COLUMN project_id TEXT NOT NULL DEFAULT 'default';
    END IF;
END;
$$;
CREATE INDEX IF NOT EXISTS idx_insights_project ON analysis_insights(project_id);

-- 3. Interview fragments - add actor_principal
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS actor_principal TEXT;

-- 4. Axial analysis - add relacion column and CORRECT unique index
ALTER TABLE analisis_axial ADD COLUMN IF NOT EXISTS relacion TEXT;

-- Create unique index with NEW pattern: (project_id, categoria, codigo, relacion)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_axial_composite_unique') THEN
        CREATE UNIQUE INDEX idx_axial_composite_unique 
        ON analisis_axial(project_id, categoria, codigo, relacion);
    END IF;
EXCEPTION
    WHEN unique_violation THEN
        RAISE NOTICE 'Cannot create unique index - duplicates exist in analisis_axial';
    WHEN OTHERS THEN
        RAISE NOTICE 'Index creation note: %', SQLERRM;
END;
$$;

-- Verify all changes applied
SELECT 'app_sessions' as table_name, column_name, data_type, column_default
FROM information_schema.columns 
WHERE table_name = 'app_sessions' AND column_name IN ('is_revoked', 'last_active_at')
UNION ALL
SELECT 'analysis_insights', column_name, data_type, column_default
FROM information_schema.columns 
WHERE table_name = 'analysis_insights' AND column_name = 'project_id'
UNION ALL
SELECT 'entrevista_fragmentos', column_name, data_type, column_default
FROM information_schema.columns 
WHERE table_name = 'entrevista_fragmentos' AND column_name = 'actor_principal'
UNION ALL
SELECT 'analisis_axial', column_name, data_type, column_default
FROM information_schema.columns 
WHERE table_name = 'analisis_axial' AND column_name = 'relacion';

-- Show indexes
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename IN ('analysis_insights', 'analisis_axial')
AND indexname LIKE 'idx_%';
