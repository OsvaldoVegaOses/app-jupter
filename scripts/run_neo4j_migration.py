"""
Ejecuta migraciones de esquema en Neo4j (índices y restricciones).
Lee el archivo migrations/neo4j_constraints_and_backfill.cypher.
"""
import os
import sys
from pathlib import Path
from neo4j import GraphDatabase, Query

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from app.settings import load_settings

def run_migration():
    settings = load_settings()
    
    print(f"Connecting to Neo4j at {settings.neo4j.uri}...")
    driver = GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.username, settings.neo4j.password or ""),
    )
    
    migration_file = Path(__file__).parent.parent / "migrations" / "neo4j_constraints_and_backfill.cypher"
    if not migration_file.exists():
        print(f"Migration file not found: {migration_file}")
        return

    print(f"Reading migration file: {migration_file}")
    cypher_script = migration_file.read_text(encoding="utf-8")
    
    # Split by semicolon to execute statements individually, as Neo4j driver usually executes one statement at a time
    statements = [s.strip() for s in cypher_script.split(';') if s.strip()]
    
    try:
        with driver.session(database=settings.neo4j.database) as session:
            for i, statement in enumerate(statements):
                print(f"Executing statement {i+1}/{len(statements)}...")
                # Skip comments if the whole statement is a comment (simple check)
                if statement.startswith("//"):
                    continue
                session.run(Query(statement))  # type: ignore
        print("Migration executed successfully.")
    except Exception as e:
        print(f"Error executing migration: {e}")
    finally:
        driver.close()

if __name__ == "__main__":
    run_migration()
