"""Quick check of jd-008 project fragments in PostgreSQL."""
import os
import sys
sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv
load_dotenv()

from app.settings import load_settings
from app.clients import build_service_clients

settings = load_settings()
clients = build_service_clients(settings)
pg = clients.postgres

project = sys.argv[1] if len(sys.argv) > 1 else "jd-008"

with pg.cursor() as cur:
    # Contar fragmentos por archivo
    cur.execute("""
        SELECT archivo, COUNT(*) as cnt
        FROM entrevista_fragmentos
        WHERE project_id = %s
        GROUP BY archivo
        ORDER BY archivo
    """, (project,))
    rows = cur.fetchall()
    
    print(f"\\n=== Fragmentos en proyecto '{project}' ===")
    if rows:
        for archivo, cnt in rows:
            print(f"  {archivo}: {cnt} fragmentos")
        print(f"  TOTAL: {sum(r[1] for r in rows)} fragmentos en {len(rows)} archivos")
    else:
        print("  ⚠️ No hay fragmentos para este proyecto")
    
    # Verificar otros proyectos
    cur.execute("""
        SELECT project_id, COUNT(*) as cnt
        FROM entrevista_fragmentos
        GROUP BY project_id
        ORDER BY cnt DESC
    """)
    all_projects = cur.fetchall()
    print(f"\\n=== Todos los proyectos ===")
    for p, cnt in all_projects:
        marker = " <-- ESTE" if p == project else ""
        print(f"  {p}: {cnt} fragmentos{marker}")

pg.close()
