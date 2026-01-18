# Guía de Despliegue: Arquitectura Asíncrona (Celery + Redis)

Para utilizar la funcionalidad de análisis asíncrono (background tasks), se deben cumplir las siguientes **3 condiciones obligatorias**:

## 1. Infraestructura: Servicio Redis
Debe existir una instancia de Redis ejecutándose y accesible desde el backend.
*   **Local**: Instalar Redis (`apt-get install redis` o `brew install redis`) y ejecutar `redis-server`.
*   **Docker (Recomendado)**:
    ```bash
    docker run -d -p 6379:6379 --name redis-broker redis:alpine
    ```

## 2. Configuración: Variable de Entorno
El backend necesita saber dónde conectar. Definir en `.env`:
```bash
CELERY_BROKER_URL=redis://localhost:6379/0
```
*(Si usas docker-compose, el hostname será el nombre del servicio, ej: `redis://redis-broker:6379/0`)*

## 3. Ejecución: Proceso Worker
La API (`backend/app.py`) **solo encola** las tareas. Se requiere un **segundo proceso** dedicado a ejecutarlas (consumirlas).

Activar el entorno virtual y correr:
```bash
# Windows
.\.venv\Scripts\celery -A backend.celery_worker worker --loglevel=info --pool=solo

# Linux/Mac
celery -A backend.celery_worker worker --loglevel=info
```
> **Nota**: En Windows es crucial usar `--pool=solo` para evitar problemas con `multiprocessing`.

---

### Verificación
1. Iniciar Redis.
2. Iniciar Worker (`celery ...`).
3. Iniciar API (`uvicorn backend.app:app ...`).
4. Enviar request a `/api/analyze`.
5. Deberías ver logs en la consola del **Worker** indicando `task.analyze.start`.
