import os
import traceback
from app.settings import load_settings
from app.clients import build_service_clients

# Force full traceback
try:
    settings = load_settings()
    print('Settings OK')
    clients = build_service_clients(settings)
    print('Clients OK')
    clients.close()
    print('SUCCESS')
except UnicodeDecodeError as e:
    print('UnicodeDecodeError:', e)
    traceback.print_exc()
except Exception as e:
    print(f'Error: {type(e).__name__}: {e}')
    traceback.print_exc()
