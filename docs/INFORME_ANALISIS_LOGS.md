# 📊 Informe de Análisis de Logs - Sistema de Análisis Cualitativo

**Fecha de generación:** 20 de diciembre de 2025  
**Período analizado:** 11 - 20 de diciembre de 2025  
**Total de archivos de log:** 15 (10 logs de aplicación + 5 resultados de load tests)

---

## 📋 Resumen Ejecutivo

El análisis de los logs revela un sistema en desarrollo activo con patrones de uso regular, algunos problemas recurrentes de infraestructura y oportunidades de mejora en la resiliencia de servicios externos.

### Indicadores Clave
| Métrica | Valor |
|---------|-------|
| Días con actividad | 10 |
| Proyectos activos | 6+ (nubeweb, prueba, nerd, perro, loadtest, default) |
| Archivos procesados | ~50+ documentos |
| Fragmentos totales ingestados | 200+ |
| Tasa de éxito de ingestión | ~85% |

---

## 🔴 Errores Críticos Identificados

### 1. Error de Transacción PostgreSQL (InFailedSqlTransaction)
**Frecuencia:** 7 ocurrencias  
**Impacto:** ALTO  
**Afecta:** Persistencia de análisis

```
psycopg2.errors.InFailedSqlTransaction: transacción abortada, 
las órdenes serán ignoradas hasta el fin de bloque de transacción
```

**Ubicación:**
- `backend/app.py` → `api_analyze` (líneas 1827, 1942)
- `app/analysis.py` → `persist_analysis` (línea 276)
- `app/postgres_block.py` → `ensure_open_coding_table` (línea 379)

**Causa raíz:** Transacción previa fallida no limpiada (rollback faltante).

**Recomendación:**
```python
# Agregar manejo de transacción explícito
try:
    with pg_conn.cursor() as cur:
        cur.execute(sql)
    pg_conn.commit()
except Exception as e:
    pg_conn.rollback()  # CRÍTICO: Limpiar estado de transacción
    raise
```

---

### 2. Error de Autenticación PostgreSQL
**Frecuencia:** 11 ocurrencias (concentradas el 18-dic)  
**Impacto:** CRÍTICO  
**Afecta:** Todas las operaciones de base de datos

```
FATAL: password authentication failed for user "postgres"
```

**Contexto:** Ocurrió durante despliegue Docker en ambiente de desarrollo.

**Resolución aplicada:** Se corrigió la variable de entorno `POSTGRES_PASSWORD`.

---

### 3. Colección Qdrant No Existe
**Frecuencia:** 10+ ocurrencias  
**Impacto:** MEDIO  
**Afecta:** Familiarización y búsqueda semántica

```
404 (Not Found) - Collection `fragments` doesn't exist!
```

**Causa:** La colección se elimina al reiniciar Qdrant sin persistencia.

**Recomendación:** 
- Implementar verificación/creación automática de colección en startup
- Configurar volumen persistente para Qdrant en Docker

---

### 4. Timeout en Transcripción
**Frecuencia:** 8+ ocurrencias  
**Impacto:** ALTO  
**Afecta:** Procesamiento de audio largo

```
error: "The read operation timed out"
event: "transcribe_chunked.chunk_error"
```

**Contexto:** Archivos de audio grandes (65MB, ~5600 segundos de duración).

**Chunk sizes observados:**
- Archivos de ~2.3MB por chunk
- 19 chunks totales para archivo de 94 minutos

**Recomendación:**
- Aumentar timeout para operaciones de transcripción
- Implementar reintentos con backoff exponencial
- Considerar procesamiento asíncrono con notificación

---

### 5. Error de API Azure OpenAI (Transcription)
**Frecuencia:** 7 ocurrencias consecutivas (17-dic)  
**Impacto:** CRÍTICO  
**Afecta:** Transcripción con diarización

```
response_format 'verbose_json' is not compatible with 
model 'gpt-4o-transcribe-diarize'. Use 'json' or 'text' instead.
```

**Causa:** Incompatibilidad entre parámetros de API y modelo.

**Recomendación:**
```python
# Cambiar response_format para modelo con diarización
if diarize:
    response_format = "json"  # No usar "verbose_json"
else:
    response_format = "verbose_json"
```

---

### 6. Error de Codificación UTF-8
**Frecuencia:** 12 ocurrencias (load tests)  
**Impacto:** MEDIO  
**Afecta:** Inicialización de clientes

```
'utf-8' codec can't decode byte 0xab in position 96: invalid start byte
```

**Causa probable:** Archivo de configuración o variable de entorno con caracteres especiales.

---

## ⚠️ Advertencias y Problemas Menores

### 1. Tipos de Relación Inválidos en Análisis Axial
**Frecuencia:** 27 ocurrencias  
**Impacto:** BAJO (datos se procesan pero no se persisten relaciones)

```
Tipo de relacion 'relacion' invalido. 
Debe ser uno de: causa, condicion, consecuencia, partede.
```

**Causa:** El LLM genera tipos de relación genéricos en lugar de específicos.

**Recomendación:** Mejorar el prompt del LLM para restringir los tipos de relación válidos.

---

### 2. Fragmentos con Muletillas (filler_repetition)
**Frecuencia:** 42+ advertencias  
**Impacto:** INFORMATIVO  
**Afecta:** Calidad de datos

```
issues: ["filler_repetition"]
```

**Ejemplos de archivos afectados:**
- Pablo_Fabrega.docx (21 fragmentos flagged)
- Claudia_Cesfam.docx (4 fragmentos flagged)
- Trancripción_Camilo_Colegio_Cayenel.docx (13 fragmentos flagged)

**Interpretación:** El sistema correctamente identifica problemas de calidad en transcripciones. Esto es comportamiento esperado para audio conversacional.

