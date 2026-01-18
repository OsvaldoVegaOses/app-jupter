"""
Operaciones de actualización de metadatos.

Este módulo permite actualizar metadatos de fragmentos en las tres
bases de datos de manera sincronizada (PostgreSQL, Qdrant, Neo4j).

Casos de uso:
    - Añadir metadatos demográficos (género, período)
    - Clasificar actores principales
    - Marcar entrevistas que requieren protocolos especiales

Funciones principales:
    - apply_metadata_entries(): Aplica metadatos desde lista de entries
    - load_plan_from_json(): Carga plan de metadatos desde JSON
    - load_plan_from_csv(): Carga plan de metadatos desde CSV

Formato de entry (JSON o CSV):
    {
        "archivo": "Entrevista_001.docx",
        "actor_principal": "pescador",
        "metadata": {"genero": "masculino", "periodo": "2020-2024"},
        "requiere_protocolo_lluvia": true,
        "fragmentos": ["frag_001", "frag_002"]  # Opcional
    }

Sincronización:
    Los metadatos se actualizan en:
    1. PostgreSQL: Columnas metadata, actor_principal, requiere_protocolo_lluvia
    2. Qdrant: Payload de los puntos vectoriales
    3. Neo4j: Propiedades de nodos Entrevista y Fragmento
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from psycopg2.extras import Json


def _ensure_fragment_ids(
    pg_conn, archivo: str, fragment_ids: Optional[Sequence[str]], project_id: str
) -> List[str]:
    """Obtiene IDs de fragmentos filtrados por project_id.
    
    IMPORTANTE: Filtra por project_id para garantizar aislamiento.
    """
    with pg_conn.cursor() as cur:
        if fragment_ids:
            cur.execute(
                """
                SELECT id FROM entrevista_fragmentos
                 WHERE id = ANY(%s) AND project_id = %s
                """,
                (list(fragment_ids), project_id),
            )
        else:
            cur.execute(
                """
                SELECT id FROM entrevista_fragmentos
                 WHERE archivo = %s AND project_id = %s
                """,
                (archivo, project_id),
            )
        rows = cur.fetchall()
    if not rows:
        raise ValueError(
            f"No se encontraron fragmentos para archivo='{archivo}' en proyecto='{project_id}'"
            + (f" con ids={fragment_ids}" if fragment_ids else "")
        )
    return [row[0] for row in rows]


def _update_postgres(
    pg_conn,
    fragment_ids: Sequence[str],
    metadata: Dict[str, Any],
    actor: Optional[str],
    lluvia: Optional[bool],
    project_id: str,
) -> List[str]:
    """Actualiza metadatos en PostgreSQL filtrado por project_id."""
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            UPDATE entrevista_fragmentos
               SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                   actor_principal = COALESCE(%s, actor_principal),
                   requiere_protocolo_lluvia = CASE
                       WHEN %s IS NULL THEN requiere_protocolo_lluvia
                       ELSE %s
                   END
             WHERE id = ANY(%s) AND project_id = %s
         RETURNING id
            """,
            (Json(metadata), actor, lluvia, lluvia, list(fragment_ids), project_id),
        )
        updated = [row[0] for row in cur.fetchall()]
    pg_conn.commit()
    return updated


def _update_qdrant(
    qdrant_client,
    collection: str,
    fragment_ids: Sequence[str],
    metadata: Dict[str, Any],
    actor: Optional[str],
    lluvia: Optional[bool],
):
    payload: Dict[str, Any] = {}
    if metadata:
        payload["metadata"] = metadata
        if "genero" in metadata:
            payload["genero"] = metadata.get("genero")
        if "periodo" in metadata:
            payload["periodo"] = metadata.get("periodo")
        if "fecha_entrevista" in metadata:
            payload["fecha_entrevista"] = metadata.get("fecha_entrevista")
        if "lugar" in metadata:
            payload["lugar"] = metadata.get("lugar")
    if actor is not None:
        payload["actor_principal"] = actor
    if lluvia is not None:
        payload["requiere_protocolo_lluvia"] = bool(lluvia)

    if payload:
        qdrant_client.set_payload(
            collection_name=collection,
            payload=payload,
            points=list(fragment_ids),
        )


def _update_neo4j(
    neo4j_driver,
    database: str,
    archivo: str,
    fragment_ids: Sequence[str],
    metadata: Dict[str, Any],
    actor: Optional[str],
    project_id: str,
):
    """Actualiza metadatos en Neo4j filtrado por project_id.
    
    IMPORTANTE: Usa claves compuestas (nombre, project_id) para aislamiento.
    """
    genero = metadata.get("genero") if metadata else None
    periodo = metadata.get("periodo") if metadata else None
    metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None

    with neo4j_driver.session(database=database) as session:
        if metadata_json is not None:
            session.run(
                """
                MATCH (e:Entrevista {nombre:$archivo, project_id:$project_id})
                SET e.metadata = COALESCE($metadata, e.metadata),
                    e.genero = COALESCE($genero, e.genero),
                    e.periodo = COALESCE($periodo, e.periodo)
                """,
                archivo=archivo,
                project_id=project_id,
                metadata=metadata_json,
                genero=genero,
                periodo=periodo,
            )
            session.run(
                """
                MATCH (:Entrevista {nombre:$archivo, project_id:$project_id})-[:TIENE_FRAGMENTO]->(f:Fragmento)
                WHERE f.id IN $ids AND f.project_id = $project_id
                SET f.metadata = COALESCE($metadata, f.metadata),
                    f.genero = COALESCE($genero, f.genero),
                    f.periodo = COALESCE($periodo, f.periodo)
                """,
                archivo=archivo,
                project_id=project_id,
                ids=list(fragment_ids),
                metadata=metadata_json,
                genero=genero,
                periodo=periodo,
            )
        if actor is not None:
            session.run(
                "MATCH (e:Entrevista {nombre:$archivo, project_id:$project_id}) SET e.actor_principal = $actor",
                archivo=archivo,
                project_id=project_id,
                actor=actor,
            )
            session.run(
                """
                MATCH (:Entrevista {nombre:$archivo, project_id:$project_id})-[:TIENE_FRAGMENTO]->(f:Fragmento)
                WHERE f.id IN $ids AND f.project_id = $project_id
                SET f.actor_principal = $actor
                """,
                archivo=archivo,
                project_id=project_id,
                ids=list(fragment_ids),
                actor=actor,
            )


