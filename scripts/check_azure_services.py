import os
from pathlib import Path
import json

# Load .env
env_path = Path(__file__).resolve().parents[1] / '.env'
if env_path.exists():
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            k, v = line.split('=', 1)
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k.strip(), v)

try:
    from app.settings import load_settings
    from app.clients import build_service_clients
    from app.blob_storage import check_blob_storage_health
except Exception as e:
    print('Import error:', e)
    raise

settings = load_settings()
print('Loaded settings OK')

# Blob health
try:
    bh = check_blob_storage_health()
    print('Blob health:', json.dumps(bh, indent=2, ensure_ascii=False))
except Exception as e:
    print('Blob health check failed:', e)

# Build clients (Postgres, Neo4j, Qdrant, AOAI cached)
clients = None
try:
    clients = build_service_clients(settings)
    print('Built service clients')

    # Postgres quick check
    try:
        with clients.postgres.cursor() as cur:
            cur.execute('SELECT 1')
            r = cur.fetchone()
            print('Postgres SELECT 1 ->', r)
    except Exception as e:
        print('Postgres check failed:', e)

    # Neo4j quick check
    try:
        s = clients.neo4j.session()
        r = s.run('RETURN 1 as v').single()
        print('Neo4j RETURN 1 ->', r['v'] if r else None)
        s.close()
    except Exception as e:
        print('Neo4j check failed:', e)

    # Qdrant quick check
    try:
        info = clients.qdrant.get_collections()
        print('Qdrant collections OK:', info)
    except Exception as e:
        print('Qdrant check failed:', e)

except Exception as e:
    print('Failed to build service clients:', e)
finally:
    if clients:
        try:
            clients.close()
        except Exception:
            pass
