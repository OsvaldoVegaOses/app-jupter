-- Migration 017: Epistemic Mode per Project
-- Adds epistemic_mode column to proyectos table for differentiated prompts
-- Values: 'constructivist' (Charmaz) | 'post_positivist' (Glaser/Strauss)

-- =============================================================================
-- 1. Add epistemic_mode column with CHECK constraint
-- =============================================================================
ALTER TABLE proyectos 
ADD COLUMN IF NOT EXISTS epistemic_mode TEXT 
DEFAULT 'constructivist';

-- Add constraint if not exists (PostgreSQL 12+ syntax)
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
END $$;

-- =============================================================================
-- 2. Index for queries filtering by epistemic mode
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_proyectos_epistemic_mode 
ON proyectos(epistemic_mode);

-- =============================================================================
-- 3. Update existing projects to have explicit mode (if NULL)
-- =============================================================================
UPDATE proyectos 
SET epistemic_mode = 'constructivist' 
WHERE epistemic_mode IS NULL;

-- =============================================================================
-- 4. Documentation
-- =============================================================================
COMMENT ON COLUMN proyectos.epistemic_mode IS 
'Modo epistemológico del proyecto: constructivist (Charmaz, gerundios/in-vivo) o post_positivist (Glaser/Strauss, abstracción/patrones)';

-- =============================================================================
-- 5. Verification query (run manually to confirm)
-- =============================================================================
-- SELECT id, name, epistemic_mode FROM proyectos;
