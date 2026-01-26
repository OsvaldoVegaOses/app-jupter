from __future__ import annotations

import sys
import types
import os
from typing import Any, Dict

os.environ.setdefault("NEO4J_API_KEY", "test-key")


def _passthrough_processor(*_args, **_kwargs):
    def processor(_logger, _method_name, event_dict: Dict[str, Any]):
        return event_dict

    return processor


if "structlog" not in sys.modules:
    structlog = types.ModuleType("structlog")

    structlog.configure = lambda *args, **kwargs: None  # type: ignore
    structlog.contextvars = types.SimpleNamespace(
        bind_contextvars=lambda **kwargs: None,
        merge_contextvars=lambda _logger, _method_name, event_dict: event_dict,
        unbind_contextvars=lambda key: None,
        clear_contextvars=lambda: None,
    )
    structlog.processors = types.SimpleNamespace(
        TimeStamper=lambda *args, **kwargs: _passthrough_processor(),
        add_log_level=_passthrough_processor(),
        StackInfoRenderer=_passthrough_processor,
        format_exc_info=_passthrough_processor(),
        JSONRenderer=_passthrough_processor,
    )

    class _BoundLogger:
        def __init__(self):
            self._context: Dict[str, Any] = {}

        def bind(self, **kwargs):
            self._context.update(kwargs)
            return self

        def info(self, *args, **kwargs):
            return None

        def error(self, *args, **kwargs):
            return None

        def exception(self, *args, **kwargs):
            return None

    class _LoggerFactory:
        def __call__(self, *args, **kwargs):
            return _BoundLogger()

    class _ProcessorFormatter:
        wrap_for_formatter = _passthrough_processor()
        def __init__(self, *args, **kwargs):
            pass

    structlog.stdlib = types.SimpleNamespace(
        LoggerFactory=_LoggerFactory,
        BoundLogger=_BoundLogger,
        add_logger_name=_passthrough_processor(),
        add_log_level=_passthrough_processor(),
        PositionalArgumentsFormatter=_passthrough_processor,
        ProcessorFormatter=_ProcessorFormatter,
    )

    class _ConsoleRenderer:
        def __init__(self, *args, **kwargs):
            pass
        def __call__(self, *args, **kwargs):
            return ""

    structlog.dev = types.SimpleNamespace(
        ConsoleRenderer=_ConsoleRenderer,
        set_exc_info=_passthrough_processor(),
    )

    structlog.make_filtering_bound_logger = lambda *args, **kwargs: _BoundLogger
    structlog.PrintLoggerFactory = _LoggerFactory

    structlog.get_logger = lambda *_args, **_kwargs: _BoundLogger()  # type: ignore

    sys.modules["structlog"] = structlog
    sys.modules["structlog.dev"] = structlog.dev
    sys.modules["structlog.stdlib"] = structlog.stdlib
    sys.modules["structlog.processors"] = structlog.processors
    sys.modules["structlog.contextvars"] = structlog.contextvars


# FastAPI mock removed to use installed package



if "neo4j" not in sys.modules:
    neo4j = types.ModuleType("neo4j")

    class _StubDriver:
        def session(self, **kwargs):
            raise RuntimeError("neo4j driver stub does not provide sessions in tests")

        def close(self):
            return None

    class Query:  # type: ignore
        """Stub for neo4j.Query."""
        def __init__(self, text: str, timeout: float = None, metadata: dict = None):
            self.text = text
            self.timeout = timeout
            self.metadata = metadata

    neo4j.GraphDatabase = types.SimpleNamespace(driver=lambda *args, **kwargs: _StubDriver())
    neo4j.Driver = _StubDriver
    neo4j.Query = Query  # type: ignore[attr-defined]

    exceptions = types.ModuleType("neo4j.exceptions")

    class ClientError(Exception):
        pass

    exceptions.ClientError = ClientError
    neo4j.exceptions = exceptions

    sys.modules["neo4j"] = neo4j
    sys.modules["neo4j.exceptions"] = exceptions
    sys.modules["neo4j.graph"] = types.ModuleType("neo4j.graph")


