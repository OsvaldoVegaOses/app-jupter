from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import main


@pytest.fixture(autouse=True)
def _stub_project_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "resolve_project", lambda project, allow_create=False: project or "default")
    monkeypatch.setattr(main, "mark_stage", lambda *args, **kwargs: None)


def test_coding_citations_outputs_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    fake_clients = SimpleNamespace(close=lambda: None)
    sample_rows = [
        {
            "fragmento_id": "entrevista/001#p12",
            "archivo": "entrevista1.docx",
            "fuente": "Participante A",
            "memo": "Refuerza la estrategia comunitaria",
            "cita": "La comunidad respondió organizada ante la emergencia.",
        }
    ]

    monkeypatch.setattr(main, "build_context", lambda env: (None, fake_clients))
    monkeypatch.setattr(main, "citations_for_code", lambda _clients, _code, _project=None: sample_rows)

    exit_code = main.main([
        "--project",
        "default",
        "coding",
        "citations",
        "--codigo",
        "Resiliencia comunitaria",
        "--json",
    ])

    assert exit_code == 0
    output = capsys.readouterr().out.strip()
    payload = json.loads(output)
    assert payload["citations"] == sample_rows
