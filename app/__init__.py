"""
Módulo app - Núcleo de procesamiento para análisis cualitativo de entrevistas.

Este paquete implementa el motor de análisis cualitativo basado en Teoría Fundamentada
(Grounded Theory) con apoyo de LLM para:

1. Ingesta y fragmentación de documentos DOCX
2. Generación de embeddings y almacenamiento vectorial (Qdrant)
3. Análisis LLM con codificación abierta y axial
4. Persistencia de códigos y relaciones (PostgreSQL + Neo4j)
5. Consultas híbridas y generación de reportes

Arquitectura de capas:
    - Configuración: settings.py, clients.py, logging_config.py
    - Datos: documents.py, embeddings.py, *_block.py
    - Procesamiento: ingestion.py, analysis.py, coding.py, axial.py
    - Consultas: queries.py, transversal.py, nucleus.py

Ver app/README.md para documentación detallada.
"""

__all__ = [
    # Configuración
    "settings",
    "clients",
    # Procesamiento
    "ingestion",
    "analysis",
    "documents",
]
