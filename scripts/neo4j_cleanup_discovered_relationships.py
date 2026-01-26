#!/usr/bin/env python3
"""Normalize legacy Neo4j relationships created as `origen='descubierta'`.

Goal:
- Keep Neo4j as a *projection* of validated state (ledger-driven).
- Legacy discovered relations contaminate centrality/community metrics and can leak into Selective.

Actions supported:
- report: list counts (default, no writes)
- migrate: move code↔code relationships into Postgres `link_predictions` (pending) and delete from Neo4j
- delete: delete from Neo4j (no ledger migration)

This script is intentionally guarded by __main__ so pytest collection won't execute it.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.clients import build_service_clients
from app.postgres_block import ensure_link_predictions_table
from app.settings import load_settings


def _fetch_discovered_relationships(
    neo4j_driver,
    *,
    database: str,
    project_id: str,
) -> List[Dict[str, Any]]:
    # Match any REL but only within the project_id, and only legacy discovery edges.
    cypher = """
    MATCH (s)-[r:REL]->(t)
    WHERE s.project_id = $project_id
      AND t.project_id = $project_id
      AND (
        toLower(coalesce(r.origen, '')) = 'descubierta'
        OR toLower(coalesce(r.source, '')) = 'descubierta'
      )
    RETURN id(r) AS rid,
           s.nombre AS source,
           labels(s) AS source_labels,
           t.nombre AS target,
           labels(t) AS target_labels,
           r.tipo AS relation_type,
           r.origen AS origen,
           r.source AS source_prop,
           r.confirmado_en AS confirmado_en
    ORDER BY rid ASC
    """
    with neo4j_driver.session(database=database) as session:
        rows = session.run(cypher, project_id=project_id).data()
    out: List[Dict[str, Any]] = []
    for r in rows or []:
        out.append(
            {
                "rid": int(r.get("rid")),
                "source": r.get("source"),
                "target": r.get("target"),
                "source_labels": r.get("source_labels") or [],
                "target_labels": r.get("target_labels") or [],
                "relation_type": r.get("relation_type"),
                "origen": r.get("origen"),
                "source_prop": r.get("source_prop"),
                "confirmado_en": r.get("confirmado_en"),
            }
        )
    return out


def _delete_relationships(
    neo4j_driver,
    *,
    database: str,
    rel_ids: List[int],
) -> int:
    if not rel_ids:
        return 0
    cypher = """
    MATCH ()-[r:REL]->()
    WHERE id(r) IN $ids
    DELETE r
    RETURN count(*) AS deleted
    """
    with neo4j_driver.session(database=database) as session:
        record = session.run(cypher, ids=[int(x) for x in rel_ids]).single()
    if not record:
        return 0
    try:
        return int(record.get("deleted") or 0)
    except Exception:
        return 0


def _migrate_to_link_predictions(
    pg,
    *,
    project_id: str,
    rows: List[Dict[str, Any]],
    algorithm: str,
) -> int:
    ensure_link_predictions_table(pg)

    inserted = 0
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with pg.cursor() as cur:
        for r in rows:
            src = str(r.get("source") or "").strip()
            tgt = str(r.get("target") or "").strip()
            if not src or not tgt or src == tgt:
                continue

            src_labels = r.get("source_labels") or []
            tgt_labels = r.get("target_labels") or []
            is_code_pair = ("Codigo" in src_labels) and ("Codigo" in tgt_labels)
            if not is_code_pair:
                # We only migrate Codigo↔Codigo to this ledger.
                continue

            # link_predictions treats code pairs as undirected; keep it consistent.
            a, b = (src, tgt) if src <= tgt else (tgt, src)
            rel_type = str(r.get("relation_type") or "asociado_con").strip() or "asociado_con"

            rid = int(r.get("rid") or 0)
            direction_note = f"original={src}->{tgt}" if src != a else f"original={a}->{b}"
            memo = (
                "Migrated from Neo4j legacy relationship (origen='descubierta'). "
                f"{direction_note}; neo4j_rel_id={rid}; migrated_at={now}"
            )

            cur.execute(
                """
                INSERT INTO link_predictions (
                    project_id, source_code, target_code, relation_type,
                    algorithm, score, rank, memo
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (project_id, source_code, target_code, algorithm) DO UPDATE SET
                    relation_type = EXCLUDED.relation_type,
                    memo = COALESCE(link_predictions.memo, EXCLUDED.memo),
                    score = GREATEST(link_predictions.score, EXCLUDED.score),
                    updated_at = NOW()
                """,
                (project_id, a, b, rel_type, algorithm, 0.0, None, memo),
            )
            inserted += 1
    pg.commit()
    return inserted


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cleanup legacy Neo4j edges with origen='descubierta' (normalize projection)."
    )
    parser.add_argument("--project", required=True, help="Project ID")
    parser.add_argument(
        "--action",
        choices=("report", "migrate", "delete"),
        default="report",
        help="What to do: report (no writes), migrate (PG + delete in Neo4j), delete (Neo4j only).",
    )
    parser.add_argument(
        "--algorithm",
        default="legacy_descubierta",
        help="Algorithm value used when migrating into link_predictions (default: legacy_descubierta).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit of relationships processed (0 = no limit).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually perform the action (required for migrate/delete).",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    clients = build_service_clients(settings)
    try:
        if not clients.neo4j:
            print("Neo4j client is not configured.")
            return 2

        project_id = str(args.project).strip()
        if not project_id:
            print("Missing --project")
            return 2

        db = settings.neo4j.database
        rels = _fetch_discovered_relationships(clients.neo4j, database=db, project_id=project_id)
        if args.limit and args.limit > 0:
            rels = rels[: int(args.limit)]

        total = len(rels)
        code_pairs = sum(
            1
            for r in rels
            if ("Codigo" in (r.get("source_labels") or [])) and ("Codigo" in (r.get("target_labels") or []))
        )
        non_code = total - code_pairs

        print(f"Project: {project_id}")
        print(f"Discovered relationships found: {total}")
        print(f"  Codigo↔Codigo: {code_pairs}")
        print(f"  Other (will only be deleted): {non_code}")
        if total:
            sample = rels[:5]
            print("\nSample (first 5):")
            for r in sample:
                src = r.get("source")
                tgt = r.get("target")
                rtype = r.get("relation_type")
                rid = r.get("rid")
                print(f"  - id={rid} {src} -> {tgt} tipo={rtype} labels={r.get('source_labels')}->{r.get('target_labels')}")

        if args.action == "report":
            return 0

        if not args.apply:
            print("\nRefusing to write: pass --apply to run migrate/delete.")
            return 2

        migrated = 0
        if args.action == "migrate":
            migrated = _migrate_to_link_predictions(
                clients.postgres, project_id=project_id, rows=rels, algorithm=str(args.algorithm).strip()
            )
            print(f"\nMigrated to link_predictions (pending): {migrated}")

        deleted = _delete_relationships(clients.neo4j, database=db, rel_ids=[r["rid"] for r in rels])
        print(f"Deleted from Neo4j: {deleted}")
        return 0
    finally:
        clients.close()


if __name__ == "__main__":
    raise SystemExit(main())

