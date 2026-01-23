Migration playbook — project scoping (multitenancy)
=================================================

This folder contains recommended migration scripts and the safe execution order to
backfill `project_id` across Postgres, Neo4j and Qdrant and to create new
project-scoped constraints/indexes.

IMPORTANT — read before running
- Always take full backups of Postgres and Neo4j before applying any changes.
- Run Postgres migrations in a maintenance window; they may add columns and
  create indexes which can be heavy on large tables.
- For Neo4j: inspect duplicates before creating composite constraints —
  creating uniqueness constraints will fail if duplicates exist.
- For Qdrant: reindexing may require re-uploading points. The provided script
  uses `qdrant-client` and requires Qdrant credentials.

Suggested safe order
1. Inspect duplicates in Neo4j and Postgres (see queries in the .cypher/.sql files).
2. Back up databases (Postgres dump, Neo4j dump, Qdrant export).
3. Run Postgres backfill (SQL) to add `project_id` and index it.
4. Create Postgres indexes (unique indexes per-project where appropriate).
5. Backfill `project_id` in Neo4j nodes (the .cypher contains commands).
6. Inspect duplicates in Neo4j grouped by `(name, project_id)`.
7. Drop or update old global uniqueness constraints if needed (manual step).
8. Create new Neo4j composite constraints including `project_id`.
9. Reindex Qdrant: either re-upload vectors with `project_id` payload, or
   create a new collection that includes `project_id` as an indexed payload.

Files in this folder
- `postgres_backfill_and_indexes.sql` — Postgres migration SQL (templates).
- `neo4j_constraints_and_backfill.cypher` — Cypher script with backfill and
  guidance for constraints. Adapt to your Neo4j version.
- `../scripts/qdrant_reindex.py` — Python script to upsert points into Qdrant
  adding `project_id` to each payload.

Additional production migrations
- `007_codigos_candidatos.sql`
- `008_schema_alignment.sql`
- `008_interview_files.sql`
- `010_neo4j_sync_tracking.sql`
- `012_add_is_deleted_to_proyectos.sql`
- `013_codes_catalog_ontology.sql`
- `014_code_id_columns.sql`
- `015_ontology_freeze.sql`

Helper script
- `../scripts/apply_migrations_production.py` — Runs the production SQL migrations in order.

If you want, I can adapt these scripts to your exact production table names and
run them if you provide DB credentials or allow me to run remote commands.
