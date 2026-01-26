# Ejecución Local (Guía Actualizada)

Este documento explica cómo levantar el entorno completo (Full Stack) de la aplicación `APP_Jupter`, incluyendo la nueva arquitectura asíncrona con Celery y Redis.

## Prerrequisitos

1.  **Docker Desktop**: Necesario para la infraestructura (Redis, Neo4j, Postgres).
2.  **Python 3.12+**: Para el Backend y Workers.
3.  **Node.js 18+**: Para el Frontend.

---

## 🚀 Inicio Rápido (Scripts Automáticos)

Hemos creado scripts en la carpeta `scripts/` para automatizar el proceso en Windows. Sigue este orden:

### 1. Iniciar Infraestructura (Bases de Datos)
Abre una terminal en la raíz del proyecto y ejecuta:
```powershell
docker-compose up -d
```
> Esto levantará Redis (para colas), Neo4j (grafo) y Postgres (datos relacionales).

### 2. Iniciar Worker (Procesamiento Asíncrono)
El worker es necesario para procesar los análisis de fondo.
*   **Ejecuta**: `scripts/start_worker.bat`
*   Se abrirá una ventana mostrando logs de conexión a Redis.

### 3. Iniciar Backend (API)
*   **Ejecuta**: `scripts/start_backend.bat`
*   La API estará disponible en `http://localhost:8000`.
*   Swagger UI: `http://localhost:8000/docs`.

### 4. Iniciar Frontend (UI)
*   **Ejecuta**: `scripts/start_frontend.bat`
*   El navegador se abrirá en `http://localhost:5173`.

---

## Ejecución Manual (Paso a Paso)

Si prefieres no usar los scripts o estás en otro sistema operativo (Linux/Mac), sigue estos pasos:

### 1. Configuración de Entorno (.env)
Asegúrate de tener un archivo `.env` en la raíz con las credenciales necesarias. Para la arquitectura asíncrona, es **CRITICO** tener:
```bash
CELERY_BROKER_URL="redis://localhost:16379/0"
```

> [!IMPORTANT]
> En Windows (Hyper-V/WSL2) el proyecto usa **puerto externo 16379** para Redis.
> Para ejecución local desde el host, usa: `CELERY_BROKER_URL=redis://localhost:16379/0`.

### 2. Infraestructura
```bash
docker-compose up -d
```

### 3. Backend
Activa tu entorno virtual y corre Uvicorn:
```bash
# Windows
.\.venv\Scripts\activate
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000

# Linux/Mac
source .venv/bin/activate
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

### 4. Celery Worker
En una **nueva terminal** (con el venv activado), inicia el consumidor de tareas:
```bash
# Windows (Importante: --pool=solo)
celery -A backend.celery_worker worker --loglevel=info --pool=solo

# Linux/Mac
celery -A backend.celery_worker worker --loglevel=info
```

### 5. Frontend
```bash
cd frontend
npm install # Si es la primera vez
npm run dev
```

---

## Troubleshooting

*   **Error de conexión a Redis**: Verifica que el contenedor `redis-broker` esté corriendo con `docker ps`.
*   **Tareas en estado "Pending"**: Significa que el Worker no está corriendo o no está conectado al mismo Redis que la API. Revisa los logs de la ventana del worker.
*   **Frontend no conecta con Backend**: Verifica que `frontend/.env` apunte a `VITE_API_BASE=http://127.0.0.1:8000`.

---

## Nuevas Funcionalidades (Diciembre 2024)

### Dashboard de Salud del Sistema
El frontend incluye un panel colapsable "Estado del Sistema" que muestra el estado de PostgreSQL, Neo4j, Qdrant y Azure OpenAI.

### Indicador de Conexión Backend
En el header hay un indicador visual (🟢 Conectado) que verifica la disponibilidad del backend cada 30 segundos.

### Panel de Validación de Códigos
Nuevo panel para validar, rechazar y fusionar códigos candidatos propuestos desde Discovery y Sugerencias Semánticas.

### Script de Validación de Entorno
Ejecuta `scripts/validate_env.ps1` para verificar la configuración antes de iniciar.
