#!/usr/bin/env python3
"""Manual smoke-test: complete project creation flow.

Note: This is an integration script (needs real Postgres). It is guarded by
__main__ so pytest collection won't execute it.
"""

import uuid

from app.clients import build_service_clients
from app.project_state import create_project
from app.settings import load_settings


def main() -> int:
    settings = load_settings()
    clients = build_service_clients(settings)
    pg = clients.postgres

    # Generate unique test name
    test_name = f"Test Flow {uuid.uuid4().hex[:6]}"
    org_id = "6fc75e26-c0f4-4559-a2ef-10e508467661"
    user_id = "5c1fc162-2ee0-41ab-8d1d-b75d835f0d26"

    print(f"Testing with project name: {test_name}")
    print(f"Org ID: {org_id}")

    # Step 1: Create project
    try:
        result = create_project(pg, test_name, "Test description", org_id=org_id, owner_id=user_id)
        print("\nProject created successfully!")
        print(f"   ID: {result['id']}")
        print(f"   Name: {result['name']}")
        print(f"   Org: {result.get('org_id')}")
    except ValueError as e:
        print(f"\nCreation failed: {e}")

    # Step 2: Try to create again (should fail)
    print("\n--- Trying to create same project again ---")
    try:
        result2 = create_project(pg, test_name, "Another description", org_id=org_id, owner_id=user_id)
        print(f"Unexpected: Second creation succeeded: {result2}")
    except ValueError as e:
        print(f"Expected error: {e}")

    # Step 3: Try to create same name but DIFFERENT org
    print("\n--- Trying same name with different org ---")
    different_org = "test-org-12345"
    try:
        result3 = create_project(pg, test_name, "Different org", org_id=different_org, owner_id=user_id)
        print("Different org creation succeeded!")
        print(f"   ID: {result3['id']}")
        print(f"   Org: {result3.get('org_id')}")
    except ValueError as e:
        print(f"Different org failed: {e}")

    # Cleanup test projects (best-effort)
    try:
        slug = test_name.lower().replace(" ", "-")
        with pg.cursor() as cur:
            cur.execute("DELETE FROM proyectos WHERE id LIKE %s", (f"{slug}%",))
        pg.commit()
        print("\nCleaned up test projects")
    except Exception as e:
        try:
            pg.rollback()
        except Exception:
            pass
        print(f"\nCleanup failed: {e}")

    clients.close()
    print("\nTest complete!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
