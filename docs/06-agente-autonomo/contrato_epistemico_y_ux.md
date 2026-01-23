# Contrato epistémico + guía UX (APP_Jupter)

> **Propósito**: no “alinear al investigador a la app”, sino **diseñar una UX/UI competitiva** que sea coherente con diversidad epistemológica/metodológica en investigación cualitativa y que aproveche tecnologías nuevas (LLM + vectores + grafo + agentes) sin colapsar el rigor.

Este documento traduce **epistemología / teoría / método** en **invariantes de producto** y **requisitos UX**. Se integra con el marco del Agente Autónomo en `docs/06-agente-autonomo/README.md`.

---

## 1) Punto de partida: pluralismo de usuarios (no hay “un solo esquema mental”)

En cualitativa aplicada, la app debe soportar al menos estas posturas (a veces convivientes dentro de un mismo equipo):

- **GT clásica / comparativo constante**: códigos emergen de incidentes; comparación sistemática; memos; saturación.
- **Descriptivo/temático pragmático**: códigos como etiquetas operativas; foco en cobertura y reporting.
- **Abductivo/teoría informada**: mezcla de sensitizing concepts y emergencia; iteración hipótesis ↔ evidencia.
- **Evaluación/consultoría (defendibilidad)**: trazabilidad y evidencia “de auditoría” como requisito de entrega.

**Implicancia UX**: el sistema debe explicitar el “contrato” de qué es *dato*, qué es *hipótesis* y qué es *resultado defendible*.

---

## 2) Contrato epistémico: 3 niveles de afirmación

### Nivel A — Dato (incidente)
- Unidad: **fragmento** (texto original con ID estable, metadatos, contexto).
- Requisito: el fragmento debe ser recuperable y citables sin ambigüedad.

### Nivel B — Hipótesis (propuesta)
- Unidad: **código sugerido** (por humano o IA), siempre acompañado de:
  - 1+ **citas/evidencias** (IDs de fragmentos)
  - **origen** (humano/LLM/discovery/runner)
  - **estado** (provisional/validado/rechazado/fusionado)
  - **memo** (razón)

### Nivel C — Resultado defendible
- Unidad: **código consolidado** + distribución de citas + (opcional) relaciones axiales.
- Requisito: auditable: “cómo llegamos aquí” debe reconstruirse con evidencias y decisiones.

**Implicancia UX**: no basta con “mostrar códigos”; hay que mostrar **estatus** y **evidencia mínima**.

---

## 3) Qué aporta cada tecnología (sin sobreprometer)

### PostgreSQL (fuente de verdad)
- Función epistémica: **ledger** de fragmentos, citas, decisiones, estados.
- UX: es lo que sostiene “auditabilidad” de producto.

### Qdrant (memoria semántica)
- Función epistémica: **proponer comparaciones** (encontrar incidentes afines), no dictar verdad.
- UX: acelera comparación constante, muestreo teórico, densificación.

### Neo4j (memoria topológica)
- Función epistémica: **explicabilidad estructural** (categorías↔códigos↔evidencias; comunidades/centralidad).
- Rol de verdad: **proyección derivada y mutable** (vista analítica). Puede recalcularse/reconstruirse desde PostgreSQL; no reemplaza al ledger.
- UX: soporta “micro-teoría del caso” y luego comparativo entre casos.

### LLM (motor abductivo)
- Función epistémica: sugiere hipótesis y memos; **no valida** por sí mismo.
- UX: debe estar “domesticado” por reglas de evidencia y límites de inferencia.

### Agente (orquestación)
- Función epistémica: automatiza loops (discovery→síntesis→candidatos) con observabilidad.
- UX: debe operar como “asistente disciplinado”, no como autor incuestionable.

---

## 4) Reglas metodológicas convertidas en invariantes de producto

### Invariante 0 — Resolución canónica obligatoria (anti-contaminación)
Toda operación que escriba o consuma códigos “con efectos” (promoción, axial, GDS/algoritmos, sincronización a grafo) debe pasar por el **resolver canónico**:
- Si un código está `merged` (o apunta a un canónico), se utiliza el **canónico**.
- Los nodos/relaciones de códigos `merged` no deben entrar a proyecciones/algoritmos (evitar duplicidad y sesgo en centralidad/comunidades).

