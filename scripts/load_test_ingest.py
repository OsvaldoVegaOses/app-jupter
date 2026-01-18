"""
Load test script for ingestion pipeline.

Usage:
    python scripts/load_test_ingest.py --input data/test_interviews --project loadtest
"""

import argparse
import time
import json
from pathlib import Path
from datetime import datetime
import requests


API_BASE = "http://localhost:8000"


def get_auth_headers() -> dict:
    """Get authentication headers."""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("API_KEY") or os.getenv("NEO4J_API_KEY", "")
    return {"X-API-Key": api_key}


def ingest_files(files: list[Path], project: str, batch_size: int = 10) -> dict:
    """Ingest a batch of files and return timing metrics."""
    results = {
        "total_files": len(files),
        "successful": 0,
        "failed": 0,
        "total_fragments": 0,
        "total_time_ms": 0,
        "avg_time_per_file_ms": 0,
        "errors": [],
    }
    
    headers = get_auth_headers()
    start_time = time.time()
    
    for file_path in files:
        try:
            file_start = time.time()
            
            payload = {
                "project": project,
                "inputs": [str(file_path)],
                "batch_size": batch_size,
            }
            
            response = requests.post(
                f"{API_BASE}/api/ingest",
                json=payload,
                headers=headers,
                timeout=120,
            )
            
            file_elapsed = (time.time() - file_start) * 1000
            
            if response.status_code == 200:
                data = response.json()
                results["successful"] += 1
                results["total_fragments"] += data.get("result", {}).get("fragments_total", 0)
            else:
                results["failed"] += 1
                results["errors"].append({
                    "file": file_path.name,
                    "status": response.status_code,
                    "error": response.text[:200],
                })
                
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "file": file_path.name,
                "error": str(e),
            })
    
    results["total_time_ms"] = (time.time() - start_time) * 1000
    if results["successful"] > 0:
        results["avg_time_per_file_ms"] = results["total_time_ms"] / results["successful"]
    
    return results


def create_project(project: str) -> bool:
    """Create project if it doesn't exist."""
    headers = get_auth_headers()
    response = requests.post(
        f"{API_BASE}/api/projects",
        json={"name": project, "description": f"Load test project: {project}"},
        headers=headers,
        timeout=30,
    )
    if response.status_code in (200, 201):
        print(f"Created project: {project}")
        return True
    elif response.status_code == 409 or "already exists" in response.text.lower():
        print(f"Project already exists: {project}")
        return True
    else:
        print(f"Warning: Could not create project ({response.status_code}): {response.text[:100]}")
        return True  # Continue anyway


def main():
    parser = argparse.ArgumentParser(description="Load test ingestion pipeline")
    parser.add_argument("--input", type=str, required=True, help="Directory with test files")
    parser.add_argument("--project", type=str, default="loadtest", help="Project ID")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of files")
    parser.add_argument("--batch-size", type=int, default=10, help="Qdrant batch size")
    
    args = parser.parse_args()
    
    input_dir = Path(args.input)
    if not input_dir.exists():
        print(f"Error: Input directory not found: {input_dir}")
        return
    
    files = sorted(input_dir.glob("*.docx"))
    if args.limit:
        files = files[:args.limit]
    
    if not files:
        print("No .docx files found in input directory")
        return
    
    print("=" * 60)
    print("LOAD TEST: INGESTION PIPELINE")
    print("=" * 60)
    print(f"Input directory: {input_dir}")
    print(f"Files to process: {len(files)}")
    print(f"Project: {args.project}")
    print(f"Batch size: {args.batch_size}")
    print("=" * 60)
    print()
    
    # Ensure project exists
    create_project(args.project)
    
    results = ingest_files(files, args.project, args.batch_size)
    
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Total files:      {results['total_files']}")
    print(f"Successful:       {results['successful']}")
    print(f"Failed:           {results['failed']}")
    print(f"Total fragments:  {results['total_fragments']}")
    print(f"Total time:       {results['total_time_ms']:.2f} ms")
    print(f"Avg per file:     {results['avg_time_per_file_ms']:.2f} ms")
    print(f"Throughput:       {results['successful'] / (results['total_time_ms'] / 1000):.2f} files/sec")
    
    if results["errors"]:
        print()
        print("ERRORS:")
        for err in results["errors"][:5]:
            print(f"  - {err}")
    
    # Save results
    report_path = Path(f"logs/loadtest_ingest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
