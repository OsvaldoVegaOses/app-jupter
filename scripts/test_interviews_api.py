"""Test the interviews API endpoint."""
import os
import sys
import logging
logging.disable(logging.CRITICAL)  # Suppress all logging
sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv
load_dotenv()

from app.settings import load_settings
from app.clients import build_service_clients
from app.coding import list_available_interviews

settings = load_settings()
clients = build_service_clients(settings)

project = sys.argv[1] if len(sys.argv) > 1 else "jd-008"

print(f"\n=== Testing list_available_interviews for '{project}' ===")
try:
    interviews = list_available_interviews(clients, project, limit=25)
    
    if interviews:
        for i in interviews:
            print(f"  {i['archivo']}: {i['fragmentos']} fragmentos")
        print(f"\n  Returned {len(interviews)} interviews")
    else:
        print("  WARNING: No interviews returned!")
except Exception as e:
    print(f"  ERROR: {e}")

clients.close()
