"""
Worker Celery para tareas asíncronas de larga duración.

Este módulo define las tareas que se ejecutan en background usando Celery:
- Análisis LLM de entrevistas (puede tomar minutos)
- Procesamiento de lotes grandes

Arquitectura:
    Backend (FastAPI) → Redis → Celery Worker → Core (app/)
    
    1. Endpoint FastAPI recibe solicitud
    2. Encola tarea en Redis
    3. Worker Celery procesa en background
    4. Resultado almacenado en Redis
    5. Cliente puede consultar estado

Configuración:
    - Broker: Redis (configurable via CELERY_BROKER_URL)
    - Serialización: JSON
    - Timezone: UTC

Tareas disponibles:
    - task_analyze_interview: Analiza fragmentos de entrevista con LLM

Ejecución del worker:
    celery -A backend.celery_worker worker --loglevel=info

Variables de entorno:
    CELERY_BROKER_URL: URL de Redis (default: redis://localhost:6379/0)

Example:
    # Desde endpoint FastAPI
    from backend.celery_worker import task_analyze_interview
    
    result = task_analyze_interview.delay(
        project_id="mi_proyecto",
        docx_path="/path/to/file.docx",
        fragments=["fragmento 1", "fragmento 2"],
        persist=True,
        file_name="entrevista_001.docx"
    )
    # result.id contiene el ID de la tarea para consultar estado
"""

import os
import structlog
from typing import Dict
from celery import Celery
from app.settings import load_settings
from app.clients import build_service_clients
from app.analysis import analyze_interview_text, persist_analysis
from app.logging_config import configure_logging

# =============================================================================
# INICIALIZACIÓN
# =============================================================================

# Configurar logging estructurado
configure_logging()

# Logger específico para el worker
logger = structlog.get_logger("celery.worker")

# URL del broker Redis (default: localhost para desarrollo)
REDIS_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:16379/0")


# =============================================================================
# CONFIGURACIÓN CELERY
# =============================================================================

celery_app = Celery(
    "backend_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["backend.celery_worker"]
)

celery_app.conf.update(
    task_serializer="json",          # Serialización de tareas
    accept_content=["json"],         # Solo aceptar JSON
    result_serializer="json",        # Serialización de resultados
    timezone="UTC",                  # Zona horaria
    enable_utc=True,                 # Usar UTC
    task_track_started=True,         # Trackear inicio de tareas
)


# =============================================================================
# TAREAS
# =============================================================================

@celery_app.task(bind=True)
def task_analyze_interview(
    self,
    project_id: str,
    docx_path: str,
    fragments: list[str],
    persist: bool,
    file_name: str,
    run_id: str | None = None,
    request_id: str | None = None,
):
    """
    Tarea asíncrona para analizar fragmentos de entrevista.
    
    Esta tarea ejecuta el análisis LLM completo (etapas 0-4) en background,
    liberando al endpoint FastAPI para responder inmediatamente.
    
    Args:
        self: Instancia de la tarea (bind=True)
        project_id: ID del proyecto para persistencia
        docx_path: Ruta al archivo DOCX original
        fragments: Lista de fragmentos de texto a analizar
        persist: Si True, persiste resultados en PostgreSQL/Neo4j
        file_name: Nombre del archivo para logging y trazabilidad
        
    Returns:
        dict: Resultado del análisis (etapa0-4 JSON) + interview_report
        
    Raises:
        Exception: Si el análisis falla (la tarea se marca como fallida)
        
    Note:
        Los clientes (ServiceClients) se reconstruyen dentro del worker
        porque son objetos no serializables.
    """
    from app.reports import generate_interview_report, save_interview_report, get_interview_reports
    from app.coding import get_all_codes_for_project
    
    logger.info("task.analyze.start", file=file_name, project=project_id)
    
    # Reconstruir clientes dentro del proceso worker
    # (los objetos de conexión no son serializables entre procesos)
    settings = load_settings()
    clients = build_service_clients(settings)
    
    try:
        # Obtener códigos existentes para calcular novedad
        try:
            existing_codes = get_all_codes_for_project(clients.postgres, project_id)
        except Exception:
            existing_codes = []
        
        # Si no se recibió run_id, usar task id para trazabilidad básica.
        if not run_id:
            try:
                run_id = getattr(getattr(self, "request", None), "id", None)
            except Exception:
                run_id = None

        # Ejecutar análisis LLM (etapas 0-4)
        result = analyze_interview_text(
            clients,
            settings,
            fragments,
            fuente=file_name,
            project_id=project_id,
            run_id=run_id,
            request_id=request_id,
        )
        
        # Persistir si se solicita
        if persist:
            persist_analysis(
                clients,
                settings,
                file_name,
                result,
                project_id=project_id,
                run_id=run_id,
                request_id=request_id,
            )
            logger.info("task.analyze.persisted", file=file_name)
        
        # Generar informe de entrevista
        try:
            report = generate_interview_report(
                archivo=file_name,
                project_id=project_id,
                analysis_result=result,
                existing_codes=existing_codes,
                fragments_total=len(fragments),
                llm_model=settings.azure.deployment_chat,
            )
            save_interview_report(clients.postgres, report)
            logger.info("task.analyze.report_saved", file=file_name)
            
            # Agregar informe al resultado
            result["interview_report"] = report.to_dict()
        except Exception as report_error:
            logger.warning("task.analyze.report_error", error=str(report_error))
            result["interview_report"] = None
            
        return result
        
    except Exception as e:
        logger.error("task.analyze.failed", error=str(e))
        # Re-lanzar para marcar tarea como fallida en Celery
        raise e
        
    finally:
        # Siempre cerrar conexiones
        clients.close()


