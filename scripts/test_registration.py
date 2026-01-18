"""Test de registro directo para Azure PostgreSQL."""
import os
import sys
import traceback

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import psycopg2

def test_registration():
    print("="*60)
    print("TEST DE REGISTRO EN AZURE POSTGRESQL")
    print("="*60)
    
    # 1. Test connection
    print("\n1. Probando conexión...")
    try:
        conn = psycopg2.connect(
            host=os.getenv('PGHOST'),
            user=os.getenv('PGUSER'),
            password=os.getenv('PGPASSWORD'),
            dbname=os.getenv('PGDATABASE'),
            sslmode='require'
        )
        print(f"   ✓ Conectado a: {os.getenv('PGHOST')}")
    except Exception as e:
        print(f"   ✗ Error conexión: {e}")
        return

    # 2. Test ensure_users_table
    print("\n2. Probando ensure_users_table...")
    try:
        from app.postgres_block import ensure_users_table
        ensure_users_table(conn)
        print("   ✓ Tablas creadas/verificadas OK")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        traceback.print_exc()
        return

    # 3. Test create_user
    print("\n3. Probando create_user...")
    try:
        from app.postgres_block import create_user
        from backend.auth_service import hash_password
        
        pwd = hash_password('TestPass123!')
        user = create_user(conn, 'scripttest@test.com', pwd, 'Script Test')
        print(f"   ✓ Usuario creado: {user['email']}")
        print(f"     ID: {user['id']}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        traceback.print_exc()
        return

    # 4. List users
    print("\n4. Listando usuarios...")
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, email, role FROM app_users ORDER BY created_at DESC LIMIT 5")
        for row in cur.fetchall():
            print(f"   - {row[1]} ({row[2]})")
        cur.close()
    except Exception as e:
        print(f"   ✗ Error: {e}")

    conn.close()
    print("\n" + "="*60)
    print("TEST COMPLETADO")
    print("="*60)

if __name__ == "__main__":
    test_registration()
