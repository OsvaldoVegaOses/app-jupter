import os, traceback
from app.settings import load_settings
from app.clients import build_service_clients
from app.postgres_block import ensure_project_members_table, log_project_action

settings = load_settings(os.getenv('APP_ENV_FILE'))
clients = build_service_clients(settings)
try:
    pg = clients.postgres
    ensure_project_members_table(pg)
    print('ensure_project_members_table: ok')
    log_project_action(pg, project='default', user_id='api-key-user', action='smoke', entity_type='test', entity_id='1', details={'a':1})
    print('log_project_action: ok')
except Exception:
    traceback.print_exc()
finally:
    clients.close()
