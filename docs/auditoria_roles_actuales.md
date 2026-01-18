# Auditoría de roles actuales y uso (2026-01-17)

## Alcance
- Backend: backend, app
- Frontend: frontend

## Roles actuales (usuario)
- **admin / analyst / viewer**
  - Definidos en tokens JWT en [backend/auth_service.py](backend/auth_service.py).
  - El `role` se guarda como string y además se añade `roles: [role]` al JWT.
  - `require_role([...])` valida contra `user.roles`.

## Roles por proyecto (project_members)
- **admin / codificador / lector**
  - Definidos en [app/postgres_block.py](app/postgres_block.py).
  - Mapeo desde rol usuario:
    - admin → admin
    - analyst → codificador
    - viewer → lector
  - Auto‑enroll por default project en [app/project_state.py](app/project_state.py).

## Autenticación / autorización
- JWT: `roles` dentro del token.
- API Key: requiere `NEO4J_API_KEY` o `API_KEY`, **y** `API_KEY_ORG_ID` (estricto multi‑tenant).
  - Si falta `API_KEY_ORG_ID`, responde 401.
  - Roles por API key: `API_KEY_ROLES` (default: admin). Ver [backend/auth.py](backend/auth.py).

## Dónde se usan los roles

### Backend (guards)
- `require_role(["admin"])` en endpoints admin y limpieza.
- `require_role(["admin", "analyst"])` en análisis y reportes.
- Validaciones “is_admin” locales en stage0/coding.

### Frontend (UI)
- `user.role` controla vistas/admin en [frontend/src/App.tsx](frontend/src/App.tsx).
- AdminPanel visible solo si `role === "admin"`.
- Stage0 usa `localStorage` para roles (array) en [frontend/src/components/Stage0PreparationPanel.tsx](frontend/src/components/Stage0PreparationPanel.tsx).

## Riesgos detectados
1. **Doble modelo de roles**: `role` (string) vs `roles` (array). UI usa `role`, backend usa `roles`.
2. **API Key sin `API_KEY_ORG_ID`** bloquea endpoints admin.
3. **Roles proyecto vs roles usuario** pueden confundirse en UI/UX (admin vs codificador/lector).
4. **SuperAdmin no existe aún**: no hay bypass global para multi‑org.

## Recomendaciones para evitar fallos
1. **Normalizar roles**
   - Backend: exponer siempre `role` y `roles` en respuestas auth.
   - Frontend: derivar `isAdmin` desde `roles` si existe; fallback a `role`.
2. **Config API Key**
   - Requerir `API_KEY_ORG_ID` en `.env` para pruebas admin.
3. **Agregar `superadmin`**
   - `require_role` aceptar superadmin como bypass.
   - UI: ocultar acciones solo si no es admin/superadmin.
4. **Documentar mapeo de roles**
   - `admin/analyst/viewer` (usuario) → `admin/codificador/lector` (proyecto).
5. **Auditoría y trazabilidad**
   - Log de cambios de rol y acciones destructivas.

## Plan de mejora (sin romper producción)
1. Añadir constantes de roles en backend y frontend (shared doc o `types`).
2. Ajustar frontend para usar `roles` si existe.
3. Agregar rol `superadmin` en JWT y guards (sin activarlo en UI todavía).
4. Añadir `API_KEY_ORG_ID` en `.env` para pruebas locales con API key.
5. Tests de permisos para endpoints admin.

## Archivos clave
- [backend/auth.py](backend/auth.py)
- [backend/auth_service.py](backend/auth_service.py)
- [app/project_state.py](app/project_state.py)
- [app/postgres_block.py](app/postgres_block.py)
- [frontend/src/App.tsx](frontend/src/App.tsx)
- [frontend/src/context/AuthContext.tsx](frontend/src/context/AuthContext.tsx)
- [frontend/src/components/Stage0PreparationPanel.tsx](frontend/src/components/Stage0PreparationPanel.tsx)
