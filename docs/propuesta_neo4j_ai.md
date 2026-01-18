# Propuesta: Potenciando el Explorador Neo4j con IA (Integrada)

Esta propuesta refina el enfoque original para **aprovechar y extender** las capacidades ya existentes en la plataforma (específicamente *Link Prediction* y *GraphRAG*), minimizando el desarrollo de "rueda nueva" y maximizando la coherencia metodológica.

## Principios de Diseño
1.  **No reinventar**: Reutilizar el panel de GraphRAG y los badges de "Estatus Epistemológico" de Link Prediction.
2.  **Contextualizar**: La IA no debe ser un agente externo, sino una herramienta que "ve" lo que el usuario ve en el grafo.
3.  **Proactividad**: Pasar de "explorar datos" a "recibir propuestas de intervención".

## Constraints (límites) y seguridad (MVP)

Para sostener el valor empresarial (auditabilidad, estabilidad, y anti-alucinaciones), estas capacidades deben nacer con límites explícitos.

### Límites de vista/subgrafo

- **Máximo de nodos/relaciones** (por request): definir un tope (p. ej. `max_nodes=300`, `max_relationships=600`).
- **Timeouts** (backend): definir timeouts para extracción del subgrafo y para análisis LLM.
- **Fallback si la vista es grande**:
    - Muestrear por importancia (p. ej. top-k por centralidad) o por vecindad acotada (k-hops) en lugar de enviar toda la vista.
    - Ofrecer modo “resumen” (solo comunidades + hubs + puentes) y modo “detallado” (bajo demanda).

### Aislamiento por proyecto y alcance

- Toda operación debe ejecutar con **filtro duro por `project_id`** (y `owner_id`/tenant según corresponda).
- El modo **"Contexto: Vista Actual"** es un **scope estricto**: la IA solo puede razonar con los nodos/relaciones visibles (y su evidencia asociada), no con el grafo completo.

### Guardrails para Text-to-Cypher

- **Solo lectura** por defecto (bloquear `CREATE`, `MERGE`, `DELETE`, `SET`, `CALL dbms.*`, `apoc.*` si aplica).
- **Validación previa**: construir Cypher + ejecutar `EXPLAIN` (o validación equivalente) y rechazar si:
    - no incluye filtros de proyecto,
    - no incluye `LIMIT`,
    - supera un umbral de complejidad.
- **Sanitización**: evitar interpolación directa; usar parámetros.
- **Resultados acotados**: limitar filas, nodos devueltos y propiedades incluidas.

---

## 1. 🔮 Interpretación Visual Estructurada (Extensión)

El usuario ya cuenta con un análisis IA estructurado en el panel de "Predicción de Enlaces". Llevaremos ese mismo rigor al **Explorador Visual**.

*   **Funcionalidad**: Botón **"✨ Interpretar Vista"** en el Explorador Neo4j.
*   **Comportamiento**:
    *   Captura los nodos y relaciones actualmente visibles por el usuario (filtrados por zoom o query).
    *   Envía este subgrafo al backend.
    *   **Reutilización**: Usa el mismo contrato JSON que `/api/axial/analyze-predictions` (`OBSERVATION`, `INTERPRETATION`, `HYPOTHESIS`, `NORMATIVE_INFERENCE`).
*   **UI**:
    *   Muestra el resultado usando los mismos componentes de badges de colores que `LinkPredictionPanel`.
    *   **Interacción**: Al hacer clic en una `[OBSERVATION]`, se iluminan en el grafo los nodos que la sustentan.

### Contrato de evidencia para “iluminar nodos”

Para que el highlight sea auditable (y no “mágico”), el análisis debe devolver un mapeo explícito de evidencia.

- Cada item de análisis (por ejemplo una `OBSERVATION`) debe incluir un campo que permita “anclar” a entidades del grafo.
- La unidad mínima sugerida:
  - `node_ids`: IDs internos o IDs estables de nodos visibles.
  - `relationship_ids`: IDs internos o IDs estables de relaciones visibles.
  - `evidence_map`: mapa desde `analysis_item_id` → `{ node_ids: [...], relationship_ids: [...] }`.

