# INFORME COMPLETO DE ANÁLISIS DE LOGS
## Sistema de Análisis Cualitativo - APP_Jupter

**Fecha de generación:** 20 de Diciembre de 2025  
**Período analizado:** 11 - 20 de Diciembre de 2025  
**Autor:** Análisis automatizado  

---

## 📋 RESUMEN EJECUTIVO

El sistema ha procesado un volumen significativo de operaciones durante el período analizado, incluyendo:
- **Ingesta de documentos DOCX** con fragmentación y embeddings
- **Transcripción de audio** con diarización de hablantes
- **Análisis cualitativo** con LLM (codificación abierta, axial, GraphRAG)
- **Almacenamiento multi-base** (Qdrant, Neo4j, PostgreSQL)

### Proyectos Activos Identificados
| Proyecto | Estado | Actividad Principal |
|----------|--------|---------------------|
| nubeweb | Activo | Análisis de entrevistas comunitarias |
| baba | Activo | Análisis cualitativo |
| prueba-2 | Pruebas | Testing del sistema |
| loadtest | Testing | Pruebas de carga |
| default | Sistema | Configuración por defecto |

---

## 🔴 ERRORES CRÍTICOS IDENTIFICADOS

### 1. Errores de API de Azure OpenAI

#### 1.1 Incompatibilidad de parámetros con modelos de transcripción
**Frecuencia:** Alta (múltiples ocurrencias)  
**Fechas afectadas:** 17, 15 de Diciembre

```json
{
  "status": 400,
  "error": "response_format 'verbose_json' is not compatible with model 'gpt-4o-transcribe-diarize'. Use 'json' or 'text' instead."
}
```

**Impacto:** Transcripciones de audio fallaron para 6 chunks de un archivo de 25MB.

**Recomendación:** Actualizar `app/transcription.py` para usar `response_format='json'` cuando se utilice el modelo `gpt-4o-transcribe-diarize`.

---

#### 1.2 Falta de chunking_strategy para diarización
**Frecuencia:** Media  
**Fecha:** 15 de Diciembre

```json
{
  "status": 400,
  "error": "chunking_strategy is required for diarization models"
}
```

**Recomendación:** Agregar parámetro `chunking_strategy` en las llamadas al modelo de diarización.

---

#### 1.3 Parámetro max_tokens no soportado
**Frecuencia:** Alta  
**Fechas:** 15, 16 de Diciembre

```json
{
  "error": "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead."
}
```

**Módulos afectados:** 
- `app/graphrag.py`
- `app/analysis.py`

**Recomendación:** Migrar de `max_tokens` a `max_completion_tokens` para compatibilidad con modelos o1 y GPT-4o.

---

#### 1.4 Parámetro temperature no soportado
**Fecha:** 16 de Diciembre

```json
{
  "error": "Unsupported value: 'temperature' does not support 0.3 with this model. Only the default (1) value is supported."
}
```

**Módulo afectado:** `api.analyze_predictions`

---

### 2. Errores de Servidor Azure (5XX)

#### 2.1 Error interno del servidor
**Fecha:** 17 de Diciembre
```json
{
  "status": 500,
  "error": "The server had an error processing your request.",
  "request_id": "68d24949-7164-430e-9859-5cfe11f59c6e"
}
```

**Impacto:** Chunk 7 de 15 falló durante transcripción.

---

### 3. Errores de Conectividad

#### 3.1 Timeouts de conexión HTTP
**Fechas:** 15 de Diciembre (múltiples)

```
httpx.ConnectTimeout: [WinError 10060] Se produjo un error durante el intento de conexión
httpx.ReadTimeout: The read operation timed out
```

**Impacto:** Transcripciones de archivos grandes (~20MB) fallaron después de ~10 minutos.

**Recomendación:** 
- Aumentar timeout en cliente httpx
- Implementar reintentos con backoff exponencial

---

