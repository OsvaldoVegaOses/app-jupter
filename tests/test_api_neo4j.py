from __future__ import annotations

from typing import Any, Dict

import pytest

from app.settings import (
    AppSettings,
    AzureSettings,
    Neo4jSettings,
    PostgresSettings,
    QdrantSettings,
)
from backend import app as backend_app


@pytest.fixture(autouse=True)
def _mock_project_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    def _resolve(identifier: str | None, *, allow_create: bool = False, pg: Any = None) -> str:
        if not identifier:
            return "default"
        return identifier

    monkeypatch.setattr(backend_app, "resolve_project", _resolve)


def _settings(database: str = "neo4j", api_key: str = "test-key") -> AppSettings:
    return AppSettings(
        azure=AzureSettings(
            endpoint="",
            api_key=None,
            api_version="2024-08-01-preview",
            deployment_embed="embed",
            deployment_chat="chat",
        ),
        qdrant=QdrantSettings(uri="", api_key=None, collection=""),
        neo4j=Neo4jSettings(uri="", username="neo4j", password=None, database=database),
        postgres=PostgresSettings(
            host="localhost",
            port=5432,
            username="postgres",
            password=None,
            database="postgres",
        ),
        embed_dims=None,
        api_key=api_key,
    )


def test_execute_cypher_filters_formats() -> None:
    payload = backend_app.CypherRequest(
        cypher="RETURN 1",
        project="default",
        formats=["graph", "raw"],
    )
    called: Dict[str, Any] = {}

    def fake_runner(cypher: str, params: Dict[str, Any], database: str) -> Dict[str, Any]:
        called.update({"cypher": cypher, "params": params, "database": database})
        return {
            "raw": [{"n": 1}],
            "table": {"columns": ["n"], "rows": [[1]]},
            "graph": {"nodes": [], "relationships": []},
        }

    result, duration_ms = backend_app._execute_cypher(payload, _settings(), fake_runner)
    assert duration_ms >= 0
    assert set(result.keys()) == {"raw", "graph"}
    assert called["cypher"] == "RETURN 1"
    assert called["database"] == "neo4j"


def test_execute_cypher_uses_custom_database() -> None:
    payload = backend_app.CypherRequest(
        cypher="RETURN 1",
        project="default",
        database="analytics",
    )
    called: Dict[str, Any] = {}

    def fake_runner(cypher: str, params: Dict[str, Any], database: str) -> Dict[str, Any]:
        called["database"] = database
        return {"raw": []}

    backend_app._execute_cypher(payload, _settings(), fake_runner)
    assert called["database"] == "analytics"


def test_execute_cypher_invalid_format() -> None:
    payload = backend_app.CypherRequest(
        cypher="RETURN 1",
        project="default",
        formats=["raw", "invalid"],
    )

    with pytest.raises(backend_app.HTTPException) as exc:
        backend_app._execute_cypher(payload, _settings(), lambda *_args, **_kwargs: {})

    assert exc.value.status_code == 400
    assert "formato válido" in str(exc.value.detail)


def test_execute_cypher_wraps_generic_errors() -> None:
    payload = backend_app.CypherRequest(cypher="RETURN 1", project="default")

    def failing_runner(*_args, **_kwargs):
        raise RuntimeError("boom")

    with pytest.raises(backend_app.HTTPException) as exc:
        backend_app._execute_cypher(payload, _settings(), failing_runner)

    assert exc.value.status_code == 502
    assert "Fallo al ejecutar" in str(exc.value.detail)


def test_validate_api_key_success() -> None:
    backend_app._validate_api_key("secret", "secret")


def test_validate_api_key_missing_expected() -> None:
    with pytest.raises(backend_app.HTTPException) as exc:
        backend_app._validate_api_key("value", None)
    assert exc.value.status_code == 500


def test_validate_api_key_invalid_value() -> None:
    with pytest.raises(backend_app.HTTPException) as exc:
        backend_app._validate_api_key("wrong", "expected")
    assert exc.value.status_code == 401


def test_table_to_csv_generates_output() -> None:
    table = {"columns": ["a", "b"], "rows": [[1, "text"], [2, "otro"]]}
    csv_text = backend_app._table_to_csv(table)
    assert "a,b" in csv_text
    assert '"text"' in csv_text
