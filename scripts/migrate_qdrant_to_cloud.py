#!/usr/bin/env python3
"""
Migra datos de Qdrant Local (Docker) a Qdrant Cloud.

Uso: python scripts/migrate_qdrant_to_cloud.py
"""

import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

load_dotenv()

# Configuración
LOCAL_URI = "http://localhost:6333"
CLOUD_URI = os.environ.get("QDRANT_URI")
CLOUD_API_KEY = os.environ.get("QDRANT_API_KEY")
COLLECTION_NAME = "fragments"
BATCH_SIZE = 50
EMBED_DIMS = 3072

def main():
    print(f"=== Migración Qdrant Local → Cloud ===")
    print(f"Local: {LOCAL_URI}")
    print(f"Cloud: {CLOUD_URI[:50]}...")
    print(f"Colección: {COLLECTION_NAME}")
    print()

    # Conectar a ambos
    local = QdrantClient(url=LOCAL_URI)
    cloud = QdrantClient(url=CLOUD_URI, api_key=CLOUD_API_KEY)

    # Verificar que la colección local existe
    local_collections = [c.name for c in local.get_collections().collections]
    if COLLECTION_NAME not in local_collections:
        print(f"❌ Colección '{COLLECTION_NAME}' no existe en local")
        return

    # Obtener info de la colección local
    local_info = local.get_collection(COLLECTION_NAME)
    print(f"Puntos totales en local: {local_info.points_count}")
    
    if local_info.points_count == 0:
        print("❌ No hay puntos para migrar")
        return

    # Crear colección en cloud si no existe
    cloud_collections = [c.name for c in cloud.get_collections().collections]
    if COLLECTION_NAME not in cloud_collections:
        print(f"\n🔨 Creando colección '{COLLECTION_NAME}' en Cloud...")
        cloud.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBED_DIMS, distance=Distance.COSINE),
        )
        print("✅ Colección creada")
    else:
        print(f"ℹ️ Colección '{COLLECTION_NAME}' ya existe en Cloud")

    # Migrar datos en batches
    print(f"\n📦 Migrando datos...")
    offset = None
    total_migrated = 0

    while True:
        # Scroll por la colección local
        points, offset = local.scroll(
            collection_name=COLLECTION_NAME,
            limit=BATCH_SIZE,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )

        if not points:
            break

        # Convertir a PointStruct para compatibilidad
        points_to_upsert = []
        for p in points:
            point = PointStruct(
                id=p.id,
                vector=p.vector,
                payload=p.payload,
            )
            points_to_upsert.append(point)

        # Upsert en cloud
        cloud.upsert(
            collection_name=COLLECTION_NAME,
            points=points_to_upsert,
        )

        total_migrated += len(points_to_upsert)
        print(f"  Migrados: {total_migrated} puntos")

        if offset is None:
            break

    print(f"\n✅ Migración completada: {total_migrated} puntos migrados")

    # Verificar
    cloud_info = cloud.get_collection(COLLECTION_NAME)
    print(f"📊 Puntos en Cloud: {cloud_info.points_count}")

    # Crear índices en cloud
    print("\n🔧 Creando índices de payload...")
    for field in ["project_id", "archivo", "speaker", "area_tematica", "actor_principal"]:
        try:
            cloud.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema="keyword",
            )
            print(f"  ✅ Índice '{field}' creado")
        except Exception as e:
            msg = str(e).lower()
            if "already exists" in msg or "already has index" in msg:
                print(f"  ℹ️ Índice '{field}' ya existe")
            else:
                print(f"  ⚠️ Error creando índice '{field}': {e}")

    print("\n🎉 ¡Migración exitosa!")


if __name__ == "__main__":
    main()
