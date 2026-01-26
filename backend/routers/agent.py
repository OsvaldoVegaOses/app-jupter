"""
Router de Agente Autónomo para APP_Jupter.

Endpoints para iniciar y monitorear el agente de investigación cualitativa.

Sprint 29 - Enero 2026
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
import structlog
import asyncio
from datetime import datetime
from functools import lru_cache
import os
from pathlib import Path
import json
import re
import math
import hashlib
from collections import defaultdict

from app.clients import ServiceClients, build_service_clients
from app.coding_runner_core import constant_comparison_sample, attach_evidence_to_codes
from app.settings import AppSettings, load_settings
from app.project_state import resolve_project
from app.error_handling import api_error, ErrorCode
from backend.auth import User, get_current_user

router = APIRouter(prefix="/api/agent", tags=["agent"])
_logger = structlog.get_logger()


def _allow_local_artifacts_fallback() -> bool:
    return os.getenv("ARTIFACTS_ALLOW_LOCAL_FALLBACK", "false").strip().lower() in {"1", "true", "yes"}


async def require_auth(user: User = Depends(get_current_user)) -> User:
    return user


# ============================================================================
# Request/Response Models
# ============================================================================

class AgentExecuteRequest(BaseModel):
    """Request para iniciar el agente."""

    project_id: str
    concepts: Optional[List[str]] = ["rol_municipal_planificacion"]
    max_iterations: int = 50
    max_interviews: int = 10  # Límite de entrevistas a procesar
    iterations_per_interview: int = 4  # Refinamientos por entrevista
    discovery_only: bool = False  # Si True, solo ejecuta Discovery
    use_constant_comparison: bool = True  # Diversificar evidencia antes de candidatos


class AgentStatusResponse(BaseModel):
    """Estado actual del agente."""

    task_id: str
    status: str  # "pending" | "running" | "completed" | "error"
    current_stage: int
    iteration: int
    memos_count: int
    codes_count: int
    errors: Optional[List[str]] = None
    final_landing_rate: Optional[Dict[str, Any]] = None
    post_run: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


class AgentResult(BaseModel):
    """Resultado final del agente."""

    project_id: str
    status: str
    iterations: int
    validated_codes: List[str]
    discovery_memos: List[str]
    saturation_score: float
    final_report: Optional[str] = None
    errors: Optional[List[str]] = None  # Errores durante ejecución
    final_landing_rate: Optional[Dict[str, Any]] = None  # Landing rate final
    logs: Optional[List[str]] = None  # Logs de ejecución para frontend
    post_run: Optional[Dict[str, Any]] = None


# ============================================================================
# Helpers
# ============================================================================

def _parse_llm_json(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    clean = raw.strip()
    clean = re.sub(r'^```json?\s*', '', clean)
    clean = re.sub(r'\s*```$', '', clean)
    try:
        return json.loads(clean)
    except Exception:
        return None


_EPISTEMIC_TYPES = {"OBSERVATION", "INTERPRETATION", "HYPOTHESIS", "NORMATIVE_INFERENCE"}


def _normalize_memo_sintesis(value: Any) -> tuple[str, List[Dict[str, Any]]]:
    """Normaliza memo_sintesis del LLM.

    Compatibilidad:
      - Si el LLM devuelve string: se retorna tal cual y lista vacía.
      - Si devuelve lista de statements: se genera string derivado y lista normalizada.
    """
    if isinstance(value, str):
        return value.strip(), []

    if not isinstance(value, list):
        return "", []

    statements: List[Dict[str, Any]] = []
    rendered_lines: List[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        stype = str(item.get("type") or "").strip().upper()
        text = str(item.get("text") or "").strip()
        evidence_ids_raw = item.get("evidence_ids")

        if not text:
            continue
        if stype not in _EPISTEMIC_TYPES:
            stype = "INTERPRETATION"

        evidence_ids: List[int] = []
        if isinstance(evidence_ids_raw, list):
            for v in evidence_ids_raw:
                try:
                    evidence_ids.append(int(v))
                except Exception:
                    continue
        # Regla de seguridad: no permitir OBSERVATION sin evidencia.
        if stype == "OBSERVATION" and not evidence_ids:
            stype = "INTERPRETATION"

        statement = {"type": stype, "text": text}
        if evidence_ids:
            statement["evidence_ids"] = evidence_ids
        statements.append(statement)

        if evidence_ids:
            rendered_lines.append(f"[{stype}] {text} (evid: {', '.join(str(i) for i in evidence_ids)})")
        else:
            rendered_lines.append(f"[{stype}] {text}")

    return "\n".join(rendered_lines).strip(), statements


def _analyze_fragments_with_llm(
    *,
    clients: ServiceClients,
    settings: AppSettings,
    positive_texts: List[str],
    negative_texts: List[str],
    target_text: Optional[str],
    fragments: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Genera síntesis + códigos sugeridos en JSON estructurado (sin usar HTTP interno)."""
    fragment_sample = fragments[:8] if fragments else []
    fragments_text: List[str] = []
    for i, frag in enumerate(fragment_sample, 1):
        fragmento = (frag.get("fragmento") or "")[:400]
        archivo = frag.get("archivo") or "?"
        score = float(frag.get("score") or 0.0)
        fragments_text.append(f"{i}. [{archivo}] (sim: {score:.1%}) {fragmento}")

    positives_str = ", ".join(positive_texts)
    negatives_str = ", ".join(negative_texts) if negative_texts else "ninguno"
    target_str = target_text or "no especificado"

    prompt = f"""Analiza los resultados de una búsqueda exploratoria (Discovery) en un proyecto de análisis cualitativo (Teoría Fundamentada).

**Parámetros de búsqueda:**
- Conceptos positivos: {positives_str}
- Conceptos negativos: {negatives_str}
- Texto objetivo: {target_str}

**Muestra de fragmentos encontrados:**
{chr(10).join(fragments_text)}

IMPORTANTE: Responde ÚNICAMENTE con un JSON válido (sin markdown, sin ```).
La síntesis debe distinguir explícitamente el estatus epistemológico de cada afirmación.
El JSON debe tener esta estructura exacta:

{{
    "memo_sintesis": [
        {{"type": "OBSERVATION", "text": "...", "evidence_ids": [1, 3]}},
        {{"type": "INTERPRETATION", "text": "...", "evidence_ids": [1, 3]}},
        {{"type": "HYPOTHESIS", "text": "...", "evidence_ids": [2]}},
        {{"type": "NORMATIVE_INFERENCE", "text": "...", "evidence_ids": [1, 2]}}
    ],
  "codigos_sugeridos": ["codigo_uno", "codigo_dos", "codigo_tres"],
  "decisiones_requeridas": ["Decisión 1...", "Decisión 2..."],
  "proximos_pasos": ["Paso 1...", "Paso 2..."]
}}

REGLAS:
1. memo_sintesis: lista de 4-8 statements. Cada statement incluye:
    - type: uno de OBSERVATION | INTERPRETATION | HYPOTHESIS | NORMATIVE_INFERENCE
    - text: una oración clara (español)
    - evidence_ids: lista de enteros referidos a la numeración de la "Muestra de fragmentos" (1..8)
2. PROHIBIDO: OBSERVATION sin evidence_ids no vacíos.
3. PROHIBIDO: poner lenguaje normativo ("debe", "hay que") en OBSERVATION.
2. codigos_sugeridos: 5-10 códigos en snake_case (ej: identidad_cultural_amenazada)
3. decisiones_requeridas: 3-6 decisiones metodológicas concretas
4. proximos_pasos: 4-8 acciones concretas para el próximo sprint"""

    # Sprint 30: Timeout para evitar que el backend quede colgado si Azure responde lento
    response = clients.aoai.chat.completions.create(
        model=settings.azure.deployment_chat,
        messages=[
            {
                "role": "system",
                "content": "Eres un experto en análisis cualitativo. Respondes SOLO con JSON válido, sin markdown ni explicaciones adicionales.",
            },
            {"role": "user", "content": prompt},
        ],
        max_completion_tokens=800,
        timeout=60.0,  # Fix: previene bloqueo indefinido si Azure está lento
    )

    choice = response.choices[0] if response.choices else None
    message = getattr(choice, "message", None)
    raw = getattr(message, "content", None) or ""
    parsed = _parse_llm_json(raw)
    if parsed is None:
        return {
            "structured": False,
            "raw": raw,
            "memo_sintesis": "",
            "memo_statements": [],
            "codigos_sugeridos": [],
            "decisiones_requeridas": [],
            "proximos_pasos": [],
        }

    memo_value = parsed.get("memo_sintesis") if isinstance(parsed, dict) else ""
    memo_text, memo_statements = _normalize_memo_sintesis(memo_value)

    return {
        "structured": True,
        "raw": raw,
        # Compatibilidad: memo_sintesis permanece como string derivado para consumidores existentes.
        "memo_sintesis": memo_text,
        # Nuevo: lista etiquetada para trazabilidad epistemológica.
        "memo_statements": memo_statements,
        "codigos_sugeridos": (parsed.get("codigos_sugeridos") or []) if isinstance(parsed, dict) else [],
        "decisiones_requeridas": (parsed.get("decisiones_requeridas") or []) if isinstance(parsed, dict) else [],
        "proximos_pasos": (parsed.get("proximos_pasos") or []) if isinstance(parsed, dict) else [],
    }


