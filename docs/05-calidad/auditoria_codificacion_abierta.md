# Auditoría — Flujo de Codificación Abierta (Etapa 3)

## Propósito
Esta página documenta (a) cómo funciona hoy el flujo de **Codificación abierta** en el sistema (Frontend + Backend + Postgres) y (b) el **modo guiado v1** ("Siguiente recomendado") que añade recomendación de fragmento + registro de feedback.

Alcance: Etapa 3 (codificación abierta). No cubre Axial/Neo4j salvo como dependencias aguas abajo.

---

## 1) UX actual (Frontend)

### 1.1 Panel principal
- Componente: `frontend/src/components/CodingPanel.tsx`
- La etapa se trabaja como un conjunto de pestañas (un "workspace" por sub-tarea).

### 1.2 Orden del flujo (reordenado)
Orden recomendado de trabajo (pestañas):
1. **🧭 Siguiente recomendado**: fragmento sugerido + decisión rápida (aceptar/rechazar/editar) con feedback.
2. **📝 Asignar código**: asignación manual controlada (fragmento_id, código, cita/memo, fuente).
3. **🔍 Sugerencias semánticas**: comparación constante (seed → similares).
4. **📊 Cobertura y avance**: métricas de progreso y cobertura.
5. **📎 Citas por código**: auditoría y trazabilidad por código.

Razonamiento: se prioriza el loop operativo (decidir y registrar) y luego la comparación constante/diagnóstico.

---

## 2) Superficie API (Backend)

### 2.1 Endpoints operativos (codificación)
- `POST /api/coding/assign`
  - Registra una asignación (fragmento + código + cita/memo + fuente).
- `GET /api/coding/stats`
  - Métricas de cobertura/avance.
- `GET /api/coding/codes`
  - Lista/contador de códigos registrados.
- `GET /api/coding/fragments`
  - Lista fragmentos por entrevista (archivo).
- `POST /api/coding/suggest`
  - Recupera fragmentos similares para comparación constante.
- `GET /api/coding/citations`
  - Citas por código (auditoría).

### 2.2 Modo guiado v1 (nuevo)
- `GET /api/coding/next`
  - Devuelve el **siguiente fragmento recomendado** (heurístico) + lista de códigos sugeridos (frecuencias) + razones.
  - Parámetros relevantes:
    - `strategy=recent|oldest|random`
    - `exclude_fragment_id=<id>` (repetible) para evitar repetir fragmentos (ej. cuando el usuario rechaza en UI)
- `POST /api/coding/feedback`
  - Persiste eventos de feedback (accept/reject/edit) para trazabilidad y aprendizaje incremental.

---

## 3) Persistencia (PostgreSQL)

### 3.1 Fragmentos
Tabla base (fragmentos de entrevistas):
- `entrevista_fragmentos`
  - Contiene `fragmento_id`, `archivo`, `par_idx`, `fragmento`, etc.

### 3.2 Codificación abierta (asignaciones)
Tabla de codificación:
- `analisis_codigos_abiertos`
  - Clave principal: `(project_id, fragmento_id, codigo)`
  - Permite guardar `memo`/cita y atributos operativos.

### 3.3 Feedback (modo guiado)
Tabla nueva (v1):
- `coding_feedback_events`
  - Eventos: `accept`, `reject`, `edit`
  - Campos típicos: `project_id`, `fragmento_id`, `suggested_code`, `final_code`, `meta`, `created_at`, `user_id`.

---

## 4) Heurística v1 (cómo decide "siguiente")

### 4.1 Objetivo
- Minimizar fricción: siempre ofrecer un fragmento pendiente.
- Evitar dependencia de Qdrant/AOAI para que el flujo funcione "offline".

### 4.2 Estrategia (actual)
- Selección de un fragmento **aún no codificado** (según lo registrado en Postgres).
- Priorización por recencia/orden del documento.
- Sugerencia de códigos basada en **frecuencia** (top codes globales del proyecto).

Limitación deliberada: esta primera versión no intenta inferir semánticamente el mejor código; solo acelera el loop y captura señales.

---

## 5) Verificación rápida (manual)

### 5.1 Obtener siguiente recomendado
```bash
curl -H "X-API-Key: dev-key" "http://localhost:8000/api/coding/next?project=default&strategy=recent"

# Excluir IDs (repetible)
curl -H "X-API-Key: dev-key" "http://localhost:8000/api/coding/next?project=default&exclude_fragment_id=entrevista/001#p12&exclude_fragment_id=entrevista/002#p05"
```

### 5.2 Registrar feedback
```bash
curl -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"project":"default","fragmento_id":"entrevista/001#p12","action":"reject","suggested_code":"X","final_code":null,"meta":{"ui":"guided_v1"}}' \
  "http://localhost:8000/api/coding/feedback"
```

### 5.3 Aceptar y registrar (asignación)
```bash
curl -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"project":"default","fragment_id":"entrevista/001#p12","codigo":"Resiliencia comunitaria","cita":"...","fuente":"entrevista.docx"}' \
  "http://localhost:8000/api/coding/assign"
```

---

## 6) Próximos pasos sugeridos (después de v1)
- Usar `coding_feedback_events` para re-rankear sugerencias (por usuario/proyecto).
- Incorporar señales semánticas opcionales (Qdrant) cuando estén disponibles.
- Exponer métricas de guided-mode: tasa de aceptación, edits, rechazos, tiempo por decisión.
