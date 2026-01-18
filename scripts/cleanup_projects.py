"""
Script to cleanup data from deleted projects in all databases.
Projects to delete: nubeweb, prueba-2, test-ingesta-proj
Run: "python scripts/cleanup_projects.py"
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.settings import load_settings
from app.clients import build_service_clients

PROJECTS_TO_DELETE = ["nubeweb", "nerd", "Nubeweb", "perro", "test-ingesta-proj"]

def cleanup_neo4j(clients, settings, project_ids):
    """Delete all Neo4j nodes for the given project IDs."""
    print("\n[Neo4j] Cleaning up...")
    with clients.neo4j.session(database=settings.neo4j.database) as session:
        for pid in project_ids:
            # Delete Fragmento nodes
            result = session.run(
                "MATCH (f:Fragmento {project_id: $pid}) DETACH DELETE f RETURN count(f) as deleted",
                pid=pid
            )
            record = result.single()
            print(f"  - {pid}: Deleted {record['deleted']} Fragmento nodes")
            
            # Delete Entrevista nodes
            result = session.run(
                "MATCH (e:Entrevista {project_id: $pid}) DETACH DELETE e RETURN count(e) as deleted",
                pid=pid
            )
            record = result.single()
            print(f"  - {pid}: Deleted {record['deleted']} Entrevista nodes")
            
            # Delete Codigo nodes
            result = session.run(
                "MATCH (c:Codigo {project_id: $pid}) DETACH DELETE c RETURN count(c) as deleted",
                pid=pid
            )
            record = result.single()
            print(f"  - {pid}: Deleted {record['deleted']} Codigo nodes")
            
            # Delete Categoria nodes
            result = session.run(
                "MATCH (c:Categoria {project_id: $pid}) DETACH DELETE c RETURN count(c) as deleted",
                pid=pid
            )
            record = result.single()
            print(f"  - {pid}: Deleted {record['deleted']} Categoria nodes")
    print("[Neo4j] Done.")


def cleanup_qdrant(clients, settings, project_ids):
    """Delete all Qdrant points for the given project IDs."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    print("\n[Qdrant] Cleaning up...")
    collection = settings.qdrant.collection
    
    for pid in project_ids:
        try:
            # Delete points matching project_id
            clients.qdrant.delete(
                collection_name=collection,
                points_selector=Filter(
                    must=[FieldCondition(key="project_id", match=MatchValue(value=pid))]
                ),
            )
            print(f"  - {pid}: Deleted points from collection '{collection}'")
        except Exception as e:
            print(f"  - {pid}: Error - {e}")
    print("[Qdrant] Done.")


def cleanup_postgres(clients, project_ids):
    """Delete all Postgres rows for the given project IDs."""
    print("\n[Postgres] Cleaning up...")
    
    tables = [
        "entrevista_fragmentos",
        "analisis_codigos_abiertos",
        "analisis_axial",
        "analisis_comparacion_constante",
        "analisis_nucleo_notas",
    ]
    
    with clients.postgres.cursor() as cur:
        for pid in project_ids:
            for table in tables:
                try:
                    # Check if table exists first
                    cur.execute(
                        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)",
                        (table,)
                    )
                    if not cur.fetchone()[0]:
                        continue
                    
                    # Check column name (project_id vs proyecto)
                    cur.execute(
                        """SELECT column_name FROM information_schema.columns 
                           WHERE table_name = %s AND column_name IN ('project_id', 'proyecto')""",
                        (table,)
                    )
                    col_row = cur.fetchone()
                    if not col_row:
                        continue
                    col_name = col_row[0]
                    
                    cur.execute(f"DELETE FROM {table} WHERE {col_name} = %s", (pid,))
                    deleted = cur.rowcount
                    print(f"  - {pid}: Deleted {deleted} rows from {table}")
                except Exception as e:
                    clients.postgres.rollback()
                    print(f"  - {pid}: Error on {table} - {e}")
    
    clients.postgres.commit()
    print("[Postgres] Done.")


def main():
    print("=" * 60)
    print("PROJECT DATA CLEANUP SCRIPT")
    print("=" * 60)
    print(f"Projects to delete: {', '.join(PROJECTS_TO_DELETE)}")
    
    settings = load_settings()
    clients = build_service_clients(settings)
    
    try:
        cleanup_neo4j(clients, settings, PROJECTS_TO_DELETE)
        cleanup_qdrant(clients, settings, PROJECTS_TO_DELETE)
        cleanup_postgres(clients, PROJECTS_TO_DELETE)
        
        print("\n" + "=" * 60)
        print("CLEANUP COMPLETE")
        print("=" * 60)
    finally:
        clients.close()


if __name__ == "__main__":
    main()
