-- Migration 009: Project Registry Tables
-- Migrates project management from local JSON files to PostgreSQL
-- for cloud deployment (Azure)

-- =============================================================================
-- 1. Tabla de proyectos (reemplaza projects_registry.json)
-- =============================================================================
CREATE TABLE IF NOT EXISTS proyectos (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    org_id VARCHAR(100),           -- Multi-tenant: organización propietaria
    owner_id VARCHAR(100),         -- Usuario creador del proyecto
    config JSONB DEFAULT '{
        "discovery_threshold": 0.30,
        "analysis_temperature": 0.3,
        "analysis_max_tokens": 2000
    }'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- 2. Tabla de estado por proyecto (reemplaza projects/{id}.json)
-- =============================================================================
CREATE TABLE IF NOT EXISTS proyecto_estado (
    id SERIAL PRIMARY KEY,
    project_id VARCHAR(100) NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
    stage VARCHAR(50) NOT NULL,
    completed BOOLEAN DEFAULT FALSE,
    last_run_id VARCHAR(100),
    command VARCHAR(100),
    subcommand VARCHAR(100),
    extras JSONB,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(project_id, stage)
);

-- =============================================================================
-- 3. Indexes para performance
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_proyectos_org ON proyectos(org_id);
CREATE INDEX IF NOT EXISTS idx_proyectos_owner ON proyectos(owner_id);
CREATE INDEX IF NOT EXISTS idx_proyectos_created ON proyectos(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_proyecto_estado_project ON proyecto_estado(project_id);

-- =============================================================================
-- 4. Trigger para auto-update de updated_at
-- =============================================================================
CREATE OR REPLACE FUNCTION update_proyectos_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_proyectos_updated_at ON proyectos;
CREATE TRIGGER trigger_proyectos_updated_at
    BEFORE UPDATE ON proyectos
    FOR EACH ROW
    EXECUTE FUNCTION update_proyectos_updated_at();

-- =============================================================================
-- 5. Insertar proyecto default si no existe
-- =============================================================================
INSERT INTO proyectos (id, name, description, created_at)
VALUES ('default', 'Proyecto default', 'Proyecto base inicial', NOW())
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- 6. Comentarios para documentación
-- =============================================================================
COMMENT ON TABLE proyectos IS 'Registro de proyectos de análisis cualitativo (reemplaza projects_registry.json)';
COMMENT ON TABLE proyecto_estado IS 'Estado de etapas por proyecto (reemplaza projects/{id}.json)';
COMMENT ON COLUMN proyectos.org_id IS 'ID de organización para multi-tenancy';
COMMENT ON COLUMN proyectos.config IS 'Configuración JSON: discovery_threshold, analysis_temperature, analysis_max_tokens';
