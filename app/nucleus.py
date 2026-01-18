"""
Identificación del núcleo selectivo (core category).

En Teoría Fundamentada, el "núcleo selectivo" es la categoría central
que integra todas las demás categorías y representa el fenómeno principal.

Este módulo implementa:
1. Análisis de centralidad de categorías (PageRank, etc.)
2. Reportes de cobertura por categoría
3. Probe semántica para exploración temática
4. Reportes integrados de candidatos a núcleo

Funciones principales:
    - centrality_overview(): Ranking de categorías por centralidad
    - coverage_report(): Cobertura de categoría (entrevistas, roles, citas)
    - probe_semantics(): Búsqueda semántica con filtros
    - nucleus_report(): Reporte completo para evaluar candidato a núcleo

Criterios de núcleo selectivo (en nucleus_report):
    - centrality: Categoría en top-N de centralidad
    - coverage: Presente en mínimo de entrevistas y roles
    - quotes: Mínimo de citas icónicas
    - probe: Relevancia semántica en búsquedas exploratorias

Generación de memos LLM:
    Opcionalmente genera resúmenes analíticos usando el LLM
    que evalúan el estado del núcleo selectivo.

Example:
    >>> from app.nucleus import nucleus_report
    >>> report = nucleus_report(
    ...     clients, settings,
    ...     categoria="resiliencia_comunitaria",
    ...     prompt="adaptación ante desastres",
    ...     min_interviews=3,
    ...     persist=True,
    ...     llm_model="gpt-5-mini"
    ... )
    >>> print(report["done"])  # True si cumple todos los criterios
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

import structlog
from qdrant_client.models import Condition, FieldCondition, Filter, MatchValue

from .clients import ServiceClients
from .postgres_block import (
    coverage_for_category,
    quote_count_for_category,
    quotes_for_category,
    upsert_nucleus_memo,
)
from .settings import AppSettings
from .qdrant_block import ensure_payload_indexes
from .queries import _build_project_filter

_logger = structlog.get_logger()


def centrality_overview(
    clients: ServiceClients,
    settings: AppSettings,
    categoria: Optional[str] = None,
    algorithm: str = "pagerank",
    top_k: int = 10,
) -> Dict[str, Any]:
    from .axial import run_gds_analysis

    results = run_gds_analysis(clients, settings, algorithm)
    categories = [
        row
        for row in results
        if isinstance(row.get("etiquetas"), list) and "Categoria" in cast(List[str], row.get("etiquetas", []))
    ]

    overview: Dict[str, Any] = {
        "algorithm": algorithm,
        "total_categorias": len(categories),
        "top": [],
        "candidate": None,
    }

    target = categoria.lower().strip() if categoria else None
    top_entries: List[Dict[str, Any]] = []
    candidate_entry: Optional[Dict[str, Any]] = None

    for idx, row in enumerate(categories):
        entry = {
            "nombre": row.get("nombre"),
            "etiquetas": row.get("etiquetas"),
            "score": row.get("score"),
            "community_id": row.get("community_id"),
            "rank": idx + 1,
        }
        top_entries.append(entry)
        if target and isinstance(entry.get("nombre"), str) and entry["nombre"].lower() == target:
            candidate_entry = entry

    overview["top"] = top_entries[:top_k]
    overview["candidate"] = candidate_entry
    return overview


def centrality_report(
    clients: ServiceClients,
    settings: AppSettings,
    algorithm: str = "pagerank",
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    overview = centrality_overview(clients, settings, categoria=None, algorithm=algorithm, top_k=top_k)
    return overview["top"]


def coverage_report(clients: ServiceClients, categoria: str, quote_limit: int = 5, project: Optional[str] = None) -> Dict[str, Any]:
    project_id = project or "default"
    stats = coverage_for_category(clients.postgres, categoria, project_id)
    quotes = quotes_for_category(clients.postgres, categoria, project_id, quote_limit)
    stats["quotes"] = quotes
    stats["quote_count"] = quote_count_for_category(clients.postgres, categoria, project_id)
    stats["quotes_limit"] = quote_limit
    return stats


def probe_semantics(
    clients: ServiceClients,
    settings: AppSettings,
    prompt: str,
    top_k: int = 10,
    filters: Optional[Dict[str, Any]] = None,
    project: Optional[str] = None,
) -> List[Dict[str, Any]]:
    # ensure payload indexes exist prior to probing
    ensure_payload_indexes(clients.qdrant, settings.qdrant.collection)

    vector = clients.aoai.embeddings.create(
        model=settings.azure.deployment_embed,
        input=prompt,
    ).data[0].embedding

    project_id = project or "default"

    def build_filter(speaker_value: Optional[str]) -> Filter:
        base = _build_project_filter(project_id, speaker_value)
        must: List[Condition] = cast(List[Condition], list(base.must)) if base.must else []
        must_not: List[Condition] = cast(List[Condition], list(base.must_not)) if base.must_not else []
        if filters:
            if filters.get("archivo"):
                must.append(FieldCondition(key="archivo", match=MatchValue(value=filters["archivo"])))
            if filters.get("area_tematica"):
                must.append(FieldCondition(key="area_tematica", match=MatchValue(value=filters["area_tematica"])))
            if filters.get("actor_principal"):
                must.append(FieldCondition(key="actor_principal", match=MatchValue(value=filters["actor_principal"])))
            if filters.get("requiere_protocolo_lluvia") is not None:
                must.append(
                    FieldCondition(
                        key="requiere_protocolo_lluvia",
                        match=MatchValue(value=bool(filters["requiere_protocolo_lluvia"])),
                    )
                )
        return Filter(must=must, must_not=must_not or None)

    speaker_filter = (filters or {}).get("speaker") or "interviewee"
    q_filter = build_filter(speaker_filter)

    response = clients.qdrant.query_points(
        collection_name=settings.qdrant.collection,
        query=vector,
        limit=top_k,
        with_payload=True,
        query_filter=q_filter,
    )
    if speaker_filter and not response.points:
        q_filter = build_filter(None)
        response = clients.qdrant.query_points(
            collection_name=settings.qdrant.collection,
            query=vector,
            limit=top_k,
            with_payload=True,
            query_filter=q_filter,
        )

    suggestions: List[Dict[str, Any]] = []
    for point in response.points:
        payload = point.payload or {}
        suggestions.append(
            {
                "fragmento_id": str(point.id),
                "score": point.score,
                "archivo": payload.get("archivo"),
                "par_idx": payload.get("par_idx"),
                "fragmento": payload.get("fragmento"),
                "area_tematica": payload.get("area_tematica"),
                "actor_principal": payload.get("actor_principal"),
                "requiere_protocolo_lluvia": payload.get("requiere_protocolo_lluvia"),
            }
        )
    return suggestions


def nucleus_report(
    clients: ServiceClients,
    settings: AppSettings,
    categoria: str,
    prompt: Optional[str],
    *,
    algorithm: str = "pagerank",
    centrality_top: int = 10,
    centrality_rank_max: int = 5,
    probe_top: int = 10,
    min_interviews: int = 3,
    min_roles: int = 2,
    min_quotes: int = 5,
    quote_limit: int = 10,
    filters: Optional[Dict[str, Any]] = None,
    memo: Optional[str] = None,
    persist: bool = False,
    llm_model: Optional[str] = None,
    run_id: Optional[str] = None,
    project: Optional[str] = None,
) -> Dict[str, Any]:
    """Aggregate triangulation metrics for the núcleo candidate."""

    project_id = project or "default"
    quote_limit = max(quote_limit, min_quotes)
    centrality = centrality_overview(
        clients,
        settings,
        categoria=categoria,
        algorithm=algorithm,
        top_k=centrality_top,
    )
    coverage = coverage_report(clients, categoria, quote_limit=quote_limit, project=project_id)

    probe_results: List[Dict[str, Any]] = []
    if prompt:
        probe_results = probe_semantics(
            clients,
            settings,
            prompt=prompt,
            top_k=probe_top,
            filters=filters,
            project=project_id,
        )

    probe_interviews = sorted(
        {
            archivo
            for archivo in (item.get("archivo") for item in probe_results)
            if isinstance(archivo, str)
        }
    )

    coverage_interviews = coverage.get("entrevistas_cubiertas") or len(coverage.get("archivos", []))
    roles_cubiertos = coverage.get("roles_cubiertos", 0)
    quote_count = coverage.get("quote_count", 0)

    candidate = centrality.get("candidate") or {}
    candidate_rank = candidate.get("rank")
    centrality_ok = bool(candidate_rank and candidate_rank <= centrality_rank_max)
    coverage_ok = coverage_interviews >= min_interviews and roles_cubiertos >= max(min_roles, 0)
    quotes_ok = quote_count >= min_quotes
    probe_ok = bool(prompt) and len(probe_interviews) >= min_interviews

    checks = {
        "centrality": centrality_ok,
        "coverage": coverage_ok,
        "quotes": quotes_ok,
        "probe": probe_ok,
    }

    report: Dict[str, Any] = {
        "categoria": categoria,
        "centrality": centrality,
        "coverage": coverage,
        "probe": {
            "prompt": prompt,
            "top_k": probe_top,
            "filters": filters,
            "results": probe_results,
            "entrevistas": probe_interviews,
            "total_resultados": len(probe_results),
        },
        "thresholds": {
            "centrality_rank_max": centrality_rank_max,
            "min_interviews": min_interviews,
            "min_roles": min_roles,
            "min_quotes": min_quotes,
        },
        "checks": checks,
    }
    report["done"] = all(checks.values())
    report["memo"] = memo

    llm_model_resolved: Optional[str] = None
    llm_summary: Optional[str] = None
    if llm_model:
        llm_model_resolved = _resolve_llm_model(settings, llm_model)
        if llm_model_resolved:
            try:
                llm_summary = _generate_nucleus_summary(
                    clients,
                    settings,
                    categoria=categoria,
                    report=report,
                    model_name=llm_model_resolved,
                )
            except Exception as exc:  # pragma: no cover - resilience
                _logger.warning("nucleus.report.llm_error", error=str(exc))
                llm_summary = None
                llm_model_resolved = None

    report["llm_summary"] = llm_summary
    report["llm_model"] = llm_model_resolved

    persisted = False
    if (persist or memo or llm_summary) and run_id:
        try:
            upsert_nucleus_memo(
                clients.postgres,
                categoria=categoria,
                project=project,
                run_id=run_id,
                memo=memo,
                llm_summary=llm_summary,
                payload=report,
            )
            persisted = True
        except Exception as exc:  # pragma: no cover - defensive
            _logger.warning("nucleus.report.persist_error", error=str(exc))

    report["persisted"] = persisted
    return report


def _resolve_llm_model(settings: AppSettings, alias: Optional[str]) -> Optional[str]:
    if not alias:
        return None
    normalized = alias.strip().lower()
    if normalized in {"gpt-5-mini", "gpt5-mini", "mini"}:
        return settings.azure.deployment_chat_mini or settings.azure.deployment_chat
    if normalized in {"gpt-5.2-chat", "gpt-5-chat", "gpt5-chat", "chat"}:
        return settings.azure.deployment_chat
    return alias


def _generate_nucleus_summary(
    clients: ServiceClients,
    settings: AppSettings,
    *,
    categoria: str,
    report: Dict[str, Any],
    model_name: str,
) -> Optional[str]:
    if not model_name:
        return None

    candidate = (report.get("centrality") or {}).get("candidate") or {}
    centrality_rank = candidate.get("rank")
    centrality_score = candidate.get("score")
    coverage = report.get("coverage") or {}
    quotes = coverage.get("quote_count")
    interviews = coverage.get("entrevistas_cubiertas") or len(coverage.get("archivos", []) or [])
    roles = coverage.get("roles_cubiertos")
    checks = report.get("checks") or {}
    probe = report.get("probe") or {}
    probe_count = probe.get("total_resultados")
    probe_interviews = len(probe.get("entrevistas") or [])

    lines = [
        "Evalúa el estado del núcleo selectivo desde teoría fundamentada.",
        "Ofrece hasta 4 viñetas con hallazgos clave y una recomendación final.",
        f"Categoría candidata: {categoria}",
        f"Centralidad rank: {centrality_rank or 'sin rank'} | score: {centrality_score or 'N/A'}",
        f"Cobertura entrevistas: {interviews} | roles: {roles}",
        f"Citas icónicas: {quotes}",
        f"Resultados de probe semántica: {probe_count} | entrevistas en probe: {probe_interviews}",
        f"Checks: centrality={checks.get('centrality')}, coverage={checks.get('coverage')}, quotes={checks.get('quotes')}, probe={checks.get('probe')}",
    ]
    if probe.get("prompt"):
        prompt_preview = (probe.get("prompt") or "")[:280]
        lines.append(f"Prompt: {prompt_preview}")
    if report.get("memo"):
        memo_preview = (report.get("memo") or "")[:280]
        lines.append(f"Memo analítico: {memo_preview}")

    messages = [
        {"role": "system", "content": "Eres un investigador cualitativo experto en teoría fundamentada."},
        {"role": "user", "content": "\n".join(lines)},
    ]

    aoai_client = getattr(clients, "aoai", None)
    if aoai_client is None:
        return None

    kwargs = {
        "model": model_name,
        "messages": messages,
    }
    
    # gpt-5.x models no soportan temperature != 1, no enviar el parámetro
    kwargs["max_completion_tokens"] = 400

    response = aoai_client.chat.completions.create(**kwargs)
    if not response.choices:
        return None
    return response.choices[0].message.content
