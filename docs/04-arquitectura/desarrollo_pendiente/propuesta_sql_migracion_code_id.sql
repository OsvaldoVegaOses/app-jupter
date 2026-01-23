-- Propuesta (futuro) — Migración hacia identidad estable por ID
-- Fecha: 2026-01-22
-- Objetivo:
--   - Evolucionar `catalogo_codigos` desde puntero textual (`canonical_codigo`) a puntero por ID (`canonical_code_id`).
--   - Mantener compatibilidad temporal (dejar `canonical_codigo` mientras el backend/UI migra).
--   - Habilitar estado opcional `superseded` (reemplazo evolutivo, distinto de `merged`).
--
-- Intención ontológica (reglas de lectura):
--   - PostgreSQL es el ledger (fuente de verdad) del estado ontológico.
--   - Un registro es “canónico” cuando canonical_code_id IS NULL (puntero vacío).
--   - Un registro no-canónico (merged/superseded) debe redirigir al canónico vía canonical_code_id.
--   - Proyecciones/algoritmos deben excluir `merged` (y típicamente `superseded`) para evitar contaminación.
--
-- NOTA: Esto es un artefacto de diseño, no está aplicado por defecto.
--       Revisar disponibilidad de extensiones (pgcrypto/uuid-ossp) en el Postgres objetivo.

BEGIN;

-- 0) (Opcional) UUID helper
-- Opción A (recomendada si está disponible):
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1) Agregar columnas (idempotente)
ALTER TABLE catalogo_codigos
  ADD COLUMN IF NOT EXISTS code_id UUID,
  ADD COLUMN IF NOT EXISTS canonical_code_id UUID;

-- 2) Backfill de code_id
-- (Se asume que esto corre una sola vez en una base real. Si se requiere determinismo,
--  puede migrarse a UUIDv5 con uuid-ossp y un namespace, o a hash->UUID controlado.)
UPDATE catalogo_codigos
   SET code_id = gen_random_uuid()
 WHERE code_id IS NULL;

-- 3) Constraint de unicidad por proyecto
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'uq_catalogo_project_code_id'
  ) THEN
    ALTER TABLE catalogo_codigos
      ADD CONSTRAINT uq_catalogo_project_code_id UNIQUE (project_id, code_id);
  END IF;
END $$;

-- 4) FK canónico (composite) dentro del mismo proyecto
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_catalogo_canonical_code_id'
  ) THEN
    ALTER TABLE catalogo_codigos
      ADD CONSTRAINT fk_catalogo_canonical_code_id
      FOREIGN KEY (project_id, canonical_code_id)
      REFERENCES catalogo_codigos (project_id, code_id)
      DEFERRABLE INITIALLY DEFERRED;
  END IF;
END $$;

-- 5) Migrar puntero textual -> puntero por ID (best-effort)
-- Solo para filas que ya estaban marcadas con canonical_codigo.
UPDATE catalogo_codigos src
   SET canonical_code_id = tgt.code_id
  FROM catalogo_codigos tgt
 WHERE src.project_id = tgt.project_id
   AND src.canonical_codigo IS NOT NULL
   AND src.canonical_code_id IS NULL
   AND tgt.codigo = src.canonical_codigo;

-- 6) Ampliar enum lógico de status (agregar superseded)
-- Nota: esto reemplaza el CHECK existente por uno más amplio.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ck_catalogo_codigos_status'
  ) THEN
    ALTER TABLE catalogo_codigos DROP CONSTRAINT ck_catalogo_codigos_status;
  END IF;

  ALTER TABLE catalogo_codigos
    ADD CONSTRAINT ck_catalogo_codigos_status
    CHECK (status IN ('active','merged','deprecated','superseded'));
END $$;

-- 7) Índices recomendados
CREATE INDEX IF NOT EXISTS ix_catalogo_project_status ON catalogo_codigos(project_id, status);
CREATE INDEX IF NOT EXISTS ix_catalogo_project_canonical_code_id ON catalogo_codigos(project_id, canonical_code_id);

-- 8) Unicidad parcial de “canónicos” (opcional, recomendado)
-- Si en el futuro se permite duplicidad de labels por estado (p. ej. mantener histórico con mismo `codigo`),
-- este índice evita tener 2+ filas “canónicas” para el mismo label dentro del proyecto.
--
-- Nota: hoy (en el esquema actual) `catalogo_codigos` suele tener PK (project_id, codigo),
-- lo cual ya hace al label único. En ese caso, este índice es redundante pero expresa la intención.
CREATE UNIQUE INDEX IF NOT EXISTS ux_catalogo_project_canonical_label
  ON catalogo_codigos(project_id, lower(codigo))
  WHERE canonical_code_id IS NULL;

COMMIT;

-- Notas operativas:
-- - Regla recomendada: canónicos => canonical_code_id IS NULL.
-- - merged/superseded => canonical_code_id apunta al canónico (resolver obligatorio).
-- - Durante transición, se puede mantener canonical_codigo como columna legacy.