def _link_codes_to_fragments(
    codes: List[str],
    fragments: List[Dict[str, Any]],
    max_fragments_per_code: int = 3,
) -> List[Dict[str, Any]]:
    """Asocia cada código sugerido con una pequeña lista de fragmentos evidenciales."""
    if not codes or not fragments:
        return []

    # Pool de evidencia: prioriza los primeros fragmentos (normalmente ordenados por score)
    # pero intenta ser lo bastante grande para evitar que todos los códigos reutilicen el mismo trío.
    pool_size = min(len(fragments), max(max_fragments_per_code * 4, max_fragments_per_code * len(codes)))
    pool = fragments[:pool_size]
    linked: List[Dict[str, Any]] = []

    def _pick_stride(n: int) -> int:
        if n <= 2:
            return 1
        for step in range(2, n):
            if math.gcd(step, n) == 1:
                return step
        return 1

    stride = _pick_stride(len(pool))
    usage: Dict[str, int] = defaultdict(int)

    for idx, code in enumerate(codes):
        if not pool:
            selected: List[Dict[str, Any]] = []
        elif len(pool) <= max_fragments_per_code:
            selected = list(pool)
        else:
            # Offset determinístico por código (evita depender de hash() de Python que cambia por sesión)
            h = hashlib.sha256(code.encode("utf-8")).hexdigest()
            base = int(h[:8], 16)
            start = (base + idx) % len(pool)

            # Candidatos en orden determinístico; luego elegimos los menos usados globalmente.
            candidates: List[tuple[int, str, Dict[str, Any]]] = []
            for pos in range(len(pool)):
                frag = pool[(start + pos * stride) % len(pool)]
                frag_id = str(frag.get("fragmento_id") or "")
                if not frag_id:
                    continue
                candidates.append((pos, frag_id, frag))

            # Dedup por fragmento_id manteniendo el primer 'pos' (determinístico)
            seen_ids: set[str] = set()
            unique: List[tuple[int, int, str, Dict[str, Any]]] = []
            for pos, frag_id, frag in candidates:
                if frag_id in seen_ids:
                    continue
                seen_ids.add(frag_id)
                unique.append((usage.get(frag_id, 0), pos, frag_id, frag))

            unique.sort(key=lambda t: (t[0], t[1]))
            chosen = unique[:max_fragments_per_code]
            selected = [frag for _, _, _, frag in chosen]

            for _, _, frag_id, _ in chosen:
                usage[frag_id] += 1

        linked.append({
            "code": code,
            "fragments": [
                {
                    "fragmento_id": frag.get("fragmento_id"),
                    "archivo": frag.get("archivo"),
                    "score": float(frag.get("score", 0.0)),
                    "preview": (frag.get("fragmento") or "")[:160],
                }
                for frag in selected if frag
            ],
        })

    return linked


