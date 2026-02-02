#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""Verifica conectividad y configuración de servicios externos (AOAI/Qdrant/PG/Neo4j)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def _ensure_tempdir() -> None:
    env_temp = os.getenv("TEMP") or os.getenv("TMP")
    if env_temp and Path(env_temp).exists():
        return

    candidates: list[Path] = []
    local_app = os.getenv("LOCALAPPDATA")
    if local_app:
        candidates.append(Path(local_app) / "Temp")
    user_profile = os.getenv("USERPROFILE")
    if user_profile:
        candidates.append(Path(user_profile) / "Temp")

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            os.environ["TEMP"] = str(candidate)
            os.environ["TMP"] = str(candidate)
            return
        except OSError:
            continue

_ensure_tempdir()

from app.clients import build_service_clients  # noqa: E402
from app.qdrant_block import ensure_payload_indexes  # noqa: E402
from app.settings import load_settings  # noqa: E402


def _check_qdrant(clients, settings, errors: List[str]) -> None:
    try:
        info = clients.qdrant.get_collection(settings.qdrant.collection)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Qdrant: {exc}")
        return

    config = info.config.params.vectors
    size = getattr(config, "size", None)
    if size is None and isinstance(config, dict):
        size = config.get("size")
    if size and size != clients.embed_dims:
        errors.append(
            f"Qdrant: dimension de coleccion {size} != {clients.embed_dims} (EMBED_DIMS)"
        )
    try:
        ensure_payload_indexes(clients.qdrant, settings.qdrant.collection)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Qdrant (payload indexes): {exc}")


def _check_postgres(clients, errors: List[str]) -> None:
    try:
        with clients.postgres.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"PostgreSQL: {exc}")


def _check_neo4j(clients, settings, errors: List[str]) -> None:
    try:
        with clients.neo4j.session(database=settings.neo4j.database) as session:
            session.run("RETURN 1 AS ok").single()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Neo4j: {exc}")


def _check_azure(clients, errors: List[str]) -> None:
    # `clients.embed_dims` already forces a minimal embedding call during init; reuse it.
    try:
        if not clients.embed_dims or clients.embed_dims <= 0:
            raise ValueError("invalid embed_dims")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Azure OpenAI: {exc}")


def run(env: str | None) -> int:
    settings = load_settings(env)
    clients = build_service_clients(settings)
    errors: List[str] = []
    try:
        _check_azure(clients, errors)
        _check_qdrant(clients, settings, errors)
        _check_postgres(clients, errors)
        _check_neo4j(clients, settings, errors)
    finally:
        clients.close()

    if errors:
        for err in errors:
            print(f"? {err}")
        return 1

    print("? Healthcheck OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verifica conectividad y configuracion de servicios externos")
    parser.add_argument("--env", help="Ruta a archivo .env", default=None)
    args = parser.parse_args()
    return run(args.env)


if __name__ == "__main__":
    sys.exit(main())
