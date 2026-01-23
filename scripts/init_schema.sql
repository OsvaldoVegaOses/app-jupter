-- =============================================================================
-- APP_Jupter - Database Schema Initialization
-- =============================================================================
-- Purpose: Create all required tables for production deployment
-- Usage: psql -h appjupter.postgres.database.azure.com -U <user> -d postgres -f init_schema.sql
-- =============================================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- AUTHENTICATION TABLES
-- =============================================================================

CREATE TABLE IF NOT EXISTS app_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    organization_id VARCHAR(100) DEFAULT 'default_org',
    role VARCHAR(50) DEFAULT 'analyst',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES app_users(id) ON DELETE CASCADE,
    refresh_token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ip_address VARCHAR(45),
    user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON app_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON app_sessions(expires_at);


-- =============================================================================
-- CORE DATA TABLES
-- =============================================================================

CREATE TABLE IF NOT EXISTS entrevista_fragmentos (
    project_id TEXT NOT NULL DEFAULT 'default',
    id TEXT NOT NULL,
    archivo TEXT NOT NULL,
    par_idx INT NOT NULL DEFAULT 0,
    fragmento TEXT NOT NULL,
    embedding DOUBLE PRECISION[],
    char_len INT NOT NULL DEFAULT 0,
    sha256 TEXT NOT NULL DEFAULT '',
    area_tematica TEXT,
    actor_principal TEXT,
    requiere_protocolo_lluvia BOOLEAN,
    metadata JSONB DEFAULT '{}',
    speaker TEXT,
    interviewer_tokens INT DEFAULT 0,
    interviewee_tokens INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (project_id, id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ef_project_fragment ON entrevista_fragmentos(project_id, id);
CREATE INDEX IF NOT EXISTS ix_ef_project_id ON entrevista_fragmentos(project_id);
CREATE INDEX IF NOT EXISTS ix_ef_project_archivo ON entrevista_fragmentos(project_id, archivo);
CREATE INDEX IF NOT EXISTS ix_ef_archivo ON entrevista_fragmentos(archivo);


-- =============================================================================
-- CODING TABLES (Stage 3 - Open Coding)
-- =============================================================================

CREATE TABLE IF NOT EXISTS analisis_codigos_abiertos (
    id SERIAL PRIMARY KEY,
    fragmento_id VARCHAR(255),
    proyecto TEXT,
    codigo TEXT,
    definicion TEXT,
    evidencia TEXT,
    archivo TEXT,
    confidence FLOAT DEFAULT 0.0,
    source VARCHAR(50) DEFAULT 'llm',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_codigos_proyecto ON analisis_codigos_abiertos(proyecto);
CREATE INDEX IF NOT EXISTS idx_codigos_codigo ON analisis_codigos_abiertos(codigo);

-- =============================================================================
-- AXIAL CODING TABLES (Stage 4)
-- =============================================================================

CREATE TABLE IF NOT EXISTS analisis_axial (
    id SERIAL PRIMARY KEY,
    proyecto TEXT,
    categoria TEXT,
    codigo TEXT,
    tipo_relacion TEXT,
    evidencia TEXT,
    fragmento_id VARCHAR(255),
    confidence FLOAT DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_axial_proyecto ON analisis_axial(proyecto);

-- =============================================================================
-- CANDIDATE CODES (Hybrid Coding Flow)
-- =============================================================================

CREATE TABLE IF NOT EXISTS codigos_candidatos (
    id SERIAL PRIMARY KEY,
    proyecto TEXT,
    codigo TEXT,
    definicion TEXT,
    evidencia TEXT,
    fragmento_id VARCHAR(255),
    source VARCHAR(50) DEFAULT 'llm',
    status VARCHAR(20) DEFAULT 'pending',
    reviewed_at TIMESTAMP WITH TIME ZONE,
    reviewed_by UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_candidatos_proyecto ON codigos_candidatos(proyecto);
CREATE INDEX IF NOT EXISTS idx_candidatos_status ON codigos_candidatos(status);

-- =============================================================================
-- REPORTS AND ANALYTICS
-- =============================================================================

CREATE TABLE IF NOT EXISTS doctoral_reports (
    id SERIAL PRIMARY KEY,
    project_id TEXT NOT NULL,
    stage TEXT NOT NULL,  -- 'stage3', 'stage4', 'stage5'
    content TEXT NOT NULL,
    stats JSONB,
    file_path TEXT,
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_doctoral_project ON doctoral_reports(project_id);
CREATE INDEX IF NOT EXISTS ix_doctoral_stage ON doctoral_reports(stage);
CREATE INDEX IF NOT EXISTS ix_doctoral_generated ON doctoral_reports(generated_at);

CREATE TABLE IF NOT EXISTS analysis_insights (
    id SERIAL PRIMARY KEY,
    proyecto TEXT,
    insight_type VARCHAR(100),
    content TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- AUDIT AND COLLABORATION
-- =============================================================================

CREATE TABLE IF NOT EXISTS project_members (
    id SERIAL PRIMARY KEY,
    project_id TEXT,
    user_id UUID,
    role VARCHAR(50) DEFAULT 'collaborator',
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    added_by UUID
);

CREATE TABLE IF NOT EXISTS project_audit_log (
    id SERIAL PRIMARY KEY,
    project_id TEXT,
    user_id UUID,
    action VARCHAR(100),
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- DISCOVERY AND NAVIGATION
-- =============================================================================

CREATE TABLE IF NOT EXISTS discovery_navigation_log (
    id SERIAL PRIMARY KEY,
    proyecto TEXT,
    session_id UUID,
    query TEXT,
    results_count INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS analisis_comparacion_constante (
    id SERIAL PRIMARY KEY,
    proyecto TEXT,
    codigo_a TEXT,
    codigo_b TEXT,
    similarity FLOAT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- NUCLEUS SELECTION (Stage 5)
-- =============================================================================

CREATE TABLE IF NOT EXISTS analisis_nucleo_notas (
    id SERIAL PRIMARY KEY,
    proyecto TEXT,
    nucleo TEXT,
    nota TEXT,
    tipo VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- CODE VERSIONING
-- =============================================================================

CREATE TABLE IF NOT EXISTS codigo_versiones (
    id SERIAL PRIMARY KEY,
    project_id TEXT NOT NULL,
    codigo TEXT NOT NULL,
    version INT NOT NULL DEFAULT 1,
    memo_anterior TEXT,
    memo_nuevo TEXT,
    accion TEXT NOT NULL DEFAULT 'create',
    changed_by TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_cv_project_codigo ON codigo_versiones(project_id, codigo);
CREATE INDEX IF NOT EXISTS ix_cv_created_at ON codigo_versiones(created_at);

-- =============================================================================
-- VERIFICATION
-- =============================================================================

-- Check tables created
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;

-- Show counts
DO $$
BEGIN
    RAISE NOTICE 'Schema initialization complete!';
END $$;
