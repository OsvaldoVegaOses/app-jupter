-- Fix/align entrevista_fragmentos schema to match backend expectations
-- Safe-ish: adds missing columns, renames legacy names, and recreates PK (project_id,id).
DO $$
DECLARE
    has_table boolean;
    missing_ids integer;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'entrevista_fragmentos'
    ) INTO has_table;

    IF NOT has_table THEN
        EXECUTE $$
        CREATE TABLE public.entrevista_fragmentos (
          project_id TEXT NOT NULL DEFAULT 'default',
          id TEXT NOT NULL,
          archivo TEXT NOT NULL,
          par_idx INT NOT NULL,
          fragmento TEXT NOT NULL,
          embedding DOUBLE PRECISION[] NOT NULL,
          char_len INT NOT NULL,
          sha256 TEXT NOT NULL,
          area_tematica TEXT,
          actor_principal TEXT,
          requiere_protocolo_lluvia BOOLEAN,
          metadata JSONB,
          speaker TEXT,
          interviewer_tokens INT DEFAULT 0,
          interviewee_tokens INT DEFAULT 0,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (project_id, id)
        );
        $$;
    END IF;

    -- Rename common legacy columns
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='fragment_id')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='id') THEN
        EXECUTE 'ALTER TABLE public.entrevista_fragmentos RENAME COLUMN fragment_id TO id';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='sha')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='sha256') THEN
        EXECUTE 'ALTER TABLE public.entrevista_fragmentos RENAME COLUMN sha TO sha256';
    END IF;

    -- Add missing columns
    PERFORM 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='project_id';
    IF NOT FOUND THEN EXECUTE 'ALTER TABLE public.entrevista_fragmentos ADD COLUMN project_id TEXT NOT NULL DEFAULT ''default'''; END IF;

    PERFORM 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='id';
    IF NOT FOUND THEN EXECUTE 'ALTER TABLE public.entrevista_fragmentos ADD COLUMN id TEXT'; END IF;

    PERFORM 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='archivo';
    IF NOT FOUND THEN EXECUTE 'ALTER TABLE public.entrevista_fragmentos ADD COLUMN archivo TEXT'; END IF;

    PERFORM 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='par_idx';
    IF NOT FOUND THEN EXECUTE 'ALTER TABLE public.entrevista_fragmentos ADD COLUMN par_idx INT'; END IF;

    PERFORM 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='fragmento';
    IF NOT FOUND THEN EXECUTE 'ALTER TABLE public.entrevista_fragmentos ADD COLUMN fragmento TEXT'; END IF;

    PERFORM 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='embedding';
    IF NOT FOUND THEN EXECUTE 'ALTER TABLE public.entrevista_fragmentos ADD COLUMN embedding DOUBLE PRECISION[]'; END IF;

    PERFORM 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='char_len';
    IF NOT FOUND THEN EXECUTE 'ALTER TABLE public.entrevista_fragmentos ADD COLUMN char_len INT'; END IF;

    PERFORM 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='sha256';
    IF NOT FOUND THEN EXECUTE 'ALTER TABLE public.entrevista_fragmentos ADD COLUMN sha256 TEXT'; END IF;

    PERFORM 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='area_tematica';
    IF NOT FOUND THEN EXECUTE 'ALTER TABLE public.entrevista_fragmentos ADD COLUMN area_tematica TEXT'; END IF;

    PERFORM 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='actor_principal';
    IF NOT FOUND THEN EXECUTE 'ALTER TABLE public.entrevista_fragmentos ADD COLUMN actor_principal TEXT'; END IF;

    PERFORM 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='requiere_protocolo_lluvia';
    IF NOT FOUND THEN EXECUTE 'ALTER TABLE public.entrevista_fragmentos ADD COLUMN requiere_protocolo_lluvia BOOLEAN'; END IF;

    PERFORM 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='metadata';
    IF NOT FOUND THEN EXECUTE 'ALTER TABLE public.entrevista_fragmentos ADD COLUMN metadata JSONB'; END IF;

    PERFORM 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='speaker';
    IF NOT FOUND THEN EXECUTE 'ALTER TABLE public.entrevista_fragmentos ADD COLUMN speaker TEXT'; END IF;

    PERFORM 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='interviewer_tokens';
    IF NOT FOUND THEN EXECUTE 'ALTER TABLE public.entrevista_fragmentos ADD COLUMN interviewer_tokens INT DEFAULT 0'; END IF;

    PERFORM 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='interviewee_tokens';
    IF NOT FOUND THEN EXECUTE 'ALTER TABLE public.entrevista_fragmentos ADD COLUMN interviewee_tokens INT DEFAULT 0'; END IF;

    PERFORM 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='created_at';
    IF NOT FOUND THEN EXECUTE 'ALTER TABLE public.entrevista_fragmentos ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()'; END IF;

    PERFORM 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='updated_at';
    IF NOT FOUND THEN EXECUTE 'ALTER TABLE public.entrevista_fragmentos ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()'; END IF;

    -- Fill null ids if possible
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='entrevista_fragmentos' AND column_name='id') THEN
        EXECUTE 'UPDATE public.entrevista_fragmentos SET id = archivo || '':'' || par_idx WHERE id IS NULL AND archivo IS NOT NULL AND par_idx IS NOT NULL';
    END IF;

    -- Enforce NOT NULL where safe
    IF EXISTS (SELECT 1 FROM public.entrevista_fragmentos WHERE id IS NULL OR project_id IS NULL) THEN
        RAISE NOTICE 'Found rows with NULL project_id or id. Fix manually before enforcing PK.';
    ELSE
        BEGIN
            EXECUTE 'ALTER TABLE public.entrevista_fragmentos ALTER COLUMN project_id SET NOT NULL';
            EXECUTE 'ALTER TABLE public.entrevista_fragmentos ALTER COLUMN id SET NOT NULL';
            EXECUTE 'ALTER TABLE public.entrevista_fragmentos ALTER COLUMN archivo SET NOT NULL';
            EXECUTE 'ALTER TABLE public.entrevista_fragmentos ALTER COLUMN par_idx SET NOT NULL';
            EXECUTE 'ALTER TABLE public.entrevista_fragmentos ALTER COLUMN fragmento SET NOT NULL';
            EXECUTE 'ALTER TABLE public.entrevista_fragmentos ALTER COLUMN embedding SET NOT NULL';
            EXECUTE 'ALTER TABLE public.entrevista_fragmentos ALTER COLUMN char_len SET NOT NULL';
            EXECUTE 'ALTER TABLE public.entrevista_fragmentos ALTER COLUMN sha256 SET NOT NULL';
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Could not set NOT NULL on some columns; please review manually: %', SQLERRM;
        END;
    END IF;

    -- Primary key (project_id, id)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.entrevista_fragmentos'::regclass
          AND contype = 'p'
    ) THEN
        EXECUTE 'ALTER TABLE public.entrevista_fragmentos DROP CONSTRAINT IF EXISTS entrevista_fragmentos_pkey';
        EXECUTE 'ALTER TABLE public.entrevista_fragmentos ADD PRIMARY KEY (project_id, id)';
    END IF;

    -- Useful indexes (match backend ensure_fragment_table)
    EXECUTE 'CREATE UNIQUE INDEX IF NOT EXISTS ux_ef_project_fragment ON public.entrevista_fragmentos(project_id, id)';
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_ef_project_id ON public.entrevista_fragmentos(project_id)';
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_ef_project_archivo ON public.entrevista_fragmentos(project_id, archivo)';
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_ef_archivo ON public.entrevista_fragmentos(archivo)';
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_ef_charlen ON public.entrevista_fragmentos(char_len)';
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_ef_area ON public.entrevista_fragmentos(area_tematica)';
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_ef_actor ON public.entrevista_fragmentos(actor_principal)';
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_ef_metadata_genero ON public.entrevista_fragmentos((metadata->>''genero''))';
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_ef_metadata_periodo ON public.entrevista_fragmentos((metadata->>''periodo''))';
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_ef_created_at ON public.entrevista_fragmentos(created_at)';
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_ef_speaker ON public.entrevista_fragmentos(speaker)';
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_ef_interview_tokens ON public.entrevista_fragmentos(interviewee_tokens)';
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_ef_fragment_tsv ON public.entrevista_fragmentos USING GIN (to_tsvector(''spanish'', fragmento))';

    SELECT COUNT(*) FROM public.entrevista_fragmentos WHERE id IS NULL INTO missing_ids;
    IF missing_ids > 0 THEN
        RAISE NOTICE 'Remaining rows without id: % (add ids then rerun script).', missing_ids;
    END IF;
END
$$ LANGUAGE plpgsql;
