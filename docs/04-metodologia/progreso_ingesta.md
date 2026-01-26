# Progreso de pruebas: creación de proyecto e ingesta

Fecha: 2025-11-21

Este documento registra los pasos ejecutados, comandos usados y resultados observados al crear proyectos y ejecutar la Etapa 1 (ingesta y normalización) del pipeline.

## 1) Contexto
- Repositorio: APP_Jupter
- Entorno: Windows (PowerShell), Python 3.12, Vite frontend
- Variables: `.env` en la raíz del repo (usado por `--env .env` cuando se invoca `main.py`)

## 2) Objetivos
1. Crear un proyecto con etiqueta `test_progre` sin usar la UI (CLI/API).
2. Verificar que el proyecto está registrado en `metadata/projects`.
3. Ejecutar la Etapa 1 — Ingesta y normalización — con entradas desde `data/interviews`.
4. Registrar logs, archivos creados y resultado de la ingesta.

## 2.1) Criterios de validación (epistemología + método)
Si necesitas tomar decisiones que sean **defendibles epistemológica y metodológicamente** (Teoría Fundamentada; contraste positivista vs constructivista/Charmaz), usa la matriz:

- `docs/02-metodologia/matriz_validacion_epistemologica_metodologica.md`

## 3) Pasos ejecutados

### 3.1 Crear proyecto vía CLI
Comando ejecutado desde la raíz del repo:

```powershell
python main.py --env .env project create --name "test_progre" --description "Proyecto de prueba progresivo" --json
```

Resultado (JSON devuelto):

```json
{
  "id": "test_progre",
  "name": "test_progre",
  "description": "Proyecto de prueba progresivo",
  "created_at": "2025-11-21T...Z"
}
```

Y el proyecto quedó registrado en `metadata/projects_registry.json`.

### 3.2 Crear proyecto vía API (simulación de la UI)
Se hizo una petición POST simulando el comportamiento del frontend hacia el endpoint `POST /api/projects` con `X-API-Key`.

Ejemplo (PowerShell):

```powershell
$body = @{ name='Proyecto desde Frontend'; description='Creado via API' } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/projects' -Method Post -Headers @{ 'X-API-Key'='dev-key' } -ContentType 'application/json' -Body $body
```

Resultado: proyecto `proyecto-desde-frontend` creado.

### 3.3 Verificación de archivos de estado
- `metadata/projects/<id>.json` se crean al registrar el proyecto; inicialmente contienen `{}` hasta que se persista un snapshot de estado.

### 3.4 Ejecutar Etapa 1 — Ingesta y normalización
Comando ejecutado (se usó `--env .env` y un run_id opcional provisto por el usuario):

```powershell
python main.py --env .env --run-id f55ad297893f4ccc8f55a0b6276f7c1b ingest data\interviews\*.docx --batch-size 64 --min-chars 200 --max-chars 1200
```

El pipeline procesó los archivos encontrados en `data/interviews`. A continuación se listan resultados y artefactos generados (resumen):

- Archivos procesados: (ver salida de la ejecución más abajo)
- Registros: entradas de logging en `logs/` (prefijo `ingest*`) y eventos `ingest.file.summary`.
- Resultado final: objeto con `per_file`, `totals` e `issues`.

> Nota: si la ejecución encuentra problemas para conectar a servicios externos (Neo4j, Qdrant, Postgres, Azure OpenAI) el pipeline devuelve errores en la salida y fallará la ingesta. Asegúrate de que `.env` contiene credenciales válidas.

## 4) Comandos y salidas relevantes (ejecutados durante la sesión)
- `python main.py --env .env project list --json` → muestra `test_progre` en la lista de proyectos.
- `python main.py --env .env project create --name "test_progre" --description "Proyecto de prueba progresivo" --json` → crea proyecto.
- `python main.py --env .env --run-id f55ad297893f4ccc8f55a0b6276f7c1b ingest data\interviews\*.docx --batch-size 64 --min-chars 200 --max-chars 1200` → ejecuta ingesta.

## 5) Siguientes pasos sugeridos
- Revisar logs en `logs/` para verificar issues por archivo.
- Ejecutar `python main.py --env .env status --project test_progre --json` para persistir y revisar snapshot de etapas.
- Opcional: abrir frontend con `VITE_NEO4J_ALWAYS_SEND_API_KEY=true` si el proxy no inyecta `X-API-Key`.

---

_Terminado: resumen inicial creado. Los detalles de la ejecución de ingesta (lista exacta de archivos procesados, totales e issues) se incluyen a continuación si lo deseas; puedo anexarlos en una segunda versión del documento con la salida completa del comando de ingesta._

