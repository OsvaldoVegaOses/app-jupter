"""
Utilidades auxiliares para logging estructurado.

Este módulo complementa a logging_config.py con funciones helper
para gestión de contexto de logging.

Funciones:
    - configure_logging(): Configura structlog y retorna logger
    - bind_run(): Asocia un run_id al contexto de logging
    - set_extra_context(): Añade contexto adicional
    - clear_context(): Limpia contexto para nueva operación

Uso de contexto:
    El run_id se propaga automáticamente a todos los logs downstream,
    permitiendo rastrear una operación completa de ingesta/análisis.

Example:
    >>> from app.logging_utils import configure_logging, bind_run
    >>> logger = configure_logging("DEBUG")
    >>> logger = bind_run(logger, "run-2024-01-15-001")
    >>> logger.info("ingest.start", files=10)
"""

from __future__ import annotations

from typing import Optional

import structlog

from .logging_config import configure_logging as configure_logging_core


def configure_logging(level: str = "INFO") -> structlog.BoundLogger:
    """Configure structlog + stdlib logging and return a bound logger."""
    configure_logging_core(level)
    return structlog.get_logger()


def bind_run(logger: structlog.BoundLogger, run_id: str) -> structlog.BoundLogger:
    structlog.contextvars.bind_contextvars(run_id=run_id)
    return logger.bind(run_id=run_id)


def set_extra_context(**kwargs) -> None:
    """Bind additional context variables for downstream logging."""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context(keys: Optional[list[str]] = None) -> None:
    """Clear selected context keys (or all if none provided)."""
    if keys:
        for key in keys:
            structlog.contextvars.unbind_contextvars(key)
    else:
        structlog.contextvars.clear_contextvars()
