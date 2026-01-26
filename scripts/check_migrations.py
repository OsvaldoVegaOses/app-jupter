import os
from pathlib import Path

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
except Exception as e:
    print('Import error:', e)
    raise

settings = load_settings()
print('Loaded settings OK')

clients = None
try:
    clients = build_service_clients(settings)
    cur = clients.postgres.cursor()
    tables = ['axial_ai_analyses', 'link_predictions_neo4j_sync_status']
    for t in tables:
        try:
            cur.execute("SELECT to_regclass(%s)", (t,))
            r = cur.fetchone()
            print(f"Table {t}:", r[0] is not None)
        except Exception as e:
            print(f"Error checking {t}:", e)
    cur.close()
except Exception as e:
    print('Failed to build clients or query DB:', e)
finally:
    if clients:
        try:
            clients.close()
        except Exception:
            pass
