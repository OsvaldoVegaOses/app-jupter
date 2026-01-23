#!/usr/bin/env python
"""Auto-merge REAL (DB directo) de códigos candidatos.

Por qué existe
- Evita depender del backend/auth cuando quieres aplicar merges en Postgres.
- Usa la misma lógica de pares similares que `scripts/cleanup_duplicate_codes.py`.
- Aplica la semántica two-phase del backend vía `merge_candidates_by_code`.

Seguridad
- Por defecto NO modifica datos.
- Para ejecutar merges reales debes pasar: `--apply --yes`.

Uso:
  # Solo plan (preview)
  python scripts/execute_db_auto_merge.py --project jd-007 --threshold 0.80 --limit 10

  # Ejecutar merges reales
  python scripts/execute_db_auto_merge.py --project jd-007 --threshold 0.80 --limit 10 --apply --yes \
    --merged-by "api-key-user" --memo "auto-merge batch 2026-01-20"
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from datetime import date
from typing import Any, Dict, List, Tuple

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from scripts.cleanup_duplicate_codes import find_similar_candidates, get_pg_connection

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
    return [p for p in parts if len(p) >= 3]


def _passes_token_overlap_guard(code1: str, code2: str) -> bool:
    t1 = set(_tokenize(code1))
    t2 = set(_tokenize(code2))
    if len(t1) >= 2 and len(t2) >= 2:
        return len(t1.intersection(t2)) >= 1
    return True


def _choose_target(code1: str, code2: str) -> Tuple[str, str]:
    """Elige target determinísticamente: más corto (normalizado); el otro es source."""
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


def _build_pairs(
    conn,
    project_id: str,
    threshold: float,
    limit: int,
    token_guard: bool,
) -> List[Dict[str, Any]]:
    # Traer más pares para poder filtrar y quedarnos con `limit`
    raw_pairs = find_similar_candidates(conn, project_id=project_id, threshold=threshold, limit=max(limit * 5, 50))

    filtered: List[Dict[str, Any]] = []
    for p in raw_pairs:
        code1 = (p.get("code1") or "").strip()
        code2 = (p.get("code2") or "").strip()
        if not code1 or not code2:
            continue
        if _normalize_text(code1) == _normalize_text(code2):
            continue
        if token_guard and not _passes_token_overlap_guard(code1, code2):
            continue
        filtered.append(p)
        if len(filtered) >= limit:
            break

    return filtered


def _apply_merge_by_code_sql(
        conn,
        project_id: str,
        source_codigo: str,
        target_codigo: str,
        merged_by: str,
) -> Dict[str, int]:
        """Aplica merge (move + dedupe) vía SQL directo.

        Esto evita depender de helpers que, en algunos entornos, pueden reportar
        'affected' sin que los cambios queden persistidos.
        """

        with conn.cursor() as cur:
                # Paso 1: mover evidencia al target cuando no existe ya
                cur.execute(
                        """
                        UPDATE codigos_candidatos src
                             SET codigo = %s,
                                     fusionado_a = %s,
                                     updated_at = NOW()
                         WHERE src.project_id = %s
                             AND (src.codigo = %s OR lower(trim(src.codigo)) = lower(trim(%s)))
                             AND src.estado IN ('pendiente', 'validado')
                             AND NOT EXISTS (
                                     SELECT 1
                                         FROM codigos_candidatos tgt
                                        WHERE tgt.project_id = src.project_id
                                            AND tgt.codigo = %s
                                            AND tgt.fragmento_id = src.fragmento_id
                             )
                         RETURNING src.id
                        """,
                        (target_codigo, target_codigo, project_id, source_codigo, source_codigo, target_codigo),
                )
                moved_ids = [r[0] for r in cur.fetchall()]

                # Paso 2: si ya existe evidencia bajo target, marcar como fusionado
                cur.execute(
                        """
                        UPDATE codigos_candidatos src
                             SET estado = 'fusionado',
                                     fusionado_a = %s,
                                     validado_por = %s,
                                     validado_en = NOW(),
                                     updated_at = NOW()
                         WHERE src.project_id = %s
                             AND (src.codigo = %s OR lower(trim(src.codigo)) = lower(trim(%s)))
                             AND src.estado IN ('pendiente', 'validado')
                             AND EXISTS (
                                     SELECT 1
                                         FROM codigos_candidatos tgt
                                        WHERE tgt.project_id = src.project_id
                                            AND tgt.codigo = %s
                                            AND tgt.fragmento_id = src.fragmento_id
                             )
                         RETURNING src.id
                        """,
                        (target_codigo, merged_by, project_id, source_codigo, source_codigo, target_codigo),
                )
                dedup_ids = [r[0] for r in cur.fetchall()]

        conn.commit()
        return {"moved": len(moved_ids), "deduped": len(dedup_ids), "affected": len(moved_ids) + len(dedup_ids)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-merge REAL (DB directo) de códigos candidatos.")
    parser.add_argument("--project", required=True, help="ID del proyecto (ej. jd-007)")
    parser.add_argument("--threshold", type=float, default=0.80, help="Umbral similitud (0-1)")
    parser.add_argument("--limit", type=int, default=10, help="Máximo de pares a evaluar")
    parser.add_argument(
        "--no-token-guard",
        action="store_true",
        help="Desactiva filtro anti falsos positivos por solapamiento de tokens",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Ejecuta merges reales (UPDATE) en vez de solo preview",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirmación requerida cuando usas --apply",
    )
    parser.add_argument(
        "--merged-by",
        default=os.getenv("API_KEY_USER_ID") or os.getenv("USER") or "script",
        help="Identificador del actor para auditoría (default env/API_KEY_USER_ID)",
    )
    parser.add_argument(
        "--memo",
        default=None,
        help="Texto libre para auditoría (se agrega a log_code_version)",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=1,
        help="Número máximo de tandas a ejecutar (default 1). Útil para 'limpiar hasta vaciar'.",
    )

    args = parser.parse_args()

    project_id: str = args.project
    threshold: float = float(args.threshold)
    limit: int = int(args.limit)

    if args.apply and not args.yes:
        print("ERROR: para ejecutar UPDATEs debes pasar --apply --yes")
        return 2

    max_batches = int(args.max_batches or 1)
    if max_batches < 1:
        max_batches = 1

    memo = args.memo
    if args.apply and (memo is None or not str(memo).strip()):
        memo = f"auto-merge batch {date.today().isoformat()}"

    conn = get_pg_connection()
    try:
        mode = "APPLY" if args.apply else "PREVIEW"
        print(f"mode={mode} project={project_id} threshold={threshold} limit={limit} merged_by={args.merged_by}")
        if memo:
            print(f"memo={memo}")

        grand_preview_move = 0
        grand_preview_dedupe = 0
        grand_preview_merge = 0
        grand_applied = 0

        for batch_index in range(1, max_batches + 1):
            pairs = _build_pairs(
                conn,
                project_id=project_id,
                threshold=threshold,
                limit=limit,
                token_guard=(not args.no_token_guard),
            )

            if not pairs:
                if batch_index == 1:
                    print(
                        f"No se encontraron pares (project={project_id}, threshold={threshold}, limit={limit}). "
                        "Tip: prueba con --threshold 0.72 o --no-token-guard."
                    )
                else:
                    print(f"Batch {batch_index:02d}: no quedan pares. Stop.")
                break

            total_preview_move = 0
            total_preview_dedupe = 0
            total_preview_merge = 0
            total_applied = 0

            print("---")
            print(f"Batch {batch_index:02d}/{max_batches:02d}")

            for idx, p in enumerate(pairs, start=1):
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

                total_preview_move += would_move
                total_preview_dedupe += would_dedupe
                total_preview_merge += would_merge

                sim_txt = f"sim={similarity}" if similarity is not None else ""
                print(
                    f"{idx:02d}. {source}  ->  {target}  {sim_txt}\n"
                    f"    preview: would_move={would_move} would_dedupe={would_dedupe} would_merge={would_merge}"
                )

                if args.apply:
                    if would_merge <= 0:
                        print("    apply: skipped (no-op)")
                        continue

                    result = _apply_merge_by_code_sql(
                        conn,
                        project_id=project_id,
                        source_codigo=source,
                        target_codigo=target,
                        merged_by=args.merged_by,
                    )
                    total_applied += int(result.get("affected") or 0)
                    print(
                        f"    apply: moved={result.get('moved')} deduped={result.get('deduped')} affected={result.get('affected')}"
                    )

            print(
                f"Batch {batch_index:02d} preview: would_move={total_preview_move} would_dedupe={total_preview_dedupe} would_merge={total_preview_merge}"
            )
            if args.apply:
                print(f"Batch {batch_index:02d} applied: affected={total_applied}")

            grand_preview_move += total_preview_move
            grand_preview_dedupe += total_preview_dedupe
            grand_preview_merge += total_preview_merge
            grand_applied += total_applied

            # Si en preview ya no había trabajo, no seguimos.
            if total_preview_merge <= 0:
                print(f"Batch {batch_index:02d}: no-op. Stop.")
                break

        print("---")
        print(
            f"TOTAL preview (acumulado): would_move={grand_preview_move} would_dedupe={grand_preview_dedupe} would_merge={grand_preview_merge}"
        )
        if args.apply:
            print(f"TOTAL applied (acumulado): affected={grand_applied}")
        print("Hecho.")
        return 0

    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
