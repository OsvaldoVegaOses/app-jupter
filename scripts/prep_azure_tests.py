"""
Script de preparación para pruebas de producción Azure.
Ejecuta: python scripts/prep_azure_tests.py
"""
import os
import sys
import shutil
import hashlib
import uuid
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import psycopg2

def get_connection():
    return psycopg2.connect(
        host=os.getenv("PGHOST"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        dbname=os.getenv("PGDATABASE"),
        sslmode=os.getenv("PGSSLMODE", "require")
    )

def list_users_and_projects():
    """Lista usuarios y proyectos activos."""
    print("\n" + "="*60)
    print("📋 USUARIOS REGISTRADOS")
    print("="*60)
    
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT id, email, role, is_active, organization_id, created_at, last_login
            FROM app_users 
            ORDER BY created_at DESC
        """)
        users = cur.fetchall()
        
        if not users:
            print("⚠️  No hay usuarios registrados.")
        else:
            for u in users:
                status = "✅ Activo" if u[3] else "⛔ Inactivo"
                print(f"\n  ID: {u[0][:8]}...")
                print(f"  📧 Email: {u[1]}")
                print(f"  🔑 Rol: {u[2]}")
                print(f"  {status}")
                print(f"  🏢 Org: {u[4]}")
                print(f"  📅 Creado: {u[5]}")
                print(f"  🕐 Último login: {u[6] or 'Nunca'}")
        
        print("\n" + "="*60)
        print("📁 PROYECTOS EN BASE DE DATOS")
        print("="*60)
        
        cur.execute("""
            SELECT DISTINCT project_id, COUNT(*) as fragment_count
            FROM entrevista_fragmentos
            GROUP BY project_id
        """)
        projects = cur.fetchall()
        
        if not projects:
            print("⚠️  No hay proyectos con fragmentos.")
        else:
            for p in projects:
                print(f"\n  📂 Proyecto: {p[0]}")
                print(f"     Fragmentos: {p[1]}")
        
        print(f"\n  Total proyectos: {len(projects)}")
        print(f"  Total usuarios: {len(users)}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        cur.close()
        conn.close()

def clear_logs():
    """Limpia los archivos de log para nueva serie de pruebas."""
    print("\n" + "="*60)
    print("🧹 LIMPIANDO LOGS")
    print("="*60)
    
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    
    if not os.path.exists(logs_dir):
        print("⚠️  Directorio logs/ no existe.")
        return
    
    files_removed = 0
    for f in os.listdir(logs_dir):
        fpath = os.path.join(logs_dir, f)
        if os.path.isfile(fpath):
            os.remove(fpath)
            print(f"  🗑️  Eliminado: {f}")
            files_removed += 1
    
    print(f"\n  ✅ {files_removed} archivos de log eliminados.")

def check_admin_system():
    """Verifica el estado del sistema de administración."""
    print("\n" + "="*60)
    print("🔧 ESTADO DEL SISTEMA DE ADMINISTRACIÓN")
    print("="*60)
    
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Check for admins
        cur.execute("""
            SELECT id, email, organization_id, created_at
            FROM app_users 
            WHERE role = 'admin'
            ORDER BY created_at
        """)
        admins = cur.fetchall()
        
        print("\n  📊 Endpoints disponibles:")
        print("     • GET  /api/admin/users - Lista usuarios")
        print("     • PATCH /api/admin/users/{id} - Actualiza rol/estado")
        print("     • DELETE /api/admin/users/{id} - Elimina usuario")
        print("     • GET  /api/admin/stats - Estadísticas de org")
        
        print(f"\n  👑 Administradores actuales: {len(admins)}")
        for a in admins:
            print(f"     • {a[1]} (desde: {a[3]})")
        
        if not admins:
            print("     ⚠️  No hay administradores configurados.")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        cur.close()
        conn.close()

def create_admin_user(email: str, password: str):
    """Crea un usuario administrador."""
    print("\n" + "="*60)
    print("👤 CREANDO USUARIO ADMINISTRADOR")
    print("="*60)
    
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Check if user exists
        cur.execute("SELECT id, role FROM app_users WHERE email = %s", (email,))
        existing = cur.fetchone()
        
        if existing:
            if existing[1] == 'admin':
                print(f"  ℹ️  Usuario {email} ya es admin.")
                return
            else:
                # Promote to admin
                cur.execute(
                    "UPDATE app_users SET role = 'admin' WHERE id = %s",
                    (existing[0],)
                )
                conn.commit()
                print(f"  ✅ Usuario {email} promovido a admin.")
                return
        
        # Create new user
        user_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        
        # Hash password (using SHA-256 for simplicity - in prod use bcrypt)
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        cur.execute("""
            INSERT INTO app_users (id, email, password_hash, role, organization_id, is_active, created_at)
            VALUES (%s, %s, %s, 'admin', %s, true, NOW())
        """, (user_id, email, password_hash, org_id))
        
        conn.commit()
        print(f"  ✅ Usuario admin creado:")
        print(f"     Email: {email}")
        print(f"     User ID: {user_id}")
        print(f"     Org ID: {org_id}")
        print(f"\n  ⚠️  NOTA: Este script usa SHA-256 para el hash.")
        print(f"     Si el backend usa bcrypt, debes registrar vía /api/auth/register")
        print(f"     y luego promover a admin con este script.")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    print("\n🚀 PREPARACIÓN AMBIENTE PRUEBAS AZURE")
    print("="*60)
    print(f"Fecha: {datetime.now().isoformat()}")
    print(f"Host: {os.getenv('PGHOST')}")
    
    # 1. List users and projects
    list_users_and_projects()
    
    # 2. Check admin system
    check_admin_system()
    
    # 3. Clear logs
    clear_logs()
    
    # 4. Create admin (uncomment to execute)
    # create_admin_user("osvaldovegaoses@gmail.com", "A51b91c5!")
    
    print("\n" + "="*60)
    print("✅ SCRIPT COMPLETADO")
    print("="*60 + "\n")
