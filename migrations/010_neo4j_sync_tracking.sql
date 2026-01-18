-- Sprint 28: Neo4j Sync Tracking
-- Permite rastrear qué fragmentos se han sincronizado a Neo4j
-- Facilita sincronización diferida cuando Neo4j no está disponible durante ingesta

-- 1. Añadir columna de tracking
ALTER TABLE entrevista_fragmentos 
ADD COLUMN IF NOT EXISTS neo4j_synced BOOLEAN DEFAULT FALSE;

-- 2. Índice para consultas eficientes de fragmentos no sincronizados
CREATE INDEX IF NOT EXISTS ix_fragments_neo4j_pending 
ON entrevista_fragmentos(project_id, neo4j_synced) 
WHERE neo4j_synced = FALSE;

-- 3. Marcar fragmentos existentes como sincronizados (asumir que ya están en Neo4j)
UPDATE entrevista_fragmentos 
SET neo4j_synced = TRUE 
WHERE neo4j_synced IS NULL;

-- 4. Comentario de documentación
COMMENT ON COLUMN entrevista_fragmentos.neo4j_synced IS 
'TRUE si el fragmento ya fue sincronizado a Neo4j. FALSE permite sincronización diferida.';