#### 3.2 Error de decodificación UTF-8
**Fecha:** 13 de Diciembre
**Frecuencia:** ~10 ocurrencias consecutivas

```json
{
  "error": "'utf-8' codec can't decode byte 0xab in position 96: invalid start byte",
  "event": "api.clients.error"
}
```

**Módulo:** `app.api` - Conexión de clientes

---

### 4. Errores de Neo4j GDS

#### 4.1 Proyección de nodos fallida
**Frecuencia:** Alta (múltiples días)
**Módulo:** `app/axial.py`

```json
{
  "error": "Invalid node projection, one or more labels not found: 'Categoria, Codigo'",
  "event": "gds.projection_failed_fallback_native"
}
```

**Causa raíz:** Los labels `Categoria` y `Codigo` no existen en la base de datos Neo4j cuando se intenta ejecutar algoritmos GDS.

**Mitigación actual:** El sistema hace fallback a algoritmos nativos de Cypher.

---

#### 4.2 Dependencia faltante: scipy
**Fecha:** 12 de Diciembre

```json
{
  "error": "No module named 'scipy'",
  "event": "api.gds.error"
}
```

**Recomendación:** Agregar `scipy` a `requirements.txt` y reinstalar dependencias.

---

### 5. Errores de Análisis Cualitativo

#### 5.1 Tipos de relación inválidos
**Frecuencia:** Muy alta
**Patrón consistente:**

```json
{
  "error": "Tipo de relacion 'relacion' invalido. Debe ser uno de: causa, condicion, consecuencia, partede.",
  "event": "analysis.axial.error"
}
```

**Archivos afectados:**
- Trancripción_Patricio_Yañez.docx
- Natalia Molina.docx
- test_ingesta.docx

**Causa raíz:** El LLM está generando "relacion" como tipo genérico en lugar de los tipos específicos permitidos.

**Recomendación:** Mejorar el prompt del sistema para análisis axial, enfatizando los tipos válidos.

---

### 6. Errores de Qdrant

#### 6.1 Índice requerido no encontrado
**Fecha:** 16 de Diciembre

```json
{
  "error": "Index required but not found for \"project\" of one of the following types: [keyword]",
  "event": "api.familiarization.error"
}
```

**Impacto:** Endpoint de familiarization fallando para búsquedas por proyecto.

**Recomendación:** Crear índice de tipo keyword para el campo `project` en la colección de Qdrant.

---

#### 6.2 Timeout en upsert grande
**Fecha:** 15 de Diciembre

```json
{
  "size": 44,
  "reason": "The write operation timed out",
  "event": "qdrant.upsert.split"
}
```

**Mitigación actual:** El sistema divide automáticamente los batches grandes.

---

### 7. Errores de Discovery API

#### 7.1 Validación de embeddings fallida
**Frecuencia:** Alta  
**Fechas:** 14, 15 de Diciembre

```json
{
  "error": "8 validation errors for DiscoverRequest - context.0.positive.list[float].0: Input should be a valid number"
}
```

**Causa raíz:** Los embeddings se pasan como lista de listas en lugar de lista plana.

**Módulo afectado:** `app/queries.py`

---

## ⚠️ WARNINGS IMPORTANTES

### 1. Neo4j - Elementos no encontrados

| Tipo | Elemento | Frecuencia |
|------|----------|------------|
| Label | `Categoria` | Alta |
| Label | `Codigo` | Alta |
| Label | `User`, `Question`, `Answer` | Media |
| RelType | `REL` | Alta |
| RelType | `TIENE_CODIGO` | Alta |
| Property | `score_centralidad` | Media |
| Property | `community_id` | Media |
| Property | `fragmento_id` | Media |
| Property | `evidencia` | Media |

**Interpretación:** El esquema de Neo4j no coincide con las consultas esperadas. Posiblemente la base de datos fue reiniciada o el esquema cambió.

---

### 2. Fragmentos con problemas de calidad

