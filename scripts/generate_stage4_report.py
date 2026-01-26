"""Generate the doctoral Stage 4 report (Codificación Axial) to a Markdown file.

Usage (PowerShell):
  ./.venv/Scripts/python.exe scripts/generate_stage4_report.py --project jd-009

Optional:
  ./.venv/Scripts/python.exe scripts/generate_stage4_report.py --project jd-009 --out reports/stage4_jd-009.md
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.clients import build_service_clients
from app.logging_utils import configure_logging
from app.settings import load_settings
from app.stage_reports import generate_stage4_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Stage 4 analytic report")
    parser.add_argument("--env", default=None, help="Path to .env (optional)")
    parser.add_argument("--project", default="default", help="Project ID (project_id)")
    parser.add_argument("--out", default=None, help="Output markdown path")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    configure_logging(args.log_level)
    settings = load_settings(args.env)
    clients = build_service_clients(settings)
    try:
        result = generate_stage4_report(
            clients,
            settings,
            project=args.project,
            org_id=os.getenv("API_KEY_ORG_ID") or None,
        )
    finally:
        clients.close()

    out_path = Path(args.out) if args.out else (REPO_ROOT / "reports" / f"stage4_{args.project}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result.get("content", ""), encoding="utf-8")

    stats = result.get("stats", {})
    print(f"Wrote: {out_path}")
    print(f"Stats: categories={stats.get('total_categories')} relationships={stats.get('total_relationships')} communities={stats.get('communities_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
