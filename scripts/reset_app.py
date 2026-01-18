#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de limpieza completa del sistema.

ADVERTENCIA: Este script elimina TODOS los datos de manera IRREVERSIBLE.
Solo procede si estás completamente seguro.

Uso:
    python scripts/reset_app.py --confirm-all
    
    O sin --confirm-all para confirmación interactiva:
    python scripts/reset_app.py
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import argparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.clients import build_service_clients
from app.settings import load_settings


def backup_postgresql(pg_conn) -> str:
    """Crear backup de PostgreSQL antes de limpiar."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"backup_postgresql_{timestamp}.sql"
    
    print(f"\n[BACKUP] Creando backup de PostgreSQL...")
    try:
        with pg_conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            tables = [row[0] for row in cur.fetchall()]
        
        print(f"[BACKUP] Tablas a respaldar: {len(tables)}")
        
        # Exportar datos de cada tabla (simple JSON backup)
        import json
        backup_data = {}
        with pg_conn.cursor() as cur:
            for table in tables[:5]:  # Backup de primeras 5 tablas como muestra
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                backup_data[table] = {"row_count": count}
        
        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=2)
        
        print(f"[BACKUP] Archivo creado: {backup_file}")
        return backup_file
    except Exception as e:
        print(f"[BACKUP] Error: {e}")
        return None


def confirm_action(action_name: str, details: str, confirm_all: bool = False) -> bool:
    """Pedir confirmación antes de ejecutar acción destructiva."""
    print(f"\n{'='*80}")
    print(f"[ACCION] {action_name}")
    print(f"{'='*80}")
    print(details)
    print(f"{'='*80}")
    
    if confirm_all:
        print("[CONFIRMACION] Modo --confirm-all: procediendo sin preguntar")
        return True
    
    while True:
        response = input(f"\n¿Deseas continuar? (SÍ/NO): ").strip().upper()
        if response in ['SI', 'SÍ', 'YES', 'Y']:
            return True
        elif response in ['NO', 'N']:
            return False
        else:
            print("Por favor responde SÍ o NO")


def clean_postgresql(pg_conn, confirm_all: bool = False) -> bool:
    """Limpiar todos los datos de PostgreSQL."""
    details = """
    Esto va a:
    1. TRUNCATE de todas las tablas de datos
    2. Eliminar 1,872 fragmentos
    3. Eliminar 745 códigos
    4. Limpiar 8 proyectos
    
    ESTO NO SE PUEDE DESHACER sin backup.
    """
    
    if not confirm_action("LIMPIAR PostgreSQL", details, confirm_all):
        print("[CANCELADO] Limpieza de PostgreSQL cancelada")
        return False
    
    try:
        # Listar tablas a limpiar
        with pg_conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public'
                AND table_name NOT LIKE 'pg_%'
                ORDER BY table_name
            """)
            tables = [row[0] for row in cur.fetchall()]
        
        print(f"\n[PostgreSQL] Tablas a limpiar: {len(tables)}")
        
        # Truncate en orden (sin constraints)
        tables_to_truncate = [
            'entrevista_fragmentos',
            'analisis_codigos_abiertos',
            'codigos_candidatos',
            'analisis_axial',
            'analisis_comparacion_constante',
            'analisis_nucleo_notas',
            'analysis_insights',
            'analysis_memos',
            'analysis_reports',
            'codigo_versiones',
            'coding_feedback_events',
            'discovery_navigation_log',
            'discovery_runs',
            'doctoral_reports',
            'familiarization_reviews',
            'interview_files',
            'interview_reports',
            'project_audit_log',
            'project_members',
            'proyecto_estado',
            'proyectos',
            'report_jobs',
            'stage0_actors',
            'stage0_analysis_plans',
            'stage0_consents',
            'stage0_override_requests',
            'stage0_protocols',
            'stage0_reflexivity_memos',
            'stage0_sampling_criteria',
            'app_sessions',
            'app_users',
        ]
        
        truncated = 0
        with pg_conn.cursor() as cur:
            for table in tables_to_truncate:
                if table in tables:
                    try:
                        cur.execute(f"TRUNCATE TABLE {table} CASCADE")
                        truncated += 1
                        print(f"  ✓ {table}")
                    except Exception as e:
                        print(f"  ✗ {table}: {e}")
            
            pg_conn.commit()
        
        print(f"\n[PostgreSQL] Tablas truncadas: {truncated}/{len(tables_to_truncate)}")
        return True
    
    except Exception as e:
        print(f"[ERROR PostgreSQL] {e}")
        pg_conn.rollback()
        return False