**Patrón detectado:** `filler_repetition`  
**Descripción:** Fragmentos con muletillas o repeticiones excesivas

**Archivos más afectados:**
| Archivo | Fragmentos Flagged |
|---------|-------------------|
| Guillermo Orestes.docx | 13 |
| Pablo_Fabrega.docx | 19 |
| Trancripción_Camilo_Colegio_Cayenel.docx | 12 |

---

## ✅ OPERACIONES EXITOSAS

### 1. Ingestas Completadas

| Fecha | Proyecto | Archivo | Fragmentos | Tokens Procesados |
|-------|----------|---------|------------|-------------------|
| 12/12 | nubeweb | Guillermo Orestes.docx | 44 | 4,061 |
| 12/12 | nubeweb | Natalia Molina.docx | 24 | 2,782 |
| 12/12 | prueba-2 | Trancripción_Patricio_Yañez.docx | 23 | 2,464 |
| 15/12 | nubeweb | Claudia_Cesfam.docx | 21 | 1,263 |
| 15/12 | nubeweb | Pablo_Fabrega.docx | 34 | 5,358 |
| 15/12 | nubeweb | Trancripción_Camilo_Colegio_Cayenel.docx | 29 | 3,582 |
| 15/12 | nubeweb | Trancripción_Elba.docx | 25 | 3,459 |
| 16/12 | nubeweb | EntrevistaJardinInfantil_UVJuanPabloII.docx | 4 | 2,047 |

---

### 2. Transcripciones de Audio Exitosas

| Fecha | Archivo Original | Duración | Chunks | Speakers |
|-------|-----------------|----------|--------|----------|
| 17/12 | Audio 64MB | 70min | 15 | 1 |
| 17/12 | Audio 65MB | 94min | 19 | 1 |

**Nota:** Optimización de audio efectiva (reducción ~50% tamaño).

---

### 3. Análisis Axial Persistidos

**Proyecto baba (14/12):**
- 10 relaciones procesadas
- 100% linkage rate
- Categorías: `contexto_histórico_y_social`, `labor_formativa_y_valores`, `barreras_y_conflictos`

**Proyecto nubeweb (15/12):**
- Categorías: `deporte_como_prevencion_e_inclusion_social`, `barreras_institucionales_y_estructurales`
- Tipos de relación: `partede`, `causa`

---

### 4. Consultas GraphRAG Completadas

| Fecha | Proyecto | Query | Nodos | Respuesta (chars) |
|-------|----------|-------|-------|-------------------|
| 15/12 | nubeweb | "que teoría emerge de la codificación" | 0 | 2,741 |
| 15/12 | default | "que significado le asignan los entrevistados" | 0 | 3,303 |
| 16/12 | nubeweb | "relación inundación calles" | 0 | 2,654 |
| 16/12 | nubeweb | "relación desarrollo urbano problemas" | 0 | 2,234 |

**Observación:** Todas las consultas retornan 0 nodos del grafo, indicando que el contexto viene principalmente de la búsqueda vectorial.

---

### 5. Link Prediction Funcionando

| Fecha | Algoritmo | Candidatos | Retornados |
|-------|-----------|------------|------------|
| 14/12 | preferential_attachment | 412 | 10 |
| 16/12 | preferential_attachment | 1,163 | 10 |
| 16/12 | preferential_attachment | 3,505 | 10 |

---

### 6. Semantic Discovery (Fallback)

**Estado:** Operativo con fallback a weighted vector search

```json
{
  "reason": "weighted vector search",
  "event": "discover.using_fallback",
  "results": 10
}
```

---

## 📊 MÉTRICAS DE USO

### Reinicios del Sistema
| Fecha | Cantidad de Reinicios |
|-------|----------------------|
| 11/12 | 35+ |
| 12/12 | 45+ |
| 13/12 | 30+ |
| 14/12 | 25+ |
| 15/12 | 40+ |
| 16/12 | 35+ |
| 17/12 | 5+ |

