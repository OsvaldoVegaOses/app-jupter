"""SeedLoopAgent: formaliza el "bucle manual" (semilla→sugerencias→código→memo→candidatos).

Este script está pensado como herramienta para el desarrollo del Agente Autónomo (docs/06-agente-autonomo)
replicando la exploración intencional del investigador, pero agregando:
- Métricas de calidad por iteración
- Política reproducible para elegir la siguiente semilla
- Persistencia opcional: memo + candidatos

Requisitos:
- Backend corriendo (default http://localhost:8000)
- API key en env: NEO4J_API_KEY

Ejemplo:
  python scripts/seed_loop_agent.py --project jd-009 --seed 482148ec-... \
    --archivo "Entrevista_...docx" --steps 6 --top-k 10 --suggest-code --save-memo --submit-candidates

"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import httpx


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    if not a or not b:
        return 0.0
    sa = set(a)
    sb = set(b)
    inter = len(sa & sb)
    union = len(sa | sb)
    return float(inter / union) if union else 0.0


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


@dataclass
class LoopFilters:
    archivo: Optional[str] = None
    area_tematica: Optional[str] = None
    actor_principal: Optional[str] = None
    requiere_protocolo_lluvia: Optional[bool] = None


@dataclass
class Suggestion:
    fragmento_id: str
    score: float
    archivo: Optional[str]
    area_tematica: Optional[str]
    actor_principal: Optional[str]
    fragmento: Optional[str]


@dataclass
class IterationMetrics:
    step: int
    seed_fragment_id: str
    requested: int
    returned: int
    elapsed_ms: float
    completeness: float
    novelty: float
    diversity_norm: float
    median_score: float
    avg_score: float
    overlap_prev: float
    quality_score: float


@dataclass
class IterationResult:
    metrics: IterationMetrics
    suggestions: List[Suggestion]
    chosen_next_seed: Optional[str]
    suggested_code: Optional[str] = None
    suggested_code_confidence: Optional[str] = None
    memo_path: Optional[str] = None
    candidates_submitted: Optional[int] = None


@dataclass
class RunReport:
    project: str
    started_at: str
    base_url: str
    filters: LoopFilters
    steps: int
    top_k: int
    strategy: str
    initial_seed: str
    iterations: List[IterationResult]


class SeedLoopAgent:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-API-Key": api_key}
        self.client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self.client.close()

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.client.post(
            f"{self.base_url}{path}",
            json=payload,
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.client.get(
            f"{self.base_url}{path}",
            params=params,
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    def coding_fragments(self, *, project: str, archivo: str, limit: int) -> List[Dict[str, Any]]:
        data = self._get(
            "/api/coding/fragments",
            params={
                "project": project,
                "archivo": archivo,
                "limit": max(1, int(limit)),
            },
        )
        return data.get("fragments", []) or []

    def list_interviews(
        self,
        *,
        project: str,
        limit: int,
        order: str = "ingest-desc",
        include_analyzed: bool = False,
        focus_codes: Optional[str] = None,
        recent_window: int = 3,
        saturation_new_codes_threshold: int = 2,
    ) -> List[Dict[str, Any]]:
        data = self._get(
            "/api/interviews",
            params={
                "project": project,
                "limit": max(1, int(limit)),
                "order": order,
                "include_analyzed": bool(include_analyzed),
                "focus_codes": focus_codes,
                "recent_window": max(1, int(recent_window)),
                "saturation_new_codes_threshold": max(0, int(saturation_new_codes_threshold)),
            },
        )
        return data.get("interviews", []) or []

    def coding_suggest(
        self,
        *,
        project: str,
        seed_fragment_id: str,
        top_k: int,
        filters: LoopFilters,
        include_coded: bool,
        persist: bool,
        llm_model: Optional[str],
    ) -> Tuple[Dict[str, Any], float]:
        payload: Dict[str, Any] = {
            "project": project,
            "fragment_id": seed_fragment_id,
            "top_k": top_k,
            "include_coded": include_coded,
            "persist": persist,
        }
        if filters.archivo:
            payload["archivo"] = filters.archivo
        if filters.area_tematica:
            payload["area_tematica"] = filters.area_tematica
        if filters.actor_principal:
            payload["actor_principal"] = filters.actor_principal
        if filters.requiere_protocolo_lluvia is not None:
            payload["requiere_protocolo_lluvia"] = filters.requiere_protocolo_lluvia
        if llm_model:
            payload["llm_model"] = llm_model

        start = time.perf_counter()
        data = self._post("/api/coding/suggest", payload)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return data, elapsed_ms

    def coding_suggest_code(
        self,
        *,
        project: str,
        fragments: List[Dict[str, Any]],
        llm_model: Optional[str],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"project": project, "fragments": fragments}
        if llm_model:
            payload["llm_model"] = llm_model
        return self._post("/api/coding/suggest-code", payload)

    def discovery_save_memo(
        self,
        *,
        project: str,
        positive_texts: List[str],
        fragments: List[Dict[str, Any]],
        memo_title: str,
        ai_synthesis: Optional[str],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "project": project,
            "positive_texts": positive_texts,
            "negative_texts": [],
            "target_text": None,
            "fragments": fragments,
            "memo_title": memo_title,
            "ai_synthesis": ai_synthesis,
        }
        return self._post("/api/discovery/save_memo", payload)

    def submit_candidates_batch(
        self,
        *,
        project: str,
        codigo: str,
        memo: Optional[str],
        fragments: List[Suggestion],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "project": project,
            "codigo": codigo,
            "memo": memo,
            "fragments": [
                {
                    "fragmento_id": s.fragmento_id,
                    "archivo": s.archivo or "",
                    "cita": (s.fragmento or "")[:500],
                    "score": float(s.score or 0.0),
                }
                for s in fragments
            ],
        }
        return self._post("/api/codes/candidates/batch", payload)


def _parse_suggestions(raw: Dict[str, Any]) -> List[Suggestion]:
    out: List[Suggestion] = []
    for s in raw.get("suggestions", []) or []:
        out.append(
            Suggestion(
                fragmento_id=str(s.get("fragmento_id") or ""),
                score=float(s.get("score") or 0.0),
                archivo=s.get("archivo"),
                area_tematica=s.get("area_tematica"),
                actor_principal=s.get("actor_principal"),
                fragmento=s.get("fragmento"),
            )
        )
    return [s for s in out if s.fragmento_id]


def _diversity_norm(suggestions: List[Suggestion]) -> float:
    if not suggestions:
        return 0.0
    archivos = {s.archivo for s in suggestions if s.archivo}
    areas = {s.area_tematica for s in suggestions if s.area_tematica}
    actores = {s.actor_principal for s in suggestions if s.actor_principal}
    # Normalización simple: máximo 3 dimensiones
    raw = 0
    raw += 1 if len(archivos) >= 2 else 0
    raw += 1 if len(areas) >= 2 else 0
    raw += 1 if len(actores) >= 2 else 0
    return raw / 3.0


def _quality_score(
    *,
    completeness: float,
    novelty: float,
    diversity_norm: float,
    median_score: float,
) -> float:
    # Pesos simples (documentados en docs/06-agente-autonomo/algoritmo_bucle_manual_semilla.md)
    q = 0.35 * completeness + 0.25 * novelty + 0.20 * diversity_norm + 0.20 * _clamp01(median_score)
    return round(q, 4)


def _select_next_seed(
    *,
    suggestions: List[Suggestion],
    used_seeds: Set[str],
    seen_fragments: Set[str],
    strategy: str,
) -> Optional[str]:
    # Filtrar candidatos no usados
    candidates = [s for s in suggestions if s.fragmento_id not in used_seeds]
    if not candidates:
        return None

    # Estrategia: diverse-first (por defecto)
    if strategy == "diverse-first":
        # Preferir candidato no visto que aporte "nuevo contexto" (archivo/actor/area)
        # Heurística: primero candidatos no vistos, luego por score.
        novel = [s for s in candidates if s.fragmento_id not in seen_fragments]
        pool = novel or candidates
        pool_sorted = sorted(pool, key=lambda s: s.score, reverse=True)
        return pool_sorted[0].fragmento_id

    # Estrategia: greedy
    if strategy == "greedy":
        best = max(candidates, key=lambda s: s.score)
        return best.fragmento_id

    # Fallback
    best = max(candidates, key=lambda s: s.score)
    return best.fragmento_id


def _suggestions_for_llm(suggestions: List[Suggestion], limit: int = 10) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in suggestions[:limit]:
        out.append(
            {
                "fragmento_id": s.fragmento_id,
                "archivo": s.archivo,
                "fragmento": s.fragmento,
                "score": float(s.score or 0.0),
                "area_tematica": s.area_tematica,
                "actor_principal": s.actor_principal,
            }
        )
    return out


def run_seed_loop(
    *,
    project: str,
    seed_fragment_id: str,
    filters: LoopFilters,
    steps: int,
    top_k: int,
    base_url: str,
    api_key: str,
    include_coded: bool,
    persist_comparisons: bool,
    llm_model: Optional[str],
    strategy: str,
    suggest_code: bool,
    save_memo: bool,
    submit_candidates: bool,
) -> RunReport:
    agent = SeedLoopAgent(base_url=base_url, api_key=api_key)
    try:
        used_seeds: Set[str] = set()
        seen_fragments: Set[str] = set()
        prev_ids: List[str] = []

        iterations: List[IterationResult] = []
        current_seed = seed_fragment_id

        for step in range(1, steps + 1):
            used_seeds.add(current_seed)

            raw, elapsed_ms = agent.coding_suggest(
                project=project,
                seed_fragment_id=current_seed,
                top_k=top_k,
                filters=filters,
                include_coded=include_coded,
                persist=persist_comparisons,
                llm_model=llm_model,
            )
            suggestions = _parse_suggestions(raw)
            ids = [s.fragmento_id for s in suggestions]

            returned = len(suggestions)
            completeness = (returned / top_k) if top_k else 0.0

            new_count = len([s for s in suggestions if s.fragmento_id not in seen_fragments])
            novelty = (new_count / returned) if returned else 0.0

            scores = [float(s.score or 0.0) for s in suggestions]
            median_score = statistics.median(scores) if scores else 0.0
            avg_score = statistics.mean(scores) if scores else 0.0

            diversity_norm = _diversity_norm(suggestions)
            overlap_prev = _jaccard(prev_ids, ids)

            q = _quality_score(
                completeness=completeness,
                novelty=novelty,
                diversity_norm=diversity_norm,
                median_score=median_score,
            )

            metrics = IterationMetrics(
                step=step,
                seed_fragment_id=current_seed,
                requested=top_k,
                returned=returned,
                elapsed_ms=round(elapsed_ms, 2),
                completeness=round(completeness, 4),
                novelty=round(novelty, 4),
                diversity_norm=round(diversity_norm, 4),
                median_score=round(median_score, 6),
                avg_score=round(avg_score, 6),
                overlap_prev=round(overlap_prev, 4),
                quality_score=q,
            )

            # Marcar vistos
            for s in suggestions:
                seen_fragments.add(s.fragmento_id)

            next_seed = _select_next_seed(
                suggestions=suggestions,
                used_seeds=used_seeds,
                seen_fragments=seen_fragments,
                strategy=strategy,
            )

            iter_result = IterationResult(
                metrics=metrics,
                suggestions=suggestions,
                chosen_next_seed=next_seed,
            )

            # Acciones opcionales: LLM + memo + candidatos
            if suggest_code and suggestions:
                llm_payload = _suggestions_for_llm(suggestions, limit=min(10, len(suggestions)))
                llm_out = agent.coding_suggest_code(project=project, fragments=llm_payload, llm_model=llm_model)
                iter_result.suggested_code = llm_out.get("suggested_code")
                iter_result.suggested_code_confidence = llm_out.get("confidence")

                if save_memo and iter_result.suggested_code:
                    memo_title = f"Memo IA - {iter_result.suggested_code}"
                    memo_out = agent.discovery_save_memo(
                        project=project,
                        positive_texts=[iter_result.suggested_code],
                        fragments=llm_payload,
                        memo_title=memo_title,
                        ai_synthesis=llm_out.get("memo"),
                    )
                    iter_result.memo_path = memo_out.get("path")

                if submit_candidates and iter_result.suggested_code:
                    resp = agent.submit_candidates_batch(
                        project=project,
                        codigo=iter_result.suggested_code,
                        memo=llm_out.get("memo"),
                        fragments=suggestions[: min(10, len(suggestions))],
                    )
                    iter_result.candidates_submitted = int(resp.get("submitted") or 0)

            iterations.append(iter_result)

            prev_ids = ids
            if not next_seed:
                break
            current_seed = next_seed

        return RunReport(
            project=project,
            started_at=datetime.utcnow().isoformat() + "Z",
            base_url=base_url,
            filters=filters,
            steps=steps,
            top_k=top_k,
            strategy=strategy,
            initial_seed=seed_fragment_id,
            iterations=iterations,
        )

    finally:
        agent.close()


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    if hasattr(obj, "_asdict"):
        return obj._asdict()
    return str(obj)


def run_segment_sweep(
    *,
    project: str,
    archivo: str,
    filters: LoopFilters,
    max_fragments: int,
    top_k: int,
    base_url: str,
    api_key: str,
    include_coded: bool,
    persist_comparisons: bool,
    llm_model: Optional[str],
    strategy: str,
    suggest_code: bool,
    save_memo: bool,
    submit_candidates: bool,
    min_quality_for_actions: float,
) -> RunReport:
    """Recorre una entrevista completa (por `par_idx`) y ejecuta el bucle por cada fragmento.

    Intención: replicar el trabajo manual del investigador (semilla = segmento actual),
    pero con trazabilidad + métricas.
    """
    agent = SeedLoopAgent(base_url=base_url, api_key=api_key)
    try:
        rows = agent.coding_fragments(project=project, archivo=archivo, limit=max(1, max_fragments))
        seeds: List[str] = [str(r.get("fragmento_id") or "") for r in rows]
        seeds = [s for s in seeds if s]

        used_seeds: Set[str] = set()
        seen_fragments: Set[str] = set()
        prev_ids: List[str] = []

        iterations: List[IterationResult] = []
        initial_seed = seeds[0] if seeds else ""

        for step, seed in enumerate(seeds, start=1):
            used_seeds.add(seed)

            raw, elapsed_ms = agent.coding_suggest(
                project=project,
                seed_fragment_id=seed,
                top_k=top_k,
                filters=filters,
                include_coded=include_coded,
                persist=persist_comparisons,
                llm_model=llm_model,
            )
            suggestions = _parse_suggestions(raw)
            ids = [s.fragmento_id for s in suggestions]

            returned = len(suggestions)
            completeness = (returned / top_k) if top_k else 0.0

            new_count = len([s for s in suggestions if s.fragmento_id not in seen_fragments])
            novelty = (new_count / returned) if returned else 0.0

            scores = [float(s.score or 0.0) for s in suggestions]
            median_score = statistics.median(scores) if scores else 0.0
            avg_score = statistics.mean(scores) if scores else 0.0

            diversity_norm = _diversity_norm(suggestions)
            overlap_prev = _jaccard(prev_ids, ids)

            q = _quality_score(
                completeness=completeness,
                novelty=novelty,
                diversity_norm=diversity_norm,
                median_score=median_score,
            )

            metrics = IterationMetrics(
                step=step,
                seed_fragment_id=seed,
                requested=top_k,
                returned=returned,
                elapsed_ms=round(elapsed_ms, 2),
                completeness=round(completeness, 4),
                novelty=round(novelty, 4),
                diversity_norm=round(diversity_norm, 4),
                median_score=round(median_score, 6),
                avg_score=round(avg_score, 6),
                overlap_prev=round(overlap_prev, 4),
                quality_score=q,
            )

            # Marcar vistos
            for s in suggestions:
                seen_fragments.add(s.fragmento_id)

            # En sweep el siguiente seed es el siguiente segmento (no depende de sugerencias)
            next_seed = seeds[step] if step < len(seeds) else None

            iter_result = IterationResult(
                metrics=metrics,
                suggestions=suggestions,
                chosen_next_seed=next_seed,
            )

            # Acciones opcionales, gatilladas por umbral de calidad
            if suggest_code and suggestions and q >= min_quality_for_actions:
                llm_payload = _suggestions_for_llm(suggestions, limit=min(10, len(suggestions)))
                llm_out = agent.coding_suggest_code(project=project, fragments=llm_payload, llm_model=llm_model)
                iter_result.suggested_code = llm_out.get("suggested_code")
                iter_result.suggested_code_confidence = llm_out.get("confidence")

                if save_memo and iter_result.suggested_code:
                    memo_title = f"Sweep IA - {iter_result.suggested_code}"
                    memo_out = agent.discovery_save_memo(
                        project=project,
                        positive_texts=[iter_result.suggested_code],
                        fragments=llm_payload,
                        memo_title=memo_title,
                        ai_synthesis=llm_out.get("memo"),
                    )
                    iter_result.memo_path = memo_out.get("path")

                if submit_candidates and iter_result.suggested_code:
                    resp = agent.submit_candidates_batch(
                        project=project,
                        codigo=iter_result.suggested_code,
                        memo=llm_out.get("memo"),
                        fragments=suggestions[: min(10, len(suggestions))],
                    )
                    iter_result.candidates_submitted = int(resp.get("submitted") or 0)

            iterations.append(iter_result)
            prev_ids = ids

        return RunReport(
            project=project,
            started_at=datetime.utcnow().isoformat() + "Z",
            base_url=base_url,
            filters=filters,
            steps=len(seeds),
            top_k=top_k,
            strategy=strategy,
            initial_seed=initial_seed,
            iterations=iterations,
        )
    finally:
        agent.close()


def run_project_sweep(
    *,
    project: str,
    filters: LoopFilters,
    interviews_limit: int,
    interview_order: str,
    include_analyzed_interviews: bool,
    focus_codes: Optional[str],
    recent_window: int,
    saturation_new_codes_threshold: int,
    max_fragments: int,
    top_k: int,
    base_url: str,
    api_key: str,
    include_coded: bool,
    persist_comparisons: bool,
    llm_model: Optional[str],
    strategy: str,
    suggest_code: bool,
    save_memo: bool,
    submit_candidates: bool,
    min_quality_for_actions: float,
) -> RunReport:
    """Recorre entrevistas del proyecto en orden y aplica segment-sweep por cada una."""
    agent = SeedLoopAgent(base_url=base_url, api_key=api_key)
    try:
        interviews = agent.list_interviews(
            project=project,
            limit=max(1, interviews_limit),
            order=interview_order,
            include_analyzed=bool(include_analyzed_interviews),
            focus_codes=focus_codes,
            recent_window=max(1, int(recent_window)),
            saturation_new_codes_threshold=max(0, int(saturation_new_codes_threshold)),
        )
        archivos: List[str] = [str(i.get("archivo") or "") for i in interviews]
        archivos = [a for a in archivos if a]

        all_iterations: List[IterationResult] = []
        initial_seed = ""
        step_offset = 0

        for idx, archivo in enumerate(archivos, start=1):
            # Si el usuario fijó filtro por archivo, respetarlo (solo ese archivo)
            if filters.archivo and filters.archivo != archivo:
                continue

            sweep_filters = LoopFilters(
                archivo=archivo,
                area_tematica=filters.area_tematica,
                actor_principal=filters.actor_principal,
                requiere_protocolo_lluvia=filters.requiere_protocolo_lluvia,
            )

            report = run_segment_sweep(
                project=project,
                archivo=archivo,
                filters=sweep_filters,
                max_fragments=max_fragments,
                top_k=top_k,
                base_url=base_url,
                api_key=api_key,
                include_coded=include_coded,
                persist_comparisons=persist_comparisons,
                llm_model=llm_model,
                strategy=strategy,
                suggest_code=suggest_code,
                save_memo=save_memo,
                submit_candidates=submit_candidates,
                min_quality_for_actions=min_quality_for_actions,
            )

            if not initial_seed and report.initial_seed:
                initial_seed = report.initial_seed

            # Reindexar steps para que sean monotonicos a través del proyecto
            for it in report.iterations:
                it.metrics.step = it.metrics.step + step_offset
                all_iterations.append(it)

            step_offset += len(report.iterations)

        return RunReport(
            project=project,
            started_at=datetime.utcnow().isoformat() + "Z",
            base_url=base_url,
            filters=filters,
            steps=len(all_iterations),
            top_k=top_k,
            strategy=strategy,
            initial_seed=initial_seed,
            iterations=all_iterations,
        )
    finally:
        agent.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="SeedLoopAgent (semilla→sugerencias→código→memo→candidatos)")
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--mode",
        default="seed-loop",
        choices=["seed-loop", "segment-sweep", "project-sweep"],
        help="Modo de ejecución",
    )
    parser.add_argument("--seed", required=False, help="fragmento_id semilla (requerido en seed-loop)")
    parser.add_argument("--archivo", default=None, help="Filtro y/o entrevista a recorrer (requerido en segment-sweep)")
    parser.add_argument("--area", default=None)
    parser.add_argument("--actor", default=None)
    parser.add_argument("--lluvia", default=None, choices=["true", "false"])  # requiere_protocolo_lluvia
    parser.add_argument("--steps", type=int, default=6)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--strategy", default="diverse-first", choices=["diverse-first", "greedy"])
    parser.add_argument("--include-coded", action="store_true")
    parser.add_argument("--persist", action="store_true", help="persistir comparison_id (si backend lo soporta)")
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--suggest-code", action="store_true")
    parser.add_argument("--save-memo", action="store_true")
    parser.add_argument("--submit-candidates", action="store_true")
    parser.add_argument(
        "--min-quality",
        type=float,
        default=0.0,
        help="Umbral mínimo de quality_score para ejecutar acciones LLM/memo/candidatos (solo aplica si flags están activos)",
    )
    parser.add_argument(
        "--max-fragments",
        type=int,
        default=5000,
        help="Máximo de fragmentos a recorrer en segment-sweep (usa /api/coding/fragments?limit=...)",
    )
    parser.add_argument(
        "--interviews-limit",
        type=int,
        default=500,
        help="Máximo de entrevistas a recorrer en project-sweep (usa /api/interviews?limit=...)",
    )
    parser.add_argument(
        "--interview-order",
        default="ingest-desc",
        choices=[
            "ingest-desc",
            "ingest-asc",
            "alpha",
            "fragments-desc",
            "fragments-asc",
            "max-variation",
            "theoretical-sampling",
        ],
        help="Orden epistemológico de entrevistas para project-sweep (proxy de ingesta y/o máxima variación)",
    )
    parser.add_argument(
        "--include-analyzed-interviews",
        action="store_true",
        help="Solo para --interview-order theoretical-sampling: incluir entrevistas ya analizadas al final del listado",
    )
    parser.add_argument(
        "--focus-codes",
        default=None,
        help="Solo para --interview-order theoretical-sampling: CSV de códigos foco (ej: 'Dificultad de pago,Acceso a subsidio')",
    )
    parser.add_argument(
        "--recent-window",
        type=int,
        default=3,
        help="Solo para --interview-order theoretical-sampling: ventana de últimos N reports para saturación",
    )
    parser.add_argument(
        "--saturation-threshold",
        type=int,
        default=2,
        help="Solo para --interview-order theoretical-sampling: umbral de suma de codigos_nuevos en la ventana",
    )
    parser.add_argument("--out", default=None, help="ruta de salida JSON (default: reports/seed_loop_*.json)")

    args = parser.parse_args()

    # Cargar .env si existe (sin sobrescribir env ya presente)
    _load_dotenv(Path(".env"))

    api_key = os.environ.get("NEO4J_API_KEY")
    if not api_key:
        raise SystemExit("NEO4J_API_KEY no está configurada (requerida para X-API-Key)")

    lluvia: Optional[bool] = None
    if args.lluvia == "true":
        lluvia = True
    elif args.lluvia == "false":
        lluvia = False

    filters = LoopFilters(
        archivo=args.archivo,
        area_tematica=args.area,
        actor_principal=args.actor,
        requiere_protocolo_lluvia=lluvia,
    )

    if args.mode == "seed-loop":
        if not args.seed:
            raise SystemExit("--seed es requerido cuando --mode=seed-loop")
        report = run_seed_loop(
            project=args.project,
            seed_fragment_id=args.seed,
            filters=filters,
            steps=max(1, args.steps),
            top_k=max(1, args.top_k),
            base_url=args.base_url,
            api_key=api_key,
            include_coded=bool(args.include_coded),
            persist_comparisons=bool(args.persist),
            llm_model=args.llm_model,
            strategy=args.strategy,
            suggest_code=bool(args.suggest_code),
            save_memo=bool(args.save_memo),
            submit_candidates=bool(args.submit_candidates),
        )
    elif args.mode == "segment-sweep":
        if not args.archivo:
            raise SystemExit("--archivo es requerido cuando --mode=segment-sweep")
        report = run_segment_sweep(
            project=args.project,
            archivo=args.archivo,
            filters=filters,
            max_fragments=max(1, int(args.max_fragments)),
            top_k=max(1, args.top_k),
            base_url=args.base_url,
            api_key=api_key,
            include_coded=bool(args.include_coded),
            persist_comparisons=bool(args.persist),
            llm_model=args.llm_model,
            strategy=args.strategy,
            suggest_code=bool(args.suggest_code),
            save_memo=bool(args.save_memo),
            submit_candidates=bool(args.submit_candidates),
            min_quality_for_actions=float(args.min_quality),
        )
    else:
        # project-sweep
        report = run_project_sweep(
            project=args.project,
            filters=filters,
            interviews_limit=max(1, int(args.interviews_limit)),
            interview_order=str(args.interview_order),
            include_analyzed_interviews=bool(args.include_analyzed_interviews),
            focus_codes=(str(args.focus_codes) if args.focus_codes else None),
            recent_window=max(1, int(args.recent_window)),
            saturation_new_codes_threshold=max(0, int(args.saturation_threshold)),
            max_fragments=max(1, int(args.max_fragments)),
            top_k=max(1, args.top_k),
            base_url=args.base_url,
            api_key=api_key,
            include_coded=bool(args.include_coded),
            persist_comparisons=bool(args.persist),
            llm_model=args.llm_model,
            strategy=args.strategy,
            suggest_code=bool(args.suggest_code),
            save_memo=bool(args.save_memo),
            submit_candidates=bool(args.submit_candidates),
            min_quality_for_actions=float(args.min_quality),
        )

    default_name = "seed_loop" if args.mode == "seed-loop" else "segment_sweep" if args.mode == "segment-sweep" else "project_sweep"
    out_path = Path(args.out) if args.out else Path("reports") / f"{default_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        **asdict(report),
        "iterations": [
            {
                "metrics": asdict(it.metrics),
                "chosen_next_seed": it.chosen_next_seed,
                "suggested_code": it.suggested_code,
                "suggested_code_confidence": it.suggested_code_confidence,
                "memo_path": it.memo_path,
                "candidates_submitted": it.candidates_submitted,
                "suggestions": [asdict(s) for s in it.suggestions],
            }
            for it in report.iterations
        ],
    }

    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    print(f"OK: wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
