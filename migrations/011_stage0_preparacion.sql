-- ETAPA 0: PREPARACIÓN (Grounded Theory)
-- Crea tablas mínimas para protocolo, actores anonimizados, consentimientos versionados,
-- criterios de muestreo, plan de análisis, memos de reflexividad y overrides con doble validación.

BEGIN;

CREATE TABLE IF NOT EXISTS stage0_protocols (
  project_id TEXT NOT NULL,
  version INT NOT NULL,
  title TEXT,
  content JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'draft', -- draft|approved|archived
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  approved_by TEXT,
  approved_at TIMESTAMPTZ,
  PRIMARY KEY (project_id, version)
);
CREATE INDEX IF NOT EXISTS ix_s0_protocols_project ON stage0_protocols(project_id);
CREATE INDEX IF NOT EXISTS ix_s0_protocols_status ON stage0_protocols(status);

CREATE TABLE IF NOT EXISTS stage0_actors (
  actor_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  alias TEXT NOT NULL,
  demographics_anon JSONB NOT NULL DEFAULT '{}'::jsonb,
  tags JSONB,
  notes TEXT,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(project_id, alias)
);
CREATE INDEX IF NOT EXISTS ix_s0_actors_project ON stage0_actors(project_id);
CREATE INDEX IF NOT EXISTS ix_s0_actors_alias ON stage0_actors(alias);

CREATE TABLE IF NOT EXISTS stage0_consents (
  consent_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  actor_id TEXT NOT NULL REFERENCES stage0_actors(actor_id) ON DELETE CASCADE,
  version INT NOT NULL,
  signed_at TIMESTAMPTZ,
  scope JSONB NOT NULL DEFAULT '{}'::jsonb,
  evidence_url TEXT,
  revoked_at TIMESTAMPTZ,
  notes TEXT,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(project_id, actor_id, version)
);
CREATE INDEX IF NOT EXISTS ix_s0_consents_project ON stage0_consents(project_id);
CREATE INDEX IF NOT EXISTS ix_s0_consents_actor ON stage0_consents(actor_id);
CREATE INDEX IF NOT EXISTS ix_s0_consents_revoked ON stage0_consents(revoked_at);

CREATE TABLE IF NOT EXISTS stage0_sampling_criteria (
  project_id TEXT NOT NULL,
  version INT NOT NULL,
  content JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (project_id, version)
);
CREATE INDEX IF NOT EXISTS ix_s0_sampling_project ON stage0_sampling_criteria(project_id);

CREATE TABLE IF NOT EXISTS stage0_analysis_plans (
  project_id TEXT NOT NULL,
  version INT NOT NULL,
  content JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (project_id, version)
);
CREATE INDEX IF NOT EXISTS ix_s0_plans_project ON stage0_analysis_plans(project_id);

CREATE TABLE IF NOT EXISTS stage0_reflexivity_memos (
  memo_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by TEXT,
  kind TEXT NOT NULL DEFAULT 'decision', -- assumption|decision|ethics|sampling_shift
  content TEXT NOT NULL,
  links JSONB
);
CREATE INDEX IF NOT EXISTS ix_s0_memos_project ON stage0_reflexivity_memos(project_id);
CREATE INDEX IF NOT EXISTS ix_s0_memos_created ON stage0_reflexivity_memos(created_at);

-- Override requests: doble validación (analyst solicita, admin aprueba).
-- reason_category es estructurado para auditoría.
CREATE TABLE IF NOT EXISTS stage0_override_requests (
  override_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT 'both', -- ingest|analyze|both
  reason_category TEXT NOT NULL,
  reason_details TEXT,
  requested_by TEXT NOT NULL,
  requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status TEXT NOT NULL DEFAULT 'pending', -- pending|approved|rejected
  decided_by TEXT,
  decided_at TIMESTAMPTZ,
  decision_note TEXT,
  expires_at TIMESTAMPTZ,
  CHECK (scope IN ('ingest', 'analyze', 'both')),
  CHECK (status IN ('pending', 'approved', 'rejected')),
  CHECK (reason_category IN ('critical_incident', 'data_validation', 'service_continuity', 'protocol_exception', 'other'))
);
CREATE INDEX IF NOT EXISTS ix_s0_overrides_project ON stage0_override_requests(project_id);
CREATE INDEX IF NOT EXISTS ix_s0_overrides_status ON stage0_override_requests(status);
CREATE INDEX IF NOT EXISTS ix_s0_overrides_requested ON stage0_override_requests(requested_at);

COMMIT;
