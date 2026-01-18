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

import logging
import sys
from typing import Optional

import structlog


def configure_logging(level: str = "INFO") -> structlog.BoundLogger:
    """Configure structlog + stdlib logging and return a bound logger."""
    logging_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        level=logging_level,
        format="%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logger = structlog.get_logger()
    return logger


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
