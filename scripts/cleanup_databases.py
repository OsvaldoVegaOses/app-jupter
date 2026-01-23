#!/usr/bin/env python3
"""
Script de limpieza de bases de datos.
Mantiene solo:
- Usuario: osvaldovegaoses@gmail.com
- Organización: 6fc75e26-c0f4-4559-a2ef-10e508467661
- Proyecto: jd-007
"""
import sys
from app.settings import load_settings
from app.clients import build_service_clients

# Configuración de lo que se mantiene
KEEP_USER_EMAIL = "osvaldovegaoses@gmail.com"
KEEP_ORG_ID = "6fc75e26-c0f4-4559-a2ef-10e508467661"
KEEP_PROJECT_ID = "jd-007"

def cleanup_postgresql(c, dry_run=True):
    """Limpia PostgreSQL manteniendo solo el proyecto jd-007."""
    print("\n" + "=" * 70)
    print("POSTGRESQL CLEANUP")
    print("=" * 70)
    
    with c.postgres.cursor() as cur:
        # 1. Eliminar proyectos que no son jd-007
        print("\n📁 Proyectos a eliminar:")
        cur.execute("SELECT id, name FROM proyectos WHERE id != %s", (KEEP_PROJECT_ID,))
        projects_to_delete = cur.fetchall()
        for p in projects_to_delete:
            print(f"  ❌ {p[0]} ({p[1]})")
        
        if not dry_run and projects_to_delete:
            cur.execute("DELETE FROM proyectos WHERE id != %s", (KEEP_PROJECT_ID,))
            print(f"  → Eliminados: {cur.rowcount}")
        
        # 2. Eliminar usuario hola@nubeweb.cl
        print("\n👤 Usuarios a eliminar:")
        cur.execute("SELECT email FROM app_users WHERE email != %s", (KEEP_USER_EMAIL,))
        users_to_delete = cur.fetchall()
        for u in users_to_delete:
            print(f"  ❌ {u[0]}")
        
        if not dry_run and users_to_delete:
            cur.execute("DELETE FROM app_users WHERE email != %s", (KEEP_USER_EMAIL,))
            print(f"  → Eliminados: {cur.rowcount}")
        
        # 3. Tablas con project_id - eliminar datos de otros proyectos
        tables_with_project = [
            "codigos_candidatos",
            "analisis_codigos_abiertos",
            "entrevista_fragmentos",
            "discovery_runs",
            "discovery_navigation_log",
            "interview_reports",
            "analysis_memos",
            "analysis_reports",
            "doctoral_reports",
            "report_jobs",
            "stage0_protocols",
            "stage0_actors",
            "stage0_consents",
            "stage0_analysis_plans",
            "stage0_sampling_criteria",
            "project_audit_log",
        ]
        
        print("\n📊 Datos de otros proyectos a eliminar:")
        for table in tables_with_project:
            try:
                # Reset transaction state if needed
                c.postgres.rollback()
                cur.execute(f"""
                    SELECT COUNT(*) FROM "{table}" 
                    WHERE project_id IS NOT NULL AND project_id != %s
                """, (KEEP_PROJECT_ID,))
                count = cur.fetchone()[0]
                if count > 0:
                    print(f"  ❌ {table}: {count} rows")
                    if not dry_run:
                        cur.execute(f"""
                            DELETE FROM "{table}" 
                            WHERE project_id IS NOT NULL AND project_id != %s
                        """, (KEEP_PROJECT_ID,))
                        print(f"     → Eliminados: {cur.rowcount}")
                        c.postgres.commit()
            except Exception as e:
                # Tabla puede no existir o no tener project_id
                c.postgres.rollback()
        
        # 4. Limpiar sesiones antiguas
        print("\n🔐 Sesiones a limpiar:")
        try:
            cur.execute("SELECT COUNT(*) FROM app_sessions")
            sessions_count = cur.fetchone()[0]
            print(f"  ❌ app_sessions: {sessions_count} rows")
            if not dry_run:
                cur.execute("DELETE FROM app_sessions")
                print(f"  → Eliminados: {cur.rowcount}")
                c.postgres.commit()
        except Exception as e:
            c.postgres.rollback()
            print(f"  Error: {e}")
        
        if not dry_run:
            c.postgres.commit()
            print("\n✅ PostgreSQL limpiado y commit realizado")
        else:
            c.postgres.rollback()
            print("\n⚠️ DRY RUN - No se aplicaron cambios")


