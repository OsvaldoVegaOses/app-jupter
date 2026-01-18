# Audit report (enero 2026)

**Fecha:** 2026-01-13  
**Ámbito:** contrastar (con evidencia de código) el “primer análisis externo” sobre: pensamiento estructurado, marcadores epistemológicos, control de versión cognitiva, y jerarquía.

---

## Contraste del primer análisis externo

### ✅ Diagnóstico honesto (pensamiento estructurado / no-wrapper)
**Veredicto: mayormente confirmado, con matices.**

- El sistema **no es un wrapper superficial**: hay pipeline multi-etapa, persistencia de artefactos y grafo (Etapa 3/4, candidatos, axial, GDS, etc.).
- El sistema sí usa **salidas estructuradas** (contratos JSON en prompts y normalización), y usa “trazas” operativas (eventos y auditoría) para correlación.
- **Matiz importante:** “logs de razonamiento” no es correcto como afirmación general. En el flujo de análisis principal (/api/analyze) lo que se obtiene y se loguea es **output estructurado + eventos**, no razonamiento paso-a-paso. El modo “chain_of_thought” existe pero está expuesto principalmente en GraphRAG.

**Evidencia:**
- /api/analyze sync y persist opcional: [backend/app.py](backend/app.py#L4680-L4860)
- GraphRAG “chain_of_thought” opcional: [backend/routers/graphrag.py](backend/routers/graphrag.py#L35-L160) y [app/graphrag.py](app/graphrag.py#L530-L675)

---

### ⚠️ Marcadores epistemológicos (existen, pero la persistencia es incompleta)
**Veredicto: parcialmente correcto (hay más de lo que indica, pero el problema de persistencia es real).**

- Los marcadores epistemológicos **sí existen** y están integrados en varios puntos (tipo + evidencia; regla: OBSERVATION requiere evidence_ids, si no se degrada).
- En el flujo principal se producen `memo_statements` como estructura explícita.
- **Problema real:** la persistencia “principal” (PostgreSQL) **no guarda de forma canónica** los `memo_statements`/tipos epistemológicos del memo. Se guardan códigos/candidatos/axial/evidencia, pero el memo epistemicamente tipado queda como payload/transitorio.

**Evidencia:**
- Tipos y reglas (_EPISTEMIC_TYPES + normalización): [backend/routers/agent.py](backend/routers/agent.py#L98-L140)
- Prompt/normalización en endpoints que retornan `memo_statements`: [backend/app.py](backend/app.py#L5639-L5750)
- Persistencia del análisis se centra en Etapa 3/4 + evidencia (sin tabla/campo explícito para memo_statements): [app/analysis.py](app/analysis.py#L530-L840)

**Implicación:** se logra claridad epistemológica “en pantalla / en respuesta”, pero no se preserva como “memoria histórica consultable” salvo que se persista el JSON completo en otro artefacto.

---

### ⚠️ Control de versión cognitiva (codigo_versiones existe, pero no se usa)
**Veredicto: confirmado.**

- Existe infraestructura para versionar cambios de códigos (`codigo_versiones`, `log_code_version`, `get_code_history`).
- En el repositorio actual, `log_code_version` **no tiene usos**: no hay wiring desde endpoints o flujos de edición.
- Además, operaciones de upsert tienden a **sobrescribir** (p.ej., updates por conflicto) sin registrar “antes/después” en historial.

**Evidencia:**
- Tabla y helpers: [app/postgres_block.py](app/postgres_block.py#L1662-L1750)

**Implicación:** el sistema puede producir y actualizar interpretaciones/códigos, pero no preserva por defecto una genealogía cognitiva (qué cambió, cuándo, por quién, y por qué).

---

### ⚠️ Jerarquía (capacidad técnica existe, pero el conocimiento producido tiende a ser plano)
**Veredicto: parcialmente correcto.**

- La **capacidad técnica de jerarquía** existe (Neo4j + relaciones categoría↔código; GDS para comunidades/centralidad).
- Sin embargo, la generación automática predominante produce estructuras **tipo lista** (matriz abierta y axial) y no un árbol/ontología multi-nivel estable (p.ej., “familias de categorías → ejes → núcleo → teoría” con trazas de evidencia por nivel).

**Evidencia:**
- Persistencia axial y vínculo con evidencia (fragmentos): [app/analysis.py](app/analysis.py#L800-L920)
- Algoritmos GDS disponibles (Louvain/PageRank, etc.): [app/graph_algorithms.py](app/graph_algorithms.py#L1-L200)

---

## Recomendaciones mínimas (para alinear con la crítica)

1) **Persistencia epistemológica:** agregar tabla/columna (idealmente JSONB) para `memo_statements` + `structured` por archivo/proyecto (y mantener `memo_sintesis` string por compatibilidad).
2) **Cognitive version control real:** conectar `log_code_version()` a los flujos que cambian memos/códigos (update/merge/delete) y exponer `get_code_history()` en API/UI.
3) **Jerarquía explícita:** definir niveles (p.ej., Código → Categoría → Eje → Núcleo) y persistir relaciones; generar “explanation graph” que permita navegar evidencia → inferencia → decisión.
4) **Trazabilidad sin “razonamiento sensible”:** si se usa chain-of-thought, tratarlo como modo diagnóstico y no como default; persistir hashes/versiones (prompt/schema/model) en lugar de “pensamiento libre” para auditoría reproducible.
