#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

# Add parent dir to sys.path to allow imports from app
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.clients import build_service_clients
from app.settings import load_settings
from qdrant_client.models import Filter, FieldCondition, MatchValue

def main():
    parser = argparse.ArgumentParser(description="Delete all data related to a specific file from all databases.")
    parser.add_argument("file_name", help="The name of the file to delete (e.g., 'Guillermo Orestes.docx')")
    parser.add_argument("--project", default="default", help="Project ID (default: 'default')")
    args = parser.parse_args()

    settings = load_settings()
    clients = build_service_clients(settings)

    print(f"Deleting data for file '{args.file_name}' in project '{args.project}'...")

    # 1. Postgres
    print("Cleaning PostgreSQL...")
    with clients.postgres.cursor() as cur:
        # Delete fragments
        cur.execute(
            "DELETE FROM entrevista_fragmentos WHERE archivo = %s AND project_id = %s",
            (args.file_name, args.project)
        )
        deleted_fragments = cur.rowcount
        
        # Delete open codes
        cur.execute(
            "DELETE FROM analisis_codigos_abiertos WHERE archivo = %s AND project_id = %s",
            (args.file_name, args.project)
        )
        deleted_codes = cur.rowcount
    clients.postgres.commit()
    print(f"  - Deleted {deleted_fragments} fragments")
    print(f"  - Deleted {deleted_codes} open codes")

    # 2. Neo4j
    print("Cleaning Neo4j...")
    with clients.neo4j.session() as session:
        # Delete Entrevista and its connected Fragmento nodes
        result = session.run(
            """
            MATCH (e:Entrevista {nombre: $file, project_id: $project})
            OPTIONAL MATCH (e)-[:TIENE_FRAGMENTO]->(f:Fragmento)
            DETACH DELETE e, f
            RETURN count(e) + count(f) as count
            """,
            file=args.file_name,
            project=args.project
        )
        # Note: count(e) + count(f) might be slightly misleading if e is null, but good enough for feedback
        # Better: just get the summary counters if possible, or just return a sum.
        # If e doesn't exist, both counts are 0.
        record = result.single()
        count = record["count"] if record else 0
    print(f"  - Deleted {count} nodes (Entrevista + Fragmento)")

    # 3. Qdrant
    print("Cleaning Qdrant...")
    q_filter = Filter(
        must=[
            FieldCondition(key="archivo", match=MatchValue(value=args.file_name)),
            FieldCondition(key="project_id", match=MatchValue(value=args.project))
        ]
    )
    clients.qdrant.delete(
        collection_name=settings.qdrant.collection,
        points_selector=q_filter
    )
    print("  - Sent delete request to Qdrant")

    clients.close()
    print("Done.")

if __name__ == "__main__":
    main()
