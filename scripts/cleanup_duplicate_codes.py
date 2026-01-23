#!/usr/bin/env python
"""
Script de limpieza Post-Hoc de códigos duplicados.

Este script detecta y reporta códigos similares que ya existen en la base de datos,
permitiendo al investigador fusionarlos manualmente o automáticamente.

Uso:
    python scripts/cleanup_duplicate_codes.py --project prueba-99 --threshold 0.80 --dry-run
    
Opciones:
    --project: ID del proyecto
    --threshold: Umbral de similitud (0.0 - 1.0, default 0.80)
    --dry-run: Solo reportar, no modificar datos
    --auto-merge: Fusionar automáticamente (requiere confirmación)
"""

from __future__ import annotations

import argparse
import os
import sys
import unicodedata
from typing import List, Dict, Any, Tuple

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
import psycopg2
from rapidfuzz.distance import Levenshtein

load_dotenv(os.getenv("APP_ENV_FILE", ".env"))


def get_pg_connection():
    """Crea conexión a PostgreSQL."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST") or os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT") or os.getenv("PGPORT", "5432")),
        dbname=os.getenv("POSTGRES_DB") or os.getenv("PGDATABASE", "jupter"),
        user=os.getenv("POSTGRES_USER") or os.getenv("PGUSER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD") or os.getenv("PGPASSWORD", "postgres"),
        sslmode=os.getenv("POSTGRES_SSLMODE") or os.getenv("PGSSLMODE", "prefer"),
    )


def _normalize_text(value: str) -> str:
    """Normaliza texto: trim, lower y remueve acentos (Unicode)."""
    if value is None:
        return ""
    trimmed = value.strip().lower()
    normalized = unicodedata.normalize("NFKD", trimmed)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Calcula distancia de Levenshtein usando RapidFuzz (compatible con Azure)."""
    return Levenshtein.distance(s1, s2)


def _find_similar_pairs(
    codes: List[str],
    threshold: float = 0.80,
    limit: int = 100,
    include_exact: bool = True,
) -> List[Dict[str, Any]]:
    """
    Encuentra pares de códigos similares usando RapidFuzz (Levenshtein).
    Si include_exact=True, incluye duplicados exactos (distancia=0).
    """
    normalized_codes = [_normalize_text(c) for c in codes if c]
    rep_by_norm: Dict[str, str] = {}
    for original, norm in zip(codes, normalized_codes):
        if original:
            rep_by_norm.setdefault(norm, original)

    duplicates: List[Dict[str, Any]] = []

    if include_exact:
        counts: Dict[str, int] = {}
        variants_by_norm: Dict[str, set[str]] = {}
        for original, norm in zip(codes, normalized_codes):
            counts[norm] = counts.get(norm, 0) + 1
            variants_by_norm.setdefault(norm, set()).add(original.strip())
        for norm, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
            if count <= 1:
                continue
            if len(variants_by_norm.get(norm, set())) <= 1:
                continue
            duplicates.append({
                "code1": rep_by_norm.get(norm, norm),
                "code2": rep_by_norm.get(norm, norm),
                "distance": 0,
                "max_len": len(norm),
                "similarity": 1.0,
                "is_exact_duplicate": True,
                "duplicate_count": count,
            })
            if len(duplicates) >= limit:
                return duplicates[:limit]

    unique_codes = list(set(normalized_codes))

    for i, c1 in enumerate(unique_codes):
        for c2 in unique_codes[i + 1:]:
            max_len = max(len(c1), len(c2))
            if max_len == 0:
                continue
            # Pre-filter por diferencia de longitud
            if abs(len(c1) - len(c2)) > int((1 - threshold) * max_len):
                continue

            distance = _levenshtein_distance(c1, c2)
            if distance == 0:
                continue
            similarity = 1 - (distance / max_len)

            if similarity >= threshold:
                duplicates.append({
                    "code1": rep_by_norm.get(c1, c1),
                    "code2": rep_by_norm.get(c2, c2),
                    "distance": distance,
                    "max_len": max_len,
                    "similarity": round(similarity, 3),
                    "is_exact_duplicate": False,
                })

                if len(duplicates) >= limit:
                    break
        if len(duplicates) >= limit:
            break

    duplicates.sort(key=lambda x: x["similarity"], reverse=True)
    return duplicates[:limit]


