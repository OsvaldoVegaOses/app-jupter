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
from typing import List, Dict, Any, Tuple

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
import psycopg2

load_dotenv()


def get_pg_connection():
    """Crea conexión a PostgreSQL."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "jupter"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    )


def ensure_fuzzystrmatch(conn) -> bool:
    """Habilita la extensión fuzzystrmatch si no existe."""
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;")
        conn.commit()
        return True
    except Exception as e:
        print(f"⚠️ No se pudo habilitar fuzzystrmatch: {e}")
        return False


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
    # Convertir threshold (0-1) a distancia máxima de Levenshtein
    # Para códigos cortos (~15 chars), threshold 0.80 ≈ max 3 ediciones
    max_distance = int((1 - threshold) * 15)  # Aproximación
    
    sql = """
    WITH unique_codes AS (
        SELECT DISTINCT codigo
        FROM codigos_candidatos
        WHERE project_id = %s AND estado IN ('pendiente', 'validado')
    )
    SELECT 
        c1.codigo AS code1,
        c2.codigo AS code2,
        levenshtein(LOWER(c1.codigo), LOWER(c2.codigo)) AS distance,
        GREATEST(LENGTH(c1.codigo), LENGTH(c2.codigo)) AS max_len,
        1.0 - (levenshtein(LOWER(c1.codigo), LOWER(c2.codigo))::float / 
               GREATEST(LENGTH(c1.codigo), LENGTH(c2.codigo))::float) AS similarity
    FROM unique_codes c1, unique_codes c2
    WHERE c1.codigo < c2.codigo  -- Evitar duplicados y auto-comparación
      AND levenshtein(LOWER(c1.codigo), LOWER(c2.codigo)) <= %s
      AND levenshtein(LOWER(c1.codigo), LOWER(c2.codigo)) > 0  -- No idénticos
    ORDER BY similarity DESC
    LIMIT %s
    """
    
    with conn.cursor() as cur:
        cur.execute(sql, (project_id, max_distance, limit))
        rows = cur.fetchall()
    
    return [
        {
            "code1": row[0],
            "code2": row[1],
            "distance": row[2],
            "max_len": row[3],
            "similarity": round(row[4], 3),
        }
        for row in rows
        if row[4] >= threshold  # Filtrar por threshold real
    ]


def find_similar_open_codes(
    conn,
    project_id: str,
    threshold: float = 0.80,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Encuentra pares de códigos abiertos (definitivos) similares.
    """
    max_distance = int((1 - threshold) * 15)
    
    sql = """
    WITH unique_codes AS (
        SELECT DISTINCT codigo
        FROM analisis_codigos_abiertos
        WHERE project_id = %s
    )
    SELECT 
        c1.codigo AS code1,
        c2.codigo AS code2,
        levenshtein(LOWER(c1.codigo), LOWER(c2.codigo)) AS distance,
        GREATEST(LENGTH(c1.codigo), LENGTH(c2.codigo)) AS max_len,
        1.0 - (levenshtein(LOWER(c1.codigo), LOWER(c2.codigo))::float / 
               GREATEST(LENGTH(c1.codigo), LENGTH(c2.codigo))::float) AS similarity
    FROM unique_codes c1, unique_codes c2
    WHERE c1.codigo < c2.codigo
      AND levenshtein(LOWER(c1.codigo), LOWER(c2.codigo)) <= %s
      AND levenshtein(LOWER(c1.codigo), LOWER(c2.codigo)) > 0
    ORDER BY similarity DESC
    LIMIT %s
    """
    
    with conn.cursor() as cur:
        cur.execute(sql, (project_id, max_distance, limit))
        rows = cur.fetchall()
    
    return [
        {
            "code1": row[0],
            "code2": row[1],
            "distance": row[2],
            "max_len": row[3],
            "similarity": round(row[4], 3),
        }
        for row in rows
        if row[4] >= threshold
    ]


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
    
    # Habilitar extensión
    if not ensure_fuzzystrmatch(conn):
        print("❌ Error: No se pudo habilitar fuzzystrmatch")
        sys.exit(1)
    
    # Buscar duplicados en candidatos
    print("📋 Códigos candidatos duplicados:")
    candidates = find_similar_candidates(conn, args.project, args.threshold, args.limit)
    if candidates:
        for pair in candidates:
            print(f"   • '{pair['code1']}' ↔ '{pair['code2']}' ({pair['similarity']:.0%})")
    else:
        print("   ✅ No se encontraron duplicados")
    
    print()
    
    # Buscar duplicados en códigos abiertos
    print("📊 Códigos abiertos (definitivos) duplicados:")
    open_codes = find_similar_open_codes(conn, args.project, args.threshold, args.limit)
    if open_codes:
        for pair in open_codes:
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
