#!/usr/bin/env python
"""Dry-run de auto-merge usando el backend local.

- Llama /api/codes/detect-duplicates (limit=N) para obtener pares.
- Construye pares source->target (target = código más corto).
- Llama /api/codes/candidates/auto-merge con dry_run=true.

No modifica datos de codigos_candidatos (solo calcula impacto).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import requests


def _read_env_key(env_path: Path, key: str) -> str | None:
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return None


def _get_api_key(repo_root: Path) -> str:
    # En este repo se documenta NEO4J_API_KEY como API key general.
    return (
        os.environ.get("NEO4J_API_KEY")
        or _read_env_key(repo_root / ".env", "NEO4J_API_KEY")
        or ""
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--threshold", type=float, default=0.80)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--env", default=".env")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    api_key = _get_api_key(repo_root)
    if not api_key:
        raise SystemExit(
            "No se encontró NEO4J_API_KEY en env/.env; se usa como X-API-Key."
        )

    headers = {"Content-Type": "application/json", "X-API-Key": api_key}

    print(f"1) Detectando duplicados en {args.project} (threshold={args.threshold}, limit={args.limit})...")
    detect_payload = {
        "project": args.project,
        "threshold": args.threshold,
        "limit": args.limit,
    }
    r = requests.post(
        f"{args.base}/api/codes/detect-duplicates",
        headers=headers,
        json=detect_payload,
        timeout=120,
    )
    print("detect status:", r.status_code)
    if r.status_code >= 400:
        print(r.text)
        return 1

    data: dict[str, Any] = r.json()
    duplicates = data.get("duplicates", [])
    print("duplicados devueltos:", len(duplicates))

    pairs: list[dict[str, str]] = []
    for d in duplicates:
        c1 = d.get("code1")
        c2 = d.get("code2")
        if not c1 or not c2:
            continue
        target = c1 if len(c1) <= len(c2) else c2
        source = c2 if target == c1 else c1
        if source.strip().lower() == target.strip().lower():
            continue
        pairs.append({"source_codigo": source, "target_codigo": target})

    print("pares para dry-run:", len(pairs))
    if pairs:
        print(json.dumps(pairs[:5], ensure_ascii=False, indent=2))

    print("\n2) Dry-run auto-merge (sin persistir cambios)...")
    auto_payload = {
        "project": args.project,
        "pairs": pairs,
        "dry_run": True,
        "memo": "dry-run: estimación de impacto de fusión (sin persistir)",
    }
    r2 = requests.post(
        f"{args.base}/api/codes/candidates/auto-merge",
        headers=headers,
        json=auto_payload,
        timeout=240,
    )
    print("auto-merge dry-run status:", r2.status_code)
    if r2.status_code >= 400:
        print(r2.text)
        return 1

    resp: dict[str, Any] = r2.json()
    print("total_merged (estimado):", resp.get("total_merged"))
    details = resp.get("details") or []
    for item in details[:10]:
        src = item.get("source")
        tgt = item.get("target")
        mc = item.get("merged_count")
        det = item.get("details") or {}
        wm = det.get("would_move")
        wd = det.get("would_dedupe")
        print(f"- {src} -> {tgt}: would_merge={mc} (move={wm}, dedupe={wd})")

    if len(details) > 10:
        print(f"... ({len(details) - 10} pares más)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
