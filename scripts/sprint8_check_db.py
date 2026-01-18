#!/usr/bin/env python3
"""
Sprint 8: Verificacion de estado de base de datos
Ejecutar: python scripts/sprint8_check_db.py
"""

from app.clients import build_service_clients
from app.settings import load_settings

def main():
    print("=" * 60)
    print("Sprint 8 - Verificacion de Estado de Base de Datos")
    print("=" * 60)
    
    settings = load_settings()
    clients = build_service_clients(settings)
    
    try:
        with clients.postgres.cursor() as cur:
            # Total codigos
            cur.execute("SELECT COUNT(*) FROM analisis_codigos_abiertos")
            total = cur.fetchone()[0]
            
            # Fantasmas (IDs sinteticos)
            cur.execute("SELECT COUNT(*) FROM analisis_codigos_abiertos WHERE fragmento_id LIKE '%#auto#%'")
            fantasmas = cur.fetchone()[0]
            
            # Datos de prueba
            cur.execute("SELECT COUNT(*) FROM analisis_codigos_abiertos WHERE codigo LIKE '%Test%' OR codigo LIKE '%Automatica%'")
            test_data = cur.fetchone()[0]
            
            # Codigos unicos
            cur.execute("SELECT COUNT(DISTINCT codigo) FROM analisis_codigos_abiertos")
            unique_codes = cur.fetchone()[0]
            
            # Proyectos
            cur.execute("SELECT COUNT(DISTINCT project_id) FROM analisis_codigos_abiertos")
            projects = cur.fetchone()[0]
            
            print("\nESTADISTICAS PostgreSQL")
            print("-" * 40)
            print(f"Total codigos abiertos: {total}")
            print(f"Codigos unicos: {unique_codes}")
            print(f"Proyectos: {projects}")
            print(f"Codigos fantasma: {fantasmas} ({100*fantasmas/total if total else 0:.1f}%)")
            print(f"Datos de prueba: {test_data}")
            
            # Axial
            cur.execute("SELECT COUNT(*) FROM analisis_axial")
            axial_total = cur.fetchone()[0]
            print(f"\nTotal relaciones axiales: {axial_total}")
            
        # Neo4j
        print("\nESTADISTICAS Neo4j")
        print("-" * 40)
        with clients.neo4j.session(database=settings.neo4j.database) as session:
            # Categorias
            result = session.run("MATCH (c:Categoria) RETURN count(c) as count")
            categorias = result.single()["count"]
            
            # Codigos
            result = session.run("MATCH (c:Codigo) RETURN count(c) as count")
            codigos = result.single()["count"]
            
            # Relaciones
            result = session.run("MATCH ()-[r:REL]->() RETURN count(r) as count")
            relaciones = result.single()["count"]
            
            # Con GDS
            result = session.run("MATCH (n) WHERE n.score_centralidad IS NOT NULL RETURN count(n) as count")
            con_gds = result.single()["count"]
            
            print(f"Categorias: {categorias}")
            print(f"Codigos: {codigos}")
            print(f"Relaciones REL: {relaciones}")
            print(f"Nodos con score_centralidad: {con_gds}")
        
        # Qdrant
        print("\nESTADISTICAS Qdrant")
        print("-" * 40)
        info = clients.qdrant.get_collection(settings.qdrant.collection)
        print(f"Puntos en coleccion: {info.points_count}")
        print(f"Vectores indexados: {info.indexed_vectors_count}")
        
        # Resumen
        print("\n" + "=" * 60)
        print("RESUMEN - BRECHAS")
        print("=" * 60)
        
        if fantasmas > 0:
            pct = 100 * fantasmas / total if total else 0
            if pct > 10:
                print(f"[!] Codigos fantasma: {pct:.1f}% (objetivo: <10%)")
            else:
                print(f"[OK] Codigos fantasma: {pct:.1f}%")
        else:
            print("[OK] Sin codigos fantasma")
            
        if test_data > 0:
            print(f"[!] Datos de prueba a limpiar: {test_data}")
        else:
            print("[OK] Sin datos de prueba")
            
        if con_gds == 0:
            print("[!] GDS no ejecutado (sin score_centralidad)")
        else:
            print(f"[OK] GDS ejecutado ({con_gds} nodos)")
            
    finally:
        clients.close()
    
    print("\n[OK] Verificacion completada")

if __name__ == "__main__":
    main()
