from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv, find_dotenv


def _get_env_value(names: list[str]) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _is_localhost(value: str) -> bool:
    lowered = value.lower()
    return "localhost" in lowered or "127.0.0.1" in lowered


def run(env_path: str | None) -> int:
    if env_path:
        load_dotenv(env_path, override=True)
    else:
        dot = find_dotenv(usecwd=True)
        if dot:
            load_dotenv(dot, override=True)

    required = {
        "QDRANT_URI": ["QDRANT_URI"],
        "NEO4J_URI": ["NEO4J_URI"],
        "NEO4J_PASSWORD": ["NEO4J_PASSWORD"],
        "POSTGRES_HOST": ["POSTGRES_HOST", "PGHOST"],
        "POSTGRES_DB": ["POSTGRES_DB", "PGDATABASE"],
        "POSTGRES_USER": ["POSTGRES_USER", "PGUSER"],
        "POSTGRES_PASSWORD": ["POSTGRES_PASSWORD", "PGPASSWORD"],
        "AZURE_OPENAI_ENDPOINT": ["AZURE_OPENAI_ENDPOINT"],
        "AZURE_OPENAI_API_KEY": ["AZURE_OPENAI_API_KEY"],
    }

    optional = {
        "NEO4J_USER": ["NEO4J_USER", "NEO4J_USERNAME"],
        "QDRANT_API_KEY": ["QDRANT_API_KEY"],
        "AZURE_STORAGE_CONNECTION_STRING": ["AZURE_STORAGE_CONNECTION_STRING"],
    }

    missing: list[str] = []
    warnings: list[str] = []

    print("Azure Env Preflight")
    print("===================")

    for label, names in required.items():
        value = _get_env_value(names)
        if not value:
            missing.append(label)
            print(f"[MISSING] {label} (aliases: {', '.join(names)})")
            continue
        print(f"[OK] {label}")
        if _is_localhost(value):
            warnings.append(f"{label} apunta a localhost; no funcionara en Azure.")

    for label, names in optional.items():
        value = _get_env_value(names)
        if not value:
            print(f"[WARN] {label} no esta definido (opcional)")
            continue
        print(f"[OK] {label}")
        if _is_localhost(value):
            warnings.append(f"{label} apunta a localhost; revisa valor.")

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"- {w}")

    if missing:
        print("\nErrores:")
        print("Faltan variables obligatorias:")
        for m in missing:
            print(f"- {m}")
        return 1

    print("\nOK: variables minimas presentes.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight de variables de entorno para Azure Container Apps.")
    parser.add_argument("--env", help="Ruta a archivo .env (opcional).", default=None)
    args = parser.parse_args()

    env_path = None
    if args.env:
        env_path = str(Path(args.env))
        if not Path(env_path).exists():
            print(f"[ERROR] Archivo .env no encontrado: {env_path}")
            return 1

    return run(env_path)


if __name__ == "__main__":
    sys.exit(main())
