"""Product-facing, high-level outputs.

Goal: bridge "engine outputs" (many notes, reports, artifacts) into a small set
of product-grade summaries that are easy to consume for non-expert users.

Artifacts generated per project (stored under reports/<project_id>/):
- executive_summary.md
- top_10_insights.json
- open_questions.md
- product_manifest.json

Design notes:
- Best-effort: if some subsystems are unavailable (Neo4j/Qdrant), still generate.
- Uses existing tables when available (analysis_insights) and existing metrics
  helpers (analysis_snapshot, saturation_curve).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from .clients import ServiceClients
from .settings import AppSettings

_logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class GeneratedArtifact:
    name: str
    path: str
    sha256: str
    bytes: int


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_text(*, org_id: Optional[str], project_id: str, logical_path: str, text: str) -> GeneratedArtifact:
    """Write a text artifact to Blob Storage under the strict multi-tenant prefix."""
    from app.blob_storage import CONTAINER_REPORTS, tenant_upload_text

    data = (text or "").encode("utf-8")
    strict = bool(org_id)
    # Use tenant-aware wrapper; allow transition when org_id is missing
    tenant_upload_text(
        org_id=org_id or None,
        project_id=project_id,
        container=CONTAINER_REPORTS,
        logical_path=logical_path,
        text=text,
        content_type="text/markdown; charset=utf-8",
        strict_tenant=strict,
    )
    name = logical_path.replace("\\", "/").split("/")[-1] or "artifact.md"
    return GeneratedArtifact(name=name, path=logical_path, sha256=_sha256_bytes(data), bytes=len(data))


def _write_json(*, org_id: Optional[str], project_id: str, logical_path: str, payload: Any) -> GeneratedArtifact:
    """Write a JSON artifact to Blob Storage under the strict multi-tenant prefix."""
    from app.blob_storage import CONTAINER_REPORTS, tenant_upload_bytes

    data = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    strict = bool(org_id)
    tenant_upload_bytes(
        org_id=org_id or None,
        project_id=project_id,
        container=CONTAINER_REPORTS,
        logical_path=logical_path,
        data=data,
        content_type="application/json",
        strict_tenant=strict,
    )
    name = logical_path.replace("\\", "/").split("/")[-1] or "artifact.json"
    return GeneratedArtifact(name=name, path=logical_path, sha256=_sha256_bytes(data), bytes=len(data))


def _count_note_files(*, org_id: Optional[str], project_id: str) -> int:
    """Best-effort note count for product summaries (Blob Storage)."""
    try:
        from app.blob_storage import CONTAINER_REPORTS, list_files, tenant_prefix

        prefix = tenant_prefix(org_id=org_id, project_id=project_id).rstrip("/") + "/notes/"
        names = list_files(CONTAINER_REPORTS, prefix=prefix)
        return len([n for n in names if str(n).lower().endswith(".md")])
    except Exception:
        # Legacy/local dev fallback
        try:
            base = Path("notes") / project_id
            if not base.exists():
                return 0
            return len([p for p in base.rglob("*.md") if p.is_file()])
        except Exception:
            return 0


def _fetch_insights(
    pg_conn,
    project_id: str,
    *,
    limit: int,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch insights from analysis_insights table if available."""
    try:
        from app.postgres_block import ensure_insights_table

        ensure_insights_table(pg_conn)
    except Exception:
        return []

    where = ["project_id = %s"]
    params: List[Any] = [project_id]
    if status:
        where.append("status = %s")
        params.append(status)

    sql = f"""
        SELECT id, source_type, source_id, insight_type, content, suggested_query, priority, status, created_at, updated_at
        FROM analysis_insights
        WHERE {' AND '.join(where)}
        ORDER BY priority DESC, created_at DESC
        LIMIT %s
    """
    params.append(int(limit))

    try:
        with pg_conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
    except Exception:
        return []

    items: List[Dict[str, Any]] = []
    for row in rows:
        (iid, source_type, source_id, insight_type, content, suggested_query, priority, status_val, created_at, updated_at) = row
        try:
            suggested = suggested_query if isinstance(suggested_query, dict) else (json.loads(suggested_query) if suggested_query else None)
        except Exception:
            suggested = None

        def _ts(v: Any) -> Optional[str]:
            if v is None:
                return None
            if hasattr(v, "isoformat"):
                return v.isoformat().replace("+00:00", "Z")
            return str(v)

        items.append(
            {
                "id": int(iid) if iid is not None else None,
                "source_type": source_type,
                "source_id": source_id,
                "insight_type": insight_type,
                "content": content,
                "suggested_query": suggested,
                "priority": float(priority) if priority is not None else 0.0,
                "status": status_val,
                "created_at": _ts(created_at),
                "updated_at": _ts(updated_at),
            }
        )

    return items


