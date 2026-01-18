"""
Detección de problemas de coherencia en fragmentos de texto.

Este módulo identifica problemas de calidad en transcripciones de entrevistas
que pueden afectar la fiabilidad del análisis. Detecta:

Patrones detectados:
    - placeholder_marker: "???" marcadores de contenido faltante
    - inaudible_tag: "[inaudible]" segmentos no transcribibles
    - filler_repetition: "eh", "mmm" muletillas excesivas
    - long_ellipsis: "...." pausas largas mal transcritas
    - uncertain_brackets: "[no se entiende]" contenido dudoso
    - sic_marker: "[sic]" errores intencionales preservados
    - empty_fragment: Fragmentos vacíos

Funciones:
    - analyze_fragment(): Retorna lista de issues detectados
    - summarize_issue_counts(): Conteo agregado de issues

Uso en ingesta:
    Durante la ingesta, cada fragmento se analiza y los issues
    se registran para revisión posterior (ingest.quality.issue).
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, List, Tuple

PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("placeholder_marker", re.compile(r"[?]{3,}")),
    ("inaudible_tag", re.compile(r"\b\[?inaudible\]?\b", re.IGNORECASE)),
    ("filler_repetition", re.compile(r"\b(eh+|mmm+|aj+a|este+)\b", re.IGNORECASE)),
    ("long_ellipsis", re.compile(r"\.{4,}")),
    ("uncertain_brackets", re.compile(r"\[(?:inaudible|desconocido|no se entiende)\]", re.IGNORECASE)),
)


def analyze_fragment(text: str) -> List[str]:
    """Return a list of issue codes detected in the fragment."""
    issues: List[str] = []
    stripped = text.strip()
    if not stripped:
        issues.append("empty_fragment")
        return issues
    lower = stripped.lower()
    if "[sic]" in lower:
        issues.append("sic_marker")
    for code, pattern in PATTERNS:
        if pattern.search(stripped):
            issues.append(code)
    return issues


def summarize_issue_counts(issue_lists: Iterable[List[str]]) -> Counter:
    counter: Counter[str] = Counter()
    for issues in issue_lists:
        counter.update(issues)
    return counter
