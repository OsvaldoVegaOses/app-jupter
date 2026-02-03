from fastapi import APIRouter, Depends
from typing import Any, Dict

from app.clients import ServiceClients, build_service_clients
from app.settings import AppSettings, load_settings
from app.nucleus import nucleus_report

router = APIRouter(prefix="/nucleus", tags=["nucleus"])


@router.get("/light/{project}/{categoria}")
async def nucleus_light(
    project: str,
    categoria: str,
    clients: Any = None,
    settings: Any = None,
) -> Dict[str, Any]:
    """Light endpoint that returns llm_summary, storyline and audit_summary for UI.

    Note: this wrapper creates its own `ServiceClients` to avoid circular
    import issues when FastAPI builds dependency graphs at import time.
    """
    owns_clients = clients is None
    settings = settings or load_settings()
    clients = clients or build_service_clients(settings)
    try:
        try:
            report = nucleus_report(clients, settings, categoria=categoria, prompt=None, project=project, persist=False)
        except Exception as e:
            # Defensive: do not let internal errors (DB, query, etc.) return 500 to UI.
            # Log and return a minimal canonical contract so the frontend can render gracefully.
            try:
                import structlog

                _logger = structlog.get_logger("backend.nucleus.light")
                warn_fn = getattr(_logger, "warning", None) or getattr(_logger, "warn", None)
                if callable(warn_fn):
                    warn_fn("nucleus.light.error", error=str(e))
            except Exception:
                pass

            report = {
                "llm_summary": "",
                "storyline_graphrag": {
                    "is_grounded": False,
                    "mode": "abstained",
                    "answer": None,
                    "nodes": [],
                    "evidence": [],
                    "confidence": "NONE",
                    "rejection": str(e),
                },
                "summary_metrics": {"text_summary": None},
            }
    finally:
        if owns_clients:
            try:
                clients.close()
            except Exception:
                pass

    return {
        "llm_summary": report.get("llm_summary") or "",
        "storyline": report.get("storyline") or report.get("storyline_graphrag") or {},
        "audit_summary": report.get("audit_summary") or report.get("summary_metrics") or {},
        "exploratory_scan": report.get("exploratory_scan") or None,
        "abstention": report.get("abstention") or None,
    }
