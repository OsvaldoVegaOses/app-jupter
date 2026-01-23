#!/usr/bin/env python3
"""
Análisis de Neo4j.
"""
from app.settings import load_settings
from app.clients import build_service_clients

def main():
    s = load_settings()
    c = build_service_clients(s)
    
    print("NEO4J ANÁLISIS")
    print("=" * 70)
    
    with c.neo4j.session() as session:
        # Proyectos en Neo4j
        result = session.run("""
            MATCH (n) 
            WHERE n.project_id IS NOT NULL
            RETURN n.project_id AS project, labels(n)[0] AS label, COUNT(*) AS cnt
            ORDER BY project, label
        """)
        print("\n📊 NODOS POR PROYECTO:")
        for r in result:
            print(f"  - {r['project']} | {r['label']}: {r['cnt']}")
        
        # Sin project_id
        result = session.run("""
            MATCH (n) 
            WHERE n.project_id IS NULL
            RETURN labels(n)[0] AS label, COUNT(*) AS cnt
        """)
        print("\n⚠️ NODOS SIN project_id:")
        for r in result:
            print(f"  - {r['label']}: {r['cnt']}")
        
        # Total
        result = session.run("MATCH (n) RETURN COUNT(n) AS nodes")
        nodes = result.single()["nodes"]
        result = session.run("MATCH ()-[r]->() RETURN COUNT(r) AS rels")
        rels = result.single()["rels"]
        print(f"\n📈 TOTALES: {nodes} nodos, {rels} relaciones")
    
    c.close()

if __name__ == "__main__":
    main()
