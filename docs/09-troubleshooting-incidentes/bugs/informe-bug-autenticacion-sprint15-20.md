# Informe: Bug de Autenticación - Sprint 15-20

**Fecha:** 2025-12-28  
**Estado:** ✅ RESUELTO

---

## Resumen Ejecutivo

El sistema de autenticación presentaba múltiples bugs que impedían el registro y login de usuarios. Se identificaron y corrigieron **5 bugs independientes** que se acumularon durante el desarrollo.

---

## Bugs Identificados y Corregidos

### Bug #1: Import `status` faltante

| Campo | Detalle |
|-------|---------|
| **Archivo** | `backend/app.py` línea 93 |
| **Síntoma** | Endpoints de auth no se registraban en FastAPI |
| **Causa** | `status.HTTP_401_UNAUTHORIZED` usado sin importar `status` |

```diff
- from fastapi import Depends, FastAPI, HTTPException, Header, Query, Body
+ from fastapi import Depends, FastAPI, HTTPException, Header, Query, Body, status
```

---

### Bug #2: Middleware Vite bloqueando rutas

| Campo | Detalle |
|-------|---------|
| **Archivo** | `frontend/vite.config.ts` líneas 372-388 |
| **Síntoma** | Llamadas a `/api/auth/*` retornaban 404 |
| **Causa** | Lista blanca del middleware sin `/api/auth/*` |

**Fix:** Rutas agregadas al bypass del middleware.

---

### Bug #3: Archivo corrupto con bytes nulos

| Campo | Detalle |
|-------|---------|
| **Archivo** | `backend/app.py` |
| **Síntoma** | `SyntaxError: source code string cannot contain null bytes` |
| **Causa** | Comando PowerShell corrompió el archivo |

```powershell
[System.IO.File]::ReadAllText("backend\app.py").Replace("`0", "") | Set-Content -Encoding UTF8
```

---

### Bug #4: Desempaquetado incorrecto de TokenResponse (endpoint `/token`)

| Campo | Detalle |
|-------|---------|
| **Archivo** | `backend/app.py` línea 416 |
| **Síntoma** | Error 500 al registrar usuario |
| **Causa** | `create_tokens_for_user()` retorna `TokenResponse`, no tuple |

```diff
- tokens, token_error = create_tokens_for_user(clients.postgres, user)
+ tokens = create_tokens_for_user(clients.postgres, user)

- tokens["access_token"]
+ tokens.access_token
```

---

### Bug #5: Desempaquetado incorrecto de TokenResponse (endpoint `/api/auth/login`)

| Campo | Detalle |
|-------|---------|
| **Archivo** | `backend/app.py` línea 473 |
| **Síntoma** | Login fallaba después de cerrar sesión |
| **Causa** | Mismo bug que #4, en diferente endpoint |

**Fix:** Mismo cambio aplicado a línea 473.

---

## Limpieza de Código Duplicado

### Sistema de usuarios JSON eliminado

| Sistema | Almacenamiento | Estado |
|---------|----------------|--------|
| `backend/users.py` | JSON (archivo) | ❌ Eliminado |
| `app/postgres_block.py` | PostgreSQL | ✅ Activo |

**Archivos eliminados:**
- `backend/users.py`
- `metadata/users_registry.json`
- Endpoint `/register` duplicado

---

## Verificación Final

```powershell
# Registro exitoso
Invoke-RestMethod -Uri "http://localhost:8000/api/auth/register" -Method Post `
  -ContentType "application/json" -Body '{"email":"test@test.com","password":"Test123!#"}'
# ✅ "message": "Usuario registrado exitosamente"

# Login exitoso
Invoke-RestMethod -Uri "http://localhost:8000/api/auth/login" -Method Post `
  -ContentType "application/json" -Body '{"email":"osvaldo_vega@hotmail.cl","password":"Test123!#"}'
# ✅ "access_token": "eyJhbGci..."
```

---

## Lecciones Aprendidas

1. **Verificar imports de FastAPI** cuando endpoints no se registran
2. **Actualizar middleware de Vite** con nuevos prefijos de API
3. **Evitar editar archivos Python con PowerShell**
4. **Verificar tipos de retorno** al desempaquetar funciones
5. **Reconstruir imágenes Docker** después de cambios (`--no-cache`)
6. **Buscar código duplicado** - puede haber múltiples endpoints con el mismo bug
```
