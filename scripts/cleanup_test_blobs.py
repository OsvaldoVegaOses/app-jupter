import os
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in os.sys.path:
    os.sys.path.insert(0, str(repo_root))

def load_env_if_missing():
    if not os.environ.get("AZURE_STORAGE_CONNECTION_STRING"):
        env_path = repo_root / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("AZURE_STORAGE_CONNECTION_STRING"):
                    _, val = line.split("=", 1)
                    os.environ["AZURE_STORAGE_CONNECTION_STRING"] = val.strip().strip('"').strip("'")
                    break

def main():
    load_env_if_missing()
    try:
        import app.blob_storage as blob_storage
    except Exception as e:
        print('Could not import blob_storage:', e)
        raise

    tenant_prefix = 'org/local-org/projects/local-project'
    containers = [blob_storage.CONTAINER_AUDIO, blob_storage.CONTAINER_INTERVIEWS]

    print('Listing blobs before deletion:')
    for c in containers:
        print(f'Container: {c}')
        items = blob_storage.list_files_with_meta(container=c, prefix=tenant_prefix)
        if not items:
            print('  (no items)')
        for it in items:
            print('  -', it.get('name'))

    confirm = input('Delete these blobs? (y/N): ').strip().lower()
    if confirm != 'y':
        print('Aborting deletion')
        return

    for c in containers:
        print('Deleting prefix in', c)
        res = blob_storage.delete_prefix(container=c, prefix=tenant_prefix, limit=5000)
        print('  result:', res)

    print('\nListing blobs after deletion:')
    for c in containers:
        print(f'Container: {c}')
        items = blob_storage.list_files_with_meta(container=c, prefix=tenant_prefix)
        if not items:
            print('  (no items)')
        for it in items:
            print('  -', it.get('name'))

if __name__ == '__main__':
    main()
