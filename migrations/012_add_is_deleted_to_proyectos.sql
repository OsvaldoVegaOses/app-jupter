-- Migration 012: Add soft-delete flag to proyectos
-- Fecha: 2026-01-17

ALTER TABLE proyectos
  ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_proyectos_is_deleted ON proyectos(is_deleted);

COMMENT ON COLUMN proyectos.is_deleted IS 'Marca lógica de borrado para limpieza segura en admin panel';
