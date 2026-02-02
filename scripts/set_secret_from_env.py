import subprocess
import sys
from pathlib import Path

env_path = Path('.') / '.env'
if not env_path.exists():
    print('.env not found', file=sys.stderr)
    sys.exit(2)

val = None
for line in env_path.read_text(encoding='utf-8').splitlines():
    if line.strip().startswith('AZURE_STORAGE_CONNECTION_STRING'):
        parts = line.split('=', 1)
        if len(parts) == 2:
            val = parts[1].strip().strip('"')
        break

if not val:
    print('AZURE_STORAGE_CONNECTION_STRING not found in .env', file=sys.stderr)
    sys.exit(3)

print('Setting secret AZURE_STORAGE_CONNECTION_STRING (value hidden)')
res = subprocess.run(['gh', 'secret', 'set', 'AZURE_STORAGE_CONNECTION_STRING', '--repo', 'OsvaldoVegaOses/app-jupter', '--body', val])
if res.returncode != 0:
    print('gh secret set failed', file=sys.stderr)
    sys.exit(res.returncode)

print('Listing secrets:')
lst = subprocess.run(['gh', 'secret', 'list', '--repo', 'OsvaldoVegaOses/app-jupter'], capture_output=True, text=True)
print(lst.stdout)
