# Despliegue del Frontend en Azure Container Apps

## Resumen
Este documento detalla el proceso de resolución de problemas y despliegue exitoso del frontend React/Vite en Azure Container Apps, conectándolo al backend FastAPI existente.

## Problemas Iniciales

### 1. Errores en el Build ACR
- **Problema**: El build fallaba con `sh: tsc: not found` porque el Dockerfile usaba `RUN npm ci --only=production`, omitiendo dependencias de desarrollo.
- **Solución**: Cambiar a `RUN npm ci` para instalar todas las dependencias.

### 2. Comando TypeScript Incorrecto
- **Problema**: `package.json` tenía `"build": "tsc && vite build"`, causando errores de permisos en contenedores.
- **Solución**: Cambiar a `"build": "npx tsc && vite build"` para usar TypeScript vía npx.

### 3. Versión Incorrecta de Dependencia
- **Problema**: `rollup-plugin-visualizer@^6.5.4` no existía; la versión correcta es `5.12.0`.
- **Solución**: Actualizar `package.json` y regenerar `package-lock.json` con `npm install`.

### 4. Errores de TypeScript
- **Problema**: Tipos undefined en `GraphRAGPanel.tsx` y `Neo4jExplorer.tsx`, causando fallos en compilación.
- **Solución**: Agregar encadenamiento opcional (`?.`), valores por defecto, y casts de tipos.

### 5. Archivo de Configuración Faltante
- **Problema**: Falta `.env.production` con la URL del backend.
- **Solución**: Crear archivo copiando de `.env.production.template`.

### 6. Autenticación ACR en Container App
- **Problema**: Container App no podía pull la imagen por falta de credenciales.
- **Solución**: Usar `--registry-server`, `--registry-username`, y `--registry-password` en `az containerapp create`.

## Soluciones Aplicadas

### Cambios en Código
1. **Dockerfile.prod**: `RUN npm ci --only=production` → `RUN npm ci`
2. **package.json**:
   - `"rollup-plugin-visualizer": "^6.5.4"` → `"^5.12.0"`
   - `"build": "tsc && vite build"` → `"npx tsc && vite build"`
   - `"build:analyze": "cross-env-shell ANALYZE=true \"tsc && vite build\""` → `"cross-env-shell ANALYZE=true \"npx tsc && vite build\""`
3. **GraphRAGPanel.tsx**:
   - `answer: response.answer` → `answer: response.answer || ''`
   - `cita: firstFrag?.fragmento?.substring(0, 300) || response.answer.substring(0, 300)` → `cita: firstFrag?.fragmento?.substring(0, 300) || response.answer?.substring(0, 300) || ''`
   - `{response.nodes.length}` → `{response.nodes?.length || 0}`
4. **Neo4jExplorer.tsx**:
   - Agregar `?.` en accesos a `graph.nodes`, `graph.relationships`
   - `label: String(...)` para asegurar string
   - Casts: `id: n.id as string | number`, `community: n.properties?.community_id as string | number | undefined`

### Configuración de Entorno
- Crear `frontend/.env.production` con:
  ```
  VITE_API_BASE=
  VITE_BACKEND_URL=
  ```

> Recomendado: **same-origin** en producción. El `nginx.conf` del frontend ya proxea `/api` al backend usando `BACKEND_URL` en runtime, evitando CORS/cookies cross-site.

### Script de Automatización
Se creó `fix_and_deploy_frontend.ps1` que:
1. Crea `.env.production`
2. Actualiza `package-lock.json` con `npm install`
3. Commitea cambios locales
4. Hace pull y push a GitHub
5. Construye imagen en ACR
6. Crea Container App con autenticación

## Pasos de Despliegue

1. **Preparar cambios locales**:
   - Editar archivos como arriba
   - Ejecutar `npm install` en `frontend/`

2. **Commit y push**:
   ```
   git add .
   git commit -m "Fix frontend build issues"
   git push origin main
   ```

3. **Build en ACR**:
   ```
   az acr build -g newsites -r axialacr12389 -t axial-frontend:latest -f Dockerfile.prod "https://github.com/OsvaldoVegaOses/app-jupter.git#main:frontend"
   ```

4. **Crear Container App**:
   ```
   az containerapp create -g newsites -n axial-frontend --image axialacr12389.azurecr.io/axial-frontend:latest --environment axial-env --target-port 80 --ingress external --registry-server axialacr12389.azurecr.io --registry-username axialacr12389 --registry-password <password>
   ```

## Resultado Final

- **Frontend URL**: https://axial-frontend.blackplant-ffb9e37f.eastus2.azurecontainerapps.io/
- **Backend URL**: https://axial-api.blackplant-ffb9e37f.eastus2.azurecontainerapps.io
- **Estado**: Frontend desplegado y conectado al backend.

## Lecciones Aprendidas

- Siempre instalar dependencias de desarrollo en Docker para builds que requieren compilación.
- Usar `npx` para binarios globales en contenedores para evitar errores de permisos.
- Verificar versiones de paquetes antes de usar rangos amplios.
- Agregar encadenamiento opcional en TypeScript para manejar tipos undefined.
- Configurar autenticación ACR en Container Apps para pulls privados.

## Archivos Modificados

- `frontend/Dockerfile.prod`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/.env.production` (nuevo)
- `frontend/src/components/GraphRAGPanel.tsx`
- `frontend/src/components/Neo4jExplorer.tsx`

Fecha: Enero 27, 2026