**Observación:** Alta frecuencia de reinicios indica desarrollo activo o inestabilidad.

---

### Distribución de Niveles de Log

| Nivel | Porcentaje Aproximado |
|-------|----------------------|
| info | 75% |
| warning | 15% |
| error | 10% |

---

## 🔧 RECOMENDACIONES DE ACCIÓN

### Alta Prioridad

1. **Actualizar parámetros de API Azure:**
   - Cambiar `max_tokens` → `max_completion_tokens`
   - Cambiar `response_format='verbose_json'` → `response_format='json'`
   - Agregar `chunking_strategy` para diarización
   - Remover o ajustar `temperature` para modelos que no lo soportan

2. **Crear índices en Qdrant:**
   ```python
   client.create_payload_index(
       collection_name="fragmentos",
       field_name="project",
       field_schema=models.PayloadSchemaType.KEYWORD
   )
   ```

3. **Instalar dependencia faltante:**
   ```bash
   pip install scipy
   ```

4. **Mejorar prompt de análisis axial:**
   - Enfatizar tipos válidos: `causa`, `condicion`, `consecuencia`, `partede`
   - Agregar ejemplos en el prompt

### Media Prioridad

5. **Aumentar timeouts HTTP para transcripciones largas**

6. **Implementar health check de Neo4j** antes de ejecutar GDS

7. **Corregir formato de embeddings** en Discovery API

### Baja Prioridad

8. **Optimizar frecuencia de logging_configured** (demasiados eventos repetidos)

9. **Agregar métricas de monitoreo** (Prometheus/Grafana)

---

## 📁 ARCHIVOS DE LOG ANALIZADOS

| Archivo | Líneas | Período |
|---------|--------|---------|
| app.jsonl.2025-12-11 | ~100 | 01:26 - 02:54 UTC |
| app.jsonl.2025-12-12 | 209 | 03:02 - 14:24 UTC |
| app.jsonl.2025-12-13 | 245 | 16:53 - 02:58 UTC+1 |
| app.jsonl.2025-12-14 | 200 | 03:00 - 04:27 UTC |
| app.jsonl.2025-12-15 | 476 | 03:02 - 18:50 UTC |
| app.jsonl.2025-12-16 | 338 | 03:23 - 23:48 UTC |
| app.jsonl.2025-12-17 | 344 | 17:03 - 18:26 UTC |

---

## 🔍 PATRONES IDENTIFICADOS

### 1. Flujo de trabajo típico
```
logging_configured → project.created → ingest.file.start → 
qdrant.upsert.success → ingest.batch → ingest.file.end → 
analyze.queued → analysis.persist.linkage_metrics → 
analysis.axial.persisted → analyze.persisted_manual
```

### 2. Flujo de transcripción
```
audio.optimize.success → transcribe_chunked.start → 
split_audio.start → split_audio.complete → 
transcribe_chunked.chunk (×N) → transcription.complete → 
transcribe_chunked.complete → api.transcribe.saved
```

### 3. Flujo de consulta GraphRAG
```
api.graphrag.start → graphrag.query_start → 
graphrag.subgraph_extracted → graphrag.query_complete → 
api.graphrag.complete → report.saved
```

---

## 📈 CONCLUSIONES

1. **El sistema está operativo** pero con varios errores de compatibilidad con APIs de Azure OpenAI.

2. **Neo4j GDS tiene problemas de esquema** - los algoritmos hacen fallback a Cypher nativo.

3. **La ingesta funciona correctamente** con buen rendimiento en fragmentación y embeddings.

4. **Las transcripciones de audio** funcionan para archivos pequeños pero fallan en archivos grandes.

5. **El análisis axial** requiere ajustes en el prompt para generar tipos de relación válidos.

6. **La Discovery API** necesita corrección en el formato de embeddings.

---

*Informe generado automáticamente - Sistema APP_Jupter*
