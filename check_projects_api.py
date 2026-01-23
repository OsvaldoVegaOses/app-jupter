#!/usr/bin/env python3
"""Check projects via API."""
import requests

resp = requests.get('http://127.0.0.1:8000/api/projects', headers={'X-API-Key': 'dev-key'})
print(f'Status: {resp.status_code}')
if resp.status_code == 200:
    data = resp.json()
    print(f'Projects: {len(data.get("projects", []))}')
    for p in data.get('projects', []):
        print(f"  - {p['id']}: {p['name']} (org={p.get('org_id')})")
else:
    print(resp.text)
