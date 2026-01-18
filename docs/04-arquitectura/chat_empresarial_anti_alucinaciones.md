# Complemento a valor_negocio.md: Chat empresarial anti‑alucinaciones (Grounded Chat)

**Fecha:** 2025-12-24  
**Repositorio/Workspace:** APP_Jupter  
**Documento complementario:** docs/04-arquitectura/valor_negocio.md  
**Objetivo:** definir cómo convertir la app en una base sólida para un **chat empresarial** que minimice alucinaciones mediante **respuestas con evidencia**, **rechazo seguro** y **evaluación continua**.

---

## 1) Definición operativa: “resolver alucinaciones”

En un chat empresarial, “resolver alucinaciones” no significa 0% invenciones en todo escenario, sino:

- **Grounding obligatorio:** toda afirmación relevante debe estar sustentada por **evidencia recuperada** del corpus.
- **Rechazo seguro (“no sé”):** si el sistema no recupera evidencia suficiente, responde: *“No encuentro soporte en el corpus disponible”* y propone pasos siguientes (preguntas aclaratorias o búsqueda alternativa).
- **Trazabilidad:** cada respuesta debe incluir referencias a fragmentos (p. ej. `archivo`, `par_idx`, `fragmento_id`).
- **Evaluación:** el sistema mantiene métricas que permitan demostrar que la alucinación bajó (y detectar regresiones).

---

## 2) Estado base: qué ya habilita APP_Jupter

APP_Jupter ya tiene piezas clave para un chat grounded:

- **Recuperación semántica + BM25** (Qdrant + Postgres) para recall y precisión.
- **Contexto de grafo (GraphRAG)** (Neo4j) para relaciones y organización conceptual.
- **Trazabilidad por fragmentos** (IDs, `archivo`, `par_idx`, payloads) para evidencias citables.
- **Persistencia de reportes/memos** para auditoría (útil en entorno empresarial).

Lo que falta no es “más IA”, sino **gates**, **contratos de respuesta**, **seguridad RAG** y **validación**.

---

## 3) Arquitectura “anti‑alucinaciones” (MVP)

### 3.1 Flujo recomendado (3 capas)

1) **Retrieval (evidencia):**
   - Recuperar top‑k fragmentos con filtros por proyecto/tenant (obligatorio).
   - Combinar señales: vector + BM25 + (opcional) señales de grafo.

2) **Synthesis (respuesta):**
   - Generar respuesta *solo* usando los fragmentos recuperados.
   - Producir un bloque “Evidencia” con referencias exactas.

3) **Verification (verificación ligera):**
   - Verificar automáticamente que la respuesta:
     - incluye evidencias,
     - no afirma cosas fuera de las citas,
     - respeta el formato y políticas.
   - Si falla: reintentar con prompt más estricto o devolver rechazo seguro.

### 3.2 “Contrato de respuesta” (formato empresarial)

Toda respuesta debe salir con esta estructura:

- **Respuesta (breve):** 3–8 líneas.
- **Evidencia:** lista de fragmentos (mínimo 2 cuando sea posible):
  - `archivo`, `par_idx`, `fragmento_id`, extracto corto.
- **Confianza / Limitaciones:**
  - “Alta / Media / Baja” (derivada de señales: score, consistencia, cobertura).
  - Qué falta para responder mejor.

Regla crítica: **si no hay evidencia, no hay afirmación**.

---

## 4) Gates (reglas de decisión) para evitar inventar

### 4.1 Gate de evidencia mínima

Antes de responder afirmativamente:

- Debe existir al menos un conjunto de fragmentos con:
  - top‑1 score ≥ umbral, y/o
  - top‑k con coherencia (no contradicción obvia), y
  - diversidad mínima (no todos del mismo fragmento duplicado).

Si no se cumple → **rechazo seguro** o **preguntas aclaratorias**.

### 4.2 Gate de “respuesta citada”

