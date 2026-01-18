#!/usr/bin/env python3
"""
scripts/verify_ingestion.py

Usage:
  python scripts/verify_ingestion.py --project <PROJECT_ID> [options]

Options:
  --cleanup             Delete data for the project after (or before) verification.
  --force               Skip interactive confirmations for cleanup.
  --dry-run             Show what would be deleted without taking action.
  --tolerance-count N   Allowed difference in counts (default 0).
  --timeout SEC         Global timeout for consistency checks (default 60).
  --json-out PATH       Write JSON report to this file.

Description:
  Verifies data integrity across Neo4j, Qdrant, and Postgres for a given project.
  Includes safety guards, locks, and structured JSON output.
"""

import argparse

try:
    import fcntl
except ImportError:
    fcntl = None  # Windows compatibility

import json
import os
import sys
import time
import socket
import getpass
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from app.settings import load_settings
from app.clients import build_service_clients
from app.postgres_block import ensure_fragment_table
from qdrant_client.http import models

# Exit Codes
EXIT_SUCCESS = 0
EXIT_VERIFICATION_FAILED = 2
EXIT_SAFETY_VIOLATION = 3
EXIT_TIMEOUT = 4

LOCK_FILE = "e2e_test.lock"

def acquire_lock():
    """Acquires a file-based lock to prevent concurrent executions."""
    try:
        lock_fd = open(LOCK_FILE, 'w')
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_fd
    except IOError:
        print(f"[ERROR] Could not acquire lock {LOCK_FILE}. Is another test running?", file=sys.stderr)
        sys.exit(EXIT_SAFETY_VIOLATION)

def log(msg: str, level: str = "INFO"):
    """Logs human-readable messages to stderr."""
    timestamp = datetime.now().isoformat()
    print(f"[{timestamp}] [{level}] {msg}", file=sys.stderr)

