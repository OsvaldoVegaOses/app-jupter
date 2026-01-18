#!/usr/bin/env python3
"""
Limpia nodos huérfanos en Neo4j para un proyecto.

Definición de huérfano (en Neo4j):
- Fragmento que no existe en PostgreSQL (entrevista_fragmentos)
- Entrevista que no existe en PostgreSQL (archivo en entrevista_fragmentos)

Uso:
    python scripts/clean_neo4j_orphans.py --project default --dry-run
    python scripts/clean_neo4j_orphans.py --project default --clean
"""

import argparse
import sys
from pathlib import Path
from typing import List, Set

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.settings import load_settings
from app.clients import build_service_clients
from app.project_state import resolve_project


def _fetch_pg_fragment_ids(pg_conn, project_id: str) -> Set[str]:
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM entrevista_fragmentos WHERE project_id = %s",
            (project_id,),
        )
        return {str(row[0]) for row in cur.fetchall() if row and row[0] is not None}


def _fetch_pg_archivos(pg_conn, project_id: str) -> Set[str]:
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT archivo FROM entrevista_fragmentos WHERE project_id = %s",
            (project_id,),
        )
        return {str(row[0]) for row in cur.fetchall() if row and row[0] is not None}


def _fetch_neo4j_fragment_ids(driver, database: str, project_id: str) -> List[str]:
    ids: List[str] = []
    with driver.session(database=database) as session:
        result = session.run(
            "MATCH (f:Fragmento {project_id: $project}) RETURN f.id AS id",
            project=project_id,
        )
        for record in result:
            frag_id = record.get("id")
            if frag_id is not None:
                ids.append(str(frag_id))
    return ids


def _fetch_neo4j_archivos(driver, database: str, project_id: str) -> List[str]:
    archivos: List[str] = []
    with driver.session(database=database) as session:
        result = session.run(
            "MATCH (e:Entrevista {project_id: $project}) RETURN e.nombre AS nombre",
            project=project_id,
        )
        for record in result:
            nombre = record.get("nombre")
            if nombre is not None:
                archivos.append(str(nombre))
    return archivos


def _delete_fragments(driver, database: str, project_id: str, ids: List[str]) -> int:
    if not ids:
        return 0
    with driver.session(database=database) as session:
        result = session.run(
            """
            UNWIND $ids AS id
            MATCH (f:Fragmento {project_id: $project, id: id})
            DETACH DELETE f
            RETURN count(f) AS deleted
            """,
            project=project_id,
            ids=ids,
        )
        record = result.single()
        return int(record["deleted"]) if record else 0


def _delete_entrevistas(driver, database: str, project_id: str, nombres: List[str]) -> int:
    if not nombres:
        return 0
    with driver.session(database=database) as session:
        result = session.run(
            """
            UNWIND $nombres AS nombre
            MATCH (e:Entrevista {project_id: $project, nombre: nombre})
            OPTIONAL MATCH (e)-[:TIENE_FRAGMENTO]->(f:Fragmento)
            DETACH DELETE e, f
            RETURN count(e) AS deleted
            """,
            project=project_id,
            nombres=nombres,
        )
        record = result.single()
        return int(record["deleted"]) if record else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Limpiar huérfanos en Neo4j por proyecto.")
    parser.add_argument("--project", required=True, help="ID del proyecto")
    parser.add_argument("--env", default=".env", help="Archivo .env a cargar")
    parser.add_argument("--dry-run", action="store_true", help="Solo reportar, no eliminar")
    parser.add_argument("--clean", action="store_true", help="Eliminar huérfanos en Neo4j")
    parser.add_argument("--batch", type=int, default=500, help="Tamaño de lote para delete")
    args = parser.parse_args()

    if not args.dry_run and not args.clean:
        args.dry_run = True

    settings = load_settings(env_file=args.env)
    clients = build_service_clients(settings)

    try:
        project_id = resolve_project(args.project, allow_create=False, pg=clients.postgres)
        pg_fragments = _fetch_pg_fragment_ids(clients.postgres, project_id)
        pg_archivos = _fetch_pg_archivos(clients.postgres, project_id)

        neo_fragments = _fetch_neo4j_fragment_ids(clients.neo4j, settings.neo4j.database, project_id)
        neo_archivos = _fetch_neo4j_archivos(clients.neo4j, settings.neo4j.database, project_id)

        orphan_fragments = [fid for fid in neo_fragments if fid not in pg_fragments]
        orphan_archivos = [a for a in neo_archivos if a not in pg_archivos]

        print(f"\n📌 Proyecto: {project_id}")
        print(f"PG fragmentos: {len(pg_fragments)} | Neo4j fragmentos: {len(neo_fragments)}")
        print(f"PG entrevistas: {len(pg_archivos)} | Neo4j entrevistas: {len(neo_archivos)}")
        print(f"Huérfanos en Neo4j -> Fragmentos: {len(orphan_fragments)} | Entrevistas: {len(orphan_archivos)}")

        if args.dry_run:
            print("\n✅ Dry-run: no se eliminó nada.")
            return 0

        deleted_fragments = 0
        deleted_entrevistas = 0

        for i in range(0, len(orphan_fragments), max(1, int(args.batch))):
            batch_ids = orphan_fragments[i : i + int(args.batch)]
            deleted_fragments += _delete_fragments(
                clients.neo4j,
                settings.neo4j.database,
                project_id,
                batch_ids,
            )

        for i in range(0, len(orphan_archivos), max(1, int(args.batch))):
            batch_names = orphan_archivos[i : i + int(args.batch)]
            deleted_entrevistas += _delete_entrevistas(
                clients.neo4j,
                settings.neo4j.database,
                project_id,
                batch_names,
            )

        print("\n🧹 Limpieza completada")
        print(f"Fragmentos eliminados: {deleted_fragments}")
        print(f"Entrevistas eliminadas: {deleted_entrevistas}")
        return 0
    finally:
        clients.close()


if __name__ == "__main__":
    raise SystemExit(main())
