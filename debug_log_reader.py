
import json
import sys

log_file = "logs/app.jsonl"

def check_logs():
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        print(f"Total lines: {len(lines)}")
        
        # Find all logs for the specific request_id
        target_id = "fa2d1060-6b8a-4130-86fa-5630b82d34b6"
        
        with open("debug_trace.txt", "w", encoding="utf-8") as out:
            for i, line in enumerate(lines):
                try:
                    entry = json.loads(line)
                    if entry.get("request_id") == target_id:
                        out.write(f"--- Line {i+1} ---\n")
                        out.write(json.dumps(entry, indent=2) + "\n")
                except json.JSONDecodeError:
                    pass
                    
        print("Done writing debug_trace.txt")
            
    except Exception as e:
        print(f"Error reading logs: {e}")

if __name__ == "__main__":
    check_logs()