class Verifier:
    def __init__(self, args):
        self.args = args
        self.settings = load_settings(args.env)
        self.clients = build_service_clients(self.settings)
        self.report = {
            "run_id": datetime.now().isoformat(),
            "project_id": args.project,
            "status": "pending",
            "counts": {},
            "mismatches": [],
            "actions": [],
            "audit": {
                "user": getpass.getuser(),
                "host": socket.gethostname(),
                "command": " ".join(sys.argv)
            }
        }

    def close(self):
        self.clients.close()

    def check_safety(self):
        """Ensures safety conditions for destructive actions."""
        if not self.args.cleanup:
            return

        is_test_env = "test" in (os.getenv("ENVIRONMENT") or "").lower() or "dev" in (os.getenv("ENVIRONMENT") or "").lower()
        val = (os.getenv("CLEANUP_CONFIRM") or "").strip().lower()
        confirm_env = val == "true"

        if not confirm_env:
            log(f"DEBUG: CLEANUP_CONFIRM='{os.getenv('CLEANUP_CONFIRM')}' (parsed as {val}) ENVIRONMENT='{os.getenv('ENVIRONMENT')}'", "WARN")
            if not is_test_env and not self.args.dry_run:
                log("SAFETY VIOLATION: CLEANUP_CONFIRM=true required in non-test env.", "ERROR")
                self.report["status"] = "safety_violation"
                sys.exit(EXIT_SAFETY_VIOLATION)
            
            if not self.args.force and not self.args.dry_run:
                # Interactive confirmation fallback
                response = input(f"WARNING: About to DELETE data for project '{self.args.project}'. Continue? [y/N] ")
                if response.lower() != 'y':
                    log("Cleanup aborted by user.", "WARNING")
                    sys.exit(EXIT_SAFETY_VIOLATION)

    def verify_neo4j(self) -> Dict[str, Any]:
        """Verifies Neo4j data."""
        query = """
        MATCH (f:Fragmento {project_id: $pid}) 
        RETURN count(f) as total, collect(f)[0..5] as samples
        """
        with self.clients.neo4j.session(database=self.settings.neo4j.database) as session:
            result_statement = session.run(query, pid=self.args.project)
            record = result_statement.single()
        valid_samples = 0
        for node in samples:
            props = dict(node)
            # Check project_id match (robust to missing key)
            if props.get("project_id") == self.args.project:
                valid_samples += 1
        
        log(f"Neo4j: Found {total} fragments, {valid_samples}/{len(samples)} valid samples.")
        return {"count": total, "valid_samples": valid_samples, "sample_size": len(samples)}

    def verify_qdrant(self) -> Dict[str, Any]:
        """Verifies Qdrant data with full scroll."""
        total = 0
        vectors_valid = 0
        payloads_valid = 0
        limit = 100
        offset = None
        
        scroll_filter = models.Filter(
            must=[models.FieldCondition(key="project_id", match=models.MatchValue(value=self.args.project))]
        )

        while True:
            points, offset = self.clients.qdrant.scroll(
                collection_name=self.settings.qdrant.collection,
                scroll_filter=scroll_filter,
                limit=limit,
                offset=offset,
                with_payload=True,
                with_vectors=True
            )
            
            for pt in points:
                total += 1
                # Vector validation (assuming standard dimension, e.g. 1536 for ada-002)
                # We relax exact dim check unless strict, but ensure vector exists
                if pt.vector: 
                    vectors_valid += 1
                
                # Payload validation
                pl = pt.payload or {}
                if pl.get("project_id") == self.args.project and pl.get("fragmento"):
                   payloads_valid += 1

            if offset is None:
                break
        
        log(f"Qdrant: Found {total} points, {vectors_valid} vectors, {payloads_valid} valid payloads.")
        return {"count": total, "vectors_valid": vectors_valid, "payloads_valid": payloads_valid}

    def verify_postgres(self) -> Dict[str, Any]:
        """Verifies Postgres data."""
        try:
            with self.clients.postgres.cursor() as cur:
                cur.execute(
                    "SELECT count(*), count(embedding) FROM entrevista_fragmentos WHERE project_id = %s", 
                    (self.args.project,)
                )
                row = cur.fetchone()
                total, vector_count = row if row else (0, 0)
            
            log(f"Postgres: Found {total} rows, {vector_count} with vectors.")
            return {"count": total, "vector_count": vector_count}
        except Exception as e:
            self.clients.postgres.rollback()
            log(f"Postgres verification check failed: {e}", "WARN")
            # Return 0 counts to indicate failure but allow retry/fallback
            return {"count": 0, "vector_count": 0}

    def run_cleanups(self):
        """Performs cleanup (delete) operations."""
        if self.args.dry_run:
            log("DRY-RUN: Would delete Neo4j nodes.", "INFO")
            log(f"DRY-RUN: Would delete Qdrant points for project {self.args.project}.", "INFO")
            log("DRY-RUN: Would delete Postgres rows.", "INFO")
            self.report["actions"].append("cleanup_dry_run")
            return

        log("Starting cleanup...", "INFO")
        
        # Neo4j
        with self.clients.neo4j.session(database=self.settings.neo4j.database) as session:
            session.run("MATCH (f:Fragmento {project_id: $pid}) DETACH DELETE f", pid=self.args.project)
            session.run("MATCH (e:Entrevista {project_id: $pid}) DETACH DELETE e", pid=self.args.project)
        
        # Qdrant
        try:
            self.clients.qdrant.delete(
                collection_name=self.settings.qdrant.collection,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[models.FieldCondition(key="project_id", match=models.MatchValue(value=self.args.project))]
                    )
                )
            )
        except Exception as e:
            log(f"Qdrant cleanup warning (collection missing?): {e}", "WARN")
        
        # Postgres
        ensure_fragment_table(self.clients.postgres)
        try:
            with self.clients.postgres.cursor() as cur:
                cur.execute("DELETE FROM entrevista_fragmentos WHERE project_id = %s", (self.args.project,))
                self.clients.postgres.commit()
        except Exception as e:
            self.clients.postgres.rollback()
            log(f"Postgres cleanup error: {e}", "ERROR")
            raise e
            
        log("Cleanup completed.", "INFO")
        self.report["actions"].append("cleanup_executed")

    def run_checks(self):
        """Runs the verification loop with retries."""
        start_time = time.time()
        attempt = 1
        
        while True:
            try:
                n4j = self.verify_neo4j()
                qdr = self.verify_qdrant()
                pg = self.verify_postgres()
                
                self.report["counts"] = {"neo4j": n4j["count"], "qdrant": qdr["count"], "postgres": pg["count"]}
                
                # Check consistency
                counts = [n4j["count"], qdr["count"], pg["count"]]
                max_count = max(counts)
                min_count = min(counts)
                
                if max_count == 0 and min_count == 0:
                     # If we expect data but found none, keep retrying if time permits (unless cleanup verified empty)
                     if not self.args.cleanup: # if checking ingestion
                         pass 
                
                if (max_count - min_count) <= self.args.tolerance_count:
                    # Semantic checks
                    if n4j["valid_samples"] == n4j["sample_size"] and qdr["vectors_valid"] == qdr["count"]:
                         log("Verification PASSED.", "INFO")
                         self.report["status"] = "success"
                         return
                
            except Exception as e:
                log(f"Verification error check attempt {attempt}: {e}", "WARN")

            elapsed = time.time() - start_time
            if elapsed > self.args.timeout:
                log("Verification TIMEOUT caused by inconsistency or missing data.", "ERROR")
                self.report["status"] = "failed"
                self.report["mismatches"].append(f"Counts mismatch or timeout: {self.report['counts']}")
                sys.exit(EXIT_TIMEOUT)
            
            wait = min(2 ** attempt, 10)
            log(f"Consistency check failed or incomplete. Retrying in {wait}s...", "INFO")
            time.sleep(wait)
            attempt += 1

