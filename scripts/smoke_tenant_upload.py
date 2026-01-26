import os
import json
from pathlib import Path

# Load .env minimally
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

API_ORG = os.environ.get('API_KEY_ORG_ID') or os.environ.get('ORG_ID')
if not API_ORG:
    print('Missing org id in .env (API_KEY_ORG_ID or ORG_ID)')
    raise SystemExit(2)

try:
    from app.blob_storage import tenant_upload_bytes, CONTAINER_REPORTS
except Exception as e:
    print('Import error:', e)
    raise

logical = f"reports/smoke_test_project/smoke_{os.urandom(4).hex()}.md"
data = b"# Smoke test\nThis is a smoke upload.\n"
try:
    res = tenant_upload_bytes(
        org_id=API_ORG,
        project_id='smoke_test_project',
        container=CONTAINER_REPORTS,
        logical_path=logical,
        data=data,
        content_type='text/markdown; charset=utf-8',
        strict_tenant=True,
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))
except Exception as exc:
    print('Upload failed:', exc)
    raise
