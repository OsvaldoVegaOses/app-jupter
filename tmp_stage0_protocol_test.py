import os, json, traceback
from app.settings import load_settings
from app.clients import build_service_clients

settings = load_settings(os.getenv('APP_ENV_FILE'))
clients = build_service_clients(settings)
try:
    pg = clients.postgres
    with pg.cursor() as cur:
        cur.execute('SELECT 1')
        print('pg ok:', cur.fetchone())
        cur.execute('SELECT COUNT(*) FROM stage0_protocols WHERE project_id=%s', ('default',))
        print('stage0_protocols count:', cur.fetchone())

        sql = """
        INSERT INTO stage0_protocols (project_id, version, title, content, status, created_by)
        VALUES (%s, %s, %s, %s::jsonb, %s, %s)
        ON CONFLICT (project_id, version) DO UPDATE SET
          title = EXCLUDED.title,
          content = EXCLUDED.content,
          status = COALESCE(EXCLUDED.status, stage0_protocols.status)
        RETURNING project_id, version, status, created_at
        """
        cur.execute(sql, ('default', 1, 'Dev protocolo (script)', json.dumps({'note':'script'}), 'draft', 'api-key-user'))
        row = cur.fetchone()
        pg.commit()
        print('inserted:', row)
except Exception:
    traceback.print_exc()
finally:
    clients.close()
