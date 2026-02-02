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

from typing import Any, Dict, List, Optional, cast, Tuple
from datetime import datetime

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
    project: Optional[str] = None,
) -> Dict[str, Any]:
    from .axial import run_gds_analysis

    results = run_gds_analysis(clients, settings, algorithm, project=project)
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
    project: Optional[str] = None,
) -> List[Dict[str, Any]]:
    overview = centrality_overview(
        clients, settings, categoria=None, algorithm=algorithm, top_k=top_k, project=project
    )
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
        project=project_id,
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

    # --- GraphRAG Storyline (Etapa 5) ---
    # Genera una narrativa grounded en el grafo + evidencias (cuando hay servicios disponibles).
    # Si GraphRAG se abstiene (baja relevancia) o falla, seguimos con el resumen clásico potenciado.
    try:
        from .graphrag import graphrag_query

        _gr_query = prompt or (
            f"Realiza un análisis estructural profundo de la categoría núcleo '{categoria}'. "
            "Identifica clusters temáticos, nodos puente y las implicancias teóricas observadas."
        )
        if memo:
            _gr_query += f" Contexto del investigador (memo): {memo}"

        report["graphrag"] = graphrag_query(
            clients,
            settings,
            query=_gr_query,
            project=project_id,
            include_fragments=True,
            enforce_grounding=True,
        )
    except Exception as e:
        _logger.warning("nucleus.report.graphrag_error", error=str(e))
        report["graphrag_error"] = str(e)

    # --- Normalizar y exponer Storyline + Audit (versión PRO) ---
    # Construimos `storyline_graphrag` y `summary_metrics` para UI y auditoría.
    gr_payload = report.get("graphrag") if isinstance(report.get("graphrag"), dict) else None
    computed_at = datetime.utcnow().isoformat() + "Z"

    if gr_payload:
        # Mapear nodos clave a estructura compacta
        def _map_node(n: Any) -> Dict[str, Any]:
            return {
                "id": n.get("id") or n.get("node_id") or None,
                "label": n.get("label") or n.get("nombre") or None,
                "score": n.get("score") or None,
                "role": n.get("role") or n.get("tipo") or None,
            }

        nodes = []
        for n in gr_payload.get("central_nodes") or []:
            try:
                nodes.append(_map_node(n))
            except Exception:
                continue

        evidence_list = []
        for ev in gr_payload.get("evidence") or []:
            try:
                evidence_list.append(
                    {
                        "fragment_id": ev.get("fragmento_id") or ev.get("fragment_id") or None,
                        "source_doc": ev.get("archivo") or ev.get("source") or None,
                        "quote": ev.get("fragmento") or ev.get("quote") or None,
                        "relevance": ev.get("score") or ev.get("relevance") or None,
                        "support_type": ev.get("support_type") or ev.get("tipo_soporte") or None,
                    }
                )
            except Exception:
                continue

        storyline_graphrag = {
            "is_grounded": bool(gr_payload.get("is_grounded")),
            "mode": gr_payload.get("mode") or "standard",
            "answer": gr_payload.get("answer") or gr_payload.get("graph_summary"),
            "nodes": nodes,
            "evidence": evidence_list,
            "confidence": gr_payload.get("confidence") or gr_payload.get("confidence_level") or "NONE",
            "rejection": gr_payload.get("rejection"),
            "run_id": run_id,
            "computed_at": computed_at,
            "inputs": {
                "project_id": project_id,
                "scope_node_ids": gr_payload.get("context_node_ids") or gr_payload.get("node_ids"),
                "prompt": _gr_query,
                "mode": gr_payload.get("mode") or "standard",
                "retrieval": gr_payload.get("retrieval") or {},
            },
        }
    else:
        storyline_graphrag = {
            "is_grounded": False,
            "mode": "standard",
            "answer": None,
            "nodes": [],
            "evidence": [],
            "confidence": "NONE",
            "rejection": report.get("graphrag_error"),
            "run_id": run_id,
            "computed_at": computed_at,
            "inputs": {"project_id": project_id, "prompt": _gr_query},
        }

    # Summary metrics (deterministic, reproducible) — texto corto + métricas estructuradas
    pagerank_top = (report.get("centrality") or {}).get("top") or []
    summary_text_lines = [
        f"Categoría candidata: {categoria}",
        f"Centrality top (muestra): {', '.join([str(x.get('nombre')) for x in pagerank_top[:5]])}",
        f"Cobertura entrevistas (estimado): {coverage_interviews}",
        f"Roles cubiertos: {roles_cubiertos}",
        f"Citas icónicas: {quote_count}",
        f"Probe resultados: {len(probe_results)} | entrevistas en probe: {len(probe_interviews)}",
        f"Checks: {checks}",
    ]
    summary_metrics = {
        "pagerank_top": pagerank_top,
        "coverage": {
            "interviews": coverage_interviews,
            "roles": roles_cubiertos,
            "fragments": quote_count,
        },
        "thresholds": report.get("thresholds"),
        "checks": checks,
        "probe": report.get("probe"),
        "run_id": run_id,
        "computed_at": computed_at,
        "inputs": {"project_id": project_id, "prompt": prompt, "probe_top": probe_top, "filters": filters},
        "text_summary": "\n".join(summary_text_lines),
    }

    report["storyline_graphrag"] = storyline_graphrag
    report["summary_metrics"] = summary_metrics

    # --- Exploratory Scan fallback (modo no causal, descriptivo) ---
    # Si GraphRAG estandar/deep se abstuvo, generamos un "Exploratory Scan"
    abstention: Optional[Dict[str, Any]] = None
    if not storyline_graphrag.get("is_grounded"):
        rejection = gr_payload.get("rejection") if isinstance(gr_payload, dict) else None
        if isinstance(rejection, dict):
            abstention = {
                "reason": rejection.get("reason") or "",
                "suggestion": rejection.get("suggestion"),
                "fragments_found": rejection.get("fragments_found"),
                "top_score": rejection.get("top_score"),
            }
        elif rejection:
            abstention = {"reason": str(rejection)}
        elif report.get("graphrag_error"):
            abstention = {"reason": str(report.get("graphrag_error"))}
    report["abstention"] = abstention

    exploratory_scan = None
    try:
        need_exploratory = not storyline_graphrag.get("is_grounded")
        if need_exploratory:
            # Si la abstencion fue por falta de fragmentos, forzar modo exploratorio.
            force_mode = None
            if isinstance(abstention, dict):
                fragments_found = abstention.get("fragments_found")
                if isinstance(fragments_found, int) and 0 < fragments_found < 2:
                    force_mode = "exploratory"

            exploratory_payload = graphrag_query(
                clients,
                settings,
                query=_gr_query,
                project=project_id,
                include_fragments=True,
                enforce_grounding=False,
                force_mode=force_mode,
            )
            report["graphrag_exploratory"] = exploratory_payload

            def _map_evidence(ev: Any) -> Dict[str, Any]:
                return {
                    "fragment_id": ev.get("fragmento_id") or ev.get("fragment_id") or None,
                    "source_doc": ev.get("archivo") or ev.get("doc_id") or ev.get("doc_ref") or None,
                    "quote": ev.get("texto") or ev.get("fragmento") or ev.get("snippet") or ev.get("quote") or None,
                    "relevance": ev.get("score") or ev.get("relevance") or None,
                    "support_type": ev.get("supports") or ev.get("support_type") or ev.get("tipo_soporte") or None,
                }

            exploratory_evidence = []
            for ev in exploratory_payload.get("evidence") or []:
                try:
                    exploratory_evidence.append(_map_evidence(ev))
                except Exception:
                    continue

            exploratory_scan = {
                "mode": exploratory_payload.get("mode") or "exploratory",
                "relevance_score": exploratory_payload.get("relevance_score"),
                "fallback_reason": exploratory_payload.get("fallback_reason"),
                "graph_summary": exploratory_payload.get("graph_summary") or exploratory_payload.get("answer"),
                "central_nodes": exploratory_payload.get("central_nodes") or [],
                "evidence": exploratory_evidence,
                "questions": exploratory_payload.get("questions") or [],
                "recommendations": exploratory_payload.get("recommendations") or [],
                "research_feedback": exploratory_payload.get("research_feedback"),
                "confidence": exploratory_payload.get("confidence"),
                "computed_at": computed_at,
                "inputs": {"project_id": project_id, "prompt": _gr_query},
            }
    except Exception as e:  # pragma: no cover - resiliencia
        _logger.warning("nucleus.report.exploratory_error", error=str(e))
        report["graphrag_exploratory_error"] = str(e)

    report["exploratory_scan"] = exploratory_scan

    llm_model_resolved: Optional[str] = None
    llm_summary_model: Optional[str] = None
    if llm_model:
        llm_model_resolved = _resolve_llm_model(settings, llm_model)
        if llm_model_resolved:
            try:
                # Si el usuario pidió LLM, generamos el resumen LLM como fallback.
                llm_summary_model = _generate_nucleus_summary(
                    clients,
                    settings,
                    categoria=categoria,
                    report=report,
                    model_name=llm_model_resolved,
                )
            except Exception as exc:  # pragma: no cover - resilience
                _logger.warning("nucleus.report.llm_error", error=str(exc))
                llm_summary_model = None
                llm_model_resolved = None

    # Prioridad final para `llm_summary` (compatibilidad):
    # 1) Storyline GraphRAG (answer) si está grounded
    # 2) Resumen LLM (si se generó)
    # 3) Texto determinístico de `summary_metrics`
    final_storyline_answer = None
    try:
        if report.get("storyline_graphrag") and report["storyline_graphrag"].get("is_grounded"):
            final_storyline_answer = report["storyline_graphrag"].get("answer")
    except Exception:
        final_storyline_answer = None

    llm_summary: Optional[str] = final_storyline_answer or llm_summary_model or summary_metrics.get("text_summary")

    if final_storyline_answer:
        _logger.info("nucleus.report.storyline_from_graphrag", categoria=categoria)

    report["llm_summary"] = llm_summary
    report["llm_model"] = llm_model_resolved

    persisted = False
    if (persist or memo or llm_summary) and run_id:
        # Build canonical payload for frontend/audit before persisting
        try:
            storyline_canonical, audit_summary_canonical = build_canonical_storyline_and_audit(report)
            report["storyline"] = storyline_canonical
            report["audit_summary"] = audit_summary_canonical
            # Ensure llm_summary follows compatibility rule: grounded answer > existing llm_summary > audit summary
            if storyline_canonical.get("mode") == "grounded" and storyline_canonical.get("answer_md"):
                llm_summary = storyline_canonical.get("answer_md")
            else:
                llm_summary = llm_summary or audit_summary_canonical.get("summary_md")
            report["llm_summary"] = llm_summary
        except Exception as e:
            _logger.warning("nucleus.report.build_canonical_error", error=str(e))
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

    # --- Inyección de Contexto GraphRAG (Storyline) ---
    gr_payload = report.get("graphrag")
    if gr_payload and isinstance(gr_payload, dict):
        graph_summary = gr_payload.get("graph_summary")
        if graph_summary:
            lines.append(f"Storyline Estructural (GraphRAG): {graph_summary}")
        
        c_nodes = gr_payload.get("central_nodes")
        if c_nodes and isinstance(c_nodes, list):
            names = [str(n.get("label") or n.get("code_id") or "") for n in c_nodes[:5]]
            lines.append(f"Nodos clave en el subgrafo: {', '.join(filter(None, names))}")
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


