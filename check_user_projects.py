#!/usr/bin/env python3
"""Check what projects the user sees via the list function."""
from app.clients import build_service_clients
from app.settings import load_settings
from app.project_state import list_projects_for_user

settings = load_settings()
clients = build_service_clients(settings)
pg = clients.postgres

# Limpiar proyecto de test
cur = pg.cursor()
cur.execute('DELETE FROM proyectos WHERE id LIKE %s', ('test-flow-%',))
pg.commit()
print('Limpiados proyectos de test')

user_id = '5c1fc162-2ee0-41ab-8d1d-b75d835f0d26'
org_id = '6fc75e26-c0f4-4559-a2ef-10e508467661'

# Como admin
projects_admin = list_projects_for_user(pg, user_id=user_id, org_id=org_id, role='admin')
print(f'\nProyectos como admin: {len(projects_admin)}')
for p in projects_admin:
    print(f"  {p['id']}: {p['name']}")

cur.close()
clients.close()
