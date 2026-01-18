# Plan Estratégico de Mejora y Corrección Técnica (v3.0)

Este documento actualiza la hoja de ruta tras la implementación del **Motor Cognitivo** (Sprints 5 y 6), transformando la plataforma en un sistema de investigación activo.

## 1. Estado Actual y Logros
Se han completado los hitos críticos de las Fases 1 a 6:

### Arquitectura Base (Fases 1-3)
-   **Backend Asíncrono**: Implementado con Celery y Redis.
-   **Visualización de Grafos**: Componente `Neo4jExplorer`.
-   **Seguridad**: Híbrida (JWT + API Key).

### Excelencia Operacional (Fase 4)
-   ✅ **Persistencia de Logs**: Implementado `structlog` con rotación diaria.
-   ✅ **Seguridad de Tipos**: Generación automática de clientes TypeScript desde OpenAPI.

### Motor Cognitivo (Fases 5-6) - ¡NUEVO!
-   ✅ **Grafo Vivo (Neo4j GDS)**: Implementación de algoritmos de **PageRank** y **Louvain** persistentes. El sistema ahora calcula automáticamente la influencia de los nodos y detecta comunidades temáticas.
-   ✅ **GraphRAG**: El análisis con LLM ahora recibe contexto global del grafo ("Temas centrales", "Comunidades") antes de procesar nuevos textos.
-   ✅ **Descubrimiento Semántico (Qdrant)**:
    -   API de Descubrimiento (`/api/search/discover`) para búsquedas trianguladas (+Positivo, -Negativo).
    -   Sugerencias de Código (`/api/coding/suggestions`) basadas en similitud vectorial.

---

## 2. Hoja de Ruta Actualizada (Fase 7: Experiencia de Usuario & Escalado)

### Hito 7.1: Adopción del Motor Cognitivo
- [ ] **Interfaz de Descubrimiento**: Crear una UI en el frontend para usar la barra de búsqueda avanzada (Positivo/Negativo).
- [ ] **Panel de Sugerencias**: Integrar las sugerencias de código directamente en el modal de codificación manual.

### Hito 7.2: Optimización y Tiempo Real
- [ ] **WebSockets**: Reemplazar el "Polling" en `AnalysisPanel` por conexiones WebSocket para recibir actualizaciones de progreso en tiempo real.
- [ ] **Docker Multi-Stage**: Optimizar imágenes de Docker para reducir tamaño.

---

## 3. Conclusión
La aplicación ha trascendido su propósito inicial de "repositorio". Ahora actúa como un **Co-Investigador Inteligente**:
1.  **Entiende Estructura**: Sabe qué temas son importantes (Centralidad).
2.  **Entiende Contexto**: Agrupa hallazgos en comunidades.
3.  **Entiende Matices**: Permite buscar por significado abstracto.
4.  **Ayuda Proactivamente**: Sugiere códigos para evitar duplicidad.
