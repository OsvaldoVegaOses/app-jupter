# Propuesta de cierre UX/UI como proceso de investigación (E2–E4)
**Fecha:** 2026-01-12  
**Estado:** Propuesta (para discusión)  
**Owner:** UX + Backend/Agente Autónomo

## 1) Intención
Cerrar UX/UI no solo como “operación” (botones que funcionan), sino como **proceso investigativo auditable**:
- cada acción deja rastro (qué se buscó, por qué, con qué alcance),
- toda hipótesis tiene evidencia (fragmentos),
- existe un gate explícito (validar/promover) que representa el cierre metodológico,
- el agente autónomo automatiza loops, pero **sin ocultar** decisiones.

Este documento complementa:
- [docs/06-agente-autonomo/contrato_epistemico_y_ux.md](../06-agente-autonomo/contrato_epistemico_y_ux.md)
- [docs/06-agente-autonomo/criterios_aceptacion_ux_e3_discovery_first.md](../06-agente-autonomo/criterios_aceptacion_ux_e3_discovery_first.md)
- [docs/05-calidad/auth_task_briefing_plus.md](./auth_task_briefing_plus.md)

---

## 2) Principios de cierre (producto = método)
1) **Scope por defecto seguro (Modo Caso):** acciones semánticas parten en entrevista activa; expandir a proyecto es explícito.
2) **Evidencia obligatoria:** nada “suelto” (código/hipótesis) sin 1–3 fragmentos ancla.
3) **Candidatos primero:** toda propuesta (humana/IA/Discovery/Runner) llega como candidato (`codigos_candidatos`).
4) **Gate humano:** validar/rechazar/fusionar y luego promover. El acto “promover” = cierre operativo.
5) **Auditabilidad:** se reconstruye “código → evidencia → decisión” desde UI y reportes.
6) **Observabilidad del agente:** mostrar iteración, query, decisiones, métricas anti-colapso.

---

## 3) Orden propuesto del flujo (UI) y qué “cierra” cada etapa
> Nota: la app tiene paneles; aquí proponemos un orden narrativo y de gates, no solo navegación.

### E2 — Familiarización (lectura + fragmentos)
**Objetivo:** entender material, preparar el terreno para codificar sin sesgo duro.
- Artefactos: selección de entrevistas, primeras notas.
- Gate sugerido: “lista mínima de entrevistas revisadas” (no bloqueante).

Ver detalle operativo en: [docs/05-calidad/aprendizaje_y_capacitacion.md](./aprendizaje_y_capacitacion.md)

### E2.5 — Briefing IA (Descripción de entrevista)
**Objetivo:** preámbulo con guardas éticas/metodológicas.
- Artefactos: briefing (borrador vs validado), anonimización contextual + checklist anti-sesgo.
- Gate sugerido: “Validado” exige checklist + anonimización (ver [docs/05-calidad/auth_task_briefing_plus.md](./auth_task_briefing_plus.md)).

### E3 — Codificación Abierta (núcleo del loop)
**Objetivo:** producir códigos iniciales con evidencia y control de alcance.
- Output principal: **candidatos + evidencia** → validar → promover → aparecen en `analisis_codigos_abiertos`.
- Gate real: validación/promoción (cierre metodológico y operativo).

Auditoría técnica y flujo guiado v1: [docs/05-calidad/auditoria_codificacion_abierta.md](./auditoria_codificacion_abierta.md)

### E3b — Discovery (Búsqueda Exploratoria) como “motor de comparación constante”
**Objetivo:** recuperar comparables y sostener muestreo teórico/refinamientos.
- Discovery no es “otra etapa aparte”: es el patrón a replicar en E3.
- Artefactos: navegación (log), memos, candidatos sugeridos.

### E4 — Axial/Relaciones (Neo4j después)
**Objetivo:** estructurar relaciones explicables a partir de material ya validado/promovido.
- Gate: relaciones tipadas con evidencia.

---

