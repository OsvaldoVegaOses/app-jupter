# ✅ Auditoría E2E — Proyectos del usuario osvaldovegaoses@gmail.com

**Fecha:** 2026-01-18  
**Usuario:** osvaldovegaoses@gmail.com  
**Proyecto objetivo:** default-6fc75e26-c0f4-4559-a2ef-10e508467661

---

## 1) Sesiones detectadas del proyecto

Se identificaron sesiones con `project_id = default-6fc75e26-c0f4-4559-a2ef-10e508467661`:

- [logs/default-6fc75e26-c0f4-4559-a2ef-10e508467661/1768706787902-xu1jmk7u8/app.jsonl](logs/default-6fc75e26-c0f4-4559-a2ef-10e508467661/1768706787902-xu1jmk7u8/app.jsonl)
- [logs/default-6fc75e26-c0f4-4559-a2ef-10e508467661/1768709515739-tstxeu48m/app.jsonl](logs/default-6fc75e26-c0f4-4559-a2ef-10e508467661/1768709515739-tstxeu48m/app.jsonl)
- [logs/default-6fc75e26-c0f4-4559-a2ef-10e508467661/1768710799695-sylity92i/app.jsonl](logs/default-6fc75e26-c0f4-4559-a2ef-10e508467661/1768710799695-sylity92i/app.jsonl)
- [logs/default-6fc75e26-c0f4-4559-a2ef-10e508467661/1768710887061-lzhy78i57/app.jsonl](logs/default-6fc75e26-c0f4-4559-a2ef-10e508467661/1768710887061-lzhy78i57/app.jsonl)
- [logs/default-6fc75e26-c0f4-4559-a2ef-10e508467661/1768710970351-99v2vt6da/app.jsonl](logs/default-6fc75e26-c0f4-4559-a2ef-10e508467661/1768710970351-99v2vt6da/app.jsonl)

**Observación:** estas sesiones solo muestran lecturas (`GET /api/status`, `GET /api/research/overview`). No hay creación ni eliminación en esas sesiones.

---

## 2) Identidad del usuario

Se observan eventos de login para `osvaldovegaoses@gmail.com` en el log agregado:

- [logs/app.jsonl](logs/app.jsonl#L259)
- [logs/app.jsonl](logs/app.jsonl#L537)
- [logs/app.jsonl](logs/app.jsonl#L551)
- [logs/app.jsonl](logs/app.jsonl#L565)

**Nota:** Los eventos de creación/eliminación de proyectos aparecen con `user: api-key-user`, por lo que el backend no vincula directamente la acción con el email en los logs de evento de negocio.

---

## 3) Creación de proyectos (para este proyecto)

**Evidencia encontrada:**
- No hay evento `project.created` para `default-6fc75e26-c0f4-4559-a2ef-10e508467661`.

**Conclusión:** No hay evidencia en logs de creación exitosa de este proyecto.

---

## 4) Eliminación de proyecto

**Evidencia encontrada:**
- `DELETE /api/projects/default-6fc75e26-c0f4-4559-a2ef-10e508467661` con respuesta 200:
  - Inicio: [logs/app.jsonl](logs/app.jsonl#L474)
  - Fin: [logs/app.jsonl](logs/app.jsonl#L479)
- Evento `project.deleted` con `pg_proyectos: 1`:
  - [logs/app.jsonl](logs/app.jsonl#L478)

**Conclusión:** La eliminación del proyecto **sí quedó registrada** y con limpieza confirmada en PostgreSQL.

---

## 5) Resultado

- **Creación:** sin evidencia de creación exitosa en logs.
- **Eliminación:** confirmada con `project.deleted` y `DELETE` 200.
- **Sesiones del proyecto:** solo lecturas (no CRUD).

---

## 6) Recomendación de trazabilidad

Para auditar creación y eliminación por usuario, se recomienda que el backend registre el `user_id`/`email` en los eventos de negocio (`project.created`, `project.deleted`). Actualmente aparece como `api-key-user`, lo cual limita trazabilidad por usuario final.