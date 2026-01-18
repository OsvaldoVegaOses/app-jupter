#!/usr/bin/env python3
"""Check existing tables in Azure PostgreSQL."""
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
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    ORDER BY table_name
""")
tables = [r[0] for r in cur.fetchall()]
print("Existing tables:")
for t in tables:
    print(f"  - {t}")

if 'users' not in tables:
    print("\n⚠️ Table 'users' does NOT exist!")
    
conn.close()