def _compute_evidence_diversity_metrics(
    codes_with_fragments: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Calcula métricas simples de diversidad de evidencia.

    Objetivo: convertir la intuición de "se repite mucho el mismo trío" en números.
    Métricas diseñadas para ser livianas y estables (deterministas) dado un input.
    """
    entries = codes_with_fragments or []
    codes_count = len(entries)

    per_code_ids: List[List[str]] = []
    all_ids: List[str] = []
    triple_counts: Dict[tuple[str, ...], int] = defaultdict(int)

    for entry in entries:
        frags = entry.get("fragments") or []
        ids = [str(f.get("fragmento_id")) for f in frags if f.get("fragmento_id")]
        per_code_ids.append(ids)
        all_ids.extend(ids)
        if ids:
            triple_counts[tuple(ids)] += 1

    total_ids = len(all_ids)
    unique_ids = len(set(all_ids))
    unique_triples = len(triple_counts)
    max_triple_repeat = max(triple_counts.values()) if triple_counts else 0

    repeated_triples: List[Dict[str, Any]] = []
    if triple_counts:
        for triple, count in sorted(triple_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            if count <= 1:
                continue
            repeated_triples.append({"fragmentos": list(triple), "count": int(count)})
            if len(repeated_triples) >= 5:
                break

    # Overlap (Jaccard) promedio y máximo entre sets de evidencias por código.
    sets = [set(ids) for ids in per_code_ids if ids]
    pairwise = []
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            a, b = sets[i], sets[j]
            denom = len(a | b)
            pairwise.append((len(a & b) / denom) if denom else 0.0)

    avg_jaccard = (sum(pairwise) / len(pairwise)) if pairwise else 0.0
    max_jaccard = max(pairwise) if pairwise else 0.0

    avg_ids_per_code = (total_ids / codes_count) if codes_count else 0.0

    return {
        "codes": int(codes_count),
        "total_evidence_ids": int(total_ids),
        "unique_evidence_ids": int(unique_ids),
        "coverage_unique_ids_ratio": float(unique_ids / total_ids) if total_ids else 0.0,
        "avg_ids_per_code": float(avg_ids_per_code),
        "unique_triples": int(unique_triples),
        "max_triple_repeat": int(max_triple_repeat),
        "repeated_triples": repeated_triples,
        "avg_pairwise_jaccard": float(avg_jaccard),
        "max_pairwise_jaccard": float(max_jaccard),
    }


def _write_runner_report(
    *,
    project_id: str,
    task_id: str,
    concepts: List[str],
    discovery_result: Dict[str, Any],
    synthesis: Dict[str, Any],
    codes_with_fragments: Optional[List[Dict[str, Any]]] = None,
    evidence_metrics: Optional[Dict[str, Any]] = None,
    org_id: Optional[str] = None,
) -> str:
    """Persist Runner post-run report (Blob-first, strict multi-tenant)."""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"{ts}_runner_avance_{task_id}.md"
    logical_path = f"reports/runner/{project_id}/{filename}"

    lr = discovery_result.get("final_landing_rate") or {}
    sample = discovery_result.get("sample_fragments") or []
    config = discovery_result.get("config") or {}

    lines: List[str] = []
    lines.append("# Informe de Avance (Runner Discovery)")
    lines.append(f"**Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Proyecto:** {project_id}")
    lines.append(f"**Task:** {task_id}")
    lines.append("")
    lines.append("## Parámetros")
    lines.append(f"- Conceptos: {', '.join(concepts) if concepts else '(ninguno)'}")
    lines.append(f"- Entrevistas procesadas: {discovery_result.get('interviews_processed', 0)} / {discovery_result.get('interviews_available', 0)}")
    lines.append(f"- Iteraciones registradas: {len(discovery_result.get('runs', []) or [])}")
    lines.append("")

    lines.append("## Métrica (Landing rate)")
    if lr:
        lines.append(
            f"- Landing rate final: {lr.get('landing_rate', 0):.1f}% ({lr.get('matched_count', 0)} de {lr.get('total_count', 0)})"
        )
        reason = lr.get("reason")
        if reason:
            lines.append(f"- Nota: {reason}")
    else:
        lines.append("- (no disponible)")
    lines.append("")

    lines.append("## Síntesis cualitativa (IA)")
    memo = (synthesis.get("memo_sintesis") or "").strip()
    lines.append(memo if memo else "(sin síntesis)")
    lines.append("")

    codes = synthesis.get("codigos_sugeridos") or []
    lines.append("## Códigos sugeridos (para bandeja)")
    if codes_with_fragments:
        for entry in codes_with_fragments:
            lines.append(f"- {entry.get('code')}")
            frag_refs = entry.get("fragments") or []
            if frag_refs:
                ids = [f.get("fragmento_id") for f in frag_refs if f.get("fragmento_id")]
                if ids:
                    lines.append(f"  - fragmentos: {', '.join(ids)}")
    elif codes:
        for c in codes:
            lines.append(f"- {c}")
    else:
        lines.append("- (sin códigos sugeridos)")
    lines.append("")

    metrics = evidence_metrics or _compute_evidence_diversity_metrics(codes_with_fragments)
    lines.append("## Métricas de diversidad de evidencia")
    if metrics.get("codes"):
        lines.append(f"- Códigos con evidencia: {metrics.get('codes', 0)}")
        lines.append(
            f"- Evidencias totales: {metrics.get('total_evidence_ids', 0)} · IDs únicos: {metrics.get('unique_evidence_ids', 0)} "
            f"(cobertura {metrics.get('coverage_unique_ids_ratio', 0.0) * 100:.1f}%)"
        )
        lines.append(
            f"- Tríos únicos: {metrics.get('unique_triples', 0)} · Repetición máxima de un mismo trío: {metrics.get('max_triple_repeat', 0)}"
        )
        lines.append(
            f"- Solapamiento (Jaccard) promedio: {metrics.get('avg_pairwise_jaccard', 0.0):.3f} · máximo: {metrics.get('max_pairwise_jaccard', 0.0):.3f}"
        )
        reps = metrics.get("repeated_triples") or []
        if reps:
            lines.append("- Tríos repetidos (top):")
            for item in reps:
                frag_list = item.get("fragmentos") or []
                cnt = item.get("count", 0)
                if frag_list and cnt:
                    lines.append(f"  - {', '.join(frag_list)} (x{cnt})")
    else:
        lines.append("- (no disponible)")
    lines.append("")

    lines.append("## Metadatos de ejecución (para trazabilidad)")
    lines.append(f"- max_interviews: {config.get('max_interviews', 'n/d')}")
    lines.append(f"- per_interview_iters: {config.get('per_interview_iters', 'n/d')}")
    lines.append(f"- global_iters: {config.get('global_iters', 'n/d')}")
    lines.append(f"- top_k: {config.get('top_k', 'n/d')}")
    lines.append(f"- score_threshold: {config.get('score_threshold', 'n/d')}")
    lines.append("")

    decisions = synthesis.get("decisiones_requeridas") or []
    lines.append("## Decisiones requeridas (metodología cualitativa)")
    if decisions:
        for d in decisions:
            lines.append(f"- {d}")
    else:
        lines.append("- (sin decisiones listadas)")
    lines.append("")

    next_steps = synthesis.get("proximos_pasos") or []
    lines.append("## Próximos pasos")
    if next_steps:
        for s in next_steps:
            lines.append(f"- {s}")
    else:
        lines.append("- (sin próximos pasos listados)")
    lines.append("")

    lines.append(f"## Muestra de fragmentos ({min(len(sample), 10)} / {len(sample)})")
    for idx, frag in enumerate(sample[:10], 1):
        archivo = frag.get("archivo") or "?"
        score = float(frag.get("score") or 0.0)
        text = (frag.get("fragmento") or "").strip()
        fid = frag.get("fragmento_id") or "?"
        lines.append(f"\n### [{idx}] {archivo} (sim: {score:.1%})")
        lines.append(f"**fragmento_id:** {fid}")
        if text:
            lines.append(f"> {text}")

    lines.append("\n---")
    lines.append("*Generado automáticamente por Runner Discovery (post-run).*")

    content = "\n".join(lines) + "\n"

    try:
        from app.blob_storage import CONTAINER_REPORTS, tenant_upload_text

        strict = bool(org_id)
        tenant_upload_text(
            org_id=org_id or None,
            project_id=project_id,
            container=CONTAINER_REPORTS,
            logical_path=logical_path,
            text=content,
            content_type="text/markdown; charset=utf-8",
            strict_tenant=strict,
        )
        return logical_path
    except Exception as exc:
        _logger.warning("agent.runner_report.blob_write_failed", error=str(exc)[:200], project_id=project_id, task_id=task_id)

    # Legacy/local fallback (dev).
    if not _allow_local_artifacts_fallback():
        return logical_path
    try:
        base_dir = Path("reports") / "runner" / project_id
        base_dir.mkdir(parents=True, exist_ok=True)
        file_path = base_dir / filename
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)
    except Exception as exc:
        _logger.warning("agent.runner_report.local_write_failed", error=str(exc)[:200], project_id=project_id, task_id=task_id)
        return logical_path


class DiscoveryRunRequest(BaseModel):
    """Payload para registrar una iteración de Discovery."""

    project: str
    concepto: str
    scope: str  # per_interview | global
    iter: int
    archivo: Optional[str] = None
    query: Optional[str] = None
    positivos: Optional[List[str]] = None
    negativos: Optional[List[str]] = None
    overlap: Optional[float] = None
    landing_rate: Optional[float] = None
    top_fragments: Optional[List[Dict[str, Any]]] = None
    memo: Optional[str] = None


# ============================================================================
# In-memory task storage (production: use Redis)
# ============================================================================

_agent_tasks: Dict[str, dict] = {}


# ============================================================================
# Settings / Clients helpers
# ============================================================================

@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    env_file = os.getenv("APP_ENV_FILE")
    return load_settings(env_file)


def build_clients_or_error(settings: AppSettings) -> ServiceClients:
    try:
        return build_service_clients(settings)
    except Exception as exc:  # pragma: no cover - infra errors
        raise api_error(
            status_code=502,
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Error conectando con servicios externos. Intente más tarde.",
            exc=exc,
        ) from exc


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/execute", response_model=Dict)
async def execute_agent(
    request: AgentExecuteRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_auth),
):
    """Inicia el agente de investigación autónoma."""
    task_id = f"agent_{request.project_id}_{datetime.now().strftime('%H%M%S')}"

    _logger.info(
        "agent.execute.started",
        task_id=task_id,
        project_id=request.project_id,
        concepts=request.concepts,
        max_iterations=request.max_iterations,
    )

    # Inicializar estado
    _agent_tasks[task_id] = {
        "status": "pending",
        "project_id": request.project_id,
        "current_stage": 0,
        "iteration": 0,
        "memos_count": 0,
        "codes_count": 0,
        "error": None,
        "started_at": datetime.now().isoformat(),
    }

    # Ejecutar en background
    background_tasks.add_task(
        _run_agent_task,
        task_id=task_id,
        project_id=request.project_id,
        concepts=request.concepts or [],
        max_iterations=request.max_iterations,
        max_interviews=request.max_interviews,
        iterations_per_interview=request.iterations_per_interview,
        discovery_only=request.discovery_only,
        use_constant_comparison=request.use_constant_comparison,
        org_id=str(getattr(user, "organization_id", None) or ""),
    )

    return {
        "task_id": task_id,
        "status": "started",
        "message": f"Agent started for project {request.project_id}",
    }


@router.get("/status/{task_id}", response_model=AgentStatusResponse)
async def get_agent_status(task_id: str):
    """Consulta estado de una tarea del agente."""
    if task_id not in _agent_tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    task = _agent_tasks[task_id]
    return AgentStatusResponse(
        task_id=task_id,
        status=task["status"],
        current_stage=task["current_stage"],
        iteration=task["iteration"],
        memos_count=task["memos_count"],
        codes_count=task["codes_count"],
        errors=task.get("errors"),
        final_landing_rate=task.get("final_landing_rate"),
        post_run=task.get("post_run"),
        message=task.get("error"),
    )


@router.get("/result/{task_id}", response_model=AgentResult)
async def get_agent_result(task_id: str):
    """Obtiene resultado final de una tarea completada."""
    if task_id not in _agent_tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    task = _agent_tasks[task_id]
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Task not completed: {task['status']}")

    return AgentResult(
        project_id=task["project_id"],
        status=task["status"],
        iterations=task["iteration"],
        validated_codes=task.get("validated_codes", []),
        discovery_memos=task.get("discovery_memos", []),
        saturation_score=task.get("saturation_score", 0.0),
        final_report=task.get("final_report"),
        errors=task.get("errors"),
        final_landing_rate=task.get("final_landing_rate"),
        logs=task.get("logs"),
        post_run=task.get("post_run"),
    )


@router.get("/tasks", response_model=List[Dict])
async def list_agent_tasks():
    """Lista todas las tareas del agente."""
    return [
        {"task_id": tid, **task}
        for tid, task in _agent_tasks.items()
    ]


# ============================================================================
# Discovery Runs - Persistencia de iteraciones de refinamiento
# ============================================================================


@router.post("/discovery/run")
async def log_discovery_run(
    payload: DiscoveryRunRequest,
    settings: AppSettings = Depends(get_settings),
):
    """Registra una iteración de Discovery con métricas de overlap/landing_rate."""
    try:
        project_id = resolve_project(payload.project, allow_create=False)
        if not project_id:
            raise HTTPException(status_code=400, detail="Invalid project ID")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    clients = build_clients_or_error(settings)
    try:
        from app.postgres_block import insert_discovery_run

        record = insert_discovery_run(
            clients.postgres,
            project=project_id,
            concepto=payload.concepto,
            scope=payload.scope,
            iter_index=payload.iter,
            archivo=payload.archivo,
            query=payload.query,
            positivos=payload.positivos,
            negativos=payload.negativos,
            overlap=payload.overlap,
            landing_rate=payload.landing_rate,
            top_fragments=payload.top_fragments,
            memo=payload.memo,
        )

        return {
            "project": project_id,
            "id": record.get("id"),
            "created_at": record.get("created_at"),
            "status": "logged",
        }
    except Exception as exc:
        _logger.error("agent.discovery.run.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()


@router.get("/discovery/runs")
async def get_discovery_runs_api(
    project: str = Query(..., description="Project ID"),
    concepto: Optional[str] = Query(None, description="Filtrar por concepto"),
    limit: int = Query(50, ge=1, le=200, description="Máximo de iteraciones"),
    settings: AppSettings = Depends(get_settings),
):
    """Devuelve iteraciones de Discovery recientes para un proyecto (y concepto opcional)."""
    try:
        project_id = resolve_project(project, allow_create=False)
        if not project_id:
            raise HTTPException(status_code=400, detail="Invalid project ID")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    clients = build_clients_or_error(settings)
    try:
        from app.postgres_block import get_discovery_runs

        runs = get_discovery_runs(
            clients.postgres,
            project=project_id,
            concepto=concepto,
            limit=limit,
        )
        return {
            "project": project_id,
            "concepto": concepto,
            "count": len(runs),
            "runs": runs,
        }
    except Exception as exc:
        _logger.error("agent.discovery.runs.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clients.close()


# ============================================================================
# Background Task Runner
# ============================================================================


async def _run_agent_task(
    task_id: str,
    project_id: str,
    concepts: List[str],
    max_iterations: int,
    max_interviews: int = 10,
    iterations_per_interview: int = 4,
    discovery_only: bool = False,
    use_constant_comparison: bool = True,
    org_id: str = "",
):
    """Ejecuta el agente en background, usando run_discovery_iterations para Discovery."""
    try:
        _agent_tasks[task_id]["status"] = "running"
        settings = get_settings()

        # Fase 1: Ejecutar Discovery con run_discovery_iterations (robusto)
        _logger.info("agent.discovery.start", task_id=task_id, project_id=project_id)
        _agent_tasks[task_id]["current_stage"] = 2  # Discovery stage

        clients = build_clients_or_error(settings)
        try:
            from app.discovery_runner import run_discovery_iterations

            discovery_result = await run_discovery_iterations(
                project_id=project_id,
                concepts=concepts,
                clients=clients,
                settings=settings,
                max_interviews=max_interviews,
                per_interview_iters=iterations_per_interview,
                global_iters=min(iterations_per_interview, 3),
                use_real_landing_rate=True,
            )

            _logger.info(
                "agent.discovery.complete",
                runs_count=len(discovery_result.get("runs", [])),
                errors_count=len(discovery_result.get("errors", [])),
                final_landing_rate=discovery_result.get("final_landing_rate"),
            )

            # Actualizar estado base
            _agent_tasks[task_id].update({
                "iteration": len(discovery_result.get("runs", [])),
                "discovery_memos": [r.get("id") for r in discovery_result.get("runs", [])],
                "memos_count": len(discovery_result.get("runs", [])),
                "errors": discovery_result.get("errors", []),
                "final_landing_rate": discovery_result.get("final_landing_rate"),
            })

            if discovery_only:
                # POST-RUN: síntesis + códigos candidatos + informe markdown
                sample_fragments: List[Dict[str, Any]] = discovery_result.get("sample_fragments") or []
                if use_constant_comparison:
                    sample_fragments = constant_comparison_sample(
                        sample_fragments,
                        max_total=60,
                        max_per_archivo=3,
                    )
                # Sprint 30: Envolver síntesis LLM en try/except para evitar crash si Azure falla
                try:
                    synthesis = _analyze_fragments_with_llm(
                        clients=clients,
                        settings=settings,
                        positive_texts=concepts,
                        negative_texts=[],
                        target_text=None,
                        fragments=sample_fragments,
                    )
                except Exception as synth_err:
                    # Fallback: continuar sin síntesis en lugar de crashear
                    _logger.error(
                        "agent.post_run.synthesis_error",
                        task_id=task_id,
                        error=str(synth_err),
                    )
                    synthesis = {
                        "structured": False,
                        "memo_sintesis": f"Error generando síntesis: {str(synth_err)[:200]}",
                        "memo_statements": [],
                        "codigos_sugeridos": [],
                        "decisiones_requeridas": [],
                        "proximos_pasos": [],
                    }
                    _agent_tasks[task_id].setdefault("errors", []).append(
                        f"Síntesis LLM fallida: {str(synth_err)[:100]}"
                    )

                suggested_codes = [
                    c for c in (synthesis.get("codigos_sugeridos") or [])
                    if isinstance(c, str) and c.strip()
                ]

                codes_with_fragments = attach_evidence_to_codes(
                    codes=suggested_codes,
                    fragments=sample_fragments,
                    max_fragments_per_code=3,
                )

                evidence_metrics = _compute_evidence_diversity_metrics(codes_with_fragments)

                def _pick_fragment_info(code_value: str) -> Dict[str, Optional[str]]:
                    for entry in codes_with_fragments:
                        if entry.get("code") == code_value:
                            frags = entry.get("fragments") or []
                            if frags:
                                first = frags[0]
                                return {
                                    "fragmento_id": first.get("fragmento_id"),
                                    "archivo": first.get("archivo"),
                                    "evidence_ids": [
                                        f.get("fragmento_id")
                                        for f in frags
                                        if f.get("fragmento_id")
                                    ],
                                }
                    return {"fragmento_id": None, "archivo": None, "evidence_ids": []}

                codes_inserted = 0
                if suggested_codes:
                    from app.postgres_block import insert_candidate_codes

                    candidates = []
                    for code in suggested_codes:
                        code_clean = code.strip()
                        frag_info = _pick_fragment_info(code_clean)
                        frag_id = frag_info.get("fragmento_id") or "runner:global"
                        memo_base = (synthesis.get("memo_sintesis") or "")
                        evidence_ids = frag_info.get("evidence_ids") or []
                        evidence_note = f"Evidencias: {', '.join(evidence_ids)}. " if evidence_ids else ""
                        candidates.append({
                            "project_id": project_id,
                            "codigo": code_clean,
                            "cita": "Código sugerido por Runner Discovery (post-run)",
                            "fragmento_id": frag_id,
                            "archivo": frag_info.get("archivo") or "runner",
                            "fuente_origen": "discovery",
                            "fuente_detalle": f"runner:{task_id}",
                            "score_confianza": 0.75,
                            "estado": "pendiente",
                            "memo": (f"{evidence_note}{memo_base}")[:500],
                        })

                    codes_inserted = insert_candidate_codes(
                        clients.postgres,
                        candidates,
                        check_similar=True,
                    )

                report_path = _write_runner_report(
                    project_id=project_id,
                    task_id=task_id,
                    concepts=concepts,
                    discovery_result=discovery_result,
                    synthesis=synthesis,
                    codes_with_fragments=codes_with_fragments,
                    evidence_metrics=evidence_metrics,
                    org_id=org_id,
                )

                post_run = {
                    "report_path": report_path,
                    "structured": bool(synthesis.get("structured")),
                    "analysis": synthesis.get("memo_sintesis") or "",
                    "codes_suggested": suggested_codes,
                    "codes_with_fragments": codes_with_fragments,
                    "evidence_metrics": evidence_metrics,
                    "codes_inserted": int(codes_inserted),
                    "sample_fragments_count": len(sample_fragments),
                    "config": discovery_result.get("config") or {},
                }

                _agent_tasks[task_id].update({
                    "status": "completed",
                    "current_stage": 2,
                    "validated_codes": [],
                    "saturation_score": 0.0,
                    "final_report": None,
                    "codes_count": int(codes_inserted),
                    "post_run": post_run,
                    "errors": _agent_tasks[task_id].get("errors", []),
                    "final_landing_rate": _agent_tasks[task_id].get("final_landing_rate"),
                })
                _logger.info(
                    "agent.execute.completed.discovery_only.post_run",
                    task_id=task_id,
                    codes_inserted=codes_inserted,
                    report_path=report_path,
                )
                return
        finally:
            clients.close()

        # discovery_only queda manejado arriba (incluye post-run)

        # Fase 2+: Ejecutar resto del pipeline con run_agent_with_real_functions
        _logger.info("agent.coding.start", task_id=task_id)
        _agent_tasks[task_id]["current_stage"] = 3  # Coding stage

        from app.agent_standalone import run_agent_with_real_functions

        result = await run_agent_with_real_functions(
            project_id=project_id,
            concepts=concepts,
            max_iterations=max_iterations,
            max_interviews=max_interviews,
            iterations_per_interview=iterations_per_interview,
            discovery_only=False,
            task_callback=lambda state: _update_task_state(task_id, state),
        )

        # Merge errors from discovery and agent execution
        all_errors = _agent_tasks[task_id].get("errors", []) + result.get("errors", [])

        # Generate execution logs for frontend
        logs = [
            f" Agent started for project {project_id}",
            f" Concepts: {', '.join(concepts)}",
            f" Max interviews: {max_interviews}",
            f" Discovery phase completed with {_agent_tasks[task_id].get('memos_count', 0)} runs",
        ]
        if _agent_tasks[task_id].get("final_landing_rate"):
            lr = _agent_tasks[task_id]["final_landing_rate"]
            logs.append(f" Landing rate: {lr.get('landing_rate', 0):.1f}% ({lr.get('matched_count', 0)}/{lr.get('total_count', 0)} fragments)")
        if result.get("validated_codes"):
            logs.append(f" Generated {len(result.get('validated_codes', []))} validated codes")
        if all_errors:
            logs.append(f" {len(all_errors)} errors during execution")
        logs.append(f" Agent completed in {result.get('iteration', 0)} iterations")

        # Update final state
        _agent_tasks[task_id].update({
            "status": "completed",
            "current_stage": result.get("current_stage", 9),
            "iteration": result.get("iteration", 0),
            "validated_codes": result.get("validated_codes", []),
            "discovery_memos": result.get("discovery_memos", []),
            "saturation_score": result.get("saturation_score", 0.0),
            "final_report": result.get("final_report"),
            "memos_count": len(result.get("memos", [])),
            "codes_count": len(result.get("validated_codes", [])),
            "errors": all_errors if all_errors else None,
            "logs": logs,
        })

        _logger.info(
            "agent.execute.completed",
            task_id=task_id,
            iterations=result.get("iteration"),
            codes_count=len(result.get("validated_codes", [])),
            errors_count=len(all_errors),
        )

    except Exception as e:
        _logger.error("agent.execute.error", task_id=task_id, error=str(e))
        _agent_tasks[task_id].update({
            "status": "error",
            "error": str(e),
            "logs": [
                f" Agent started for project {project_id}",
                f" Error: {str(e)}",
            ],
        })


def _update_task_state(task_id: str, state: dict):
    """Callback para actualizar estado durante ejecución."""
    if task_id in _agent_tasks:
        _agent_tasks[task_id].update({
            "current_stage": state.get("current_stage", 0),
            "iteration": state.get("iteration", 0),
            "memos_count": len(state.get("memos", [])),
            "codes_count": len(state.get("validated_codes", [])),
        })
