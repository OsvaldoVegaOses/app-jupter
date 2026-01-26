#!/usr/bin/env python
"""
Migración: Agregar project_id a todas las relaciones Neo4j existentes.

Las relaciones deben heredar el project_id de los nodos que conectan.
Este script corrige las relaciones que fueron creadas sin project_id.

Uso:
    python scripts/migrate_neo4j_rel_project_id.py [--dry-run]
"""
import argparse
import sys
from pathlib import Path

# Añadir raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from neo4j import GraphDatabase
from app.settings import load_settings


def migrate_relationships(dry_run: bool = False) -> dict:
    """
    Migra todas las relaciones sin project_id, heredando del nodo origen.
    
    Returns:
        Dict con conteos de relaciones actualizadas por tipo
    """
    settings = load_settings()
    driver = GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.username, settings.neo4j.password),
    )
    database = settings.neo4j.database
    
    results = {}
    
    # Tipos de relaciones a migrar
    rel_types = [
        ("TIENE_FRAGMENTO", "Entrevista", "Fragmento"),
        ("TIENE_CODIGO", "Fragmento", "Codigo"),
        ("REL", "Categoria", "Codigo"),
        ("REL", "Codigo", "Codigo"),  # Link prediction
    ]
    
    with driver.session(database=database) as session:
        for rel_type, source_label, target_label in rel_types:
            # Contar relaciones sin project_id
            count_query = f"""
            MATCH (a:{source_label})-[r:{rel_type}]->()
            WHERE r.project_id IS NULL AND a.project_id IS NOT NULL
            RETURN count(r) AS count
            """
            count_result = session.run(count_query).single()
            count = count_result["count"] if count_result else 0
            
            key = f"{rel_type} ({source_label}→)"
            
            if count == 0:
                results[key] = {"sin_project_id": 0, "actualizadas": 0}
                continue
            
            if dry_run:
                results[key] = {"sin_project_id": count, "actualizadas": 0, "dry_run": True}
                continue
            
            # Actualizar relaciones heredando project_id del nodo origen
            update_query = f"""
            MATCH (a:{source_label})-[r:{rel_type}]->()
            WHERE r.project_id IS NULL AND a.project_id IS NOT NULL
            SET r.project_id = a.project_id
            RETURN count(r) AS updated
            """
            update_result = session.run(update_query).single()
            updated = update_result["updated"] if update_result else 0
            
            results[key] = {"sin_project_id": count, "actualizadas": updated}
    
    driver.close()
    return results


def main():
    parser = argparse.ArgumentParser(description="Migrar relaciones Neo4j sin project_id")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar qué se haría")
    args = parser.parse_args()
    
    print("=" * 60)
    print("MIGRACIÓN: Agregar project_id a relaciones Neo4j")
    print("=" * 60)
    
    if args.dry_run:
        print("\n🔍 MODO DRY-RUN: No se realizarán cambios\n")
    else:
        print("\n⚠️  MODO EJECUCIÓN: Se actualizarán las relaciones\n")
    
    results = migrate_relationships(dry_run=args.dry_run)
    
    print("\nResultados:")
    print("-" * 50)
    
    total_sin = 0
    total_upd = 0
    
    for key, data in results.items():
        sin = data.get("sin_project_id", 0)
        upd = data.get("actualizadas", 0)
        total_sin += sin
        total_upd += upd
        
        status = "✅" if sin == upd or args.dry_run else "❌"
        dry = " (DRY-RUN)" if data.get("dry_run") else ""
        print(f"  {status} {key}: {sin} sin project_id → {upd} actualizadas{dry}")
    
    print("-" * 50)
    print(f"  TOTAL: {total_sin} relaciones sin project_id")
    if not args.dry_run:
        print(f"  ACTUALIZADAS: {total_upd} relaciones")
    
    print("\n✅ Migración completada")
    
    return 0 if total_sin == total_upd or args.dry_run else 1


if __name__ == "__main__":
    sys.exit(main())
