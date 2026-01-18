-- Postgres migration: backfill project_id/proyecto and create project-scoped indexes
BEGIN;

-- 1) Add project_id/proyecto column to target tables
ALTER TABLE IF EXISTS entrevista_fragmentos
  ADD COLUMN IF NOT EXISTS project_id TEXT DEFAULT 'default';

ALTER TABLE IF EXISTS analisis_codigos_abiertos
  ADD COLUMN IF NOT EXISTS project_id TEXT DEFAULT 'default';

ALTER TABLE IF EXISTS analisis_axial
  ADD COLUMN IF NOT EXISTS project_id TEXT DEFAULT 'default';

ALTER TABLE IF EXISTS analisis_nucleo_notas
  ADD COLUMN IF NOT EXISTS proyecto TEXT DEFAULT 'default';

ALTER TABLE IF EXISTS analisis_comparacion_constante
  ADD COLUMN IF NOT EXISTS proyecto TEXT DEFAULT 'default';

-- 2) Backfill NULL values
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'entrevista_fragmentos') THEN
        UPDATE entrevista_fragmentos SET project_id = 'default' WHERE project_id IS NULL;
    END IF;
    
    IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'analisis_codigos_abiertos') THEN
        UPDATE analisis_codigos_abiertos SET project_id = 'default' WHERE project_id IS NULL;
    END IF;

    IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'analisis_axial') THEN
        UPDATE analisis_axial SET project_id = 'default' WHERE project_id IS NULL;
    END IF;

    IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'analisis_nucleo_notas') THEN
        UPDATE analisis_nucleo_notas SET proyecto = 'default' WHERE proyecto IS NULL;
    END IF;

    IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'analisis_comparacion_constante') THEN
        UPDATE analisis_comparacion_constante SET proyecto = 'default' WHERE proyecto IS NULL;
    END IF;
END $$;

-- 3) Create indexes to speed up project-scoped queries
CREATE INDEX IF NOT EXISTS ix_ef_project_id ON entrevista_fragmentos (project_id);
CREATE INDEX IF NOT EXISTS ix_aca_project_id ON analisis_codigos_abiertos (project_id);
CREATE INDEX IF NOT EXISTS ix_axial_project_id ON analisis_axial (project_id);
CREATE INDEX IF NOT EXISTS ix_nucleo_proyecto ON analisis_nucleo_notas (proyecto);

-- 4) Create unique indexes/constraints scoped to project
-- Note: Primary keys might need to be adjusted if they were previously just (id) etc.
-- But here we just ensure the unique indexes exist as per app/postgres_block.py

-- entrevista_fragmentos: (project_id, id)
-- If PK exists on (id), we might want to drop it and add (project_id, id), but for now let's ensure the unique index exists.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ef_project_fragment ON entrevista_fragmentos(project_id, id);

-- analisis_codigos_abiertos: (project_id, fragmento_id, codigo)
CREATE UNIQUE INDEX IF NOT EXISTS ux_aca_project_fragment_codigo ON analisis_codigos_abiertos(project_id, fragmento_id, codigo);

-- analisis_axial: (project_id, categoria, codigo, relacion)
CREATE UNIQUE INDEX IF NOT EXISTS ux_axial_project_cat_cod_rel ON analisis_axial(project_id, categoria, codigo, relacion);

-- analisis_nucleo_notas: (proyecto, categoria)
CREATE UNIQUE INDEX IF NOT EXISTS ux_nucleo_proyecto_categoria ON analisis_nucleo_notas(proyecto, categoria);

COMMIT;
