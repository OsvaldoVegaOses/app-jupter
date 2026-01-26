from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import structlog

from app.clients import ServiceClients
from app.settings import AppSettings

_logger = structlog.get_logger()


def _truncate(text: str, limit: int) -> str:
    clean = (text or "").strip()
    if limit <= 0:
        return clean
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip() + "…"


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _cooccurrence_fragment_ids_neo4j(
    clients: ServiceClients,
    settings: AppSettings,
    *,
    project_id: str,
    code_a: str,
    code_b: str,
    limit: int,
) -> List[str]:
    if not clients.neo4j:
        return []

    cypher = """
    MATCH (f:Fragmento {project_id: $project_id})-[:TIENE_CODIGO]->(c1:Codigo {nombre: $code_a, project_id: $project_id})
    MATCH (f)-[:TIENE_CODIGO]->(c2:Codigo {nombre: $code_b, project_id: $project_id})
    RETURN f.id AS fragmento_id
    LIMIT $limit
    """
    try:
        with clients.neo4j.session(database=settings.neo4j.database) as session:
            result = session.run(
                cypher,
                project_id=project_id,
                code_a=code_a,
                code_b=code_b,
                limit=int(limit),
            )
            return [str(r["fragmento_id"]) for r in result if r and r.get("fragmento_id")]
    except Exception as exc:  # noqa: BLE001
        _logger.debug(
            "axial_evidence.neo4j_cooccurrence_failed",
            project_id=project_id,
            error=str(exc)[:200],
        )
        return []


def _cooccurrence_fragment_ids_pg(
    clients: ServiceClients,
    *,
    project_id: str,
    code_a: str,
    code_b: str,
    limit: int,
) -> List[str]:
    # Requires open coding evidence table.
    from app.postgres_block import ensure_open_coding_table

    ensure_open_coding_table(clients.postgres)
    sql = """
    SELECT a.fragmento_id
      FROM analisis_codigos_abiertos a
      JOIN analisis_codigos_abiertos b
        ON b.project_id = a.project_id
       AND b.fragmento_id = a.fragmento_id
      JOIN entrevista_fragmentos ef
        ON ef.project_id = a.project_id
       AND ef.id = a.fragmento_id
     WHERE a.project_id = %s
       AND a.codigo = %s
       AND b.codigo = %s
       AND (ef.speaker IS NULL OR ef.speaker <> 'interviewer')
     ORDER BY ef.archivo, ef.par_idx
     LIMIT %s
    """
    with clients.postgres.cursor() as cur:
        cur.execute(sql, (project_id, code_a, code_b, int(limit)))
        return [str(r[0]) for r in (cur.fetchall() or []) if r and r[0]]


def _single_code_fragment_ids_pg(
    clients: ServiceClients,
    *,
    project_id: str,
    code: str,
    exclude_ids: Sequence[str],
    limit: int,
) -> List[str]:
    from app.postgres_block import ensure_open_coding_table

    ensure_open_coding_table(clients.postgres)
    exclude = [str(x) for x in exclude_ids if str(x)]
    sql = """
    SELECT DISTINCT aca.fragmento_id
      FROM analisis_codigos_abiertos aca
      JOIN entrevista_fragmentos ef
        ON ef.project_id = aca.project_id
       AND ef.id = aca.fragmento_id
     WHERE aca.project_id = %s
       AND aca.codigo = %s
       AND (ef.speaker IS NULL OR ef.speaker <> 'interviewer')
       AND NOT (aca.fragmento_id = ANY(%s))
     ORDER BY aca.fragmento_id
     LIMIT %s
    """
    with clients.postgres.cursor() as cur:
        cur.execute(sql, (project_id, code, exclude, int(limit)))
        return [str(r[0]) for r in (cur.fetchall() or []) if r and r[0]]


def _negative_case_fragment_ids_pg(
    clients: ServiceClients,
    *,
    project_id: str,
    positive_code: str,
    negative_code: str,
    exclude_ids: Sequence[str],
    limit: int,
) -> List[str]:
    """Return fragments where positive_code appears and negative_code does NOT (coded evidence)."""
    from app.postgres_block import ensure_open_coding_table

    ensure_open_coding_table(clients.postgres)
    exclude = [str(x) for x in exclude_ids if str(x)]
    sql = """
    SELECT DISTINCT aca.fragmento_id
      FROM analisis_codigos_abiertos aca
      JOIN entrevista_fragmentos ef
        ON ef.project_id = aca.project_id
       AND ef.id = aca.fragmento_id
     WHERE aca.project_id = %s
       AND aca.codigo = %s
       AND (ef.speaker IS NULL OR ef.speaker <> 'interviewer')
       AND NOT EXISTS (
             SELECT 1
               FROM analisis_codigos_abiertos b
              WHERE b.project_id = aca.project_id
                AND b.fragmento_id = aca.fragmento_id
                AND b.codigo = %s
       )
       AND NOT (aca.fragmento_id = ANY(%s))
     ORDER BY aca.fragmento_id
     LIMIT %s
    """
    with clients.postgres.cursor() as cur:
        cur.execute(sql, (project_id, positive_code, negative_code, exclude, int(limit)))
        return [str(r[0]) for r in (cur.fetchall() or []) if r and r[0]]


