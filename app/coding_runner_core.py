"""
Core utilities for coding runner workflows (shared by router and agent).

These helpers are domain-level (no HTTP/routers) to keep orchestration
reusable in background tasks and API handlers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class RunnerResumeState:
    archivos: List[str]
    visited_seeds_global: Set[str]
    visited_seed_ids: List[str]
    union_by_id_global: Dict[str, Dict[str, Any]]
    iterations: List[Dict[str, Any]]
    memos: List[Dict[str, Any]]
    candidates_total: int
    memos_saved: int
    llm_calls: int
    llm_failures: int
    qdrant_failures: int
    qdrant_retries: int
    last_suggested_code: Optional[str]
    saturated: bool
    cursor: Dict[str, Any]


def normalize_resume_state(resume_state: Optional[Dict[str, Any]]) -> RunnerResumeState:
    state = resume_state or {}
    archivos = [str(a) for a in state.get("archivos") or [] if a]
    visited_seeds_global = {str(x) for x in state.get("visited_seeds_global") or [] if x}
    visited_seed_ids = [str(x) for x in state.get("visited_seed_ids") or [] if x]
    union_by_id_global: Dict[str, Dict[str, Any]] = {}
    for s in state.get("union_by_id_global") or []:
        try:
            fid = str((s or {}).get("fragmento_id") or "")
            if fid:
                union_by_id_global[fid] = dict(s)
        except Exception:
            continue

    iterations = list(state.get("iterations") or [])
    memos = list(state.get("memos") or [])
    candidates_total = int(state.get("candidates_total") or 0)
    memos_saved = int(state.get("memos_saved") or 0)
    llm_calls = int(state.get("llm_calls") or 0)
    llm_failures = int(state.get("llm_failures") or 0)
    qdrant_failures = int(state.get("qdrant_failures") or 0)
    qdrant_retries = int(state.get("qdrant_retries") or 0)
    last_suggested_code = state.get("last_suggested_code")
    saturated = bool(state.get("saturated") or False)
    cursor = dict(state.get("cursor") or {})

    return RunnerResumeState(
        archivos=archivos,
        visited_seeds_global=visited_seeds_global,
        visited_seed_ids=visited_seed_ids,
        union_by_id_global=union_by_id_global,
        iterations=iterations,
        memos=memos,
        candidates_total=candidates_total,
        memos_saved=memos_saved,
        llm_calls=llm_calls,
        llm_failures=llm_failures,
        qdrant_failures=qdrant_failures,
        qdrant_retries=qdrant_retries,
        last_suggested_code=last_suggested_code,
        saturated=saturated,
        cursor=cursor,
    )


def constant_comparison_sample(
    fragments: List[Dict[str, Any]],
    *,
    max_total: int = 60,
    max_per_archivo: int = 3,
) -> List[Dict[str, Any]]:
    """Select a diversified, deduplicated sample for constant comparison.

    - Deduplicates by fragmento_id
    - Sorts by score desc
    - Caps per archivo to encourage coverage
    - Truncates to max_total
    """
    if not fragments:
        return []

    seen_ids: Set[str] = set()
    per_archivo: Dict[str, int] = {}

    def _score(f: Dict[str, Any]) -> float:
        try:
            return float(f.get("score") or 0.0)
        except Exception:
            return 0.0

    sorted_frags = sorted(fragments, key=_score, reverse=True)
    selected: List[Dict[str, Any]] = []
    for frag in sorted_frags:
        fid = str(frag.get("fragmento_id") or frag.get("id") or "")
        if not fid or fid in seen_ids:
            continue
        archivo = str(frag.get("archivo") or "?")
        count = per_archivo.get(archivo, 0)
        if count >= max_per_archivo:
            continue
        selected.append(frag)
        seen_ids.add(fid)
        per_archivo[archivo] = count + 1
        if len(selected) >= max_total:
            break
    return selected


def attach_evidence_to_codes(
    *,
    codes: List[str],
    fragments: List[Dict[str, Any]],
    max_fragments_per_code: int = 3,
) -> List[Dict[str, Any]]:
    """Return a list of {code, fragments} with limited evidence per code.

    Keeps ordering of codes; fragments are taken in order.
    """
    if not codes or not fragments:
        return []

    clean_codes = [c.strip() for c in codes if isinstance(c, str) and c.strip()]
    if not clean_codes:
        return []

    result: List[Dict[str, Any]] = []
    for code in clean_codes:
        bucket = []
        for frag in fragments:
            if len(bucket) >= max_fragments_per_code:
                break
            fid = frag.get("fragmento_id") or frag.get("id")
            if not fid:
                continue
            bucket.append(frag)
        result.append({"code": code, "fragments": bucket})
    return result
