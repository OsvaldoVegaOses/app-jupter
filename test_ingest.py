from dotenv import load_dotenv
import os
load_dotenv()
import requests
api_key = os.getenv('NEO4J_API_KEY', '')
abs_path = os.path.abspath('data/test_interviews/Entrevista_Sintetica_001.docx')
print('Path:', abs_path)
print('Exists:', os.path.exists(abs_path))
r = requests.post(
    'http://localhost:8000/api/ingest',
    json={'project': 'loadtest', 'inputs': [abs_path]},
    headers={'X-API-Key': api_key},
    timeout=60
)
print('Status:', r.status_code)
print('Response:', r.text[:300])
