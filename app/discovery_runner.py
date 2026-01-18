"""DiscoveryRunner: ejecuta iteraciones de discovery por concepto y persiste métricas.

MVP pensado para cerrar el flujo end-to-end:
- Itera conceptos × entrevistas (fase per_interview) y luego fase global.
- Ejecuta KNN en Qdrant por query de concepto (sin dependencias adicionales).
- Calcula overlap simple (Jaccard) entre sets de fragmento_id por iteración.
- Calcula landing_rate REAL contra códigos axiales (analisis_codigos_abiertos).
- Persiste cada iteración en discovery_runs vía insert_discovery_run.

Sprint 29 - Enero 2026
- Conectado a calculate_landing_rate (validación axial real)
- Retry con backoff en embeddings/search
- Límites configurables (max_interviews, iterations per interview)
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Sequence, Tuple, Any

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.clients import ServiceClients
from app.postgres_block import (
    insert_discovery_run,
    list_interviews_summary,
    calculate_landing_rate,  # NUEVO: Landing rate real
)
from app.settings import AppSettings

_logger = structlog.get_logger()

# ============================================================================
# Configuración de robustez
# ============================================================================

AUTO_NEGATIVES = ["conversacion_informal", "logistica_entrevista", "muletilla"]
DEFAULT_TOP_K = 8
SCORE_THRESHOLD = 0.3

# Límites por defecto
DEFAULT_MAX_INTERVIEWS = 10
DEFAULT_PER_INTERVIEW_ITERS = 4
DEFAULT_GLOBAL_ITERS = 3

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1.5
TIMEOUT_EMBEDDING = 30.0


# ============================================================================
# Funciones auxiliares
# ============================================================================

def _compute_overlap(prev_ids: List[str], current_ids: List[str]) -> float:
    """Jaccard simple entre iteraciones."""
    if not prev_ids or not current_ids:
        return 0.0
    prev_set = set(prev_ids)
    curr_set = set(current_ids)
    inter = len(prev_set & curr_set)
    union = len(prev_set | curr_set)
    return round(inter / union, 4) if union else 0.0


def _embed_query_with_retry(
    clients: ServiceClients,
    settings: AppSettings,
    text: str,
    max_retries: int = MAX_RETRIES,
) -> Tuple[bool, List[float]]:
    """
    Embedding con retry y manejo de errores.
    
    Returns:
        (success, embedding_vector_or_empty)
    """
    for attempt in range(max_retries + 1):
        try:
            response = clients.aoai.embeddings.create(
                model=settings.azure.deployment_embed,
                input=text,
                timeout=TIMEOUT_EMBEDDING,
            )
            return (True, list(response.data[0].embedding))
        
        except Exception as e:
            _logger.warning(
                "discovery.embed.retry",
                attempt=attempt,
                error=str(e),
            )
            if attempt < max_retries:
                import time
                time.sleep(RETRY_BACKOFF_BASE * (2 ** attempt))
            else:
                _logger.error("discovery.embed.failed", error=str(e))
                return (False, [])
    
    return (False, [])


def _search_qdrant_with_retry(
    client: QdrantClient,
    collection: str,
    vector: Sequence[float],
    project_id: str,
    archivo: Optional[str],
    limit: int = DEFAULT_TOP_K,
    max_retries: int = MAX_RETRIES,
) -> Tuple[bool, List[Tuple[str, float, Dict]]]:
    """
    KNN en Qdrant con retry y manejo de errores.
    
    Returns:
        (success, list_of_hits)
    """
    must: List[FieldCondition] = [FieldCondition(key="project_id", match=MatchValue(value=project_id))]
    if archivo:
        must.append(FieldCondition(key="archivo", match=MatchValue(value=archivo)))
    query_filter = Filter(must=must)  # type: ignore[arg-type]
    
    for attempt in range(max_retries + 1):
        try:
            results = client.search(
                collection_name=collection,
                query_vector=list(vector),
                limit=limit,
                score_threshold=SCORE_THRESHOLD,
                query_filter=query_filter,
                timeout=30,
            )
            parsed: List[Tuple[str, float, Dict]] = []
            for hit in results:
                frag_id = getattr(hit, "id", None)
                payload = getattr(hit, "payload", {}) or {}
                parsed.append((str(frag_id), float(hit.score or 0.0), payload))
            return (True, parsed)
        
        except Exception as e:
            _logger.warning(
                "discovery.search.retry",
                attempt=attempt,
                error=str(e),
            )
            if attempt < max_retries:
                import time
                time.sleep(RETRY_BACKOFF_BASE * (2 ** attempt))
            else:
                _logger.error("discovery.search.failed", error=str(e))
                return (False, [])
    
    return (False, [])


def _iter_patterns(concepto: str, iter_index: int) -> Tuple[str, List[str], List[str]]:
    """Devuelve (query_text, positivos, negativos) según patrón de refinamiento."""
    if iter_index == 0:
        return concepto, [concepto], []
    if iter_index == 1:
        return f"{concepto} contexto comunitario", [concepto], AUTO_NEGATIVES
    if iter_index == 2:
        return f"{concepto} AND evidencia concreta", [concepto], AUTO_NEGATIVES
    return f"{concepto} variaciones", [concepto], AUTO_NEGATIVES


# ============================================================================
# Función principal
# ============================================================================

async def run_discovery_iterations(
    *,
    project_id: str,
    concepts: List[str],
    clients: ServiceClients,
    settings: AppSettings,
    max_interviews: int = DEFAULT_MAX_INTERVIEWS,  # NUEVO: límite configurable
    per_interview_iters: int = DEFAULT_PER_INTERVIEW_ITERS,
    global_iters: int = DEFAULT_GLOBAL_ITERS,
    top_k: int = DEFAULT_TOP_K,
    use_real_landing_rate: bool = True,  # NUEVO: usar validación axial real
) -> Dict[str, Any]:
    """
    Ejecuta discovery iterativo y persiste métricas en discovery_runs.
    
    Args:
        project_id: ID del proyecto
        concepts: Lista de conceptos a explorar
        clients: ServiceClients con conexiones
        settings: AppSettings con configuración
        max_interviews: Máximo de entrevistas a procesar
        per_interview_iters: Iteraciones por entrevista
        global_iters: Iteraciones globales
        top_k: Número de resultados por búsqueda
        use_real_landing_rate: Si True, calcula landing rate contra códigos axiales reales
    
    Returns:
        Dict con runs registrados, métricas, y errores
    """
    runs: List[Dict[str, Any]] = []
    errors: List[str] = []
    total_fragments_found: List[str] = []
    # Mantener una muestra de fragmentos únicos para post-run (reporte/códigos)
    best_fragments: Dict[str, Dict[str, Any]] = {}
    
    _logger.info(
        "discovery.start",
        project=project_id,
        concepts=concepts,
        max_interviews=max_interviews,
        per_interview_iters=per_interview_iters,
        global_iters=global_iters,
    )

    # Fase 1: por entrevista (respeta límite)
    all_interviews = list_interviews_summary(clients.postgres, project_id, limit=200)
    interviews = all_interviews[:max_interviews]  # Aplicar límite
    
    _logger.info(
        "discovery.interviews_limited",
        total_available=len(all_interviews),
        processing=len(interviews),
    )
    
    for concepto in concepts:
        for interview in interviews:
            archivo = interview.get("archivo")
            prev_ids: List[str] = []
            
            for iter_idx in range(per_interview_iters):
                query_text, pos, neg = _iter_patterns(concepto, iter_idx)
                
                # Embedding con retry
                embed_success, query_vec = _embed_query_with_retry(
                    clients, settings, query_text
                )
                if not embed_success:
                    errors.append(f"Embedding failed: {concepto}/{archivo}/iter{iter_idx}")
                    continue
                
                # Search con retry
                search_success, hits = _search_qdrant_with_retry(
                    clients.qdrant,
                    settings.qdrant.collection,
                    query_vec,
                    project_id,
                    archivo,
                    limit=top_k,
                )
                if not search_success:
                    errors.append(f"Search failed: {concepto}/{archivo}/iter{iter_idx}")
                    continue
                
                frag_ids = [h[0] for h in hits]
                total_fragments_found.extend(frag_ids)
                # Acumular mejores fragmentos por score
                for frag_id, score, payload in hits:
                    existing = best_fragments.get(frag_id)
                    if (existing is None) or (float(score) > float(existing.get("score", 0.0))):
                        best_fragments[frag_id] = {
                            "fragmento_id": str(frag_id),
                            "score": float(score),
                            "archivo": payload.get("archivo"),
                            "fragmento": (payload.get("fragmento") or "")[:600],
                        }
                overlap = _compute_overlap(prev_ids, frag_ids)
                
                # LANDING RATE REAL vs PROXY
                if use_real_landing_rate and frag_ids:
                    lr_result = calculate_landing_rate(
                        clients.postgres, project_id, frag_ids
                    )
                    landing_rate = lr_result["landing_rate"] / 100.0  # Normalizar a 0-1
                else:
                    # Proxy: porcentaje de hits que ya aparecieron
                    prev_set = set(prev_ids)
                    hits_count = len([fid for fid in frag_ids if fid in prev_set])
                    landing_rate = round(hits_count / len(frag_ids), 4) if frag_ids else 0.0
                
                prev_ids = frag_ids

                record = insert_discovery_run(
                    clients.postgres,
                    project=project_id,
                    concepto=concepto,
                    scope="per_interview",
                    iter_index=iter_idx,
                    archivo=archivo,
                    query=query_text,
                    positivos=pos,
                    negativos=neg,
                    overlap=overlap,
                    landing_rate=landing_rate,
                    top_fragments=[
                        {
                            "fragmento_id": h[0],
                            "score": h[1],
                            "archivo": h[2].get("archivo"),
                            "fragmento": (h[2].get("fragmento") or "")[:200],
                        }
                        for h in hits
                    ],
                    memo=f"Iter {iter_idx} {concepto} {archivo} overlap={overlap:.2f} landing={landing_rate:.2f}",
                )
                runs.append({
                    "id": record.get("id"),
                    "overlap": overlap,
                    "landing_rate": landing_rate,
                    "scope": "per_interview",
                    "concepto": concepto,
                    "iter": iter_idx,
                    "archivo": archivo,
                    "fragments_count": len(frag_ids),
                })

    # Fase 2: global
    for concepto in concepts:
        prev_ids: List[str] = []
        for iter_idx in range(global_iters):
            query_text, pos, neg = _iter_patterns(concepto, iter_idx)
            
            embed_success, query_vec = _embed_query_with_retry(
                clients, settings, query_text
            )
            if not embed_success:
                errors.append(f"Embedding failed: {concepto}/global/iter{iter_idx}")
                continue
            
            search_success, hits = _search_qdrant_with_retry(
                clients.qdrant,
                settings.qdrant.collection,
                query_vec,
                project_id,
                archivo=None,
                limit=top_k,
            )
            if not search_success:
                errors.append(f"Search failed: {concepto}/global/iter{iter_idx}")
                continue
            
            frag_ids = [h[0] for h in hits]
            total_fragments_found.extend(frag_ids)
            for frag_id, score, payload in hits:
                existing = best_fragments.get(frag_id)
                if (existing is None) or (float(score) > float(existing.get("score", 0.0))):
                    best_fragments[frag_id] = {
                        "fragmento_id": str(frag_id),
                        "score": float(score),
                        "archivo": payload.get("archivo"),
                        "fragmento": (payload.get("fragmento") or "")[:600],
                    }
            overlap = _compute_overlap(prev_ids, frag_ids)
            
            # LANDING RATE REAL
            if use_real_landing_rate and frag_ids:
                lr_result = calculate_landing_rate(
                    clients.postgres, project_id, frag_ids
                )
                landing_rate = lr_result["landing_rate"] / 100.0
            else:
                prev_set = set(prev_ids)
                hits_count = len([fid for fid in frag_ids if fid in prev_set])
                landing_rate = round(hits_count / len(frag_ids), 4) if frag_ids else 0.0
            
            prev_ids = frag_ids

            record = insert_discovery_run(
                clients.postgres,
                project=project_id,
                concepto=concepto,
                scope="global",
                iter_index=iter_idx,
                archivo=None,
                query=query_text,
                positivos=pos,
                negativos=neg,
                overlap=overlap,
                landing_rate=landing_rate,
                top_fragments=[
                    {
                        "fragmento_id": h[0],
                        "score": h[1],
                        "archivo": h[2].get("archivo"),
                        "fragmento": (h[2].get("fragmento") or "")[:200],
                    }
                    for h in hits
                ],
                memo=f"Iter {iter_idx} {concepto} global overlap={overlap:.2f} landing={landing_rate:.2f}",
            )
            runs.append({
                "id": record.get("id"),
                "overlap": overlap,
                "landing_rate": landing_rate,
                "scope": "global",
                "concepto": concepto,
                "iter": iter_idx,
                "archivo": None,
                "fragments_count": len(frag_ids),
            })
    
    # Calcular landing rate final sobre todos los fragmentos únicos
    unique_fragments = list(set(total_fragments_found))
    final_landing_rate = None
    if use_real_landing_rate and unique_fragments:
        lr_final = calculate_landing_rate(
            clients.postgres, project_id, unique_fragments
        )
        final_landing_rate = lr_final
    
    _logger.info(
        "discovery.complete",
        runs_count=len(runs),
        errors_count=len(errors),
        unique_fragments=len(unique_fragments),
        final_landing_rate=final_landing_rate,
    )

    return {
        "runs": runs,
        "errors": errors,
        "unique_fragments_count": len(unique_fragments),
        "final_landing_rate": final_landing_rate,
        "interviews_processed": len(interviews),
        "interviews_available": len(all_interviews),
        "config": {
            "max_interviews": max_interviews,
            "per_interview_iters": per_interview_iters,
            "global_iters": global_iters,
            "top_k": top_k,
            "score_threshold": SCORE_THRESHOLD,
        },
        "sample_fragments": sorted(
            best_fragments.values(),
            key=lambda x: float(x.get("score", 0.0)),
            reverse=True,
        )[:12],
    }

