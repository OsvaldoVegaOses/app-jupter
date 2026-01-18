-- Migration 008: Schema Alignment Fix
-- Date: 2026-01-04
-- Purpose: Add missing columns to analisis_codigos_abiertos and discovery_navigation_log

-- 1. Add missing columns to analisis_codigos_abiertos
ALTER TABLE analisis_codigos_abiertos 
  ADD COLUMN IF NOT EXISTS cita TEXT;
ALTER TABLE analisis_codigos_abiertos 
  ADD COLUMN IF NOT EXISTS fuente TEXT;

-- 2. Recreate discovery_navigation_log with correct schema
-- First, add missing columns
ALTER TABLE discovery_navigation_log 
  ADD COLUMN IF NOT EXISTS busqueda_id UUID DEFAULT gen_random_uuid();
ALTER TABLE discovery_navigation_log 
  ADD COLUMN IF NOT EXISTS positivos TEXT[];
ALTER TABLE discovery_navigation_log 
  ADD COLUMN IF NOT EXISTS negativos TEXT[];
ALTER TABLE discovery_navigation_log 
  ADD COLUMN IF NOT EXISTS target_text TEXT;
ALTER TABLE discovery_navigation_log 
  ADD COLUMN IF NOT EXISTS fragments_count INT;
ALTER TABLE discovery_navigation_log 
  ADD COLUMN IF NOT EXISTS codigos_sugeridos TEXT[];
ALTER TABLE discovery_navigation_log 
  ADD COLUMN IF NOT EXISTS refinamientos_aplicados JSONB;
ALTER TABLE discovery_navigation_log 
  ADD COLUMN IF NOT EXISTS ai_synthesis TEXT;
ALTER TABLE discovery_navigation_log 
  ADD COLUMN IF NOT EXISTS action_taken TEXT;
ALTER TABLE discovery_navigation_log 
  ADD COLUMN IF NOT EXISTS busqueda_origen_id UUID;

-- 3. Create indexes
CREATE INDEX IF NOT EXISTS ix_aco_cita ON analisis_codigos_abiertos(cita);
CREATE INDEX IF NOT EXISTS ix_dnl_busqueda ON discovery_navigation_log(busqueda_id);
CREATE INDEX IF NOT EXISTS ix_dnl_origen ON discovery_navigation_log(busqueda_origen_id);
CREATE INDEX IF NOT EXISTS ix_dnl_action ON discovery_navigation_log(action_taken);
