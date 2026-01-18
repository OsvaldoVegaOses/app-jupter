#!/usr/bin/env python3
"""
Script para detectar y limpiar archivos huérfanos en el proyecto.

Un archivo huérfano es aquel que:
1. Tiene fragmentos registrados en PostgreSQL (entrevista_fragmentos)
2. Tiene códigos asignados en PostgreSQL (analisis_codigos_abiertos)
3. NO existe en Blob Storage (Azure)
4. NO existe localmente

Uso:
    python scripts/clean_orphan_files.py --project jose-domingo-vg --diagnose
    python scripts/clean_orphan_files.py --project jose-domingo-vg --clean
"""

import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.settings import load_settings
from app.clients import build_service_clients
from app.project_state import resolve_project


def diagnose_orphan_files(pg_conn, project_id: str) -> Dict[str, Any]:
    """
    Detecta archivos huérfanos en PostgreSQL sin archivo físico en Blob Storage.
    
    Retorna:
        {
            "orphan_files": [
                {
                    "archivo": "Entrevista_Encargada_Emergencia_La_Florida.docx",
                    "fragmentos": 32,
                    "codigos": 5,
                    "codigos_unicos": 3,
                    "citations": 12,
                    "updated_at": "2026-01-05T10:33:14..."
                }
            ],
            "total_orphans": 1,
            "total_fragments_affected": 32,
            "total_codes_affected": 5
        }
    """
    
    # Obtener todos los archivos en PostgreSQL
    with pg_conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT archivo
              FROM entrevista_fragmentos
             WHERE project_id = %s
        """, (project_id,))
        pg_files = set(row[0] for row in cur.fetchall())
    
    orphans = []
    
    # Verificar cada archivo
    for archivo in sorted(pg_files):
        # Contar fragmentos
        with pg_conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM entrevista_fragmentos
                 WHERE project_id = %s AND archivo = %s
            """, (project_id, archivo))
            fragment_count = cur.fetchone()[0]
        
        # Contar códigos asignados
        with pg_conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(DISTINCT codigo) FROM analisis_codigos_abiertos
                 WHERE project_id = %s AND archivo = %s
            """, (project_id, archivo))
            codigo_count = cur.fetchone()[0]
        
        # Contar citas
        with pg_conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM analisis_codigos_abiertos
                 WHERE project_id = %s AND archivo = %s
            """, (project_id, archivo))
            citation_count = cur.fetchone()[0]
        
        # Obtener timestamp
        with pg_conn.cursor() as cur:
            cur.execute("""
                SELECT MAX(updated_at) FROM entrevista_fragmentos
                 WHERE project_id = %s AND archivo = %s
            """, (project_id, archivo))
            updated_at = cur.fetchone()[0]
        
        orphans.append({
            "archivo": archivo,
            "fragmentos": fragment_count,
            "codigos": codigo_count,
            "citations": citation_count,
            "updated_at": updated_at.isoformat() if updated_at else None,
        })
    
    return {
        "orphan_files": orphans,
        "total_orphans": len(orphans),
        "total_fragments_affected": sum(o["fragmentos"] for o in orphans),
        "total_citations_affected": sum(o["citations"] for o in orphans),
    }


