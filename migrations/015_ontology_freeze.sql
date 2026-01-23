-- Migration 015: Freeze ontológico por proyecto (pre-axialidad)
-- Fecha: 2026-01-22
-- Objetivo:
--   - Permitir congelar operaciones con efectos sobre la ontología
--   - Bloquear backfill/repair y acciones equivalentes salvo ruptura explícita

BEGIN;

CREATE TABLE IF NOT EXISTS project_ontology_freeze (
  project_id TEXT PRIMARY KEY,
  is_frozen BOOLEAN NOT NULL DEFAULT FALSE,
  frozen_at TIMESTAMPTZ,
  frozen_by TEXT,
  broken_at TIMESTAMPTZ,
  broken_by TEXT,
  note TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION update_project_ontology_freeze_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_project_ontology_freeze_updated_at ON project_ontology_freeze;
CREATE TRIGGER trg_project_ontology_freeze_updated_at
  BEFORE UPDATE ON project_ontology_freeze
  FOR EACH ROW
  EXECUTE FUNCTION update_project_ontology_freeze_updated_at();

COMMIT;
