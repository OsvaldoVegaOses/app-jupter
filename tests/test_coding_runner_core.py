import pytest

from app.coding_runner_core import (
    normalize_resume_state,
    constant_comparison_sample,
    attach_evidence_to_codes,
)


def test_normalize_resume_state_defaults():
    state = normalize_resume_state(None)
    assert state.archivos == []
    assert state.visited_seeds_global == set()
    assert state.candidates_total == 0
    assert state.cursor == {}


def test_normalize_resume_state_populates_fields():
    resume = {
        "archivos": ["a1", None, "a2"],
        "visited_seeds_global": ["x", None],
        "visited_seed_ids": ["x", "y"],
        "union_by_id_global": [{"fragmento_id": "f1", "score": 0.9}],
        "iterations": [{"step": 1}],
        "memos": [{"memo": "m"}],
        "candidates_total": 3,
        "memos_saved": 2,
        "llm_calls": 4,
        "llm_failures": 1,
        "qdrant_failures": 0,
        "qdrant_retries": 1,
        "last_suggested_code": "code",
        "saturated": True,
        "cursor": {"interview_index": 2},
    }
    state = normalize_resume_state(resume)
    assert state.archivos == ["a1", "a2"]
    assert state.visited_seeds_global == {"x"}
    assert state.visited_seed_ids == ["x", "y"]
    assert "f1" in state.union_by_id_global
    assert state.memos_saved == 2
    assert state.llm_calls == 4
    assert state.saturated is True
    assert state.cursor == {"interview_index": 2}


def test_constant_comparison_sample_limits_and_dedup():
    fragments = [
        {"fragmento_id": "f1", "archivo": "a", "score": 0.9},
        {"fragmento_id": "f1", "archivo": "a", "score": 0.8},  # duplicate id
        {"fragmento_id": "f2", "archivo": "a", "score": 0.7},
        {"fragmento_id": "f3", "archivo": "b", "score": 0.6},
        {"fragmento_id": "f4", "archivo": "b", "score": 0.5},
        {"fragmento_id": "f5", "archivo": "b", "score": 0.4},
        {"fragmento_id": "f6", "archivo": "b", "score": 0.3},  # exceeds per-archivo cap
    ]
    selected = constant_comparison_sample(fragments, max_total=10, max_per_archivo=2)
    assert len(selected) == 4  # f1,f2 from a; f3,f4 from b
    ids = {f["fragmento_id"] for f in selected}
    assert ids == {"f1", "f2", "f3", "f4"}


def test_attach_evidence_to_codes_respects_limits():
    codes = ["alpha", "beta"]
    frags = [
        {"fragmento_id": "f1"},
        {"fragmento_id": "f2"},
        {"fragmento_id": "f3"},
    ]
    result = attach_evidence_to_codes(codes=codes, fragments=frags, max_fragments_per_code=2)
    assert len(result) == 2
    assert len(result[0]["fragments"]) == 2
    assert len(result[1]["fragments"]) == 2
