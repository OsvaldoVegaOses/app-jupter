from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
pat = re.compile(r"logical_path_to_blob_name\s*\(")

for p in root.rglob('*.py'):
    try:
        text = p.read_text(encoding='utf-8')
    except Exception:
        continue
    lines = text.splitlines()
    for i, line in enumerate(lines, start=1):
        if 'logical_path_to_blob_name' in line:
            # collect context up to next 6 lines
            ctx = '\n'.join(lines[i-1:i+6])
            if 'org_id=' not in ctx:
                print(p.relative_to(root), i)
                print(ctx)
                print('---')
