# Informe de Revisión Operativa — JD-009
**Fecha:** 2026-01-08  
**Proyecto:** jd-009  
**Fuente:** logs/app.jsonl + notas de discovery en notes/jd-009/  

## 1) Resumen ejecutivo
Durante la sesión se ejecutó el flujo completo de **creación del proyecto**, **carga + ingesta** de entrevistas (DOCX) y posteriormente **análisis asistido** con persistencia de códigos candidatos y relaciones axiales. El sistema completó la ingesta y análisis, pero se observan **degradaciones operativas** repetidas en:
- `api.coding.stats` por `statement timeout` (PostgreSQL)
- `qdrant.upsert` por timeout de escritura (Qdrant)

## 2) Alcance investigativo (contexto del estudio)
El trabajo asociado a JD-009 se enmarca en el diseño/continuidad de alternativas para resolver el drenaje y evacuación de aguas lluvias en el corredor quebrada de Macul – Av. La Florida – Camilo Henríquez, incorporando coordinación institucional (SECPLAN, MOP/MINVU/Serviu, municipio) y consideración de riesgos territoriales e infraestructura base (colectores/vialidad/mitigaciones).

Evidencia (discovery):
- Presentación del estudio y continuidad con informe 2017: `notes/jd-009/2026-01-08_00-27_discovery_Memo_IA__presentacion_estudio.md`
- Rol institucional municipal/SECPLAN, normativa y planificación integral: `notes/jd-009/2026-01-08_11-36_discovery_estado_sector_público.md`

## 3) Clasificación operativa de eventos observados
### 3.1 Evento: Creación de proyecto
- **OK**: `project.created` registrado para `jd-009`.

### 3.2 Evento: Carga + ingesta de documentos (upload_and_ingest)
Se observan cargas exitosas con cierre de archivo (`ingest.file.end`) y métricas consistentes.

**Archivos observados (muestra representativa):**
- `_entrevista_Gerente_Canal_San_Carlos_20260108_000506.docx`
- `Entrevista_equipo_Asesor_Urbano_La_Florida_20260108_000523.docx`
- `Entrevista_DIPMA_La_Florida_20260108_000611.docx`
- `Entrevista_Encargada_Emergencia_La_Florida_20260108_000622.docx`
- `Jefa_Territorial_Municipalidad_La_Florida_20260108_000709.docx`
- `Secpla_I_M_Puente_Alto_20260108_000823.docx`

**Señales de calidad de texto (QA):**
- Múltiples `ingest.fragment.flagged` por `filler_repetition` en varios documentos.
- Impacto operativo: **bajo-medio** (no corta el flujo), pero puede aumentar ruido en análisis/codificación.

### 3.3 Evento: Análisis asistido y persistencia
- Descarga posterior de blobs (`analyze.downloaded_blob`) y persistencia de resultados:
  - `analysis.persist.linkage_metrics` con tasas de enlace altas (87.5%–100%).
  - `analysis.persist.candidates_inserted` (candidatos insertados, fuente LLM).
  - `analysis.axial.persisted` (relaciones y categorías).

### 3.4 Incidencias y degradaciones
#### A) PostgreSQL: `api.coding.stats.timeout_or_error`
- Se observa repetición del error `canceling statement due to statement timeout` para `jd-009`.
- Impacto: degradación en paneles/estadísticas de codificación; potencialmente afecta UX y monitoreo.

#### B) Qdrant: `qdrant.upsert.split`
- Se registra `The write operation timed out` y división de lote.
- Impacto: el sistema se recupera (split), pero sugiere presión de red/latencia o límites de timeout.

## 4) Diagnóstico con nivel de alerta
**Nivel de alerta global: AMARILLO (Degradación operativa, servicio funcional)**

**Justificación:**
- El pipeline principal (ingesta + análisis) **completa**, pero hay fallas repetidas en endpoints de soporte crítico (`coding.stats`) y señales de estrés en persistencia vectorial (Qdrant).

**Riesgo si no se actúa:**
- Degradación progresiva de UX (estadísticas), saturación de recursos, y mayor probabilidad de timeouts en cargas más grandes o en concurrencia.

## 5) Priorización de acciones
### P0 — Inmediato (bloquea observabilidad/UX)
1) **Reducir/diagnosticar timeouts en `api.coding.stats` (PostgreSQL)**
   - Revisar consulta(s) y plan de ejecución; agregar/ajustar índices si aplica.
   - Revisar `statement_timeout` y tiempos de respuesta reales.
   - Confirmar si `coding.stats` se ejecuta sobre tablas grandes sin filtros por proyecto o sin índices.

### P1 — Alta (estabilidad de persistencia vectorial)
2) **Mitigar `qdrant.upsert` timeout**
   - Forzar lotes más pequeños o reintentos con backoff en escritura.
   - Revisar timeouts de cliente/servidor y latencias en el entorno.

### P2 — Media (calidad y eficiencia del análisis)
3) **Ajustar heurísticas de `filler_repetition` y preprocesamiento**
   - Reducir falsos positivos o colapsar muletillas sin marcar tantos fragmentos.
   - Beneficio: menos ruido para el modelo/analista y mejor señal para codificación.

## 6) Checklist de verificación post-fix
- Reintentar `coding.stats` en JD-009 sin timeouts (mínimo 10 ejecuciones consecutivas).
- Confirmar que `qdrant.upsert.split` no aparece en cargas de tamaño comparable.
- Validar que la tasa de `ingest.fragment.flagged` baja o se vuelve más informativa.

## 7) Anexo (sin problemas): Mapa Discovery → codificación
Se dejó un documento dedicado que cruza:
- Memos de Discovery (criterios y fragmentos) con
- la codificación axial persistida (`analysis.axial.persisted`) por archivo.

Documento:
- `docs/revision_operativa/sin_problemas/JD-009_mapa_discovery_codificacion_2026-01-08.md`

Hallazgo metodológico (resumen):
- El bucle manual de Discovery sigue un patrón repetible: **query amplia → negativos → texto objetivo → consolidación**, con mejoras claras de pertinencia.
- Hay oportunidad de automatizar el refinamiento (sin cambiar UX) generando variantes y validando “aterrizaje” contra categorías/códigos persistidos.

---
**Archivos de soporte (referencias):**
- logs/app.jsonl
- notes/jd-009/2026-01-08_00-27_discovery_Memo_IA__presentacion_estudio.md
- notes/jd-009/2026-01-08_11-36_discovery_estado_sector_público.md
- docs/revision_operativa/sin_problemas/JD-009_mapa_discovery_codificacion_2026-01-08.md
