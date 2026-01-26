"""
Coding router - Code management, assignment, validation, and statistics endpoints.

This router handles the core coding workflow for qualitative analysis.
"""
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body, BackgroundTasks
import structlog
from functools import lru_cache
import os
from datetime import datetime
import time
from pathlib import Path
import re
import random
import json
import traceback

from pydantic import BaseModel, Field

from app.clients import ServiceClients, build_service_clients
from app.coding_runner_core import normalize_resume_state
from app.project_state import resolve_project
from app.settings import AppSettings, load_settings
from backend.auth import User, get_current_user

# Logger
api_logger = structlog.get_logger("app.api.coding")

def _allow_local_artifacts_fallback() -> bool:
    return os.getenv("ARTIFACTS_ALLOW_LOCAL_FALLBACK", "false").strip().lower() in {"1", "true", "yes"}


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    env_file = os.getenv("APP_ENV_FILE")
    return load_settings(env_file)


def build_clients_or_error(settings: AppSettings) -> ServiceClients:
    try:
        return build_service_clients(settings)
    except Exception as exc:
        from app.error_handling import api_error, ErrorCode

        raise api_error(
            status_code=502,
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Error conectando con servicios externos. Intente más tarde.",
            exc=exc,
        ) from exc


async def require_auth(user: User = Depends(get_current_user)) -> User:
    return user


class CodingSuggestRunnerExecuteRequest(BaseModel):
    project: str = Field(..., description="Proyecto")
    seed_fragment_id: str = Field(..., description="Fragmento inicial para el runner")
    steps: int = Field(5, ge=1, description="Pasos por entrevista")
    top_k: int = Field(5, ge=1, description="Cantidad de fragmentos similares a recuperar")
    strategy: Optional[str] = Field("best-score", description="Estrategia para escoger siguiente seed")
    interview_order: Optional[str] = Field("ingest-desc", description="Orden de entrevistas")
    max_interviews: Optional[int] = Field(200, ge=1, description="Máximo de entrevistas a procesar")
    archivo: Optional[str] = Field(None, description="Archivo inicial")
    include_coded: bool = Field(False, description="Incluir fragmentos ya codificados")
    submit_candidates: bool = Field(False, description="Insertar candidatos en Postgres")
    candidates_per_step: Optional[int] = Field(5, ge=1, description="Máximo de candidatos por paso")
    save_memos: bool = Field(True, description="Guardar memos en disco")
    llm_suggest: bool = Field(True, description="Habilitar sugerencias LLM")
    llm_model: Optional[str] = Field(None, description="Modelo LLM para sugerencias")
    min_new_unique_per_step: Optional[int] = Field(1, ge=0, description="Nuevos fragmentos únicos requeridos por paso")
    saturation_patience: Optional[int] = Field(3, ge=1, description="Pasos sin crecimiento antes de saturar")
    code_repeat_patience: Optional[int] = Field(3, ge=1, description="Repeticiones del mismo código antes de parar")
    area_tematica: Optional[str] = None
    actor_principal: Optional[str] = None
    requiere_protocolo_lluvia: Optional[bool] = None


class CodingSuggestRunnerResumeRequest(BaseModel):
    project: str
    task_id: str


class CodingSuggestRunnerStatusResponse(BaseModel):
    task_id: str
    status: str
    current_step: int
    total_steps: int
    visited_seeds: int
    unique_suggestions: int
    current_archivo: Optional[str]
    current_step_in_interview: int
    steps_per_interview: int
    interview_index: int
    interviews_total: int
    memos_saved: int
    candidates_submitted: int
    candidates_pending_before_db: Optional[int] = None
    candidates_pending_after_db: Optional[int] = None
    llm_calls: int
    llm_failures: int
    qdrant_failures: int
    qdrant_retries: int
    last_suggested_code: Optional[str]
    saturated: bool
    message: Optional[str]
    errors: Optional[List[str]] = None
    report_path: Optional[str] = None


class CodingSuggestRunnerResultResponse(BaseModel):
    task_id: str
    project: str
    status: str
    steps_requested: int
    steps_completed: int
    seed_fragment_id: str
    visited_seed_ids: List[str]
    suggestions: List[Dict[str, Any]]
    iterations: List[Dict[str, Any]]
    memos: List[Dict[str, Any]]
    candidates_submitted: int
    candidates_pending_before_db: Optional[int] = None
    candidates_pending_after_db: Optional[int] = None
    llm_calls: int
    llm_failures: int
    qdrant_failures: int
    qdrant_retries: int
    errors: Optional[List[str]] = None
    report_path: Optional[str] = None


class CodingSuggestRunnerMemosResponse(BaseModel):
    project: str
    archivo: Optional[str] = None
    archivo_slug: Optional[str] = None
    memos: List[Dict[str, Any]]
    count: int


class CodingNextResponse(BaseModel):
    project: str
    found: bool
    pending_total: int = 0
    pending_in_archivo: Optional[int] = None
    fragmento: Optional[Dict[str, Any]] = None
    suggested_codes: List[Dict[str, Any]] = []
    reasons: List[str] = []


class CodingFeedbackRequest(BaseModel):
    project: str = Field(..., description="Proyecto")
    fragmento_id: str = Field(..., description="ID del fragmento")
    archivo: Optional[str] = None
    action: str = Field(..., description="accept|reject|edit")
    suggested_code: Optional[str] = None
    final_code: Optional[str] = None
    source: Optional[str] = Field("next", description="Origen: next|manual|semantic|llm|runner")
    meta: Optional[Dict[str, Any]] = None


router = APIRouter(prefix="/api/coding", tags=["Coding"])
codes_router = APIRouter(prefix="/api/codes", tags=["Codes"])

_coding_suggest_runner_tasks: Dict[str, Dict[str, Any]] = {}


def _is_admin(user: User) -> bool:
    roles = user.roles or []
    return "admin" in set([str(r).strip().lower() for r in roles if r])


def _assert_task_access(*, task_id: str, task: Dict[str, Any], user: User) -> None:
    """Enforce that only the creator (or admin) can access a runner task."""
    auth = task.get("auth") or {}
    owner_user_id = str(auth.get("user_id") or "").strip()
    if not owner_user_id:
        # Backward-compat: older in-memory tasks may not have auth metadata.
        # Allow only admins to access to avoid cross-user leakage.
        if _is_admin(user):
            return
        raise HTTPException(status_code=403, detail="Forbidden: task has no owner metadata")

    if owner_user_id != str(user.user_id):
        if _is_admin(user):
            return
        raise HTTPException(status_code=403, detail="Forbidden: task belongs to another user")


def _assert_checkpoint_access(*, checkpoint: Dict[str, Any], user: User) -> None:
    """Enforce that only the creator (or admin) can resume a checkpoint."""
    auth = checkpoint.get("auth") or {}
    owner_user_id = str(auth.get("user_id") or "").strip()
    if not owner_user_id:
        if _is_admin(user):
            return
        raise HTTPException(status_code=403, detail="Forbidden: checkpoint has no owner metadata")

    if owner_user_id != str(user.user_id):
        if _is_admin(user):
            return
        raise HTTPException(status_code=403, detail="Forbidden: checkpoint belongs to another user")


def _save_runner_checkpoint(*, project: str, task_id: str, state: Dict[str, Any]) -> None:
    """Persist runner state for resume/post-mortem (Blob-first, strict multi-tenant)."""
    logical_path = f"logs/runner_checkpoints/{project}/{task_id}.json"
    data = json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8")
    org_id = str((state.get("auth") or {}).get("org") or os.getenv("API_KEY_ORG_ID") or "")

    try:
        from app.blob_storage import CONTAINER_REPORTS, tenant_upload

        tenant_upload(
            container=CONTAINER_REPORTS,
            org_id=org_id or "",
            project_id=project,
            logical_path=logical_path,
            data=data,
            content_type="application/json",
        )
        return
    except Exception as exc:
        api_logger.warning("coding.runner.checkpoint_blob_write_failed", error=str(exc)[:200], task_id=task_id)

    # Legacy/local fallback (dev).
    if not _allow_local_artifacts_fallback():
        return
    try:
        local = Path("logs") / "runner_checkpoints" / project
        local.mkdir(parents=True, exist_ok=True)
        (local / f"{task_id}.json").write_bytes(data)
    except Exception as exc:
        api_logger.warning("coding.runner.checkpoint_write_failed", error=str(exc), task_id=task_id)