Implicancia: PostgreSQL sostiene el estado ontológico; Neo4j materializa la vista (y puede rehacerse).

### Invariante 1 — Nada sin evidencia
Cualquier código sugerido debe incluir 1–3 fragmentos evidenciales o quedar marcado como “sin evidencia” y no ser promovible.

### Invariante 2 — Separación clara: por entrevista vs entre entrevistas
- **Modo Caso (E3)**: el default es trabajar dentro de la entrevista activa.
- **Modo Comparativo (E4)**: comparación explícita entre entrevistas, con trazabilidad de qué se comparó.

### Invariante 3 — Estado explícito (provisionalidad)
El sistema debe tratar “asignación” como **acto provisional** hasta validación (o definir otro gate explícito, pero debe existir uno).

### Invariante 4 — Registro de operaciones analíticas
Búsquedas, refinamientos y comparaciones deben dejar rastro (qué se buscó, con qué filtros, qué salió).

### Invariante 5 — Reproducibilidad razonable
En outputs del agente (runner), si el input es estable, el output debe ser estable (determinismo donde sea posible).

---

## 5) Requisitos UX/UI accionables (sin imponer una sola escuela)

### A) Señales de “estatus epistémico” (siempre visibles)
- Para códigos: **origen + estado + evidencia**.
- Para relaciones: **tipo + evidencia + memo**.

### B) Controles de “alcance” (scope) con defaults seguros
- En E3, sugerencias semánticas deberían default a **entrevista activa**, con opción explícita a expandir a “todas”.
- En E4, la comparación debe mostrar “qué entrevistas entran” y por qué.

### C) Observabilidad del agente (estilo Devin, sin misticismo)
- Mostrar: qué iteración va, qué consulta ejecutó, qué decidió enviar a bandeja, y métricas de diversidad/overlap.
- Mostrar fallos: servicios caídos, timeouts, pools agotados.

### D) Flujos de cierre (quality gates)
- Validar / fusionar / promover no es burocracia: es el mecanismo metodológico de cierre.
- UX debe hacer ese cierre **rápido** (batch), con evidencia a la vista.

---

## 6) Discovery como “modelo de referencia” (patrón a replicar y mejorar)

Hoy, **Discovery** es el ejemplo más completo de “loop disciplinado” en la app: combina recuperación semántica (Qdrant), trazabilidad (PostgreSQL) y una síntesis (LLM) que produce artefactos accionables. Por eso debe ser el **modelo a seguir** para el resto de la experiencia (especialmente E3), no como feature aislada.

### 6.1 Qué hace a Discovery un buen modelo
- **Artefactos**: siempre deja rastro (log + memo/síntesis + acción). No es “chat”; es navegación analítica.
- **Separación rol-verdad**: Qdrant propone; PostgreSQL registra; humano valida.
- **Gates explícitos**: lo propuesto termina en bandeja/candidatos y requiere validación.
- **Observabilidad**: permite métricas y lectura crítica del resultado (ej. landing rate; diversidad de evidencia en runner).

### 6.2 Patrón “Discovery-first” (aplicable a E3)
Definición operativa del patrón:
1) **Ancla** (dato): fragmento(s) con `fragmento_id` estable.
2) **Recuperación** (propuesta): Qdrant devuelve vecinos (con filtros de scope).
3) **Síntesis** (hipótesis): LLM propone (códigos/memo/decisiones) *solo sobre la evidencia recuperada*.
4) **Persistencia de hipótesis**: inserción en `codigos_candidatos` (estado `pendiente`) con 1–3 evidencias.
5) **Gate humano**: validar/rechazar/fusionar; y sólo luego promover a definitivo.
6) **Rastro**: cada paso queda trazado (qué se buscó, por qué, qué se propuso, qué se aceptó).

### 6.3 Adaptación paso a paso para Codificación Abierta (E3) con PostgreSQL + Qdrant

**Paso 1 — Declarar el alcance por defecto (modo Caso)**
- E3 debe partir en **entrevista activa**: el scope default para Qdrant es `project_id + archivo` (o `interview_id` si existe).
- Expandir a “todas las entrevistas del proyecto” debe ser una acción explícita (y registrada).

