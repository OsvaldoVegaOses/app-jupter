"""
Azure Blob Storage operations for file storage.

This module provides cloud storage for interview files and audio,
replacing local file system storage for Azure deployment.

Containers:
    - interviews: DOCX files
    - audio-raw: Raw audio files before transcription
"""

from __future__ import annotations

import logging
import os
import re
import time
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass(frozen=True)
class BlobRef:
    artifact_version: int
    container: str
    blob_name: str
    logical_path: str
    url: Optional[str]
    sha256: str
    content_type: Optional[str]
    size_bytes: int
    metadata: Dict[str, Any]


class TenantRequiredError(ValueError):
    """Raised when org_id is required but missing/empty."""
    pass

# Optional dependency: allow local/dev startup without Azure SDK installed.
try:
    from azure.storage.blob import BlobServiceClient, ContentSettings  # type: ignore
    from azure.core.exceptions import ResourceExistsError  # type: ignore

    _AZURE_BLOB_AVAILABLE = True
except Exception:  # pragma: no cover
    BlobServiceClient = None  # type: ignore
    ContentSettings = None  # type: ignore
    ResourceExistsError = Exception  # type: ignore
    _AZURE_BLOB_AVAILABLE = False

_logger = logging.getLogger(__name__)

# Container names
CONTAINER_INTERVIEWS = "interviews"
CONTAINER_AUDIO = "audio-raw"
CONTAINER_REPORTS = "reports"

_SAFE_COMPONENT_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def allow_orgless_tasks() -> bool:
    """Return whether orgless mode is explicitly enabled (development only)."""
    return os.getenv("ALLOW_ORGLESS_TASKS", "false").lower() in ("1", "true", "yes")


def require_org_id(org_id: Optional[str], *, operation: str) -> None:
    """Enforce tenant identity unless orgless mode is explicitly enabled."""
    if org_id:
        return
    if allow_orgless_tasks():
        return
    raise TenantRequiredError(
        f"org_id is required for {operation}. "
        "Set ALLOW_ORGLESS_TASKS=true for development only."
    )


def _safe_blob_component(value: Optional[str], *, default: str) -> str:
    """Normalize a user/org/project identifier into a safe blob path component."""
    raw = (value or "").strip()
    if not raw:
        return default
    safe = _SAFE_COMPONENT_RE.sub("-", raw).strip("-")
    return safe or default


def tenant_prefix(*, org_id: Optional[str], project_id: str) -> str:
    """Tenant-scoped prefix for strict multi-tenant storage paths."""
    require_org_id(org_id, operation="tenant-scoped blob paths")
    org = _safe_blob_component(org_id, default="unknown_org")
    proj = _safe_blob_component(project_id, default="unknown_project")
    return f"org/{org}/projects/{proj}"


def logical_path_to_blob_name(*, org_id: Optional[str], project_id: str, logical_path: str) -> str:
    """Map a logical artifact path to a tenant-scoped blob name.

    Logical paths are stable product paths used by the UI/API, e.g.:
    - reports/<project_id>/foo.md
    - notes/<project_id>/runner_semantic/bar.md
    - logs/runner_reports/<project_id>/<task_id>.json

    The resulting blob name is always under tenant_prefix(org_id, project_id).
    """
    norm = (logical_path or "").replace("\\", "/").lstrip("/")
    if not norm:
        raise ValueError("logical_path is empty")

    require_org_id(org_id, operation="tenant-scoped blob mapping")

    prefix = tenant_prefix(org_id=org_id, project_id=project_id)

    def _strip(expected: str) -> str:
        if not norm.startswith(expected):
            raise ValueError("logical_path does not match expected prefix")
        return norm[len(expected) :]

    # reports/<project_id>/...
    if norm.startswith(f"reports/{project_id}/"):
        rest = _strip(f"reports/{project_id}/")
        return f"{prefix}/reports/{rest}"

    # notes/<project_id>/...
    if norm.startswith(f"notes/{project_id}/"):
        rest = _strip(f"notes/{project_id}/")
        return f"{prefix}/notes/{rest}"

    # logs/runner_reports/<project_id>/...
    if norm.startswith(f"logs/runner_reports/{project_id}/"):
        rest = _strip(f"logs/runner_reports/{project_id}/")
        return f"{prefix}/logs/runner_reports/{rest}"

    # logs/runner_checkpoints/<project_id>/...
    if norm.startswith(f"logs/runner_checkpoints/{project_id}/"):
        rest = _strip(f"logs/runner_checkpoints/{project_id}/")
        return f"{prefix}/logs/runner_checkpoints/{rest}"

    # Legacy: reports/runner/<project_id>/...
    if norm.startswith(f"reports/runner/{project_id}/"):
        rest = _strip(f"reports/runner/{project_id}/")
        return f"{prefix}/reports/runner/{rest}"

    # Interviews: interviews/<project_id>/...
    if norm.startswith(f"interviews/{project_id}/"):
        rest = _strip(f"interviews/{project_id}/")
        return f"{prefix}/interviews/{rest}"

    # Audio raw: audio/<project_id>/raw/<file>
    if norm.startswith(f"audio/{project_id}/"):
        rest = _strip(f"audio/{project_id}/")
        return f"{prefix}/audio/{rest}"

    raise ValueError(f"Unsupported logical_path for blob mapping: {norm}")


