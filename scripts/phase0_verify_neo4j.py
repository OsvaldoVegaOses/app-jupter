"""
Phase 0.3: Verify Neo4j Aura labels and relationships for GDS/GraphRAG
"""
import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

# Neo4j Aura credentials from .env
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD")
NEO4J_DB = os.getenv("NEO4J_DATABASE", "neo4j")

print(f"Connecting to: {NEO4J_URI}")
print(f"Database: {NEO4J_DB}")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

with driver.session(database=NEO4J_DB) as session:
    # 1. Check existing labels
    print("\n=== LABELS ===")
    result = session.run("CALL db.labels() YIELD label RETURN label ORDER BY label")
    labels = [r["label"] for r in result]
    print(f"Found {len(labels)} labels: {labels}")
    
    # Check for required labels
    required_labels = ["Codigo", "Categoria", "Fragmento", "Entrevista"]
    for label in required_labels:
        status = "✅" if label in labels else "❌ MISSING"
        print(f"  {label}: {status}")
    
    # 2. Check relationship types
    print("\n=== RELATIONSHIP TYPES ===")
    result = session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType")
    rel_types = [r["relationshipType"] for r in result]
    print(f"Found {len(rel_types)} types: {rel_types}")
    
    # 3. Count nodes by label
    print("\n=== NODE COUNTS ===")
    for label in labels[:10]:  # First 10
        result = session.run(f"MATCH (n:{label}) RETURN count(n) as cnt")
        cnt = result.single()["cnt"]
        print(f"  {label}: {cnt} nodes")
    
    # 4. Check if GDS is available
    print("\n=== GDS AVAILABILITY ===")
    try:
        result = session.run("RETURN gds.version() AS version")
        version = result.single()["version"]
        print(f"✅ GDS version: {version}")
    except Exception as e:
        print(f"❌ GDS not available: {e}")
        print("   NOTE: GDS requires Neo4j Enterprise or Aura Professional")

driver.close()
print("\n=== VERIFICATION COMPLETE ===")
