# INFORME AUTOMÁTICO DE LOGS
## Sistema de Análisis Cualitativo - APP_Jupter

**Generado:** 2025-12-20 13:49:24  
**Período de logs:** 2025-12-20T03:57:53 → 2025-12-20T16:41:16  
**Total de registros:** 119

---

## 📋 RESUMEN EJECUTIVO

⚠️ **Estado:** 1 error(es) detectado(s)

### Distribución por Nivel

| Nivel | Cantidad | Porcentaje |
|-------|----------|------------|
| 🔴 error | 1 | 0.8% |
| ⚠️ warning | 11 | 9.2% |
| ℹ️ info | 107 | 89.9% |
| 🔍 debug | 0 | 0.0% |

### Proyectos Activos

- `nubeweb`
- `perro`

### Archivos Procesados

Total: **16** archivos

- Entrevista APR Horcón.docx
- Entrevista APR_Horcon_20251220_125919.docx
- logs/app.jsonl
- logs\app.jsonl
- tmpctqoupsw.mp3
- tmpctqoupsw_chunk000.mp3
- tmpctqoupsw_chunk001.mp3
- tmpctqoupsw_chunk002.mp3
- tmpctqoupsw_chunk003.mp3
- tmpctqoupsw_chunk004.mp3
- tmpctqoupsw_chunk005.mp3
- tmpctqoupsw_chunk006.mp3
- tmpctqoupsw_chunk007.mp3
- tmpctqoupsw_chunk008.mp3
- tmpctqoupsw_chunk009.mp3
- tmpctqoupsw_chunk010.mp3

---

## 🔴 ERRORES DETECTADOS

### Azure OpenAI API (1 errores)

**Error:** `Unexpected Response: 404 (Not Found)
Raw response content:
b'{"status":{"error":"Not found: Collecti`  
**Ocurrencias:** 1  
**Evento:** `api.familiarization.error`  

---

## ⚠️ ADVERTENCIAS

Total: **11** advertencias

| Tipo de Evento | Cantidad |
|----------------|----------|
| `ingest.fragment.flagged` | 10 |
| `qdrant.upsert.split` | 1 |

---

## ✅ OPERACIONES REALIZADAS

### Ingesta de Documentos: 18 eventos


### Transcripción de Audio: 40 eventos


### Análisis Cualitativo: 30 eventos


---

## 🗄️ OPERACIONES DE BASE DE DATOS

| Base de Datos | Operaciones |
|---------------|-------------|
| Neo4j | 0 |
| Qdrant | 5 |
| PostgreSQL | 0 |

---

## 📊 EVENTOS MÁS FRECUENTES

| Evento | Cantidad |
|--------|----------|
| `analysis.axial.persisted` | 20 |
| `transcribe_chunked.chunk` | 11 |
| `transcription.start` | 11 |
| `transcription.complete` | 11 |
| `ingest.fragment.flagged` | 10 |
| `api.familiarization.fragments` | 6 |
| `qdrant.upsert.success` | 4 |
| `ingest.batch` | 3 |
| `coding.assign` | 3 |
| `ingest.file.start` | 2 |
| `ingest.file.end` | 2 |
| `analyze.sync.start` | 2 |
| `analysis.persist.linkage_metrics` | 2 |
| `analyze.sync.persisted` | 2 |

---

*Informe generado automáticamente por `scripts/generate_log_report.py`*