def blob_name_to_logical_path(*, org_id: Optional[str], project_id: str, blob_name: str) -> Optional[str]:
    """Best-effort reverse mapping for artifact listing."""
    name = (blob_name or "").replace("\\", "/").lstrip("/")
    if not name:
        return None

    prefix = tenant_prefix(org_id=org_id, project_id=project_id).rstrip("/")
    if not name.startswith(prefix + "/"):
        # Fallback to legacy-style blobs without tenant prefix if enabled by env
        allow_legacy = os.getenv("ALLOW_BLOB_LEGACY_READ", "false").lower() in ("1", "true", "yes")
        if not allow_legacy:
            return None
        # Legacy blobs often start with "<project_id>/..." - map back when allowed
        if name.startswith(f"{project_id}/"):
            rel = name[len(f"{project_id}/") :]
            # Determine common logical prefixes
            if rel.startswith("interviews/"):
                rest = rel[len("interviews/"):]
                _logger.info("blob.legacy_read_used", extra={"blob": blob_name, "project": project_id})
                return f"interviews/{project_id}/{rest}"
            if rel.startswith("audio/"):
                rest = rel[len("audio/"):]
                _logger.info("blob.legacy_read_used", extra={"blob": blob_name, "project": project_id})
                return f"audio/{project_id}/{rest}"
        return None
    rel = name[len(prefix) + 1 :]

    if rel.startswith("reports/"):
        rest = rel[len("reports/") :]
        return f"reports/{project_id}/{rest}"
    if rel.startswith("notes/"):
        rest = rel[len("notes/") :]
        return f"notes/{project_id}/{rest}"
    if rel.startswith("logs/runner_reports/"):
        rest = rel[len("logs/runner_reports/") :]
        return f"logs/runner_reports/{project_id}/{rest}"
    if rel.startswith("logs/runner_checkpoints/"):
        rest = rel[len("logs/runner_checkpoints/") :]
        return f"logs/runner_checkpoints/{project_id}/{rest}"

    return None


def get_blob_service_client() -> BlobServiceClient:
    """
    Creates a BlobServiceClient from the connection string.
    
    Returns:
        BlobServiceClient instance
        
    Raises:
        ValueError: If connection string is not configured
    """
    if not _AZURE_BLOB_AVAILABLE:
        raise RuntimeError(
            "Azure Blob Storage SDK no está instalado. Instala 'azure-storage-blob' (y 'azure-core') "
            "o desactiva/evita rutas que dependan de Blob Storage en desarrollo."
        )

    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not conn_str:
        # Best-effort: load .env into os.environ for scripts that call blob helpers directly.
        try:
            from app.settings import load_settings

            load_settings(os.getenv("APP_ENV_FILE"))
            conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        except Exception:
            conn_str = None
    if not conn_str:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING not set in environment")
    return BlobServiceClient.from_connection_string(conn_str)


