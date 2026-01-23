-- Migration 018: Propagación de code_id a tablas de codificación
-- Fecha: 2026-01-23
-- Objetivo:
--   - Añadir columna code_id a analisis_codigos_abiertos (códigos definitivos)
--   - Añadir columna code_id a codigos_candidatos (bandeja de validación)
--   - Backfill desde catalogo_codigos para datos existentes
-- Prerequisito: 014_code_id_columns.sql (code_id en catalogo_codigos)
-- Notas:
--   - Usa BIGINT para consistencia con catalogo_codigos
--   - FK opcional (comentada) para evitar bloqueos en producción
--   - Backfill es best-effort: códigos sin match en catálogo quedan NULL

BEGIN;

-- =============================================================================
-- 1. Añadir columna code_id a analisis_codigos_abiertos
-- =============================================================================

ALTER TABLE analisis_codigos_abiertos
  ADD COLUMN IF NOT EXISTS code_id BIGINT;

CREATE INDEX IF NOT EXISTS ix_aca_project_code_id
  ON analisis_codigos_abiertos(project_id, code_id)
  WHERE code_id IS NOT NULL;

-- FK opcional (descomentar si se desea integridad referencial estricta):
-- ALTER TABLE analisis_codigos_abiertos
--   ADD CONSTRAINT fk_aca_code_id
--   FOREIGN KEY (project_id, code_id)
--   REFERENCES catalogo_codigos(project_id, code_id)
--   ON DELETE SET NULL;

-- =============================================================================
-- 2. Añadir columna code_id a codigos_candidatos
-- =============================================================================

ALTER TABLE codigos_candidatos
  ADD COLUMN IF NOT EXISTS code_id BIGINT;

CREATE INDEX IF NOT EXISTS ix_cc_project_code_id
  ON codigos_candidatos(project_id, code_id)
  WHERE code_id IS NOT NULL;

-- =============================================================================
-- 3. Backfill: Asignar code_id desde catalogo_codigos a registros existentes
-- =============================================================================

-- 3a. analisis_codigos_abiertos: JOIN por (project_id, codigo)
UPDATE analisis_codigos_abiertos aca
   SET code_id = cat.code_id
  FROM catalogo_codigos cat
 WHERE aca.project_id = cat.project_id
   AND lower(aca.codigo) = lower(cat.codigo)
   AND aca.code_id IS NULL
   AND cat.code_id IS NOT NULL;

-- 3b. codigos_candidatos: JOIN por (project_id, codigo)
UPDATE codigos_candidatos cc
   SET code_id = cat.code_id
  FROM catalogo_codigos cat
 WHERE cc.project_id = cat.project_id
   AND lower(cc.codigo) = lower(cat.codigo)
   AND cc.code_id IS NULL
   AND cat.code_id IS NOT NULL;

-- =============================================================================
-- 4. Estadísticas de migración (para auditoría)
-- =============================================================================

DO $$
DECLARE
  aca_total INT;
  aca_with_id INT;
  cc_total INT;
  cc_with_id INT;
BEGIN
  SELECT COUNT(*), COUNT(code_id) INTO aca_total, aca_with_id
    FROM analisis_codigos_abiertos;
  
  SELECT COUNT(*), COUNT(code_id) INTO cc_total, cc_with_id
    FROM codigos_candidatos;
  
  RAISE NOTICE 'Migration 018 stats:';
  RAISE NOTICE '  analisis_codigos_abiertos: %/% rows with code_id', aca_with_id, aca_total;
  RAISE NOTICE '  codigos_candidatos: %/% rows with code_id', cc_with_id, cc_total;
END $$;

COMMIT;
