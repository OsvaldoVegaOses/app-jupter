"""
Configuración de logging estructurado con structlog.

Este módulo configura el sistema de logging para:
1. Salida a consola (formato legible, coloreado)
2. Salida a archivo (JSONL, rotación diaria)

Características:
    - Logging estructurado JSON para análisis automatizado
    - Rotación diaria con 30 días de retención
    - Integración con bibliotecas externas (uvicorn, neo4j, etc.)

Configuración:
    - LOGS_DIR: Directorio de logs (default: logs/)
    - LOG_FILENAME: Nombre del archivo (default: app.jsonl)
    - BACKUP_COUNT: Días de retención (default: 30)

Uso:
    from app.logging_config import configure_logging
    configure_logging(log_level="INFO")

Formato de logs JSONL:
    {"event": "ingest.fragment", "archivo": "...", "par_idx": 1, "timestamp": "..."}
"""

import logging
import logging.handlers
import re
import sys
import threading
from pathlib import Path
from typing import Optional

import structlog
import structlog.dev
import structlog.stdlib

# Constants
LOGS_DIR = Path("logs")
LOG_FILENAME = "app.jsonl"
BACKUP_COUNT = 30  # Keep 30 days of logs


class ContextualFileHandler(logging.Handler):
    """
    Enruta logs a carpetas por session_id (y opcionalmente project_id).

    Estructura:
        logs/{project_id}/{session_id}/app.jsonl

    Si no hay session_id, usa logs/app.jsonl.
    """

    def __init__(
        self,
        base_dir: Path,
        filename: str,
        when: str = "midnight",
        interval: int = 1,
        backup_count: int = BACKUP_COUNT,
        encoding: str = "utf-8",
    ) -> None:
        super().__init__()
        self.base_dir = Path(base_dir)
        self.filename = filename
        self.when = when
        self.interval = interval
        self.backup_count = backup_count
        self.encoding = encoding
        self._lock = threading.RLock()
        self._handlers: dict[tuple[str, str], logging.Handler] = {}
        self._default_handler = self._build_handler(self.base_dir)

    def _build_handler(self, directory: Path) -> logging.Handler:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            handler = logging.handlers.TimedRotatingFileHandler(
                filename=directory / self.filename,
                when=self.when,
                interval=self.interval,
                backupCount=self.backup_count,
                encoding=self.encoding,
            )
            if self.formatter:
                handler.setFormatter(self.formatter)
            return handler
        except OSError as exc:
            # If file creation fails (e.g., ENOSPC), fallback to stderr stream handler
            fallback = logging.StreamHandler(sys.stderr)
            if self.formatter:
                fallback.setFormatter(self.formatter)
            fallback.handle = fallback.emit  # type: ignore[attr-defined]
            return fallback

    @staticmethod
    def _sanitize(value: Optional[str], fallback: str) -> str:
        if not value:
            return fallback
        cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(value).strip())
        cleaned = cleaned.strip("._-") or fallback
        return cleaned[:80]

    def _select_handler(self) -> logging.Handler:
        try:
            ctx = structlog.contextvars.get_contextvars()
        except Exception:
            ctx = {}
        session_id = ctx.get("session_id")
        if not session_id:
            return self._default_handler
        project_id = ctx.get("project_id") or ctx.get("project") or "default"
        project_safe = self._sanitize(project_id, "default")
        session_safe = self._sanitize(session_id, "session")
        key = (project_safe, session_safe)
        with self._lock:
            handler = self._handlers.get(key)
            if handler is None:
                handler = self._build_handler(self.base_dir / project_safe / session_safe)
                if self.formatter:
                    handler.setFormatter(self.formatter)
                self._handlers[key] = handler
        return handler

    def emit(self, record: logging.LogRecord) -> None:
        handler = self._select_handler()
        try:
            handler.emit(record)
        except OSError as e:
            # Disk full or other IO error when writing logs; degrade gracefully to stderr
            try:
                msg = self.format(record) if self.formatter else record.getMessage()
                sys.stderr.write(f"[logging-fallback] {msg}\n")
                sys.stderr.flush()
            except Exception:
                # Last resort: ignore to avoid crashing the application
                pass
        except Exception:
            # Catch-all to ensure logging failures never bubble up
            try:
                msg = record.getMessage()
                sys.stderr.write(f"[logging-error] {msg}\n")
                sys.stderr.flush()
            except Exception:
                pass

    def setFormatter(self, fmt: logging.Formatter) -> None:  # type: ignore[override]
        super().setFormatter(fmt)
        with self._lock:
            self._default_handler.setFormatter(fmt)
            for handler in self._handlers.values():
                handler.setFormatter(fmt)

    def close(self) -> None:
        with self._lock:
            try:
                self._default_handler.close()
            finally:
                for handler in self._handlers.values():
                    handler.close()
                self._handlers.clear()
        super().close()

def configure_logging(log_level: str = "INFO") -> None:
    """
    Configures structlog and standard logging to output to:
    1. Console (Human readable, colored)
    2. File (JSONL, rotating daily)
    """
    
    # 1. Ensure logs directory exists
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / LOG_FILENAME

    # 2. Configure Standard Library Logging
    # This captures logs from libraries like uvicorn, neo4j, etc.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    
    # Create a contextual file handler (routes by session/project)
    file_handler = ContextualFileHandler(
        base_dir=LOGS_DIR,
        filename=LOG_FILENAME,
        when="midnight",
        interval=1,
        backup_count=BACKUP_COUNT,
        encoding="utf-8",
    )
    
    # We can use a simple formatter here, or rely on structlog's processor to format it before it gets here
    # But usually standard logging integration with structlog is complex.
    # Simpler approach: Standard logging goes to file as is, or we attach structlog to it.
    
    # Let's configure Structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            # Decide renderer based on output
            structlog.processors.JSONRenderer() if False else structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # RE-CONFIGURATION for Hybrid Output (Console + File)
    # The above valid configuration is for console-only or json-only.
    # To split outputs, we need to use `structlog.stdlib`
    
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Console Formatter (Colored)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(colors=True),
    ))

    # File Formatter (JSON)
    file_handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
    ))

    # Root Logger Configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers to avoid duplication (e.g. uvicorn default)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Silence noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("neo4j").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Log startup
    structlog.get_logger().info("logging_configured", log_dir=str(LOGS_DIR), file=str(log_file))
