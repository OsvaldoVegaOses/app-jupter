// Neo4j migration script (Cypher)
// NOTE: Syntax for constraints varies across Neo4j versions. Test in a dev
// environment first. If your version does not support multi-property `IS NODE KEY`
// or `IF NOT EXISTS`, adapt accordingly.

// 1) Backfill missing project_id on nodes
MATCH (n:Entrevista)
WHERE n.project_id IS NULL
SET n.project_id = 'default'
;

MATCH (c:Codigo)
WHERE c.project_id IS NULL
SET c.project_id = 'default'
;

// 2) Find potential duplicates (by name + project)
// This returns any (nombre, project_id) that have more than one node
MATCH (n:Entrevista)
WITH n.nombre AS nombre, n.project_id AS project, collect(id(n)) AS ids
WHERE size(ids) > 1
RETURN nombre, project, ids LIMIT 200;

MATCH (c:Codigo)
WITH c.nombre AS nombre, c.project_id AS project, collect(id(c)) AS ids
WHERE size(ids) > 1
RETURN nombre, project, ids LIMIT 200;

// Resolve duplicates manually before creating constraints. If no duplicates,
// proceed to create composite unique constraints including project_id.

// Example (Neo4j 4.x+ style) — adapt if your server doesn't accept IF NOT EXISTS:
// Drop old global uniqueness constraints if present (manual step recommended):
// CALL db.constraints() YIELD name, description RETURN name, description;

// Create composite node key using nombre + project_id
CREATE CONSTRAINT unique_entrevista_name_project IF NOT EXISTS
FOR (n:Entrevista)
REQUIRE (n.nombre, n.project_id) IS NODE KEY
;

CREATE CONSTRAINT unique_codigo_name_project IF NOT EXISTS
FOR (c:Codigo)
REQUIRE (c.nombre, c.project_id) IS NODE KEY
;

// Also consider adding index on project_id for fast lookups
CREATE INDEX idx_entrevista_project_id IF NOT EXISTS FOR (n:Entrevista) ON (n.project_id);
CREATE INDEX idx_codigo_project_id IF NOT EXISTS FOR (c:Codigo) ON (c.project_id);

// Note: If your Neo4j version doesn't support composite node keys with this
// syntax, use the appropriate syntax for your server or create a synthetic
// compound property (e.g., `nombre_project = nombre + '||' + project_id`) as a
// fallback and index that.
