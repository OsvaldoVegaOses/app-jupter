"""
Script para inicializar tablas de auth y crear admin.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import psycopg2
import uuid
from datetime import datetime, timedelta
try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False
    import hashlib

def main():
    print("="*60)
    print("🔧 INICIALIZACIÓN DE TABLAS AUTH Y ADMIN")
    print("="*60)
    
    conn = psycopg2.connect(
        host=os.getenv("PGHOST"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        dbname=os.getenv("PGDATABASE"),
        sslmode=os.getenv("PGSSLMODE", "require")
    )
    cur = conn.cursor()
    
    # Check if app_users exists
    cur.execute("""
        SELECT EXISTS(
            SELECT 1 FROM information_schema.tables 
            WHERE table_schema='public' AND table_name='app_users'
        )
    """)
    table_exists = cur.fetchone()[0]
    print(f"\n✓ Tabla app_users existe: {table_exists}")
    
    if not table_exists:
        print("\n📦 Creando tablas de autenticación...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                full_name VARCHAR(255),
                role VARCHAR(50) DEFAULT 'analyst',
                organization_id UUID DEFAULT gen_random_uuid(),
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW(),
                last_login TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_sessions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES app_users(id) ON DELETE CASCADE,
                refresh_token TEXT NOT NULL,
                is_revoked BOOLEAN DEFAULT false,
                created_at TIMESTAMP DEFAULT NOW(),
                expires_at TIMESTAMP NOT NULL
            )
        """)
        conn.commit()
        print("✓ Tablas creadas exitosamente!")
    
    # Check for existing users
    cur.execute("SELECT COUNT(*) FROM app_users")
    user_count = cur.fetchone()[0]
    print(f"✓ Usuarios existentes: {user_count}")
    
    # List existing users
    cur.execute("SELECT email, role, is_active FROM app_users ORDER BY created_at DESC LIMIT 10")
    users = cur.fetchall()
    if users:
        print("\n📋 Usuarios actuales:")
        for u in users:
            status = "✅" if u[2] else "⛔"
            print(f"   {status} {u[0]} ({u[1]})")
    
    # Check for admins
    cur.execute("SELECT email FROM app_users WHERE role = 'admin'")
    admins = cur.fetchall()
    print(f"\n👑 Administradores: {len(admins)}")
    for a in admins:
        print(f"   {a[0]}")
    
    # Create admin user
    admin_email = "osvaldovegaoses@gmail.com"
    admin_password = "A51b91c5!"
    
    cur.execute("SELECT id, role FROM app_users WHERE email = %s", (admin_email,))
    existing = cur.fetchone()
    
    if existing:
        if existing[1] == 'admin':
            print(f"\n✓ {admin_email} ya es administrador")
        else:
            cur.execute("UPDATE app_users SET role = 'admin' WHERE id = %s", (existing[0],))
            conn.commit()
            print(f"\n✓ {admin_email} promovido a administrador")
    else:
        # Hash password
        if HAS_BCRYPT:
            password_hash = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt()).decode()
        else:
            # Fallback - usar el mismo método que auth_service si no hay bcrypt
            password_hash = f"$sha256${hashlib.sha256(admin_password.encode()).hexdigest()}"
            print("⚠️  Usando SHA256 (bcrypt no disponible)")
        
        user_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        
        cur.execute("""
            INSERT INTO app_users (id, email, password_hash, full_name, role, organization_id, is_active, created_at)
            VALUES (%s, %s, %s, %s, 'admin', %s, true, NOW())
        """, (user_id, admin_email, password_hash, "Osvaldo Admin", org_id))
        conn.commit()
        
        print(f"\n✓ Administrador creado:")
        print(f"   Email: {admin_email}")
        print(f"   User ID: {user_id}")
        print(f"   Org ID: {org_id}")
    
    # Final count
    cur.execute("SELECT COUNT(*) FROM app_users")
    final_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM app_users WHERE role = 'admin'")
    admin_count = cur.fetchone()[0]
    
    print(f"\n✅ RESUMEN:")
    print(f"   Total usuarios: {final_count}")
    print(f"   Administradores: {admin_count}")
    
    cur.close()
    conn.close()
    print("\n" + "="*60)

if __name__ == "__main__":
    main()