if "psycopg2" not in sys.modules:
    psycopg2 = types.ModuleType("psycopg2")

    class _StubCursor:
        def execute(self, *args, **kwargs):
            return None

        def fetchall(self):
            return []

        def close(self):
            return None

    class _StubConnection:
        def close(self):
            return None

        def cursor(self):
            return _StubCursor()

        def set_client_encoding(self, *_args, **_kwargs):
            return None

    psycopg2.connect = lambda *args, **kwargs: _StubConnection()  # type: ignore
    extensions = types.ModuleType("psycopg2.extensions")
    extensions.connection = object  # type: ignore[attr-defined]
    psycopg2.extensions = extensions

    # Add pool module stub for connection pooling
    pool_module = types.ModuleType("psycopg2.pool")

    class ThreadedConnectionPool:  # type: ignore
        def __init__(self, minconn, maxconn, *args, **kwargs):
            self.minconn = minconn
            self.maxconn = maxconn

        def getconn(self):
            return _StubConnection()

        def putconn(self, conn, close=False):
            return None

        def closeall(self):
            return None

    pool_module.ThreadedConnectionPool = ThreadedConnectionPool  # type: ignore[attr-defined]
    psycopg2.pool = pool_module  # type: ignore[attr-defined]

    sys.modules["psycopg2"] = psycopg2
    sys.modules["psycopg2.extensions"] = extensions
    sys.modules["psycopg2.pool"] = pool_module

    extras = types.ModuleType("psycopg2.extras")

    def execute_values(*args, **kwargs):
        return None

    class Json:  # type: ignore
        def __init__(self, value):
            self.value = value

    extras.execute_values = execute_values  # type: ignore[attr-defined]
    extras.Json = Json  # type: ignore[attr-defined]
    psycopg2.extras = extras  # type: ignore[attr-defined]
    sys.modules["psycopg2.extras"] = extras


if "azure" not in sys.modules:
    azure = types.ModuleType("azure")
    identity = types.ModuleType("azure.identity")

    class DefaultAzureCredential:  # type: ignore
        def __init__(self, *args, **kwargs):
            return None

    def get_bearer_token_provider(_credential, _scope):
        return lambda: "token"

    identity.DefaultAzureCredential = DefaultAzureCredential  # type: ignore[attr-defined]
    identity.get_bearer_token_provider = get_bearer_token_provider  # type: ignore[attr-defined]
    azure.identity = identity  # type: ignore[attr-defined]

    sys.modules["azure"] = azure
    sys.modules["azure.identity"] = identity


if "openai" not in sys.modules:
    openai = types.ModuleType("openai")

    class AzureOpenAI:  # type: ignore
        class _Embeddings:
            def create(self, *args, **kwargs):
                point = types.SimpleNamespace(embedding=[0.0])
                return types.SimpleNamespace(data=[point])

        def __init__(self, *args, **kwargs):
            self.embeddings = self._Embeddings()

    openai.AzureOpenAI = AzureOpenAI  # type: ignore[attr-defined]
    sys.modules["openai"] = openai

    types_module = types.ModuleType("openai.types")
    chat_module = types.ModuleType("openai.types.chat")

    class _Param:
        def __init__(self, *args, **kwargs):
            return None

    chat_module.ChatCompletionMessageParam = _Param  # type: ignore[attr-defined]
    chat_module.ChatCompletionNamedToolChoiceParam = _Param  # type: ignore[attr-defined]
    chat_module.ChatCompletionToolParam = _Param  # type: ignore[attr-defined]
    chat_module.ChatCompletionToolMessageParam = _Param  # type: ignore[attr-defined]
    chat_module.ChatCompletionUserMessageParam = _Param  # type: ignore[attr-defined]
    chat_module.ChatCompletionSystemMessageParam = _Param  # type: ignore[attr-defined]

    types_module.chat = chat_module  # type: ignore[attr-defined]
    sys.modules["openai.types"] = types_module
    sys.modules["openai.types.chat"] = chat_module


# qdrant_client mocking removed - using installed package instead
# The real qdrant_client library is installed and should be used.


if "tenacity" not in sys.modules:
    tenacity = types.ModuleType("tenacity")

    def retry(*_args, **_kwargs):
        def decorator(func):
            return func

        return decorator

    def stop_after_attempt(*_args, **_kwargs):
        return None

    def wait_exponential(*_args, **_kwargs):
        return None

    tenacity.retry = retry  # type: ignore[attr-defined]
    tenacity.stop_after_attempt = stop_after_attempt  # type: ignore[attr-defined]
    tenacity.wait_exponential = wait_exponential  # type: ignore[attr-defined]

    sys.modules["tenacity"] = tenacity


if "docx" not in sys.modules:
    docx = types.ModuleType("docx")

    class Document:  # type: ignore
        def __init__(self, *args, **kwargs):
            self.paragraphs = []

    docx.Document = Document  # type: ignore[attr-defined]
    sys.modules["docx"] = docx


if "rapidfuzz" not in sys.modules:
    rapidfuzz = types.ModuleType("rapidfuzz")
    distance = types.ModuleType("rapidfuzz.distance")

    class Levenshtein:  # type: ignore
        @staticmethod
        def normalized_similarity(s1, s2):
            # Simple stub that returns 1.0 for equal strings, 0.0 otherwise
            return 1.0 if s1 == s2 else 0.5

        @staticmethod
        def distance(s1, s2):
            return 0 if s1 == s2 else len(s1)

    distance.Levenshtein = Levenshtein  # type: ignore[attr-defined]
    rapidfuzz.distance = distance  # type: ignore[attr-defined]

    sys.modules["rapidfuzz"] = rapidfuzz
    sys.modules["rapidfuzz.distance"] = distance