def upload_file(
    container: str,
    blob_name: str,
    data: bytes,
    content_type: Optional[str] = None,
) -> str:
    """
    Upload a file to Azure Blob Storage.
    
    Args:
        container: Container name (interviews, audio-raw)
        blob_name: Full blob path (e.g., "project_id/filename.docx")
        data: File contents as bytes
        content_type: MIME type (optional)
        
    Returns:
        URL of the uploaded blob
    """
    client = get_blob_service_client()

    # Ensure container exists (idempotent)
    try:
        client.create_container(container)
    except ResourceExistsError:
        pass
    except Exception as exc:
        _logger.warning(
            "blob.container.ensure_failed",
            extra={"container": container, "error": str(exc)[:200]},
        )

    blob = client.get_blob_client(container=container, blob=blob_name)
    
    content_settings = None
    if content_type:
        # ContentSettings only exists when Azure SDK is installed.
        content_settings = ContentSettings(content_type=content_type) if ContentSettings else None
    
    blob.upload_blob(data, overwrite=True, content_settings=content_settings)
    
    _logger.info(
        "blob.uploaded",
        extra={"container": container, "blob": blob_name, "size": len(data)}
    )
    
    return blob.url


def upload_text(
    *,
    container: str,
    blob_name: str,
    text: str,
    content_type: str = "text/plain; charset=utf-8",
) -> str:
    return upload_file(
        container=container,
        blob_name=blob_name,
        data=(text or "").encode("utf-8"),
        content_type=content_type,
    )


def upload_local_path(
    *,
    container: str,
    blob_name: str,
    file_path: str,
    content_type: Optional[str] = None,
) -> str:
    with open(file_path, "rb") as f:
        data = f.read()
    return upload_file(container=container, blob_name=blob_name, data=data, content_type=content_type)


def tenant_upload_file(
    *,
    org_id: str,
    project_id: str,
    container: str,
    logical_path: str,
    file_path: str,
    content_type: str,
    metadata: Optional[Dict[str, Any]] = None,
    strict_tenant: bool = True,
) -> Dict[str, Any]:
    """Upload from file path, returns artifact dict (compatible with BlobRef fields)."""
    artifact = tenant_upload(
        container=container,
        org_id=org_id,
        project_id=project_id,
        logical_path=logical_path,
        file_path=file_path,
        content_type=content_type,
        strict_tenant=strict_tenant,
    )
    if metadata:
        artifact_meta = artifact.get("metadata") or {}
        artifact_meta.update(metadata)
        artifact["metadata"] = artifact_meta
    return artifact


def tenant_upload_bytes(
    *,
    org_id: Optional[str],
    project_id: str,
    container: str,
    logical_path: str,
    data: bytes,
    content_type: str,
    metadata: Optional[Dict[str, Any]] = None,
    strict_tenant: bool = True,
) -> Dict[str, Any]:
    artifact = tenant_upload(
        container=container,
        org_id=org_id,
        project_id=project_id,
        logical_path=logical_path,
        data=data,
        content_type=content_type,
        strict_tenant=strict_tenant,
    )
    if metadata:
        artifact_meta = artifact.get("metadata") or {}
        artifact_meta.update(metadata)
        artifact["metadata"] = artifact_meta
    return artifact


def tenant_upload_text(
    *,
    org_id: Optional[str],
    project_id: str,
    container: str,
    logical_path: str,
    text: str,
    content_type: str = "text/plain; charset=utf-8",
    metadata: Optional[Dict[str, Any]] = None,
    strict_tenant: bool = True,
) -> Dict[str, Any]:
    data = (text or "").encode("utf-8")
    return tenant_upload_bytes(
        org_id=org_id,
        project_id=project_id,
        container=container,
        logical_path=logical_path,
        data=data,
        content_type=content_type,
        metadata=metadata,
        strict_tenant=strict_tenant,
    )


