"""
Test de Aislamiento por Proyecto (Project Isolation Test).

Este script verifica que los datos de un proyecto no sean accesibles
desde otro proyecto en las tres bases de datos:
- PostgreSQL (entrevista_fragmentos)
- Qdrant (coleccion de fragmentos)
- Neo4j (nodos Fragmento, Codigo, Categoria)

Uso:
    python tests/test_project_isolation.py

Requisitos:
    - Servicios corriendo (docker compose up)
    - Variables de entorno configuradas (.env)
"""

import sys
import os
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import List, Dict, Any
import structlog

_logger = structlog.get_logger()

# Test projects
PROJECT_A = "isolation_test_project_A"
PROJECT_B = "isolation_test_project_B"
TEST_ARCHIVO = "Claudia_Cesfam.docx"


def setup_clients():
    """Initialize service clients."""
    from app.settings import load_settings
    from app.clients import build_service_clients
    
    settings = load_settings()
    clients = build_service_clients(settings)
    return clients, settings


def cleanup_test_projects(clients, settings):
    """Remove test project data before/after tests."""
    # PostgreSQL - with error handling
    try:
        with clients.postgres.cursor() as cur:
            cur.execute(
                "DELETE FROM entrevista_fragmentos WHERE project_id IN (%s, %s)",
                (PROJECT_A, PROJECT_B)
            )
        clients.postgres.commit()
        print("[OK] PostgreSQL: Cleaned up entrevista_fragmentos")
    except Exception as e:
        clients.postgres.rollback()
        print(f"[WARN] PostgreSQL entrevista_fragmentos: {e}")
    
    try:
        with clients.postgres.cursor() as cur:
            cur.execute(
                "DELETE FROM codigo_candidatos WHERE project_id IN (%s, %s)",
                (PROJECT_A, PROJECT_B)
            )
        clients.postgres.commit()
        print("[OK] PostgreSQL: Cleaned up codigo_candidatos")
    except Exception as e:
        clients.postgres.rollback()
        print(f"[WARN] PostgreSQL codigo_candidatos: {e}")
    
    # Neo4j
    with clients.neo4j.session(database=settings.neo4j.database) as session:
        session.run(
            "MATCH (n) WHERE n.project_id IN $pids DETACH DELETE n",
            pids=[PROJECT_A, PROJECT_B]
        )
    print("[OK] Neo4j: Cleaned up test projects")
    
    # Qdrant - delete by filter
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchAny
        clients.qdrant.delete(
            collection_name=settings.qdrant.collection,
            points_selector=Filter(must=[
                FieldCondition(
                    key="project_id",
                    match=MatchAny(any=[PROJECT_A, PROJECT_B])
                )
            ])
        )
        print("[OK] Qdrant: Cleaned up test projects")
    except Exception as e:
        print(f"[WARN] Qdrant cleanup: {e}")


def ingest_test_file(clients, settings, project_id: str, archivo: str):
    """Ingest a test file into a specific project."""
    from app.ingestion import ingest_documents
    
    test_path = Path(__file__).parent.parent / "data" / "test_interviews" / "transcription_interviews" / archivo
    
    if not test_path.exists():
        raise FileNotFoundError(f"Test file not found: {test_path}")
    
    result = ingest_documents(
        clients=clients,
        settings=settings,
        files=[str(test_path)],
        project=project_id,
    )
    
    print(f"[OK] Ingested {archivo} into {project_id}: {result.get('fragments_created', 0)} fragments")
    return result