## 2. 🔌 Chat GraphRAG Contextual (Integración)

*   **Situación Actual**: Existe un `GraphRAGPanel` en la sección "Codificación Selectiva" que permite preguntas libres.
*   **Mejora Propuesta**: Integrar este panel (o un acceso directo) dentro del `Neo4jExplorer`.
*   **Nueva Capacidad "Scope"**:
    *   Añadir un modo **"Contexto: Vista Actual"**.
    *   Al preguntar "¿Qué relación tienen estos actores?", el sistema inyecta automáticamente los IDs de los nodos visibles como filtro estricto para la respuesta.
    *   Esto reduce alucinaciones y permite un análisis focalizado en sub-grafos específicos (ej. comunidades aisladas).

## 3. 💡 Generador de Propuestas (Foco en Normative Inference)

Aprovechando la categoría `NORMATIVE_INFERENCE` (Inferencia Normativa) que ya maneja el modelo mental del usuario:

*   **Objetivo**: Transformar el análisis en acción.
*   **Flujo**:
    1.  Usuario visualiza "Nudos Críticos" o "Brechas Estructurales".
    2.  Solicita IA centrada en **Intervención**.
    3.  El prompt del sistema prioriza la generación de *Inferencias Normativas*: "Dado que X e Y no se conectan (Observación), se recomienda establecer una mesa de trabajo (Propuesta)".
*   **Salida**: Opción para guardar estas propuestas directamente como "Memos de Proyecto" o "Tareas".

### “Guardar como tareas” (definición mínima)

Para evitar ambigüedad, “Tareas” debe tener un scope y persistencia definidos.

- **MVP recomendado**: persistir como “Memo” con tipo `TASK` (misma infraestructura de memos/reportes) y opcionalmente promover a entidad propia después.
- **Campos mínimos**:
    - `project_id`, `owner_id`/tenant
    - `title`, `description`
    - `status` (p. ej. `open|in_progress|done`)
    - `source` (p. ej. `neo4j_explorer_ai`)
    - `evidence_refs` (node_ids/relationship_ids y/o fragment IDs)

## 4. 🪄 Magic Queries (Text-to-Cypher)

*   **Objetivo**: Democratizar el acceso a consultas complejas del grafo.
*   **Funcionalidad**: Input de texto natural ("Mostrar actores centrales desconectados entre sí") -> Traducción automática a Cypher.
*   **Valor**: Permite a investigadores no técnicos navegar el grafo con la potencia de un ingeniero de datos.

> Nota de seguridad: este feature debe operar con filtros de proyecto, límites estrictos y modo read-only por defecto.

---

## Plan de Implementación (Fases)

### Fase 1: Unificación de Componentes (Frontend)
*   Extraer `EpistemicBadge` y `MemoViewer` de `LinkPredictionPanel.tsx` a `components/common/Analysis`.
*   Hacer que `GraphRAGPanel` acepte `contextNodeIds` como prop opcional.

### Fase 2: Backend Endpoints
*   Crear `/api/neo4j/analyze`: Clon de lógica de `analyze-predictions` pero aceptando lista de nodos/relaciones arbitraria.
*   Actualizar `/api/graphrag/query`: Soportar filtrado por lista de IDs (`node_ids`).

#### Payload sugerido: `/api/neo4j/analyze`

Request (ejemplo):

```json
{
    "project_id": "...",
    "node_ids": ["..."],
    "relationship_ids": ["..."],
    "max_nodes": 300,
    "max_relationships": 600,
    "timeout_ms": 8000
}
```

Response (ejemplo):

```json
{
    "items": [
        {
            "id": "obs_1",
            "type": "OBSERVATION",
            "text": "...",
            "evidence": {
                "node_ids": ["..."],
                "relationship_ids": ["..."]
            }
        }
    ],
    "limits": {
        "max_nodes": 300,
        "max_relationships": 600,
        "applied_sampling": true
    }
}
```

### Fase 3: Integración en Explorer
*   Añadir barra de herramientas IA en `Neo4jExplorer`.
*   Conectar botones a los nuevos endpoints reutilizados.

¿Procedemos con la **Fase 1** (Refactorización de UI para reutilización)?
