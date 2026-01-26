"""Verificar estructura de tabla analisis_codigos_abiertos"""
from app.settings import load_settings
from app.clients import get_pg_pool

settings = load_settings()
pool = get_pg_pool(settings)
conn = pool.getconn()
try:
    cur = conn.cursor()
    
    # 1. Ver columnas
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'analisis_codigos_abiertos'
        ORDER BY ordinal_position
    """)
    print("=== COLUMNAS DE analisis_codigos_abiertos ===")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")
    
    # 2. Ver valores de proyecto
    cur.execute("""
        SELECT proyecto, COUNT(*) 
        FROM analisis_codigos_abiertos 
        GROUP BY proyecto 
        ORDER BY COUNT(*) DESC
        LIMIT 10
    """)
    print("\n=== VALORES DE 'proyecto' ===")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]} registros")
    
    # 3. Buscar project_id si existe
    cur.execute("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = 'analisis_codigos_abiertos' 
        AND column_name LIKE '%project%'
    """)
    project_cols = [r[0] for r in cur.fetchall()]
    print(f"\n=== COLUMNAS con 'project' ===: {project_cols}")
    
finally:
    pool.putconn(conn)