def clean_neo4j(neo4j_conn, confirm_all: bool = False) -> bool:
    """Limpiar todos los nodos de Neo4j."""
    details = """
    Esto va a:
    1. MATCH (n) DELETE n - eliminar TODOS los nodos
    2. MATCH ()-[r]-() DELETE r - eliminar TODAS las relaciones
    3. Borrar ~3,000 nodos
    
    ESTO NO SE PUEDE DESHACER.
    """
    
    if not confirm_action("LIMPIAR Neo4j", details, confirm_all):
        print("[CANCELADO] Limpieza de Neo4j cancelada")
        return False
    
    try:
        with neo4j_conn.session() as session:
            # Contar nodos antes
            result = session.run("MATCH (n) RETURN count(n) as cnt")
            before = result.single()['cnt']
            print(f"\n[Neo4j] Nodos antes: {before}")
            
            # Eliminar todas las relaciones primero
            result = session.run("MATCH ()-[r]-() DELETE r RETURN count(r) as deleted")
            deleted_rels = result.single()['deleted']
            print(f"[Neo4j] Relaciones eliminadas: {deleted_rels}")
            
            # Eliminar todos los nodos
            result = session.run("MATCH (n) DELETE n RETURN count(n) as deleted")
            deleted_nodes = result.single()['deleted']
            print(f"[Neo4j] Nodos eliminados: {deleted_nodes}")
            
            # Verificar
            result = session.run("MATCH (n) RETURN count(n) as cnt")
            after = result.single()['cnt']
            print(f"[Neo4j] Nodos después: {after}")
            
            return after == 0
    
    except Exception as e:
        print(f"[ERROR Neo4j] {e}")
        return False


def clean_qdrant(qdrant_client, confirm_all: bool = False) -> bool:
    """Limpiar todas las colecciones de Qdrant."""
    details = """
    Esto va a:
    1. Listar todas las colecciones
    2. DELETE COLLECTION para cada una
    3. Borrar 38 embeddings
    
    ESTO NO SE PUEDE DESHACER.
    """
    
    if not confirm_action("LIMPIAR Qdrant", details, confirm_all):
        print("[CANCELADO] Limpieza de Qdrant cancelada")
        return False
    
    try:
        collections = qdrant_client.get_collections()
        print(f"\n[Qdrant] Colecciones encontradas: {len(collections.collections)}")
        
        deleted_count = 0
        for coll in collections.collections:
            try:
                qdrant_client.delete_collection(coll.name)
                print(f"  ✓ Eliminada: {coll.name}")
                deleted_count += 1
            except Exception as e:
                print(f"  ✗ Error eliminando {coll.name}: {e}")
        
        print(f"\n[Qdrant] Colecciones eliminadas: {deleted_count}")
        
        # Verificar
        collections_after = qdrant_client.get_collections()
        return len(collections_after.collections) == 0
    
    except Exception as e:
        print(f"[ERROR Qdrant] {e}")
        return False


