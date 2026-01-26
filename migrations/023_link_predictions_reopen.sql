ALTER TABLE link_predictions ADD COLUMN IF NOT EXISTS reopened_at TIMESTAMPTZ;
ALTER TABLE link_predictions ADD COLUMN IF NOT EXISTS reopened_by TEXT;
ALTER TABLE link_predictions ADD COLUMN IF NOT EXISTS reopen_reason TEXT;
