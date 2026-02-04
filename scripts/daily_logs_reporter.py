#!/usr/bin/env python3
"""
Daily Logs Reporter - Azure Log Analytics (KQL) -> Markdown.

Requires env vars:
- LOG_WORKSPACE_ID
- CONTAINER_APP_NAME (default: axial-api)
- REPORT_WINDOW_HOURS (default: 24)
- REPORT_OUT_DIR (default: reports/daily)

Uses queries/*.kql files with {{APP_NAME}} placeholder.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from reporter.triage import triage_from_top

from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus

WORKSPACE_ID = os.environ.get("LOG_WORKSPACE_ID")
APP_NAME = os.environ.get("CONTAINER_APP_NAME", "axial-api")
WINDOW_HOURS = int(os.environ.get("REPORT_WINDOW_HOURS", "24"))
OUT_DIR = Path(os.environ.get("REPORT_OUT_DIR", "reports/daily"))
QUERIES_DIR = Path(os.environ.get("REPORT_QUERIES_DIR", "queries"))


def load_kql(name: str) -> str:
    kql_path = QUERIES_DIR / f"{name}.kql"
    if not kql_path.exists():
        raise FileNotFoundError(f"Missing query: {kql_path}")
    return kql_path.read_text(encoding="utf-8").replace("{{APP_NAME}}", APP_NAME)


def run_query(client: LogsQueryClient, kql: str) -> List[Dict[str, Any]]:
    response = client.query_workspace(
        WORKSPACE_ID,
        kql,
        timespan=timedelta(hours=WINDOW_HOURS),
    )
    if response.status != LogsQueryStatus.SUCCESS:
        raise RuntimeError(response.error)
    if not response.tables:
        return []
    table = response.tables[0]
    cols = []
    for col in table.columns:
        if hasattr(col, "name"):
            cols.append(col.name)
        elif isinstance(col, dict) and "name" in col:
            cols.append(col["name"])
        else:
            cols.append(str(col))
    return [dict(zip(cols, row)) for row in table.rows]


def render_markdown(
    day: str,
    schema: List[Dict[str, Any]],
    top: List[Dict[str, Any]],
    validate_top: List[Dict[str, Any]],
) -> str:
    lines: List[str] = []
    lines.append(f"# Reporte diario Logs - {day}")
    lines.append("")
    lines.append(f"- App: {APP_NAME}")
    lines.append(f"- Ventana: ultimas {WINDOW_HOURS}h")
    lines.append("")

    if schema:
        s = schema[0]
        lines.append("## Schema Health")
        lines.append(f"- pct_json: {round(float(s.get('pct_json', 0)), 2)}%")
        lines.append(f"- pct_request_min: {round(float(s.get('pct_request_min', 0)), 2)}%")
        lines.append("")

    lines.append("## Top endpoints (p95)")
    lines.append("| Metodo | Route | Req | Slow% | Err% | p95(ms) | p99(ms) |")
    lines.append("|---|---|---:|---:|---:|---:|---:|")
    for row in top[:10]:
        lines.append(
            "| {method} | {route} | {req} | {slow} | {err} | {p95} | {p99} |".format(
                method=row.get("method", ""),
                route=row.get("route", ""),
                req=row.get("req", 0),
                slow=round(float(row.get("slow_rate", 0)), 2),
                err=round(float(row.get("error_rate", 0)), 2),
                p95=round(float(row.get("p95", 0)), 1),
                p99=round(float(row.get("p99", 0)), 1),
            )
        )
    lines.append("")

    lines.append("## Evidencia /validate (top request_id lentos)")
    lines.append("| TimeGenerated | dur(ms) | status | request_id | build | test_run |")
    lines.append("|---|---:|---:|---|---|---|")
    for row in validate_top[:10]:
        lines.append(
            "| {ts} | {dur} | {status} | {req_id} | {build} | {test_run} |".format(
                ts=row.get("TimeGenerated", ""),
                dur=round(float(row.get("dur", 0)), 1),
                status=row.get("status", 0),
                req_id=row.get("req_id", ""),
                build=row.get("build", ""),
                test_run=row.get("test_run", ""),
            )
        )

    triage = triage_from_top(top)
    if triage:
        lines.append("")
        lines.append("## Severidad e hipotesis")
        for item in triage[:5]:
            lines.append(f"- {item.severity} | {item.route} | {item.hypothesis}")
            for action in item.actions[:3]:
                lines.append(f"  - {action}")

    return "\n".join(lines) + "\n"


def main() -> int:
    if not WORKSPACE_ID:
        raise RuntimeError("LOG_WORKSPACE_ID is required")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    credential = DefaultAzureCredential()
    client = LogsQueryClient(credential)

    schema = run_query(client, load_kql("01_schema_health"))
    top = run_query(client, load_kql("02_top_endpoints"))
    validate_top = run_query(client, load_kql("04_validate_top_request_ids"))

    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    out_path = OUT_DIR / f"{day}.md"

    report = render_markdown(day, schema, top, validate_top)
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
