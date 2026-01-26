# Guía paso a paso: pasar de Codificación Abierta → Codificación Axial

> **Fecha**: 2026-01-21
>
> **Ámbito**: transición operativa/metodológica desde **códigos abiertos** (evidencias + codebook) hacia **categorías axiales** y **relaciones** (estructura + grafo).
>
> **Artefactos del sistema**:
> - PostgreSQL: `analisis_codigos_abiertos` (abierta), `codigos_candidatos` (bandeja), `analisis_axial` (axial)
> - Neo4j: nodos `Categoria`, `Codigo` y relaciones axiales (para GDS y visualización)
> - UI: `CodeValidationPanel` (bandeja) y `Neo4jExplorer` (grafo/GDS)

## 0) Gate infra (pre-axialidad): ¿la ontología está lista?

Antes de comenzar axialidad (relaciones + GDS), valida **solo infraestructura**:

- Endpoint: `GET /api/admin/code-id/status?project=<project>`
- Condición normativa:

```text
axial_ready = (
  missing_code_id == 0 AND
  missing_canonical_code_id == 0 AND
  divergences_text_vs_id == 0 AND
  cycles_non_trivial_nodes == 0
)
```

Reglas de lectura (para evitar errores conceptuales):

- `self-canonical` (`canonical_code_id = code_id`) es **estado esperado** de códigos canónicos estables. No es inconsistencia.
- `cycles_non_trivial` refiere a ciclos de longitud > 1 (ej. A→B→A). Los self-loops (A→A) no bloquean.
- `ontology_freeze` es un **bloqueo operacional de mutación** (backfill/repair); no es parte de `axial_ready`.

Recomendación operativa:

- Al iniciar axialidad, activa freeze para evitar cambios ontológicos durante relaciones/GDS.

## 1) ¿Cuándo “conviene” pasar a axial?

Criterios prácticos (no dogmáticos) para iniciar **axial**:

- El **codebook** dejó de crecer caóticamente y está **consolidado** (deduplicado y con definiciones mínimas).
- El backlog de candidatos se mantiene **controlado** (no “explota” tras cada corrida de sugerencias).
- Se observa **cobertura razonable** (códigos aplicados a una porción amplia de fragmentos) y/o señales de **saturación**.

Herramientas para verificarlo:

- Gate operativo: `GET /api/coding/gate`.
- Métricas de bandeja (incluye códigos únicos): `GET /api/codes/stats/sources`.
  - Buen UX: la respuesta incluye `validated_unpromoted_total` / `validated_unpromoted_unique` para medir **validados pendientes por promover**.
  - En la UI (CodeValidationPanel) los candidatos validados ya promovidos quedan marcados como `↑ promovido`.

## 2) Paso 0 — Consolidar codificación abierta (pre-requisito)

Antes de crear estructura axial, estabiliza el “material”:

1. **Deduplicación Pre‑Hoc** (antes de insertar masivamente):
   - `POST /api/codes/check-batch`

2. **Deduplicación Post‑Hoc** (sobre el codebook ya existente):
   - `POST /api/codes/detect-duplicates`

3. **Fusión gobernada** (auditable):
   - Manual: `POST /api/codes/candidates/merge`
   - Lote/auto: `POST /api/codes/candidates/auto-merge`

Regla operativa recomendada:

- Toda fusión debe dejar **memo** (justificación) y, si aplica, `idempotency_key` para evitar repeticiones.

## 2.1) Ruta UI (Frontend) — clicks exactos (de Abierta → Axial)

Ruta A (barra superior):

1. Selecciona el proyecto activo (arriba).
2. En la navegación principal, haz click en **Investigación**.
3. En la sub‑navegación de Investigación:
  - **Codificación abierta**: aquí están Discovery/Coding y la **Bandeja de Códigos Candidatos** (panel `CodeValidationPanel`).
  - **Codificación axial**: haz click en **Codificación axial** para abrir el stack axial.

Al entrar a **Codificación axial** verás (en este orden):

- `LinkPredictionPanel`: sugerencias estructurales (hipótesis) basadas en link prediction.
- `HiddenRelationshipsPanel`: descubrimiento de “relaciones ocultas” + auditoría de evidencia + memo IA.
- `Neo4j Bloom` (si está configurado) o fallback **Neo4j Explorer** (React).

Ruta B (desde el panel de etapas):

1. En la navegación principal, entra a **Flujo de trabajo**.
2. En **ETAPA 4: CODIFICACIÓN AXIAL**, haz click en **Ir a Codificación Axial**.

