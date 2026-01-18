#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostico de busqueda semantica por archivo en Qdrant.

Este script verifica:
1. Valores unicos del campo "archivo" en Qdrant
2. Cantidad de fragmentos por archivo
3. Prueba de filtrado por archivo especifico
4. Comparacion con PostgreSQL

Uso:
    python scripts/diagnose_qdrant_archivo.py --project "mi_proyecto"
    python scripts/diagnose_qdrant_archivo.py --project "mi_proyecto" --archivo "Entrevista X.docx"
"""

import argparse
import sys
import os
from pathlib import Path
from collections import Counter

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Agregar raiz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import psycopg2

from app.settings import load_settings


def get_qdrant_client(settings) -> QdrantClient:
    """Crea cliente Qdrant desde settings."""
    if settings.qdrant.api_key:
        return QdrantClient(
            url=settings.qdrant.uri,
            api_key=settings.qdrant.api_key,
        )
    return QdrantClient(url=settings.qdrant.uri)


def get_postgres_conn(settings):
    """Crea conexion PostgreSQL desde settings."""
    return psycopg2.connect(
        host=settings.postgres.host,
        port=settings.postgres.port,
        user=settings.postgres.username,
        password=settings.postgres.password,
        database=settings.postgres.database,
    )


def diagnose_qdrant_archivos(client: QdrantClient, collection: str, project_id: str):
    """Analiza los valores unicos del campo 'archivo' en Qdrant."""
    print("\n" + "=" * 60)
    print("[DIAGNOSTICO] Valores de 'archivo' en Qdrant")
    print("=" * 60)
    
    # Scroll para obtener todos los puntos del proyecto
    all_archivos = []
    offset = None
    total_points = 0
    
    project_filter = Filter(must=[
        FieldCondition(key="project_id", match=MatchValue(value=project_id))
    ])
    
    while True:
        result = client.scroll(
            collection_name=collection,
            scroll_filter=project_filter,
            limit=100,
            offset=offset,
            with_payload=["archivo", "project_id"],
            with_vectors=False,
        )
        
        points, offset = result
        if not points:
            break
            
        for point in points:
            total_points += 1
            archivo = point.payload.get("archivo") if point.payload else None
            all_archivos.append(archivo)
        
        if offset is None:
            break
    
    print(f"\n[INFO] Total de fragmentos en proyecto '{project_id}': {total_points}")
    
    # Contar por archivo
    archivo_counts = Counter(all_archivos)
    
    print(f"\n[ARCHIVOS] Archivos unicos encontrados: {len(archivo_counts)}")
    print("-" * 50)
    
    for archivo, count in archivo_counts.most_common():
        if archivo is None:
            print(f"  [WARNING] [NULL/None]: {count} fragmentos")
        elif archivo == "":
            print(f"  [WARNING] [VACIO '']: {count} fragmentos")
        else:
            print(f"  [OK] '{archivo}': {count} fragmentos")
    
    return archivo_counts


def test_filter_by_archivo(client: QdrantClient, collection: str, project_id: str, archivo: str):
    """Prueba el filtrado por archivo especifico."""
    print("\n" + "=" * 60)
    print(f"[PRUEBA DE FILTRO] archivo='{archivo}'")
    print("=" * 60)
    
    # Crear filtro combinado
    combined_filter = Filter(must=[
        FieldCondition(key="project_id", match=MatchValue(value=project_id)),
        FieldCondition(key="archivo", match=MatchValue(value=archivo)),
    ])
    
    result = client.scroll(
        collection_name=collection,
        scroll_filter=combined_filter,
        limit=10,
        with_payload=True,
        with_vectors=False,
    )
    
    points, _ = result
    
    if not points:
        print(f"\n[ERROR] No se encontraron fragmentos con archivo='{archivo}'")
        print("\n[POSIBLES CAUSAS]")
        print("   1. El nombre del archivo no coincide exactamente (mayusculas, tildes, espacios)")
        print("   2. El campo 'archivo' esta vacio o null en Qdrant")
        print("   3. Los fragmentos pertenecen a otro proyecto")
        return False
    
    print(f"\n[OK] Encontrados {len(points)} fragmentos (mostrando hasta 5):")
    print("-" * 50)
    
    for i, point in enumerate(points[:5], 1):
        payload = point.payload or {}
        fragmento = (payload.get("fragmento") or "")[:100]
        print(f"\n  [{i}] ID: {point.id}")
        print(f"      archivo: {payload.get('archivo')}")
        print(f"      par_idx: {payload.get('par_idx')}")
        print(f"      texto: {fragmento}...")
    
    return True


def compare_with_postgres(pg_conn, project_id: str):
    """Compara con los archivos en PostgreSQL."""
    print("\n" + "=" * 60)
    print("[COMPARACION] Archivos en PostgreSQL")
    print("=" * 60)
    
    with pg_conn.cursor() as cur:
        # Fragmentos
        cur.execute("""
            SELECT archivo, COUNT(*) as total
            FROM fragmentos
            WHERE project_id = %s
            GROUP BY archivo
            ORDER BY total DESC
        """, (project_id,))
        rows = cur.fetchall()
    
    if not rows:
        print(f"\n[WARNING] No hay fragmentos en PostgreSQL para proyecto '{project_id}'")
        return
    
    print(f"\n[ARCHIVOS] Archivos en PostgreSQL ({len(rows)} unicos):")
    print("-" * 50)
    for archivo, count in rows:
        print(f"  [OK] '{archivo}': {count} fragmentos")


def simulate_suggest_filter(client: QdrantClient, collection: str, project_id: str, fragment_id: str, archivo_filter: str):
    """Simula exactamente lo que hace suggest_similar_fragments."""
    print("\n" + "=" * 60)
    print("[SIMULACION] suggest_similar_fragments")
    print("=" * 60)
    
    # Primero, obtener el fragmento semilla
    try:
        points = client.retrieve(
            collection_name=collection,
            ids=[fragment_id],
            with_payload=True,
            with_vectors=True,
        )
    except Exception as e:
        print(f"\n[ERROR] Error obteniendo fragmento semilla: {e}")
        return
    
    if not points:
        print(f"\n[ERROR] Fragmento semilla '{fragment_id}' no encontrado en Qdrant")
        return
    
    seed_point = points[0]
    seed_archivo = seed_point.payload.get("archivo") if seed_point.payload else None
    
    print(f"\n[FRAGMENTO SEMILLA]")
    print(f"   ID: {fragment_id}")
    print(f"   archivo (en Qdrant): '{seed_archivo}'")
    print(f"   Filtro solicitado: '{archivo_filter}'")
    
    if seed_archivo != archivo_filter:
        print(f"\n[DISCREPANCIA] El fragmento semilla pertenece a '{seed_archivo}'")
        print(f"   pero el filtro busca en '{archivo_filter}'")
    
    # Simular busqueda con filtro
    vector = seed_point.vector
    
    combined_filter = Filter(
        must=[
            FieldCondition(key="project_id", match=MatchValue(value=project_id)),
            FieldCondition(key="archivo", match=MatchValue(value=archivo_filter)),
        ],
        must_not=[
            FieldCondition(key="speaker", match=MatchValue(value="interviewer")),
        ]
    )
    
    results = client.search(
        collection_name=collection,
        query_vector=vector,
        limit=5,
        query_filter=combined_filter,
        with_payload=True,
    )
    
    print(f"\n[RESULTADOS] Busqueda (top 5):")
    print("-" * 50)
    
    if not results:
        print("   [ERROR] Sin resultados. El filtro no encontro fragmentos.")
    else:
        for i, hit in enumerate(results, 1):
            payload = hit.payload or {}
            print(f"\n  [{i}] Score: {hit.score:.4f}")
            print(f"      ID: {hit.id}")
            print(f"      archivo: {payload.get('archivo')}")
            fragmento = (payload.get("fragmento") or "")[:80]
            print(f"      texto: {fragmento}...")


def main():
    parser = argparse.ArgumentParser(description="Diagnostico de busqueda por archivo en Qdrant")
    parser.add_argument("--project", required=True, help="ID del proyecto")
    parser.add_argument("--archivo", help="Archivo especifico a probar")
    parser.add_argument("--fragment-id", help="ID de fragmento semilla para simular busqueda")
    args = parser.parse_args()
    
    settings = load_settings()
    
    print("\n[CONFIG]")
    print(f"   Qdrant URL: {settings.qdrant.uri}")
    print(f"   Coleccion: {settings.qdrant.collection}")
    print(f"   Proyecto: {args.project}")
    
    # Conectar a Qdrant
    qdrant = get_qdrant_client(settings)
    
    # Diagnostico principal
    archivo_counts = diagnose_qdrant_archivos(qdrant, settings.qdrant.collection, args.project)
    
    # Comparar con PostgreSQL
    try:
        pg_conn = get_postgres_conn(settings)
        compare_with_postgres(pg_conn, args.project)
        pg_conn.close()
    except Exception as e:
        print(f"\n[WARNING] No se pudo conectar a PostgreSQL: {e}")
    
    # Probar filtro especifico
    if args.archivo:
        test_filter_by_archivo(qdrant, settings.qdrant.collection, args.project, args.archivo)
        
        # Simular busqueda si se proporciona fragmento
        if args.fragment_id:
            simulate_suggest_filter(
                qdrant, 
                settings.qdrant.collection, 
                args.project, 
                args.fragment_id, 
                args.archivo
            )
    
    print("\n" + "=" * 60)
    print("[OK] Diagnostico completado")
    print("=" * 60)
    
    # Resumen de problemas detectados
    null_count = archivo_counts.get(None, 0) + archivo_counts.get("", 0)
    if null_count > 0:
        print(f"\n[ADVERTENCIA] {null_count} fragmentos tienen 'archivo' vacio o null")
        print("   Esto puede causar que no aparezcan en busquedas filtradas.")
        print("   Solucion: Re-ingestar las entrevistas afectadas.")


if __name__ == "__main__":
    main()