def _load_runner_checkpoint(*, project: str, task_id: str, org_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    logical_path = f"logs/runner_checkpoints/{project}/{task_id}.json"
    try:
        from app.blob_storage import CONTAINER_REPORTS, download_file, logical_path_to_blob_name

        blob_name = logical_path_to_blob_name(org_id=org_id or "", project_id=project, logical_path=logical_path)
        data = download_file(CONTAINER_REPORTS, blob_name)
        return json.loads(data.decode("utf-8", errors="ignore") or "{}")
    except Exception:
        pass

    # Legacy/local fallback
    path = Path("logs") / "runner_checkpoints" / project / f"{task_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore") or "{}")
    except Exception as exc:
        api_logger.warning("coding.runner.checkpoint_read_failed", error=str(exc), task_id=task_id)
        return None


def _save_runner_report(*, project: str, task_id: str, report: Dict[str, Any]) -> Optional[str]:
    logical_path = f"logs/runner_reports/{project}/{task_id}.json"
    data = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    org_id = str((report.get("auth") or {}).get("org") or os.getenv("API_KEY_ORG_ID") or "")

    try:
        from app.blob_storage import CONTAINER_REPORTS, tenant_upload

        tenant_upload(
            container=CONTAINER_REPORTS,
            org_id=org_id or "",
            project_id=project,
            logical_path=logical_path,
            data=data,
            content_type="application/json",
        )
        return logical_path
    except Exception as exc:
        api_logger.warning("coding.runner.report_blob_write_failed", error=str(exc)[:200], task_id=task_id)

    # Legacy/local fallback (dev).
    if not _allow_local_artifacts_fallback():
        return None
    try:
        base_dir = Path("logs") / "runner_reports" / project
        base_dir.mkdir(parents=True, exist_ok=True)
        (base_dir / f"{task_id}.json").write_bytes(data)
        return logical_path
    except Exception as exc:
        api_logger.warning("coding.runner.report_write_failed", error=str(exc), task_id=task_id)
        return None


def _capture_qdrant_error(
    *,
    task_id: str,
    project: str,
    archivo: Optional[str],
    step: int,
    step_in_interview: int,
    seed_fragment_id: str,
    top_k: int,
    filters: Optional[Dict[str, Any]],
    attempt: int,
    exc: Exception,
) -> None:
    try:
        Path("logs").mkdir(parents=True, exist_ok=True)
        out_path = Path("logs") / "qdrant_errors.jsonl"
        record = {
            "ts": datetime.now().isoformat(),
            "task_id": task_id,
            "project": project,
            "archivo": archivo,
            "step": step,
            "step_in_interview": step_in_interview,
            "seed_fragment_id": seed_fragment_id,
            "top_k": top_k,
            "filters": filters,
            "attempt": attempt,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=6),
        }
        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        return


def _capture_llm_error(
    *,
    task_id: str,
    project: str,
    archivo: Optional[str],
    step: int,
    step_in_interview: int,
    seed_fragment_id: str,
    llm_model: str,
    attempt: int,
    exc: Exception,
) -> None:
    try:
        Path("logs").mkdir(parents=True, exist_ok=True)
        out_path = Path("logs") / "llm_errors.jsonl"
        record = {
            "ts": datetime.now().isoformat(),
            "task_id": task_id,
            "project": project,
            "archivo": archivo,
            "step": step,
            "step_in_interview": step_in_interview,
            "seed_fragment_id": seed_fragment_id,
            "llm_model": llm_model,
            "attempt": attempt,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=8),
        }
        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        return


def _capture_runner_error(
    *,
    task_id: str,
    project: str,
    archivo: Optional[str],
    step: Optional[int],
    step_in_interview: Optional[int],
    seed_fragment_id: Optional[str],
    stage: str,
    exc: Exception,
) -> None:
    try:
        base_dir = Path("logs") / "runner_checkpoints" / project
        base_dir.mkdir(parents=True, exist_ok=True)
        out_path = base_dir / "_errors.jsonl"
        record = {
            "ts": datetime.now().isoformat(),
            "task_id": task_id,
            "project": project,
            "archivo": archivo,
            "step": step,
            "step_in_interview": step_in_interview,
            "seed_fragment_id": seed_fragment_id,
            "stage": stage,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=8),
        }
        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        return


def _build_filters_from_request(req: CodingSuggestRunnerExecuteRequest) -> Dict[str, Any]:
    filters: Dict[str, Any] = {}
    # NOTE: archivo is handled per-interview in the runner; don't set it globally here.
    if req.area_tematica:
        filters["area_tematica"] = req.area_tematica
    if req.actor_principal:
        filters["actor_principal"] = req.actor_principal
    if req.requiere_protocolo_lluvia is not None:
        filters["requiere_protocolo_lluvia"] = bool(req.requiere_protocolo_lluvia)
    return filters


def _safe_slug(text: str, max_len: int = 60) -> str:
    text = (text or "").strip()
    if not text:
        return "untitled"
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return (text[:max_len] or "untitled")


def _is_transient_qdrant_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "qdrant" in msg
        and (
            "502" in msg
            or "bad gateway" in msg
            or "gateway" in msg
            or "timeout" in msg
            or "temporarily unavailable" in msg
        )
    )


def _sleep_backoff(attempt: int) -> None:
    # Exponential backoff with a little jitter.
    base = 0.75
    delay = min(6.0, base * (2 ** max(0, attempt - 1)))
    delay += random.uniform(0.0, 0.35)
    time.sleep(delay)


def _save_runner_memo(
    *,
    project: str,
    org_id: Optional[str] = None,
    archivo: str,
    step_global: int,
    step_in_interview: int,
    seed_fragment_id: str,
    suggested_code: Optional[str],
    confidence: Optional[str],
    ai_memo: Optional[str],
    fragments: List[Dict[str, Any]],
) -> Dict[str, str]:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    safe_archivo = _safe_slug(archivo, max_len=40)
    safe_code = _safe_slug(suggested_code or "sin_codigo", max_len=30)
    filename = f"{ts}_semantic_runner_{safe_archivo}_s{step_global:03d}_i{step_in_interview:02d}_{safe_code}.md"
    logical_path = f"notes/{project}/runner_semantic/{filename}"

    lines: List[str] = []
    lines.append(f"# Memo Runner Semántico: {suggested_code or '(sin código)'}")
    lines.append(f"**Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Proyecto:** {project}")
    lines.append(f"**Entrevista:** {archivo}")
    lines.append(f"**Seed:** {seed_fragment_id}")
    lines.append(f"**Paso (global):** {step_global}")
    lines.append(f"**Paso (entrevista):** {step_in_interview}")
    if confidence:
        lines.append(f"**Confianza IA:** {confidence}")

    lines.append("")
    lines.append(f"## Fragmentos (muestra) ({len(fragments)})")
    for idx, frag in enumerate(fragments[:12], 1):
        fid = frag.get("fragmento_id") or frag.get("id") or "?"
        src = frag.get("archivo") or archivo or "?"
        score = frag.get("score", 0.0)
        text = (frag.get("fragmento") or "")
        lines.append("")
        lines.append(f"### [{idx}] {src} ({float(score):.1%})")
        lines.append(f"**ID:** {fid}")
        if text:
            text_chunk = text[:800].replace('\n', ' ')
            lines.append(f"> {text_chunk}")

    if ai_memo:
        lines.append("")
        lines.append("## 🧠 Síntesis y decisión (IA)")
        lines.append("")
        lines.extend(ai_memo.splitlines())

    lines.append("\n---")
    lines.append("*Generado automáticamente por el Runner Semántico*")

    content = "\n".join(lines)

    blob_url: Optional[str] = None
    try:
        from app.blob_storage import CONTAINER_REPORTS, tenant_upload

        artifact = tenant_upload(
            container=CONTAINER_REPORTS,
            org_id=org_id or "",
            project_id=project,
            logical_path=logical_path,
            data=content.encode("utf-8"),
            content_type="text/markdown; charset=utf-8",
        )
        blob_url = artifact.get("url") if isinstance(artifact, dict) else None
    except Exception as exc:
        api_logger.warning("coding.runner.memo_blob_write_failed", error=str(exc)[:200], project=project)
        # Legacy/local fallback (dev).
        if not _allow_local_artifacts_fallback():
            pass
        else:
            try:
                base_dir = Path("notes") / project / "runner_semantic"
                base_dir.mkdir(parents=True, exist_ok=True)
                (base_dir / filename).write_text(content, encoding="utf-8")
            except Exception:
                pass

    rel_path = f"runner_semantic/{filename}"
    out: Dict[str, str] = {"path": logical_path, "rel": rel_path, "filename": filename}
    if blob_url:
        out["blob_url"] = blob_url
    return out