def build_artifact_contract(
    *,
    audio: Optional[Dict[str, Any]] = None,
    docx: Optional[Dict[str, Any]] = None,
    chunks_completed: Optional[int] = None,
    text_preview: Optional[str] = None,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"artifact_version": 1}
    if docx:
        out["docx_logical_path"] = docx.get("logical_path")
        out["docx_blob"] = {
            "container": docx.get("container"),
            "name": docx.get("name"),
            "url": docx.get("url"),
            "sha256": docx.get("sha256"),
            "size_bytes": docx.get("size_bytes"),
            "content_type": docx.get("content_type"),
        }
    if audio:
        out["audio_logical_path"] = audio.get("logical_path")
        out["audio_blob"] = {
            "container": audio.get("container"),
            "name": audio.get("name"),
            "url": audio.get("url"),
            "sha256": audio.get("sha256"),
            "size_bytes": audio.get("size_bytes"),
            "content_type": audio.get("content_type"),
        }
    if chunks_completed is not None:
        out["chunks_completed"] = int(chunks_completed)
    if text_preview is not None:
        out["text_preview"] = text_preview
    if warnings:
        out["warnings"] = list(warnings)
    return out


def download_file(container: str, blob_name: str) -> bytes:
    """
    Download a file from Azure Blob Storage.
    
    Args:
        container: Container name
        blob_name: Full blob path
        
    Returns:
        File contents as bytes
    """
    client = get_blob_service_client()
    blob = client.get_blob_client(container=container, blob=blob_name)
    return blob.download_blob().readall()


def delete_file(container: str, blob_name: str) -> bool:
    """
    Delete a file from Azure Blob Storage.
    
    Args:
        container: Container name
        blob_name: Full blob path
        
    Returns:
        True if deleted successfully
    """
    client = get_blob_service_client()
    blob = client.get_blob_client(container=container, blob=blob_name)
    blob.delete_blob()
    
    _logger.info(
        "blob.deleted",
        extra={"container": container, "blob": blob_name}
    )
    
    return True


def delete_prefix(*, container: str, prefix: str, limit: int = 5000) -> Dict[str, Any]:
    """Delete blobs under a prefix (best-effort).

    Note: Azure Blob Storage has no "folder" delete; we delete blobs individually.
    """
    client = get_blob_service_client()
    container_client = client.get_container_client(container)
    deleted = 0
    errors = 0
    try:
        for b in container_client.list_blobs(name_starts_with=prefix):
            name = getattr(b, "name", None)
            if not name:
                continue
            try:
                container_client.delete_blob(name)
                deleted += 1
            except Exception:
                errors += 1
            if deleted + errors >= max(1, int(limit)):
                break
    except Exception as exc:
        _logger.warning(
            "blob.delete_prefix_failed",
            extra={"container": container, "prefix": prefix, "error": str(exc)[:200]},
        )
        return {"deleted": deleted, "errors": errors, "status": "error"}

    return {"deleted": deleted, "errors": errors, "status": "ok"}


def list_files(container: str, prefix: Optional[str] = None) -> List[str]:
    """
    List files in a container.
    
    Args:
        container: Container name
        prefix: Optional prefix to filter (e.g., "project_id/")
        
    Returns:
        List of blob names
    """
    client = get_blob_service_client()
    container_client = client.get_container_client(container)
    blobs = container_client.list_blobs(name_starts_with=prefix)
    return [b.name for b in blobs]


