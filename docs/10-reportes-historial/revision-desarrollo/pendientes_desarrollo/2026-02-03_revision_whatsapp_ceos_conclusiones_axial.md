# Revisión — Hilo WhatsApp (CEOs Startup) y conclusiones para Axial

**Fecha de elaboración:** 2026-02-03  
**Fuente:** conversación en grupo de WhatsApp (CEOs / founders) compartida por Osvaldo (29/01/2026 → 01/02/2026).

---

## 1) Resumen ejecutivo (lo que realmente se validó)

- El dolor dominante no es “velocidad/costo”: es **confianza** (subjetividad, sesgo, auditabilidad, trazabilidad).
- La promesa “IA + grafos” genera interés, pero el **grafo como output principal** no está validado: un decisor lo percibe como **ruidoso, poco legible y poco accionable**.
- La comparación competitiva aparece explícita: **“esto compite con un LLM”** para análisis de texto a escala; por lo tanto, Axial debe ganar por **trazabilidad, reproducibilidad, cobertura y control de calidad**, no solo por “resumir”.

---

## 2) Hilo del chat (secuencia y señales)

### 2.1 Mensaje de apertura (29/01)
- Problema declarado: análisis cualitativo como “caja negra” (lento/caro/subjetivo/difícil de auditar).
- Solución (Axial): IA + grafos que convierten fragmentos en un mapa visual trazable; evidencia estructural en horas.

### 2.2 Encuesta de dolor
- Pregunta: al decidir el futuro de un proyecto con 500+ entrevistas, ¿qué duele más?
  - costo/tiempo
  - subjetividad
  - riesgo legal/trazabilidad
  - inacción

### 2.3 Resultado (31/01)
- **Subjetividad ~80%** vence a costo/tiempo.
- Señal: el mercado (al menos este grupo) prioriza **rigor y confianza** por sobre “barato/rápido”.

### 2.4 Solicitud de evidencia
- Un CEO pide: **“¿Tienes ejemplos de visualizaciones?”**
- Señal: antes de creer la tesis, quieren **ver el output** y entender si ayuda a decidir.

### 2.5 Demo compartida (01/02)
- Se comparte una vista tipo Observation / Interpretation / Hypothesis con mención a subgrafo, densidad, códigos.

### 2.6 Feedback crítico
- “Disclaimer: muestra tamaño 1” (señala poca evidencia del demo).
- “Yo no usaría el grafo… no me aporta para tomar decisiones.”
- Sugiere alternativa: **heatmap** si el vocabulario/códigos es más acotado.
- Problemas de UX/semántica:
  - no se entiende qué nodos son conceptos vs documentos
  - exceso de nodos llamados “fragmento”
  - demasiada data / estructura no ayuda
- Competencia: “si no hago estadística, compite con un LLM para texto masivo; difícil de batir”.

---

## 3) Conclusiones para el producto (Axial)

### 3.1 “Job to be done” (JTBD) real
- **Tomar decisiones con evidencia verificable**, reduciendo sesgo del analista y aumentando auditabilidad.

### 3.2 Riesgo principal observado
- Si el grafo es el “centro del producto”, puede percibirse como:
  - complejidad añadida
  - poca “decisionalidad” (no traduce en acción)
  - baja legibilidad (sin semántica visual clara)

### 3.3 Ventaja competitiva vs LLM (debe ser explícita)
Axial debe diferenciarse en:
- **Trazabilidad**: cada conclusión con citas y ruta a fragmentos.
- **Cobertura**: qué % del corpus soporta el hallazgo; qué quedó fuera.
- **Reproducibilidad**: mismo input → mismo output (o controlado/explicable).
- **Control de calidad**: contradicciones, outliers, muletillas/ruido, sesgos, lagunas.

---

## 4) Implicaciones de UX y “output packaging”

### 4.1 Cambiar el “hero output”
**Recomendación:** convertir el “primer pantallazo” en un **Decision Brief** (1 página) y dejar el grafo como vista secundaria de auditoría.

Decision Brief debería incluir:
- Top 5 hallazgos (accionables) + “por qué importa”.
- Evidencia cuantificada: frecuencia, cobertura, segmentación (si aplica).
- Citas trazables (fragmentos) + link a contexto.
- Contra-evidencia: fragmentos que contradicen o matizan.
- Nivel de confianza y notas de sesgo/lagunas.

### 4.2 Si se mantiene grafo: requisitos mínimos de legibilidad
- Tipos de nodos explícitos (Documento / Entrevista / Código / Fragmento) con **colores/formas fijas** y **leyenda persistente**.
- Evitar nodos genéricos “fragmento” sin contexto:
  - label con 6–10 palabras del fragmento
  - tooltip con cita completa
  - metadatos (entrevista, timestamp, participante)
- Controles de reducción:
  - colapsar fragmentos por código
  - filtros por comunidad/tema
  - mostrar solo relaciones fuertes / top-k

### 4.3 Vistas alternativas pedidas indirectamente
- **Heatmap**: códigos × entrevistas/segmentos.
- Ranking de temas por cobertura.
- Matriz de co-ocurrencia de códigos (más “decision-friendly” que un grafo denso).

---

## 5) Mensaje comercial (ajuste recomendado)

### 5.1 Propuesta de valor en 1 frase
- “Axial convierte entrevistas en **decisiones auditables**: cada insight trae su prueba y su cobertura.”

### 5.2 Qué NO vender primero
- “Grafos” como protagonista (a menos que el público sea técnico/analítico).

### 5.3 Cómo responder a la objeción “compite con LLM”
- “Un LLM resume; Axial **demuestra**: cobertura, trazabilidad, reproducibilidad y control de calidad del análisis.”

---

## 6) Experimentos y próximos pasos (pendientes de desarrollo)

### 6.1 Experimentos de demo
- A/B demo: (A) grafo primero vs (B) Decision Brief primero.
- Medir: tiempo a primer insight, comprensión de nodos, confianza, intención de uso.

### 6.2 Cambios de producto priorizados
1) Decision Brief como vista principal.
2) Semántica visual del grafo (tipos/leyenda/filtros).
3) Heatmap + matriz co-ocurrencia.
4) Módulo “Evidencia y cobertura” (si no existe ya): porcentaje del corpus y contra-evidencia.

### 6.3 “Criterio de éxito” sugerido
- Un CEO debe poder:
  - entender la pantalla en < 10s
  - extraer 3 decisiones/acciones en < 2 min
  - auditar 1 insight hasta el fragmento original en < 30s

---

## 7) Notas
- El feedback crítico se emitió con “muestra tamaño 1”; aun así, es valioso porque identifica fricciones típicas de adopción.
- El hilo también muestra una necesidad transversal en founders: comunicación simple, canales, y feedback honesto. Axial debe reflejar esa claridad en su output.
