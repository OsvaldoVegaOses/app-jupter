#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Análisis completo del estado de almacenamiento en todas las bases de datos."""

import sys
import os
from pathlib import Path

# Force UTF-8 output
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.clients import build_service_clients
from app.settings import load_settings

settings = load_settings()
clients = build_service_clients(settings)

print('='*80)
print('[AUDITORIA] Estado global de almacenamiento')
print('='*80)

# Todos los proyectos
print('\n[PROYECTOS] Registrados:')
with clients.postgres.cursor() as cur:
    cur.execute('''
        SELECT id, name, created_at
        FROM proyectos
        ORDER BY created_at DESC
        LIMIT 10
    ''')
    projects = cur.fetchall()
    for row in projects:
        print(f'  • {row[1]}')
        print(f'    ID: {row[0]}')
        print(f'    Creado: {row[2]}')

# Fragmentos globales
print('\n[DATOS] Estadisticas globales:')
with clients.postgres.cursor() as cur:
    cur.execute('SELECT COUNT(*) FROM entrevista_fragmentos')
    total_frags = cur.fetchone()[0]
    print(f'  • Fragmentos en PostgreSQL: {total_frags}')
    
    cur.execute('SELECT COUNT(DISTINCT project_id) FROM entrevista_fragmentos')
    projects_with_data = cur.fetchone()[0]
    print(f'  • Proyectos con fragmentos: {projects_with_data}')
    
    cur.execute('SELECT COUNT(DISTINCT archivo) FROM entrevista_fragmentos')
    total_files = cur.fetchone()[0]
    print(f'  • Archivos ingestionados: {total_files}')
    
    cur.execute('SELECT COUNT(*) FROM analisis_codigos_abiertos')
    total_codes = cur.fetchone()[0]
    print(f'  • Códigos en PostgreSQL: {total_codes}')

# Proyectos con datos
print('\n[PROYECTOS] Con datos:')
with clients.postgres.cursor() as cur:
    cur.execute('''
        SELECT COALESCE(f.project_id, c.project_id) as proj_id,
               COUNT(DISTINCT f.archivo) as files,
               COUNT(DISTINCT f.id) as fragments,
               COUNT(DISTINCT c.codigo) as codes
        FROM (SELECT DISTINCT project_id, archivo, id FROM entrevista_fragmentos) f
        FULL OUTER JOIN (SELECT DISTINCT project_id, codigo FROM analisis_codigos_abiertos) c
          ON f.project_id = c.project_id
        GROUP BY proj_id
        ORDER BY COUNT(DISTINCT f.id) DESC
    ''')
    results = cur.fetchall()
    if results:
        for row in results:
            print(f'  • Proyecto: {row[0][:8]}...')
            print(f'    Archivos: {row[1]}, Fragmentos: {row[2]}, Códigos: {row[3]}')
    else:
        print('  (sin datos)')

# Estado en Neo4j
print('\n[NEO4J] Conteos globales:')
try:
    with clients.neo4j.session() as session:
        result = session.run('MATCH (n) RETURN labels(n)[0] as label, count(n) as cnt GROUP BY label')
        for record in result:
            label = record.get('label')
            cnt = record.get('cnt')
            print(f'  • {label}: {cnt}')
except Exception as e:
    print(f'  ⚠️  Error: {str(e)[:100]}')

# Qdrant
print('\n[QDRANT] Colecciones:')
try:
    collections = clients.qdrant.get_collections()
    if collections.collections:
        for coll in collections.collections:
            info = clients.qdrant.get_collection(coll.name)
            print(f'  • {coll.name}: {info.points_count} puntos')
    else:
        print('  (sin colecciones)')
except Exception as e:
    print(f'  ⚠️  Error: {str(e)[:100]}')

print('\n' + '='*80)
print('[EXITO] Auditoria completada')
print('='*80)

clients.close()
