# Arquitectura (App Bibliográfica)

## Objetivo
Soportar revisión y síntesis de literatura: ingesta de fuentes, normalización de referencias y construcción de un marco teórico con evidencia auditable.

## Bloques
- Registry de obras (works)
- Ingesta PDF/HTML → texto estructurado → fragmentos con ubicación
- Extracción/normalización de referencias (DOI/ISBN)
- Motor de síntesis (LLM + reglas) con citas formales
- Export bibliográfico (BibTeX/RIS/CSL-JSON)

## Nota
La evaluación de brechas frente al baseline de entrevistas está en `matriz_brechas_marco_teorico_literatura.md`.