def test_postgres_isolation(clients, settings) -> bool:
    """Test PostgreSQL isolation."""
    print("\n--- PostgreSQL Isolation Test ---")
    
    with clients.postgres.cursor() as cur:
        cur.execute("""
            SELECT project_id, COUNT(*) 
            FROM entrevista_fragmentos 
            WHERE project_id IN (%s, %s)
            GROUP BY project_id
        """, (PROJECT_A, PROJECT_B))
        counts = dict(cur.fetchall())
    
    print(f"  Project A fragments: {counts.get(PROJECT_A, 0)}")
    print(f"  Project B fragments: {counts.get(PROJECT_B, 0)}")
    
    with clients.postgres.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM entrevista_fragmentos 
            WHERE project_id = %s AND archivo = %s
        """, (PROJECT_B, TEST_ARCHIVO))
        cross_count = cur.fetchone()[0]
    
    if cross_count == 0:
        print("[OK] PASS: Project B cannot see Project A's file")
        return True
    else:
        print(f"[FAIL] Project B saw {cross_count} fragments from Project A!")
        return False


def test_qdrant_isolation(clients, settings) -> bool:
    """Test Qdrant isolation."""
    print("\n--- Qdrant Isolation Test ---")
    
    from app.isolation import qdrant_project_filter
    
    test_query = "comunidad participacion vecinos"
    vector = clients.aoai.embeddings.create(
        model=settings.azure.deployment_embed,
        input=test_query
    ).data[0].embedding
    
    # Use helper from isolation.py
    filter_a = qdrant_project_filter(PROJECT_A)
    results_a = clients.qdrant.search(
        collection_name=settings.qdrant.collection,
        query_vector=vector,
        limit=10,
        query_filter=filter_a,
    )
    
    filter_b = qdrant_project_filter(PROJECT_B)
    results_b = clients.qdrant.search(
        collection_name=settings.qdrant.collection,
        query_vector=vector,
        limit=10,
        query_filter=filter_b,
    )
    
    print(f"  Project A results: {len(results_a)}")
    print(f"  Project B results: {len(results_b)}")
    
    cross_contaminated = False
    for r in results_a:
        if r.payload.get("project_id") != PROJECT_A:
            print(f"[FAIL] Wrong project_id: {r.payload.get('project_id')}")
            cross_contaminated = True
    
    if not cross_contaminated:
        print("[OK] PASS: Qdrant properly isolates by project_id")
        return True
    return False


def test_neo4j_isolation(clients, settings) -> bool:
    """Test Neo4j isolation."""
    print("\n--- Neo4j Isolation Test ---")
    
    with clients.neo4j.session(database=settings.neo4j.database) as session:
        result = session.run("""
            MATCH (f:Fragmento)
            WHERE f.project_id IN $pids
            RETURN f.project_id AS project, COUNT(f) AS count
        """, pids=[PROJECT_A, PROJECT_B])
        counts = {r["project"]: r["count"] for r in result}
    
    print(f"  Project A fragments: {counts.get(PROJECT_A, 0)}")
    print(f"  Project B fragments: {counts.get(PROJECT_B, 0)}")
    
    with clients.neo4j.session(database=settings.neo4j.database) as session:
        result = session.run("""
            MATCH (e:Entrevista {project_id: $project_id, nombre: $archivo})
            RETURN COUNT(e) AS count
        """, project_id=PROJECT_B, archivo=TEST_ARCHIVO)
        cross_count = result.single()["count"]
    
    if cross_count == 0:
        print("[OK] PASS: Neo4j properly isolates by project_id")
        return True
    else:
        print(f"[FAIL] Project B saw {cross_count} entrevistas!")
        return False


def run_all_tests():
    """Run complete isolation test suite."""
    print("=" * 60)
    print("PROJECT ISOLATION TEST SUITE")
    print("=" * 60)
    
    clients, settings = setup_clients()
    
    try:
        print("\n[1/5] Cleaning up test projects...")
        cleanup_test_projects(clients, settings)
        
        print("\n[2/5] Ingesting test file to Project A...")
        ingest_test_file(clients, settings, PROJECT_A, TEST_ARCHIVO)
        
        print("\n[3/5] Running PostgreSQL isolation test...")
        pg_pass = test_postgres_isolation(clients, settings)
        
        print("\n[4/5] Running Qdrant isolation test...")
        qdrant_pass = test_qdrant_isolation(clients, settings)
        
        print("\n[5/5] Running Neo4j isolation test...")
        neo4j_pass = test_neo4j_isolation(clients, settings)
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  PostgreSQL: {'[OK] PASS' if pg_pass else '[FAIL]'}")
        print(f"  Qdrant:     {'[OK] PASS' if qdrant_pass else '[FAIL]'}")
        print(f"  Neo4j:      {'[OK] PASS' if neo4j_pass else '[FAIL]'}")
        
        all_pass = pg_pass and qdrant_pass and neo4j_pass
        print(f"\nOverall: {'[OK] ALL TESTS PASSED' if all_pass else '[FAIL] SOME TESTS FAILED'}")
        
        return all_pass
        
    finally:
        print("\n[Cleanup] Removing test data...")
        cleanup_test_projects(clients, settings)
        clients.close()


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