def list_files_with_meta(
    *,
    container: str,
    prefix: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """List blob names with lightweight metadata (best-effort)."""
    client = get_blob_service_client()
    container_client = client.get_container_client(container)
    out: List[Dict[str, Any]] = []
    try:
        for b in container_client.list_blobs(name_starts_with=prefix):
            item = {
                "name": getattr(b, "name", None),
                "size": getattr(b, "size", None),
                "last_modified": None,
            }
            lm = getattr(b, "last_modified", None)
            try:
                item["last_modified"] = lm.isoformat().replace("+00:00", "Z") if lm else None
            except Exception:
                item["last_modified"] = None
            out.append(item)
            if len(out) >= max(1, int(limit)):
                break
    except Exception as exc:
        _logger.warning(
            "blob.list_failed",
            extra={"container": container, "prefix": prefix, "error": str(exc)[:200]},
        )
        return []
    return out


def file_exists(container: str, blob_name: str) -> bool:
    """
    Check if a file exists in Azure Blob Storage.
    
    Args:
        container: Container name
        blob_name: Full blob path
        
    Returns:
        True if file exists
    """
    client = get_blob_service_client()
    blob = client.get_blob_client(container=container, blob=blob_name)
    return blob.exists()


def get_file_url(container: str, blob_name: str) -> str:
    """
    Get the URL of a blob (without downloading).
    
    Args:
        container: Container name
        blob_name: Full blob path
        
    Returns:
        Blob URL
    """
    client = get_blob_service_client()
    blob = client.get_blob_client(container=container, blob=blob_name)
    return blob.url


def tenant_upload(
    *,
    container: str,
    org_id: Optional[str],
    project_id: str,
    logical_path: str,
    data: Optional[bytes] = None,
    file_path: Optional[str] = None,
    content_type: Optional[str] = None,
    strict_tenant: bool = True,
) -> Dict[str, Any]:
    """
    Tenant-aware upload helper that centralizes mapping, upload and sha256 calculation.

    Returns a dict: {"container","name","url","sha256"}.
    """
    from pathlib import Path
    import hashlib

    if data is None and file_path is None:
        raise ValueError("Either data or file_path must be provided to tenant_upload")

    if strict_tenant:
        require_org_id(org_id, operation="tenant-scoped uploads")

    # Resolve blob name (may raise ValueError if logical_path invalid)
    blob_name = logical_path_to_blob_name(org_id=org_id, project_id=project_id, logical_path=logical_path)

    # Compute sha256 and size
    if data is not None:
        h = hashlib.sha256()
        h.update(data)
        sha = h.hexdigest()
        size = len(data)
        url = upload_file(container=container, blob_name=blob_name, data=data, content_type=content_type)
    else:
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(str(file_path))
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        sha = h.hexdigest()
        size = int(p.stat().st_size or 0)
        url = upload_local_path(container=container, blob_name=blob_name, file_path=file_path, content_type=content_type)

    # Build metadata
    base_metadata: Dict[str, Any] = {
        "org_id": org_id or "",
        "project_id": project_id,
        "logical_path": logical_path,
        "artifact_version": 1,
    }

    out = {
        "artifact_version": 1,
        "container": container,
        "name": blob_name,
        "logical_path": logical_path,
        "url": url,
        "sha256": sha,
        "content_type": content_type,
        "size_bytes": size,
        "metadata": base_metadata,
    }
    return out


def download_by_url(blob_url: str) -> bytes:
    """Download a blob given its full URL.

    Works for private containers because it uses the account connection string.
    The URL is used only to locate container + blob name.
    """
    if not blob_url or not blob_url.strip():
        raise ValueError("blob_url is empty")
    parsed = urlparse(blob_url.strip())
    host = (parsed.netloc or "").lower()
    if not host.endswith(".blob.core.windows.net"):
        raise ValueError("Unsupported blob host")

    path = (parsed.path or "").lstrip("/")
    parts = path.split("/", 1)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError("Invalid blob URL path")
    container = parts[0]
    blob_name = parts[1]
    return download_file(container=container, blob_name=blob_name)


def check_blob_storage_health() -> Dict[str, Any]:
    """Check whether Azure Blob Storage is configured and reachable.

    This function is designed for diagnostics/health endpoints.
    It never returns secrets (e.g., connection strings).
    """
    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not conn_str:
        return {
            "configured": False,
            "status": "not_configured",
            "message": "AZURE_STORAGE_CONNECTION_STRING no configurada",
        }

    if not _AZURE_BLOB_AVAILABLE:
        return {
            "configured": False,
            "status": "missing_dependency",
            "message": "Dependencia faltante: azure-storage-blob (Azure SDK).",
        }

    start = time.perf_counter()
    client = BlobServiceClient.from_connection_string(conn_str)
    # Forces a network call; will raise if creds/network are wrong.
    client.get_service_properties()
    latency_ms = int((time.perf_counter() - start) * 1000)

    interviews_container_exists = False
    try:
        interviews_container_exists = client.get_container_client(CONTAINER_INTERVIEWS).exists()
    except Exception as exc:
        _logger.warning(
            "blob.health.container_check_failed",
            extra={"container": CONTAINER_INTERVIEWS, "error": str(exc)[:200]},
        )

    return {
        "configured": True,
        "status": "ok",
        "latency_ms": latency_ms,
        "account_name": getattr(client, "account_name", None),
        "interviews_container": {
            "name": CONTAINER_INTERVIEWS,
            "exists": interviews_container_exists,
        },
    }
