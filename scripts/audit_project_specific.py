#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.clients import build_service_clients
from app.settings import load_settings

settings = load_settings()
clients = build_service_clients(settings)

project_id = '64317059-08aa-4831-b1b7-ab83d357c08f'

print('='*80)
print('[AUDITORIA DETALLADA] Proyecto especifico')
print('='*80)
print(f'\nProyecto UUID: {project_id}')
print(f'Cuenta: osvaldovegaoses@gmail.com')

# Verificar si existe en proyectos
with clients.postgres.cursor() as cur:
    cur.execute('SELECT id, name, created_at FROM proyectos WHERE id = %s', (project_id,))
    row = cur.fetchone()
    if row:
        print(f'\nExiste en tabla proyectos: SI')
        print(f'  Nombre: {row[1]}')
        print(f'  Creado: {row[2]}')
    else:
        print(f'\nExiste en tabla proyectos: NO')

# Verificar datos en PostgreSQL
print('\n[PostgreSQL]')
with clients.postgres.cursor() as cur:
    cur.execute('SELECT COUNT(*) FROM entrevista_fragmentos WHERE project_id = %s', (project_id,))
    frags = cur.fetchone()[0]
    print(f'  Fragmentos: {frags}')
    
    cur.execute('SELECT COUNT(*) FROM analisis_codigos_abiertos WHERE project_id = %s', (project_id,))
    codes = cur.fetchone()[0]
    print(f'  Codigos abiertos: {codes}')
    
    # Otros análisis
    cur.execute('SELECT COUNT(*) FROM codigos_candidatos WHERE project_id = %s', (project_id,))
    cand_codes = cur.fetchone()[0]
    print(f'  Codigos candidatos: {cand_codes}')

# Verificar en Neo4j
print('\n[Neo4j]')
try:
    with clients.neo4j.session() as session:
        result = session.run(
            'MATCH (n {project_id: $pid}) RETURN labels(n)[0] as label, count(n) as cnt',
            pid=project_id
        )
        has_data = False
        for record in result:
            label = record.get('label')
            cnt = record.get('cnt')
            print(f'  {label}: {cnt}')
            has_data = True
        if not has_data:
            print('  (sin nodos)')
except Exception as e:
    print(f'  Error: {str(e)[:80]}')

# Verificar en Qdrant
print('\n[Qdrant]')
try:
    collections = clients.qdrant.get_collections()
    found = False
    for coll in collections.collections:
        if project_id in coll.name or 'default' in coll.name:
            info = clients.qdrant.get_collection(coll.name)
            print(f'  Coleccion: {coll.name}')
            print(f'    Puntos: {info.points_count}')
            found = True
    if not found:
        print('  (sin colecciones)')
except Exception as e:
    print(f'  Error: {str(e)[:80]}')

# Verificar Blob Storage
print('\n[Azure Blob Storage]')
try:
    from azure.storage.blob import BlobServiceClient
    blob_client = BlobServiceClient.from_connection_string(
        settings.azure_storage_connection_string
    )
    containers = list(blob_client.list_containers())
    container_names = [c.name for c in containers]
    
    if 'interviews' in container_names:
        container_client = blob_client.get_container_client('interviews')
        blobs = list(container_client.list_blobs())
        project_blobs = [b for b in blobs if project_id in b.name or 'default' in b.name]
        print(f'  Archivos encontrados: {len(project_blobs)}')
        if project_blobs:
            for blob in project_blobs[:5]:
                size_mb = blob.size / (1024*1024)
                print(f'    - {blob.name} ({size_mb:.2f} MB)')
    else:
        print('  Contenedor "interviews" no encontrado')
except ImportError:
    print('  Azure SDK no instalado')
except Exception as e:
    print(f'  Error: {str(e)[:80]}')

print('\n' + '='*80)
clients.close()
