# Sprint 9: GraphRAG, Discovery API & Link Prediction

> **Fecha:** Diciembre 2024  
> **Estado:** COMPLETADO  
> **Última actualización:** 15 Diciembre 2024

---

## Resumen de Implementación

| Feature | Archivos | Endpoints |
|---------|----------|-----------|
| **GraphRAG** | `app/graphrag.py` | `POST /api/graphrag/query`, `POST /api/graphrag/save_report` |
| **Discovery API** | `app/queries.py` | `POST /api/search/discover`, `POST /api/discovery/save_memo` |
| **Link Prediction** | `app/link_prediction.py` | `GET /api/axial/predict`, `GET /api/axial/community-links` |
| **Relaciones Ocultas** | `app/link_prediction.py` | `GET /api/axial/hidden-relationships`, `POST /api/axial/confirm-relationship` |

---

## 1. GraphRAG (app/graphrag.py)

Consultas LLM con contexto de grafo Neo4j. Combina búsqueda semántica (Qdrant) + estructura del grafo (Neo4j) + LLM para respuestas contextualizadas.

### Funciones
- `extract_relevant_subgraph()`: Extrae nodos y relaciones relevantes del grafo
- `format_subgraph_for_prompt()`: Formatea el subgrafo para inyección en el prompt del LLM
- `graphrag_query()`: Consulta completa con contexto de grafo
- `graphrag_chain_of_thought()`: Razonamiento paso a paso (análisis profundo)

### Modos de Consulta

| Modo | Profundidad | Descripción |
|------|-------------|-------------|
| **Normal** | depth=2 | Consultas directas, respuestas concisas |
| **Chain of Thought** | depth=3 | Análisis paso a paso con 5 secciones explícitas |

### Chain of Thought (CoT)
Cuando se activa, el LLM responde con este formato estructurado:

```markdown
## PASO 1: ANÁLISIS DEL GRAFO
[Descripción de nodos y relaciones relevantes]

## PASO 2: IDENTIFICACIÓN DE RELACIONES CAUSALES
[Conexiones causales entre códigos/categorías]

## PASO 3: SÍNTESIS INTERPRETATIVA
[Respuesta basada en evidencia]

## PASO 4: CITAS DE RESPALDO
[Referencias a fragmentos [1], [2], etc.]

## CONCLUSIÓN
[Respuesta final breve]
```

### Guardar Reportes
Los resultados de GraphRAG pueden guardarse como archivos Markdown:

- **Endpoint:** `POST /api/graphrag/save_report`
- **Ubicación:** `reports/{proyecto}/YYYY-MM-DD_HH-MM_{query_slug}.md`
- **Contenido:** Pregunta, respuesta, contexto del grafo, fragmentos de evidencia

### Uso (API)
```bash
# Consulta normal
curl -X POST http://localhost:8000/api/graphrag/query \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Que causa la inseguridad?",
    "project": "default",
    "include_fragments": true,
    "chain_of_thought": false
  }'

# Con Chain of Thought
curl -X POST http://localhost:8000/api/graphrag/query \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Como influye la participacion ciudadana?",
    "project": "default",
    "chain_of_thought": true
  }'

# Guardar reporte
curl -X POST http://localhost:8000/api/graphrag/save_report \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "...",
    "answer": "...",
    "context": "...",
    "fragments": [...],
    "project": "default"
  }'
```

### Uso (Frontend)
1. Navegar a la sección **GraphRAG**
2. Escribir la pregunta en el campo de texto
3. Opcionalmente activar **"Razonamiento paso a paso"**
4. Presionar **"Preguntar"**
5. Revisar la respuesta y contexto
6. Presionar **"💾 Guardar Informe"** para persistir

---

## 2. Discovery API (app/queries.py)

Búsqueda exploratoria con triplete positivo/negativo/target. Usa Qdrant para navegación semántica ponderada.

### Algoritmo
1. Genera embeddings para conceptos positivos → promedia
2. Genera embeddings para conceptos negativos → resta 30% de influencia
3. Opcionalmente combina con texto objetivo (70% query + 30% target)
4. Busca en Qdrant con el vector resultante

### Funciones
- `discover_search()`: Busca fragmentos similares a X, diferentes de Y

### Guardar Memos
Los resultados pueden guardarse para documentar el proceso exploratorio:

- **Endpoint:** `POST /api/discovery/save_memo`
- **Ubicación:** `notes/{proyecto}/YYYY-MM-DD_HH-MM_discovery_{concepto}.md`
- **Contenido:** Criterios de búsqueda + fragmentos encontrados con scores

### Uso (API)
```bash
# Búsqueda exploratoria
curl -X POST http://localhost:8000/api/search/discover \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "positive_texts": ["participacion ciudadana", "organizacion comunitaria"],
    "negative_texts": ["conflicto violento"],
    "target_text": "seguridad barrial",
    "top_k": 10,
    "project": "default"
  }'

# Guardar memo
curl -X POST http://localhost:8000/api/discovery/save_memo \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "positive_texts": ["participacion ciudadana"],
    "negative_texts": ["violencia"],
    "fragments": [...],
    "project": "default",
    "memo_title": "Exploración de participación"
  }'
```

