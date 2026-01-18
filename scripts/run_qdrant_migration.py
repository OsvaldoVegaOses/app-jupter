"""
Ejecuta migraciones en Qdrant (creación de colección y configuración).
Verifica si la colección existe y la crea si es necesario.
"""
import os
import sys
from pathlib import Path
from qdrant_client import QdrantClient, models

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from app.settings import load_settings

def run_migration():
    settings = load_settings()
    
    print(f"Connecting to Qdrant at {settings.qdrant.uri}...")
    client = QdrantClient(url=settings.qdrant.uri, api_key=settings.qdrant.api_key)
    collection_name = settings.qdrant.collection
    
    print(f"Connecting to Qdrant collection '{collection_name}'...")
    
    # Check if collection exists
    try:
        client.get_collection(collection_name)
    except Exception as e:
        print(f"Collection '{collection_name}' not found or error: {e}")
        return

    # Scroll through all points
    offset = None
    limit = 100
    total_updated = 0
    
    print("Starting migration of Qdrant points...")
    
    while True:
        points, next_offset = client.scroll(
            collection_name=collection_name,
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False
        )
        
        points_to_update = []
        for point in points:
            payload = point.payload or {}
            if "project_id" not in payload:
                payload["project_id"] = "default"
                points_to_update.append(
                    {
                        "id": point.id,
                        "payload": payload
                    }
                )
        
        if points_to_update:
            # Update payload
            for p in points_to_update:
                client.set_payload(
                    collection_name=collection_name,
                    payload=p["payload"],
                    points=[p["id"]]
                )
            total_updated += len(points_to_update)
            print(f"Updated {len(points_to_update)} points in this batch.")
        
        if next_offset is None:
            break
        offset = next_offset

    print(f"Migration completed. Total points updated: {total_updated}")
    
    # Create payload index for project_id
    print("Creating payload index for 'project_id'...")
    client.create_payload_index(
        collection_name=collection_name,
        field_name="project_id",
        field_schema=models.PayloadSchemaType.KEYWORD
    )
    print("Index created.")

if __name__ == "__main__":
    run_migration()
