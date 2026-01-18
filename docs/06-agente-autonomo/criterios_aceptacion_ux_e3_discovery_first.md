# Criterios de aceptación UX — E3 (Codificación Abierta) con patrón Discovery-first

> **Objetivo**: convertir la sección “Discovery como modelo de referencia” en un backlog implementable.
> 
> Alcance: **Panel E3**, **Bandeja (candidatos)** y **Reportes**.

---

## A. Panel E3 (Codificación Abierta)

### 1) Alcance visible + default seguro (Modo Caso)
**Dado** que el usuario está trabajando en una entrevista/archivo activo, **cuando** el Panel E3 abre o se refresca, **entonces**:
- El scope por defecto para sugerencias semánticas y búsquedas debe ser **solo entrevista activa** (ej. `project_id + archivo`).
- El UI debe mostrar el scope actual en forma textual (p.ej. “Scope: Entrevista actual” vs “Scope: Todo el proyecto”).
- Cambiar a “Todo el proyecto” debe requerir una acción explícita del usuario.

**Criterio de verificación**: ejecutar una búsqueda en E3 y comprobar en el payload/log que incluye el filtro de scope por defecto.

### 2) Evento analítico mínimo: “incidente → comparables” (navegación, no chat)
**Dado** un fragmento seleccionado como incidente, **cuando** el usuario solicita “buscar comparables” o “sugerir códigos”, **entonces** el sistema debe:
- Registrar un evento analítico con:
  - `fragmento_id` semilla
  - query/seed usado
  - filtros aplicados (scope)
  - `top_k` y/o parámetros relevantes
  - timestamps
- Mostrar en el panel un resumen breve del evento (qué se buscó y con qué alcance).

**Criterio de verificación**: el evento existe en PostgreSQL como registro trazable (no solo en memoria del frontend).

### 3) Sugerencias siempre como hipótesis trazable (nada “suelto”)
**Dado** que el sistema propone códigos (por IA o por el usuario), **cuando** el usuario pulsa “Proponer” o equivalente, **entonces**:
- Cada código propuesto debe incluir **1–3 evidencias** (`fragmento_id`) asociadas.
- El UI debe mostrar esas evidencias (IDs) junto al código *antes* de enviar a bandeja.
- Si no hay evidencia disponible, el UI debe bloquear la acción de “enviar a bandeja” o marcar explícitamente “sin evidencia” y no permitir promoción.

**Criterio de verificación**: un código propuesto se ve con evidencias visibles y se persiste con evidencia.

### 4) Persistencia unificada: E3 escribe candidatos (gate humano explícito)
**Dado** que el usuario confirma una propuesta, **cuando** se envía a bandeja, **entonces** se persiste como fila en `codigos_candidatos` con:
- `project_id`, `codigo`, `fragmento_id` (ancla), `archivo`
- `fuente_origen` (ej. `manual`, `semantic_suggestion`, `llm`)
- `memo` (razón breve)
- `estado = 'pendiente'`

**Criterio de verificación**: el código aparece en la bandeja y no aparece como definitivo hasta promoción.

---

## B. Bandeja (códigos candidatos)

### 5) Operaciones batch con evidencia siempre visible
**Dado** que existen candidatos pendientes, **cuando** el usuario realiza acciones batch (validar / rechazar / fusionar), **entonces**:
- Cada fila debe mostrar (sin navegar a otra pantalla): `codigo`, `fragmento_id` (ancla) y evidencias (1–3).
- Acciones batch deben requerir confirmación mínima (para evitar clic accidental).
- La bandeja debe permitir ordenar/filtrar por `estado` y (opcional) `fuente_origen` sin perder el proyecto seleccionado.

**Criterio de verificación**: validar 10 candidatos en batch actualiza su estado y quedan listos para promoción.

### 6) Promoción a definitivo como acto separado (y reversible via rastro)
**Dado** un conjunto de candidatos `validado`, **cuando** el usuario pulsa “Promover a definitivo”, **entonces**:
- Se insertan en la tabla definitiva de codificación abierta (p.ej. `analisis_codigos_abiertos`).
- El UI debe reportar cuántos fueron promovidos y cuántos fueron omitidos (p.ej. por falta de `fragmento_id`).
- Debe quedar trazabilidad mínima del acto (quién/cuándo/lote).

**Criterio de verificación**: el mismo candidato no se promueve dos veces; la tabla definitiva refleja el cambio.

---

## C. Reportes (E3 / Runner)

### 7) Reporte de E3: auditable por diseño (no narrativo “plano”)
**Dado** que hay actividad E3 en un proyecto, **cuando** se genera un reporte de E3 (manual o automático), **entonces** el reporte debe incluir:
- Resumen de decisiones (qué códigos se propusieron, cuántos validados/rechazados/fusionados/promovidos).
- Para cada código sugerido/promovido: 1–3 evidencias (IDs) y su `fuente_origen`.
- Notas metodológicas explícitas: “esto es hipótesis hasta validación/promoción”.

**Criterio de verificación**: un tercero puede reconstruir “código → evidencia → decisión” desde el reporte.

### 8) Métricas anti-colapso de evidencia (calidad operativa)
**Dado** un conjunto de códigos sugeridos (E3 o Runner), **cuando** se genera el reporte o el output post-run, **entonces** debe incluir:
- Métricas de diversidad/overlap de evidencia (p.ej. cobertura y repetición de triples).
- Una interpretación breve (p.ej. “alto overlap → revisar muestreo/scope”).

**Criterio de verificación**: las métricas aparecen en el JSON/post-run y en el Markdown de reporte.

---

## Nota de implementación (para priorización)

Orden recomendado (MVP → robusto):
1) Scope default + persistencia unificada a `codigos_candidatos`.
2) Evidencia visible/obligatoria en propuestas.
3) Batch validation + promoción a definitivo.
4) Reporte auditable + métricas anti-colapso.
