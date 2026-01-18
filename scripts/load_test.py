#!/usr/bin/env python3
"""Simple load tester for the /neo4j/query or /neo4j/export endpoints.

Usage:
    python scripts/load_test.py --endpoint http://localhost:8000/neo4j/query \
        --api-key mykey --duration 30 --concurrency 4 --export csv

Results are printed as JSON to stdout.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from collections import Counter
from statistics import mean
from typing import Dict, List, Optional

import requests

DEFAULT_BODY = {
    "cypher": "MATCH (c:Categoria)-[r:REL]->(k:Codigo) RETURN c.nombre AS categoria, k.nombre AS codigo LIMIT 10",
    "formats": ["table"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a lightweight load test against the Neo4j API")
    parser.add_argument("--endpoint", required=True, help="Endpoint completo (p. ej. http://localhost:8000/neo4j/query)")
    parser.add_argument("--api-key", required=True, help="Valor para el header X-API-Key")
    parser.add_argument("--duration", type=int, default=30, help="Duración total de la prueba en segundos (default: 30)")
    parser.add_argument("--concurrency", type=int, default=4, help="Número de hilos concurrentes (default: 4)")
    parser.add_argument("--sleep", type=float, default=0.1, help="Pausa entre solicitudes por hilo (default: 0.1s)")
    parser.add_argument("--export", choices=["csv", "json"], help="Testear endpoint de exporte (usa /neo4j/export)")
    parser.add_argument("--body", type=str, help="JSON con el payload a enviar (por defecto usa consulta predefinida)")
    return parser.parse_args()


def load_worker(
    endpoint: str,
    headers: Dict[str, str],
    body: Dict[str, object],
    stop_time: float,
    sleep_time: float,
    stats: List[float],
    errors: Counter,
) -> None:
    session = requests.Session()
    while time.perf_counter() < stop_time:
        start = time.perf_counter()
        try:
            response = session.post(endpoint, headers=headers, json=body, timeout=30)
            duration = (time.perf_counter() - start) * 1000
            if response.ok:
                stats.append(duration)
            else:
                errors[f"HTTP_{response.status_code}"] += 1
        except requests.RequestException as exc:
            errors[type(exc).__name__] += 1
        time.sleep(sleep_time)


def main() -> None:
    args = parse_args()
    endpoint = args.endpoint.rstrip("/")
    body: Dict[str, object]
    if args.body:
        body = json.loads(args.body)
    else:
        body = dict(DEFAULT_BODY)
    if args.export:
        endpoint = f"{endpoint}/export" if not endpoint.endswith("/export") else endpoint
        body = {
            **body,
            "export_format": args.export,
        }

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": args.api_key,
    }

    stop_time = time.perf_counter() + max(args.duration, 1)
    stats: List[float] = []
    errors: Counter = Counter()
    threads: List[threading.Thread] = []

    for _ in range(max(args.concurrency, 1)):
        thread = threading.Thread(
            target=load_worker,
            args=(endpoint, headers, body, stop_time, max(args.sleep, 0), stats, errors),
            daemon=True,
        )
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

    total_requests = len(stats) + sum(errors.values())
    stats_sorted = sorted(stats)
    summary = {
        "endpoint": endpoint,
        "duration_seconds": args.duration,
        "concurrency": args.concurrency,
        "requests_total": total_requests,
        "requests_ok": len(stats),
        "requests_error": sum(errors.values()),
        "errors": errors,
    }
    if stats:
        summary.update(
            {
                "latency_avg_ms": mean(stats),
                "latency_p95_ms": stats_sorted[int(0.95 * (len(stats_sorted) - 1))],
                "latency_p99_ms": stats_sorted[int(0.99 * (len(stats_sorted) - 1))],
            }
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
