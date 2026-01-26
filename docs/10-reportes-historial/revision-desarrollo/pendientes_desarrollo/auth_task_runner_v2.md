# AUTH Task — Runner v2 (Discovery contrastivo: Positivos/Negativos/Target + trazabilidad)

**Fecha:** 2026-01-12  
**Estado:** Propuesto (Backlog)  
**Owner:** Backend+UX (Discovery/Agente)  

## 1) Contexto
El sistema ya soporta **Discovery manual** con triplete **Positivos / Negativos / Target** en `frontend/src/components/DiscoveryPanel.tsx`.

Sin embargo, el **Runner automatizado** (Sprint 29) que se ejecuta desde el botón “Runner”:
- llama a `POST /api/agent/execute` enviando solo `concepts` (positivos),
- en backend ejecuta `app/discovery_runner.py` con patrones que hoy usan **negativos automáticos** (`AUTO_NEGATIVES`) y **no consumen** los negativos/target definidos por el usuario,
- en el post-run (`backend/routers/agent.py`) genera síntesis y códigos con `_analyze_fragments_with_llm(... negative_texts=[] , target_text=None)`.

Resultado: el Runner **no implementa el Discovery contrastivo** (positivos vs negativos + objetivo), lo que desalineó la expectativa metodológica (E3 discovery-first) con el comportamiento real.

---

## 2) Objetivo
Implementar **Runner v2** para que el Runner automatizado:
1) use el **triplete completo** (Positivos/Negativos/Target) como contrato de entrada,
2) ejecute **búsqueda contrastiva** (penalización por negativos y orientación por target) de forma reproducible,
3) persista trazas suficientes para auditoría (parámetros, pesos, query efectiva y resultados agregados),
4) mantenga compatibilidad con Runner MVP (solo positivos) sin romper UI ni API.

---

## 3) Alcance

### Frontend
- Componente: `frontend/src/components/DiscoveryPanel.tsx`
  - Actualizar el botón Runner para que envíe:
    - `concepts` (positivos)
    - `negative_concepts` (negativos, opcional)
    - `target_text` (opcional)
    - `runner_version: "v2"` (o `mode: "contrastive"`) para poder mantener MVP.
  - UX:
    - Cambiar tooltip y copy: dejar explícito cuándo es v1 vs v2.
    - Mostrar en el panel de estado del runner (Runner Discovery) un resumen de parámetros usados:
      - positivos/negativos/target
      - top_k
      - pesos (si aplica)

### Backend
- Router: `backend/routers/agent.py`
  - Extender `AgentExecuteRequest` para aceptar:
    - `negative_concepts: Optional[List[str]] = None`
    - `target_text: Optional[str] = None`
    - `runner_version: Optional[str] = "v1"` (o enum simple)
    - (opcional) `contrastive_weights: Optional[Dict[str, float]]` (ver Diseño)
  - Pasar el triplete a `run_discovery_iterations(...)`.
  - En `discovery_only` post-run:
    - llamar `_analyze_fragments_with_llm` con `negative_texts` y `target_text` reales.
    - reflejar el triplete en `_write_runner_report` (sección Parámetros).

- Runner: `app/discovery_runner.py`
  - Introducir un modo **contrastivo** que genere una **query vectorial** a partir de:
    - positivos (lista)
    - negativos (lista)
    - target_text (string opcional)
  - Mantener `AUTO_NEGATIVES` como fallback, pero solo si el usuario no entrega negativos (o como “negativos adicionales”).

### Persistencia y trazabilidad
- Ya existe `discovery_runs` con columnas `positivos` y `negativos`.
- Requisito v2: registrar también `target_text` y la “config efectiva” (pesos, top_k, score_threshold, reglas de combinación).

Opciones:
1) **Extender `discovery_runs`** con:
   - `target_text TEXT`
   - `config JSONB`
   - `vector_mode TEXT` ("v1"/"v2")
2) Si se quiere mínimo riesgo inicial: persistir `target_text` dentro de `query` y/o `memo`, y usar `discovery_navigation_log` para trazabilidad rica (ya soporta `target_text`).

Recomendación: (1) con una función `ensure_*` que haga `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` para instalaciones existentes.

---

## 4) Diseño (propuesta)

