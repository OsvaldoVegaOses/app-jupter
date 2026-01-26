-- 021_axial_ai_evidence.sql
-- AX-AI-03: Evidence pack (positivo/negativo) para análisis IA axial.
--
-- Nota: se mantiene compatible con instalaciones donde axial_ai_analyses ya existe.

ALTER TABLE axial_ai_analyses
  ADD COLUMN IF NOT EXISTS evidence_schema_version INT NOT NULL DEFAULT 1;

ALTER TABLE axial_ai_analyses
  ADD COLUMN IF NOT EXISTS evidence_json JSONB;