# =============================================================================
# TAREA: TRANSCRIPCIÓN DE AUDIO
# =============================================================================

@celery_app.task(bind=True)
def task_transcribe_audio(
    self,
    org_id: str,
    project_id: str,
    *,
    # Mode A: raw audio provided inline (base64)
    audio_base64: str | None = None,
    # Mode B: existing blob reference (container + blob_name)
    audio_blob: Dict[str, str] | None = None,
    filename: str | None = None,
    diarize: bool = True,
    language: str = "es",
    ingest: bool = True,
    min_chars: int = 200,
    max_chars: int = 1200,
    speaker_refs: list | None = None,  # Lista de (nombre, audio_base64) para identificación por voz
    incremental: bool = False,
):
    """
    Tarea asíncrona para transcribir archivos de audio.
    
    Permite transcripción paralela de múltiples archivos simultáneamente.
    
    Args:
        self: Instancia de la tarea (bind=True)
        audio_base64: Audio codificado en base64
        filename: Nombre original del archivo
        project_id: ID del proyecto
        diarize: Usar diarización de speakers
        language: Código de idioma (es, en, pt)
        ingest: Ingestar al pipeline después de transcribir
        min_chars: Mínimo caracteres por fragmento
        max_chars: Máximo caracteres por fragmento
        speaker_refs: Lista de [nombre, audio_base64] para identificación por timbre de voz.
                      Máximo 4 speakers, cada clip debe ser 2-10 segundos.
        
    Returns:
        dict: Resultado de la transcripción con segmentos y metadata
    """
    import tempfile
    import base64
    from pathlib import Path
    from datetime import datetime
    from app.transcription import (
        transcribe_audio_chunked,
        save_transcription_docx,
        TranscriptionResult,
    )
    
    log = logger.bind(
        task_id=self.request.id,
        filename=filename or "",
        project=project_id,
        org=org_id,
    )
    
    log.info("task.transcribe.start")
    
    settings = load_settings()
    from app.blob_storage import CONTAINER_INTERVIEWS, CONTAINER_AUDIO, tenant_upload

    # Validate mode: XOR audio_base64 vs audio_blob
    if (audio_base64 is None) == (audio_blob is None):
        log.error("task.transcribe.invalid_mode", audio_base64_present=(audio_base64 is not None), audio_blob_present=(audio_blob is not None))
        raise ValueError("Must provide exactly one of audio_base64 or audio_blob")

    suffix = Path(filename).suffix.lower() if filename else ".wav"
    tmp_path = None
    audio_blob_info = None
    # Obtain audio bytes: from base64 or download existing blob
    if audio_base64 is not None:
        try:
            audio_bytes = base64.b64decode(audio_base64)
        except Exception as e:
            log.error("task.transcribe.decode_error", error=str(e))
            return {"status": "error", "error": f"Error decodificando audio: {e}", "filename": filename}

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)

        # upload raw audio to blob (tenant-aware)
        logical = f"audio/{project_id}/raw/{Path(filename).name if filename else tmp_path.name}"
        content_type = f"audio/{suffix.lstrip('.') or 'wav'}"
        try:
            audio_blob = tenant_upload(
                container=CONTAINER_AUDIO,
                org_id=org_id,
                project_id=project_id,
                logical_path=logical,
                file_path=str(tmp_path),
                content_type=content_type,
                strict_tenant=True,
            )
            audio_url = audio_blob["url"]
            audio_hash = audio_blob["sha256"]
            blob_name = audio_blob["name"]
            audio_blob_info = {"container": CONTAINER_AUDIO, "name": blob_name, "url": audio_url, "content_type": content_type, "sha256": audio_hash}
        except Exception as exc:
            log.error("task.transcribe.audio_upload_failed", error=str(exc))
            raise

    else:
        # audio_blob expected to be {"container":..., "name":...}
        audio_blob_info = audio_blob
        # If provided as blob ref, we don't download - assume already durable
        tmp_path = None
    
    try:
        # Actualizar estado: transcribiendo
        self.update_state(state="PROCESSING", meta={"stage": "transcribing", "filename": filename})

        # Transcribir usando chunked (síncrono)
        # If tmp_path is None (audio_blob mode), download to temp for transcription
        if tmp_path is None and audio_blob_info:
            # download blob to temp
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmpd:
                tmpd_path = Path(tmpd.name)
            try:
                from app.blob_storage import download_file
                data = download_file(container=audio_blob_info.get("container"), blob_name=audio_blob_info.get("name"))
                with open(tmpd_path, "wb") as f:
                    f.write(data)
                tmp_path = tmpd_path
            except Exception as e:
                log.error("task.transcribe.download_blob_failed", error=str(e))
                raise

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
        
        # Guardar DOCX final to temp then upload to interviews container
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmpdoc:
            tmp_doc_path = Path(tmpdoc.name)
        save_transcription_docx(result, tmp_doc_path)

        # Build logical path relative to project
        docx_logical = f"interviews/{project_id}/audio/transcriptions/{tmp_doc_path.name}"
        try:
            docx_blob = tenant_upload(
                container=CONTAINER_INTERVIEWS,
                org_id=org_id,
                project_id=project_id,
                logical_path=docx_logical,
                file_path=str(tmp_doc_path),
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                strict_tenant=True,
            )
            docx_url = docx_blob["url"]
            docx_hash = docx_blob["sha256"]
            docx_blob_name = docx_blob["name"]
        except Exception as exc:
            log.error("task.transcribe.docx_upload_failed", error=str(exc))
            raise

        log.info("task.transcribe.saved_blob", blob=docx_blob_name, url=docx_url)
        
        # Ingestar al final si corresponde (ingestará desde el docx temp path uploaded)
        total_fragments_ingested = 0
        if ingest:
            self.update_state(state="PROCESSING", meta={"stage": "ingesting", "filename": filename})
            from app.ingestion import ingest_documents

            clients = build_service_clients(settings)
            try:
                # Ingest expects filesystem path; download blob to temp and pass path
                # For efficiency, we can use the tmp_doc_path we just created
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
                total_fragments_ingested = totals.get("fragments", 0)
                log.info("task.transcribe.ingested", fragments=total_fragments_ingested)
            finally:
                clients.close()
        
        # Build standardized return payload
        payload = {
            "artifact_version": 1,
            "status": "completed",
            "docx_logical_path": docx_logical,
            "docx_blob": {"container": CONTAINER_INTERVIEWS, "name": docx_blob_name, "url": docx_url, "sha256": docx_hash},
            "audio_blob": audio_blob_info or {},
            "chunks_completed": len(result.segments),
            "text_preview": (result.text or "")[:500],
            "text": result.text,
            "segments": [
                {"speaker": seg.speaker, "text": seg.text, "start": seg.start, "end": seg.end}
                for seg in result.segments
            ],
            "speaker_count": result.speaker_count,
            "duration_seconds": result.duration_seconds,
            "fragments_ingested": total_fragments_ingested,
            "warnings": [],
        }

        return payload
        
    except Exception as e:
        log.exception("task.transcribe.error")
        return {"artifact_version": 1, "status": "failed", "error": str(e), "filename": filename or "unknown", "warnings": []}
    finally:
        # Clean up any temporary files we created
        try:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