---

### 3. Advertencias Neo4j sobre Esquema
**Frecuencia:** Múltiples  
**Impacto:** BAJO

```
warn: label does not exist. The label `Categoria` does not exist
warn: relationship type does not exist. The relationship type `REL`
warn: property key does not exist. The property `fragmento_id`
```

**Causa:** Consultas a base de datos antes de que se creen los nodos/relaciones.

**Recomendación:** Normalizar la inicialización del esquema Neo4j al inicio de la aplicación.

---

## 📊 Estadísticas de Operaciones Exitosas

### Ingestión de Documentos
| Archivo | Fragmentos | Flagged | Tokens Mantenidos |
|---------|------------|---------|-------------------|
| Claudia_Cesfam.docx | 21 | 4 | 1,263 |
| Pablo_Fabrega.docx | 43 | 21 | 5,358 |
| Natalia Molina.docx | 24 | 4 | 2,782 |
| Trancripción_Camilo_Colegio_Cayenel.docx | 34 | 13 | 3,582 |

### Transcripción de Audio
| Métrica | Valor Observado |
|---------|-----------------|
| Optimización promedio | 30-50% reducción de tamaño |
| Tamaño máximo procesado | 65.13 MB (original) → 43.19 MB |
| Duración máxima | 5,661 segundos (~94 minutos) |
| Chunks por archivo largo | 19 |

### Análisis Cualitativo
- **Análisis axiales completados:** 10+
- **Códigos vinculados exitosamente:** 100% tasa de linkage en análisis exitosos
- **Categorías creadas:** 20+

---

## 🔧 Métricas de Rendimiento

### Tiempos de Respuesta Observados
| Operación | Tiempo Típico |
|-----------|---------------|
| Qdrant upsert (21 fragmentos) | 766-3,187 ms |
| Embedding batch | ~1,200 ms |
| Transcripción chunk (5 min) | 2-3 minutos |
| Análisis LLM completo | 15-30 segundos |

### Load Tests (13-dic)
| Test | Archivos | Exitosos | Fallidos | Tiempo Total |
|------|----------|----------|----------|--------------|
| 11:41 | 10 | 0 | 10 | 20.7s |
| 11:46 | 10 | 0 | 10 | - |
| 11:50 | 10 | 0 | 10 | - |
| 13:52 | 10 | 0 | 10 | 44.1s |
| 13:54 | 10 | 0 | 10 | - |

**Nota:** Los load tests fallaron por problemas de autenticación (401) y codificación UTF-8 (502), no por problemas de rendimiento.

---

## 📈 Patrones de Uso

### Horarios de Mayor Actividad
- **Madrugada (03:00-05:00 UTC):** Desarrollo y testing intensivo
- **Mediodía (12:00-14:00 UTC):** Uso productivo
- **Tarde (16:00-18:00 UTC):** Sesiones de transcripción

### Funcionalidades Más Utilizadas
1. **Familiarización** (api.familiarization.fragments) - 50+ llamadas
2. **Ingestión** (ingest.file.start/end) - 30+ archivos
3. **Transcripción** (transcribe_chunked) - 10+ audios
4. **Análisis** (analyze.sync) - 15+ documentos
5. **Discovery** (api.discover) - 10+ búsquedas semánticas
6. **GraphRAG** (api.graphrag) - 5+ consultas

---

## ✅ Recomendaciones Prioritarias

### Críticas (Resolver inmediatamente)
1. **Implementar rollback automático en PostgreSQL** - Evitará cascada de errores InFailedSqlTransaction
2. **Corregir response_format para transcripción con diarización** - Bloquea toda transcripción
3. **Aumentar timeouts para transcripción de audio largo** - Mejorará tasa de éxito

### Importantes (Próxima iteración)
4. **Crear colección Qdrant en startup** - Evitará errores 404 frecuentes
5. **Persistir datos de Qdrant en volumen Docker** - Evitará pérdida de datos
6. **Mejorar prompt LLM para relaciones axiales** - Aumentará calidad de datos

### Deseables (Backlog)
7. **Implementar retry con backoff exponencial para APIs externas**
8. **Agregar monitoreo de salud de servicios (health checks)**
9. **Configurar alertas para errores críticos**
10. **Documentar umbrales de timeout recomendados**

---

## 📁 Archivos de Log Analizados

| Archivo | Líneas | Período |
|---------|--------|---------|
| app.jsonl | 12 | 20-dic |
| app.jsonl.2025-12-19 | 254 | 19-dic |
| app.jsonl.2025-12-18 | 254 | 18-dic |
| app.jsonl.2025-12-17 | 344 | 17-dic |
| app.jsonl.2025-12-16 | - | 16-dic |
| app.jsonl.2025-12-15 | - | 15-dic |
| app.jsonl.2025-12-14 | - | 14-dic |
| app.jsonl.2025-12-13 | 245 | 13-dic |
| app.jsonl.2025-12-12 | - | 12-dic |
| app.jsonl.2025-12-11 | - | 11-dic |
| loadtest_ingest_*.json | 5 files | 13-dic |

---

## 🏁 Conclusión

El sistema muestra un comportamiento generalmente estable con errores localizados y predecibles. Los principales problemas están relacionados con:

1. **Manejo de transacciones PostgreSQL** - Necesita mejora en gestión de errores
2. **Compatibilidad de API Azure OpenAI** - Requiere ajuste de parámetros
3. **Timeouts para operaciones de larga duración** - Configuración insuficiente

La arquitectura multi-servicio (PostgreSQL + Neo4j + Qdrant + Azure OpenAI) funciona correctamente cuando todos los componentes están disponibles. Se recomienda priorizar la resiliencia ante fallos parciales.

---

*Informe generado automáticamente por análisis de logs estructurados (JSONL)*