def _fetch_fragment_snapshot(
    clients: ServiceClients,
    *,
    project_id: str,
    fragment_id: str,
    excerpt_chars: int,
) -> Optional[Dict[str, Any]]:
    from app.postgres_block import fetch_fragment_by_id

    frag = fetch_fragment_by_id(clients.postgres, fragment_id, project_id)
    if not frag:
        return None
    if frag.get("speaker") == "interviewer":
        return None
    return {
        "fragmento_id": str(frag.get("id")),
        "archivo": frag.get("archivo"),
        "par_idx": frag.get("par_idx"),
        "speaker": frag.get("speaker"),
        "fragmento": _truncate(str(frag.get("fragmento") or ""), excerpt_chars),
    }


def build_link_prediction_evidence_pack(
    clients: ServiceClients,
    settings: AppSettings,
    *,
    project_id: str,
    suggestions: Sequence[Dict[str, Any]],
    positive_total: int = 24,
    negative_total: int = 12,
    excerpt_chars: int = 280,
) -> Dict[str, Any]:
    """Build evidence pack for link prediction suggestions (positive + negative cases).

    Evidence sources:
    - direct co-occurrence from coded fragments (Neo4j TIENE_CODIGO or Postgres analisis_codigos_abiertos)
    - negative cases from coded fragments (A without B, B without A)
    - optional semantic fallback via Qdrant (pair query + contrast) when evidence is scarce
    """
    normalized: List[Dict[str, Any]] = []
    for raw in suggestions:
        src = str(raw.get("source") or "").strip()
        tgt = str(raw.get("target") or "").strip()
        if not src or not tgt:
            continue
        normalized.append(
            {
                "source": src,
                "target": tgt,
                "score": _safe_float(raw.get("score", 0.0)),
                "evidence_ids": raw.get("evidence_ids"),
            }
        )

    n = len(normalized)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if n == 0:
        return {
            "schema_version": 1,
            "generated_at": now,
            "limits": {
                "positive_total": int(positive_total),
                "negative_total": int(negative_total),
                "excerpt_chars": int(excerpt_chars),
            },
            "suggestions": [],
            "totals": {"positive": 0, "negative": 0, "by_method": {}},
            "notes": {"reason": "no_suggestions"},
        }

    # Allocate per-suggestion budgets (keeps UI predictable and stable).
    # Use an exact distribution (sum == totals) to avoid truncating suggestions.
    pos_total = max(int(positive_total), 0)
    neg_total = max(int(negative_total), 0)

    pos_base = (pos_total // n) if n else 0
    pos_rem = (pos_total % n) if n else 0
    pos_quotas = [pos_base + (1 if i < pos_rem else 0) for i in range(n)]

    neg_base = (neg_total // n) if n else 0
    neg_rem = (neg_total % n) if n else 0
    neg_quotas = [neg_base + (1 if i < neg_rem else 0) for i in range(n)]

    # Safety caps (rare with defaults, but keeps payload bounded for n small).
    pos_quotas = [min(int(q), 6) for q in pos_quotas]
    neg_quotas = [min(int(q), 4) for q in neg_quotas]

    used_positive: set[str] = set()
    used_negative: set[str] = set()
    method_counter: Counter[str] = Counter()

    suggestions_out: List[Dict[str, Any]] = []
    for idx, s in enumerate(normalized, 1):
        code_a = s["source"]
        code_b = s["target"]
        pos_budget = int(pos_quotas[idx - 1]) if idx - 1 < len(pos_quotas) else 0
        neg_budget = int(neg_quotas[idx - 1]) if idx - 1 < len(neg_quotas) else 0

        pos_items: List[Dict[str, Any]] = []
        neg_items: List[Dict[str, Any]] = []
        coverage: Counter[str] = Counter()
        notes: Dict[str, Any] = {}

        # 0) Provided evidence IDs (if upstream already computed them).
        provided = s.get("evidence_ids")
        if pos_budget > 0 and isinstance(provided, list):
            for fid in [str(x) for x in provided if x]:
                if len(pos_items) >= pos_budget:
                    break
                if fid in used_positive:
                    continue
                snap = _fetch_fragment_snapshot(clients, project_id=project_id, fragment_id=fid, excerpt_chars=excerpt_chars)
                if not snap:
                    continue
                snap["method"] = "provided_evidence_ids"
                pos_items.append(snap)
                used_positive.add(fid)
                coverage["provided_evidence_ids"] += 1

        # 1) Direct co-occurrence (best evidence).
        if pos_budget > 0 and len(pos_items) < pos_budget:
            co_ids: List[str] = []
            co_ids = _cooccurrence_fragment_ids_neo4j(
                clients,
                settings,
                project_id=project_id,
                code_a=code_a,
                code_b=code_b,
                limit=max(pos_budget * 3, 6),
            )
            co_method = "cooccurrence_neo4j"
            if not co_ids:
                co_ids = _cooccurrence_fragment_ids_pg(
                    clients, project_id=project_id, code_a=code_a, code_b=code_b, limit=max(pos_budget * 3, 6)
                )
                co_method = "cooccurrence_pg"

            for fid in co_ids:
                if len(pos_items) >= pos_budget:
                    break
                if fid in used_positive:
                    continue
                snap = _fetch_fragment_snapshot(clients, project_id=project_id, fragment_id=fid, excerpt_chars=excerpt_chars)
                if not snap:
                    continue
                snap["method"] = co_method
                snap["present_source"] = True
                snap["present_target"] = True
                pos_items.append(snap)
                used_positive.add(fid)
                coverage[co_method] += 1

        # 2) Negative cases from coded fragments (variation/tension).
        if neg_budget > 0:
            neg_ids_a = _negative_case_fragment_ids_pg(
                clients,
                project_id=project_id,
                positive_code=code_a,
                negative_code=code_b,
                exclude_ids=list(used_negative) + list(used_positive),
                limit=max(neg_budget * 3, 6),
            )
            for fid in neg_ids_a:
                if len(neg_items) >= neg_budget:
                    break
                if fid in used_negative:
                    continue
                snap = _fetch_fragment_snapshot(clients, project_id=project_id, fragment_id=fid, excerpt_chars=excerpt_chars)
                if not snap:
                    continue
                snap["method"] = "negative_case_pg"
                snap["present_source"] = True
                snap["present_target"] = False
                neg_items.append(snap)
                used_negative.add(fid)
                coverage["negative_case_pg"] += 1

            if len(neg_items) < neg_budget:
                neg_ids_b = _negative_case_fragment_ids_pg(
                    clients,
                    project_id=project_id,
                    positive_code=code_b,
                    negative_code=code_a,
                    exclude_ids=list(used_negative) + list(used_positive),
                    limit=max(neg_budget * 3, 6),
                )
                for fid in neg_ids_b:
                    if len(neg_items) >= neg_budget:
                        break
                    if fid in used_negative:
                        continue
                    snap = _fetch_fragment_snapshot(
                        clients, project_id=project_id, fragment_id=fid, excerpt_chars=excerpt_chars
                    )
                    if not snap:
                        continue
                    snap["method"] = "negative_case_pg"
                    snap["present_source"] = False
                    snap["present_target"] = True
                    neg_items.append(snap)
                    used_negative.add(fid)
                    coverage["negative_case_pg"] += 1

        # 3) Semantic fallback (pair query) when direct evidence is scarce.
        #    This keeps the feature usable even when codes were suggested by communities (no co-occurrence).
        if pos_budget > 0 and len(pos_items) < min(2, pos_budget):
            try:
                from app.queries import semantic_search
                from app.postgres_block import coded_fragments_for_code

                results = semantic_search(
                    clients,
                    settings,
                    query=f"{code_a} {code_b}",
                    top_k=max(pos_per * 2, 6),
                    project=project_id,
                    speaker="interviewee",
                    use_hybrid=True,
                    bm25_weight=0.25,
                )
                cand_ids = [str(r.get("fragmento_id")) for r in results if r and r.get("fragmento_id")]
                present_a = coded_fragments_for_code(clients.postgres, code_a, cand_ids, project_id)
                present_b = coded_fragments_for_code(clients.postgres, code_b, cand_ids, project_id)
                for r in results:
                    if len(pos_items) >= pos_budget:
                        break
                    fid = str(r.get("fragmento_id") or "")
                    if not fid or fid in used_positive:
                        continue
                    # Keep at least some connection to the codes (either is fine for context).
                    if not (present_a.get(fid) or present_b.get(fid)):
                        continue
                    item = {
                        "fragmento_id": fid,
                        "archivo": r.get("archivo"),
                        "par_idx": r.get("par_idx"),
                        "speaker": r.get("speaker"),
                        "fragmento": _truncate(str(r.get("fragmento") or ""), excerpt_chars),
                        "method": "semantic_pair",
                        "score": _safe_float(r.get("score")),
                        "present_source": bool(present_a.get(fid)),
                        "present_target": bool(present_b.get(fid)),
                    }
                    pos_items.append(item)
                    used_positive.add(fid)
                    coverage["semantic_pair"] += 1
            except Exception as exc:  # noqa: BLE001
                _logger.debug(
                    "axial_evidence.semantic_pair_failed",
                    project_id=project_id,
                    error=str(exc)[:200],
                )

        # 4) Semantic contrast fallback for negative cases.
        if neg_budget > 0 and len(neg_items) < min(1, neg_budget):
            try:
                from app.queries import discover_search
                from app.postgres_block import coded_fragments_for_code

                results_a = discover_search(
                    clients,
                    settings,
                    positive_texts=[code_a],
                    negative_texts=[code_b],
                    top_k=max(neg_per * 2, 6),
                    project=project_id,
                )
                results_b = discover_search(
                    clients,
                    settings,
                    positive_texts=[code_b],
                    negative_texts=[code_a],
                    top_k=max(neg_per * 2, 6),
                    project=project_id,
                )
                combined = (results_a or []) + (results_b or [])
                cand_ids = [str(r.get("fragmento_id")) for r in combined if r and r.get("fragmento_id")]
                present_a = coded_fragments_for_code(clients.postgres, code_a, cand_ids, project_id)
                present_b = coded_fragments_for_code(clients.postgres, code_b, cand_ids, project_id)
                for r in combined:
                    if len(neg_items) >= neg_budget:
                        break
                    fid = str(r.get("fragmento_id") or "")
                    if not fid or fid in used_negative or fid in used_positive:
                        continue
                    # Prefer true "contrast": one code present, the other absent (when we have coding evidence).
                    pa = bool(present_a.get(fid))
                    pb = bool(present_b.get(fid))
                    if pa and pb:
                        continue
                    if not (pa or pb):
                        continue
                    item = {
                        "fragmento_id": fid,
                        "archivo": r.get("archivo"),
                        "par_idx": r.get("par_idx"),
                        "speaker": r.get("speaker"),
                        "fragmento": _truncate(str(r.get("fragmento") or ""), excerpt_chars),
                        "method": "semantic_contrast",
                        "score": _safe_float(r.get("score")),
                        "present_source": pa,
                        "present_target": pb,
                        "discovery_type": r.get("discovery_type"),
                    }
                    neg_items.append(item)
                    used_negative.add(fid)
                    coverage["semantic_contrast"] += 1
            except Exception as exc:  # noqa: BLE001
                _logger.debug(
                    "axial_evidence.semantic_contrast_failed",
                    project_id=project_id,
                    error=str(exc)[:200],
                )

        if pos_budget > 0 and not pos_items:
            notes["positive_missing"] = True
        if neg_budget > 0 and not neg_items:
            notes["negative_missing"] = True

        for method, count in coverage.items():
            method_counter[method] += count

        suggestions_out.append(
            {
                "id": idx,
                "source": code_a,
                "target": code_b,
                "score": s.get("score", 0.0),
                "quota": {"positive": pos_budget, "negative": neg_budget},
                "positive": pos_items,
                "negative": neg_items,
                "coverage": dict(coverage),
                "notes": notes or None,
            }
        )

    totals = {
        "positive": len(used_positive),
        "negative": len(used_negative),
        "by_method": dict(method_counter),
    }

    _logger.info(
        "axial_evidence.pack_built",
        project_id=project_id,
        suggestions=len(suggestions_out),
        positive=totals["positive"],
        negative=totals["negative"],
    )

    return {
        "schema_version": 1,
        "generated_at": now,
        "limits": {
            "positive_total": int(pos_total),
            "negative_total": int(neg_total),
            "positive_distribution": pos_quotas,
            "negative_distribution": neg_quotas,
            "positive_per_suggestion_max": int(max(pos_quotas) if pos_quotas else 0),
            "negative_per_suggestion_max": int(max(neg_quotas) if neg_quotas else 0),
            "excerpt_chars": int(excerpt_chars),
        },
        "suggestions": suggestions_out,
        "totals": totals,
    }
