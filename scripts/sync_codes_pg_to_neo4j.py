#!/usr/bin/env python
"""
Sincronización: Códigos de PostgreSQL a Neo4j.

Busca códigos en analisis_codigos_abiertos que no existen en Neo4j
y los crea con sus relaciones TIENE_CODIGO.

Uso:
    python scripts/sync_codes_pg_to_neo4j.py [--dry-run] [--project PROJECT_ID]
"""
import argparse
import sys
from pathlib import Path
from typing import Optional

# Añadir raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from neo4j import GraphDatabase
from app.settings import load_settings
from app.clients import get_pg_pool


def sync_codes_to_neo4j(project_id: Optional[str] = None, dry_run: bool = False) -> dict:
    """
    Sincroniza códigos de PostgreSQL a Neo4j.
    
    Args:
        project_id: Filtrar por proyecto (None = todos)
        dry_run: Solo mostrar qué se haría
        
    Returns:
        Dict con métricas de sincronización
    """
    settings = load_settings()
    pool = get_pg_pool(settings)
    driver = GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.username, settings.neo4j.password),
    )
    database = settings.neo4j.database
    
    results = {
        "pg_total": 0,
        "pg_skipped_null": 0,
        "neo4j_codes": 0,
        "missing_codes": 0,
        "synced_codes": 0,
        "synced_relations": 0,
        "missing_fragments": 0,
    }
    
    # 1. Obtener códigos de PostgreSQL
    with pool.getconn() as conn:
        try:
            with conn.cursor() as cur:
                if project_id:
                    cur.execute("""
                        SELECT DISTINCT codigo, fragmento_id, archivo, project_id
                        FROM analisis_codigos_abiertos
                        WHERE project_id = %s
                        ORDER BY codigo
                    """, (project_id,))
                else:
                    cur.execute("""
                        SELECT DISTINCT codigo, fragmento_id, archivo, project_id
                        FROM analisis_codigos_abiertos
                        ORDER BY project_id, codigo
                    """)
                pg_codes = cur.fetchall()
        finally:
            pool.putconn(conn)
    
    results["pg_total"] = len(pg_codes)
    
    if not pg_codes:
        driver.close()
        return results
    
    # 2. Verificar qué códigos existen en Neo4j
    unique_codes = {}  # {(proj_id, codigo): [fragmento_ids]}
    skipped_null = 0
    for codigo, frag_id, archivo, proj_id in pg_codes:
        # Ignorar registros sin project_id
        if not proj_id:
            skipped_null += 1
            continue
        key = (proj_id, codigo)
        if key not in unique_codes:
            unique_codes[key] = []
        if frag_id:
            unique_codes[key].append(frag_id)
    
    with driver.session(database=database) as session:
        # Contar códigos existentes en Neo4j
        if project_id:
            result = session.run("""
                MATCH (c:Codigo {project_id: $project_id})
                RETURN count(c) AS count
            """, project_id=project_id).single()
        else:
            result = session.run("""
                MATCH (c:Codigo)
                WHERE c.project_id IS NOT NULL
                RETURN count(c) AS count
            """).single()
        results["neo4j_codes"] = result["count"] if result else 0
        
        # Encontrar códigos faltantes
        missing = []
        for (proj_id, codigo), frag_ids in unique_codes.items():
            check = session.run("""
                MATCH (c:Codigo {nombre: $codigo, project_id: $project_id})
                RETURN c IS NOT NULL AS exists
            """, codigo=codigo, project_id=proj_id).single()
            
            if not check or not check["exists"]:
                missing.append((proj_id, codigo, frag_ids))
        
        results["missing_codes"] = len(missing)
        results["pg_skipped_null"] = skipped_null
        
        if dry_run:
            driver.close()
            return results
        
        # 3. Crear códigos faltantes y relaciones
        for proj_id, codigo, frag_ids in missing:
            # Crear el nodo Codigo
            session.run("""
                MERGE (c:Codigo {nombre: $codigo, project_id: $project_id})
                SET c.status = 'active',
                    c.synced_at = datetime()
            """, codigo=codigo, project_id=proj_id)
            results["synced_codes"] += 1
            
            # Crear relaciones TIENE_CODIGO para cada fragmento
            for frag_id in frag_ids:
                # Verificar si el fragmento existe
                frag_check = session.run("""
                    MATCH (f:Fragmento {id: $frag_id, project_id: $project_id})
                    RETURN f IS NOT NULL AS exists
                """, frag_id=frag_id, project_id=proj_id).single()
                
                if frag_check and frag_check["exists"]:
                    session.run("""
                        MATCH (f:Fragmento {id: $frag_id, project_id: $project_id})
                        MATCH (c:Codigo {nombre: $codigo, project_id: $project_id})
                        MERGE (f)-[rel:TIENE_CODIGO]->(c)
                        SET rel.project_id = $project_id,
                            rel.synced_at = datetime()
                    """, frag_id=frag_id, codigo=codigo, project_id=proj_id)
                    results["synced_relations"] += 1
                else:
                    results["missing_fragments"] += 1
    
    driver.close()
    return results


def main():
    parser = argparse.ArgumentParser(description="Sincronizar códigos de PostgreSQL a Neo4j")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar qué se haría")
    parser.add_argument("--project", type=str, help="Filtrar por project_id")
    args = parser.parse_args()
    
    print("=" * 60)
    print("SINCRONIZACIÓN: Códigos PostgreSQL → Neo4j")
    print("=" * 60)
    
    if args.dry_run:
        print("\n🔍 MODO DRY-RUN: No se realizarán cambios\n")
    else:
        print("\n⚠️  MODO EJECUCIÓN: Se crearán códigos y relaciones\n")
    
    if args.project:
        print(f"📁 Proyecto: {args.project}\n")
    
    results = sync_codes_to_neo4j(project_id=args.project, dry_run=args.dry_run)
    
    print("Resultados:")
    print("-" * 50)
    print(f"  📊 Códigos en PostgreSQL: {results['pg_total']}")
    if results.get('pg_skipped_null', 0) > 0:
        print(f"  ⚠️  Registros sin proyecto (ignorados): {results['pg_skipped_null']}")
    print(f"  📊 Códigos en Neo4j: {results['neo4j_codes']}")
    print(f"  ⚠️  Códigos faltantes: {results['missing_codes']}")
    
    if not args.dry_run:
        print(f"  ✅ Códigos sincronizados: {results['synced_codes']}")
        print(f"  ✅ Relaciones creadas: {results['synced_relations']}")
        if results['missing_fragments'] > 0:
            print(f"  ⚠️  Fragmentos no encontrados: {results['missing_fragments']}")
    
    print("-" * 50)
    
    if results['missing_codes'] == 0:
        print("\n✅ Todos los códigos ya están sincronizados")
    elif args.dry_run:
        print(f"\n📋 Se sincronizarían {results['missing_codes']} códigos")
        print("   Ejecuta sin --dry-run para aplicar cambios")
    else:
        print("\n✅ Sincronización completada")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
