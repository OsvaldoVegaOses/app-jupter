ALTER TABLE link_predictions ADD COLUMN IF NOT EXISTS neo4j_sync_status TEXT;
ALTER TABLE link_predictions ADD COLUMN IF NOT EXISTS neo4j_sync_error TEXT;
ALTER TABLE link_predictions ADD COLUMN IF NOT EXISTS neo4j_synced_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_lp_project_sync_status
    ON link_predictions(project_id, neo4j_sync_status);
