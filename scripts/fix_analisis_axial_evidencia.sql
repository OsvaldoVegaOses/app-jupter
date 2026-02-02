-- Script sugerido: Normalizar la columna `evidencia` en `analisis_axial`
-- Este script prepara una columna jsonb `evidencia_jsonb` basada en el tipo
-- actual de `evidencia`. Revise y ejecute en un entorno de staging primero.

BEGIN;

-- 1) Añadir columna temporal para normalizar
ALTER TABLE IF EXISTS analisis_axial ADD COLUMN IF NOT EXISTS evidencia_jsonb jsonb;

-- 2) Rellenar evidencia_jsonb desde text[] -> to_jsonb(text[])
UPDATE analisis_axial
   SET evidencia_jsonb = to_jsonb(evidencia)
 WHERE pg_typeof(evidencia)::text = 'text[]'
   AND evidencia IS NOT NULL;

-- 3) Rellenar evidencia_jsonb desde json/jsonb -> cast
UPDATE analisis_axial
   SET evidencia_jsonb = evidencia::jsonb
 WHERE pg_typeof(evidencia)::text IN ('json', 'jsonb')
   AND evidencia IS NOT NULL
   AND evidencia_jsonb IS NULL;

-- 4) Revisar filas donde no se pudo convertir
-- SELECT id, pg_typeof(evidencia), evidencia FROM analisis_axial WHERE evidencia_jsonb IS NULL AND evidencia IS NOT NULL LIMIT 50;

-- 5) Si todo OK, opcional: reemplazar la columna original (por seguridad, hacerlo en mantenimiento)
-- ALTER TABLE analisis_axial DROP COLUMN evidencia;
-- ALTER TABLE analisis_axial RENAME COLUMN evidencia_jsonb TO evidencia;

COMMIT;

-- NOTE: Este script no hace DROP de la columna original automáticamente.
-- Revise resultados y cierre manualmente la migración.
