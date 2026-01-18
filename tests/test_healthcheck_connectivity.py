from __future__ import annotations

from types import SimpleNamespace
from typing import List

from scripts import healthcheck


class StubCollectionInfo:
    def __init__(self, size: int):
        self.config = SimpleNamespace(params=SimpleNamespace(vectors=SimpleNamespace(size=size)))


class StubQdrant:
    def __init__(self, size: int, fail_get: bool = False):
        self.size = size
        self.fail_get = fail_get
        self.indexes: List[str] = []

    def get_collection(self, _name: str):
        if self.fail_get:
            raise RuntimeError("boom")
        return StubCollectionInfo(self.size)

    def create_payload_index(self, *, field_name: str, **_kwargs):
        self.indexes.append(field_name)


class StubCursor:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.executed: List[str] = []

    def __enter__(self):
        if self.fail:
            raise RuntimeError("db down")
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, *_args, **_kwargs):
        if self.fail:
            raise RuntimeError("db down")
        self.executed.append(sql)
        return None

    def fetchone(self):
        return (1,)


class StubPostgres:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls = 0

    def cursor(self):
        self.calls += 1
        return StubCursor(fail=self.fail)


class StubNeo4jSession:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.called = False

    def __enter__(self):
        if self.fail:
            raise RuntimeError("neo4j down")
        return self

    def __exit__(self, *_args):
        return False

    def run(self, *_args, **_kwargs):
        self.called = True
        return SimpleNamespace(single=lambda: None)


class StubNeo4jDriver:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.sessions: List[StubNeo4jSession] = []

    def session(self, **_kwargs):
        session = StubNeo4jSession(fail=self.fail)
        self.sessions.append(session)
        return session


def _clients(
    *,
    qdrant_size: int = 1536,
    qdrant_fail: bool = False,
    pg_fail: bool = False,
    neo4j_fail: bool = False,
    embed_dims: int | None = 1536,
):
    # embed_dims defaults to 1536 (typical embedding size); tests can override to simulate mismatches
    return SimpleNamespace(
        qdrant=StubQdrant(qdrant_size, fail_get=qdrant_fail),
        postgres=StubPostgres(fail=pg_fail),
        neo4j=StubNeo4jDriver(fail=neo4j_fail),
        embed_dims=embed_dims if embed_dims is not None else qdrant_size,
    )


def _settings(collection: str = "entrevistas", database: str = "neo4j"):
    return SimpleNamespace(
        qdrant=SimpleNamespace(collection=collection),
        neo4j=SimpleNamespace(database=database),
    )


def test_check_qdrant_success_builds_indexes():
    clients = _clients()
    errors: List[str] = []

    healthcheck._check_qdrant(clients, _settings(), errors)

    assert errors == []
    # ensure_payload_indexes should attempt all field indexes
    assert clients.qdrant.indexes  # at least one index registered


def test_check_qdrant_dimension_mismatch():
    clients = _clients(qdrant_size=256)
    errors: List[str] = []

    healthcheck._check_qdrant(clients, _settings(), errors)

    assert any("dimension de coleccion" in err for err in errors)


def test_check_postgres_reports_errors():
    clients = _clients(pg_fail=True)
    errors: List[str] = []

    healthcheck._check_postgres(clients, errors)

    assert any(err.startswith("PostgreSQL") for err in errors)


def test_check_neo4j_reports_errors():
    clients = _clients(neo4j_fail=True)
    errors: List[str] = []

    healthcheck._check_neo4j(clients, _settings(), errors)

    assert any(err.startswith("Neo4j") for err in errors)
