#!/usr/bin/env python3
"""
Script de prueba rápida para verificar los nuevos endpoints de AdminPanel.
Ejecutar después de reiniciar el backend.

Requisitos:
- Backend en http://localhost:8000
- Usuario admin autenticado (JWT token)
"""

import requests
import json
from typing import Optional, Any

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════

BASE_URL = "http://localhost:8000"
# Reemplazar con un JWT token válido
JWT_TOKEN = "tu_jwt_token_aqui"

headers = {
    "Authorization": f"Bearer {JWT_TOKEN}",
    "Content-Type": "application/json",
}


# ═══════════════════════════════════════════════════════════════════════════
# TEST FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def test_get_users():
    """Test: GET /api/admin/users"""
    print("\n📋 TEST 1: GET /api/admin/users")
    try:
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers=headers)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"✅ Total users: {data.get('total')}")
            for user in data.get("users", [])[:2]:
                print(f"  - {user['email']}: {user['role']}")
        else:
            print(f"❌ Error: {resp.text}")
    except Exception as e:
        print(f"❌ Exception: {e}")


def test_get_stats():
    """Test: GET /api/admin/stats"""
    print("\n📊 TEST 2: GET /api/admin/stats")
    try:
        resp = requests.get(f"{BASE_URL}/api/admin/stats", headers=headers)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"✅ Organization: {data.get('organization_id')}")
            print(f"  - Total users: {data.get('total_users')}")
            print(f"  - Total fragments: {data.get('total_fragments')}")
            print(f"  - Active sessions: {data.get('active_sessions')}")
        else:
            print(f"❌ Error: {resp.text}")
    except Exception as e:
        print(f"❌ Exception: {e}")


def test_find_duplicates(project: str = "default"):
    """Test: POST /api/admin/cleanup/duplicate-codes"""
    print(f"\n🔎 TEST 3: POST /api/admin/cleanup/duplicate-codes (project={project})")
    try:
        resp = requests.post(
            f"{BASE_URL}/api/admin/cleanup/duplicate-codes?project={project}&threshold=0.85",
            headers=headers,
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"✅ Analysis completed")
            print(f"  - Total codes: {data.get('total_codes')}")
            print(f"  - Duplicate groups: {data.get('groups_count')}")
            if data.get("duplicate_groups"):
                print(f"  - Sample groups:")
                for group in data.get("duplicate_groups", [])[:2]:
                    print(f"    {group}")
        else:
            print(f"❌ Error: {resp.text}")
    except Exception as e:
        print(f"❌ Exception: {e}")


def test_orphan_files(project: str = "default"):
    """Test: GET /api/admin/analysis/orphan-files"""
    print(f"\n📁 TEST 4: GET /api/admin/analysis/orphan-files (project={project})")
    try:
        resp = requests.get(
            f"{BASE_URL}/api/admin/analysis/orphan-files?project={project}",
            headers=headers,
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"✅ Analysis completed")
            print(f"  - Total files: {data.get('total_files')}")
            print(f"  - Orphans found: {data.get('orphans_count')}")
            if data.get("orphans"):
                print(f"  - Sample orphans:")
                for orphan in data.get("orphans", [])[:2]:
                    print(f"    {orphan['filename']}")
        else:
            print(f"❌ Error: {resp.text}")
    except Exception as e:
        print(f"❌ Exception: {e}")


def test_integrity_check(project: str = "default"):
    """Test: GET /api/admin/analysis/integrity"""
    print(f"\n✓ TEST 5: GET /api/admin/analysis/integrity (project={project})")
    try:
        resp = requests.get(
            f"{BASE_URL}/api/admin/analysis/integrity?project={project}",
            headers=headers,
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"✅ Integrity check completed")
            checks = data.get("checks", {})
            print(f"  - Total fragments: {checks.get('total_fragments')}")
            print(f"  - Fragments without codes: {checks.get('fragments_without_codes')}")
            print(f"  - Unique codes: {checks.get('unique_codes')}")
            print(f"  - Total code assignments: {checks.get('total_code_assignments')}")
        else:
            print(f"❌ Error: {resp.text}")
    except Exception as e:
        print(f"❌ Exception: {e}")


def test_cleanup_unconfirmed(project: str = "default"):
    """Test: POST /api/admin/cleanup/all-data (sin confirmación)"""
    print(f"\n🧹 TEST 6: POST /api/admin/cleanup/all-data (NO CONFIRM - project={project})")
    try:
        resp = requests.post(
            f"{BASE_URL}/api/admin/cleanup/all-data?project={project}",
            headers=headers,
            json={"confirm": False, "reason": "Testing without confirmation"},
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"✅ Request rejected (as expected)")
            print(f"  - Status: {data.get('status')}")
            print(f"  - Message: {data.get('message')}")
        else:
            print(f"❌ Unexpected error: {resp.text}")
    except Exception as e:
        print(f"❌ Exception: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 80)
    print("🧪 ADMIN PANEL ENDPOINTS - TEST SUITE")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print(f"Token: {JWT_TOKEN[:20]}..." if JWT_TOKEN != "tu_jwt_token_aqui" else "⚠️  Please set JWT_TOKEN")
    
    if JWT_TOKEN == "tu_jwt_token_aqui":
        print("\n❌ ERROR: JWT_TOKEN not configured. Edit this script and set your token.")
        exit(1)
    
    # Run tests
    test_get_users()
    test_get_stats()
    test_find_duplicates()
    test_orphan_files()
    test_integrity_check()
    test_cleanup_unconfirmed()
    
    print("\n" + "=" * 80)
    print("✅ TEST SUITE COMPLETED")
    print("=" * 80)
    print("\nNext steps:")
    print("1. Verify all tests passed with status 200")
    print("2. Check logs/app.jsonl for admin event logging")
    print("3. Test cleanup with confirm=true (CAREFUL - destructive!)")
    print("4. Test from UI: open AdminPanel and click buttons")
