"""
Migration 012: Add 'hipotesis' state for Theoretical Sampling support.

This migration implements Grounded Theory's theoretical sampling concept:
- New state 'hipotesis' for codes without empirical evidence
- Tracking fields for sampling workflow
- Reclassification of existing link_prediction candidates

Fecha: 2026-01-18
Sprint: 32 - Validación Metodológica
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.settings import load_settings
from app.clients import build_service_clients
import structlog

log = structlog.get_logger()


def apply_migration(project_id: str = "jd-007") -> dict:
    """
    Apply migration 012: Add hipotesis state and related fields.
    
    Args:
        project_id: Project to migrate (default: jd-007)
        
    Returns:
        Dict with migration results
    """
    settings = load_settings()
    clients = build_service_clients(settings)
    pg = clients.postgres
    
    results = {
        "columns_added": [],
        "candidates_reclassified": 0,
        "index_created": False,
    }
    
    try:
        cur = pg.cursor()
        
        # 1. Add new columns if they don't exist
        new_columns = [
            ("requiere_muestreo", "BOOLEAN DEFAULT FALSE"),
            ("muestreo_notas", "TEXT"),
            ("codigo_origen_hipotesis", "TEXT"),
        ]
        
        for col_name, col_def in new_columns:
            try:
                cur.execute(f"""
                    ALTER TABLE codigos_candidatos 
                    ADD COLUMN IF NOT EXISTS {col_name} {col_def}
                """)
                results["columns_added"].append(col_name)
                log.info("migration.column_added", column=col_name)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    raise
                log.info("migration.column_exists", column=col_name)
        
        pg.commit()
        
        # 2. Reclassify link_prediction candidates without fragmento_id
        cur.execute("""
            UPDATE codigos_candidatos 
            SET estado = 'hipotesis',
                requiere_muestreo = TRUE,
                memo = COALESCE(memo, '') || ' [RECLASIFICADO 2026-01-18: Hipótesis pendiente de muestreo teórico según Grounded Theory]'
            WHERE fuente_origen = 'link_prediction'
              AND (fragmento_id IS NULL OR fragmento_id = '')
              AND estado IN ('validado', 'pendiente')
              AND project_id = %s
            RETURNING id
        """, (project_id,))
        
        reclassified = cur.fetchall()
        results["candidates_reclassified"] = len(reclassified)
        log.info(
            "migration.reclassified",
            count=len(reclassified),
            project=project_id,
        )
        
        pg.commit()
        
        # 3. Create index for hypothesis queries
        try:
            cur.execute("""
                CREATE INDEX IF NOT EXISTS ix_cc_hipotesis 
                ON codigos_candidatos(project_id, estado) 
                WHERE estado = 'hipotesis'
            """)
            results["index_created"] = True
            log.info("migration.index_created", index="ix_cc_hipotesis")
        except Exception as e:
            log.warning("migration.index_error", error=str(e))
        
        pg.commit()
        
        # 4. Verify final state
        cur.execute("""
            SELECT estado, COUNT(*) 
            FROM codigos_candidatos 
            WHERE project_id = %s AND fuente_origen = 'link_prediction'
            GROUP BY estado
        """, (project_id,))
        
        final_stats = {row[0]: row[1] for row in cur.fetchall()}
        results["final_stats"] = final_stats
        
        cur.close()
        
        log.info(
            "migration.complete",
            results=results,
        )
        
        return results
        
    except Exception as e:
        pg.rollback()
        log.error("migration.failed", error=str(e))
        raise
    finally:
        clients.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Apply migration 012: Add hipotesis state for theoretical sampling"
    )
    parser.add_argument(
        "--project",
        default="jd-007",
        help="Project ID to migrate (default: jd-007)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    
    args = parser.parse_args()
    
    if args.dry_run:
        print("=" * 60)
        print("DRY RUN MODE - No changes will be made")
        print("=" * 60)
        
        settings = load_settings()
        clients = build_service_clients(settings)
        cur = clients.postgres.cursor()
        
        cur.execute("""
            SELECT id, codigo, estado, fuente_origen
            FROM codigos_candidatos 
            WHERE fuente_origen = 'link_prediction'
              AND (fragmento_id IS NULL OR fragmento_id = '')
              AND estado IN ('validado', 'pendiente')
              AND project_id = %s
        """, (args.project,))
        
        rows = cur.fetchall()
        print(f"\nCandidates that would be reclassified to 'hipotesis': {len(rows)}")
        for row in rows[:10]:
            print(f"  ID {row[0]}: {row[1]} (current: {row[2]})")
        if len(rows) > 10:
            print(f"  ... and {len(rows) - 10} more")
        
        clients.close()
    else:
        print("=" * 60)
        print(f"Applying migration 012 for project: {args.project}")
        print("=" * 60)
        
        results = apply_migration(args.project)
        
        print("\n✅ Migration complete!")
        print(f"   Columns added: {results['columns_added']}")
        print(f"   Candidates reclassified: {results['candidates_reclassified']}")
        print(f"   Index created: {results['index_created']}")
        print(f"   Final stats: {results.get('final_stats', {})}")