def _generate_executive_summary_md(
    clients: ServiceClients,
    settings: AppSettings,
    project_id: str,
    *,
    org_id: Optional[str] = None,
    top_insights: List[Dict[str, Any]],
) -> str:
    timestamp = dt.datetime.utcnow().isoformat() + "Z"

    # Snapshot (Postgres only)
    try:
        from app.reporting import analysis_snapshot

        snapshot = analysis_snapshot(clients, project=project_id)
    except Exception as e:
        _logger.warning("product.exec.snapshot_error", project=project_id, error=str(e))
        snapshot = {}

    # Saturation (Postgres only)
    try:
        from app.validation import saturation_curve

        sat = saturation_curve(clients.postgres, project=project_id)
        plateau = sat.get("plateau") or {}
        plateau_reached = bool(plateau.get("plateau"))
    except Exception as e:
        _logger.warning("product.exec.saturation_error", project=project_id, error=str(e))
        sat = {}
        plateau = {}
        plateau_reached = False

    # Nucleus candidates (Neo4j best-effort)
    candidates: List[Dict[str, Any]] = []
    try:
        from app.reports import identify_nucleus_candidates

        candidates = identify_nucleus_candidates(clients.neo4j, settings.neo4j.database, project_id, top_k=5)
    except Exception as e:
        _logger.warning("product.exec.nucleus_error", project=project_id, error=str(e))
        candidates = []

    notes_count = _count_note_files(org_id=org_id, project_id=project_id)

    lines: List[str] = []
    lines.append(f"# Executive Summary — {project_id}")
    lines.append("")
    lines.append(f"Generated: {timestamp}")
    lines.append("")

    lines.append("## Key Metrics")
    lines.append("")
    lines.append(f"- Fragments: {snapshot.get('fragmentos', 'n/a')}")
    lines.append(f"- Open codes: {snapshot.get('codigos', 'n/a')}")
    lines.append(f"- Axial categories: {snapshot.get('categorias', 'n/a')}")
    lines.append(f"- Member-checking packets (sample): {snapshot.get('miembros', 'n/a')}")
    lines.append(f"- Notes (md files): {notes_count}")
    lines.append("")

    lines.append("## Saturation")
    lines.append("")
    total_codigos = sat.get("total_codigos")
    lines.append(f"- Total codes (curve): {total_codigos if total_codigos is not None else 'n/a'}")
    if plateau:
        lines.append(f"- Plateau reached: {'yes' if plateau_reached else 'no'}")
        if plateau.get("window") is not None:
            lines.append(f"- Window: {plateau.get('window')}")
        if plateau.get("reason"):
            lines.append(f"- Note: {plateau.get('reason')}")
    else:
        lines.append("- Plateau reached: n/a")
    lines.append("")

    lines.append("## Candidate Nucleus (Top 5)")
    lines.append("")
    if candidates:
        for idx, c in enumerate(candidates[:5], start=1):
            cat = c.get("categoria") or "(unknown)"
            score = c.get("score_nucleo")
            ncod = c.get("num_codigos")
            nrel = c.get("num_relaciones")
            lines.append(f"{idx}. {cat} — score={score}, codes={ncod}, relations={nrel}")
    else:
        lines.append("- n/a (Neo4j unavailable or no candidates)")
    lines.append("")

    lines.append("## Top Insights (10)")
    lines.append("")
    if top_insights:
        for idx, it in enumerate(top_insights[:10], start=1):
            t = it.get("insight_type") or "insight"
            pr = it.get("priority")
            content = (it.get("content") or "").strip()
            if len(content) > 220:
                content = content[:220].rstrip() + "…"
            lines.append(f"{idx}. [{t}] (p={pr}) {content}")
    else:
        lines.append("- (no insights found)")

    lines.append("")
    lines.append("## Recommended Next Actions")
    lines.append("")
    actions: List[str] = []
    if not plateau_reached:
        actions.append("Increase theoretical sampling: target under-covered categories and outlier fragments.")
    if notes_count > 200:
        actions.append("Promote/curate: consolidate repeated memos into a small set of validated insights.")
    if candidates:
        actions.append("Run selective coding on the top nucleus candidate and validate with evidence links.")
    if not actions:
        actions = ["Review top insights and validate them against primary evidence."]

    for a in actions[:5]:
        lines.append(f"- {a}")

    lines.append("")
    lines.append("---")
    lines.append("This executive summary is a product-facing view. For full traceability, see Reports/Artifacts and the interview-level reports.")
    lines.append("")

    return "\n".join(lines)


