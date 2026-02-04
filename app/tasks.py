"""
Celery tasks for background processing.
"""
import structlog
from pathlib import Path
from typing import Dict, Any, Optional
import tempfile
import base64
import os

from .celery_app import celery_app
from .settings import load_settings
from .transcription import (
    transcribe_audio_chunked,
    save_transcription_docx,
    TranscriptionResult,
)

logger = structlog.get_logger(__name__)


@celery_app.task(bind=True, name="app.tasks.transcribe_audio_task")
def transcribe_audio_task(
    self,
    org_id: Optional[str],
    audio_base64: str,
    filename: str,
    project_id: str,
    diarize: bool = True,
    language: str = "es",
    ingest: bool = True,
    min_chars: int = 200,
    max_chars: int = 1200,
) -> Dict[str, Any]:
    """
    Background task for transcribing audio files.
    
    Args:
        audio_base64: Base64 encoded audio data
        filename: Original filename
        project_id: Project ID
        diarize: Use speaker diarization
        language: Language code
        ingest: Ingest after transcription
        min_chars: Min chars per fragment
        max_chars: Max chars per fragment
        
    Returns:
        Dict with transcription result and metadata
    """
    log = logger.bind(
        task_id=self.request.id,
        filename=filename,
        project=project_id,
    )
    
    log.info("task.transcribe.start")
    
    settings = load_settings()
    # Enforce tenant scoping: org_id must be provided in production.
    allow_orgless = os.getenv("ALLOW_ORGLESS_TASKS", "false").lower() in ("1", "true", "yes")
    if not org_id:
        if allow_orgless:
            logger.warning("task.transcribe.org_missing.allow_fallback", task_id=getattr(self.request, "id", None))
            org_id = ""
        else:
            logger.error("task.transcribe.missing_org", task_id=getattr(self.request, "id", None))
            return {"status": "failed", "error": "Missing org_id for tenant-scoped storage"}
    suffix = Path(filename).suffix.lower()
    
    # Decode audio
    try:
        audio_bytes = base64.b64decode(audio_base64)
    except Exception as e:
        log.error("task.transcribe.decode_error", error=str(e))
        return {"status": "error", "error": f"Error decodificando audio: {e}"}
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)
    
    try:
        # Update task state
        self.update_state(state="PROCESSING", meta={"stage": "transcribing"})
        
        # Transcribe
        result = transcribe_audio_chunked(
            tmp_path,
            settings,
            diarize=diarize,
            language=language,
        )
        
        log.info(
            "task.transcribe.complete",
            speakers=result.speaker_count,
            segments=len(result.segments),
            duration=result.duration_seconds,
        )
        
        # Save to a temp docx, upload to Blob Storage (tenant-scoped), and optionally ingest
        import tempfile
        from .blob_storage import CONTAINER_INTERVIEWS, tenant_upload

        # Create temp docx and save
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmpdoc:
            tmp_doc_path = Path(tmpdoc.name)
        save_transcription_docx(result, tmp_doc_path)

        # Build logical path and upload (tenant-aware)
        logical = f"interviews/{project_id}/audio/transcriptions/{tmp_doc_path.name}"
        try:
            docx_blob = tenant_upload(
                container=CONTAINER_INTERVIEWS,
                org_id=org_id,
                project_id=project_id,
                logical_path=logical,
                file_path=str(tmp_doc_path),
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            docx_url = docx_blob["url"]
            docx_blob_name = docx_blob["name"]
            docx_hash = docx_blob["sha256"]
        except Exception as exc:
            log.error("task.transcribe.upload_docx_failed", error=str(exc))
            raise

        log.info("task.transcribe.saved_blob", blob=docx_blob_name)

        # Ingest if requested (ingest from temp file path)
        fragments_ingested = None
        if ingest:
            self.update_state(state="PROCESSING", meta={"stage": "ingesting"})
            from .clients import build_service_clients
            from .ingestion import ingest_documents

            clients = build_service_clients(settings)
            try:
                ingest_result = ingest_documents(
                    clients,
                    settings,
                    files=[str(tmp_doc_path)],
                    batch_size=20,
                    min_chars=min_chars,
                    max_chars=max_chars,
                    logger=log,
                    project=project_id,
                    org_id=org_id,
                )
                totals = ingest_result.get("totals", {})
                fragments_ingested = totals.get("fragments", 0)
                log.info("task.transcribe.ingested", fragments=fragments_ingested)
            finally:
                clients.close()
        
        return {
            "status": "completed",
            "filename": filename,
            "saved_path": docx_url,
            "docx_blob": {"container": CONTAINER_INTERVIEWS, "name": docx_blob_name, "url": docx_url, "sha256": docx_hash},
            "text": result.text,
            "segments": [
                {
                    "speaker": seg.speaker,
                    "text": seg.text,
                    "start": seg.start,
                    "end": seg.end,
                }
                for seg in result.segments
            ],
            "speaker_count": result.speaker_count,
            "duration_seconds": result.duration_seconds,
            "fragments_ingested": fragments_ingested,
        }
        
    except Exception as e:
        log.exception("task.transcribe.error")
        return {"status": "error", "error": str(e), "filename": filename}
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            tmp_doc_path.unlink(missing_ok=True)
        except Exception:
            pass


@celery_app.task(name="app.tasks.batch_status")
def batch_status(batch_id: str) -> Dict[str, Any]:
    """Get status of all tasks in a batch."""
    from .celery_app import celery_app
    
    # This is a placeholder - actual implementation would track batch
    return {"batch_id": batch_id, "status": "checking"}


@celery_app.task(bind=True, name="app.tasks.run_agent")
def task_run_agent(
    self,
    project_id: str,
    concepts: list,
    max_iterations: int = 50,
    max_interviews: int = 10,
    iterations_per_interview: int = 4,
    discovery_only: bool = False,
) -> Dict[str, Any]:
    """
    Celery task para ejecutar el agente autónomo de investigación.
    
    Sprint 29 - Enero 2026
    
    Args:
        project_id: ID del proyecto a analizar
        concepts: Conceptos iniciales para Discovery
        max_iterations: Límite de seguridad para el loop
        max_interviews: Máximo de entrevistas a procesar
        iterations_per_interview: Refinamientos por entrevista
        discovery_only: Solo ejecutar fase Discovery
    
    Returns:
        Dict con resultado del agente
    """
    import asyncio
    
    log = logger.bind(
        task_id=self.request.id,
        project=project_id,
        concepts=concepts,
    )
    
    log.info("task.agent.start")
    
    # Update task state
    self.update_state(
        state="PROCESSING",
        meta={"stage": "initializing", "iteration": 0}
    )
    
    try:
        # Run agent with callback to update task state
        from .agent_standalone import run_agent_with_real_functions
        
        def update_progress(state: dict):
            self.update_state(
                state="PROCESSING",
                meta={
                    "stage": state.get("current_stage", 0),
                    "iteration": state.get("iteration", 0),
                    "memos_count": len(state.get("memos", [])),
                    "codes_count": len(state.get("validated_codes", [])),
                }
            )
        
        # Run async function in sync context
        result = asyncio.run(
            run_agent_with_real_functions(
                project_id=project_id,
                concepts=concepts,
                max_iterations=max_iterations,
                max_interviews=max_interviews,
                iterations_per_interview=iterations_per_interview,
                discovery_only=discovery_only,
                task_callback=update_progress,
            )
        )
        
        log.info(
            "task.agent.complete",
            iterations=result.get("iteration"),
            codes_count=len(result.get("validated_codes", [])),
            memos_count=len(result.get("discovery_memos", [])),
        )
        
        return {
            "status": "completed",
            "project_id": project_id,
            "iterations": result.get("iteration", 0),
            "validated_codes": result.get("validated_codes", []),
            "discovery_memos": result.get("discovery_memos", []),
            "saturation_score": result.get("saturation_score", 0.0),
            "errors": result.get("errors", []),
            "needs_human": result.get("needs_human", False),
            "final_report": result.get("final_report"),
        }
        
    except Exception as e:
        log.exception("task.agent.error")
        return {
            "status": "error",
            "error": str(e),
            "project_id": project_id,
        }
