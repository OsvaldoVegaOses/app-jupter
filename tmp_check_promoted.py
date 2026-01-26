"""Verificar estado de candidatos validados."""
from app.clients import get_pg_pool
from app.settings import load_settings

s = load_settings()
pool = get_pg_pool(s)
pg = pool.getconn()

print("=== Estadísticas generales ===")
with pg.cursor() as cur:
    cur.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN promovido_en IS NULL THEN 1 ELSE 0 END) as sin_promover,
            SUM(CASE WHEN promovido_en IS NOT NULL THEN 1 ELSE 0 END) as promovidos
        FROM codigos_candidatos 
        WHERE estado = 'validado' AND project_id = 'jd-007'
    """)
    r = cur.fetchone()
    print(f"Total validados: {r[0]}")
    print(f"Sin promover: {r[1]}")
    print(f"Ya promovidos: {r[2]}")

print("\n=== Los 13 sin promover (detalles) ===")
with pg.cursor() as cur:
    cur.execute("""
        SELECT id, codigo, fragmento_id, archivo, fuente_detalle, created_at
        FROM codigos_candidatos 
        WHERE estado = 'validado' 
          AND project_id = 'jd-007'
          AND promovido_en IS NULL
        ORDER BY created_at DESC
    """)
    for r in cur.fetchall():
        frag = r[2] if r[2] else "NULL"
        arch = r[3] if r[3] else "NULL"
        print(f"ID {r[0]}: codigo='{r[1][:30]}...' frag_id={frag} archivo={arch}")

pg.close()
