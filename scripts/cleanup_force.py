#!/usr/bin/env python3
"""
Limpieza completa - investigar y forzar eliminación.
"""
from app.settings import load_settings
from app.clients import build_service_clients

def main():
    s = load_settings()
    c = build_service_clients(s)
    
    KEEP_PROJECT = "jd-007"
    KEEP_USER = "osvaldovegaoses@gmail.com"
    
    with c.postgres.cursor() as cur:
        # 1. Ver foreign keys
        print("=" * 70)
        print("INVESTIGANDO FOREIGN KEYS")
        print("=" * 70)
        
        cur.execute("""
            SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = 'proyectos'
        """)
        fks = cur.fetchall()
        print(f"\nForeign keys apuntando a proyectos: {len(fks)}")
        for fk in fks:
            print(f"  - {fk[0]}.{fk[1]} -> {fk[2]}")
        
        # 2. Proyectos a eliminar
        cur.execute("SELECT id, name FROM proyectos WHERE id != %s", (KEEP_PROJECT,))
        projects_to_delete = [p[0] for p in cur.fetchall()]
        print(f"\nProyectos a eliminar: {projects_to_delete}")
        
        # 3. Eliminar datos relacionados primero
        print("\n" + "=" * 70)
        print("ELIMINANDO DATOS RELACIONADOS")
        print("=" * 70)
        
        # Tablas que tienen project_id
        tables_with_project = [
            "stage0_sampling_criteria",
            "stage0_consents", 
            "stage0_actors",
            "stage0_analysis_plans",
            "stage0_protocols",
            "project_audit_log",
            "discovery_runs",
            "discovery_navigation_log",
            "interview_reports",
            "analysis_memos",
            "analysis_reports",
            "doctoral_reports",
            "report_jobs",
            "codigos_candidatos",
            "analisis_codigos_abiertos",
            "entrevista_fragmentos",
        ]
        
        for table in tables_with_project:
            try:
                cur.execute(f"""
                    DELETE FROM "{table}" 
                    WHERE project_id != %s OR project_id IS NULL
                """, (KEEP_PROJECT,))
                if cur.rowcount > 0:
                    print(f"  {table}: {cur.rowcount} eliminados")
                c.postgres.commit()
            except Exception as e:
                c.postgres.rollback()
        
        # 4. Ahora eliminar proyectos
        print("\n" + "=" * 70)
        print("ELIMINANDO PROYECTOS")
        print("=" * 70)
        
        for pid in projects_to_delete:
            try:
                cur.execute("DELETE FROM proyectos WHERE id = %s", (pid,))
                c.postgres.commit()
                print(f"  ✅ {pid} eliminado")
            except Exception as e:
                c.postgres.rollback()
                print(f"  ❌ {pid}: {e}")
        
        # 5. Eliminar usuario
        print("\n" + "=" * 70)
        print("ELIMINANDO USUARIOS")
        print("=" * 70)
        
        try:
            cur.execute("DELETE FROM app_users WHERE email != %s", (KEEP_USER,))
            c.postgres.commit()
            print(f"  ✅ Usuarios eliminados: {cur.rowcount}")
        except Exception as e:
            c.postgres.rollback()
            print(f"  ❌ Error: {e}")
        
        # 6. Verificar estado final
        print("\n" + "=" * 70)
        print("ESTADO FINAL")
        print("=" * 70)
        
        cur.execute("SELECT id FROM proyectos")
        print(f"\nProyectos: {[p[0] for p in cur.fetchall()]}")
        
        cur.execute("SELECT email FROM app_users")
        print(f"Usuarios: {[u[0] for u in cur.fetchall()]}")
    
    c.close()

if __name__ == "__main__":
    main()
