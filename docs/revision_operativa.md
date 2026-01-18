# Revisión Operativa (Grounded Theory) — APP_Jupter

**Fecha:** 2026-01-16  
**Alcance:** `app/`, `backend/`, `frontend/`  

## 1) Veredicto: paradigma de Teoría Fundamentada usado

**Paradigma dominante (implementado):** **Teoría Fundamentada sistemática (Strauss & Corbin)**.

**Por qué:** el sistema formaliza un workflow por etapas con **Codificación Abierta → Codificación Axial → Núcleo selectivo (core category)**, y en axial usa tipos de relación estilo **causa / condición / consecuencia / parte-de**, lo cual encaja con el enfoque “sistemático/paradigmático” de Strauss/Corbin.

**Matices presentes (compatibles, pero no “paradigma dominante”):**
- **Reflexividad y memos** como artefactos persistibles.
- **Iteración exploratoria (Discovery)** como soporte de muestreo teórico/refinamientos, sin que eso implique “re-analizar todo” en cada iteración.

## 2) Evidencia en el código (puntos de anclaje)

### 2.1 app/
- **Workflow por etapas GT:** `Etapa 0..4` con codificación abierta y axial.
  - Ver: [app/analysis.py](../app/analysis.py)
- **Codificación axial formal (relaciones tipadas + evidencia mínima):**
  - Ver: [app/axial.py](../app/axial.py)
- **Núcleo selectivo (core category):**
  - Ver: [app/nucleus.py](../app/nucleus.py)
- **Comparación constante + codificación abierta (operacionalizada):**
  - Ver: [app/coding.py](../app/coding.py)

### 2.2 backend/
- **Discovery** produce memo/síntesis + códigos sugeridos + refinamientos para la próxima búsqueda.
  - Ver: [backend/app.py](../backend/app.py)
- **Health checks** disponibles para conectividad y diagnóstico.
  - Ver: [backend/app.py](../backend/app.py) (`/healthz`, `/api/health/full`)
- **Gestión de códigos candidatos** expuesta por API.
  - Ver: [backend/app.py](../backend/app.py) y rutas `/api/codes/candidates/*`
- **Autorización multi-tenant estricta** (org/proyecto/roles).
  - Ver: [backend/auth.py](../backend/auth.py), [app/project_state.py](../app/project_state.py)

### 2.3 frontend/
- **Dashboard por etapas** declara explícitamente el flujo de trabajo (incluye núcleo y validación/saturación).
  - Ver: [frontend/src/App.tsx](../frontend/src/App.tsx)
- **Panel de validación de códigos candidatos**.
  - Ver: [frontend/src/components/CodeValidationPanel.tsx](../frontend/src/components/CodeValidationPanel.tsx)
- **Salud del sistema y conectividad**.
  - Ver: [frontend/src/components/BackendStatus.tsx](../frontend/src/components/BackendStatus.tsx)
  - Ver: [frontend/src/components/SystemHealthDashboard.tsx](../frontend/src/components/SystemHealthDashboard.tsx)
- **Resiliencia UX (errores y carga)**.
  - Ver: [frontend/src/components/ApiErrorToast.tsx](../frontend/src/components/ApiErrorToast.tsx)
  - Ver: [frontend/src/components/PanelErrorBoundary.tsx](../frontend/src/components/PanelErrorBoundary.tsx)
  - Ver: [frontend/src/components/Skeleton.tsx](../frontend/src/components/Skeleton.tsx)

## 3) Implicaciones prácticas (operación del sistema)

- **Si el objetivo es coherencia metodológica**, la app debe seguir priorizando:
  - trazabilidad (memos, evidencias, versionado de códigos),
  - comparación constante,
  - validación mínima de relaciones axiales por evidencia,
  - y criterios explícitos para “núcleo selectivo”.

- **Discovery** debe entenderse como:
  - *búsqueda exploratoria + refinamientos (muestreo teórico asistido)*,
  - no como “re-ejecución del análisis completo de cada entrevista” en cada iteración.

- **Validación de códigos candidatos** agrega una etapa operativa explícita:
  - consolidación de propuestas y promoción a códigos definitivos,
  - mejora la trazabilidad entre sugerencias automáticas y decisiones humanas.

- **Multi-tenant estricto** implica:
  - segmentación por organización y proyecto,
  - verificación de roles en creación, lectura y administración.

## 4) Decisión metodológica recomendada (texto pegable)

> **Decisión:** El proyecto opera principalmente bajo Teoría Fundamentada **sistemática (Strauss & Corbin)**: se ejecuta codificación abierta, luego axial con relaciones tipadas (causa/condición/consecuencia/parte-de) respaldadas por evidencia, y posteriormente se evalúa un núcleo selectivo. Se incorporan memos y reflexividad como trazabilidad del proceso, y Discovery se usa como mecanismo de muestreo teórico/refinamiento exploratorio.

---

## 5) Notas

- Este documento describe el **paradigma que el software ya implementa** (por su diseño y affordances), no necesariamente el único paradigma compatible.
- Si se desea migrar el “paradigma dominante” hacia Charmaz (constructivista), habría que revisar: lenguaje de prompts, criterios de validación, y el rol explícito de reflexividad/co-construcción en reportes y decisiones.
