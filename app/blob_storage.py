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
import time
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional

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
