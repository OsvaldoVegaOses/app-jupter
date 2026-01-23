#!/usr/bin/env python
"""Dry-run (DB directo) de auto-merge de códigos candidatos.

Objetivo
- Reproducir el flujo "detect duplicates -> auto-merge" sin depender del backend/auth.
- NO modifica datos: usa `preview_merge_candidates_by_code`.

Uso:
  python scripts/dry_run_db_auto_merge.py --project jd-007 --threshold 0.80 --limit 10

Salida:
- Lista de pares sugeridos (source -> target)
- Por par: would_move / would_dedupe / would_merge
- Totales agregados
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from typing import Any, Dict, List, Tuple

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from scripts.cleanup_duplicate_codes import (
    find_similar_candidates,
    get_pg_connection,
)

from app.postgres_block import preview_merge_candidates_by_code


load_dotenv(os.getenv("APP_ENV_FILE", ".env"))


_WORD_SPLIT_RE = re.compile(r"[\s_\-\/\\]+", re.UNICODE)


def _normalize_text(value: str) -> str:
    if value is None:
        return ""
    trimmed = str(value).strip().lower()
    normalized = unicodedata.normalize("NFKD", trimmed)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _tokenize(value: str) -> List[str]:
    norm = _normalize_text(value)
    parts = [p for p in _WORD_SPLIT_RE.split(norm) if p]
    # Mantener tokens de contenido (evitar 1-2 letras)
    return [p for p in parts if len(p) >= 3]


def _passes_token_overlap_guard(code1: str, code2: str) -> bool:
    """Filtro simple anti falsos positivos (ej. 'cauce' vs 'canal').

    Regla:
    - Si ambos tienen >= 2 tokens, exigir al menos 1 token en común.
    - Si alguno tiene < 2 tokens, no bloquear (son frases cortas).
    """

    t1 = set(_tokenize(code1))
    t2 = set(_tokenize(code2))

    if len(t1) >= 2 and len(t2) >= 2:
        return len(t1.intersection(t2)) >= 1

    return True


def _choose_target(code1: str, code2: str) -> Tuple[str, str]:
    """Elige target determinísticamente: el más corto (normalizado); el otro es source."""

    n1 = _normalize_text(code1)
    n2 = _normalize_text(code2)

    if len(n1) < len(n2):
        return code2, code1  # source, target
    if len(n2) < len(n1):
        return code1, code2

    # empate: orden lexicográfico normalizado
    if n1 <= n2:
        return code2, code1
    return code1, code2


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run DB directo de auto-merge (candidatos).")
    parser.add_argument("--project", required=True, help="ID del proyecto (ej. jd-007)")
    parser.add_argument("--threshold", type=float, default=0.80, help="Umbral similitud (0-1)")
    parser.add_argument("--limit", type=int, default=10, help="Máximo de pares a evaluar")
    parser.add_argument(
        "--no-token-guard",
        action="store_true",
        help="Desactiva filtro anti falsos positivos por solapamiento de tokens",
    )

    args = parser.parse_args()

    project_id: str = args.project
    threshold: float = float(args.threshold)
    limit: int = int(args.limit)

    conn = get_pg_connection()
    try:
        # Detectar pares similares (solo candidatos)
        pairs = find_similar_candidates(conn, project_id=project_id, threshold=threshold, limit=max(limit * 5, 50))

        # Filtrar exact duplicates (code1==code2) y aplicar guard
        filtered: List[Dict[str, Any]] = []
        for p in pairs:
            code1 = (p.get("code1") or "").strip()
            code2 = (p.get("code2") or "").strip()
            if not code1 or not code2:
                continue
            if _normalize_text(code1) == _normalize_text(code2):
                continue
            if not args.no_token_guard and not _passes_token_overlap_guard(code1, code2):
                continue
            filtered.append(p)
            if len(filtered) >= limit:
                break

        if not filtered:
            print(
                f"No se encontraron pares (project={project_id}, threshold={threshold}, limit={limit}). "
                "Tip: prueba con --threshold 0.72 o --no-token-guard."
            )
            return 0

        total_would_move = 0
        total_would_dedupe = 0
        total_would_merge = 0

        print(f"project={project_id} threshold={threshold} limit={limit}")
        print("---")

        for idx, p in enumerate(filtered, start=1):
            code1 = str(p.get("code1") or "").strip()
            code2 = str(p.get("code2") or "").strip()
            similarity = p.get("similarity")

            source, target = _choose_target(code1, code2)

            preview = preview_merge_candidates_by_code(
                conn,
                project_id=project_id,
                source_codigo=source,
                target_codigo=target,
            )

            would_move = int(preview.get("would_move") or 0)
            would_dedupe = int(preview.get("would_dedupe") or 0)
            would_merge = int(preview.get("would_merge") or 0)

            total_would_move += would_move
            total_would_dedupe += would_dedupe
            total_would_merge += would_merge

            sim_txt = f"sim={similarity}" if similarity is not None else ""
            print(
                f"{idx:02d}. {source}  ->  {target}  {sim_txt}\n"
                f"    would_move={would_move} would_dedupe={would_dedupe} would_merge={would_merge}"
            )

        print("---")
        print(f"TOTAL would_move={total_would_move} would_dedupe={total_would_dedupe} would_merge={total_would_merge}")
        print("(Esto es un dry-run DB: no se ejecutaron UPDATEs.)")
        return 0

    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
