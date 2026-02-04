"""
Triage helpers for daily logs reporter.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class TriageResult:
    severity: str
    route: str
    hypothesis: str
    actions: List[str]


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def compute_severity(route: str, p95_ms: float, slow_rate: float, error_rate: float) -> str:
    if "/validate" in route:
        if error_rate > 0.05 or p95_ms > 15000:
            return "Sev1"
        if slow_rate > 0.30 or p95_ms > 5000:
            return "Sev2"
        return "Sev3"
    if error_rate > 0.10 or p95_ms > 20000:
        return "Sev2"
    if slow_rate > 0.40 or p95_ms > 8000:
        return "Sev3"
    return "Sev4"


def build_hypothesis(route: str, p95_ms: float, slow_rate: float, error_rate: float) -> str:
    notes = []
    if error_rate > 0.05:
        notes.append(f"error_rate alto ({error_rate * 100:.1f}%)")
    if slow_rate > 0.30:
        notes.append(f"slow_rate alto ({slow_rate * 100:.1f}%)")
    if p95_ms > 10000:
        notes.append(f"p95 muy alto ({p95_ms:.0f}ms)")
    if "/validate" in route:
        notes.append("endpoint critico /validate")
    return " | ".join(notes) if notes else "sin anomalias relevantes"


def build_actions(route: str, severity: str) -> List[str]:
    actions = []
    if severity in {"Sev1", "Sev2"}:
        actions.append("Abrir Workbook Logs MVP (TimeRange 15m)")
        actions.append("Revisar top request_id y build_version")
    if "/validate" in route:
        actions.append("Revisar segmentos dominantes (db/neo4j/qdrant/llm)")
    actions.append("Comparar con build_version anterior si aplica")
    return actions


def triage_from_top(top_rows: List[Dict[str, object]]) -> List[TriageResult]:
    results: List[TriageResult] = []
    for row in top_rows:
        route = str(row.get("route", ""))
        p95 = _to_float(row.get("p95"))
        slow_rate = _to_float(row.get("slow_rate")) / 100.0
        error_rate = _to_float(row.get("error_rate")) / 100.0
        severity = compute_severity(route, p95, slow_rate, error_rate)
        if severity in {"Sev1", "Sev2", "Sev3"}:
            results.append(
                TriageResult(
                    severity=severity,
                    route=route,
                    hypothesis=build_hypothesis(route, p95, slow_rate, error_rate),
                    actions=build_actions(route, severity),
                )
            )
    return results
