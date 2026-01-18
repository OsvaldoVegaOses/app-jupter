import json

with open('logs/app.jsonl', 'r', encoding='utf-8') as f:
    lines = f.readlines()

discovery = [json.loads(l) for l in lines if 'discovery' in l.lower()]

# Write to docs folder (not gitignored)
with open('docs/05-troubleshooting/discovery_session_logs.md', 'w', encoding='utf-8') as out:
    out.write("# Discovery Session Logs\n\n")
    out.write(f"**Total discovery logs:** {len(discovery)}\n\n")
    out.write(f"**Session date:** 2026-01-08\n\n")
    out.write("---\n\n")
    
    for i, d in enumerate(discovery[-20:]):
        ts = d.get('timestamp', '')[:19]
        path = d.get('path', '')
        event = d.get('event', '')
        status = d.get('status_code', '')
        
        out.write(f"## [{len(discovery)-20+i+1}] {ts}\n\n")
        out.write(f"- **Path:** `{path}`\n")
        out.write(f"- **Event:** `{event}`\n")
        out.write(f"- **Status:** {status}\n")
        
        # Show details
        extra_keys = []
        for k, v in d.items():
            if k not in ['timestamp', 'path', 'event', 'status_code', 'logger', 'level', 'method', 'request_id']:
                val = str(v)[:200]
                extra_keys.append((k, val))
        
        if extra_keys:
            out.write("\n**Details:**\n```\n")
            for k, v in extra_keys:
                out.write(f"{k}: {v}\n")
            out.write("```\n")
        out.write("\n---\n\n")

print("Written to docs/05-troubleshooting/discovery_session_logs.md")
