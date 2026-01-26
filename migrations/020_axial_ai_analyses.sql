-- 020_axial_ai_analyses.sql
-- Axial IA: persistir análisis como artefactos auditables (multi-tenant)
--
-- Nota: el backend también puede crear la tabla en modo idempotente (ensure_*),
-- pero en producción se recomienda aplicar esta migración para trazabilidad.

CREATE TABLE IF NOT EXISTS axial_ai_analyses (
    id BIGSERIAL PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'analyze_predictions',
    algorithm TEXT,
    algorithm_description TEXT,
    suggestions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    analysis_text TEXT,
    memo_statements JSONB,
    structured BOOLEAN NOT NULL DEFAULT FALSE,
    estado TEXT NOT NULL DEFAULT 'pendiente',
    created_by TEXT,
    reviewed_by TEXT,
    reviewed_en TIMESTAMPTZ,
    review_memo TEXT,
    epistemic_mode TEXT,
    prompt_version TEXT,
    llm_deployment TEXT,
    llm_api_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_axial_ai_project_created
    ON axial_ai_analyses(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_axial_ai_project_estado
    ON axial_ai_analyses(project_id, estado);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ck_axial_ai_analyses_estado'
  ) THEN
    ALTER TABLE axial_ai_analyses
      ADD CONSTRAINT ck_axial_ai_analyses_estado
      CHECK (estado IN ('pendiente','validado','rechazado'));
  END IF;
END $$;

