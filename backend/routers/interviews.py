"""
Interviews router - Decoupled pipeline endpoints.

Endpoints:
    GET  /api/interviews              - List interview files with status
    POST /api/interviews/upload       - Step 1: Upload DOCX to Azure & register
    POST /api/interviews/{id}/process - Step 2: Segment, Embed & Index
"""
import uuid
import structlog
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict

from app.clients import ServiceClients, build_service_clients
from app.settings import AppSettings, load_settings
from app.blob_storage import upload_file, CONTAINER_INTERVIEWS, tenant_upload, TenantRequiredError
from app.ingestion import ingest_documents
from app.documents import load_fragments
from app.project_state import resolve_project
from backend.auth import User, get_current_user

router = APIRouter(prefix="/api/interviews", tags=["interviews"])
logger = structlog.get_logger("app.api.interviews")

# =============================================================================
# DEPENDENCIES
# =============================================================================

def get_settings() -> AppSettings:
    import os
    env_file = os.getenv("APP_ENV_FILE")
    return load_settings(env_file)

from typing import AsyncGenerator

async def get_service_clients(settings: AppSettings = Depends(get_settings)) -> AsyncGenerator[ServiceClients, None]:
    """
    CRITICAL: Uses yield + finally to ensure connections are returned to pool!
    """
    clients = build_service_clients(settings)
    try:
        yield clients
    finally:
        clients.close()

async def require_auth(user: User = Depends(get_current_user)) -> User:
    return user

# =============================================================================
# MODELS
# =============================================================================

class InterviewFileDTO(BaseModel):
    id: int
    project_id: str
    filename: str
    status: str
    segments_count: Optional[int]
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str]

    model_config = ConfigDict(from_attributes=True)

# =============================================================================
# DB OPS
# =============================================================================

def _get_file_record(pg, file_id: int):
    with pg.cursor() as cur:
        cur.execute(
            "SELECT id, project_id, filename, blob_url, status FROM interview_files WHERE id = %s",
            (file_id,)
        )
        return cur.fetchone()

def _update_status(pg, file_id: int, status: str, error: str = None, segments: int = None):
    with pg.cursor() as cur:
        updates = ["status = %s", "updated_at = NOW()"]
        params = [status, file_id]
        
        if error is not None:
            updates.append("error_message = %s")
            params.insert(1, error)
        
        if segments is not None:
            updates.append("segments_count = %s")
            params.insert(1, segments)
            
        sql = f"UPDATE interview_files SET {', '.join(updates)} WHERE id = %s"
        cur.execute(sql, tuple(params))
    pg.commit()

# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/files", response_model=List[InterviewFileDTO])
def list_interviews(
    project: str,
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth)
):
    """List all interviews for a project with their pipeline status."""
    with clients.postgres.cursor() as cur:
        cur.execute("""
            SELECT id, project_id, filename, status, segments_count, 
                   created_at, updated_at, error_message
            FROM interview_files 
            WHERE project_id = %s
            ORDER BY created_at DESC
        """, (project,))
        
        cols = [desc[0] for desc in cur.description]
        results = []
        for row in cur.fetchall():
            results.append(dict(zip(cols, row)))
            
        return results

@router.post("/upload")
async def upload_interview(
    project: str = Form(...),
    file: UploadFile = File(...),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth)
):
    """Step 1: Upload file to Azure and register in DB."""
    logger.info("upload.start", filename=file.filename, project=project)
    
    # 1. Upload to Azure (tenant-aware)
    try:
        content = await file.read()
        logical = f"interviews/{file.filename}"
        org_id = getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=409, detail="Missing organization_id (tenant). Contact admin or use a tenant-scoped API key.")

        try:
            blob_info = tenant_upload(
                container=CONTAINER_INTERVIEWS,
                org_id=org_id,
                project_id=project,
                logical_path=logical,
                data=content,
                content_type=file.content_type,
            )
            blob_url = blob_info["url"]
        except TenantRequiredError:
            raise HTTPException(status_code=409, detail="Missing organization_id (tenant). Contact admin or use a tenant-scoped API key.")
        except Exception as e:
            logger.error("upload.azure_failed", error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to upload to Azure: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("upload.azure_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to upload to Azure: {str(e)}")

    # 2. Register in DB
    try:
        with clients.postgres.cursor() as cur:
            cur.execute("""
                INSERT INTO interview_files (project_id, filename, blob_url, file_size, status)
                VALUES (%s, %s, %s, %s, 'uploaded')
                ON CONFLICT (project_id, filename) 
                DO UPDATE SET 
                    blob_url = EXCLUDED.blob_url,
                    file_size = EXCLUDED.file_size,
                    status = 'uploaded',
                    updated_at = NOW()
                RETURNING id
            """, (project, file.filename, blob_url, len(content)))
            file_id = cur.fetchone()[0]
        clients.postgres.commit()
        
        logger.info("upload.success", file_id=file_id)
        return {"id": file_id, "status": "uploaded", "url": blob_url}
        
    except Exception as e:
        clients.postgres.rollback()
        logger.error("upload.db_failed", error=str(e))
        raise HTTPException(500, f"Database error: {str(e)}")
    finally:
        clients.close()

@router.post("/{file_id}/process")
def process_interview(
    file_id: int,
    settings: AppSettings = Depends(get_settings),
    clients: ServiceClients = Depends(get_service_clients),
    user: User = Depends(require_auth)
):
    """Step 2: Trigger processing (Segment -> Embed -> Index)."""
    import tempfile
    import os
    from app.blob_storage import download_file, CONTAINER_INTERVIEWS

    # 1. Get file record
    record = _get_file_record(clients.postgres, file_id)
    if not record:
        raise HTTPException(404, "File not found")
        
    _, project_id, filename, blob_url, current_status = record
    
    # If already indexing or analyzed, we might still want to allow re-processing if requested (retry)
    # But for now let's blocking concurrent indexing on same file to avoid duplicates/race conditions
    if current_status == 'indexing':
        raise HTTPException(409, "File is already being processed")

    # 2. Update status to indexing
    _update_status(clients.postgres, file_id, 'indexing')
    logger.info("process.start", file_id=file_id, filename=filename)

    try:
        # 3. Download from Azure to temp file
        blob_path = f"{project_id}/{filename}"
        
        try:
            file_content = download_file(CONTAINER_INTERVIEWS, blob_path)
        except Exception as e:
            raise ValueError(f"Failed to download blob {blob_path}: {e}")

        # Create temp file with proper extension (.docx)
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name
        
        try:
            # 4. Ingest (Segment + Embed + Index)
            # ingest_documents expects a list of paths
            result = ingest_documents(
                clients,
                settings,
                files=[tmp_path],
                project=project_id,
                org_id=str(getattr(user, "organization_id", None) or ""),
                logger=logger
            )
            
            # Extract stats
            total_fragments = result['totals']['fragments']
            
            # 5. Update status to indexed
            _update_status(
                clients.postgres, 
                file_id, 
                'indexed', 
                segments=total_fragments
            )
            
            return {
                "id": file_id,
                "status": "indexed",
                "segments": total_fragments,
                "details": result['totals']
            }
            
        finally:
            # Cleanup temp file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    except Exception as e:
        _update_status(clients.postgres, file_id, 'error', error=str(e))
        logger.error("process.failed", error=str(e))
        raise HTTPException(500, str(e))
    finally:
        clients.close()