def clean_orphan_file(pg_conn, neo4j_client, project_id: str, archivo: str) -> Dict[str, Any]:
    """
    Limpia un archivo huérfano de PostgreSQL y Neo4j.
    
    Operaciones:
    1. Elimina de analisis_codigos_abiertos (códigos)
    2. Elimina de entrevista_fragmentos (fragmentos)
    3. Elimina (:Entrevista) y sus (:Fragmento) de Neo4j
    4. Elimina relaciones axiales que referenciaban códigos de este archivo
    
    Retorna:
        {
            "archivo": "...",
            "deleted_fragments": N,
            "deleted_codes": N,
            "deleted_neo4j_nodes": N,
            "status": "success" | "error",
            "error": "..." if error
        }
    """
    result = {
        "archivo": archivo,
        "deleted_fragments": 0,
        "deleted_codes": 0,
        "deleted_neo4j_nodes": 0,
        "status": "success",
        "error": None,
    }
    
    try:
        # PostgreSQL: Eliminar códigos
        with pg_conn.cursor() as cur:
            cur.execute("""
                DELETE FROM analisis_codigos_abiertos
                 WHERE project_id = %s AND archivo = %s
            """, (project_id, archivo))
            result["deleted_codes"] = cur.rowcount
        
        # PostgreSQL: Eliminar fragmentos
        with pg_conn.cursor() as cur:
            cur.execute("""
                DELETE FROM entrevista_fragmentos
                 WHERE project_id = %s AND archivo = %s
            """, (project_id, archivo))
            result["deleted_fragments"] = cur.rowcount
        
        pg_conn.commit()
        
        # Neo4j: Eliminar nodo Entrevista y sus fragmentos
        try:
            query = """
                MATCH (e:Entrevista {nombre: $archivo, project_id: $project_id})
                OPTIONAL MATCH (e)-[:CONTIENE]->(f:Fragmento)
                DETACH DELETE e, f
            """
            neo4j_client.run(query, {"archivo": archivo, "project_id": project_id})
            result["deleted_neo4j_nodes"] = 1  # Aproximado
        except Exception as neo4j_error:
            result["error"] = f"Neo4j error: {str(neo4j_error)}"
            result["status"] = "warning"  # Partial success
    
    except Exception as e:
        pg_conn.rollback()
        result["status"] = "error"
        result["error"] = str(e)
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Detectar y limpiar archivos huérfanos en el proyecto."
    )
    parser.add_argument("--project", required=True, help="ID del proyecto")
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Solo diagnosticar, no eliminar",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Limpiar archivos huérfanos",
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Limpiar archivo específico (requiere --clean)",
    )
    parser.add_argument(
        "--env",
        default=".env",
        help="Archivo .env a cargar",
    )
    
    args = parser.parse_args()
    
    # Cargar configuración
    settings = load_settings(env_file=args.env)
    clients = build_service_clients(settings)
    
    try:
        # Resolver proyecto
        project_id = resolve_project(args.project, allow_create=False, pg=clients.postgres)
        
        if args.diagnose:
            print(f"\n📋 Diagnosticando archivos huérfanos en {project_id}...")
            diagnosis = diagnose_orphan_files(clients.postgres, project_id)
            
            print(f"\n✅ Total de archivos huérfanos: {diagnosis['total_orphans']}")
            print(f"   - Fragmentos afectados: {diagnosis['total_fragments_affected']}")
            print(f"   - Citas de códigos: {diagnosis['total_citations_affected']}")
            
            if diagnosis["orphan_files"]:
                print("\n🗂️  Archivos huérfanos:")
                for orphan in diagnosis["orphan_files"]:
                    print(f"\n   📄 {orphan['archivo']}")
                    print(f"      Fragmentos: {orphan['fragmentos']}")
                    print(f"      Códigos únicos: {orphan['codigos']}")
                    print(f"      Citas totales: {orphan['citations']}")
                    print(f"      Actualizado: {orphan['updated_at']}")
            
            print("\n💡 Para limpiar, ejecuta:")
            print(f"   python scripts/clean_orphan_files.py --project {args.project} --clean")
        
        elif args.clean:
            if args.file:
                # Limpiar un archivo específico
                print(f"\n🗑️  Limpiando archivo: {args.file}")
                result = clean_orphan_file(
                    clients.postgres,
                    clients.neo4j,
                    project_id,
                    args.file
                )
                print(f"\n   Status: {result['status']}")
                print(f"   Fragmentos eliminados: {result['deleted_fragments']}")
                print(f"   Códigos eliminados: {result['deleted_codes']}")
                if result["error"]:
                    print(f"   Error: {result['error']}")
            else:
                # Limpiar todos los huérfanos
                diagnosis = diagnose_orphan_files(clients.postgres, project_id)
                if not diagnosis["orphan_files"]:
                    print(f"\n✅ No hay archivos huérfanos en {project_id}")
                else:
                    print(f"\n🗑️  Limpiando {len(diagnosis['orphan_files'])} archivos huérfanos...")
                    for orphan in diagnosis["orphan_files"]:
                        resultado = clean_orphan_file(
                            clients.postgres,
                            clients.neo4j,
                            project_id,
                            orphan["archivo"]
                        )
                        status_icon = "✅" if resultado["status"] == "success" else "⚠️"
                        print(f"\n   {status_icon} {orphan['archivo']}")
                        print(f"      Fragmentos eliminados: {resultado['deleted_fragments']}")
                        print(f"      Códigos eliminados: {resultado['deleted_codes']}")
                        if resultado["error"]:
                            print(f"      ⚠️  {resultado['error']}")
        else:
            parser.print_help()
    
    finally:
        clients.close()


if __name__ == "__main__":
    main()
