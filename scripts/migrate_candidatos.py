"""Script para migrar columnas en codigos_candidatos."""
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

print('Migrando columnas en codigos_candidatos...')

# Check current columns
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'codigos_candidatos'")
cols = [r[0] for r in cur.fetchall()]
print(f'Columnas actuales: {cols}')

# Add project_id if missing and proyecto exists
if 'proyecto' in cols and 'project_id' not in cols:
    print('Renombrando proyecto -> project_id...')
    cur.execute('ALTER TABLE codigos_candidatos RENAME COLUMN proyecto TO project_id')
    print('  OK')
elif 'project_id' not in cols:
    print('Agregando project_id...')
    cur.execute("ALTER TABLE codigos_candidatos ADD COLUMN project_id TEXT DEFAULT 'default'")
    print('  OK')
else:
    print('project_id ya existe')

# Refresh column list
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'codigos_candidatos'")
cols = [r[0] for r in cur.fetchall()]

# Add other missing columns expected by the code
missing_cols = [
    ('cita', 'TEXT'),
    ('fuente_origen', "TEXT DEFAULT 'manual'"),
    ('fuente_detalle', 'JSONB'),
    ('score_confianza', 'FLOAT'),
    ('estado', "TEXT DEFAULT 'pendiente'"),
    ('validado_por', 'TEXT'),
    ('validado_en', 'TIMESTAMPTZ'),
    ('fusionado_a', 'TEXT'),
    ('memo', 'TEXT'),
    ('archivo', 'TEXT'),
    ('updated_at', 'TIMESTAMPTZ DEFAULT NOW()'),
]

for col_name, col_type in missing_cols:
    if col_name not in cols:
        try:
            cur.execute(f'ALTER TABLE codigos_candidatos ADD COLUMN IF NOT EXISTS {col_name} {col_type}')
            print(f'  Agregada: {col_name}')
        except Exception as e:
            print(f'  Error {col_name}: {e}')

conn.commit()
print('\nMigración completada!')

# Verify
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'codigos_candidatos'")
cols = [r[0] for r in cur.fetchall()]
print(f'Columnas finales: {cols}')

conn.close()
