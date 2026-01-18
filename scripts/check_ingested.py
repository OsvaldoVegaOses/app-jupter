"""Check ingested files in nubeweb project - detailed."""
from app.settings import load_settings
from app.clients import build_service_clients

settings = load_settings()
clients = build_service_clients(settings)

# Check PostgreSQL
print("=== Tablas en PostgreSQL ===")
with clients.postgres.cursor() as cur:
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    tables = [r[0] for r in cur.fetchall()]
    print(f"Tablas: {tables}")
    
    # Check fragments table
    if 'fragments' in tables:
        cur.execute("SELECT source_file, COUNT(*) FROM fragments WHERE project_id='nubeweb' GROUP BY source_file")
        rows = cur.fetchall()
        print("\n=== Archivos en fragments (nubeweb) ===")
        if rows:
            for row in rows:
                print(f"  - {row[0]}: {row[1]} fragmentos")
        else:
            cur.execute("SELECT DISTINCT project_id FROM fragments LIMIT 5")
            projects = [r[0] for r in cur.fetchall()]
            print(f"  (ninguno en nubeweb - proyectos existentes: {projects})")

# Check Neo4j - full properties
print("\n=== Entrevistas en Neo4j ===")
with clients.neo4j.session() as session:
    result = session.run(
        "MATCH (e:Entrevista) RETURN properties(e) as props LIMIT 5"
    )
    records = list(result)
    if records:
        for i, rec in enumerate(records):
            print(f"\nEntrevista {i+1}:")
            props = rec['props']
            for k, v in props.items():
                val = str(v)[:80] if v else 'None'
                print(f"  {k}: {val}")
    else:
        print("  (ninguna)")

    # Count by project
    result = session.run("MATCH (e:Entrevista) RETURN e.project_id as pid, count(*) as cnt")
    print("\n=== Conteo por proyecto ===")
    for rec in result:
        print(f"  {rec['pid']}: {rec['cnt']} entrevistas")

clients.close()
