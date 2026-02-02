-- 024_axial_evidencia_text_array.sql
-- Purpose: Convert analisis_axial.evidencia to text[] safely and align defaults.

CREATE OR REPLACE FUNCTION safe_text_to_text_array(t text)
RETURNS text[]
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  j jsonb;
BEGIN
  IF t IS NULL OR btrim(t) = '' THEN
    RETURN ARRAY[]::text[];
  END IF;

  -- JSON array: '["a","b"]'
  IF btrim(t) LIKE '[%' THEN
    BEGIN
      j := t::jsonb;
      IF jsonb_typeof(j) = 'array' THEN
        RETURN ARRAY(SELECT jsonb_array_elements_text(j));
      END IF;
    EXCEPTION WHEN others THEN
      -- fall through
    END;
  END IF;

  -- CSV: 'a,b,c'
  IF position(',' in t) > 0 THEN
    RETURN string_to_array(t, ',');
  END IF;

  -- Single token
  RETURN ARRAY[t];
END $$;

DO $$
DECLARE
  col_type text;
  col_udt text;
BEGIN
  IF NOT EXISTS (
    SELECT 1
      FROM information_schema.tables
     WHERE table_schema = 'public'
       AND table_name = 'analisis_axial'
  ) THEN
    RAISE NOTICE 'analisis_axial not found, skipping evidencia migration';
    RETURN;
  END IF;

  SELECT data_type, udt_name
    INTO col_type, col_udt
    FROM information_schema.columns
   WHERE table_schema = 'public'
     AND table_name = 'analisis_axial'
     AND column_name = 'evidencia';

  IF col_type IS NULL THEN
    ALTER TABLE analisis_axial
      ADD COLUMN evidencia TEXT[] DEFAULT ARRAY[]::text[] NOT NULL;
  ELSIF col_type <> 'ARRAY' OR col_udt <> '_text' THEN
    ALTER TABLE analisis_axial
      ALTER COLUMN evidencia TYPE text[]
      USING safe_text_to_text_array(evidencia);
  END IF;

  ALTER TABLE analisis_axial
    ALTER COLUMN evidencia SET DEFAULT ARRAY[]::text[];

  UPDATE analisis_axial
     SET evidencia = ARRAY[]::text[]
   WHERE evidencia IS NULL;

  ALTER TABLE analisis_axial
    ALTER COLUMN evidencia SET NOT NULL;
END $$;
