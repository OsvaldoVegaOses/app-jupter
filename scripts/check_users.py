#!/usr/bin/env python3
"""Check app_users table structure and data."""
import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("PGHOST"),
    port=int(os.getenv("PGPORT", "5432")),
    user=os.getenv("PGUSER"),
    password=os.getenv("PGPASSWORD"),
    dbname=os.getenv("PGDATABASE"),
    sslmode=os.getenv("PGSSLMODE", "require"),
)

cur = conn.cursor()

# Check table structure
cur.execute("""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns 
    WHERE table_name = 'app_users'
    ORDER BY ordinal_position
""")
print("Table structure - app_users:")
for col in cur.fetchall():
    print(f"  {col[0]}: {col[1]} (nullable: {col[2]})")

print("\nUsers data:")
cur.execute(
    """
    SELECT id, email, full_name, role, organization_id, is_active, last_login_at
    FROM app_users
    ORDER BY created_at DESC
    """
)
columns = [desc[0] for desc in cur.description]
print(f"Columns: {columns}")
for row in cur.fetchall():
    print(dict(zip(columns, row)))

conn.close()