## Nota: por qué la UI puede mostrar el estado inicial (placeholders) y cómo arreglarlo

Lo que se ve en pantalla es el estado inicial que usa valores por defecto porque las llamadas del frontend no están llegando al backend; por eso siguen apareciendo “Proyecto sin título / 0/9 etapas”. Hay dos causas típicas:

1. Falta de clave y URL en el frontend: si no defines VITE_API_KEY (o VITE_NEO4J_API_KEY) y VITE_BACKEND_URL/VITE_API_BASE, el cliente no envía X-API-Key y las peticiones a /api fallan (401/500). En ese caso el hook deja el estado vacío y la UI muestra los placeholders.
2. Servir estático sin proxy: si estás viendo el build (npm run build + vite preview o servidor externo) pero no hay un proxy a http://localhost:8000, las rutas /api/... responderán 404/errores y el estado no se carga.

Cómo verificar y corregir:

- En la terminal del frontend, exporta las variables antes de arrancar (Bash):

  export VITE_API_KEY=$NEO4J_API_KEY
  export VITE_BACKEND_URL=http://localhost:8000

  Luego npm run dev.

- PowerShell (Windows) equivalente antes de arrancar Vite:

  $env:VITE_API_KEY = $env:NEO4J_API_KEY
  $env:VITE_BACKEND_URL = 'http://localhost:8000'
  npm run dev

- Asegúrate de que el backend esté corriendo (uvicorn backend.app:app --reload --port 8000) y registre las peticiones /api/status, /api/projects, etc. sin errores.
- Revisa la consola del navegador (Network/Console): si ves 401/500/404 en /api/status o /api/projects, es la señal de que falta la clave o el backend no está accesible desde el host donde corre Vite.
- Si estás sirviendo el build sin Vite dev server, configura un reverse proxy para /api y /neo4j apuntando al backend en 8080, y pasa la cabecera X-API-Key con la misma clave.

Una vez que el frontend envíe X-API-Key y llegue al backend correcto, los datos de proyectos/estado se poblarán y verás el dashboard actualizado en lugar del placeholder.

## 6) Resultados de la ingesta (ejecución vía API / interfaz)

Se invocó el endpoint `POST /api/ingest` con `X-API-Key: dev-key` y el patrón `data/interviews/*.docx` para el proyecto `test-progre` (run_id `f55ad297893f4ccc8f55a0b6276f7c1b-frontend`). La respuesta fue la siguiente (resumen):

Archivos procesados (7):
- data\\interviews\\Claudia_Cesfam.docx — fragments: 50 — flagged: 7
- data\\interviews\\Guillermo Orestes.docx — fragments: 89 — flagged: 21
- data\\interviews\\Natalia Molina.docx — fragments: 84 — flagged: 10
- data\\interviews\\Pablo_Fabrega.docx — fragments: 160 — flagged: 38
- data\\interviews\\Trancripcion_Camilo_Colegio_Cayenel.docx — fragments: 146 — flagged: 22
- data\\interviews\\Trancripcion_Elba.docx — fragments: 124 — flagged: 7
- data\\interviews\\Trancripcion_Patricio_Yanez.docx — fragments: 95 — flagged: 6

Totales:
- archivos: 7
- fragmentos: 748
- flagged_fragments: 111
- issues detectadas: { "filler_repetition": 111 }

Estos resultados indican que la ingesta y la creación de embeddings en Qdrant se ejecutaron correctamente (peticiones HTTP a Azure OpenAI y Qdrant retornaron 200 OK durante el proceso). Los fragmentos que contienen repeticiones/muletas fueron marcados como `filler_repetition` (warnings) y contabilizados en el campo `flagged_fragments`.

Los archivos de logs apropiados y resúmenes por archivo se registraron como eventos `ingest.file.summary` en el logger. Puedes revisar entradas detalladas en la carpeta `logs/` (busca prefijos `ingest*`) o re-ejecutar:

```powershell
python main.py --env .env status --project test-progre --json
```

para persistir un snapshot del estado del proyecto y ver la página de estado generada en `metadata/projects/test-progre.json`.

---

## 7) Observaciones y próximos pasos

- Si quieres que la interfaz web muestre el progreso en tiempo real, podemos añadir un pequeño polling en la vista de Ingesta que consulte `GET /api/status?project=test-progre` durante la ejecución.
- Para producción, evita forzar el envío de `X-API-Key` desde el bundle del frontend; configura un reverse-proxy que inyecte la cabecera o implementa un flujo de auth más seguro.
- Puedo actualizar este documento con los extractos de logs (eventos `ingest.batch` y `ingest.file.summary`) si lo deseas.

Fin del registro inicial.