def _choose_next_seed(strategy: str, suggestions: List[Dict[str, Any]], visited: set[str]) -> Optional[str]:
    if not suggestions:
        return None
    candidates = [s for s in suggestions if str(s.get("fragmento_id") or "") and str(s.get("fragmento_id")) not in visited]
    if not candidates:
        return None
    if strategy == "first":
        return str(candidates[0]["fragmento_id"])
    # default: best-score
    candidates.sort(key=lambda s: float(s.get("score") or 0.0), reverse=True)
    return str(candidates[0]["fragmento_id"])


def _list_runner_semantic_memos(
    *,
    org_id: Optional[str],
    project: str,
    archivo: Optional[str],
    limit: int,
) -> Dict[str, Any]:
    project_id = str(project or "default")
    slug = _safe_slug(archivo or "", max_len=40) if (archivo and archivo.strip()) else None
    token = f"_semantic_runner_{slug}_" if slug else None

    # Blob-first (cloud mode)
    try:
        from app.blob_storage import CONTAINER_REPORTS, blob_name_to_logical_path, list_files_with_meta, tenant_prefix

        blob_prefix = tenant_prefix(org_id=org_id, project_id=project_id).rstrip("/") + "/notes/runner_semantic/"
        blobs = list_files_with_meta(container=CONTAINER_REPORTS, prefix=blob_prefix, limit=max(60, int(limit) * 6))
        items: List[Dict[str, Any]] = []
        for b in blobs:
            name = str(b.get("name") or "")
            if not name:
                continue
            logical = blob_name_to_logical_path(org_id=org_id, project_id=project_id, blob_name=name) or ""
            filename = logical.replace("\\", "/").split("/")[-1] if logical else name.split("/")[-1]
            if token and token not in filename:
                continue
            rel = ""
            if logical.startswith(f"notes/{project_id}/"):
                rel = logical[len(f"notes/{project_id}/") :]
            else:
                rel = filename
            items.append({"filename": filename, "rel": rel, "mtime": b.get("last_modified") or ""})

        items.sort(key=lambda x: str(x.get("mtime") or ""), reverse=True)
        if limit > 0:
            items = items[:limit]
        return {"project": project_id, "archivo": archivo, "archivo_slug": slug, "memos": items, "count": len(items)}
    except Exception:
        pass

    # Legacy/local fallback (dev)
    base_dir = Path("notes") / project_id / "runner_semantic"
    if not base_dir.exists() or not base_dir.is_dir():
        return {"project": project_id, "archivo": archivo, "archivo_slug": None, "memos": [], "count": 0}

    items_local: List[Dict[str, Any]] = []
    try:
        for file_path in base_dir.glob("*.md"):
            if not file_path.is_file():
                continue
            name = file_path.name
            if token and token not in name:
                continue
            try:
                rel = file_path.relative_to(Path("notes") / project_id).as_posix()
            except Exception:
                rel = name
            try:
                mtime = file_path.stat().st_mtime
            except Exception:
                mtime = 0.0
            items_local.append({"filename": name, "rel": rel, "mtime": mtime})
    except Exception as exc:
        api_logger.warning("coding.runner.memos_list_failed", error=str(exc), project=project_id, archivo=archivo)
        return {"project": project_id, "archivo": archivo, "archivo_slug": slug, "memos": [], "count": 0}

    items_local.sort(key=lambda x: float(x.get("mtime") or 0.0), reverse=True)
    if limit > 0:
        items_local = items_local[:limit]
    return {"project": project_id, "archivo": archivo, "archivo_slug": slug, "memos": items_local, "count": len(items_local)}


def _existing_fragment_ids(
    *,
    clients: ServiceClients,
    project_id: str,
    ids: List[str],
) -> set[str]:
    """Return the subset of fragment IDs that exist in entrevista_fragmentos for the project."""
    clean = [i for i in ids if i]
    if not clean:
        return set()

    # psycopg2 safe IN clause
    placeholders = ",".join(["%s"] * len(clean))
    sql = f"SELECT id FROM entrevista_fragmentos WHERE project_id = %s AND id IN ({placeholders})"
    params: List[Any] = [project_id]
    params.extend(clean)
    with clients.postgres.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall() or []
    return {str(r[0]) for r in rows if r and r[0]}


