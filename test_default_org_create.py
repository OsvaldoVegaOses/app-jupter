#!/usr/bin/env python3
"""Test creating a project with default_org to debug the 500 error."""
from app.clients import build_service_clients
from app.settings import load_settings
from app.project_state import create_project
import uuid
import traceback

settings = load_settings()
clients = build_service_clients(settings)
pg = clients.postgres

# Generate unique test name
test_name = f"Test API {uuid.uuid4().hex[:6]}"
org_id = "default_org"
user_id = "api-key-user"

print(f"Testing with project name: {test_name}")
print(f"Org ID: {org_id}")
print(f"User ID: {user_id}")

try:
    result = create_project(pg, test_name, "Test description", org_id=org_id, owner_id=user_id)
    print(f"\n✅ Project created successfully!")
    print(f"   ID: {result['id']}")
    print(f"   Name: {result['name']}")
    print(f"   Org: {result.get('org_id')}")
    
    # Cleanup
    cur = pg.cursor()
    cur.execute("DELETE FROM proyectos WHERE id = %s", (result['id'],))
    pg.commit()
    print(f"\n🧹 Cleaned up test project")
    
except Exception as e:
    print(f"\n❌ Error: {type(e).__name__}: {e}")
    traceback.print_exc()

clients.close()
