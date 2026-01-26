# Valor de negocio (Interoperabilidad CAQDAS)

## Usuario objetivo
- Academia y centros de estudio con tooling CAQDAS existente
- Consultoras que necesitan entregar artefactos interoperables

## Promesa
Reducir fricción: permitir que equipos adopten APP_Jupter sin perder compatibilidad con su ecosistema actual.

## Diferenciador
Exports con trazabilidad y QA (no solo “dump” de datos).

## Oportunidad: IA + análisis en resultados de búsqueda
Incorporar IA y analítica “in situ” en la tabla de resultados (por ejemplo: “fragmento semilla”, “fragmentos similares”, score de similitud coseno, “Proponer” y “Codificar”) es viable y aporta valor directo porque transforma una lista de coincidencias en un flujo defendible de decisión (qué codificar, por qué, con qué evidencia).

## Viabilidad (alta)
- Ya existe la materia prima: embeddings + búsqueda semántica por similitud (score), fragmentos con metadatos (archivo/entrevista), y acciones de codificación/propuesta.
- La IA no tiene que “inventar” resultados: su rol puede ser explicar, priorizar, agrupar y resumir usando evidencia recuperada (grounding).
- La analítica requerida es incremental: contadores, cobertura, distribución de scores, y trazas por código/entrevista pueden calcularse con datos ya persistidos.

## Valor que aporta (por bloque del panel)
- 📝 Asignar código: sugerir 1–3 códigos candidatos con justificación basada en fragmentos similares; reduce sesgo de memoria y acelera codificación consistente.
- 🔍 Sugerencias semánticas: agrupar resultados por “tema probable”/cluster y mostrar “por qué aparece” (términos, evidencia, relación con semilla); baja carga cognitiva.
- 📊 Cobertura y avance: mostrar cobertura por código (n.º de fragmentos, entrevistas cubiertas, concentración por periodo/actor) y “huecos” (entrevistas sin evidencia); soporta saturación y planificación.
- 📎 Citas por código: extraer citas recomendadas (con contexto y referencia a fragmento_id/archivo) y preparar artefactos exportables a CAQDAS como memos/quotes con trazabilidad.
- 📁 Entrevista activa / Todas las entrevistas: comparar “perfil semántico” entre entrevistas (qué tan representado está un código/tema) y detectar outliers; acelera triangulación.
- “Fragmento semilla” / “Fragmentos similares”: añadir explicabilidad del ranking (por qué un score 0.64 aparece arriba) y recomendaciones de “siguiente mejor acción” (proponer vs codificar).
- 📊 Interpretación del score: convertir el umbral en reglas operativas (p.ej., “>0.85 casi duplicado”, “0.5–0.7 requiere lectura”), evitando decisiones automáticas.

## Encaje con interoperabilidad CAQDAS
- Exportar no solo datos, sino decisión + evidencia: “quote + código + memo/justificación + score + semilla” mapea mejor a flujos CAQDAS (auditable y reutilizable por equipos mixtos).
- Mejora adopción: usuarios CAQDAS reconocen el patrón de trabajo (quotes/codes/memos), pero con asistencia para consistencia y cobertura.

## Riesgos y mitigaciones (para mantener defendibilidad)
- Riesgo: alucinación o sobre-confianza → Mitigación: respuestas siempre ancladas a evidencia (fragmentos recuperados) y con opción de rechazo/edición por el analista.
- Riesgo: sesgo por umbrales de similitud → Mitigación: mostrar distribución de scores y permitir calibración por proyecto.
- Riesgo: ruido por “sugerencias” → Mitigación: limitar recomendaciones, registrar métricas de calidad (aceptación/rechazo) y mejorar con feedback.