### 4.1 Contrato Runner v2 (entrada)
Ejemplo payload desde UI:

```json
{
  "project_id": "proj_x",
  "concepts": ["rol_municipal_planificacion"],
  "negative_concepts": ["logistica_entrevista", "muletilla"],
  "target_text": "Planificación urbana y gobernanza local",
  "runner_version": "v2",
  "max_interviews": 10,
  "iterations_per_interview": 4
}
```

### 4.2 Combinación vectorial (contrastive)
Qdrant usa una sola query vectorial por búsqueda. Propuesta estable y simple:
- $v_+ = \text{avg}(\text{embed}(p_i))$
- $v_- = \text{avg}(\text{embed}(n_j))$ (si hay negativos)
- $v_t = \text{embed}(target)$ (si hay target)

Vector final:
$$
 v = \text{normalize}(w_+ v_+ - w_- v_- + w_t v_t)
$$

Valores iniciales sugeridos:
- `w_plus = 1.0`
- `w_minus = 0.6`
- `w_target = 0.8`

Notas:
- Si no hay negativos, usar `AUTO_NEGATIVES` como “negativos suaves” (o `w_minus=0`).
- Si no hay target, `w_target=0`.

### 4.3 Refinamientos por iteración
Mantener la idea actual de patrones por iteración, pero que el refinamiento opere sobre:
- target_text (si existe) y/o
- “query textual efectiva” (para logging y memo), mientras la búsqueda vectorial se basa en la combinación anterior.

Ejemplo:
- iter0: base (positivos/negativos/target)
- iter1: target + “contexto comunitario”
- iter2: target + “evidencia concreta”

---

## 5) Criterios de aceptación

### A. Consumo real del triplete
- Dado un usuario que llena Positivos, Negativos y Target en `DiscoveryPanel`, cuando ejecuta Runner v2, entonces:
  - el backend registra en `discovery_runs` (o log equivalente) los `positivos`, `negativos` y `target_text` usados,
  - el informe `reports/runner/<project>/...` muestra esos parámetros.

### B. Compatibilidad con Runner MVP
- Si el usuario ejecuta Runner sin negativos/target, el flujo funciona como hoy:
  - no hay errores
  - se generan runs
  - se genera post-run e inserta candidatos

### C. Trazabilidad mínima
- Cada iteración del runner persiste:
  - `query` (texto humano)
  - `positivos`, `negativos`
  - `top_fragments` (IDs/preview)
  - `landing_rate` / `overlap`
- Para v2, además:
  - `target_text` y `config` (pesos y modo) quedan accesibles en DB o log.

### D. Post-run coherente con el triplete
- La síntesis y códigos sugeridos (`_analyze_fragments_with_llm`) incluyen en su prompt:
  - negativos reales (si existen)
  - target real (si existe)

### E. UX explícita
- El UI deja claro que Runner v2 usa el triplete (no “ignora Negativos/Target”).

---

## 6) Plan de implementación (orden sugerido)

1) Backend API (compatibilidad)
   - Extender `AgentExecuteRequest` para aceptar `negative_concepts` y `target_text`.
   - Propagar a `_run_agent_task`.

2) DiscoveryRunner v2 (cálculo vectorial)
   - Implementar combinación `v = normalize(w+v+ - w-v- + wt*vt)`.
   - Mantener modo v1 intacto.

3) Persistencia
   - Añadir columnas opcionales a `discovery_runs` (target_text/config/vector_mode) o persistir por memo/log con `discovery_navigation_log`.

4) Frontend
   - Actualizar llamada a `/api/agent/execute` para enviar negativos/target.
   - Ajustar tooltip y panel de estado.

5) Reporte y auditoría
   - Incluir parámetros v2 en `_write_runner_report`.
   - (Opcional) linkear reportes con un `runner_run_id` reutilizable.

---

## 7) Fuera de alcance (por ahora)
- Re-ranking multi-vector (buscar con v+, penalizar con v- post hoc por score) con calibración formal.
- Evaluación automática robusta (dataset + métricas offline) más allá de landing_rate.
- UI avanzada para ajustar pesos (w+/w-/wt) por usuario; se deja como “feature flag” posterior.
- Persistencia de embeddings de conceptos/targets en cache (optimización).
