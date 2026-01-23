-- Migration 013: Catálogo ontológico de códigos (status + canonical)
-- Fecha: 2026-01-22
-- Objetivo:
--   - Registrar estado post-fusión de códigos definitivos
--   - Permitir resolución canónica (canonical pointer)
--   - Mantener compatibilidad con `analisis_codigos_abiertos`

BEGIN;

CREATE TABLE IF NOT EXISTS catalogo_codigos (
  project_id TEXT NOT NULL,
  codigo TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  canonical_codigo TEXT,
  merged_at TIMESTAMPTZ,
  merged_by TEXT,
  memo TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (project_id, codigo)
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ck_catalogo_codigos_status'
  ) THEN
    ALTER TABLE catalogo_codigos
      ADD CONSTRAINT ck_catalogo_codigos_status
      CHECK (status IN ('active','merged','deprecated'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_catalogo_project_status ON catalogo_codigos(project_id, status);
CREATE INDEX IF NOT EXISTS ix_catalogo_project_canonical ON catalogo_codigos(project_id, canonical_codigo);

CREATE OR REPLACE FUNCTION update_catalogo_codigos_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_catalogo_codigos_updated_at ON catalogo_codigos;
CREATE TRIGGER trg_catalogo_codigos_updated_at
    BEFORE UPDATE ON catalogo_codigos
    FOR EACH ROW
    EXECUTE FUNCTION update_catalogo_codigos_updated_at();

-- Backfill best-effort: crear entradas para códigos ya existentes.
INSERT INTO catalogo_codigos (project_id, codigo, status)
SELECT DISTINCT project_id, codigo, 'active'
  FROM analisis_codigos_abiertos
 WHERE project_id IS NOT NULL AND codigo IS NOT NULL
ON CONFLICT (project_id, codigo) DO NOTHING;

COMMIT;
