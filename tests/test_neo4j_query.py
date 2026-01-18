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
from app import queries


class FakeNode:
    def __init__(self, node_id: int, labels: list[str], **props: object) -> None:
        self.id = node_id
        self.labels = tuple(labels)
        self._props = dict(props)

    def __iter__(self):
        return iter(self._props)

    def __getitem__(self, key: str):
        return self._props[key]

    def items(self):
        return self._props.items()

    def keys(self):
        return self._props.keys()


class FakeRelationship:
    def __init__(self, rel_id: int, start_node: FakeNode, end_node: FakeNode, rel_type: str, **props: object) -> None:
        self.id = rel_id
        self.start_node = start_node
        self.end_node = end_node
        self.type = rel_type
        self._props = dict(props)

    def __iter__(self):
        return iter(self._props)

    def __getitem__(self, key: str):
        return self._props[key]

    def items(self):
        return self._props.items()

    def keys(self):
        return self._props.keys()


class FakePath:
    def __init__(self, nodes: list[FakeNode], relationships: list[FakeRelationship]) -> None:
        self.nodes = nodes
        self.relationships = relationships


class FakeRecord:
    def __init__(self, data: dict[str, object]) -> None:
        self._data = data

    def items(self):
        return self._data.items()

    def keys(self):
        return list(self._data.keys())

    def values(self):
        return list(self._data.values())

    def get(self, key: str, default=None):
        return self._data.get(key, default)


class FakeResult:
    def __init__(self, records):
        self._records = records

    def __iter__(self):
        return iter(self._records)


class FakeSession:
    def __init__(self, result: FakeResult):
        self._result = result
        self.last_query = None
        self.last_params = None

    def run(self, cypher: str, parameters: dict | None = None):
        self.last_query = cypher
        self.last_params = parameters
        return self._result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeDriver:
    def __init__(self, session: FakeSession):
        self._session = session
        self.last_kwargs = None

    def session(self, **kwargs):
        self.last_kwargs = kwargs
        return self._session


@pytest.fixture(autouse=True)
def _stub_project_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "resolve_project", lambda project, allow_create=False: project or "default")
    monkeypatch.setattr(main, "mark_stage", lambda *args, **kwargs: None)


def test_run_cypher_provides_multi_view() -> None:
    node_a = FakeNode(1, ["Categoria"], nombre="Infraestructura")
    node_b = FakeNode(2, ["Codigo"], nombre="Déficit de equipamientos")
    rel = FakeRelationship(10, node_a, node_b, "REL", tipo="condicion")
    path = FakePath([node_a, node_b], [rel])
    records = [
        FakeRecord({"categoria": node_a, "relacion": rel}),
        FakeRecord({"camino": path, "conteo": 1}),
    ]
    session = FakeSession(FakeResult(records))
    driver = FakeDriver(session)
    clients = SimpleNamespace(neo4j=driver)

    result = queries.run_cypher(clients, "MATCH (c) RETURN c", params={"limit": 5}, database="neo4j")

    assert driver.last_kwargs == {"database": "neo4j"}
    assert session.last_query == "CALL { MATCH (c) RETURN c } RETURN * LIMIT 500"
    assert session.last_params == {"limit": 5}

    assert result["table"]["columns"] == ["categoria", "relacion", "camino", "conteo"]
    assert result["raw"][0]["categoria"]["properties"]["nombre"] == "Infraestructura"

    graph_nodes = {node["id"] for node in result["graph"]["nodes"]}
    assert graph_nodes == {1, 2}
    assert result["graph"]["relationships"][0]["type"] == "REL"


def test_cli_neo4j_query_emits_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    settings = SimpleNamespace(neo4j=SimpleNamespace(database="neo4j"))
    fake_clients = SimpleNamespace(close=lambda: None)
    last_call: dict = {}

    class DummyLogger:
        def bind(self, **kwargs):
            return self

        def info(self, *args, **kwargs):
            return None

        def error(self, *args, **kwargs):
            return None

        def exception(self, *args, **kwargs):
            return None

    monkeypatch.setattr(main, "configure_logging", lambda level: DummyLogger())
    monkeypatch.setattr(main, "bind_run", lambda logger, run_id: logger)
    monkeypatch.setattr(main, "build_context", lambda env: (settings, fake_clients))

    def fake_run_cypher(_clients, cypher, params=None, database=None):
        last_call.update({"cypher": cypher, "params": params, "database": database})
        return {
            "raw": [{"n": 1}],
            "table": {"columns": ["n"], "rows": [[1]]},
            "graph": {"nodes": [], "relationships": []},
        }

    monkeypatch.setattr(main, "run_cypher", fake_run_cypher)

    exit_code = main.main([
        "--project",
        "default",
        "neo4j",
        "query",
        "--cypher",
        "RETURN $limit",
        "--param",
        "limit=5",
        "--param",
        "activo=true",
        "--format",
        "raw",
        "--json",
    ])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload == {"raw": [{"n": 1}]}

    assert last_call["cypher"] == "RETURN $limit"
    assert last_call["database"] == "neo4j"
    assert last_call["params"] == {"limit": 5, "activo": True}