Nota operativa importante:

- Hoy la UI te ayuda a **explorar** y **auditar** hipótesis (link prediction / relaciones ocultas) y a **visualizar** el grafo.
- El registro explícito de relaciones `Categoria → Codigo` con evidencia mínima (>=2 fragmentos) se hace por CLI (`python main.py axial relate ...`) y luego se visualiza en Neo4j.

## 3) Paso 1 — Definir categorías axiales (diseño)

Crea un set inicial de **categorías axiales** (pocas y claras). Para cada categoría define:

- Nombre (estable y no redundante)
- Definición operacional (qué incluye / qué excluye)
- Indicadores / señales empíricas (cómo “se ve” en el texto)
- Códigos abiertos candidatos a pertenecer a la categoría

Sugerencia: iniciar con 5–12 categorías “provisionales” y refinarlas iterativamente.

## 4) Paso 2 — Proponer relaciones axiales (manual + asistido)

### 4.1 Manual (recomendado para el arranque)

Registra relaciones **Categoría → Código** con evidencia explícita (mínimo 2 fragmentos):

- CLI:
  - `python main.py axial relate --categoria "..." --codigo "..." --tipo <REL> --evidencia <frag1> <frag2> [--memo "..."]`

Notas:

- `--tipo` está restringido a `ALLOWED_REL_TYPES` (ver `python main.py axial relate --help`).
- `--evidencia` debe contener IDs de fragmentos existentes en PostgreSQL.

### 4.2 Asistido (para generar hipótesis)

Genera sugerencias para revisión humana:

- Link prediction general:
  - `GET /api/axial/predict?project=...&top_k=10`
- Sugerencias por categoría:
  - `GET /api/axial/predict?project=...&categoria=...&top_k=10`
- Sugerencias por comunidades:
  - `GET /api/axial/community-links?project=...`

Estas salidas se tratan como **hipótesis** (no como “verdad” automática).

## 5) Paso 3 — Evaluar sugerencias y producir memo (IA + métricas)

Para sostener gobernanza epistemológica (qué es observación vs interpretación vs hipótesis):

1. Métricas rápidas de evidencia (diversidad/overlap):
   - `POST /api/axial/hidden-relationships/metrics`

2. Memo estructurado con estatus epistemológico:
   - `POST /api/axial/analyze-hidden-relationships`

Uso recomendado:

- Primero filtrar sugerencias con evidencia débil (métricas).
- Luego pedir memo IA **solo** sobre el top más prometedor.
- Finalmente validar con lectura de fragmentos y criterio humano.

## 6) Paso 4 — Persistir y sincronizar al grafo (Neo4j)

1. Persistencia axial (PostgreSQL)

- Las relaciones se registran en `analisis_axial` al usar el CLI `axial relate`.

2. Sincronización a Neo4j (para visualización y GDS)

- `POST /admin/sync-neo4j/axial?project=<project>&batch_size=500&offset=0`

## 7) Paso 5 — Cálculo estructural (GDS) y lectura diagnóstica

Ejecuta algoritmos de Graph Data Science sobre el grafo axial:

- API:
  - `POST /api/axial/gds` con `{"algorithm": "louvain"|"pagerank"|"betweenness", "persist": false}`
- CLI:
  - `python main.py axial gds --algorithm louvain`

Interpretación típica:

- `louvain`: comunidades (agrupamientos) útiles para contrastar tu esquema de categorías.
- `pagerank`: centralidad (qué categorías/códigos estructuran el sistema).
- `betweenness`: puentes (elementos que conectan subdominios).

## 8) Paso 6 — Control de calidad (QA) y checklist mínimo

Checklist sugerido antes de declarar “Axial en curso”:

- [ ] Categorías axiales tienen definiciones (aunque sean provisionales).
- [ ] Cada relación axial tiene evidencia (>=2 fragmentos) y, cuando aplique, memo.
- [ ] Se sincronizó a Neo4j y la visualización es consistente.
- [ ] GDS ejecutado al menos una vez (para diagnóstico, no como “verdad”).

## 9) Referencias internas

- `backend/routers/graphrag.py` (endpoints `/api/axial/*`)
- `backend/app.py` (endpoints `/api/axial/analyze-hidden-relationships`, `/api/axial/hidden-relationships/metrics`)
- `backend/routers/admin.py` (`/admin/sync-neo4j/axial`)
- `app/axial.py` (reglas y validaciones de codificación axial)
- `main.py` (CLI: `axial relate`, `axial gds`)
