-- =============================================================================
-- Fix Schema Mismatch: entrevista_fragmentos column naming
-- =============================================================================
-- Date: 2026-01-04
-- Issue: init_schema.sql uses fragmento_id, but postgres_block.py expects id
-- Run: Get-Content scripts/fix_fragmentos_id_column.sql | docker exec -i app_jupter-postgres-1 psql -U Osvaldo -d entrevistas
-- =============================================================================

-- Step 1: Check if table exists and what columns it has
DO $$
DECLARE
    has_fragmento_id BOOLEAN;
    has_id BOOLEAN;
BEGIN
    -- Check for fragmento_id column
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'entrevista_fragmentos' AND column_name = 'fragmento_id'
    ) INTO has_fragmento_id;
    
    -- Check for id column
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'entrevista_fragmentos' AND column_name = 'id'
    ) INTO has_id;
    
    IF has_fragmento_id AND NOT has_id THEN
        RAISE NOTICE 'Found fragmento_id column, will rename to id';
    ELSIF has_id THEN
        RAISE NOTICE 'Column id already exists, no rename needed';
    ELSE
        RAISE NOTICE 'Table may not exist or has different schema';
    END IF;
END;
$$;

-- Step 2: Rename fragmento_id to id if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'entrevista_fragmentos' AND column_name = 'fragmento_id'
    ) THEN
        ALTER TABLE entrevista_fragmentos RENAME COLUMN fragmento_id TO id;
        RAISE NOTICE 'Renamed fragmento_id to id';
    END IF;
END;
$$;

-- Step 3: Rename proyecto to project_id if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'entrevista_fragmentos' AND column_name = 'proyecto'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'entrevista_fragmentos' AND column_name = 'project_id'
    ) THEN
        ALTER TABLE entrevista_fragmentos RENAME COLUMN proyecto TO project_id;
        RAISE NOTICE 'Renamed proyecto to project_id';
    END IF;
END;
$$;

-- Step 4: Rename idx to par_idx if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'entrevista_fragmentos' AND column_name = 'idx'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'entrevista_fragmentos' AND column_name = 'par_idx'
    ) THEN
        ALTER TABLE entrevista_fragmentos RENAME COLUMN idx TO par_idx;
        RAISE NOTICE 'Renamed idx to par_idx';
    END IF;
END;
$$;

-- Step 5: Add missing columns with defaults
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS project_id TEXT DEFAULT 'default';
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS par_idx INT DEFAULT 0;
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS embedding DOUBLE PRECISION[];
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS char_len INT DEFAULT 0;
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS sha256 TEXT DEFAULT '';
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS area_tematica TEXT;
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS actor_principal TEXT;
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS requiere_protocolo_lluvia BOOLEAN;
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS metadata JSONB;
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS speaker TEXT;
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS interviewer_tokens INT DEFAULT 0;
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS interviewee_tokens INT DEFAULT 0;
ALTER TABLE entrevista_fragmentos ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Step 6: Make project_id NOT NULL after setting defaults
UPDATE entrevista_fragmentos SET project_id = 'default' WHERE project_id IS NULL;

-- Step 7: Create indexes expected by postgres_block.py
CREATE UNIQUE INDEX IF NOT EXISTS ux_ef_project_fragment ON entrevista_fragmentos(project_id, id);
CREATE INDEX IF NOT EXISTS ix_ef_project_id ON entrevista_fragmentos(project_id);
CREATE INDEX IF NOT EXISTS ix_ef_project_archivo ON entrevista_fragmentos(project_id, archivo);
CREATE INDEX IF NOT EXISTS ix_ef_archivo ON entrevista_fragmentos(archivo);
CREATE INDEX IF NOT EXISTS ix_ef_charlen ON entrevista_fragmentos(char_len);
CREATE INDEX IF NOT EXISTS ix_ef_area ON entrevista_fragmentos(area_tematica);
CREATE INDEX IF NOT EXISTS ix_ef_actor ON entrevista_fragmentos(actor_principal);
CREATE INDEX IF NOT EXISTS ix_ef_created_at ON entrevista_fragmentos(created_at);
CREATE INDEX IF NOT EXISTS ix_ef_speaker ON entrevista_fragmentos(speaker);

-- Step 8: Verify final schema
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns 
WHERE table_name = 'entrevista_fragmentos'
ORDER BY ordinal_position;

DO $$
BEGIN
    RAISE NOTICE '=== Schema fix complete! ===';
END;
$$;
