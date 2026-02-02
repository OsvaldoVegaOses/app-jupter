import pytest
from app.nucleus import build_canonical_storyline_and_audit


def test_build_canonical_from_grounded():
    report = {
        "storyline_graphrag": {
            "is_grounded": True,
            "answer": "**Hallazgos**\n- Observación 1",
            "evidence": [{"fragmento_id": "f1", "score": 0.7}],
            "inputs": {"retrieval": {"threshold": 0.5}, "scope_node_ids": [1, 2]},
            "nodes": [{"id": 10, "label": "Nodo A", "role": "bridge", "score": 0.8}],
            "run_id": "r1",
            "computed_at": "2026-01-30T00:00:00Z",
        },
        "summary_metrics": {"text_summary": "Resumen métrico", "pagerank_top": ["A", "B"]},
        "centrality": {"top": [{"nombre": "A"}]},
        "coverage": {"entrevistas_cubiertas": 5},
        "checks": {"centrality": True},
    }

    storyline, audit = build_canonical_storyline_and_audit(report)
    assert storyline["mode"] == "grounded"
    assert storyline["is_grounded"] is True
    assert storyline["answer_md"].startswith("**Hallazgos**")
    assert isinstance(storyline["evidence"], list)
    assert audit["summary_md"] == "Resumen métrico"


def test_build_canonical_from_abstained_and_exploratory():
    report = {
        "graphrag": {"is_grounded": False, "rejection": {"reason": "low"}},
        "storyline_graphrag": {"exploratory_used": True, "answer": "Exploratory text", "nodes": []},
        "summary_metrics": {"text_summary": "Metrics summary"},
    }
    storyline, audit = build_canonical_storyline_and_audit(report)
    assert storyline["mode"] == "exploratory"
    assert storyline["is_grounded"] is False
    assert storyline["answer_md"] == "Exploratory text"
    assert audit["summary_md"] == "Metrics summary"