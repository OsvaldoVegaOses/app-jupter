#!/usr/bin/env python3
"""
Script de diagnóstico para inspeccionar la consistencia de datos entre PostgreSQL, Neo4j y Qdrant.
Muestra conteos de fragmentos y verifica la alineación de IDs por proyecto.
"""
import sys
from pathlib import Path
from collections import Counter

# Add parent dir to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.clients import build_service_clients
from app.settings import load_settings

def main():
    settings = load_settings()
    clients = build_service_clients(settings)

    print("--- PostgreSQL Inspection ---")
    with clients.postgres.cursor() as cur:
        cur.execute("SELECT DISTINCT project_id, archivo FROM entrevista_fragmentos")
        rows = cur.fetchall()
        if rows:
            for pid, fname in rows:
                print(f"Project: '{pid}', File: '{fname}'")
        else:
            print("No fragments found in Postgres.")

    print("\n--- Neo4j Inspection ---")
    with clients.neo4j.session() as session:
        result = session.run("MATCH (n:Fragmento) RETURN DISTINCT n.project_id as pid, n.archivo as fname")
        records = list(result)
        if records:
            for r in records:
                print(f"Project: '{r['pid']}', File: '{r['fname']}'")
        else:
            print("No Fragmento nodes found in Neo4j.")

    print("\n--- Qdrant Inspection ---")
    # Qdrant doesn't support "SELECT DISTINCT" easily, we have to scroll or sample.
    # We'll scroll a batch to see what's there.
    try:
        response = clients.qdrant.scroll(
            collection_name=settings.qdrant.collection,
            limit=100,
            with_payload=True,
            with_vectors=False
        )
        points, _ = response
        if points:
            seen = set()
            for p in points:
                payload = p.payload or {}
                pid = payload.get("project_id")
                fname = payload.get("archivo")
                key = (pid, fname)
                if key not in seen:
                    print(f"Project: '{pid}', File: '{fname}'")
                    seen.add(key)
        else:
            print("No points found in Qdrant.")
    except Exception as e:
        print(f"Error inspecting Qdrant: {e}")

    clients.close()

if __name__ == "__main__":
    main()
