"""List all projects in Qdrant."""
import sys
sys.path.insert(0, '.')
from qdrant_client import QdrantClient
from app.settings import load_settings
from collections import Counter

s = load_settings()
c = QdrantClient(url=s.qdrant.uri, api_key=s.qdrant.api_key)

# Get ALL points to find project_ids
all_data = []
offset = None
while True:
    result = c.scroll(s.qdrant.collection, limit=100, offset=offset, with_payload=['project_id', 'archivo'], with_vectors=False)
    points, offset = result
    if not points:
        break
    for p in points:
        payload = p.payload or {}
        all_data.append((payload.get('project_id'), payload.get('archivo')))
    if offset is None:
        break

# Count projects
projects = Counter(d[0] for d in all_data)

with open('projects_list.txt', 'w', encoding='utf-8') as f:
    f.write(f'Total fragmentos en Qdrant: {len(all_data)}\n\n')
    f.write('PROYECTOS:\n')
    for proj, cnt in projects.most_common():
        f.write(f'  {proj}: {cnt} fragmentos\n')
    
    f.write('\n\nARCHIVOS POR PROYECTO:\n')
    for proj in projects:
        f.write(f'\n=== {proj} ===\n')
        archivos = Counter(d[1] for d in all_data if d[0] == proj)
        for arch, cnt in archivos.most_common():
            f.write(f'  {arch}: {cnt}\n')

print('Listo! Ver projects_list.txt')
