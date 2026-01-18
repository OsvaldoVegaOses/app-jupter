"""Aplica un plan de codificación abierta y axial desde archivos JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from app.coding import assign_open_code
from app.axial import assign_axial_relation
from app.clients import build_service_clients
from app.settings import load_settings


def load_json(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"Expected a list in {path}, got {type(data).__name__}")
    return data


def apply_open_codes(open_defs: List[Dict[str, Any]], env_settings, clients) -> None:
    for entry in open_defs:
        fragment_id = entry.get("fragmento_id")
        codigo = entry.get("codigo")
        cita = entry.get("cita")
        if not fragment_id or not codigo or not cita:
            raise ValueError(f"Entrada de codificación incompleta: {entry}")
        assign_open_code(
            clients,
            env_settings,
            fragment_id=fragment_id,
            codigo=codigo,
            cita=cita,
            fuente=entry.get("fuente"),
            memo=entry.get("memo"),
        )


def apply_axial_relations(axial_defs: List[Dict[str, Any]], env_settings, clients) -> None:
    for entry in axial_defs:
        categoria = entry.get("categoria")
        codigo = entry.get("codigo")
        relacion = entry.get("tipo") or entry.get("relacion")
        evidencia = entry.get("evidencia") or entry.get("fragmentos")
        if not categoria or not codigo or not relacion or not evidencia:
            raise ValueError(f"Entrada axial incompleta: {entry}")
        if isinstance(evidencia, str):
            evidencia = [evidencia]
        assign_axial_relation(
            clients,
            env_settings,
            categoria=categoria,
            codigo=codigo,
            relacion=relacion,
            evidencia=list(dict.fromkeys(evidencia)),
            memo=entry.get("memo"),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Aplica codificación abierta y axial desde archivos JSON")
    parser.add_argument("--env", default=None, help="Ruta al archivo .env")
    parser.add_argument("--open-codes", type=Path, help="JSON con definiciones de codificación abierta")
    parser.add_argument("--axial", type=Path, help="JSON con relaciones axiales")
    args = parser.parse_args()

    settings = load_settings(args.env)
    clients = build_service_clients(settings)

    try:
        open_defs = load_json(args.open_codes)
        axial_defs = load_json(args.axial)
        apply_open_codes(open_defs, settings, clients)
        apply_axial_relations(axial_defs, settings, clients)
    finally:
        clients.close()

    print("Codificación aplicada correctamente")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
