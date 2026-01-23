#!/usr/bin/env python3
"""
Auditoría completa de las 3 bases de datos.
"""
from app.settings import load_settings
from app.clients import build_service_clients

def main():
    s = load_settings()
    c = build_service_clients(s)
    
    print("=" * 70)
    print("AUDITORÍA COMPLETA DE BASES DE DATOS")
    print("=" * 70)
    
    # ========== POSTGRESQL ==========
    print("\n" + "=" * 70)
    print("1. POSTGRESQL")
    print("=" * 70)
    
    with c.postgres.cursor() as cur:
        # Listar todas las tablas
        cur.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' ORDER BY table_name
        """)
        tables = [r[0] for r in cur.fetchall()]
        print(f"\n📋 Tablas ({len(tables)}):")
        for t in tables:
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{t}"')
                cnt = cur.fetchone()[0]
                print(f"  - {t}: {cnt} rows")
            except Exception as e:
                print(f"  - {t}: ERROR {e}")
        
        # Proyectos
        print("\n📁 PROYECTOS (proyectos):")
        cur.execute("SELECT id, name, org_id, created_at FROM proyectos ORDER BY created_at")
        projects = cur.fetchall()
        for p in projects:
            org_str = str(p[2])[:20] + "..." if p[2] else "NULL"
            print(f"  - {p[0]} | {p[1]} | org: {org_str} | {p[3]}")
        
        # Datos por project_id en tablas principales
        print("\n📊 DATOS POR PROYECTO:")
        
        data_tables = [
            ("codigos_candidatos", "project_id"),
            ("analisis_codigos_abiertos", "project_id"),
            ("pg_fragmentos", "project_id"),
            ("pg_entrevistas", "project_id"),
        ]
        
        for table, col in data_tables:
            try:
                cur.execute(f'SELECT {col}, COUNT(*) FROM "{table}" GROUP BY {col}')
                rows = cur.fetchall()
                print(f"\n  {table}:")
                for r in rows:
                    print(f"    - project={r[0]}: {r[1]} rows")
            except Exception as e:
                print(f"\n  {table}: ERROR {e}")
        
        # Buscar huérfanos (datos sin proyecto válido)
        print("\n⚠️ HUÉRFANOS (project_id no en proyectos):")
        valid_projects = [p[0] for p in projects]
        
        for table, col in data_tables:
            try:
                cur.execute(f"""
                    SELECT DISTINCT {col} FROM "{table}" 
                    WHERE {col} IS NOT NULL
                """)
                found_projects = [r[0] for r in cur.fetchall()]
                orphans = [p for p in found_projects if p not in valid_projects]
                if orphans:
                    print(f"  {table}: {orphans}")
            except Exception as e:
                pass
    
    # ========== NEO4J ==========
    print("\n" + "=" * 70)
    print("2. NEO4J")
    print("=" * 70)
    
    try:
        from app.neo4j_block import run_cypher
        
        # Contar nodos por tipo y project_id
        result = run_cypher(c, """
            MATCH (n) 
            WHERE n.project_id IS NOT NULL
            RETURN labels(n)[0] AS label, n.project_id AS project, COUNT(*) AS cnt
            ORDER BY project, label
        """)
        print("\n📊 NODOS POR PROYECTO:")
        for r in result:
            print(f"  - {r['project']} | {r['label']}: {r['cnt']}")
        
        # Nodos sin project_id
        result = run_cypher(c, """
            MATCH (n) 
            WHERE n.project_id IS NULL
            RETURN labels(n)[0] AS label, COUNT(*) AS cnt
        """)
        print("\n⚠️ NODOS SIN project_id:")
        for r in result:
            print(f"  - {r['label']}: {r['cnt']}")
            
    except Exception as e:
        print(f"ERROR Neo4j: {e}")
    
    # ========== QDRANT ==========
    print("\n" + "=" * 70)
    print("3. QDRANT")
    print("=" * 70)
    
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        # Listar colecciones
        collections = c.qdrant.get_collections().collections
        print(f"\n📦 Colecciones ({len(collections)}):")
        for col in collections:
            info = c.qdrant.get_collection(col.name)
            print(f"  - {col.name}: {info.points_count} points")
        
        # Contar por project_id en la colección principal
        main_col = s.qdrant.collection
        print(f"\n📊 PUNTOS POR PROYECTO en '{main_col}':")
        
        # Obtener project_ids únicos
        scroll_result = c.qdrant.scroll(
            collection_name=main_col,
            limit=1000,
            with_payload=["project_id"],
        )
        
        project_counts = {}
        for point in scroll_result[0]:
            pid = point.payload.get("project_id", "NULL")
            project_counts[pid] = project_counts.get(pid, 0) + 1
        
        for pid, cnt in sorted(project_counts.items()):
            print(f"  - {pid}: {cnt} points")
            
    except Exception as e:
        print(f"ERROR Qdrant: {e}")
    
    c.close()
    print("\n" + "=" * 70)
    print("AUDITORÍA COMPLETADA")
    print("=" * 70)

if __name__ == "__main__":
    main()
