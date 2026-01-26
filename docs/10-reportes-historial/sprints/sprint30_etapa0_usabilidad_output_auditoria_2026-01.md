# Sprint 30: Operacionalización Etapa 0 + Usabilidad del Output (estatus epistemológico)

**Fecha:** 13 Enero 2026  
**Estado:** ✅ Completado  
**Nota:** Docker se deja explícitamente para el final.

## Resumen Ejecutivo

Este sprint consolidó el sistema como una **máquina operativa de exploración conceptual** (no solo “una app que responde”), cerrando el circuito entre:

- **Control metodológico (Etapa 0)**: preparación, trazabilidad y gates antes de análisis.
- **Auditabilidad**: historial/versionado de decisiones de codificación.
- **Artefactos de producto**: outputs reutilizables (Markdown/JSON) para stakeholders.
- **Documentación coherente**: puertos/URLs/env canónicos y scripts alineados.

## Objetivos

- Operacionalizar Etapa 0 en UI y API (con gates y overrides auditables).
- Aumentar la usabilidad del output (salida “productizable”).
- Consolidar auditoría (historial de código) en backend + frontend.
- Reducir drift documental (puertos/URLs/env) y dejar guías consistentes.

## Entregables (alto nivel)

### Backend / App

- Gate Etapa 0 aplicado a flujos críticos de análisis (bloqueo controlado cuando no hay readiness).
- Endpoints de Etapa 0 para lectura/edición (protocol, actores/consentimientos, muestreo, plan de análisis) y workflow de overrides.
- Endpoints para artefactos de producto (generación/listado/descarga bajo carpeta `reports/<project_id>/`).

### Frontend

- Panel operativo de Etapa 0 integrado al flujo de trabajo.
- Modal/UX de historial de código para candidatos y códigos validados (auditoría “en contexto”).
- Trigger UI para generar artefactos de producto y visualizarlos/descargarlos.

### Documentación y scripts

- Puertos y URLs canónicos normalizados (backend `:8000`, Vite dev `:5173`, Redis host `:16379`).
- Scripts de validación y load test ajustados al puerto canónico.

## Cambios Destacados (por tema)

### 1) Gate metodológico (Etapa 0)

- **Qué problema resuelve:** evitar análisis “sin preparación” o sin condiciones mínimas (riesgo de interpretaciones fuera de marco, falta de consentimiento/actores/plan).
- **Qué se habilita:** override explícito y auditable cuando hay justificación institucional.

### 2) Auditabilidad de codificación

- **Qué problema resuelve:** “caja negra” en mutaciones de código (merge/promote/unassign) y dificultad para reconstruir decisiones.
- **Qué se habilita:** trazabilidad histórica accesible desde UI para revisión/corrección y auditorías.

### 3) Outputs productizables

- **Qué problema resuelve:** outputs “bonitos” pero poco reutilizables para informes/decisión.
- **Qué se habilita:** artefactos consistentes por proyecto (Markdown/JSON) para resumen ejecutivo, top insights, preguntas abiertas, etc.

### 4) Normalización documental

- **Qué problema resuelve:** drift de puertos/URLs/env (5000/8080 vs 8000) y guías contradictorias.
- **Qué se habilita:** onboarding más estable y menos fricción operativa.

## Validación realizada (pragmática)

- Backend levantando en `http://localhost:8000` y health check operativo.
- Import sanity-check del backend (carga de app y rutas).
- Barridos de documentación y scripts para eliminar referencias legacy a `:5000` y `:8080`.

## Riesgos y deuda técnica identificada

- **Estatus epistemológico aún no forzado por contrato:** el sistema puede presentar inferencias con forma de “hecho” si no hay etiquetas + evidencia visible.
- **Fricción de entorno frontend:** se observó un `npm run dev` con salida no exitosa durante sesión; requiere diagnóstico separado.
- **Docker:** intencionalmente pospuesto; falta alinear ejemplos y runbooks cuando se retome.

## Oportunidades de mejora (priorizadas)

### P0 — Estructurar estatus epistemológico (alto impacto, bajo costo)

**Problema:** el output no siempre distingue entre descripción, inferencia e implicación normativa, lo que puede confundir el estatus (“¿dijo el entrevistado o lo interpretó el sistema?”).

**Recomendación mínima viable (MVP):**

- Añadir etiquetas por insight:
  - `QUOTE` (cita textual)
  - `SUMMARY` (paráfrasis descriptiva)
  - `INTERPRETATION` (lectura teórica)
  - `HYPOTHESIS` (conjetura verificable)
  - `NORMATIVE` (recomendación/juicio)

**Reglas (para que no sea cosmética):**

- `QUOTE` y `SUMMARY` deben referenciar evidencia (fragment IDs).
- `HYPOTHESIS` debe incluir una pista de falsación/verificación (“qué buscar para confirmarlo/refutarlo”).
- `NORMATIVE` se presenta separado (bloque “Implicaciones/Recomendaciones”).

### P1 — Eje de soporte/confianza (reduce riesgo de “autoridad”)

- Añadir `confidence` (`high/medium/low`) y `evidence_count` por insight.
- UI: chip `TYPE • CONFIDENCE • #FRAGMENTS` + acceso rápido a 3–5 fragmentos.

### P1 — Contrato de artefactos (JSON) + rendering consistente

- Definir un schema simple para artefactos tipo `top_insights.json`:
  - `type`, `confidence`, `claim`, `evidence_ids`, `counterevidence`, `falsification_hint`.

### P2 — Tests y hardening

- Tests de API para Etapa 0 (status/readiness/overrides) y regresión de gates.
- E2E mínimo del flujo Etapa 0 → habilitar análisis.

### P2 — Mejora operativa (docs/lint)

- Check automático para detectar puertos legacy en CI (docs + scripts).

---

*Documentado: 13 Enero 2026*
