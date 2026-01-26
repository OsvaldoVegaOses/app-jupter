**CI Smoke Checklist & Scripts**

Propósito
- Proveer un conjunto minimal y reproducible de comprobaciones que debe correr el pipeline CI (o manualmente) antes de un despliegue a Azure.

Requisitos de entorno (variables)
- `BACKEND_URL` (default `http://127.0.0.1:8000`)
- `API_KEY` (clave API para endpoints protegidos)
- `API_KEY_ORG_ID` (org id usado por scripts SDK)
- `AZURE_STORAGE_CONNECTION_STRING` (para pruebas de blob)
- `WORKER_ENABLED` (opcional, `true` si el worker Celery está desplegado y quieres probar jobs async)

Archivos útiles
- `scripts/ci_smoke.sh` - Bash runner (Linux CI)
- `scripts/ci_smoke.ps1` - PowerShell runner (Windows/Azure Pipelines)
- `scripts/smoke_tenant_upload.py` - Realiza un `tenant_upload_bytes` vía SDK para verificar subida y contrato
- `scripts/check_azure_services.py` - Verifica conectividad a Blob, Postgres, Neo4j y Qdrant
- `scripts/apply_migrations_production.py` - Aplica migraciones SQL listadas (usar con precaución)

Qué hace `ci_smoke` (pasos)
1. `GET /healthz` → espera HTTP 200.
2. Ejecuta `scripts/check_azure_services.py` (comprueba Blob, Postgres, Neo4j, Qdrant).
3. Ejecuta `scripts/smoke_tenant_upload.py` para hacer un `tenant_upload_bytes` bajo `reports/<project>` y validar que la respuesta incluye `artifact_version`, `sha256`, `size_bytes` y `name` con prefijo `org/<org_id>/projects/<project>`.
4. Opcional (si `WORKER_ENABLED=true`): encola un job de transcripción a través de `/api/transcribe/stream` y lo consulta hasta `SUCCESS` (requiere worker en ejecución).

Resultados esperados
- Health: 200
- `check_azure_services.py`: `configured: true`, `status: ok` y conexiones a servicios listas
- `smoke_tenant_upload.py`: imprime JSON con keys `artifact_version`, `container`, `name`, `url`, `sha256`, `size_bytes`, `metadata.org_id` igual a `API_KEY_ORG_ID`
- Si `WORKER_ENABLED`: job async llega a `SUCCESS` dentro del timeout de la prueba

Integración en GitHub Actions (ejemplo simplificado)

jobs:
  ci_smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install deps
        run: |
          python -m pip install -r requirements.txt
      - name: Run CI smoke
        env:
          BACKEND_URL: ${{ secrets.BACKEND_URL }}
          API_KEY: ${{ secrets.API_KEY }}
          API_KEY_ORG_ID: ${{ secrets.API_KEY_ORG_ID }}
          AZURE_STORAGE_CONNECTION_STRING: ${{ secrets.AZURE_STORAGE_CONNECTION_STRING }}
          WORKER_ENABLED: 'false'
        run: bash scripts/ci_smoke.sh

Notas y recomendaciones
- El test de escritura por HTTP (endpoints que realizan transcripción/ingestión) puede depender de servicios externos (Azure OpenAI). Por eso el script principal valida la subida por SDK y ofrece la opción `WORKER_ENABLED` para pruebas async solamente cuando el worker y servicios estén desplegados y accesibles.
- Evitar exponer `AZURE_STORAGE_CONNECTION_STRING` en texto plano: guárdalo en secrets (Key Vault / GitHub Secrets) y monta en el runner.
- Para validar 409 en endpoints que exigen `organization_id`, crea una cuenta de API sin org o mockea la cabecera de usuario en el entorno de CI (esto puede requerir control adicional del mecanismo de `backend/auth`).

Errores comunes
- `esbuild` EPERM en Vite: en runners Windows/Ubuntu puede requerir `npm ci --unsafe-perm` o configurar `ESBUILD_BINARY_PATH`. Preferible usar contenedor Linux con Node 18+ y permisos adecuados.
- Worker/Redis no accesible: la fase `WORKER_ENABLED=true` fallará si el worker no está desplegado.

Contacto
- Si quieres, integro este script en un workflow YAML y lo pruebo localmente contra tu entorno si me indicas las credenciales (o indicas que las guardemos como secrets en el runner).
