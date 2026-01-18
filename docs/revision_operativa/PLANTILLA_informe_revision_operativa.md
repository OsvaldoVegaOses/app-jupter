# Informe de Revisión Operativa — {{PROJECT_ID}}
**Fecha:** {{YYYY-MM-DD}}  
**Proyecto:** {{PROJECT_ID}}  
**Fuente:** {{FUENTES}}  

## 1) Resumen ejecutivo
{{RESUMEN_EJECUTIVO}}

## 2) Alcance investigativo (contexto del estudio)
{{ALCANCE_INVESTIGATIVO}}

Evidencia (discovery / documentos):
- {{REF_1}}
- {{REF_2}}

## 3) Clasificación operativa de eventos observados
### 3.1 Evento: Creación de proyecto
- {{EVENTO_CREACION_PROYECTO}}

### 3.2 Evento: Carga + ingesta de documentos (upload_and_ingest)
{{DESCRIPCION_INGESTA}}

**Archivos observados (muestra representativa):**
- {{ARCHIVO_1}}
- {{ARCHIVO_2}}
- {{ARCHIVO_3}}

**Señales de calidad de texto (QA):**
- {{QA_FLAG_1}}
- {{QA_FLAG_2}}

### 3.3 Evento: Análisis asistido y persistencia
{{DESCRIPCION_ANALISIS}}

### 3.4 Incidencias y degradaciones
#### A) PostgreSQL: `api.coding.stats.timeout_or_error`
- {{INCIDENCIA_PG}}

#### B) Qdrant: `qdrant.upsert.split` (u otras)
- {{INCIDENCIA_QDRANT}}

#### C) Otros (opcional)
- {{INCIDENCIA_OTRA}}

## 4) Diagnóstico con nivel de alerta
**Nivel de alerta global: {{ALERTA}}**

**Justificación:**
- {{JUSTIFICACION_ALERTA}}

**Riesgo si no se actúa:**
- {{RIESGO}}

## 5) Priorización de acciones
### P0 — Inmediato
1) {{ACCION_P0_1}}
2) {{ACCION_P0_2}}

### P1 — Alta
1) {{ACCION_P1_1}}

### P2 — Media
1) {{ACCION_P2_1}}

## 6) Checklist de verificación post-fix
- {{CHECK_1}}
- {{CHECK_2}}
- {{CHECK_3}}

---
**Archivos de soporte (referencias):**
- {{REF_LOGS}}
- {{REF_NOTAS_1}}
- {{REF_NOTAS_2}}