def load_plan_from_json(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"El archivo {path} debe contener una lista de entradas.")
    return data


def _coerce_str_value(value: str) -> Any:
    text = value.strip()
    if not text:
        return None
    lower = text.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def load_plan_from_csv(path: Path) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if "archivo" not in reader.fieldnames:
            raise ValueError("El CSV debe contener una columna 'archivo'.")
        for row in reader:
            archivo = (row.get("archivo") or "").strip()
            if not archivo:
                continue
            actor = row.get("actor_principal")
            actor = actor.strip() if actor else None
            lluvia_raw = row.get("requiere_protocolo_lluvia")
            lluvia = None
            if lluvia_raw is not None and lluvia_raw.strip():
                parsed = _coerce_str_value(lluvia_raw)
                if isinstance(parsed, bool):
                    lluvia = parsed
                else:
                    raise ValueError(f"Valor invalido para requiere_protocolo_lluvia: {lluvia_raw!r}")
            fragmentos_raw = row.get("fragmentos")
            fragmentos: Optional[List[str]] = None
            if fragmentos_raw:
                parts = [frag.strip() for frag in fragmentos_raw.replace(";", ",").split(",")]
                fragmentos = [frag for frag in parts if frag]
                if not fragmentos:
                    fragmentos = None

            metadata: Dict[str, Any] = {}
            for key, value in row.items():
                if key in {"archivo", "actor_principal", "requiere_protocolo_lluvia", "fragmentos"}:
                    continue
                if value is None:
                    continue
                coerced = _coerce_str_value(value)
                if coerced is None:
                    continue
                metadata[key] = coerced

            entries.append(
                {
                    "archivo": archivo,
                    "metadata": metadata,
                    "actor_principal": actor,
                    "requiere_protocolo_lluvia": lluvia,
                    "fragmentos": fragmentos,
                }
            )
    return entries


def apply_metadata_entries(
    clients, settings, entries: Iterable[Dict[str, Any]], project_id: str = "default"
) -> Dict[str, Any]:
    """Aplica metadatos a fragmentos filtrados por project_id.
    
    IMPORTANTE: project_id es requerido para garantizar aislamiento.
    """
    total_fragments = 0
    details: List[Dict[str, Any]] = []

    for raw_entry in entries:
        archivo = raw_entry.get("archivo")
        if not archivo or not isinstance(archivo, str):
            raise ValueError(f"Cada entrada debe incluir 'archivo' (str). Entrada: {raw_entry}")

        metadata = raw_entry.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError(f"'metadata' debe ser un objeto. Entrada: {raw_entry}")

        actor = raw_entry.get("actor_principal")
        if actor is not None and not isinstance(actor, str):
            raise ValueError(f"'actor_principal' debe ser texto. Entrada: {raw_entry}")

        lluvia = raw_entry.get("requiere_protocolo_lluvia")
        if lluvia is not None and not isinstance(lluvia, bool):
            raise ValueError(f"'requiere_protocolo_lluvia' debe ser booleano. Entrada: {raw_entry}")

        fragment_ids = raw_entry.get("fragmentos")
        if fragment_ids is not None:
            if not isinstance(fragment_ids, Sequence):
                raise ValueError(f"'fragmentos' debe ser una lista de IDs. Entrada: {raw_entry}")

        # Todas las operaciones filtradas por project_id
        ids = _ensure_fragment_ids(clients.postgres, archivo, fragment_ids, project_id)
        updated_ids = _update_postgres(clients.postgres, ids, metadata, actor, lluvia, project_id)
        _update_qdrant(
            clients.qdrant,
            settings.qdrant.collection,
            updated_ids,
            metadata,
            actor,
            lluvia,
        )
        _update_neo4j(
            clients.neo4j,
            settings.neo4j.database,
            archivo,
            updated_ids,
            metadata,
            actor,
            project_id,
        )

        total_fragments += len(updated_ids)
        details.append(
            {
                "archivo": archivo,
                "fragmentos": updated_ids,
                "metadata_keys": sorted(metadata.keys()),
                "actor_principal": actor,
                "requiere_protocolo_lluvia": lluvia,
            }
        )

    return {
        "total_files": len(details),
        "total_fragments": total_fragments,
        "details": details,
    }
