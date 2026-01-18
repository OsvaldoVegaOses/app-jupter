"""
Generación de embeddings via Azure OpenAI.

Este módulo encapsula la generación de embeddings vectoriales para fragmentos
de texto, utilizando Azure OpenAI como backend.

Características:
    - Retry automático con exponential backoff (3 intentos)
    - Splitting automático de batches en caso de error
    - Logging de eventos para diagnóstico

Modelo recomendado:
    - text-embedding-3-large (3072 dimensiones)
    - Alternativa: text-embedding-ada-002 (1536 dimensiones)

Funciones:
    - embed_batch(): Genera embeddings para una lista de textos
    - _call_embeddings(): Llamada directa a la API (con retry)

Estrategia de errores:
    Si un batch falla, se divide recursivamente a la mitad hasta
    poder procesar los textos. Esto maneja límites de tokens de la API.

Example:
    >>> from app.embeddings import embed_batch
    >>> embeddings = embed_batch(client, "text-embedding-3-large", ["Hola mundo", "Texto dos"])
    >>> print(len(embeddings[0]))  # 3072 dimensiones
"""

from __future__ import annotations

from typing import Iterable, List, Optional

import structlog
from openai import AzureOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

_logger = structlog.get_logger()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=30), reraise=True)
def _call_embeddings(client: AzureOpenAI, deployment: str, payload: List[str]):
    return client.embeddings.create(model=deployment, input=payload)


def embed_batch(
    client: AzureOpenAI,
    deployment: str,
    texts: Iterable[str],
    logger: Optional[structlog.BoundLogger] = None,
) -> List[List[float]]:
    payload = list(texts)
    if not payload:
        return []

    log = logger or _logger
    try:
        response = _call_embeddings(client, deployment, payload)
    except Exception as exc:
        if len(payload) <= 1:
            log.error("embed.batch.failure", error=str(exc), size=len(payload))
            raise
        midpoint = max(1, len(payload) // 2)
        log.warning("embed.batch.split", size=len(payload), reason=str(exc))
        left = embed_batch(client, deployment, payload[:midpoint], logger=log)
        right = embed_batch(client, deployment, payload[midpoint:], logger=log)
        return left + right

    data = sorted(response.data, key=lambda item: item.index)
    embeddings = [item.embedding for item in data]
    if len(embeddings) != len(payload):
        log.warning(
            "embed.batch.misaligned",
            requested=len(payload),
            returned=len(embeddings),
        )
    return embeddings
