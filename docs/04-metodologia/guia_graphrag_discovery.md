# Guía de Usuario: GraphRAG, Discovery y Relaciones Ocultas

> **Versión:** 1.1  
> **Última actualización:** 15 Diciembre 2024

---

## Introducción

Este documento explica cómo utilizar las funcionalidades de **GraphRAG**, **Discovery** y **Relaciones Ocultas** para potenciar tu investigación cualitativa.

---

## 🧠 GraphRAG - Chat con Contexto de Grafo

### ¿Qué es?
GraphRAG combina tres tecnologías para responder preguntas de investigación:
1. **Qdrant** - Encuentra fragmentos de texto relevantes
2. **Neo4j** - Agrega contexto de relaciones entre códigos
3. **LLM** - Genera respuestas interpretativas

### ¿Cuándo usarlo?
- Preguntas sobre **significados** asignados por entrevistados
- Exploración de **relaciones causales** entre conceptos
- Síntesis de **patrones** a través de múltiples entrevistas

### Cómo usar

1. **Navega a GraphRAG** en el menú lateral
2. **Escribe tu pregunta** en el campo de texto
   - Ejemplo: *"¿Qué significado le asignan los entrevistados a la participación ciudadana?"*
3. **Activa "Razonamiento paso a paso"** si quieres un análisis profundo
4. **Presiona "Preguntar"**
5. **Revisa la respuesta** que incluye:
   - Respuesta principal
   - Contexto del grafo (nodos y relaciones)
   - Fragmentos de evidencia citados
6. **Guarda el informe** presionando "💾 Guardar Informe" si quieres conservarlo

### Modos de Consulta

| Modo | Cuándo usarlo |
|------|---------------|
| **Normal** | Preguntas directas, respuestas concisas |
| **Chain of Thought** | Análisis profundo con razonamiento visible |

### Ejemplos de preguntas efectivas

| ✅ Buena pregunta | ❌ Pregunta vaga |
|-------------------|------------------|
| ¿Qué factores causan la inseguridad según los entrevistados? | ¿Qué dicen? |
| ¿Cómo se relaciona la participación ciudadana con la confianza institucional? | Háblame de participación |
| ¿Qué consecuencias tiene la falta de liderazgo comunitario? | ¿Qué pasa con los líderes? |

### Dónde se guardan los informes
Los informes se guardan en:
```
reports/{tu_proyecto}/YYYY-MM-DD_HH-MM_{pregunta}.md
```

---

## 🔍 Discovery - Búsqueda Exploratoria

### ¿Qué es?
Discovery te permite navegar semánticamente por tus datos usando la lógica:
- **Quiero fragmentos similares a X** (conceptos positivos)
- **Pero diferentes de Y** (conceptos negativos)
- **Cerca de Z** (texto objetivo opcional)

### ¿Cuándo usarlo?
- **Descubrimiento** de fragmentos que no habrías buscado directamente
- **Contraste** entre conceptos opuestos
- **Inspiración** para nuevos códigos
- **Validación** de hipótesis emergentes

### Cómo usar

1. **Navega a Discovery** en el menú lateral
2. **Ingresa conceptos positivos** (uno por línea)
   - Ejemplo: `participación ciudadana`
3. **Opcionalmente agrega conceptos negativos**
   - Ejemplo: `violencia`
4. **Opcionalmente agrega texto objetivo**
   - Ejemplo: `seguridad barrial`
5. **Selecciona número de resultados** (1-50)
6. **Presiona "Buscar"**
7. **Revisa los fragmentos** encontrados
8. **Acciones disponibles:**
   - **"💾 Guardar Memo"** - Guarda toda la exploración
   - **"📝 Enviar a Coding"** - Envía un fragmento al panel de codificación

### Ejemplos de búsquedas

| Objetivo | Positivos | Negativos | Resultado esperado |
|----------|-----------|-----------|-------------------|
| Participación pacífica | participación ciudadana, organización comunitaria | violencia, protesta | Fragmentos sobre colaboración vecinal |
| Problemas urbanos | inseguridad, delincuencia | rural | Problemas específicos de ciudad |
| Liderazgo positivo | líder, dirigente, organización | corrupción, clientelismo | Ejemplos de buen liderazgo |
| Confianza institucional | gobierno, municipio | desconfianza, crítica | Percepciones positivas |

### Dónde se guardan los memos
Los memos se guardan en:
```
notes/{tu_proyecto}/YYYY-MM-DD_HH-MM_discovery_{concepto}.md
```

---

## 🔮 Relaciones Ocultas - Descubrimiento de Conexiones Latentes

### ¿Qué es?
Relaciones Ocultas analiza tu grafo para encontrar **conexiones que no son obvias a simple vista**. Son relaciones que probablemente existen pero que no has documentado explícitamente.