def _run_coding_suggest_runner_task(
    *,
    task_id: str,
    req: CodingSuggestRunnerExecuteRequest,
    settings: AppSettings,
    resume_state: Optional[Dict[str, Any]] = None,
) -> None:
    from app.coding import suggest_similar_fragments, CodingError, list_available_interviews, list_open_codes, suggest_code_from_fragments
    from app.postgres_block import (
        list_fragments_for_file,
        fetch_fragment_by_id,
        ensure_candidate_codes_table,
        count_pending_candidates,
        insert_candidate_codes,
    )

    task = _coding_suggest_runner_tasks.get(task_id)
    if not task:
        return
    task["status"] = "running"
    task.setdefault("errors", [])

    task_auth = task.get("auth") or {}

    clients = build_clients_or_error(settings)
    last_checkpoint_state: Optional[Dict[str, Any]] = None
    try:
        project_id = str(req.project or "default")

        # Snapshot canonical backlog size once (avoid polling DB from /status)
        try:
            pending_before = int(count_pending_candidates(clients.postgres, project_id))
        except Exception as exc:
            pending_before = None
            task.setdefault("errors", []).append(f"No se pudo contar pendientes (inicio): {exc}")
            _capture_runner_error(
                task_id=task_id,
                project=project_id,
                archivo=None,
                step=None,
                step_in_interview=None,
                seed_fragment_id=req.seed_fragment_id,
                stage="pending_count_start",
                exc=exc,
            )
        task["candidates_pending_before_db"] = pending_before
        task["candidates_pending_after_db"] = None
        seed_input = (req.seed_fragment_id or "").strip()
        if not seed_input:
            raise ValueError("seed_fragment_id requerido")

        top_k = max(1, int(req.top_k))
        steps_per_interview = max(1, int(req.steps))
        base_filters = _build_filters_from_request(req)

        # Preload existing codes once (helps LLM avoid duplicates)
        existing_codes: List[str] = [
            str(c.get("codigo")) for c in list_open_codes(clients, project_id, limit=200) if c.get("codigo")
        ]

        # Prepare candidate table if needed
        if req.submit_candidates:
            ensure_candidate_codes_table(clients.postgres)

        # Interviews (persisted for resume)
        resume_data = normalize_resume_state(resume_state)
        archivos: List[str] = []
        start_archivo = (req.archivo or "").strip() or None
        if resume_data.archivos:
            archivos = list(resume_data.archivos)
        else:
            interviews_raw = list_available_interviews(
                clients,
                project_id,
                limit=max(1, int(req.max_interviews or 200)),
                order=req.interview_order or "ingest-desc",
                include_analyzed=True,
            )
            interviews: List[Dict[str, Any]] = list(interviews_raw or [])
            archivos = [str(i.get("archivo")) for i in interviews if i.get("archivo")]
            if not archivos:
                raise ValueError("No hay entrevistas disponibles para este proyecto")

            # Start from selected archivo if provided
            if start_archivo and start_archivo in archivos:
                start_idx = archivos.index(start_archivo)
                archivos = archivos[start_idx:] + archivos[:start_idx]

        task["interviews_total"] = len(archivos)
        task["steps_per_interview"] = steps_per_interview
        # Expose global total steps for UI (even if the runner stops earlier)
        task["total_steps"] = steps_per_interview * len(archivos)

        # Resume-aware state
        visited_seeds_global: set[str] = set(resume_data.visited_seeds_global)
        visited_seed_ids: List[str] = list(resume_data.visited_seed_ids)
        union_by_id_global: Dict[str, Dict[str, Any]] = dict(resume_data.union_by_id_global)

        iterations: List[Dict[str, Any]] = list(resume_data.iterations)
        memos: List[Dict[str, Any]] = list(resume_data.memos)
        candidates_total = resume_data.candidates_total
        task["memos_saved"] = resume_data.memos_saved or task.get("memos_saved", 0) or 0
        task["candidates_submitted"] = candidates_total
        task["llm_calls"] = resume_data.llm_calls or task.get("llm_calls", 0) or 0
        task["llm_failures"] = resume_data.llm_failures or task.get("llm_failures", 0) or 0
        task["qdrant_failures"] = resume_data.qdrant_failures or task.get("qdrant_failures", 0) or 0
        task["qdrant_retries"] = resume_data.qdrant_retries or task.get("qdrant_retries", 0) or 0
        task["last_suggested_code"] = resume_data.last_suggested_code or task.get("last_suggested_code")
        task["saturated"] = bool(resume_data.saturated)

        resume_cursor = resume_data.cursor or {}
        resume_interview_index = int(resume_cursor.get("interview_index") or 0)
        resume_step_in_interview_completed = int(resume_cursor.get("step_in_interview_completed") or 0)
        resume_next_seed = (resume_cursor.get("next_seed") or "")
        global_step = int(resume_cursor.get("global_step_completed") or 0)
        task["current_step"] = global_step
        task["interview_index"] = max(0, resume_interview_index)

        # Persist initial checkpoint (useful for post-mortem)
        last_checkpoint_state = {
            "auth": task_auth,
            "status": "running",
            "req": req.model_dump(),
            "archivos": archivos,
            "visited_seeds_global": sorted(list(visited_seeds_global))[:50000],
            "visited_seed_ids": visited_seed_ids[-50000:],
            "union_by_id_global": list(union_by_id_global.values()),
            "iterations": iterations,
            "memos": memos,
            "candidates_total": candidates_total,
            "memos_saved": int(task.get("memos_saved", 0)),
            "llm_calls": int(task.get("llm_calls", 0)),
            "llm_failures": int(task.get("llm_failures", 0)),
            "qdrant_failures": int(task.get("qdrant_failures", 0)),
            "qdrant_retries": int(task.get("qdrant_retries", 0)),
            "last_suggested_code": task.get("last_suggested_code"),
            "saturated": bool(task.get("saturated", False)),
            "cursor": {
                "interview_index": resume_interview_index,
                "archivo": archivos[resume_interview_index - 1] if resume_interview_index and resume_interview_index <= len(archivos) else None,
                "step_in_interview_completed": resume_step_in_interview_completed,
                "next_seed": resume_next_seed,
                "global_step_completed": global_step,
            },
        }
        _save_runner_checkpoint(
            project=project_id,
            task_id=task_id,
            state=last_checkpoint_state,
        )

        for idx, archivo in enumerate(archivos, 1):
            if resume_interview_index and idx < resume_interview_index:
                continue
            task["interview_index"] = idx
            task["current_archivo"] = archivo
            task["current_step_in_interview"] = 0
            task["message"] = f"Entrevista {idx}/{len(archivos)}: {archivo}" 

            # Reset per-interview state (resume-aware)
            union_by_id_local: Dict[str, Dict[str, Any]] = {}
            visited_seeds_local: set[str] = set()
            no_growth_streak = 0
            repeat_code_streak = 0
            last_code: Optional[str] = None

            fragments = list_fragments_for_file(clients.postgres, project_id, archivo, limit=10000)
            seed_queue = [str(f.get("fragmento_id") or "") for f in fragments if f.get("fragmento_id")]
            seed_queue = [s for s in seed_queue if s]
            if not seed_queue:
                continue

            # Choose initial seed (resume > explicit seed > first fragment)
            if resume_interview_index == idx and resume_next_seed:
                seed = str(resume_next_seed)
            elif idx == 1 and start_archivo == archivo and seed_input:
                seed = seed_input
            else:
                seed = seed_queue[0]

            # Ensure seed exists in this archivo; otherwise fall back
            seed_meta = fetch_fragment_by_id(clients.postgres, seed, project_id)
            if not seed_meta or seed_meta.get("archivo") != archivo:
                seed = seed_queue[0]

            start_step = 1
            if resume_interview_index == idx and resume_step_in_interview_completed:
                start_step = min(steps_per_interview + 1, resume_step_in_interview_completed + 1)
            for step_in_interview in range(start_step, steps_per_interview + 1):
                global_step += 1
                task["current_step"] = global_step
                task["current_step_in_interview"] = step_in_interview

                visited_seeds_local.add(seed)
                visited_seeds_global.add(seed)
                visited_seed_ids.append(seed)

                # Per-interview filters: force archivo to current
                filters = dict(base_filters)
                filters["archivo"] = archivo

                start = time.perf_counter()
                result = None
                qdrant_attempts = 0
                while True:
                    try:
                        result = suggest_similar_fragments(
                            clients,
                            settings,
                            fragment_id=seed,
                            top_k=top_k,
                            filters=filters or None,
                            exclude_coded=(not bool(req.include_coded)),
                            project=project_id,
                            persist=False,
                            llm_model=None,
                        )
                        break
                    except Exception as exc:
                        _capture_qdrant_error(
                            task_id=task_id,
                            project=project_id,
                            archivo=archivo,
                            step=global_step,
                            step_in_interview=step_in_interview,
                            seed_fragment_id=seed,
                            top_k=top_k,
                            filters=filters or None,
                            attempt=qdrant_attempts + 1,
                            exc=exc,
                        )
                        if _is_transient_qdrant_error(exc) and qdrant_attempts < 3:
                            qdrant_attempts += 1
                            task["qdrant_retries"] = int(task.get("qdrant_retries", 0)) + 1
                            task["message"] = (
                                f"Qdrant temporalmente no disponible (reintento {qdrant_attempts}/3). "
                                f"Entrevista {idx}/{len(archivos)}: {archivo}"
                            )
                            _sleep_backoff(qdrant_attempts)
                            continue

                        # Non-transient or exhausted retries: don't kill the whole run.
                        task["qdrant_failures"] = int(task.get("qdrant_failures", 0)) + 1
                        err_msg = f"No se pudo consultar Qdrant ({exc})"
                        task.setdefault("errors", []).append(err_msg)
                        _capture_runner_error(
                            task_id=task_id,
                            project=project_id,
                            archivo=archivo,
                            step=global_step,
                            step_in_interview=step_in_interview,
                            seed_fragment_id=seed,
                            stage="qdrant_failure",
                            exc=exc,
                        )

                        iterations.append({
                            "step": global_step,
                            "step_in_interview": step_in_interview,
                            "archivo": archivo,
                            "seed_fragment_id": seed,
                            "returned": 0,
                            "orphan_filtered": 0,
                            "elapsed_ms": round((time.perf_counter() - start) * 1000.0, 2),
                            "new_unique": 0,
                            "suggested_code": None,
                            "confidence": None,
                            "memo_path": None,
                            "candidates_inserted": 0,
                            "error": err_msg,
                        })

                        # Skip to next unvisited seed within this interview
                        next_seed = None
                        for candidate_seed in seed_queue:
                            if candidate_seed and candidate_seed not in visited_seeds_local:
                                next_seed = candidate_seed
                                break
                        if not next_seed:
                            task["message"] = f"Qdrant no disponible y sin semillas restantes en {archivo}"
                            break
                        seed = next_seed
                        # Continue loop (next iteration) without raising
                        result = {"suggestions": []}
                        break
                elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)

                raw_suggestions = list((result or {}).get("suggestions") or [])
                suggested_ids = [str(s.get("fragmento_id") or "") for s in raw_suggestions]
                existing_ids = _existing_fragment_ids(clients=clients, project_id=project_id, ids=suggested_ids)
                filtered_suggestions = [s for s in raw_suggestions if str(s.get("fragmento_id") or "") in existing_ids]
                orphan_count = max(0, len(raw_suggestions) - len(filtered_suggestions))
                raw_suggestions = filtered_suggestions

                # Update unions (local + global)
                before_local = len(union_by_id_local)
                for s in raw_suggestions:
                    frag_id = str(s.get("fragmento_id") or "")
                    if not frag_id:
                        continue
                    prev = union_by_id_local.get(frag_id)
                    if not prev or float(s.get("score") or 0.0) > float(prev.get("score") or 0.0):
                        union_by_id_local[frag_id] = s
                    prev_g = union_by_id_global.get(frag_id)
                    if not prev_g or float(s.get("score") or 0.0) > float(prev_g.get("score") or 0.0):
                        union_by_id_global[frag_id] = s
                after_local = len(union_by_id_local)
                new_unique = max(0, after_local - before_local)

                # LLM suggestion per iteration
                suggested_code: Optional[str] = None
                ai_memo: Optional[str] = None
                confidence: Optional[str] = None
                if req.llm_suggest:
                    # Build fragment pack: seed + top suggestions
                    seed_row = fetch_fragment_by_id(clients.postgres, seed, project_id)
                    fragment_pack: List[Dict[str, Any]] = []
                    if seed_row:
                        fragment_pack.append({
                            "fragmento_id": seed_row.get("id"),
                            "archivo": seed_row.get("archivo"),
                            "fragmento": seed_row.get("fragmento"),
                            "score": 1.0,
                        })
                    for s in raw_suggestions[: min(8, len(raw_suggestions))]:
                        fragment_pack.append({
                            "fragmento_id": s.get("fragmento_id"),
                            "archivo": s.get("archivo"),
                            "fragmento": s.get("fragmento"),
                            "score": float(s.get("score") or 0.0),
                        })

                    if fragment_pack:
                        llm_attempts = 0
                        last_llm_error: Optional[Exception] = None
                        while llm_attempts < 3 and not suggested_code:
                            llm_attempts += 1
                            try:
                                task["llm_calls"] = int(task.get("llm_calls", 0)) + 1
                                llm_result = suggest_code_from_fragments(
                                    clients=clients,
                                    settings=settings,
                                    fragments=fragment_pack,
                                    existing_codes=existing_codes,
                                    llm_model=req.llm_model,
                                    project=project_id,
                                )
                                suggested_code = (llm_result.get("suggested_code") or "").strip() or None
                                ai_memo = (llm_result.get("memo") or "").strip() or None
                                confidence = llm_result.get("confidence")
                                task["last_suggested_code"] = suggested_code

                                if suggested_code:
                                    api_logger.info(
                                        "api.coding.suggest_runner.llm_suggested_code",
                                        task_id=task_id,
                                        project=project_id,
                                        archivo=archivo,
                                        step=global_step,
                                        suggested_code=suggested_code,
                                        confidence=confidence,
                                    )

                                    if suggested_code not in existing_codes:
                                        existing_codes.append(suggested_code)
                                    break

                                # Missing suggested_code is a failure we can retry.
                                raise RuntimeError(
                                    "LLM no devolvió suggested_code (JSON inválido o respuesta vacía). "
                                    "Revisa Azure OpenAI / deployment_chat y logs."
                                )
                            except Exception as exc:
                                last_llm_error = exc
                                _capture_llm_error(
                                    task_id=task_id,
                                    project=project_id,
                                    archivo=archivo,
                                    step=global_step,
                                    step_in_interview=step_in_interview,
                                    seed_fragment_id=seed,
                                    llm_model=str(req.llm_model or "chat"),
                                    attempt=llm_attempts,
                                    exc=exc,
                                )
                                task["llm_failures"] = int(task.get("llm_failures", 0)) + 1
                                task.setdefault("errors", []).append(
                                    f"LLM error (step={global_step} archivo={archivo} attempt={llm_attempts}/3): {exc}"
                                )
                                _capture_runner_error(
                                    task_id=task_id,
                                    project=project_id,
                                    archivo=archivo,
                                    step=global_step,
                                    step_in_interview=step_in_interview,
                                    seed_fragment_id=seed,
                                    stage="llm_failure",
                                    exc=exc,
                                )
                                _sleep_backoff(llm_attempts)

                        if not suggested_code and last_llm_error is not None:
                            if bool(getattr(req, "continue_on_llm_failure", True)):
                                # Continue the run: skip candidates/memo content for this step.
                                task["message"] = (
                                    f"LLM falló (step={global_step}). Se omite este paso y se continúa con la siguiente semilla."
                                )
                            else:
                                raise RuntimeError(
                                    f"LLM suggest failed (step={global_step} archivo={archivo}): {last_llm_error}"
                                ) from last_llm_error

                # Memo per iteration
                memo_info: Optional[Dict[str, str]] = None
                if req.save_memos:
                    try:
                        memo_info = _save_runner_memo(
                            project=project_id,
                            org_id=str((task_auth or {}).get("org") or ""),
                            archivo=archivo,
                            step_global=global_step,
                            step_in_interview=step_in_interview,
                            seed_fragment_id=seed,
                            suggested_code=suggested_code,
                            confidence=confidence,
                            ai_memo=ai_memo,
                            fragments=[
                                {
                                    "fragmento_id": s.get("fragmento_id"),
                                    "archivo": s.get("archivo"),
                                    "score": float(s.get("score") or 0.0),
                                    "fragmento": s.get("fragmento"),
                                }
                                for s in raw_suggestions[: min(12, len(raw_suggestions))]
                            ],
                        )
                        task["memos_saved"] = int(task.get("memos_saved", 0)) + 1
                        memos.append({
                            "archivo": archivo,
                            "step": global_step,
                            "step_in_interview": step_in_interview,
                            "seed_fragment_id": seed,
                            "suggested_code": suggested_code,
                            **(memo_info or {}),
                        })
                    except Exception as exc:
                        task.setdefault("errors", []).append(f"Memo save failed (step={global_step} archivo={archivo}): {exc}")
                        _capture_runner_error(
                            task_id=task_id,
                            project=project_id,
                            archivo=archivo,
                            step=global_step,
                            step_in_interview=step_in_interview,
                            seed_fragment_id=seed,
                            stage="memo_save",
                            exc=exc,
                        )

                # Submit candidates per iteration
                inserted = 0
                if req.submit_candidates and suggested_code:
                    n = max(1, int(req.candidates_per_step or 5))
                    chosen = raw_suggestions[: min(n, len(raw_suggestions))]
                    candidates = []
                    for s in chosen:
                        frag_text = (s.get("fragmento") or "")
                        candidates.append({
                            "project_id": project_id,
                            "codigo": suggested_code,
                            "cita": frag_text[:500],
                            "fragmento_id": s.get("fragmento_id"),
                            "archivo": s.get("archivo") or archivo,
                            "fuente_origen": "semantic_suggestion",
                            "fuente_detalle": f"Runner Semántico (task_id={task_id} archivo={archivo}) step={global_step} seed={seed}",
                            "memo": ai_memo,
                            "score_confianza": float(s.get("score") or 0.0),
                        })
                    try:
                        inserted = insert_candidate_codes(clients.postgres, candidates, check_similar=True)
                        candidates_total += inserted
                        task["candidates_submitted"] = candidates_total
                    except Exception as exc:
                        task.setdefault("errors", []).append(f"Candidate insert failed (step={global_step} archivo={archivo}): {exc}")
                        _capture_runner_error(
                            task_id=task_id,
                            project=project_id,
                            archivo=archivo,
                            step=global_step,
                            step_in_interview=step_in_interview,
                            seed_fragment_id=seed,
                            stage="candidate_insert",
                            exc=exc,
                        )

                iterations.append({
                    "step": global_step,
                    "step_in_interview": step_in_interview,
                    "archivo": archivo,
                    "seed_fragment_id": seed,
                    "returned": len(raw_suggestions),
                    "orphan_filtered": orphan_count,
                    "elapsed_ms": elapsed_ms,
                    "new_unique": new_unique,
                    "suggested_code": suggested_code,
                    "confidence": confidence,
                    "memo_path": (memo_info or {}).get("path") if memo_info else None,
                    "candidates_inserted": inserted,
                })

                # Update status counters
                task["visited_seeds"] = len(visited_seeds_global)
                task["unique_suggestions"] = len(union_by_id_global)

                # Saturation rules
                if new_unique < max(0, int(req.min_new_unique_per_step or 1)):
                    no_growth_streak += 1
                else:
                    no_growth_streak = 0

                if suggested_code and last_code and suggested_code == last_code:
                    repeat_code_streak += 1
                else:
                    repeat_code_streak = 0
                last_code = suggested_code or last_code

                if no_growth_streak >= max(1, int(req.saturation_patience or 3)):
                    task["saturated"] = True
                    task["message"] = f"Saturación detectada en {archivo} (sin nuevos únicos por {no_growth_streak} pasos)"
                    break
                if repeat_code_streak >= max(1, int(req.code_repeat_patience or 3)):
                    task["saturated"] = True
                    task["message"] = f"Saturación detectada en {archivo} (código repetido por {repeat_code_streak} pasos)"
                    break

                # Next seed: from suggestions, else from unvisited fragments in interview
                next_seed = _choose_next_seed(req.strategy or "best-score", raw_suggestions, visited_seeds_local)
                if not next_seed:
                    # fallback: next unvisited seed from the interview
                    next_seed = None
                    for candidate_seed in seed_queue:
                        if candidate_seed and candidate_seed not in visited_seeds_local:
                            next_seed = candidate_seed
                            break

                if not next_seed:
                    task["message"] = f"Sin semillas restantes en {archivo}"
                    break
                seed = next_seed

                # Checkpoint after a successful step (or Qdrant-skipped step)
                try:
                    last_checkpoint_state = {
                        "auth": task_auth,
                        "status": "running",
                        "req": req.model_dump(),
                        "archivos": archivos,
                        "visited_seeds_global": sorted(list(visited_seeds_global))[:50000],
                        "visited_seed_ids": visited_seed_ids[-50000:],
                        "union_by_id_global": list(union_by_id_global.values()),
                        "iterations": iterations,
                        "memos": memos,
                        "candidates_total": candidates_total,
                        "memos_saved": int(task.get("memos_saved", 0)),
                        "llm_calls": int(task.get("llm_calls", 0)),
                        "llm_failures": int(task.get("llm_failures", 0)),
                        "qdrant_failures": int(task.get("qdrant_failures", 0)),
                        "qdrant_retries": int(task.get("qdrant_retries", 0)),
                        "last_suggested_code": task.get("last_suggested_code"),
                        "saturated": bool(task.get("saturated", False)),
                        "cursor": {
                            "interview_index": idx,
                            "archivo": archivo,
                            "step_in_interview_completed": step_in_interview,
                            "next_seed": seed,
                            "global_step_completed": global_step,
                        },
                    }
                    _save_runner_checkpoint(
                        project=project_id,
                        task_id=task_id,
                        state=last_checkpoint_state,
                    )
                except Exception:
                    pass

            # Continue next interview

        final_suggestions = list(union_by_id_global.values())
        final_suggestions.sort(key=lambda s: float(s.get("score") or 0.0), reverse=True)

        task["result"] = {
            "task_id": task_id,
            "project": project_id,
            "status": "completed",
            "steps_requested": steps_per_interview,
            "steps_completed": len(iterations),
            "seed_fragment_id": req.seed_fragment_id,
            "visited_seed_ids": visited_seed_ids,
            "suggestions": final_suggestions,
            "iterations": iterations,
            "memos": memos,
            "candidates_submitted": candidates_total,
            "candidates_pending_before_db": task.get("candidates_pending_before_db"),
            "llm_calls": int(task.get("llm_calls", 0)),
            "llm_failures": int(task.get("llm_failures", 0)),
            "qdrant_failures": int(task.get("qdrant_failures", 0)),
            "qdrant_retries": int(task.get("qdrant_retries", 0)),
            "errors": task.get("errors") or None,
        }
        task["status"] = "completed"
        task["message"] = "Runner completado"

        # Snapshot canonical backlog size at end
        try:
            pending_after = int(count_pending_candidates(clients.postgres, project_id))
        except Exception as exc:
            pending_after = None
            task.setdefault("errors", []).append(f"No se pudo contar pendientes (final): {exc}")
            _capture_runner_error(
                task_id=task_id,
                project=project_id,
                archivo=task.get("current_archivo"),
                step=int(task.get("current_step") or 0) or None,
                step_in_interview=int(task.get("current_step_in_interview") or 0) or None,
                seed_fragment_id=req.seed_fragment_id,
                stage="pending_count_final",
                exc=exc,
            )
        task["candidates_pending_after_db"] = pending_after
        task["result"]["candidates_pending_after_db"] = pending_after

        # Final checkpoint for completed runs
        try:
            last_checkpoint_state = {
                "auth": task_auth,
                "status": "completed",
                "req": req.model_dump(),
                "archivos": archivos,
                "visited_seeds_global": sorted(list(visited_seeds_global))[:50000],
                "visited_seed_ids": visited_seed_ids[-50000:],
                "union_by_id_global": list(union_by_id_global.values()),
                "iterations": iterations,
                "memos": memos,
                "candidates_total": candidates_total,
                "memos_saved": int(task.get("memos_saved", 0)),
                "llm_calls": int(task.get("llm_calls", 0)),
                "llm_failures": int(task.get("llm_failures", 0)),
                "qdrant_failures": int(task.get("qdrant_failures", 0)),
                "qdrant_retries": int(task.get("qdrant_retries", 0)),
                "last_suggested_code": task.get("last_suggested_code"),
                "saturated": bool(task.get("saturated", False)),
                "cursor": {
                    "interview_index": len(archivos),
                    "archivo": archivos[-1] if archivos else None,
                    "step_in_interview_completed": steps_per_interview,
                    "next_seed": None,
                    "global_step_completed": global_step,
                },
            }
            _save_runner_checkpoint(
                project=project_id,
                task_id=task_id,
                state=last_checkpoint_state,
            )
        except Exception:
            pass

        # Persist a compact report for post-mortem and traceability
        try:
            report = {
                "ts": datetime.now().isoformat(),
                "task_id": task_id,
                "project": project_id,
                "auth": task_auth,
                "status": "completed",
                "started_at": task.get("started_at"),
                "finished_at": datetime.now().isoformat(),
                "steps_requested": steps_per_interview,
                "steps_completed": len(iterations),
                "interviews_total": len(archivos),
                "memos_saved": int(task.get("memos_saved", 0)),
                "candidates_submitted": int(task.get("candidates_submitted", 0)),
                "candidates_pending_before_db": task.get("candidates_pending_before_db"),
                "candidates_pending_after_db": task.get("candidates_pending_after_db"),
                "llm_calls": int(task.get("llm_calls", 0)),
                "llm_failures": int(task.get("llm_failures", 0)),
                "qdrant_failures": int(task.get("qdrant_failures", 0)),
                "qdrant_retries": int(task.get("qdrant_retries", 0)),
                "saturated": bool(task.get("saturated", False)),
                "errors": task.get("errors") or None,
                "checkpoint_path": f"logs/runner_checkpoints/{project_id}/{task_id}.json",
                "memos_count": len(memos),
            }
            report_path = _save_runner_report(project=project_id, task_id=task_id, report=report)
            if report_path:
                task["report_path"] = report_path
                task["result"]["report_path"] = report_path
        except Exception:
            pass

    except Exception as exc:
        task["status"] = "error"
        task["message"] = str(exc)
        task.setdefault("errors", []).append(str(exc))
        seed_for_error: Optional[str] = None
        try:
            seed_for_error = seed  # type: ignore[name-defined]
        except Exception:
            seed_for_error = None
        _capture_runner_error(
            task_id=task_id,
            project=str(req.project or "default"),
            archivo=task.get("current_archivo"),
            step=int(task.get("current_step") or 0) or None,
            step_in_interview=int(task.get("current_step_in_interview") or 0) or None,
            seed_fragment_id=seed_for_error or req.seed_fragment_id,
            stage="fatal",
            exc=exc,
        )
        # Persist checkpoint on fatal error so we can resume later.
        try:
            project_id = str(req.project or "default")
            error_state = dict(last_checkpoint_state or {
                "auth": task_auth,
                "status": "running",
                "req": req.model_dump(),
                "archivos": [],
                "visited_seeds_global": [],
                "visited_seed_ids": [],
                "union_by_id_global": [],
                "iterations": [],
                "memos": [],
                "candidates_total": 0,
                "memos_saved": int(task.get("memos_saved", 0)),
                "llm_calls": int(task.get("llm_calls", 0)),
                "llm_failures": int(task.get("llm_failures", 0)),
                "qdrant_failures": int(task.get("qdrant_failures", 0)),
                "qdrant_retries": int(task.get("qdrant_retries", 0)),
                "last_suggested_code": task.get("last_suggested_code"),
                "saturated": bool(task.get("saturated", False)),
                "cursor": {},
            })
            error_state["status"] = "error"
            error_state["fatal_error"] = str(exc)
            _save_runner_checkpoint(project=project_id, task_id=task_id, state=error_state)
        except Exception:
            pass

        # Persist report on fatal error (best-effort)
        try:
            project_id = str(req.project or "default")
            report = {
                "ts": datetime.now().isoformat(),
                "task_id": task_id,
                "project": project_id,
                "auth": task_auth,
                "status": "error",
                "started_at": task.get("started_at"),
                "finished_at": datetime.now().isoformat(),
                "steps_completed": int(task.get("current_step", 0)),
                "memos_saved": int(task.get("memos_saved", 0)),
                "candidates_submitted": int(task.get("candidates_submitted", 0)),
                "candidates_pending_before_db": task.get("candidates_pending_before_db"),
                "candidates_pending_after_db": task.get("candidates_pending_after_db"),
                "llm_calls": int(task.get("llm_calls", 0)),
                "llm_failures": int(task.get("llm_failures", 0)),
                "qdrant_failures": int(task.get("qdrant_failures", 0)),
                "qdrant_retries": int(task.get("qdrant_retries", 0)),
                "fatal_error": str(exc),
                "errors": task.get("errors") or None,
                "checkpoint_path": f"logs/runner_checkpoints/{project_id}/{task_id}.json",
            }
            report_path = _save_runner_report(project=project_id, task_id=task_id, report=report)
            if report_path:
                task["report_path"] = report_path
        except Exception:
            pass
    finally:
        clients.close()


