#!/usr/bin/env python3
"""
Script para crear usuario administrador.

Uso:
    python scripts/create_admin.py --email admin@example.com --password "SecurePass123!"
    
O interactivo:
    python scripts/create_admin.py
"""

import argparse
import getpass
import sys
import os

# Agregar path del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.clients import build_service_clients
from app.settings import load_settings
from backend.auth_service import (
    RegisterRequest,
    hash_password,
    HAS_BCRYPT,
)
from app.postgres_block import (
    ensure_users_table,
    create_user,
    get_user_by_email,
    count_users,
)


def main():
    parser = argparse.ArgumentParser(description="Crear usuario administrador")
    parser.add_argument("--email", help="Email del administrador")
    parser.add_argument("--password", help="Password (si no se especifica, se pide interactivo)")
    parser.add_argument("--name", default="Administrador", help="Nombre completo")
    parser.add_argument("--org", default="default_org", help="ID de organización")
    args = parser.parse_args()
    
    print("=" * 50)
    print("CREAR USUARIO ADMINISTRADOR")
    print("=" * 50)
    
    # Verificar bcrypt
    if not HAS_BCRYPT:
        print("\n⚠️  ADVERTENCIA: bcrypt no está instalado.")
        print("   Se usará hash SHA256 (NO recomendado para producción)")
        print("   Instalar: pip install bcrypt\n")
    
    # Obtener email
    email = args.email
    if not email:
        email = input("Email del administrador: ").strip()
        if not email:
            print("❌ Error: Email requerido")
            sys.exit(1)
    
    # Validar formato email básico
    if "@" not in email or "." not in email:
        print(f"❌ Error: Email inválido: {email}")
        sys.exit(1)
    
    # Obtener password
    password = args.password
    if not password:
        password = getpass.getpass("Password: ")
        password_confirm = getpass.getpass("Confirmar password: ")
        if password != password_confirm:
            print("❌ Error: Los passwords no coinciden")
            sys.exit(1)
    
    # Validar password
    try:
        RegisterRequest(email=email, password=password)
    except ValueError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    
    # Conectar a BD
    print("\n📡 Conectando a PostgreSQL...")
    try:
        settings = load_settings()
        clients = build_service_clients(settings)
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        sys.exit(1)
    
    try:
        pg = clients.postgres
        
        # Crear tablas si no existen
        print("📦 Verificando tablas...")
        ensure_users_table(pg)
        
        # Verificar si ya existe
        existing = get_user_by_email(pg, email)
        if existing:
            print(f"⚠️  Usuario {email} ya existe (ID: {existing['id']})")
            sys.exit(0)
        
        # Hash del password
        print("🔐 Generando hash de password...")
        password_hash = hash_password(password)
        
        # Crear usuario admin
        print("👤 Creando usuario...")
        user = create_user(
            pg=pg,
            email=email,
            password_hash=password_hash,
            full_name=args.name,
            organization_id=args.org,
            role="admin",  # <-- ROL ADMIN
        )
        
        print("\n" + "=" * 50)
        print("✅ USUARIO ADMINISTRADOR CREADO")
        print("=" * 50)
        print(f"   ID: {user['id']}")
        print(f"   Email: {user['email']}")
        print(f"   Nombre: {user['full_name']}")
        print(f"   Rol: {user['role']}")
        print(f"   Organización: {user['organization_id']}")
        print(f"   Creado: {user['created_at']}")
        
        # Mostrar estadísticas
        total = count_users(pg)
        print(f"\n📊 Total de usuarios en sistema: {total}")
        
    finally:
        clients.close()


if __name__ == "__main__":
    main()