### Uso (Frontend)
1. Navegar a la sección **Discovery**
2. Ingresar conceptos positivos (uno por línea)
3. Opcionalmente agregar conceptos negativos y texto objetivo
4. Presionar **"Buscar"**
5. Revisar fragmentos encontrados
6. Opción A: **"💾 Guardar Memo"** - Guarda toda la exploración
7. Opción B: **"📝 Enviar a Coding"** (por fragmento) - Envía al panel de codificación

### Ejemplos de Uso
| Escenario | Positivos | Negativos | Resultado |
|-----------|-----------|-----------|-----------|
| Participación pacífica | participacion, comunidad | violencia, protesta | Fragmentos sobre colaboración |
| Inseguridad urbana | inseguridad, miedo | rural | Fragmentos urbanos |
| Liderazgo positivo | líder, organización | corrupción | Ejemplos positivos |

---

## 3. Link Prediction (app/link_prediction.py)

Predicción de relaciones faltantes en el grafo axial.

### Algoritmos
| Algoritmo | Descripción | Mejor para |
|-----------|-------------|------------|
| `common_neighbors` | Vecinos compartidos | Densidad local |
| `jaccard` | Coeficiente de similitud | Normalizado por tamaño |
| `adamic_adar` | Vecinos ponderados por rareza | Conexiones únicas |
| `preferential_attachment` | Producto de grados | Nodos populares |

### Funciones
- `suggest_links()`: Sugerencias generales entre nodos
- `suggest_axial_relations()`: Para categoría específica
- `detect_missing_links_by_community()`: Basado en comunidades Louvain

### Uso
```bash
# Predicción general
curl "http://localhost:8000/api/axial/predict?algorithm=jaccard&top_k=10&project=default"

# Por categoría
curl "http://localhost:8000/api/axial/predict?categoria=Participacion&algorithm=common_neighbors"

# Por comunidad
curl "http://localhost:8000/api/axial/community-links?project=default"
```

---

## 4. Relaciones Ocultas (app/link_prediction.py)

Descubre relaciones latentes que no son obvias a simple vista.

### Métodos de Descubrimiento

| Método | Icono | Descripción | Confianza |
|--------|-------|-------------|-----------|
| **Co-ocurrencia** | 🔗 | Códigos que aparecen juntos en fragmentos pero no están relacionados | Alta |
| **Categoría Compartida** | 📂 | Códigos que pertenecen a la misma categoría pero no tienen relación directa | Media |
| **Comunidad** | 🏘️ | Códigos en la misma comunidad Louvain pero desconectados | Baja |

### Funciones
- `discover_hidden_relationships()`: Combina los 3 métodos
- `confirm_hidden_relationship()`: Confirma y persiste una relación descubierta

### Uso (API)
```bash
# Descubrir relaciones ocultas
curl "http://localhost:8000/api/axial/hidden-relationships?project=default&top_k=20"

# Confirmar una relación
curl -X POST http://localhost:8000/api/axial/confirm-relationship \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "Codigo_A",
    "target": "Codigo_B",
    "relation_type": "causa",
    "project": "default"
  }'
```

### Uso (Frontend)
1. Navega a la sección **Relaciones Ocultas**
2. Presiona **"Descubrir Relaciones"**
3. Revisa las sugerencias con su nivel de confianza
4. Confirma las relaciones válidas seleccionando el tipo (partede, causa, condicion, consecuencia)

### Marcador en Neo4j
Las relaciones confirmadas desde este módulo tienen `origen: 'descubierta'`:
```cypher
MATCH ()-[r:REL]->()
WHERE r.origen = 'descubierta'
RETURN r
```

---

## Estructura de Directorios

```
/
├── reports/                    # Reportes GraphRAG guardados
│   └── {proyecto}/
│       └── YYYY-MM-DD_query.md
├── notes/                      # Memos de Discovery
│   └── {proyecto}/
│       └── YYYY-MM-DD_discovery.md
└── app/
    ├── graphrag.py            # Lógica GraphRAG
    ├── queries.py             # Discovery + búsqueda híbrida
    └── link_prediction.py     # Predicción de enlaces
```

---

## Verificación

```bash
# Verificar imports
python -c "from app.graphrag import graphrag_query, graphrag_chain_of_thought; print('GraphRAG OK')"
python -c "from app.queries import discover_search; print('Discovery OK')"
python -c "from app.link_prediction import suggest_links; print('LinkPred OK')"

# Verificar endpoints
curl -s http://localhost:8000/health | grep -q ok && echo "API OK"
```

---

## Notas de Implementación

### Compatibilidad con GPT-5/O1
- **temperature:** Se omite (modelos de razonamiento usan valor fijo 1.0)
- **max_tokens:** Se usa `max_completion_tokens` en lugar de `max_tokens`
- **CoT prompt:** Formato explícito con headers para forzar salida visible

### Discovery Fallback
- El API `discover()` de Qdrant tiene variaciones entre versiones
- Se usa `query_points()` con vector ponderado como fallback robusto

---

*Implementado: 13 Diciembre 2024*  
*Actualizado: 15 Diciembre 2024 (persistencia de reportes y memos)*
