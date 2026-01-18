import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.settings import load_settings
from neo4j import GraphDatabase

settings = load_settings()
driver = GraphDatabase.driver(settings.neo4j.uri, auth=(settings.neo4j.username, settings.neo4j.password))

with driver.session(database=settings.neo4j.database) as session:
    result = session.run("CALL db.labels() YIELD label RETURN label")
    labels = [r["label"] for r in result]
    print("Labels:", labels)

    def _print_label_counts() -> None:
        for label in labels:
            result = session.run(f"MATCH (n:`{label}`) RETURN count(n) as c")
            print(f"  {label}: {result.single()['c']}")

    def _print_project_id_distribution(label: str, limit: int = 20) -> None:
        cypher = (
            "MATCH (n:`" + label + "`) "
            "WHERE n.project_id IS NOT NULL "
            "RETURN n.project_id AS project_id, count(*) AS c "
            "ORDER BY c DESC "
            "LIMIT $limit"
        )
        rows = list(session.run(cypher, limit=limit))
        if not rows:
            print(f"  {label} project_id: (none)")
            return
        print(f"  {label} project_id (top {limit}):")
        for r in rows:
            print(f"    {r['project_id']}: {r['c']}")

    def _print_label_keys_and_sample(label: str) -> None:
        rec = session.run(f"MATCH (n:`{label}`) RETURN keys(n) AS keys, n LIMIT 1").single()
        if not rec:
            print(f"  {label} sample: (none)")
            return
        print(f"  {label} properties:", rec["keys"])
        print(f"  {label} sample:", dict(rec["n"]))

    _print_label_counts()
    
    result = session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")
    rels = [r["relationshipType"] for r in result]
    print("Relationships:", rels)

    print("\nLabel samples / keys:")
    for label in labels:
        _print_label_keys_and_sample(label)

    print("\nProject coverage by label:")
    for label in labels:
        _print_project_id_distribution(label)

    # Quick global view of available project_ids
    global_projects = [
        r["project_id"]
        for r in session.run(
            "MATCH (n) WHERE n.project_id IS NOT NULL RETURN DISTINCT n.project_id AS project_id ORDER BY project_id"
        )
    ]
    print("\nDistinct project_id values (nodes):", global_projects)

    target_project = "jd-009"
    print(f"\nPresence check for {target_project}:")
    for label in labels:
        c = session.run(
            f"MATCH (n:`{label}`) WHERE n.project_id = $pid RETURN count(n) AS c",
            pid=target_project,
        ).single()["c"]
        print(f"  {label}: {c}")

driver.close()
