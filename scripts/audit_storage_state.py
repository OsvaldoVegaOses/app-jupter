#!/usr/bin/env python3
"""
Script de auditoría completa: revisa estado de datos en 4 bases de datos.

Audita:
1. PostgreSQL (fragmentos, códigos, proyectos)
2. Neo4j (nodos Entrevista, Fragmento, Codigo, relaciones)
3. Qdrant (colecciones, puntos)
4. Azure Blob Storage (archivos, metadata)

Uso:
    python scripts/audit_storage_state.py --project-id [uuid] --account [email] --detailed
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.settings import load_settings
from app.clients import build_service_clients
from app.project_state import resolve_project


def audit_postgresql(pg_conn, project_id: str) -> Dict[str, Any]:
    """Audita estado de PostgreSQL para el proyecto."""
    
    result = {
        "database": "PostgreSQL",
        "project_id": project_id,
        "tables": {}
    }
    
    # Fragmentos
    with pg_conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) as total,
                   COUNT(DISTINCT archivo) as unique_files,
                   COUNT(DISTINCT speaker) as unique_speakers,
                   MIN(created_at) as oldest,
                   MAX(created_at) as newest
              FROM entrevista_fragmentos
             WHERE project_id = %s
        """, (project_id,))
        row = cur.fetchone()
        result["tables"]["entrevista_fragmentos"] = {
            "total_records": row[0],
            "unique_files": row[1],
            "unique_speakers": row[2],
            "oldest_record": row[3].isoformat() if row[3] else None,
            "newest_record": row[4].isoformat() if row[4] else None,
        }
    
    # Detalles por archivo
    with pg_conn.cursor() as cur:
        cur.execute("""
            SELECT archivo, COUNT(*) as fragmentos, MIN(created_at), MAX(updated_at)
              FROM entrevista_fragmentos
             WHERE project_id = %s
             GROUP BY archivo
             ORDER BY COUNT(*) DESC
        """, (project_id,))
        files = cur.fetchall()
        result["tables"]["entrevista_fragmentos"]["files"] = [
            {
                "archivo": f[0],
                "fragmentos": f[1],
                "created_at": f[2].isoformat() if f[2] else None,
                "updated_at": f[3].isoformat() if f[3] else None,
            }
            for f in files
        ]
    
    # Códigos abiertos
    with pg_conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) as total,
                   COUNT(DISTINCT codigo) as unique_codes,
                   COUNT(DISTINCT archivo) as unique_files,
                   COUNT(DISTINCT fragmento_id) as unique_fragments
              FROM analisis_codigos_abiertos
             WHERE project_id = %s
        """, (project_id,))
        row = cur.fetchone()
        result["tables"]["analisis_codigos_abiertos"] = {
            "total_citations": row[0],
            "unique_codes": row[1],
            "unique_files": row[2],
            "unique_fragments": row[3],
        }
    
    # Top códigos
    with pg_conn.cursor() as cur:
        cur.execute("""
            SELECT codigo, COUNT(*) as citations, COUNT(DISTINCT fragmento_id) as fragments
              FROM analisis_codigos_abiertos
             WHERE project_id = %s
             GROUP BY codigo
             ORDER BY COUNT(*) DESC
             LIMIT 10
        """, (project_id,))
        codes = cur.fetchall()
        result["tables"]["analisis_codigos_abiertos"]["top_codes"] = [
            {
                "codigo": c[0],
                "citations": c[1],
                "fragments": c[2],
            }
            for c in codes
        ]
    
    # Proyectos
    with pg_conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) as total
              FROM proyectos
             WHERE id = %s
        """, (project_id,))
        row = cur.fetchone()
        result["tables"]["proyectos"] = {
            "exists": row[0] > 0,
        }
    
    return result