def build_canonical_storyline_and_audit(report: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Construye `storyline` y `audit_summary` en el formato canonical propuesto.

    No modifica keys legacy excepto para devolver los dicts.
    """
    story_src = report.get("storyline_graphrag") or report.get("graphrag") or {}
    summary_src = report.get("summary_metrics") or {}

    # mode
    if story_src.get("is_grounded"):
        mode = "grounded"
    elif story_src.get("exploratory_used") or story_src.get("mode") == "exploratory":
        mode = "exploratory"
    else:
        mode = "abstained"

    # answer as markdown
    answer_md = None
    if story_src.get("answer"):
        answer_md = story_src.get("answer")
    elif story_src.get("answer_md"):
        answer_md = story_src.get("answer_md")

    evidence = story_src.get("evidence") or []

    # relevance
    max_score = None
    try:
        scores = [e.get("relevance") or e.get("score") for e in evidence if isinstance(e, dict)]
        scores = [s for s in scores if isinstance(s, (int, float))]
        if scores:
            max_score = max(scores)
    except Exception:
        max_score = None

    relevance = {"max_score": max_score, "threshold": (story_src.get("inputs", {}).get("retrieval", {}).get("threshold") if isinstance(story_src.get("inputs", {}).get("retrieval", {}), dict) else None)}

    scope = {"context_node_ids": story_src.get("inputs", {}).get("scope_node_ids") or story_src.get("inputs", {}).get("context_node_ids"), "visible_nodes": len(story_src.get("nodes") or [])}

    graph_insights = {
        "clusters": story_src.get("inputs", {}).get("retrieval", {}).get("clusters") or story_src.get("clusters") or [],
        "bridge_nodes": [],
        "gaps": [],
    }
    # bridge nodes heuristic
    try:
        for n in story_src.get("nodes") or []:
            if isinstance(n, dict) and (n.get("role") == "bridge" or n.get("role") == "puente"):
                graph_insights["bridge_nodes"].append({"node_id": n.get("id"), "reason": "role=bridge"})
    except Exception:
        pass

    if story_src.get("rejection"):
        graph_insights["gaps"].append(str(story_src.get("rejection")))

    abstention = None
    if mode == "abstained":
        abstention = story_src.get("rejection") or story_src.get("graphrag_error")

    storyline = {
        "mode": mode,
        "is_grounded": bool(story_src.get("is_grounded")),
        "answer_md": answer_md,
        "relevance": relevance,
        "scope": scope,
        "evidence": evidence,
        "graph_insights": graph_insights,
        "abstention": abstention,
        "run_id": story_src.get("run_id"),
        "computed_at": story_src.get("computed_at"),
    }

    audit_summary = {
        "summary_md": summary_src.get("text_summary") or summary_src.get("summary_md") or None,
        "pagerank_top": summary_src.get("pagerank_top") or (report.get("centrality") or {}).get("top"),
        "coverage": summary_src.get("coverage") or report.get("coverage"),
        "checks": report.get("checks"),
        "probe": summary_src.get("probe") or report.get("probe"),
        "run_id": summary_src.get("run_id"),
        "computed_at": summary_src.get("computed_at"),
    }

    return storyline, audit_summary
