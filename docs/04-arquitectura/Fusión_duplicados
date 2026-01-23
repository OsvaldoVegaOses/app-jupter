Documento de Contexto: Función de Fusión y Consolidación de Códigos
Funcionalidad: Fusión de Códigos (Code Merge) y Gestión de Duplicados. Módulo: Gestión del Codebook / Validación Humana. Objetivo: Transición de listas planas de etiquetas a entidades de grafo consolidadas.

**Documento técnico asociado (API + capa de datos):**
- Ver: [docs/04-arquitectura/fusion_duplicados_api_spec.md](docs/04-arquitectura/fusion_duplicados_api_spec.md)

1. Visión General y Definición
La "Fusión de Códigos" no es una operación administrativa de limpieza o borrado de datos. Se define como una operación de gobernanza del Codebook que permite consolidar múltiples variaciones léxicas (sinónimos, plurales, errores tipográficos) en una única Entidad Canónica.

Esta función es el mecanismo crítico para garantizar la integridad metodológica del análisis cualitativo, transformando la "proliferación de etiquetas" en "densidad teórica" apta para el modelado en grafos.

2. Propósito de la Funcionalidad
La función atiende a tres necesidades fundamentales del sistema:

A. Higiene de Datos y Reducción de Entropía
(Fuente: sprint26_save_memo_duplicate_automation.md)

Problema: La generación automática y manual produce ruido (ej. "escasez agua", "escasez de agua", "falta agua").

Solución: Automatizar la detección de estas redundancias para evitar que diluyan el análisis. El sistema debe operar bajo el principio de Unicidad Conceptual: un concepto = un nodo.

B. Normalización y Usabilidad (UX)
Problema: La revisión manual de cientos de casi-duplicados genera una alta carga cognitiva y fatiga en el investigador.

Solución: El sistema propone fusiones automáticas basadas en heurísticas (ej. "preferir el descriptor más corto" o "el más frecuente") para establecer un estándar canónico, reduciendo la fricción en la toma de decisiones.

C. Preparación Topológica para el Grafo
Problema: Los algoritmos de grafos (GDS) fragmentan su cálculo si la red está dispersa en sinónimos.

Solución: La fusión densifica la topología. Al transferir las relaciones (aristas) de los duplicados al nodo maestro, se habilita el cálculo correcto de métricas de centralidad (PageRank) y detección de comunidades (Louvain).

3. Diseño del Flujo Operativo (Workflow)
La funcionalidad se implementa siguiendo el ciclo de vida Merge-Validate-Promote, asegurando que ninguna fusión sea una "caja negra" sin supervisión.

Paso 1: Merge (Consolidación Algorítmica)
El sistema identifica candidatos similares (vía distancia de Levenshtein o embeddings semánticos) y propone una agrupación hacia un Código Destino.

Nota de Implementación: Se debe operar sobre el dataset completo precargado en memoria, evitando bugs de inconsistencia por paginación visual (ej. detectar duplicados que no están visibles en la página 1 de la tabla).

Paso 2: Validate (Confirmación Humana)
El investigador revisa la propuesta en la "Bandeja de Validación".

Acción: Ratificar que Variante A y Variante B son semánticamente equivalentes al Código Destino.

Feedback: Posibilidad de rechazar la fusión si la similitud es léxica pero no semántica (falsos positivos).

Paso 3: Promote (Persistencia y Trazabilidad)
Una vez validada, la fusión se ejecuta en la base de datos:

El Código Destino se promueve a la lista definitiva (nodo activo en Neo4j).

Los códigos fusionados NO SE ELIMINAN físicamente; cambian su estado a FUSIONADO (o MERGED) y guardan una referencia fusionado_a (destino de fusión). Esto garantiza la auditabilidad forense del proceso.

Nota de alineación (implementación actual):
- En PostgreSQL, `fusionado_a` existe hoy como **TEXT** en `codigos_candidatos` y en la práctica almacena el **nombre/código canónico destino** (string).
- Si se requiere estrictamente “ID del destino” (integridad referencial dura), la recomendación es evolucionar el modelo agregando un `fusionado_a_id` (FK) y mantener `fusionado_a` como snapshot textual para auditoría.

Endpoints de referencia (implementación actual):
- `POST /api/codes/candidates/merge` (fusión manual por IDs)
- `POST /api/codes/candidates/auto-merge` (fusión masiva por pares source/target)

4. Fundamentación Metodológica (Grounded Theory)
Desde una perspectiva epistemológica, esta función digitaliza el método de Comparación Constante de Strauss & Corbin:

Control de la Saturación Teórica: Evita la inflación artificial de métricas. La saturación real solo se observa cuando las variantes se agrupan, revelando que "no emergen nuevos conceptos", sino solo nuevos nombres para lo mismo.

Validación de Categorías: Permite que las categorías emerjan por densidad de evidencia. Un código con 50 fragmentos vinculados (tras la fusión) tiene más peso teórico que 50 códigos con 1 fragmento cada uno.

Trazabilidad Científica: Al no borrar los duplicados, el sistema permite volver atrás y auditar decisiones interpretativas ("¿Por qué consideramos que X era igual a Y?"), manteniendo el rigor científico.