def audit_neo4j(neo4j_conn, project_id: str) -> Dict[str, Any]:
    """Audita estado de Neo4j para el proyecto."""
    
    result = {
        "database": "Neo4j",
        "project_id": project_id,
        "nodes": {},
        "relationships": {}
    }
    
    try:
        # Nodos Entrevista
        query = """
            MATCH (e:Entrevista {project_id: $project_id})
            RETURN COUNT(e) as count
        """
        tx = neo4j_conn.session()
        result_set = tx.run(query, {"project_id": project_id})
        count = result_set.single()[0]
        result["nodes"]["Entrevista"] = {"count": count}
        
        # Listar entrevistas
        query = """
            MATCH (e:Entrevista {project_id: $project_id})
            RETURN e.nombre as nombre, e.actor_principal as actor, e.area_tematica as area
            ORDER BY nombre
            LIMIT 20
        """
        result_set = tx.run(query, {"project_id": project_id})
        entrevistas = [dict(record) for record in result_set]
        result["nodes"]["Entrevista"]["items"] = entrevistas
        
        # Nodos Fragmento
        query = """
            MATCH (f:Fragmento {project_id: $project_id})
            RETURN COUNT(f) as count
        """
        result_set = tx.run(query, {"project_id": project_id})
        count = result_set.single()[0]
        result["nodes"]["Fragmento"] = {"count": count}
        
        # Nodos Codigo
        query = """
            MATCH (c:Codigo {project_id: $project_id})
            RETURN COUNT(c) as count
        """
        result_set = tx.run(query, {"project_id": project_id})
        count = result_set.single()[0]
        result["nodes"]["Codigo"] = {"count": count}
        
        # Top códigos por relaciones
        query = """
            MATCH (c:Codigo {project_id: $project_id})-[r:ASIGNADO_A]->(f:Fragmento)
            RETURN c.nombre as codigo, COUNT(f) as fragmentos
            ORDER BY COUNT(f) DESC
            LIMIT 10
        """
        result_set = tx.run(query, {"project_id": project_id})
        top_codes = [dict(record) for record in result_set]
        result["nodes"]["Codigo"]["top_by_fragments"] = top_codes
        
        # Relaciones
        query = """
            MATCH ()-[r]-() 
            WHERE (r.project_id = $project_id OR 
                   EXISTS((h)-[r]) OR 
                   EXISTS((t)-[r]))
            RETURN type(r) as type, COUNT(r) as count
            GROUP BY type
        """
        result_set = tx.run(query, {"project_id": project_id})
        relations = [dict(record) for record in result_set]
        result["relationships"] = relations if relations else []
        
        tx.close()
    
    except Exception as e:
        result["error"] = str(e)
    
    return result


def audit_qdrant(qdrant_client, project_id: str) -> Dict[str, Any]:
    """Audita estado de Qdrant para el proyecto."""
    
    result = {
        "database": "Qdrant",
        "project_id": project_id,
        "collections": {}
    }
    
    try:
        # Listar colecciones
        collections = qdrant_client.get_collections()
        result["available_collections"] = [c.name for c in collections.collections]
        
        # Buscar colecciones del proyecto
        for collection in collections.collections:
            coll_name = collection.name
            if project_id in coll_name or "default" in coll_name:
                try:
                    info = qdrant_client.get_collection(coll_name)
                    result["collections"][coll_name] = {
                        "points_count": info.points_count,
                        "vector_size": info.config.params.vectors.size,
                        "status": str(info.status),
                    }
                except Exception as e:
                    result["collections"][coll_name] = {"error": str(e)}
    
    except Exception as e:
        result["error"] = str(e)
    
    return result