def cleanup_neo4j(c, dry_run=True):
    """Limpia Neo4j manteniendo solo el proyecto jd-007."""
    print("\n" + "=" * 70)
    print("NEO4J CLEANUP")
    print("=" * 70)
    
    with c.neo4j.session() as session:
        # Contar nodos de otros proyectos
        result = session.run("""
            MATCH (n) 
            WHERE n.project_id IS NOT NULL AND n.project_id <> $project
            RETURN labels(n)[0] AS label, COUNT(*) AS cnt
        """, project=KEEP_PROJECT_ID)
        
        print("\n📊 Nodos de otros proyectos a eliminar:")
        total_to_delete = 0
        for r in result:
            print(f"  ❌ {r['label']}: {r['cnt']}")
            total_to_delete += r['cnt']
        
        if total_to_delete == 0:
            print("  ✅ No hay nodos de otros proyectos")
        elif not dry_run:
            result = session.run("""
                MATCH (n) 
                WHERE n.project_id IS NOT NULL AND n.project_id <> $project
                DETACH DELETE n
                RETURN COUNT(*) AS deleted
            """, project=KEEP_PROJECT_ID)
            deleted = result.single()["deleted"]
            print(f"\n✅ Eliminados: {deleted} nodos")
        else:
            print("\n⚠️ DRY RUN - No se aplicaron cambios")


def cleanup_qdrant(c, s, dry_run=True):
    """Limpia Qdrant manteniendo solo el proyecto jd-007."""
    print("\n" + "=" * 70)
    print("QDRANT CLEANUP")
    print("=" * 70)
    
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    collection = s.qdrant.collection
    
    # Contar puntos de otros proyectos
    scroll_result = c.qdrant.scroll(
        collection_name=collection,
        limit=10000,
        with_payload=["project_id"],
    )
    
    other_project_ids = []
    for point in scroll_result[0]:
        pid = point.payload.get("project_id")
        if pid and pid != KEEP_PROJECT_ID:
            other_project_ids.append(point.id)
    
    print(f"\n📊 Puntos de otros proyectos a eliminar: {len(other_project_ids)}")
    
    if len(other_project_ids) == 0:
        print("  ✅ No hay puntos de otros proyectos")
    elif not dry_run:
        c.qdrant.delete(
            collection_name=collection,
            points_selector=other_project_ids,
        )
        print(f"\n✅ Eliminados: {len(other_project_ids)} puntos")
    else:
        print("\n⚠️ DRY RUN - No se aplicaron cambios")


def main():
    dry_run = "--execute" not in sys.argv
    
    if dry_run:
        print("=" * 70)
        print("🔍 MODO DRY RUN - Solo muestra qué se eliminaría")
        print("   Para ejecutar: python cleanup_databases.py --execute")
        print("=" * 70)
    else:
        print("=" * 70)
        print("⚠️  MODO EJECUCIÓN - SE ELIMINARÁN DATOS")
        print("=" * 70)
        confirm = input("¿Confirmar limpieza? (escribe 'SI' para continuar): ")
        if confirm != "SI":
            print("Cancelado.")
            return
    
    print(f"\n🎯 CONSERVANDO:")
    print(f"   Usuario: {KEEP_USER_EMAIL}")
    print(f"   Organización: {KEEP_ORG_ID}")
    print(f"   Proyecto: {KEEP_PROJECT_ID}")
    
    s = load_settings()
    c = build_service_clients(s)
    
    try:
        cleanup_postgresql(c, dry_run)
        cleanup_neo4j(c, dry_run)
        cleanup_qdrant(c, s, dry_run)
        
        print("\n" + "=" * 70)
        if dry_run:
            print("🔍 DRY RUN COMPLETADO - Ejecuta con --execute para aplicar")
        else:
            print("✅ LIMPIEZA COMPLETADA")
        print("=" * 70)
    finally:
        c.close()


if __name__ == "__main__":
    main()
