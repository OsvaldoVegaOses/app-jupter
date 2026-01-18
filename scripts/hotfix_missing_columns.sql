-- Phase 0 Hotfix: Add missing columns detected at runtime
-- Date: 2026-01-03
-- Run via: Get-Content scripts/hotfix_missing_columns.sql | docker exec -i app_jupter-postgres-1 psql -U Osvaldo -d entrevistas

-- 1. Add area_tematica column to entrevista_fragmentos (referenced in list_interviews_summary)
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS area_tematica TEXT;

-- 2. Add status column to analysis_insights (referenced in list_insights)
-- This column should already exist per ensure_insights_table, but adding it just in case
ALTER TABLE analysis_insights ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';

-- 3. Add metadata column to entrevista_fragmentos (referenced in get_fragment_context)
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS metadata JSONB;

-- 4. Add updated_at column to entrevista_fragmentos
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Verify columns added
SELECT 'entrevista_fragmentos' as table_name, column_name 
FROM information_schema.columns 
WHERE table_name = 'entrevista_fragmentos' 
AND column_name IN ('area_tematica', 'metadata', 'updated_at', 'actor_principal')
UNION ALL
SELECT 'analysis_insights', column_name 
FROM information_schema.columns 
WHERE table_name = 'analysis_insights' AND column_name = 'status';