## 4) Discovery: UX propuesta (manual) — triplete Positivos/Negativos/Target
### 4.1 Qué significa el triplete
- **Positivos:** conceptos/indicadores que queremos atraer (uno por línea).
- **Negativos (opcional):** conceptos que queremos evitar (uno por línea).
- **Texto objetivo (opcional):** foco contextual para orientar la recuperación.

### 4.2 Comportamiento esperado (definición de producto)
- Entrada por líneas: `splitlines()` + `trim()` + eliminar vacíos.
- Resultados: `k` fragmentos con:
  - score,
  - archivo/entrevista,
  - fragmento_id,
  - preview,
  - acciones: “abrir”, “guardar memo”, “enviar a candidatos”.

### 4.3 Especificación mínima del ranking (contrastivo)
Modelo simple y suficiente para MVP:
- Embeddings:
  - $v_{pos} = mean(emb(pos_i))$
  - $v_{neg} = mean(emb(neg_j))$ si hay negativos
  - $v_{tgt} = emb(target)$ si hay target
- Query vector:
  - $q = normalize(v_{pos} - \lambda v_{neg} + \alpha v_{tgt})$
- Defaults sugeridos:
  - $\lambda = 0.35$ (penaliza negativos)
  - $\alpha = 0.25$ (orienta por target)

Además:
- scope por defecto: entrevista activa; expandir a proyecto completo explícitamente.

---

## 5) Runner: ¿antes o después de Codificación Abierta?
**Respuesta de diseño:** el Runner y E3 apuntan al mismo “objeto” (candidatos/códigos), pero cumplen roles distintos.

### 5.1 Regla recomendada
- **Runner (Discovery) debe ser un amplificador post‑E3 inicial**, no el punto de partida.

**Por qué:**
- Antes de tener codificación mínima, el Runner puede introducir sesgo de anclaje (la app “impone” temas demasiado pronto).
- Con algunos códigos ya promovidos, el Runner se convierte en herramienta de muestreo teórico y comparación constante:
  - encuentra contra‑evidencia,
  - explora variación,
  - sugiere nuevos candidatos con trazabilidad.

### 5.2 UX concreta (para evitar confusión)
- Discovery manual puede estar disponible desde post‑ingesta, pero:
  - el botón **🚀 Runner** muestra un aviso/estado: “Recomendado tras codificar al menos 1 entrevista” o “tras tener N códigos promovidos”.
  - el Runner trabaja sobre el mismo modelo: recuperación → síntesis → candidatos → validación.

### 5.3 Gap actual (importante)
Según [docs/06-agente-autonomo/README.md](../06-agente-autonomo/README.md), el Runner MVP:
- usa solo **Conceptos Positivos**,
- ignora Negativos y Target.

Propuesta de cierre:
- definir “Runner v2” que use el triplete completo y deje trazabilidad del ranking (incluyendo parámetros $\lambda,\alpha$).

---

## 6) Propuesta para el agente autónomo (módulos `app/` + `backend/routers/`)
### 6.1 Orquestación por estado (no por clicks)
- El agente debe leer estado del proyecto y sugerir el siguiente paso:
  - si no hay ingesta → ingestar
  - si no hay fragmentos → reparar/diagnóstico
  - si hay análisis sin persistencia → persistir
  - si hay candidatos pendientes → pedir validación (batch)
  - si hay validados → promover
  - si hay codificación mínima → habilitar Runner para muestreo teórico

### 6.2 “Cerrar UX” = cerrar el loop
- UI debe hacer explícito el loop:
  - **Proponer (candidato)** → **Validar** → **Promover** → **Aparece en E3**.
- Reportes deben incluir:
  - fuentes (llm/manual/discovery/runner),
  - evidencias, 
  - decisiones.

---

## 7) Próximos pasos (acción)
1) Alinear el texto UI de Discovery con esta definición (triplete + ranking contrastivo).
2) Definir gate UX para Runner: habilitación posterior a codificación mínima.
3) Implementar Runner v2 (usar Negativos + Target) y loguear parámetros.
4) Consolidar un “Mapa de Proceso” en el dashboard (modo caso vs modo comparativo).
