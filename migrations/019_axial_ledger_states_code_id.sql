-- Migration 019: Ledger axial (estado + code_id) para analisis_axial
-- Fecha: 2026-01-25
-- Objetivo:
--   - Formalizar analisis_axial como ledger auditable: estado + timestamps
--   - Añadir code_id (BIGINT) para identidad estable (compatible con catalogo_codigos)
--   - Backfill best-effort desde catalogo_codigos

BEGIN;

-- 1) Columnas nuevas (idempotente)
ALTER TABLE analisis_axial
  ADD COLUMN IF NOT EXISTS code_id BIGINT;

ALTER TABLE analisis_axial
  ADD COLUMN IF NOT EXISTS estado TEXT;

ALTER TABLE analisis_axial
  ADD COLUMN IF NOT EXISTS validado_por TEXT;

ALTER TABLE analisis_axial
  ADD COLUMN IF NOT EXISTS validado_en TIMESTAMPTZ;

ALTER TABLE analisis_axial
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- 2) Backfill estado (compatibilidad)
UPDATE analisis_axial
   SET estado = COALESCE(NULLIF(estado, ''), 'validado')
 WHERE estado IS NULL OR estado = '';

-- 3) Constraint de estado (idempotente)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ck_analisis_axial_estado'
  ) THEN
    ALTER TABLE analisis_axial
      ADD CONSTRAINT ck_analisis_axial_estado
      CHECK (estado IN ('pendiente','validado','rechazado'));
  END IF;
END $$;

-- 4) Índices
CREATE INDEX IF NOT EXISTS ix_axial_project_estado
  ON analisis_axial(project_id, estado);

CREATE INDEX IF NOT EXISTS ix_axial_project_code_id
  ON analisis_axial(project_id, code_id)
  WHERE code_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_axial_project_updated_at
  ON analisis_axial(project_id, updated_at);

-- 5) Backfill code_id (best-effort)
UPDATE analisis_axial ax
   SET code_id = cat.code_id
  FROM catalogo_codigos cat
 WHERE ax.project_id = cat.project_id
   AND lower(ax.codigo) = lower(cat.codigo)
   AND ax.code_id IS NULL
   AND cat.code_id IS NOT NULL;

COMMIT;