**Paso 2 — Definir el evento analítico mínimo (y loguearlo como Discovery)**
- En E3, el evento mínimo es: “tomé este fragmento como incidente y busqué comparables”.
- Ese evento debe registrarse igual que Discovery (estructura equivalente a `discovery_navigation_log`): query/semilla, filtros, resultados top-k, refinamientos y acción tomada.

**Paso 3 — Unificar el output: siempre candidatos con evidencia (no ‘código suelto’)**
- Cualquier sugerencia de E3 (humana o IA) debe terminar como fila en `codigos_candidatos` con:
  - `codigo`, `fragmento_id`, `archivo`, `fuente_origen`, `memo`, y **1–3 evidencias**.
- Si el usuario asigna un código manualmente, sigue siendo una hipótesis (candidato) hasta validación; el “acto definitivo” es la promoción.

**Paso 4 — Mejorar la calidad del muestreo y la diversidad de evidencia (heredando lo ya hecho en Runner)**
- Reutilizar el enfoque de “muestra representativa” y métricas de diversidad/overlap para evitar que E3 se convierta en eco de los mismos fragmentos.
- Interpretación UX: mostrar rápidamente si la evidencia está “colapsando” (repetición alta) antes de validar en batch.

**Paso 5 — Integrar ‘comparación constante’ como navegación, no como pantalla extra**
- E3 no necesita “otra feature”: necesita que cada búsqueda/sugerencia deje rastro y que el usuario pueda volver atrás y ver:
  - qué comparó,
  - qué decidió,
  - qué quedó pendiente.

**Paso 6 — Definir el cierre de E3 en términos de producto**
- “Cerrar E3” no es “tener muchos códigos”; es:
  - candidatos validados con evidencia,
  - tasa de repetición controlada,
  - y (si aplica) primeras agrupaciones/memos de caso.

### 6.4 Luego Neo4j (no antes): de hipótesis validadas a estructura explicable

Neo4j debe entrar **después** de E3, cuando ya existe suficiente material validado (o al menos un subconjunto) para evitar que el grafo formalice ruido.

**Regla de oro**: Neo4j materializa **relaciones** (topología/axialidad) sólo cuando hay:
- `codigo` consolidado (idealmente promovido a definitivo), y
- evidencia citada (IDs de fragmentos) para cada relación.

**Regla de higiene**: antes de escribir o proyectar, resolver siempre el **código canónico** y excluir códigos `merged` de análisis/algoritmos.

Aplicación práctica:
- E3 (modo Caso) → construir “micro-grafo del caso” (código ↔ fragmento ↔ memo) sin inferencias fuertes.
- E4 (comparativo) → recién aquí permitir aristas entre entrevistas/códigos, con evidencia cruzada y trazabilidad.

---

## 7) Lectura crítica de tu esquema (como “familia de workflows”)

Tu secuencia por entrevista + “micro-teoría del caso” es una **variante válida** (case-based GT/abductiva) si:
- E3 se mantiene como modo caso por defecto.
- La axial por entrevista se trata como **provisional** (micro-teoría) y se diferencia de E4 comparativa.

El punto clave no es que la app “imponga” eso, sino que la UX:
- permita trabajar así, y
- haga visible cuándo se está en modo caso vs comparativo.

---

## 8) Criterios de éxito (producto competitivo)

- **Auditabilidad**: un tercero puede seguir evidencia→código→decisión.
- **Rigor asistido**: el sistema acelera sin ocultar el método.
- **Pluralismo**: diferentes estilos de investigación pueden usarlo sin sentirlo “forzado”.
- **Eficiencia**: loops (discovery/coding) y gates (validar/promover) con fricción mínima.

---

## 9) Próximos documentos relacionados

- Evidencia en runner: `docs/06-agente-autonomo/analisis_algoritmo_link_codes_to_fragments.md`
- Auditoría de Discovery: `docs/06-agente-autonomo/auditoria_calidad_discovery.md`
- Ejemplo de informe: `docs/06-agente-autonomo/informe_runner_avance_jd009.md`

### Roadmap (identidad estable de conceptos)
Si el volumen de merges crece, considerar evolucionar de `codigo` (texto) a una identidad estable (`code_id`) y registrar merges como eventos:
- `code_id` (concepto), `canonical_code_id` (puntero), y `code_merge_events` (quién/cuándo/por qué).
- Mantener compatibilidad: el UI puede seguir mostrando `codigo` (label), mientras el backend resuelve por ID.
