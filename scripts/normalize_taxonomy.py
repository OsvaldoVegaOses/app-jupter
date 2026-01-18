"""Normaliza códigos y categorías mal acentuados en Postgres, Neo4j y Qdrant."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from psycopg2.extras import Json
from qdrant_client.models import FieldCondition, Filter, MatchValue

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.clients import build_service_clients
from app.neo4j_block import merge_fragments
from app.settings import load_settings


NORMALIZATION_MAP: Dict[str, str] = {
    "Gesti�n de Programas": "Gestión de Programas",
    "Gesti�n": "Gestión",
    "Infraestructura Cr�tica": "Infraestructura Crítica",
    "Participaci�n Ciudadana": "Participación Ciudadana",
    "Planificaci�n": "Planificación",
    "Planificaci�n Regional": "Planificación Regional",
    "Memoria Territorial": "Memoria territorial",
}

LOCAL_FILES = [
    Path("metadata/open_codes.json"),
    Path("metadata/axial.json"),
    Path("metadata/metadata_plan.json"),
]


def normalize_string(value: Any) -> Any:
    if isinstance(value, str):
        return NORMALIZATION_MAP.get(value, value)
    return value


def normalize_postgres(clients) -> Tuple[Dict[str, int], Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    stats = defaultdict(int)
    payload_updates: Dict[str, Dict[str, Any]] = {}
    neo_rows: List[Dict[str, Any]] = []
    with clients.postgres.cursor() as cur:
        for old, new in NORMALIZATION_MAP.items():
            if old == new:
                continue
            cur.execute(
                "UPDATE analisis_codigos_abiertos SET codigo = %s WHERE codigo = %s",
                (new, old),
            )
            stats["analisis_codigos_abiertos"] += cur.rowcount

            cur.execute(
                "UPDATE analisis_axial SET codigo = %s WHERE codigo = %s",
                (new, old),
            )
            stats["analisis_axial_codigo"] += cur.rowcount
            cur.execute(
                "UPDATE analisis_axial SET categoria = %s WHERE categoria = %s",
                (new, old),
            )
            stats["analisis_axial_categoria"] += cur.rowcount

        cur.execute(
            """
            SELECT id, archivo, fragmento, par_idx, char_len,
                   area_tematica, actor_principal, metadata
              FROM entrevista_fragmentos
            """
        )
        rows = cur.fetchall()
    for row in rows:
        fragment_id, archivo, fragmento, par_idx, char_len, area_tematica, actor_principal, metadata = row
        new_area = normalize_string(area_tematica)
        new_actor = normalize_string(actor_principal)

        metadata_dict = metadata if isinstance(metadata, dict) else {}
        metadata_changed = False
        if metadata_dict:
            for key, value in list(metadata_dict.items()):
                if isinstance(value, str):
                    new_value = normalize_string(value)
                    if new_value != value:
                        metadata_dict[key] = new_value
                        metadata_changed = True
            codigos = metadata_dict.get("codigos_ancla")
            if isinstance(codigos, list) and codigos:
                new_codigos = [normalize_string(code) for code in codigos]
                if new_codigos != codigos:
                    metadata_dict["codigos_ancla"] = new_codigos
                    metadata_changed = True

        if (
            metadata_changed
            or new_area != area_tematica
            or new_actor != actor_principal
        ):
            with clients.postgres.cursor() as cur:
                cur.execute(
                    """
                    UPDATE entrevista_fragmentos
                       SET area_tematica = %s,
                           actor_principal = %s,
                           metadata = %s
                     WHERE id = %s
                    """,
                    (
                        new_area,
                        new_actor,
                        Json(metadata_dict) if metadata_dict else None,
                        fragment_id,
                    ),
                )
            stats["entrevista_fragmentos"] += 1

            payload = {}
            if new_area != area_tematica and new_area is not None:
                payload["area_tematica"] = new_area
            if new_actor != actor_principal and new_actor is not None:
                payload["actor_principal"] = new_actor
            if metadata_changed:
                payload["metadata"] = metadata_dict
                if "codigos_ancla" in metadata_dict:
                    payload["codigos_ancla"] = metadata_dict["codigos_ancla"]
            if payload:
                payload_updates[fragment_id] = payload

            metadata_json = json.dumps(metadata_dict, ensure_ascii=False) if metadata_dict else None
            neo_rows.append(
                {
                    "id": fragment_id,
                    "archivo": archivo,
                    "fragmento": fragmento,
                    "par_idx": par_idx,
                    "char_len": char_len,
                    "actor_principal": new_actor,
                    "metadata": metadata_json,
                    "genero": metadata_dict.get("genero") if metadata_dict else None,
                    "periodo": metadata_dict.get("periodo") if metadata_dict else None,
                }
            )

    clients.postgres.commit()
    return stats, payload_updates, neo_rows


def normalize_qdrant(client, collection: str, payload_updates: Dict[str, Dict[str, Any]]) -> int:
    updated_points = 0
    for point_id, payload in payload_updates.items():
        cleaned_payload = {key: value for key, value in payload.items() if value is not None}
        if not cleaned_payload:
            continue
        client.set_payload(collection_name=collection, payload=cleaned_payload, points=[point_id])
        updated_points += 1

    list_fields = ["codigos_ancla"]
    single_fields = ["area_tematica", "actor_principal"]

    for old, new in NORMALIZATION_MAP.items():
        if old == new:
            continue
        for field in single_fields:
            scroll_filter = Filter(must=[FieldCondition(key=field, match=MatchValue(value=old))])
            offset = None
            while True:
                points, offset = client.scroll(
                    collection_name=collection,
                    scroll_filter=scroll_filter,
                    limit=128,
                    offset=offset,
                    with_payload=False,
                )
                if not points:
                    break
                ids = [point.id for point in points]
                client.set_payload(collection_name=collection, payload={field: new}, points=ids)
                updated_points += len(ids)
        for field in list_fields:
            scroll_filter = Filter(must=[FieldCondition(key=field, match=MatchValue(value=old))])
            offset = None
            while True:
                points, offset = client.scroll(
                    collection_name=collection,
                    scroll_filter=scroll_filter,
                    limit=128,
                    offset=offset,
                    with_payload=True,
                )
                if not points:
                    break
                for point in points:
                    payload = point.payload or {}
                    current = payload.get(field)
                    if not isinstance(current, list):
                        continue
                    new_list = [new if item == old else item for item in current]
                    if new_list != current:
                        client.set_payload(
                            collection_name=collection,
                            payload={field: new_list},
                            points=[point.id],
                        )
                        updated_points += 1
    return updated_points


def normalize_neo4j(clients, database: str, neo_rows: List[Dict[str, Any]]) -> Dict[str, int]:
    stats = defaultdict(int)
    if neo_rows:
        merge_fragments(clients.neo4j, database, neo_rows)
        stats["fragmentos"] = len(neo_rows)

    for label in ("Codigo", "Categoria"):
        for old, new in NORMALIZATION_MAP.items():
            if old == new:
                continue
            cypher = f"MATCH (n:{label} {{nombre:$old}}) SET n.nombre = $new"
            with clients.neo4j.session(database=database) as session:
                result = session.run(cypher, old=old, new=new)
                summary = result.consume()
                stats[f"{label.lower()}"] += summary.counters.properties_set
    return stats


def normalize_local_files() -> Dict[str, int]:
    result = {}
    for path in LOCAL_FILES:
        if not path.exists():
            continue
        try:
            content = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        changed = False
        if isinstance(content, list):
            for entry in content:
                if not isinstance(entry, dict):
                    continue
                for key in ("codigo", "categoria", "actor_principal", "area_tematica"):
                    if key in entry:
                        new_value = normalize_string(entry[key])
                        if new_value != entry[key]:
                            entry[key] = new_value
                            changed = True
                if "codigos" in entry and isinstance(entry["codigos"], list):
                    entry["codigos"] = [normalize_string(val) for val in entry["codigos"]]
                    changed = True
                metadata = entry.get("metadata")
                if isinstance(metadata, dict):
                    for meta_key, meta_value in list(metadata.items()):
                        new_value = normalize_string(meta_value)
                        if new_value != meta_value:
                            metadata[meta_key] = new_value
                            changed = True
        if changed:
            path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result[str(path)] = len(content) if isinstance(content, list) else 1
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normaliza nombres de códigos/categorías con tildes correctas en Postgres, Neo4j y Qdrant."
    )
    parser.add_argument("--env", default=None, help="Ruta al archivo .env")
    args = parser.parse_args()

    settings = load_settings(args.env)
    clients = build_service_clients(settings)

    try:
        pg_stats, payload_updates, neo_rows = normalize_postgres(clients)
        qdrant_updated = normalize_qdrant(clients.qdrant, settings.qdrant.collection, payload_updates)
        neo_stats = normalize_neo4j(clients, settings.neo4j.database, neo_rows)
    finally:
        clients.close()

    local_stats = normalize_local_files()

    print("Normalización completada.")
    if pg_stats:
        print("PostgreSQL:", dict(pg_stats))
    print(f"Qdrant: {qdrant_updated} puntos actualizados")
    if neo_stats:
        print("Neo4j:", dict(neo_stats))
    if local_stats:
        print("Archivos locales normalizados:", local_stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
