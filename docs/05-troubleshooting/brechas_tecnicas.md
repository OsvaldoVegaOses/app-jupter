# Análisis de Brechas Técnicas para Evolución de Negocio

## 1. Brechas Críticas (Must-Have)

### Backend (API)
*   **Regression en `api_analyze`**: El endpoint `/api/analyze` en `backend/app.py` (línea 800) **NO** ha sido actualizado para usar la nueva lógica "Pre-Hoc" de `app/analysis.py`.
    *   *Estado Actual*: `text_payload = "\n".join(fragments)` (Concatena todo).
    *   *Estado Deseado*: Pasar `fragments` (lista) directamente a `analyze_interview_text` para soportar la indexación `[IDX: n]`.
    *   *Impacto*: Si se usa la API web, se seguirán generando "ghost codes". Solo el CLI (`main.py`) está arreglado.

### Seguridad
*   **Autenticación Débil**: Actualmente usa una sola `API_KEY` compartida para todo el servidor.
    *   *Requerimiento*: Implementar OAuth2/JWT para usuarios reales si se va a vender como SaaS.
*   **Autorización Nula**: No hay roles (RBAC). Cualquier usuario con la API Key puede borrar proyectos o ingerir documentos.

## 2. Brechas de Producto (Should-Have)

### Frontend (UX)
*   **Visualización de Grafos limitada**: La API retorna JSON de grafos (`"graph": {...}`), pero el frontend necesita una librería robusta (e.g., `react-force-graph` o `cytoscape.js`) para visualizarlos interactivamente.
*   **Editor de Codificación**: No existe una UI para corrección manual de códigos ("Human-in-the-loop"). Si la IA se equivoca, el usuario debe poder editar el fragmento/código desde la web.

### Infraestructura
*   **Colas de Trabajo (Async)**: `ingest` y `analyze` son endpoints síncronos (bloqueantes) o pseudo-async. Para archivos grandes, esto causará Timeouts en HTTP. Se necesita una cola de tareas real (Celery/Redis o BullMQ).

## 3. Hoja de Ruta Inmediata (Quick Wins)

1.  **Corregir `backend/app.py`**: Alinear el endpoint de análisis con la refactorización reciente.
2.  **Dockerizar**: Asegurar que Backend y Frontend se levanten con `docker-compose` para despliegue fácil en clientes.
3.  **Demo Mode**: Crear un script "seed" que pueble la base de datos con un proyecto de demostración para clientes potenciales.
