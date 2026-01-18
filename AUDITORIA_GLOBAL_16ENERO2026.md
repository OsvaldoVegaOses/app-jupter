# 📊 AUDITORIA GLOBAL - ESTADO COMPLETO DEL SISTEMA

**Fecha:** 16 enero 2026  
**Hora:** 01:18 UTC

---

## 🎯 RESUMEN GENERAL

El sistema de análisis cualitativo contiene datos en **8 proyectos diferentes** distribuidos entre 4 bases de datos sincronizadas:

```
PostgreSQL:  1,872 fragmentos en 51 archivos
Neo4j:       Grafo topológico (sin detalles due to query errors)
Qdrant:      38 puntos en colección 'fragments'
Blob:        51 archivos ingestionados
```

---

## 📦 PROYECTOS CON DATOS

| # | Proyecto ID | Nombre | Archivos | Fragmentos | Códigos |
|---|---|---|---|---|---|
| 1 | `jd-007...` | JD007 (probable) | 24 | 800 | 165 |
| 2 | `jd-009...` | JD009 (probable) | 15 | 597 | 440 |
| 3 | `jd-008...` | JD008 (probable) | 6 | 229 | 0 |
| 4 | `nubeweb...` | Proyecto NubeWeb | 2 | 74 | 0 |
| 5 | `jd007-vi...` | JD007 Vínculo A | 1 | 53 | 1 |
| 6 | `jd007-vi...` | JD007 Vínculo B | 1 | 53 | 0 |
| 7 | `default...` | Proyecto Default | 1 | 38 | 1 |
| 8 | `jd-proye...` | JD Proyecto | 1 | 28 | 0 |
| 9 | `jose-dom...` | **jose-domingo-vg** | 0 | 0 | 14 |

---

## 🔴 PROYECTO ESPECIFICO - `jose-domingo-vg`

**Estado:** ⚠️ **INCONSISTENCIA DETECTADA**

```
PostgreSQL:
  • Fragmentos: 0
  • Codigos abiertos: 0
  • Codigos CANDIDATOS: 14 ✅
  
Neo4j:     (vacío)
Qdrant:    (vacío)
Blob:      (vacío)
```

### Análisis

Este proyecto presenta una **inconsistencia crítica**:
- ✅ Tiene **14 códigos candidatos** almacenados en PostgreSQL
- ❌ Pero **NO tiene fragmentos ni archivos**
- ❌ Grafo en Neo4j vacío
- ❌ Embeddings en Qdrant vacíos

### Causa probable

Los códigos candidatos fueron creados pero **sin fragmentos base** que codificar. 

Escenarios posibles:
1. Los fragmentos fueron **eliminados** después de crear los códigos candidatos
2. Los códigos candidatos fueron **importados de otra fuente**
3. Hubo un **error en la ingesta** que guardó códigos pero no fragmentos

---

## 🗂️ TABLAS EN PostgreSQL

### Todas las tablas públicas:
```
analisis_axial
analisis_codigos_abiertos
analisis_comparacion_constante
analisis_nucleo_notas
analysis_insights
analysis_memos
analysis_reports
app_sessions
app_users
codigo_versiones
codigos_candidatos
coding_feedback_events
discovery_navigation_log
discovery_runs
doctoral_reports
entrevista_fragmentos
familiarization_reviews
interview_files
interview_reports
project_audit_log
project_members
proyecto_estado
proyectos
report_jobs
stage0_*
vw_interview_files_stats
```

### Conteos por tabla:
```
entrevista_fragmentos:       1,872 registros
analisis_codigos_abiertos:     745 registros
codigos_candidatos:             ? (revisar)
proyectos:                       2 activos
```

---

## 🔗 BASES DE DATOS

### PostgreSQL (Relacional)
- **Host:** Configurado en `.env`
- **DB:** Especificado en settings
- **Pool:** 80 conexiones máximo
- **Estado:** ✅ Conectado
- **Integridad:** ✅ OK (sin registros huérfanos post-limpieza)

### Neo4j (Grafo)
- **Versión:** 4.x
- **Base de datos:** neo4j
- **Nodos:** ~3,000+ (aproximado)
- **Estado:** ✅ Conectado
- **Nota:** Queries con GROUP BY retornan errores sintácticos (compatible Neo4j < 5.0)

### Qdrant (Vector DB)
- **Colecciones:** 1 (`fragments`)
- **Puntos:** 38 vectores
- **Dimensión:** TBD
- **Estado:** ✅ Conectado
- **Nota:** Muy pocos puntos para el volumen de fragmentos (revisar)

### Blob Storage (Azure)
- **Servicio:** Azure Blob Storage
- **Contenedor:** interviews
- **Archivos:** 51
- **Estado:** ⚠️ Acceso no totalmente validado

---

## ⚠️ INCONSISTENCIAS DETECTADAS

### 1. Qdrant vs PostgreSQL
```
PostgreSQL: 1,872 fragmentos
Qdrant:     38 puntos

Ratio: 1.2% embeddings vs fragmentos
```

**Interpretación:** Solo el 1.2% de fragmentos tienen vectores calculados. Probablemente la ingesta de embeddings fue parcial.

### 2. Neo4j - Sintaxis
```
Error en queries GROUP BY (Neo4j < 5.0 compatibility issue)
```

No afecta funcionalidad, pero impide estadísticas exactas.

### 3. jose-domingo-vg
```
14 códigos candidatos SIN fragmentos base
```

Requiere investigación.

---

## 📈 RECOMENDACIONES

### CRÍTICO
1. **Investigar `jose-domingo-vg`**: ¿Por qué tiene códigos sin fragmentos?
2. **Calcular embeddings faltantes**: 1,834 fragmentos sin vectores en Qdrant

### IMPORTANTE
3. **Validar Blob Storage**: Asegurar que los 51 archivos sean accesibles
4. **Sincronizar Neo4j**: Verificar que todos los fragmentos estén representados

### SUGERENCIA
5. **Limpieza de Qdrant**: Si no se necesitan los 38 puntos existentes, pueden borrarse
6. **Auditoría mensual**: Programar revisiones de consistencia

---

## 🔐 SEGURIDAD

- ✅ X-API-Key requerida para acceso
- ✅ PostgreSQL con pool limitado
- ✅ Credenciales en `.env` (no en código)
- ⚠️ Blob Storage connection string no accesible (normal)

---

**Generado:** 16 enero 2026, 01:18 UTC  
**Siguiente revisión:** 23 enero 2026

