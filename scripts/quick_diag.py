"""Quick diagnostic to write Qdrant data to file."""
import sys
sys.path.insert(0, '.')
from qdrant_client import QdrantClient
from app.settings import load_settings
from collections import Counter

s = load_settings()
c = QdrantClient(url=s.qdrant.uri, api_key=s.qdrant.api_key)
col = s.qdrant.collection

# Get all points (paginated)
all_data = []
offset = None
while True:
    result = c.scroll(collection_name=col, limit=100, offset=offset, with_payload=['archivo', 'project_id'], with_vectors=False)
    points, offset = result
    if not points:
        break
    for p in points:
        payload = p.payload or {}
        all_data.append((payload.get('project_id'), payload.get('archivo')))
    if offset is None:
        break

# Write to file
with open('qdrant_diagnosis.txt', 'w', encoding='utf-8') as f:
    f.write(f'Coleccion: {col}\n')
    f.write(f'Total fragmentos: {len(all_data)}\n\n')
    
    # Count by project
    projects = Counter(d[0] for d in all_data)
    f.write('PROYECTOS:\n')
    for proj, cnt in projects.most_common():
        f.write(f'  {proj}: {cnt} fragmentos\n')
    
    f.write('\nARCHIVOS POR PROYECTO:\n')
    for proj in projects:
        f.write(f'\n=== Proyecto: {proj} ===\n')
        archivos = Counter(d[1] for d in all_data if d[0] == proj)
        for arch, cnt in archivos.most_common():
            f.write(f'  {arch}: {cnt} fragmentos\n')

print('Done. Check qdrant_diagnosis.txt')
