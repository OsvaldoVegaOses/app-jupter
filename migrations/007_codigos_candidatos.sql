-- Migración: Tabla de Códigos Candidatos
-- Propósito: Centralizar códigos de todas las fuentes (LLM, manual, discovery, sugerencias)
-- para validación antes de promoverlos a la lista definitiva.
-- Fecha: 2024-12-20

-- 1. Crear tabla de candidatos
CREATE TABLE IF NOT EXISTS codigos_candidatos (
    id SERIAL PRIMARY KEY,
    project_id TEXT NOT NULL,
    codigo TEXT NOT NULL,
    cita TEXT,
    fragmento_id TEXT,
    archivo TEXT,
    fuente_origen TEXT NOT NULL,  -- 'llm', 'manual', 'discovery', 'semantic_suggestion', 'legacy'
    fuente_detalle TEXT,          -- Actor, entrevistado, detalles adicionales
    score_confianza FLOAT,        -- Score de similitud (para sugerencias semánticas)
    estado TEXT NOT NULL DEFAULT 'pendiente',  -- 'pendiente', 'validado', 'rechazado', 'fusionado'
    validado_por TEXT,            -- Usuario que validó
    validado_en TIMESTAMPTZ,
    fusionado_a TEXT,             -- Si se fusionó, referencia al código destino
    memo TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(project_id, codigo, fragmento_id)
);

-- 2. Índices para consultas frecuentes
CREATE INDEX IF NOT EXISTS ix_cc_project_estado ON codigos_candidatos(project_id, estado);
CREATE INDEX IF NOT EXISTS ix_cc_project_fuente ON codigos_candidatos(project_id, fuente_origen);
CREATE INDEX IF NOT EXISTS ix_cc_score ON codigos_candidatos(score_confianza DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS ix_cc_created_at ON codigos_candidatos(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_cc_archivo ON codigos_candidatos(archivo);
CREATE INDEX IF NOT EXISTS ix_cc_codigo ON codigos_candidatos(codigo);

-- 3. Trigger para actualizar updated_at
CREATE OR REPLACE FUNCTION update_codigos_candidatos_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_codigos_candidatos_updated_at ON codigos_candidatos;
CREATE TRIGGER trg_codigos_candidatos_updated_at
    BEFORE UPDATE ON codigos_candidatos
    FOR EACH ROW
    EXECUTE FUNCTION update_codigos_candidatos_updated_at();

-- 4. Vista de estadísticas por origen
CREATE OR REPLACE VIEW vw_codigos_candidatos_stats AS
SELECT 
    project_id,
    fuente_origen,
    estado,
    COUNT(*) as cantidad,
    COUNT(DISTINCT codigo) as codigos_unicos,
    AVG(score_confianza) as score_promedio
FROM codigos_candidatos
GROUP BY project_id, fuente_origen, estado;

-- 5. Migrar códigos existentes como "legacy" validados (opcional, ejecutar manualmente)
-- INSERT INTO codigos_candidatos (project_id, codigo, cita, fragmento_id, archivo, fuente_origen, estado, validado_en)
-- SELECT 
--     project_id, 
--     codigo, 
--     cita, 
--     fragmento_id, 
--     archivo, 
--     'legacy' as fuente_origen,
--     'validado' as estado,
--     created_at as validado_en
-- FROM analisis_codigos_abiertos
-- ON CONFLICT (project_id, codigo, fragmento_id) DO NOTHING;

COMMENT ON TABLE codigos_candidatos IS 'Bandeja de códigos candidatos para validación antes de ser definitivos';
COMMENT ON COLUMN codigos_candidatos.fuente_origen IS 'llm, manual, discovery, semantic_suggestion, legacy';
COMMENT ON COLUMN codigos_candidatos.estado IS 'pendiente, validado, rechazado, fusionado';
