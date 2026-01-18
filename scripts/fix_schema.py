"""Script para agregar columnas faltantes a app_users."""
import os
from dotenv import load_dotenv
load_dotenv()
import psycopg2

conn = psycopg2.connect(
    host=os.getenv('PGHOST'),
    user=os.getenv('PGUSER'),
    password=os.getenv('PGPASSWORD'),
    dbname=os.getenv('PGDATABASE'),
    sslmode='require'
)
cur = conn.cursor()

print("Verificando y agregando columnas faltantes a app_users...")

# Columnas que pueden faltar
alterations = [
    ("is_verified", "BOOLEAN DEFAULT false"),
    ("updated_at", "TIMESTAMPTZ DEFAULT NOW()"),
    ("last_login_at", "TIMESTAMPTZ"),
]

for col_name, col_type in alterations:
    try:
        cur.execute(f"ALTER TABLE app_users ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
        print(f"  ✓ {col_name} OK")
    except Exception as e:
        print(f"  ✗ {col_name}: {e}")

conn.commit()

# Verificar columnas
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'app_users'")
columns = [r[0] for r in cur.fetchall()]
print(f"\nColumnas en app_users: {columns}")

conn.close()
print("\n¡Esquema actualizado!")