- Cada afirmación sustantiva (dato, causa, política, recomendación) debe mapear a al menos 1 evidencia.
- Si el verificador detecta frases sin soporte → reintento o rechazo.

### 4.3 Gate de alcance

- Si la pregunta pide información fuera del corpus (“¿cuánto costó X?” sin documento), el sistema debe declarar el límite.

---

## 5) Estrategias concretas contra alucinaciones

### 5.1 Recuperación robusta

- **Híbrida:** vector + BM25 (ya existe) con filtros por proyecto.
- **K mayor en retrieval que en respuesta:** recuperar más, sintetizar con menos (p. ej. recuperar 20–30, citar 3–6).
- **Normalización de duplicados:** deduplicar fragmentos muy similares.

### 5.2 Prompting con restricciones (sin sobre‑prometer)

- Instrucción central: “Usa solo la evidencia proporcionada. Si no hay evidencia, di que no sabes.”
- Prohibir “relleno”: nada de suposiciones.

### 5.3 Verificación automática

- Chequeo de “citas presentes” + “menciones apoyadas”:
  - Heurístico simple (palabras clave), o
  - segundo paso LLM tipo “validator” que solo devuelve PASS/FAIL + razón.

### 5.4 Persistencia de trazas

- Guardar:
  - pregunta,
  - lista de evidencias recuperadas,
  - respuesta final,
  - scores,
  - resultado del verificador.

Esto permite auditoría y evaluación real.

---

## 6) Métricas (para demostrar mejora)

Mínimo recomendado:

- **grounded_precision (muestreo humano):** % respuestas cuyas afirmaciones están soportadas por evidencia citada.
- **hallucination_rate (muestreo humano):** % respuestas con afirmaciones no soportadas.
- **answerable_rate:** % preguntas donde el sistema encuentra evidencia suficiente.
- **refusal_correctness:** % rechazos correctos (rechaza cuando debe) vs falsos rechazos.
- **latencia p95** por etapa: retrieval, síntesis, verificación.

---

## 7) Dataset de evaluación (práctico y rápido)

Construir un set de 50–100 queries con etiquetas:

- **Answerable:** la respuesta existe en el corpus.
- **Unanswerable:** no existe.
- **Adversarial:** intento de prompt injection (“ignora documentos, inventa…”).

Para cada query, registrar expectativa:
- “Debe responder con evidencia” o “Debe rechazar”.

---

## 8) Riesgos y condiciones de éxito

### 8.1 Riesgos

- **Cross‑project leakage:** si el aislamiento por `project_id` no es total, un chat “enterprise” es inviable.
- **Evidencia débil:** corpus con fragmentación pobre o metadatos incompletos sube rechazos.
- **Costo/latencia:** verificación LLM agrega costo; mitigable con heurísticos + muestreo.

### 8.2 Condiciones de éxito (MVP)

- Respuestas siempre incluyen evidencia o rechazan.
- Métricas muestran reducción estable de alucinación en el dataset.
- Se puede auditar: “por qué respondió esto”.

---

## 9) Plan mínimo (2 sprints) para “chat grounded”

**Sprint 1 (gates + formato):**
- Contrato de respuesta con sección “Evidencia”.
- Gate de evidencia mínima + rechazo seguro.
- Logging de evidencias/scores/respuesta.

**Sprint 2 (verificación + evaluación):**
- Verificador (heurístico o LLM) con PASS/FAIL.
- Dataset de evaluación + reporte de métricas.
- Regresión: alertar si `hallucination_rate` sube.

---

## 10) Criterio Go/No‑Go (enfocado en alucinaciones)

- **Go (MVP empresarial):** grounded_precision ≥ 90% en muestreo; hallucination_rate ≤ 5%; refusal_correctness ≥ 85%.
- **No‑Go:** si hay cualquier evidencia de leakage cross‑proyecto o si no se puede producir evidencia citada de forma consistente.