def _generate_open_questions_md(
    project_id: str,
    pending: List[Dict[str, Any]],
    *,
    max_items: int = 25,
) -> str:
    timestamp = dt.datetime.utcnow().isoformat() + "Z"

    lines: List[str] = []
    lines.append(f"# Open Questions — {project_id}")
    lines.append("")
    lines.append(f"Generated: {timestamp}")
    lines.append("")
    lines.append("These are actionable research questions derived from pending insights and gaps.")
    lines.append("")

    if not pending:
        lines.append("- (no pending insights)")
        lines.append("")
        return "\n".join(lines)

    for it in pending[: max(1, int(max_items))]:
        iid = it.get("id")
        t = it.get("insight_type") or "question"
        pr = it.get("priority")
        content = (it.get("content") or "").strip()
        suggested = it.get("suggested_query")
        lines.append(f"- [ ] ({t}, p={pr}, id={iid}) {content}")
        if suggested:
            try:
                lines.append("  - suggested_query: ```")
                lines.append(json.dumps(suggested, ensure_ascii=False))
                lines.append("  ```")
            except Exception:
                pass

    lines.append("")
    lines.append("---")
    lines.append("Tip: prioritize 'saturate' and 'validate' questions before 'merge'.")
    lines.append("")
    return "\n".join(lines)


def generate_and_write_product_artifacts(
    clients: ServiceClients,
    settings: AppSettings,
    project_id: str,
    *,
    org_id: Optional[str] = None,
    changed_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate and persist product-facing artifacts (Blob Storage, multi-tenant)."""
    logger = _logger.bind(action="product_artifacts.generate", project=project_id)

    top_insights = _fetch_insights(clients.postgres, project_id, limit=10)
    pending_insights = _fetch_insights(clients.postgres, project_id, limit=25, status="pending")

    exec_md = _generate_executive_summary_md(
        clients,
        settings,
        project_id,
        org_id=org_id,
        top_insights=top_insights,
    )

    top_json_payload = {
        "schema_version": 1,
        "project": project_id,
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "items": top_insights,
    }

    # Hard validation: ensure product insights are actionable and structurally sound.
    try:
        from app.schemas import TopInsightsArtifact

        validated = TopInsightsArtifact(**top_json_payload)
        top_json_payload = validated.model_dump()
    except Exception as e:
        # Fail fast: generating product artifacts must not silently emit invalid contracts.
        logger.error("product_artifacts.top_insights_invalid", error=str(e))
        raise

    open_md = _generate_open_questions_md(project_id, pending_insights, max_items=25)

    artifacts: List[GeneratedArtifact] = []

    artifacts.append(
        _write_text(
            org_id=org_id,
            project_id=project_id,
            logical_path=f"reports/{project_id}/executive_summary.md",
            text=exec_md,
        )
    )
    artifacts.append(
        _write_json(
            org_id=org_id,
            project_id=project_id,
            logical_path=f"reports/{project_id}/top_10_insights.json",
            payload=top_json_payload,
        )
    )
    artifacts.append(
        _write_text(
            org_id=org_id,
            project_id=project_id,
            logical_path=f"reports/{project_id}/open_questions.md",
            text=open_md,
        )
    )

    manifest = {
        "project": project_id,
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "changed_by": changed_by,
        "artifacts": [asdict(a) for a in artifacts],
    }
    artifacts.append(
        _write_json(
            org_id=org_id,
            project_id=project_id,
            logical_path=f"reports/{project_id}/product_manifest.json",
            payload=manifest,
        )
    )

    logger.info("product_artifacts.generated", count=len(artifacts))

    return {
        "project": project_id,
        "generated_at": manifest["generated_at"],
        "changed_by": changed_by,
        "artifacts": [asdict(a) for a in artifacts],
    }
