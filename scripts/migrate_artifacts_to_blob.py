#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Migrate local artifacts (reports/notes/runner logs) to Azure Blob Storage.

This script is intended to help transition legacy local archives to the new
strict multi-tenant Blob layout used by the backend:
  org/<org_id>/projects/<project_id>/...

It uploads:
  - reports/<project_id>/**
  - reports/runner/<project_id>/**
  - notes/<project_id>/**
  - logs/runner_reports/<project_id>/**
  - logs/runner_checkpoints/<project_id>/**

By default it does NOT delete local files. Use --delete-local with --confirm.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterable, Iterator, Optional, Tuple


def _iter_files(base: Path) -> Iterator[Path]:
    if not base.exists():
        return
    for p in base.rglob("*"):
        if p.is_file():
            yield p


def _detect_logical_path_and_project(p: Path) -> Optional[Tuple[str, str]]:
    rel = p.as_posix().lstrip("./")
    parts = rel.split("/")
    if len(parts) < 2:
        return None

    # reports/<project_id>/...
    if parts[0] == "reports" and parts[1] != "runner":
        project_id = parts[1]
        return rel, project_id

    # reports/runner/<project_id>/...
    if parts[0] == "reports" and len(parts) >= 3 and parts[1] == "runner":
        project_id = parts[2]
        return rel, project_id

    # notes/<project_id>/...
    if parts[0] == "notes" and len(parts) >= 2:
        project_id = parts[1]
        return rel, project_id

    # logs/runner_reports/<project_id>/...
    if parts[0] == "logs" and len(parts) >= 4 and parts[1] == "runner_reports":
        project_id = parts[2]
        return rel, project_id

    # logs/runner_checkpoints/<project_id>/...
    if parts[0] == "logs" and len(parts) >= 4 and parts[1] == "runner_checkpoints":
        project_id = parts[2]
        return rel, project_id

    return None


def _content_type_for(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "text/markdown; charset=utf-8"
    if suffix == ".json":
        return "application/json"
    if suffix == ".csv":
        return "text/csv; charset=utf-8"
    return "application/octet-stream"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate local artifacts to Azure Blob Storage (reports container).")
    parser.add_argument("--org-id", default=os.getenv("API_KEY_ORG_ID") or os.getenv("ORG_ID") or "", help="Tenant org id.")
    parser.add_argument("--project", default=None, help="Optional project_id to limit migration (e.g., jd-007).")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without uploading.")
    parser.add_argument("--delete-local", action="store_true", help="Delete local files after successful upload.")
    parser.add_argument("--confirm", action="store_true", help="Required when using --delete-local.")
    args = parser.parse_args(argv)

    org_id = (args.org_id or "").strip()
    if not org_id:
        print("ERROR: --org-id is required (or set API_KEY_ORG_ID/ORG_ID).")
        return 2

    if args.delete_local and not args.confirm:
        print("ERROR: --delete-local requires --confirm.")
        return 2

    from app.blob_storage import CONTAINER_REPORTS, logical_path_to_blob_name, tenant_upload_bytes

    roots: list[Path] = [
        Path("reports"),
        Path("notes"),
        Path("logs") / "runner_reports",
        Path("logs") / "runner_checkpoints",
    ]

    total = 0
    uploaded = 0
    skipped = 0
    deleted = 0
    errors = 0

    for root in roots:
        for fp in _iter_files(root):
            detected = _detect_logical_path_and_project(fp)
            if not detected:
                continue
            logical_path, project_id = detected
            if args.project and project_id != args.project:
                continue

            total += 1
            try:
                blob_name = logical_path_to_blob_name(org_id=org_id, project_id=project_id, logical_path=logical_path)
            except Exception as exc:
                errors += 1
                print(f"[ERR] map failed: {logical_path} ({exc})")
                continue

            if args.dry_run:
                skipped += 1
                print(f"[DRY] {logical_path} -> {blob_name}")
                continue

            try:
                data = fp.read_bytes()
                # Tenant-aware upload; script requires --org-id so strict mode is appropriate
                tenant_upload_bytes(
                    org_id=org_id,
                    project_id=project_id,
                    container=CONTAINER_REPORTS,
                    logical_path=logical_path,
                    data=data,
                    content_type=_content_type_for(logical_path),
                    strict_tenant=True,
                )
                uploaded += 1
                print(f"[OK]  {logical_path} -> {blob_name} ({len(data)} bytes)")
            except Exception as exc:
                errors += 1
                print(f"[ERR] upload failed: {logical_path} ({exc})")
                continue

            if args.delete_local:
                try:
                    fp.unlink()
                    deleted += 1
                except Exception as exc:
                    errors += 1
                    print(f"[ERR] delete failed: {fp} ({exc})")

    print("")
    print("Done.")
    print(f"  total:   {total}")
    print(f"  uploaded:{uploaded}")
    print(f"  skipped: {skipped} (dry-run)")
    print(f"  deleted: {deleted}")
    print(f"  errors:  {errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

