import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

import structlog
from app.settings import load_settings
from app.clients import build_service_clients
from app.embeddings import embed_batch

logger = structlog.get_logger()

def remap_ghost_codes():
    settings = load_settings()
    clients = build_service_clients(settings)
    
    logger.info("remap.start")
    
    try:
        # 1. Fetch ghost codes
        query_ghosts = """
        SELECT project_id, fragmento_id, codigo, archivo, cita, fuente
        FROM entrevista_codigos
        WHERE fragmento_id LIKE '%#auto#%'
        """
        
        with clients.postgres.cursor() as cur:
            cur.execute(query_ghosts)
            ghosts = cur.fetchall()
            
        logger.info("remap.found_ghosts", count=len(ghosts))
        
        if not ghosts:
            return

        updates = []
        
        for row in ghosts:
            project_id, old_id, codigo, archivo, cita, fuente = row
            
            if not cita or len(cita) < 10:
                logger.warning("remap.skip_short_quote", id=old_id)
                continue
                
            # 2. Vectorize quote
            vectors = embed_batch(clients.aoai, settings.azure.deployment_embed, [cita])
            if not vectors:
                continue
            vector = vectors[0]

            # 3. Search Qdrant
            # Filter by archivo to ensure we find the fragment in the correct document
            search_result = clients.qdrant.search(
                collection_name=settings.qdrant.collection,
                query_vector=vector,
                limit=1,
                query_filter={
                    "must": [
                        {"key": "archivo", "match": {"value": archivo}}
                    ]
                }
            )
            
            if not search_result:
                logger.warning("remap.no_match", id=old_id, archivo=archivo)
                continue
                
            best = search_result[0]
            if best.score > 0.92:
                real_id = best.id
                logger.info("remap.match_found", old=old_id, new=real_id, score=best.score)
                updates.append((real_id, old_id))
            else:
                 logger.warning("remap.low_score", id=old_id, best_score=best.score, cita_preview=cita[:50])

        # 4. Apply updates
        if updates:
            with clients.postgres.cursor() as cur:
                logger.info("remap.applying_updates", count=len(updates))
                # Update Postgres
                for real_id, old_id in updates:
                    # We use ON CONFLICT DO NOTHING just in case the real relationship already exists manually
                    # But here we are updating the ID. If the new ID already exists for this code, it might duplicate
                    # primary key (project_id, fragmento_id, codigo).
                    # So we should delete the old ghost and ensure the new one exists.
                    # Or simpler: UPDATE IGNORE logic.
                     
                    # Attempt update; if it fails due to PK constraint, it means the code exists on the real fragment already.
                    # In that case, we should just delete the ghost.
                    
                    try:
                        cur.execute("""
                            UPDATE entrevista_codigos 
                            SET fragmento_id = %s 
                            WHERE fragmento_id = %s
                        """, (real_id, old_id))
                    except Exception as e:
                        clients.postgres.rollback()
                        logger.info("remap.conflict_deleting_ghost", old=old_id, reason=str(e))
                        # Delete the ghost since the real one likely exists
                        with clients.postgres.cursor() as del_cur:
                             del_cur.execute("DELETE FROM entrevista_codigos WHERE fragmento_id = %s", (old_id,))
                        clients.postgres.commit()
                    else:
                        clients.postgres.commit()
            
            # Neo4j update would be needed if Neo4j was consistent with Postgres, 
            # but usually we handle Neo4j Sync separately. 
            # For now, let's assume re-running 'main.py neo4j sync' or similar would fix it,
            # or we can update directly.
            
            # Let's clean up Neo4j relations from the ghost node.
            # MATCH (c:Codigo)-[r]->(f:Fragmento {id: old_id}) DELETE r
            # This is complex because 'f' might not exist as a node if it was a ghost ID? 
            # Actually, ingestion creates nodes for valid fragments. 
            # Ghost components in Neo4j:
            # - Analysis creates (c:Codigo) nodes and connects them to (f:Fragmento).
            # - If f:Fragmento doesn't exist, it might create it or fail depending on logic.
            # Given we are not sure about Neo4j state for ghosts, fixing Postgres is the source of truth.
            
            logger.info("remap.complete")

    except Exception as e:
        logger.exception("remap.failed", error=str(e))
    finally:
        clients.close()

if __name__ == "__main__":
    remap_ghost_codes()