### ¿Cuándo usarlo?
- Después de codificar varias entrevistas
- Cuando quieras **validar** que no te has perdido conexiones importantes
- Para **descubrir** patrones emergentes entre códigos
- Como paso previo a la **saturación teórica**

### Métodos de Descubrimiento

| Icono | Método | Descripción | Confianza |
|-------|--------|-------------|-----------|
| 🔗 | **Co-ocurrencia** | Códigos que aparecen juntos en los mismos fragmentos pero no están relacionados | ⭐ Alta |
| 📂 | **Categoría Compartida** | Códigos bajo la misma categoría pero sin relación directa entre ellos | ● Media |
| 🏘️ | **Comunidad** | Códigos en la misma comunidad temática (Louvain) pero desconectados | ○ Baja |

### Cómo usar

1. **Navega a Relaciones Ocultas** en el menú lateral
2. **Presiona "Descubrir Relaciones"**
3. **Revisa las sugerencias** organizadas por confianza:
   - ⭐ **Alta**: Muy probable que exista la relación
   - ● **Media**: Posible relación, requiere validación
   - ○ **Baja**: Sugerencia tentativa
4. **Para cada sugerencia**, decide si es válida
5. **Confirma** seleccionando el tipo de relación:
   - `partede` - El código es parte de/pertenece a
   - `causa` - El código causa/origina
   - `condicion` - El código depende de/requiere
   - `consecuencia` - El código es resultado de

### Ejemplo de uso

```
Descubrimiento: "Desconfianza Institucional" ↔ "Participación Baja"
Razón: co-ocurrencia en fragmentos (aparecen juntos 5 veces)
Confianza: Alta

→ Confirmas como: "causa"
   (La desconfianza causa baja participación)
```

### Consultar relaciones descubiertas en Neo4j
```cypher
MATCH (a)-[r:REL]->(b)
WHERE r.origen = 'descubierta'
RETURN a.nombre, r.tipo, b.nombre, r.confirmado_en
ORDER BY r.confirmado_en DESC
```

---

## Flujo de Trabajo Recomendado

```
┌─────────────────────┐
│   1. DISCOVERY      │ Explorar y descubrir fragmentos
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   2. CODING         │ Asignar códigos a fragmentos relevantes
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   3. NEO4J          │ Visualizar relaciones entre códigos
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   4. REL. OCULTAS   │ Descubrir conexiones no obvias    ← NUEVO
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   5. GRAPHRAG       │ Hacer preguntas interpretativas
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   6. REPORTS        │ Guardar y documentar hallazgos
└─────────────────────┘
```

---

## Preguntas Frecuentes

### ¿Por qué Discovery no encuentra resultados?
- Verifica que tienes documentos ingestados en el proyecto seleccionado
- Intenta con conceptos más generales
- Reduce los conceptos negativos

### ¿Por qué GraphRAG no responde con Chain of Thought?
- Algunos modelos (GPT-5/O1) tienen comportamiento diferente
- El prompt está optimizado para forzar salida estructurada
- Si persiste, intenta reformular la pregunta

### ¿Puedo usar Discovery y GraphRAG juntos?
Sí, es el flujo recomendado:
1. Usa Discovery para encontrar fragmentos interesantes
2. Codifica los más relevantes
3. Usa GraphRAG para interpretar patrones

### ¿Los memos y reportes se sincronizan con el grafo?
No directamente. Son documentos de reflexión del investigador (memorandos analíticos en Grounded Theory). El grafo se actualiza mediante Coding.

### ¿Cuándo debo usar Relaciones Ocultas?
- Después de codificar al menos 3-4 entrevistas
- Cuando el grafo tenga suficientes nodos para detectar patrones
- Como validación antes de declarar saturación teórica

### ¿Qué pasa si confirmo una relación incorrecta?
Puedes eliminarla directamente en Neo4j Browser:
```cypher
MATCH (a {nombre: 'Codigo_A'})-[r:REL]->(b {nombre: 'Codigo_B'})
WHERE r.origen = 'descubierta'
DELETE r
```

---

## Atajos y Tips

| Tip | Descripción |
|-----|-------------|
| Usa múltiples positivos | Combinar 2-3 conceptos relacionados mejora la precisión |
| Negativos como filtros | Los negativos son útiles para excluir temas no deseados |
| CoT para causalidad | Activa Chain of Thought para preguntas "¿por qué?" o "¿cómo influye?" |
| Guarda frecuentemente | Los memos documentan tu proceso reflexivo |
| Relaciones ocultas iterativas | Ejecuta el descubrimiento después de cada sesión de codificación |

---

*Documento creado: 15 Diciembre 2024*  
*Actualizado: 15 Diciembre 2024 (añadido Relaciones Ocultas)*
