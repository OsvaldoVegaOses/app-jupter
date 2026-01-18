# INFORME AUTOMÁTICO DE LOGS
## Sistema de Análisis Cualitativo - APP_Jupter

**Generado:** 2025-12-20 12:43:21  
**Período de logs:** 2025-12-20T03:57:53 → 2025-12-20T14:56:55  
**Total de registros:** 12

---

## 📋 RESUMEN EJECUTIVO

⚠️ **Estado:** 1 error(es) detectado(s)

### Distribución por Nivel

| Nivel | Cantidad | Porcentaje |
|-------|----------|------------|
| 🔴 error | 1 | 8.3% |
| ⚠️ warning | 0 | 0.0% |
| ℹ️ info | 11 | 91.7% |
| 🔍 debug | 0 | 0.0% |

### Proyectos Activos

- `perro`

### Archivos Procesados

Total: **2** archivos

- logs/app.jsonl
- logs\app.jsonl

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

✅ No se detectaron advertencias durante el período analizado.

---

## ✅ OPERACIONES REALIZADAS

---

## 🗄️ OPERACIONES DE BASE DE DATOS

| Base de Datos | Operaciones |
|---------------|-------------|
| Neo4j | 0 |
| Qdrant | 0 |
| PostgreSQL | 0 |

---

## 📊 EVENTOS MÁS FRECUENTES

| Evento | Cantidad |
|--------|----------|
| `api.familiarization.fragments` | 4 |
| `api.familiarization.error` | 1 |

---

*Informe generado automáticamente por `scripts/generate_log_report.py`*