import time
import subprocess
import json
import sys

run_id = 21369911038
max_checks = 60
interval = 8

for i in range(max_checks):
    try:
        p = subprocess.run(["gh", "run", "view", str(run_id), "--json", "status,conclusion"], capture_output=True, text=True)
        if p.returncode != 0:
            print(f"[{i}] gh returned {p.returncode}, retrying...", flush=True)
        else:
            obj = json.loads(p.stdout)
            status = obj.get("status")
            conclusion = obj.get("conclusion")
            print(f"[{i}] status={status} conclusion={conclusion}", flush=True)
            if status == "completed":
                break
    except Exception as e:
        print(f"[{i}] exception: {e}", flush=True)
    time.sleep(interval)

# final summary
p = subprocess.run(["gh", "run", "view", str(run_id), "--json", "status,conclusion,createdAt,updatedAt,url"], capture_output=True, text=True)
if p.returncode == 0:
    obj = json.loads(p.stdout)
    print("FINAL:")
    print(json.dumps(obj, indent=2), flush=True)
    conclusion = obj.get("conclusion")
    if conclusion != "success":
        print("\n--- Fetching logs (truncated) ---\n", flush=True)
        # stream logs
        plog = subprocess.run(["gh", "run", "view", str(run_id), "--log"], capture_output=True, text=False)
        if plog.returncode == 0:
            # decode bytes with fallback to avoid encoding errors
            out = plog.stdout.decode('utf-8', errors='replace')
            lines = out.splitlines()
            for ln in lines[:2000]:
                print(ln)
        else:
            print(f"Could not fetch logs: {plog.returncode}", flush=True)
else:
    print(f"Could not fetch final run info: {p.returncode}", flush=True)
