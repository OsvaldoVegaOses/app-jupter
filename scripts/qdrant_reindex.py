"""
qdrant_reindex.py
-----------------
Simple helper to re-upload points from a JSON export into Qdrant while adding
`project_id` into the payload. Useful when you changed payload schema and need
to ensure `project_id` is present for every point.

Usage:
  pip install qdrant-client
  QDRANT_URL and QDRANT_API_KEY environment variables must be set (if needed)

  python scripts/qdrant_reindex.py --collection my_collection --input data/qdrant_data/vectors_124.json --project default

Note: For very large files, consider streaming or using batch uploads.
"""
import argparse
import json
import os
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct


def load_points_from_file(path, project_id):
    """Yield PointStruct objects with project_id added to payload."""
    with open(path, 'r', encoding='utf-8') as f:
        # expecting a JSON array of {"id":..., "vector": [...], "payload": {...} }
        data = json.load(f)
        for item in data:
            payload = item.get('payload') or {}
            if 'project_id' not in payload:
                payload['project_id'] = project_id
            yield PointStruct(id=item['id'], vector=item['vector'], payload=payload)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--collection', required=True)
    parser.add_argument('--input', required=True)
    parser.add_argument('--project', default='default')
    args = parser.parse_args()

    url = os.environ.get('QDRANT_URL', 'http://localhost:6333')
    api_key = os.environ.get('QDRANT_API_KEY')

    client = QdrantClient(url=url, api_key=api_key)

    # Ensure collection exists — if not, create with default config
    # NOTE: adapt vector size and distance metric to your setup.
    try:
        col_info = client.get_collection(args.collection)
        print('Collection exists:', args.collection)
    except Exception:
        print('Collection not found — creating collection', args.collection)
        # Attempt to infer vector size from first point
        with open(args.input, 'r', encoding='utf-8') as fh:
            sample = json.load(fh)
            if not sample:
                raise RuntimeError('Input file empty')
            vlen = len(sample[0]['vector'])
        client.recreate_collection(collection_name=args.collection, vectors_config={'size': vlen, 'distance': 'Cosine'})

    batch = []
    batch_size = 256
    count = 0
    for point in load_points_from_file(args.input, args.project):
        batch.append(point)
        if len(batch) >= batch_size:
            client.upsert(collection_name=args.collection, points=batch)
            count += len(batch)
            print('Upserted', count, 'points')
            batch = []
    if batch:
        client.upsert(collection_name=args.collection, points=batch)
        count += len(batch)
        print('Upserted', count, 'points (final)')


if __name__ == '__main__':
    main()
