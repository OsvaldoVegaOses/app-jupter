from app.clients import get_pg_connection
from app.settings import load_settings

s = load_settings()
c = get_pg_connection(s)
cur = c.cursor()

cur.execute("SELECT COUNT(*) FROM codigos_candidatos")
count = cur.fetchone()[0]
print(f"Total rows in codigos_candidatos: {count}")

if count > 0:
    cur.execute("SELECT id, codigo, status, source FROM codigos_candidatos LIMIT 5")
    print("\nSample data:")
    for row in cur.fetchall():
        print(f"  {row}")

c.close()