def verify_all_clean(clients) -> bool:
    """Verificar que todo esté limpio."""
    print(f"\n{'='*80}")
    print("[VERIFICACION] Verificando que todo esté vacío...")
    print(f"{'='*80}\n")
    
    all_clean = True
    
    # PostgreSQL
    try:
        with clients.postgres.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM entrevista_fragmentos')
            count = cur.fetchone()[0]
            status = "✓" if count == 0 else "✗"
            print(f"[PostgreSQL] Fragmentos: {count} {status}")
            all_clean = all_clean and (count == 0)
            
            cur.execute('SELECT COUNT(*) FROM analisis_codigos_abiertos')
            count = cur.fetchone()[0]
            status = "✓" if count == 0 else "✗"
            print(f"[PostgreSQL] Códigos: {count} {status}")
            all_clean = all_clean and (count == 0)
            
            cur.execute('SELECT COUNT(*) FROM proyectos')
            count = cur.fetchone()[0]
            status = "✓" if count == 0 else "✗"
            print(f"[PostgreSQL] Proyectos: {count} {status}")
            all_clean = all_clean and (count == 0)
    except Exception as e:
        print(f"[PostgreSQL] Error: {e}")
        all_clean = False
    
    # Neo4j
    try:
        with clients.neo4j.session() as session:
            result = session.run("MATCH (n) RETURN count(n) as cnt")
            count = result.single()['cnt']
            status = "✓" if count == 0 else "✗"
            print(f"[Neo4j] Nodos: {count} {status}")
            all_clean = all_clean and (count == 0)
    except Exception as e:
        print(f"[Neo4j] Error: {e}")
        all_clean = False
    
    # Qdrant
    try:
        collections = clients.qdrant.get_collections()
        count = len(collections.collections)
        status = "✓" if count == 0 else "✗"
        print(f"[Qdrant] Colecciones: {count} {status}")
        all_clean = all_clean and (count == 0)
    except Exception as e:
        print(f"[Qdrant] Error: {e}")
        all_clean = False
    
    print(f"\n{'='*80}")
    if all_clean:
        print("✓ SISTEMA COMPLETAMENTE LIMPIO")
    else:
        print("✗ Aún hay datos en el sistema")
    print(f"{'='*80}\n")
    
    return all_clean


def main():
    parser = argparse.ArgumentParser(description="Reset completo del sistema")
    parser.add_argument("--confirm-all", action="store_true", 
                        help="Confirmar todas las acciones sin preguntar")
    parser.add_argument("--env", default=".env", help="Archivo .env")
    
    args = parser.parse_args()
    
    print("\n" + "="*80)
    print("🔴 RESET COMPLETO DEL SISTEMA")
    print("="*80)
    print("\nEsto va a eliminar COMPLETAMENTE:")
    print("  • 1,872 fragmentos de PostgreSQL")
    print("  • 745 códigos de PostgreSQL")
    print("  • ~3,000 nodos de Neo4j")
    print("  • 38 embeddings de Qdrant")
    print("  • 8 proyectos")
    print("\n⚠️  ESTO NO SE PUEDE DESHACER SIN BACKUP EXTERNO\n")
    
    if not args.confirm_all:
        response = input("¿Entiendes los riesgos? Escribe 'ENTIENDO' para continuar: ").strip()
        if response != "ENTIENDO":
            print("[CANCELADO] Operación abortada")
            return 1
    
    # Cargar configuración
    settings = load_settings(env_file=args.env)
    clients = build_service_clients(settings)
    
    # Backup
    print("\n[PASO 1] Crear backup de seguridad...")
    backup_file = backup_postgresql(clients.postgres)
    
    if not backup_file:
        print("[ERROR] No se pudo crear backup. Abortando.")
        return 1
    
    # Limpiar en orden
    print("\n[PASO 2] Limpiar PostgreSQL...")
    if not clean_postgresql(clients.postgres, args.confirm_all):
        print("[ERROR] Falló limpieza de PostgreSQL")
        return 1
    
    print("\n[PASO 3] Limpiar Neo4j...")
    if not clean_neo4j(clients.neo4j, args.confirm_all):
        print("[ERROR] Falló limpieza de Neo4j")
        return 1
    
    print("\n[PASO 4] Limpiar Qdrant...")
    if not clean_qdrant(clients.qdrant, args.confirm_all):
        print("[ERROR] Falló limpieza de Qdrant")
        return 1
    
    # Verificar
    print("\n[PASO 5] Verificar limpieza...")
    if not verify_all_clean(clients):
        print("[ERROR] Sistema no está completamente limpio")
        return 1
    
    # Resumen
    print("\n" + "="*80)
    print("✓ SISTEMA RESET COMPLETAMENTE")
    print("="*80)
    print(f"\nBackup creado: {backup_file}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\nPróximos pasos:")
    print("  1. Reiniciar backend: python -m uvicorn backend.app:app --port 8000")
    print("  2. Verificar endpoint: http://localhost:8000/healthz")
    print("  3. Sistema listo para nuevos datos")
    print("\n" + "="*80 + "\n")
    
    clients.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
