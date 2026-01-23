#!/usr/bin/env python3
"""
Análisis adicional de bases de datos.
"""
from app.settings import load_settings
from app.clients import build_service_clients

def main():
    s = load_settings()
    c = build_service_clients(s)
    
    print("ANÁLISIS ADICIONAL")
    print("=" * 70)
    
    with c.postgres.cursor() as cur:
        # app_users
        print("\n👤 USUARIOS (app_users):")
        cur.execute("SELECT id, email, org_id, role FROM app_users")
        for r in cur.fetchall():
            print(f"  - {r[1]} | org: {r[2]} | role: {r[3]}")
        
        # entrevista_fragmentos por project
        print("\n📄 ENTREVISTA_FRAGMENTOS por proyecto:")
        cur.execute("SELECT project_id, COUNT(*) FROM entrevista_fragmentos GROUP BY project_id")
        for r in cur.fetchall():
            print(f"  - {r[0]}: {r[1]} rows")
        
        # discovery_runs por project
        print("\n🔍 DISCOVERY_RUNS por proyecto:")
        cur.execute("SELECT project_id, COUNT(*) FROM discovery_runs GROUP BY project_id")
        for r in cur.fetchall():
            print(f"  - {r[0]}: {r[1]} rows")
        
        # interview_reports por project
        print("\n📋 INTERVIEW_REPORTS por proyecto:")
        cur.execute("SELECT project_id, COUNT(*) FROM interview_reports GROUP BY project_id")
        for r in cur.fetchall():
            print(f"  - {r[0]}: {r[1]} rows")
        
        # analysis_memos por project
        print("\n📝 ANALYSIS_MEMOS por proyecto:")
        cur.execute("SELECT project_id, COUNT(*) FROM analysis_memos GROUP BY project_id")
        for r in cur.fetchall():
            print(f"  - {r[0]}: {r[1]} rows")
        
        # stage0 tables
        print("\n🎯 STAGE0_PROTOCOLS por proyecto:")
        cur.execute("SELECT project_id, COUNT(*) FROM stage0_protocols GROUP BY project_id")
        for r in cur.fetchall():
            print(f"  - {r[0]}: {r[1]} rows")
    
    # Neo4j
    print("\n" + "=" * 70)
    print("NEO4J")
    print("=" * 70)
    
    with c.neo4j.session() as session:
        # Proyectos en Neo4j
        result = session.run("""
            MATCH (n) 
            WHERE n.project_id IS NOT NULL
            RETURN DISTINCT n.project_id AS project, labels(n)[0] AS label, COUNT(*) AS cnt
            ORDER BY project
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
        
        # Total de nodos y relaciones
        result = session.run("MATCH (n) RETURN COUNT(n) AS nodes")
        nodes = result.single()["nodes"]
        result = session.run("MATCH ()-[r]->() RETURN COUNT(r) AS rels")
        rels = result.single()["rels"]
        print(f"\n📈 TOTALES: {nodes} nodos, {rels} relaciones")
    
    c.close()
    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()