def find_similar_candidates(
    conn,
    project_id: str,
    threshold: float = 0.80,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Encuentra pares de códigos candidatos similares usando Levenshtein.
    
    Args:
        conn: Conexión PostgreSQL
        project_id: ID del proyecto
        threshold: Umbral de similitud (0.0 - 1.0)
        limit: Máximo de pares a retornar
        
    Returns:
        Lista de pares similares con sus scores
    """
    sql = """
    SELECT DISTINCT codigo
    FROM codigos_candidatos
    WHERE project_id = %s AND estado IN ('pendiente', 'validado')
    """
    with conn.cursor() as cur:
        cur.execute(sql, (project_id,))
        rows = cur.fetchall()

    codes = [row[0] for row in rows if row[0]]
    return _find_similar_pairs(codes, threshold=threshold, limit=limit)


def find_similar_open_codes(
    conn,
    project_id: str,
    threshold: float = 0.80,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Encuentra pares de códigos abiertos (definitivos) similares.
    """
    sql = """
    SELECT DISTINCT codigo
    FROM analisis_codigos_abiertos
    WHERE project_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (project_id,))
        rows = cur.fetchall()

    codes = [row[0] for row in rows if row[0]]
    return _find_similar_pairs(codes, threshold=threshold, limit=limit)


def get_duplicate_stats(conn, project_id: str, threshold: float = 0.80) -> Dict[str, Any]:
    """
    Obtiene estadísticas de duplicados potenciales.
    """
    candidates = find_similar_candidates(conn, project_id, threshold)
    open_codes = find_similar_open_codes(conn, project_id, threshold)
    
    return {
        "project_id": project_id,
        "threshold": threshold,
        "candidates_duplicates": len(candidates),
        "open_codes_duplicates": len(open_codes),
        "total_pairs": len(candidates) + len(open_codes),
        "candidate_pairs": candidates[:20],  # Top 20
        "open_code_pairs": open_codes[:20],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Detecta y reporta códigos duplicados en el proyecto."
    )
    parser.add_argument("--project", required=True, help="ID del proyecto")
    parser.add_argument("--threshold", type=float, default=0.80, 
                       help="Umbral de similitud (0.0 - 1.0)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Solo reportar, no modificar")
    parser.add_argument("--limit", type=int, default=50,
                       help="Máximo de pares a mostrar")
    
    args = parser.parse_args()
    
    print(f"\n🔍 Analizando duplicados en proyecto: {args.project}")
    print(f"   Umbral de similitud: {args.threshold:.0%}")
    print(f"   Modo: {'DRY-RUN (solo lectura)' if args.dry_run else 'ACTIVO'}")
    print()
    
    conn = get_pg_connection()
    
    # RapidFuzz no requiere extensiones en PostgreSQL
    
    # Buscar duplicados en candidatos
    print("📋 Códigos candidatos duplicados:")
    candidates = find_similar_candidates(conn, args.project, args.threshold, args.limit)
    if candidates:
        for pair in candidates:
            if pair.get("is_exact_duplicate"):
                print(
                    f"   • '{pair['code1']}' ↔ '{pair['code2']}' "
                    f"(EXACTO x{pair.get('duplicate_count', 2)})"
                )
            else:
                print(f"   • '{pair['code1']}' ↔ '{pair['code2']}' ({pair['similarity']:.0%})")
    else:
        print("   ✅ No se encontraron duplicados")
    
    print()
    
    # Buscar duplicados en códigos abiertos
    print("📊 Códigos abiertos (definitivos) duplicados:")
    open_codes = find_similar_open_codes(conn, args.project, args.threshold, args.limit)
    if open_codes:
        for pair in open_codes:
            if pair.get("is_exact_duplicate"):
                print(
                    f"   • '{pair['code1']}' ↔ '{pair['code2']}' "
                    f"(EXACTO x{pair.get('duplicate_count', 2)})"
                )
            else:
                print(f"   • '{pair['code1']}' ↔ '{pair['code2']}' ({pair['similarity']:.0%})")
    else:
        print("   ✅ No se encontraron duplicados")
    
    print()
    print(f"📈 Resumen:")
    print(f"   - Pares candidatos: {len(candidates)}")
    print(f"   - Pares definitivos: {len(open_codes)}")
    print(f"   - Total: {len(candidates) + len(open_codes)}")
    
    if not args.dry_run and (candidates or open_codes):
        print()
        print("💡 Para fusionar, usa la herramienta de fusión en la Bandeja de Candidatos")
        print("   o ejecuta manualmente las queries de UPDATE en PostgreSQL.")
    
    conn.close()


if __name__ == "__main__":
    main()
