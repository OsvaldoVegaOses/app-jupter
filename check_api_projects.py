#!/usr/bin/env python3
"""Check projects via API for different orgs."""
import requests

# Ver proyectos con API key (default_org)
resp = requests.get('http://127.0.0.1:8000/api/projects', headers={'X-API-Key': 'dev-key'})
print('Con API Key (default_org):')
if resp.status_code == 200:
    for p in resp.json().get('projects', []):
        print(f"  {p['id']}: {p['name']} (org={p.get('org_id')})")
else:
    print(f'  Error: {resp.status_code} - {resp.text}')
