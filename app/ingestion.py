"""
Pipeline de ingesta de documentos para análisis cualitativo.

Este módulo implementa el flujo completo de ingesta:
1. Lectura de archivos DOCX
2. Fragmentación optimizada para análisis
3. Generación de embeddings via Azure OpenAI
4. Almacenamiento en Qdrant (vectores) y PostgreSQL (metadatos)

Flujo de datos:
    DOCX Files → Fragmentos → Embeddings → Qdrant + PostgreSQL
    
Función principal:
    ingest_documents(): Procesa múltiples archivos en un solo batch
    
Características:
    - Batch processing con progress bar (tqdm)
    - Retry automático para timeouts de Qdrant
    - Detección de quality issues (coherencia, ruido)
    - Logging estructurado para trazabilidad
    
Parámetros clave:
    - batch_size: Tamaño de batch para Qdrant (default: 20, reducido para evitar timeouts)
    - min_chars/max_chars: Control de tamaño de fragmentos
    - min_interviewee_tokens: Filtro de calidad para contenido sustantivo

Example:
    >>> from app.clients import build_service_clients
    >>> from app.settings import load_settings
    >>> from app.ingestion import ingest_documents
    >>> 
    >>> settings = load_settings()
    >>> clients = build_service_clients(settings)
    >>> result = ingest_documents(
    ...     clients, settings,
    ...     files=["entrevista1.docx", "entrevista2.docx"],
    ...     project="mi_proyecto"
    ... )
    >>> print(f"Fragmentos procesados: {result['totals']['fragments']}")

Eventos de logging:
    - ingest.fragment: Fragmento procesado
    - ingest.quality.issue: Problema de calidad detectado
    - qdrant.upsert.success: Vectores insertados exitosamente
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from math import ceil
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

import structlog
from tqdm import tqdm

from .clients import ServiceClients
from .coherence import analyze_fragment, summarize_issue_counts
from .documents import batched, load_fragment_records, make_fragment_id
from .embeddings import embed_batch
from .neo4j_block import ensure_constraints as ensure_neo4j_constraints, merge_fragments
from .postgres_block import ensure_fragment_table, insert_fragments
from .qdrant_block import build_points, ensure_collection, ensure_payload_indexes, upsert
from .settings import AppSettings

_logger = structlog.get_logger()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _mark_fragments_sync_status(pg, fragment_ids: list, synced: bool) -> None:
    """
    Marca fragmentos como sincronizados o pendientes de sincronizar a Neo4j.
    
    Args:
        pg: Conexión PostgreSQL
        fragment_ids: Lista de IDs de fragmentos
        synced: True si ya se sincronizaron a Neo4j
    """
    if not fragment_ids:
        return
    
    try:
        with pg.cursor() as cur:
            cur.execute("""
                UPDATE entrevista_fragmentos
                SET neo4j_synced = %s
                WHERE id = ANY(%s)
            """, (synced, fragment_ids))
        pg.commit()
    except Exception as e:
        # No fallar si la columna no existe aún (migración pendiente)
        pg.rollback()  # CRITICAL: Rollback to clear aborted transaction state
        _logger.debug("mark_sync_status.skip", error=str(e)[:50])


def ingest_documents(
    clients: ServiceClients,
    settings: AppSettings,
    files: Sequence[str | Path],
    batch_size: int = 20,  # Reduced from 64 to prevent Qdrant timeouts
    min_chars: int = 200,
    max_chars: int = 1200,
    min_interviewee_tokens: int = 10,
    metadata: Mapping[str, Mapping[str, Any]] | None = None,
    run_id: Optional[str] = None,
    logger: Optional[structlog.BoundLogger] = None,
    project: Optional[str] = None,
    org_id: Optional[str] = None,
) -> Dict[str, Any]:
    metadata_map = metadata or {}
    log = logger or _logger
    project_id = project or "default"
    from .blob_storage import allow_orgless_tasks
    allow_orgless = allow_orgless_tasks()

    if not org_id and not allow_orgless:
        raise ValueError(
            "org_id is required for ingest_documents in tenant-scoped environments. "
            "Set ALLOW_ORGLESS_TASKS=true for development only."
        )
    
    # Validar que el proyecto existe antes de ingestar
    from .project_state import get_project
    if not get_project(clients.postgres, project_id):
        raise ValueError(
            f"Proyecto '{project_id}' no existe. "
            "Crea el proyecto primero desde el Dashboard antes de ingestar."
        )
    
    if run_id:
        log = log.bind(run_id=run_id)
    log = log.bind(project=project_id)

    ensure_collection(clients.qdrant, settings.qdrant.collection, clients.embed_dims)
    ensure_payload_indexes(clients.qdrant, settings.qdrant.collection)
    ensure_fragment_table(clients.postgres)  # PostgreSQL primero (datos maestros)
    
    # Neo4j es opcional - si falla, continuamos sin él
    neo4j_available = False
    try:
        ensure_neo4j_constraints(clients.neo4j, settings.neo4j.database)
        neo4j_available = True
        log.info("ingest.neo4j.available")
    except Exception as e:
        log.warning(
            "ingest.neo4j.unavailable",
            error=str(e)[:100],
            note="Ingesta continuará sin Neo4j. Sincronizar después con /api/admin/sync-neo4j"
        )


    summaries = []
    issue_counter: Counter[str] = Counter()
    totals: Dict[str, Any] = {
        "files": 0,
        "files_archived": 0,
        "fragments": 0,
        "char_len_zero": 0,
        "duplicate_fragments": 0,
        "flagged_fragments": 0,
        "global_duplicates": 0,
        "interviewer_tokens_filtered": 0,
        "interviewer_tokens_attached": 0,
        "interviewee_tokens_kept": 0,
        "fragments_discarded_low_interviewee": 0,
    }
    global_hashes: set[str] = set()

    for file_path in files:
        path = Path(file_path)

        # Best-effort: archive original DOCX to Azure Blob Storage when configured.
        blob_url: Optional[str] = None
        blob_path: Optional[str] = None
        try:
            from .blob_storage import CONTAINER_INTERVIEWS, tenant_upload_bytes
            import os

            conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
            if conn_str and path.exists() and path.is_file():
                logical_path = f"interviews/{project_id}/{path.name}"
                blob_info = tenant_upload_bytes(
                    org_id=org_id,
                    project_id=project_id,
                    container=CONTAINER_INTERVIEWS,
                    logical_path=logical_path,
                    data=path.read_bytes(),
                    content_type=(
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    ),
                    strict_tenant=True,
                )
                blob_url = blob_info.get("url")
                blob_path = blob_info.get("name")
                if blob_url and blob_path:
                    totals["files_archived"] += 1
                    log.info("ingest.file.archived", file=path.name, blob_path=blob_path)
        except Exception as exc:
            # Do not block ingestion on storage issues.
            log.warning(
                "ingest.file.archive_failed",
                file=path.name,
                error=str(exc)[:200],
            )

        load_result = load_fragment_records(
            path,
            min_chars=min_chars,
            max_chars=max_chars,
            min_interviewee_tokens=min_interviewee_tokens,
        )
        fragments = load_result.fragments
        file_name = path.name
        if not fragments:
            log.warning("ingest.file.empty", file=file_name)
            continue

        log.info("ingest.file.start", file=file_name, fragments=len(fragments))
        file_meta_defaults = metadata_map.get(file_name, {})
        entries = []
        flagged_issue_lists = []
        flagged_preview_limit = 5
        local_hashes: set[str] = set()
        local_duplicates = 0
        char_zero_count = 0
        discarded_fragments = load_result.stats.get("fragments_discarded_low_interviewee", 0)

        for idx, fragment in enumerate(fragments):
            issues = analyze_fragment(fragment.text)
            if issues:
                flagged_issue_lists.append(issues)
                if len(flagged_issue_lists) <= flagged_preview_limit:
                    log.warning(
                        "ingest.fragment.flagged",
                        file=file_name,
                        par_idx=idx,
                        issues=issues,
                        preview=fragment.text[:120].strip(),
                    )
            fragment_len = len(fragment.text)
            if fragment_len == 0:
                char_zero_count += 1

            fragment_sha = sha256_text(fragment.text)
            if fragment_sha in local_hashes:
                local_duplicates += 1
            else:
                local_hashes.add(fragment_sha)
            if fragment_sha in global_hashes:
                totals["global_duplicates"] += 1
            else:
                global_hashes.add(fragment_sha)

            raw_meta = file_meta_defaults.get("metadata") or {}
            metadata_payload: Dict[str, Any]
            if isinstance(raw_meta, dict):
                metadata_payload = dict(raw_meta)
            else:
                metadata_payload = {}

            # Persist archive reference at fragment-level metadata (cheap to query at interview-summary level).
            if blob_url and "blob_url" not in metadata_payload:
                metadata_payload["blob_url"] = blob_url
            if blob_path and "blob_path" not in metadata_payload:
                metadata_payload["blob_path"] = blob_path
            metadata_json = json.dumps(metadata_payload, ensure_ascii=False) if metadata_payload else None

            entries.append(
                {
                    "project_id": project_id,
                    "id": make_fragment_id(file_name, idx),
                    "archivo": file_name,
                    "par_idx": idx,
                    "fragmento": fragment.text,
                    "char_len": fragment_len,
                    "sha": fragment_sha,
                    "speaker": fragment.speaker,
                    "interviewer_tokens": fragment.interviewer_tokens,
                    "interviewee_tokens": fragment.interviewee_tokens,
                    "area_tematica": file_meta_defaults.get("area_tematica"),
                    "actor_principal": file_meta_defaults.get("actor_principal"),
                    "requiere_protocolo_lluvia": file_meta_defaults.get("requiere_protocolo_lluvia"),
                    "codigos_ancla": file_meta_defaults.get("codigos_ancla") or [],
                    "genero": metadata_payload.get("genero"),
                    "periodo": metadata_payload.get("periodo"),
                    "metadata": metadata_payload,
                    "metadata_json": metadata_json,
                }
            )

        total_batches = max(1, ceil(len(entries) / batch_size))
        batch_iterable = batched(entries, batch_size)
        for batch_index, batch in enumerate(
            tqdm(batch_iterable, total=total_batches, desc=f"{file_name}", unit="lotes"),
            start=1,
        ):
            _logger.debug(
                "ingestion.batch_processing",
                batch_index=batch_index,
                batch_size=len(batch),
                project_id=project_id,
                file_name=file_name,
            )
            ids = [item["id"] for item in batch]
            payloads = [
                {
                    "project_id": item["project_id"],
                    "archivo": item["archivo"],
                    "par_idx": item["par_idx"],
                    "fragmento": item["fragmento"],
                    "char_len": item["char_len"],
                    "speaker": item.get("speaker"),
                    "interviewer_tokens": item.get("interviewer_tokens"),
                    "interviewee_tokens": item.get("interviewee_tokens"),
                    "area_tematica": item.get("area_tematica"),
                    "actor_principal": item.get("actor_principal"),
                    "requiere_protocolo_lluvia": item.get("requiere_protocolo_lluvia"),
                    "codigos_ancla": item.get("codigos_ancla"),
                    "genero": item.get("genero"),
                    "periodo": item.get("periodo"),
                    "metadata": item.get("metadata"),
                }
                for item in batch
            ]
            texts = [item["fragmento"] for item in batch]
            vectors = embed_batch(
                clients.aoai,
                settings.azure.deployment_embed,
                texts,
                logger=log,
            )

            if len(vectors) != len(texts):
                raise ValueError(
                    f"Expected {len(texts)} embeddings for batch but received {len(vectors)}"
                )
            for vec in vectors:
                if len(vec) != clients.embed_dims:
                    raise ValueError(
                        f"Embedding dimensionality mismatch: got {len(vec)}, expected {clients.embed_dims}"
                    )

            # PostgreSQL PRIMERO (datos maestros - siempre debe funcionar)
            pg_rows = [
                (
                    item["project_id"],
                    item["id"],
                    item["archivo"],
                    item["par_idx"],
                    item["fragmento"],
                    vector,
                    item["char_len"],
                    item["sha"],
                    item.get("area_tematica"),
                    item.get("actor_principal"),
                    item.get("requiere_protocolo_lluvia"),
                    item.get("metadata"),
                    item.get("speaker"),
                    item.get("interviewer_tokens"),
                    item.get("interviewee_tokens"),
                )
                for item, vector in zip(batch, vectors)
            ]
            try:
                insert_fragments(clients.postgres, pg_rows)
            except Exception as exc:
                log.error(
                    "ingest.pg.insert_failed",
                    file=file_name,
                    batch=batch_index,
                    size=len(batch),
                    error=str(exc),
                )
                raise

            qdrant_points = build_points(ids, payloads, vectors)
            try:
                upsert(
                    clients.qdrant,
                    settings.qdrant.collection,
                    qdrant_points,
                    logger=log,
                )
            except Exception as exc:
                log.error(
                    "ingest.qdrant.upsert_failed",
                    file=file_name,
                    batch=batch_index,
                    size=len(qdrant_points),
                    error=str(exc),
                )
                raise

            # Neo4j OPCIONAL - solo si está disponible
            batch_synced_to_neo4j = False
            if neo4j_available:
                try:
                    neo_rows = [
                        {
                            "project_id": item["project_id"],
                            "id": item["id"],
                            "archivo": item["archivo"],
                            "par_idx": item["par_idx"],
                            "fragmento": item["fragmento"],
                            "char_len": item["char_len"],
                            "speaker": item.get("speaker"),
                            "interviewer_tokens": item.get("interviewer_tokens"),
                            "interviewee_tokens": item.get("interviewee_tokens"),
                            "actor_principal": item.get("actor_principal"),
                            "metadata": item.get("metadata_json"),
                            "genero": item.get("genero"),
                            "periodo": item.get("periodo"),
                        }
                        for item in batch
                    ]
                    merge_fragments(clients.neo4j, settings.neo4j.database, neo_rows)
                    batch_synced_to_neo4j = True
                except Exception as e:
                    log.warning(
                        "ingest.neo4j.batch_failed",
                        batch_start=batch_index,
                        error=str(e)[:80]
                    )
                    neo4j_available = False  # Deshabilitar para siguientes batches
            
            # Marcar fragmentos como sincronizados o pendientes
            fragment_ids = [item["id"] for item in batch]
            _mark_fragments_sync_status(clients.postgres, fragment_ids, batch_synced_to_neo4j)

            log.info(
                "ingest.batch",
                file=file_name,
                batch=batch_index,
                batch_size=len(batch),
                char_len_zero=sum(1 for item in batch if item["char_len"] == 0),
                duplicates_in_batch=len(batch) - len({item["sha"] for item in batch}),
            )

        file_issue_counts = summarize_issue_counts(flagged_issue_lists)
        issue_counter.update(file_issue_counts)

        summary = {
            "file": file_name,
            "fragments": len(entries),
            "blob_url": blob_url,
            "blob_path": blob_path,
            "char_len_zero": char_zero_count,
            "duplicate_fragments": local_duplicates,
            "flagged_fragments": len(flagged_issue_lists),
            "fragments_discarded_low_interviewee": discarded_fragments,
            "interviewer_tokens_filtered": load_result.stats.get("interviewer_tokens_dropped", 0),
            "interviewer_tokens_attached": load_result.stats.get("interviewer_tokens_attached", 0),
            "interviewee_tokens_kept": load_result.stats.get("interviewee_tokens_kept", 0),
            "issues": dict(file_issue_counts),
        }
        summaries.append(summary)

        totals["files"] += 1
        totals["fragments"] += len(entries)
        totals["char_len_zero"] += char_zero_count
        totals["duplicate_fragments"] += local_duplicates
        totals["flagged_fragments"] += len(flagged_issue_lists)
        totals["fragments_discarded_low_interviewee"] += discarded_fragments
        totals["interviewer_tokens_filtered"] += load_result.stats.get("interviewer_tokens_dropped", 0)
        totals["interviewer_tokens_attached"] += load_result.stats.get("interviewer_tokens_attached", 0)
        totals["interviewee_tokens_kept"] += load_result.stats.get("interviewee_tokens_kept", 0)

        log.info("ingest.file.end", **summary)

    if totals["fragments"]:
        totals["char_len_zero_pct"] = totals["char_len_zero"] / totals["fragments"]
        totals["duplicate_ratio"] = totals["duplicate_fragments"] / totals["fragments"]
        totals["flagged_ratio"] = totals["flagged_fragments"] / totals["fragments"]
    else:
        totals["char_len_zero_pct"] = 0.0
        totals["duplicate_ratio"] = 0.0
        totals["flagged_ratio"] = 0.0
    considered = totals["fragments"] + totals["fragments_discarded_low_interviewee"]
    totals["discarded_low_interviewee_ratio"] = (
        totals["fragments_discarded_low_interviewee"] / considered if considered else 0.0
    )
    token_denominator = totals["interviewee_tokens_kept"] + totals["interviewer_tokens_attached"]
    totals["interviewer_token_ratio"] = (
        totals["interviewer_tokens_attached"] / token_denominator if token_denominator else 0.0
    )
    return {
        "per_file": summaries,
        "totals": totals,
        "issues": dict(issue_counter),
    }