@router.post("/suggest/runner/execute")
async def execute_coding_suggest_runner(
    request: CodingSuggestRunnerExecuteRequest,
    background_tasks: BackgroundTasks,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    # Multi-tenant: resolve canonical project_id and validate access.
    try:
        clients = build_clients_or_error(settings)
        try:
            project_id = resolve_project(request.project, allow_create=False, pg=clients.postgres)
        finally:
            clients.close()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Proyecto inválido: {exc}") from exc

    request.project = project_id
    task_id = f"coding_suggest_{project_id}_{datetime.now().strftime('%H%M%S')}"

    task_auth = {
        "user_id": str(user.user_id),
        "org": str(user.organization_id),
        "roles": list(user.roles or []),
    }

    _coding_suggest_runner_tasks[task_id] = {
        "status": "pending",
        "project": project_id,
        "auth": task_auth,
        "seed_fragment_id": request.seed_fragment_id,
        "current_step": 0,
        "total_steps": max(1, int(request.steps)),
        "visited_seeds": 0,
        "unique_suggestions": 0,
        "current_archivo": request.archivo,
        "current_step_in_interview": 0,
        "steps_per_interview": max(1, int(request.steps)),
        "interview_index": 0,
        "interviews_total": 0,
        "memos_saved": 0,
        "candidates_submitted": 0,
        "candidates_pending_before_db": None,
        "candidates_pending_after_db": None,
        "llm_calls": 0,
        "llm_failures": 0,
        "qdrant_failures": 0,
        "qdrant_retries": 0,
        "last_suggested_code": None,
        "saturated": False,
        "errors": [],
        "message": "Inicializando...",
        "started_at": datetime.now().isoformat(),
        "report_path": None,
    }

    api_logger.info(
        "api.coding.suggest_runner.started",
        task_id=task_id,
        project=project_id,
        seed_fragment_id=request.seed_fragment_id,
        steps=request.steps,
        top_k=request.top_k,
        strategy=request.strategy,
    )

    background_tasks.add_task(
        _run_coding_suggest_runner_task,
        task_id=task_id,
        req=request,
        settings=settings,
    )

    return {"task_id": task_id, "status": "started"}


@router.post("/suggest/runner/resume")
async def resume_coding_suggest_runner(
    request: CodingSuggestRunnerResumeRequest,
    background_tasks: BackgroundTasks,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    # Multi-tenant: resolve canonical project_id and validate access.
    try:
        clients = build_clients_or_error(settings)
        try:
            project_id = resolve_project(request.project, allow_create=False, pg=clients.postgres)
        finally:
            clients.close()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Proyecto inválido: {exc}") from exc

    checkpoint = _load_runner_checkpoint(project=project_id, task_id=request.task_id, org_id=str(user.organization_id))
    if not checkpoint:
        raise HTTPException(status_code=404, detail="Checkpoint not found for task")

    _assert_checkpoint_access(checkpoint=checkpoint, user=user)

    req_payload = checkpoint.get("req") or {}
    try:
        resumed_req = CodingSuggestRunnerExecuteRequest(**req_payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid checkpoint req payload: {exc}") from exc
    resumed_req.project = project_id

    # Start a new task id for the resumed run
    new_task_id = f"coding_suggest_{project_id}_resume_{datetime.now().strftime('%H%M%S')}"
    checkpoint_auth = checkpoint.get("auth") or {
        "user_id": str(user.user_id),
        "org": str(user.organization_id),
        "roles": list(user.roles or []),
    }
    _coding_suggest_runner_tasks[new_task_id] = {
        "status": "pending",
        "project": resumed_req.project,
        "auth": checkpoint_auth,
        "resumed_from": request.task_id,
        "resumed_by": {
            "user_id": str(user.user_id),
            "org": str(user.organization_id),
            "roles": list(user.roles or []),
        },
        "seed_fragment_id": resumed_req.seed_fragment_id,
        "current_step": int((checkpoint.get("cursor") or {}).get("global_step_completed") or 0),
        "total_steps": max(1, int(resumed_req.steps)),
        "visited_seeds": int(len(checkpoint.get("visited_seeds_global") or [])),
        "unique_suggestions": int(len(checkpoint.get("union_by_id_global") or [])),
        "current_archivo": (checkpoint.get("cursor") or {}).get("archivo") or resumed_req.archivo,
        "current_step_in_interview": int((checkpoint.get("cursor") or {}).get("step_in_interview_completed") or 0),
        "steps_per_interview": max(1, int(resumed_req.steps)),
        "interview_index": int((checkpoint.get("cursor") or {}).get("interview_index") or 0),
        "interviews_total": int(len(checkpoint.get("archivos") or [])),
        "memos_saved": int(checkpoint.get("memos_saved") or 0),
        "candidates_submitted": int(checkpoint.get("candidates_total") or 0),
        "llm_calls": int(checkpoint.get("llm_calls") or 0),
        "llm_failures": int(checkpoint.get("llm_failures") or 0),
        "qdrant_failures": int(checkpoint.get("qdrant_failures") or 0),
        "qdrant_retries": int(checkpoint.get("qdrant_retries") or 0),
        "last_suggested_code": checkpoint.get("last_suggested_code"),
        "saturated": bool(checkpoint.get("saturated") or False),
        "errors": [],
        "message": f"Reanudando desde checkpoint de {request.task_id}",
        "started_at": datetime.now().isoformat(),
    }

    api_logger.info(
        "api.coding.suggest_runner.resumed",
        previous_task_id=request.task_id,
        task_id=new_task_id,
        project=resumed_req.project,
    )

    background_tasks.add_task(
        _run_coding_suggest_runner_task,
        task_id=new_task_id,
        req=resumed_req,
        settings=settings,
        resume_state=checkpoint,
    )

    return {"task_id": new_task_id, "status": "started", "resumed_from": request.task_id}


@router.get("/suggest/runner/status/{task_id}", response_model=CodingSuggestRunnerStatusResponse)
async def get_coding_suggest_runner_status(
    task_id: str,
    user: User = Depends(require_auth),
) -> CodingSuggestRunnerStatusResponse:
    task = _coding_suggest_runner_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    _assert_task_access(task_id=task_id, task=task, user=user)
    return CodingSuggestRunnerStatusResponse(
        task_id=task_id,
        status=task.get("status", "pending"),
        current_step=int(task.get("current_step", 0)),
        total_steps=int(task.get("total_steps", 0)),
        visited_seeds=int(task.get("visited_seeds", 0)),
        unique_suggestions=int(task.get("unique_suggestions", 0)),
        current_archivo=task.get("current_archivo"),
        current_step_in_interview=int(task.get("current_step_in_interview", 0)),
        steps_per_interview=int(task.get("steps_per_interview", 0)),
        interview_index=int(task.get("interview_index", 0)),
        interviews_total=int(task.get("interviews_total", 0)),
        memos_saved=int(task.get("memos_saved", 0)),
        candidates_submitted=int(task.get("candidates_submitted", 0)),
        candidates_pending_before_db=task.get("candidates_pending_before_db"),
        candidates_pending_after_db=task.get("candidates_pending_after_db"),
        llm_calls=int(task.get("llm_calls", 0)),
        llm_failures=int(task.get("llm_failures", 0)),
        qdrant_failures=int(task.get("qdrant_failures", 0)),
        qdrant_retries=int(task.get("qdrant_retries", 0)),
        last_suggested_code=task.get("last_suggested_code"),
        saturated=bool(task.get("saturated", False)),
        message=task.get("message"),
        errors=task.get("errors") or None,
        report_path=task.get("report_path"),
    )


@router.get("/suggest/runner/result/{task_id}", response_model=CodingSuggestRunnerResultResponse)
async def get_coding_suggest_runner_result(
    task_id: str,
    user: User = Depends(require_auth),
) -> CodingSuggestRunnerResultResponse:
    task = _coding_suggest_runner_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    _assert_task_access(task_id=task_id, task=task, user=user)
    if task.get("status") != "completed":
        raise HTTPException(status_code=400, detail=f"Task not completed: {task.get('status')}")
    result = task.get("result") or {}
    return CodingSuggestRunnerResultResponse(**result)


@router.get("/suggest/runner/memos", response_model=CodingSuggestRunnerMemosResponse)
async def list_coding_suggest_runner_memos(
    project: str = Query(..., description="Proyecto requerido"),
    archivo: Optional[str] = Query(default=None, description="Filtrar por nombre de archivo (usa el mismo slug del runner)"),
    limit: int = Query(default=25, ge=1, le=200, description="Máximo de memos a retornar"),
    user: User = Depends(require_auth),
) -> CodingSuggestRunnerMemosResponse:
    try:
        project_id = resolve_project(project, allow_create=False)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Proyecto inválido: {exc}") from exc

    data = _list_runner_semantic_memos(
        org_id=str(getattr(user, "organization_id", None) or ""),
        project=project_id,
        archivo=archivo,
        limit=int(limit),
    )
    return CodingSuggestRunnerMemosResponse(**data)

# Note: This is a minimal implementation for the refactoring.
# Full coding endpoints to be migrated in future iterations.
# Current endpoints in app.py lines ~4093-5800 include:
# - /api/coding/suggestions, /assign, /suggest, /stats, /unassign, etc.
# - /api/codes/candidates/* (list, merge, validate, promote, detect-duplicates, etc.)
# - /api/codes/export/* (maxqda-csv, refi-qda)
# 
# These will be migrated incrementally to ensure stability.

@router.get("/stats")
async def get_coding_stats(
    project: str = Query(default="default"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Get coding statistics. Returns empty stats on timeout to prevent connection leaks."""
    from app.coding import coding_statistics
    
    clients = build_clients_or_error(settings)
    try:
        # Set short timeout to prevent pool exhaustion from slow queries
        with clients.postgres.cursor() as cur:
            cur.execute("SET statement_timeout = '30s'")
        
        stats = coding_statistics(clients, project=project)
        return stats
    except Exception as exc:
        # CRITICAL: Return empty stats instead of 500 to keep UI working
        api_logger.warning("api.coding.stats.timeout_or_error", error=str(exc), project=project)
        return {
            "total_codes": 0,
            "total_fragments": 0,
            "coded_fragments": 0,
            "coverage_percent": 0.0,
            "codes_per_fragment_avg": 0.0,
            "error": "Stats temporarily unavailable",
        }
    finally:
        clients.close()

@codes_router.get("/")
async def list_codes(
    project: str = Query(default="default"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """List all codes for a project."""
    from app.coding import list_open_codes
    
    clients = build_clients_or_error(settings)
    try:
        codes = list_open_codes(clients, project=project)
        return {"codes": codes, "count": len(codes)}
    except Exception as exc:
        api_logger.error("api.codes.list_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()

# Additional coding endpoints can be added here as needed
# This minimal router establishes the pattern for future expansion

@router.post("/suggestions")
async def api_coding_suggestions(
    fragment_text: str = Body(..., embed=True),
    limit: int = Body(default=5, embed=True),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Get semantic code suggestions for a fragment."""
    from app.embeddings import embed_batch
    from app.qdrant_block import search_similar
    from collections import Counter
    
    clients = build_clients_or_error(settings)
    try:
        # Embed fragment
        vectors = embed_batch(clients.aoai, settings.azure.deployment_embed, [fragment_text])
        vector = vectors[0] if vectors else []
        
        # Search Similar
        points = search_similar(
            clients.qdrant,
            settings.qdrant.collection,
            vector=vector,
            limit=limit * 2,  # Fetch more to aggregate
        )
        
        # Aggregate Codes from payload
        suggested_codes = Counter()
        evidence_map = {}
        
        for point in points:
            codes = point.payload.get("codigos_ancla", [])
            if isinstance(codes, list):
                for code in codes:
                    suggested_codes[code] += 1
                    if code not in evidence_map:
                        evidence_map[code] = point.payload.get("fragmento")
            elif isinstance(codes, str):  # Legacy single code
                suggested_codes[codes] += 1
                if codes not in evidence_map:
                    evidence_map[codes] = point.payload.get("fragmento")
        
        top_suggestions = []
        for code, count in suggested_codes.most_common(5):
            top_suggestions.append({
                "code": code,
                "confidence": count / len(points) if points else 0,
                "example": evidence_map.get(code)
            })
        
        return {"suggestions": top_suggestions}
    
    except Exception as exc:
        api_logger.error("api.coding.suggestions_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()


@router.get("/next", response_model=CodingNextResponse)
async def api_coding_next_fragment(
    project: str = Query(..., description="Proyecto requerido"),
    archivo: Optional[str] = Query(default=None, description="Opcional: limitar a una entrevista"),
    strategy: str = Query(default="recent", description="Estrategia de selección: recent|oldest|random"),
    exclude_fragment_id: List[str] = Query(default_factory=list, description="IDs a excluir (ej. rechazados en UI)"),
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> CodingNextResponse:
    """Devuelve el próximo fragmento recomendado para Codificación Abierta.

    v1: heurística Postgres-only (no depende de AOAI/Qdrant), y sugiere códigos
    por frecuencia (en entrevista + global) para acelerar el flujo.
    """
    from app.postgres_block import select_next_uncoded_fragment, get_top_open_codes, get_open_coding_pending_counts

    clients = build_clients_or_error(settings)
    try:
        project_id = str(project or "default")
        frag = select_next_uncoded_fragment(
            clients.postgres,
            project_id=project_id,
            archivo=(archivo or None),
            exclude_fragment_ids=list(exclude_fragment_id or []),
            strategy=strategy,
        )
        effective_archivo = None
        if frag and frag.get("archivo"):
            effective_archivo = str(frag.get("archivo") or "").strip() or None
        else:
            effective_archivo = str(archivo or "").strip() or None

        counts = get_open_coding_pending_counts(clients.postgres, project_id=project_id, archivo=effective_archivo)

        if not frag:
            return CodingNextResponse(
                project=project_id,
                found=False,
                pending_total=int(counts.get("pending_total") or 0),
                pending_in_archivo=counts.get("pending_in_archivo"),
                fragmento=None,
                suggested_codes=[],
                reasons=["No hay fragmentos pendientes de codificación."],
            )

        archivo_name = str(frag.get("archivo") or "")
        top_local = get_top_open_codes(clients.postgres, project_id=project_id, archivo=archivo_name, limit=6)
        top_global = get_top_open_codes(clients.postgres, project_id=project_id, archivo=None, limit=6)

        seen: set[str] = set()
        suggested: List[Dict[str, Any]] = []

        for item in top_local:
            code = str(item.get("codigo") or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            suggested.append({"codigo": code, "citas": int(item.get("citas") or 0), "source": "local"})
            if len(suggested) >= 8:
                break
        if len(suggested) < 8:
            for item in top_global:
                code = str(item.get("codigo") or "").strip()
                if not code or code in seen:
                    continue
                seen.add(code)
                suggested.append({"codigo": code, "citas": int(item.get("citas") or 0), "source": "global"})
                if len(suggested) >= 8:
                    break

        reasons = [
            "Fragmento no codificado (pendiente).",
            "Prioriza entrevistas recientes y mantiene orden interno (par_idx)." if (strategy or "").strip().lower() != "oldest" else "Prioriza entrevistas antiguas y mantiene orden interno (par_idx).",
        ]
        if archivo:
            reasons.append("Filtrado por entrevista.")
        if exclude_fragment_id:
            reasons.append("Excluye IDs provistos por UI (ej. rechazados).")

        return CodingNextResponse(
            project=project_id,
            found=True,
            pending_total=int(counts.get("pending_total") or 0),
            pending_in_archivo=counts.get("pending_in_archivo"),
            fragmento=frag,
            suggested_codes=suggested,
            reasons=reasons,
        )
    finally:
        clients.close()


@router.post("/feedback")
async def api_coding_feedback(
    payload: CodingFeedbackRequest,
    settings: AppSettings = Depends(get_settings),
    user: User = Depends(require_auth),
) -> Dict[str, Any]:
    """Registra feedback sobre sugerencias/decisiones de codificación.

    No altera el flujo actual: solo persiste trazas para aprendizaje.
    """
    from app.postgres_block import insert_coding_feedback_event

    action = (payload.action or "").strip().lower()
    if action not in {"accept", "reject", "edit"}:
        raise HTTPException(status_code=400, detail="action inválida (accept|reject|edit)")

    clients = build_clients_or_error(settings)
    try:
        project_id = str(payload.project or "default")
        insert_coding_feedback_event(
            clients.postgres,
            project_id=project_id,
            fragmento_id=str(payload.fragmento_id),
            archivo=payload.archivo,
            action=action,
            suggested_code=payload.suggested_code,
            final_code=payload.final_code,
            source=payload.source,
            meta={
                **(payload.meta or {}),
                "user_id": user.user_id,
            },
        )
        return {"ok": True}
    finally:
        clients.close()