def audit_blob_storage(settings, project_id: str) -> Dict[str, Any]:
    """Audita estado de Azure Blob Storage para el proyecto."""
    
    result = {
        "database": "Azure Blob Storage",
        "project_id": project_id,
        "containers": {}
    }
    
    try:
        from azure.storage.blob import BlobServiceClient
        from azure.core.exceptions import AzureError
        
        blob_client = BlobServiceClient.from_connection_string(
            settings.azure_storage_connection_string
        )
        
        # Listar contenedores
        containers = blob_client.list_containers()
        container_names = [c.name for c in containers]
        
        # Buscar contenedor de entrevistas
        interviews_container = f"interviews/{project_id}"
        if interviews_container in container_names or "interviews" in container_names:
            try:
                container_client = blob_client.get_container_client(
                    interviews_container if interviews_container in container_names else "interviews"
                )
                blobs = list(container_client.list_blobs())
                
                project_blobs = [
                    {
                        "name": b.name,
                        "size": b.size,
                        "last_modified": b.last_modified.isoformat() if b.last_modified else None,
                    }
                    for b in blobs
                    if project_id in b.name or "default" in b.name
                ]
                
                result["containers"]["interviews"] = {
                    "total_blobs": len(project_blobs),
                    "blobs": project_blobs[:20],  # Primeros 20
                }
            except Exception as e:
                result["containers"]["interviews"] = {"error": str(e)}
    
    except ImportError:
        result["error"] = "Azure SDK not installed"
    except Exception as e:
        result["error"] = str(e)
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Auditar estado de datos en todas las bases de datos."
    )
    parser.add_argument("--project-id", required=True, help="UUID del proyecto")
    parser.add_argument("--account", help="Email de la cuenta")
    parser.add_argument("--detailed", action="store_true", help="Mostrar detalles completos")
    parser.add_argument("--env", default=".env", help="Archivo .env a cargar")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    
    args = parser.parse_args()
    
    # Cargar configuración
    settings = load_settings(env_file=args.env)
    clients = build_service_clients(settings)
    
    print(f"\n{'='*80}")
    print(f"🔍 AUDITORÍA DE ESTADO - PROYECTO: {args.project_id}")
    if args.account:
        print(f"   Cuenta: {args.account}")
    print(f"   Timestamp: {datetime.now().isoformat()}")
    print(f"{'='*80}\n")
    
    audit_results = {}
    
    try:
        # PostgreSQL
        print("📊 Auditando PostgreSQL...")
        audit_results["postgresql"] = audit_postgresql(clients.postgres, args.project_id)
        print(f"   ✅ {audit_results['postgresql']['tables']['entrevista_fragmentos']['total_records']} fragmentos")
        print(f"   ✅ {audit_results['postgresql']['tables']['analisis_codigos_abiertos']['unique_codes']} códigos únicos")
        
        # Neo4j
        print("\n📊 Auditando Neo4j...")
        audit_results["neo4j"] = audit_neo4j(clients.neo4j, args.project_id)
        print(f"   ✅ {audit_results['neo4j']['nodes'].get('Entrevista', {}).get('count', 0)} entrevistas")
        print(f"   ✅ {audit_results['neo4j']['nodes'].get('Fragmento', {}).get('count', 0)} fragmentos")
        print(f"   ✅ {audit_results['neo4j']['nodes'].get('Codigo', {}).get('count', 0)} códigos")
        
        # Qdrant
        print("\n📊 Auditando Qdrant...")
        audit_results["qdrant"] = audit_qdrant(clients.qdrant, args.project_id)
        collections_info = {
            k: v.get("points_count", 0)
            for k, v in audit_results['qdrant']['collections'].items()
        }
        total_qdrant = sum(collections_info.values())
        print(f"   ✅ {total_qdrant} puntos en {len(collections_info)} colecciones")
        
        # Blob Storage
        print("\n📊 Auditando Azure Blob Storage...")
        audit_results["blob_storage"] = audit_blob_storage(settings, args.project_id)
        if "interviews" in audit_results['blob_storage']['containers']:
            blob_count = audit_results['blob_storage']['containers']['interviews'].get('total_blobs', 0)
            print(f"   ✅ {blob_count} archivos")
        else:
            print(f"   ⚠️  No se encontraron archivos")
    
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    finally:
        clients.close()
    
    # Mostrar resumen
    print(f"\n{'='*80}")
    print("📋 RESUMEN")
    print(f"{'='*80}\n")
    
    if audit_results.get('postgresql', {}).get('tables', {}).get('entrevista_fragmentos'):
        pg = audit_results['postgresql']['tables']['entrevista_fragmentos']
        print(f"PostgreSQL:")
        print(f"  • Fragmentos: {pg.get('total_records', 0)}")
        print(f"  • Archivos únicos: {pg.get('unique_files', 0)}")
        if args.detailed and pg.get('files'):
            print(f"\n  Archivos ingestados:")
            for f in pg['files'][:10]:
                print(f"    - {f['archivo']}: {f['fragmentos']} fragmentos")
    
    if audit_results.get('neo4j', {}).get('nodes'):
        neo = audit_results['neo4j']['nodes']
        print(f"\nNeo4j:")
        print(f"  • Entrevistas: {neo.get('Entrevista', {}).get('count', 0)}")
        print(f"  • Fragmentos: {neo.get('Fragmento', {}).get('count', 0)}")
        print(f"  • Códigos: {neo.get('Codigo', {}).get('count', 0)}")
        if args.detailed and neo.get('Entrevista', {}).get('items'):
            print(f"\n  Entrevistas en Neo4j:")
            for e in neo['Entrevista'].get('items', [])[:5]:
                print(f"    - {e.get('nombre', '?')}")
    
    if audit_results.get('qdrant', {}).get('collections'):
        print(f"\nQdrant:")
        for coll_name, info in audit_results['qdrant']['collections'].items():
            print(f"  • {coll_name}: {info.get('points_count', 0)} puntos")
    
    if audit_results.get('blob_storage', {}).get('containers', {}).get('interviews'):
        blob = audit_results['blob_storage']['containers']['interviews']
        print(f"\nBlob Storage:")
        print(f"  • Archivos: {blob.get('total_blobs', 0)}")
        if args.detailed and blob.get('blobs'):
            print(f"\n  Archivos almacenados:")
            for b in blob['blobs'][:5]:
                size_mb = b['size'] / (1024*1024)
                print(f"    - {b['name']}: {size_mb:.2f} MB")
    
    # Consistencia
    print(f"\n{'='*80}")
    print("🔗 CONSISTENCIA ENTRE BASES")
    print(f"{'='*80}\n")
    
    pg_frags = audit_results.get('postgresql', {}).get('tables', {}).get('entrevista_fragmentos', {}).get('total_records', 0)
    neo_frags = audit_results.get('neo4j', {}).get('nodes', {}).get('Fragmento', {}).get('count', 0)
    qdrant_total = sum(
        v.get('points_count', 0)
        for v in audit_results.get('qdrant', {}).get('collections', {}).values()
    )
    
    print(f"Fragmentos en PostgreSQL: {pg_frags}")
    print(f"Fragmentos en Neo4j:      {neo_frags}")
    print(f"Puntos en Qdrant:         {qdrant_total}")
    
    if pg_frags == neo_frags == qdrant_total:
        print(f"\n✅ CONSISTENCIA OK: Todas las bases coinciden")
    else:
        print(f"\n⚠️  INCONSISTENCIA DETECTADA:")
        if pg_frags != neo_frags:
            print(f"   • PostgreSQL ({pg_frags}) ≠ Neo4j ({neo_frags})")
        if pg_frags != qdrant_total:
            print(f"   • PostgreSQL ({pg_frags}) ≠ Qdrant ({qdrant_total})")
    
    # Exportar JSON si se solicita
    if args.format == "json":
        output_file = f"audit_result_{args.project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(audit_results, f, indent=2, default=str)
        print(f"\n💾 Resultados guardados en: {output_file}")
    
    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    main()