def main():
    parser = argparse.ArgumentParser(description="Ingestion Verifier")
    parser.add_argument("--project", required=True, help="Project ID")
    parser.add_argument("--env", help="Path to .env", default=".env")
    parser.add_argument("--cleanup", action="store_true", help="Perform cleanup")
    parser.add_argument("--force", action="store_true", help="Force cleanup without interactive prompt")
    parser.add_argument("--dry-run", action="store_true", help="Simulate cleanup")
    parser.add_argument("--tolerance-count", type=int, default=0, help="Allowed count difference")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds")
    parser.add_argument("--json-out", help="Output JSON report file")
    
    args = parser.parse_args()
    
    # Platform specific lock (simple version for win/linux)
    if sys.platform != 'win32':
        lock_handle = acquire_lock()
    else:
        # Windows file locking is different, skipping for this POC or implement msvcrt
        log("File locking skipped on Windows (not fully implemented in script)", "WARN")

    verifier = Verifier(args)
    
    try:
        verifier.check_safety()
        
        if args.cleanup:
            verifier.run_cleanups()
        else:
            verifier.run_checks()
            
    except SystemExit as se:
        if args.json_out:
            with open(args.json_out, "w") as f:
                json.dump(verifier.report, f, indent=2)
        else:
            print(json.dumps(verifier.report, indent=2))
        raise se
    except Exception as e:
        log(f"Unhandled exception: {e}", "ERROR")
        import traceback
        traceback.print_exc(file=sys.stderr)
        verifier.report["status"] = "error"
        verifier.report["error"] = str(e)
        sys.exit(1)
    finally:
        verifier.close()
        if args.json_out:
            with open(args.json_out, "w") as f:
                json.dump(verifier.report, f, indent=2)
        else:
            print(json.dumps(verifier.report, indent=2))

if __name__ == "__main__":
    main()
