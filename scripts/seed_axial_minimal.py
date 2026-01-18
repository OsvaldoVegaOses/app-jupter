"""Seed minimal axial relationships into PostgreSQL to unlock Stage 4 graph analytics.

Why this exists:
- Graph community/centrality needs edges.
- If each fragment only has a single open code, co-occurrence edges can be empty.
- This script creates a small, evidence-backed axial layer (Categoria -> Codigo)
  in `analisis_axial` so Louvain/PageRank/Betweenness have a non-empty graph.

This script ONLY writes to PostgreSQL (source of truth). It does not touch Neo4j.

Usage (PowerShell):
    ./.venv/Scripts/python.exe scripts/seed_axial_minimal.py --project jose-domingo-vg --max-relations 20

Dry-run:
    ./.venv/Scripts/python.exe scripts/seed_axial_minimal.py --project jose-domingo-vg --max-relations 20 --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

# Allow running as a script from the repo root or from the scripts/ folder.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


@dataclass(frozen=True)
class SeedRow:
    project_id: str
    categoria: str
    codigo: str
    relacion: str
    archivo: str
    memo: Optional[str]
    evidencia: List[str]


def _pick_category(code: str) -> str:
    c = (code or "").lower()
    if any(k in c for k in ["particip", "gobern", "organiza", "vincul"]):
        return "gobernanza_participacion"
    if any(k in c for k in ["drenaje", "aneg", "agua", "lluv", "reforest", "ambient"]):
        return "gestion_urbana_ambiental"
    if any(k in c for k in ["inform", "whatsapp", "comunic", "canal"]):
        return "informacion_comunicacion"
    return "otros_ejes"


def _fetch_top_codes(pg, project_id: str, limit: int) -> List[Tuple[str, int]]:
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT codigo, COUNT(*) AS citas
            FROM analisis_codigos_abiertos
            WHERE project_id = %s
            GROUP BY codigo
            ORDER BY COUNT(*) DESC
            LIMIT %s
            """,
            (project_id, limit),
        )
        return [(r[0], int(r[1])) for r in cur.fetchall()]


def _fetch_evidence_fragments(pg, project_id: str, code: str, limit: int) -> List[str]:
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT fragmento_id
            FROM analisis_codigos_abiertos
            WHERE project_id = %s AND codigo = %s
            ORDER BY fragmento_id
            LIMIT %s
            """,
            (project_id, code, limit),
        )
        return [r[0] for r in cur.fetchall()]


def _fetch_archivo_for_fragment(pg, project_id: str, fragment_id: str) -> str:
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT archivo
            FROM entrevista_fragmentos
            WHERE project_id = %s AND id = %s
            """,
            (project_id, fragment_id),
        )
        row = cur.fetchone()
    return str(row[0]) if row and row[0] is not None else ""


def _build_seed_rows(
    pg,
    project_id: str,
    max_relations: int,
    codes_scan: int,
    min_evidence: int,
) -> List[SeedRow]:
    top_codes = _fetch_top_codes(pg, project_id, codes_scan)
    rows: List[SeedRow] = []

    for code, citas in top_codes:
        if len(rows) >= max_relations:
            break
        evidence = _fetch_evidence_fragments(pg, project_id, code, max(1, min_evidence))
        if len(evidence) < min_evidence:
            continue
        archivo = _fetch_archivo_for_fragment(pg, project_id, evidence[0])
        categoria = _pick_category(code)
        memo = f"[seed] relación mínima para destrabar E4 (citas={citas}, evidencias={len(evidence)})"
        rows.append(
            SeedRow(
                project_id=project_id,
                categoria=categoria,
                codigo=code,
                relacion="partede",
                archivo=archivo or "(unknown)",
                memo=memo,
                evidencia=evidence,
            )
        )

    return rows


def _upsert_rows(pg, rows: Iterable[SeedRow]) -> int:
    data = list(rows)
    if not data:
        return 0

    # Import locally to avoid heavy imports unless needed.
    from app.postgres_block import ensure_axial_table, upsert_axial_relationships

    ensure_axial_table(pg)

    axial_rows = [
        (
            r.project_id,
            r.categoria,
            r.codigo,
            r.relacion,
            r.archivo,
            r.memo,
            r.evidencia,
        )
        for r in data
    ]
    upsert_axial_relationships(pg, axial_rows)
    return len(data)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="default", help="Project ID (project_id)")
    parser.add_argument("--max-relations", type=int, default=20, help="How many axial edges to seed")
    parser.add_argument(
        "--codes-scan",
        type=int,
        default=100,
        help="Scan top-N open codes to find evidence-backed seeds",
    )
    parser.add_argument(
        "--min-evidence",
        type=int,
        default=1,
        help="Minimum number of fragment IDs to attach as evidence (1 or 2 recommended)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write, only print plan")
    args = parser.parse_args(argv)

    from app.settings import load_settings
    from app.clients import get_pg_connection, return_pg_connection

    settings = load_settings()
    pg = get_pg_connection(settings)
    try:
        rows = _build_seed_rows(
            pg,
            args.project,
            args.max_relations,
            args.codes_scan,
            max(1, int(args.min_evidence)),
        )
        if not rows:
            print(
                "No seed rows built. Possible causes: project has no open codes in analisis_codigos_abiertos, "
                "or codes have insufficient fragments for the requested --min-evidence.",
                file=sys.stderr,
            )
            return 2

        print(f"Project: {args.project}")
        print(f"Seed candidates: {len(rows)}")
        by_cat = {}
        for r in rows:
            by_cat[r.categoria] = by_cat.get(r.categoria, 0) + 1
        print("By category:")
        for k in sorted(by_cat):
            print(f"  - {k}: {by_cat[k]}")

        if args.dry_run:
            print("Dry-run: no writes.")
            # Show a compact preview.
            for r in rows[:10]:
                print(f"  {r.categoria} -[:{r.relacion}]-> {r.codigo}  (evid={len(r.evidencia)})")
            return 0

        inserted = _upsert_rows(pg, rows)
        print(f"Upserted into analisis_axial: {inserted}")
        return 0
    finally:
        return_pg_connection(pg)


if __name__ == "__main__":
    raise SystemExit(main())
