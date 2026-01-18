-- Migración: Tabla de archivos de entrevistas
-- Propósito: Tracking de status por archivo para pipeline desacoplado
-- Fases: uploaded → indexed → analyzed
-- Fecha: 2026-01-05

-- 1. Crear tabla de archivos
CREATE TABLE IF NOT EXISTS interview_files (
    id SERIAL PRIMARY KEY,
    project_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    original_filename TEXT,        -- Nombre original subido por usuario
    blob_url TEXT,                 -- URL en Azure Blob Storage
    file_size INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, uploaded, indexing, indexed, analyzing, analyzed, error
    error_message TEXT,
    segments_count INTEGER,        -- Número de fragmentos generados
    indexed_at TIMESTAMPTZ,        -- Cuando se completó la indexación
    analyzed_at TIMESTAMPTZ,       -- Cuando se completó el análisis
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(project_id, filename)
);

-- 2. Índices para consultas frecuentes
CREATE INDEX IF NOT EXISTS ix_if_project_status ON interview_files(project_id, status);
CREATE INDEX IF NOT EXISTS ix_if_created_at ON interview_files(created_at DESC);

-- 3. Trigger para actualizar updated_at
CREATE OR REPLACE FUNCTION update_interview_files_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_interview_files_updated_at ON interview_files;
CREATE TRIGGER trg_interview_files_updated_at
    BEFORE UPDATE ON interview_files
    FOR EACH ROW
    EXECUTE FUNCTION update_interview_files_updated_at();

-- 4. Vista de estadísticas por proyecto
CREATE OR REPLACE VIEW vw_interview_files_stats AS
SELECT 
    project_id,
    status,
    COUNT(*) as total,
    SUM(segments_count) as total_segments,
    SUM(file_size) as total_size_bytes
FROM interview_files
GROUP BY project_id, status;

COMMENT ON TABLE interview_files IS 'Tracking de archivos de entrevistas por fase del pipeline';
COMMENT ON COLUMN interview_files.status IS 'pending, uploaded, indexing, indexed, analyzing, analyzed, error';
