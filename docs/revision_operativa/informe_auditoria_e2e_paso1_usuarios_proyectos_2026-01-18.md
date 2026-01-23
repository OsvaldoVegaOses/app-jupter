# ✅ Auditoría E2E Paso 1 — Usuarios y Proyectos

**Fecha:** 2026-01-18  
**Paso auditado:** Registro de usuarios y creación/eliminación de proyectos  
**Estado:** Ejecutado con evidencia en logs

---

## 1) Registro de usuarios

### Evidencia encontrada
- Solo hay lecturas de usuarios (`GET /api/admin/users`) con respuesta 200.
  - [logs/app.jsonl](logs/app.jsonl#L8)
  - [logs/app.jsonl](logs/app.jsonl#L16)
  - [logs/default/1768707330393-imm79sffl/app.jsonl](logs/default/1768707330393-imm79sffl/app.jsonl#L1)

### Evidencia **no** encontrada
- No hay registros de creación de usuarios (`POST /api/admin/users`) en logs.

**Conclusión:** El flujo de **registro/creación de usuarios no fue ejercitado** en esta sesión; solo se observan consultas. Si el paso requiere validación de creación, se necesita ejecutar explícitamente el endpoint de alta y revisar `request.start`/`request.end` + evento de negocio asociado.

---

## 2) Creación de proyectos

### Evidencia encontrada
- Múltiples intentos de `POST /api/projects` con `status_code: 400` (duplicado de identificador).
  - Inicio de request: [logs/default/1768707330393-imm79sffl/app.jsonl](logs/default/1768707330393-imm79sffl/app.jsonl#L157)
  - Respuesta 400: [logs/default/1768707330393-imm79sffl/app.jsonl](logs/default/1768707330393-imm79sffl/app.jsonl#L173)
  - Otro 400: [logs/default/1768707330393-imm79sffl/app.jsonl](logs/default/1768707330393-imm79sffl/app.jsonl#L263)
  - Otro 400: [logs/default/1768707330393-imm79sffl/app.jsonl](logs/default/1768707330393-imm79sffl/app.jsonl#L353)

### Evidencia **no** encontrada
- No hay evento `project.created` en esta sesión.

**Conclusión:** Se ejecutó el flujo de creación, pero falló por duplicado (400). No hay evidencia de creación exitosa en este paso.

---

## 3) Eliminación de proyectos

### Evidencia encontrada
- `DELETE /api/projects/jd-007` con `status_code: 200`.
  - Inicio de request: [logs/default/1768707330393-imm79sffl/app.jsonl](logs/default/1768707330393-imm79sffl/app.jsonl#L140)
  - Fin con 200: [logs/default/1768707330393-imm79sffl/app.jsonl](logs/default/1768707330393-imm79sffl/app.jsonl#L145)

- Evento `project.deleted` con confirmación de eliminación en PostgreSQL (`pg_proyectos: 1`).
  - [logs/default/1768707330393-imm79sffl/app.jsonl](logs/default/1768707330393-imm79sffl/app.jsonl#L144)

**Conclusión:** La eliminación **sí quedó registrada** y con evidencia de limpieza en PostgreSQL.

---

## Resultado del Paso 1

- **Usuarios:** Solo lecturas, sin creación. Falta evidencia de registro.
- **Proyectos:** Creación fallida por duplicado (400); eliminación exitosa y registrada.

---

## Próximo paso

Indica el **Paso 2** a auditar y ejecuto el mismo nivel de evidencia E2E.