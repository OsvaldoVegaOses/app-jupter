#!/usr/bin/env python3
"""Check exactly what's in app_users, output to file."""
import psycopg2

conn = psycopg2.connect(
    host='appjupter.postgres.database.azure.com',
    port=5432,
    user='Osvaldo',
    password='A51b91c5!',
    dbname='entrevistas',
    sslmode='require'
)

cur = conn.cursor()

# Get column names
cur.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'app_users'
    ORDER BY ordinal_position
""")
columns = [r[0] for r in cur.fetchall()]

with open('scripts/columns_output.txt', 'w') as f:
    f.write(f"Columns in app_users:\n")
    for c in columns:
        f.write(f"  - {c}\n")
    
    # Check required columns
    required = ['organization_id', 'full_name', 'role', 'is_active']
    missing = [c for c in required if c not in columns]
    if missing:
        f.write(f"\n⚠️ MISSING COLUMNS: {missing}\n")
    else:
        f.write(f"\n✅ All required columns present\n")

print("Output written to scripts/columns_output.txt")
conn.close()
