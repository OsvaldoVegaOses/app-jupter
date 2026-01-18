# Configuración de Transcripción de Audio

## Arquitectura del Sistema

```mermaid
flowchart LR
    subgraph Frontend
        UI[TranscriptionPanel.tsx]
    end
    subgraph Backend
        API[/api/transcribe]
        MERGE[/api/transcribe/merge]
    end
    subgraph Azure
        AOAI[gpt-4o-transcribe-diarize]
    end
    
    UI -->|POST audio_base64| API
    API -->|chunked audio| AOAI
    AOAI -->|json response| API
    API -->|TranscriptionResult| UI
    UI -->|segments + text| MERGE
    MERGE -->|docx_base64| UI
```

---

## Configuración Actual

| Parámetro | Valor | Ubicación |
|-----------|-------|-----------|
| **Idioma** | `es` (Español) | `TranscriptionPanel.tsx:131` |
| **Diarización** | `true` (habilitado) | `TranscriptionPanel.tsx:130` |
| **Modelo** | `gpt-4o-transcribe-diarize` | `.env` → `AZURE_OPENAI_DEPLOYMENT_TRANSCRIBE_DIARIZE` |
| **Formato respuesta** | `json` | `transcription.py:378` |
| **Chunking** | `auto` | `transcription.py:377` |
| **Max chunk** | 5 min (300s) | `transcription.py:66` |
| **Max archivo** | 25 MB | `transcription.py:62` |

---

## Flujo de Transcripción Síncrono

### ¿Por qué se mantiene síncrono en lugar de Celery?

El sistema originalmente usaba el endpoint asíncrono `/api/transcribe/batch` con Celery, pero se cambió a síncrono por las siguientes razones:

1. **Worker Celery no procesaba tareas**: Las tareas quedaban en estado `PENDING` indefinidamente
2. **Sin logs de worker**: Nunca se registró `task.transcribe.start` en los logs
3. **Simplicidad**: El endpoint síncrono `/api/transcribe` funciona correctamente
4. **Fiabilidad**: Respuesta inmediata sin dependencias externas

### Trade-offs

| Aspecto | Síncrono ✅ | Asíncrono (Celery) ❌ |
|---------|------------|----------------------|
| Fiabilidad | Alta | Requiere worker funcional |
| Paralelismo | Secuencial | Paralelo |
| Complejidad | Baja | Alta (Redis + Worker) |
| Timeout | Manejable | N/A (worker caído) |

---

## Cambios Realizados (2025-12-17)

### 1. Corrección de Error de API Azure

**Problema**: El modelo `gpt-4o-transcribe-diarize` dejó de soportar `response_format: verbose_json`

**Error**:
```json
{
  "error": {
    "message": "response_format 'verbose_json' is not compatible with model 'gpt-4o-transcribe-diarize'. Use 'json' or 'text' instead.",
    "type": "invalid_request_error"
  }
}
```

**Solución**: Cambiar a `response_format: json` en `transcription.py:378`

```diff
- data["response_format"] = "verbose_json"
+ data["response_format"] = "json"
```

### 2. Cambio a Endpoint Síncrono

**Archivo**: `TranscriptionPanel.tsx` (líneas 286-382)

**Antes**: Usaba `/api/transcribe/batch` + polling de status
**Ahora**: Usa `/api/transcribe` directamente

### 3. Descarga Individual de Transcripciones

**Nueva función**: `downloadSingleDocx(result)` en `TranscriptionPanel.tsx:412-438`

Permite descargar cada transcripción como DOCX individual:
- Inmediatamente después de completar
- En cualquier momento posterior

### 4. Validación Backend de Merge

**Archivo**: `backend/app.py` (líneas 1120-1135)

Agregada validación para rechazar merge de transcripciones vacías:
```python
if valid_count == 0:
    raise HTTPException(
        status_code=400,
        detail="Las transcripciones no tienen contenido..."
    )
```

---

## Variables de Entorno Requeridas

```env
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT_TRANSCRIBE_DIARIZE=gpt-4o-transcribe-diarize

# Opcional: modelo sin diarización
AZURE_OPENAI_DEPLOYMENT_TRANSCRIBE=gpt-4o-transcribe
```

---

## Limitaciones Conocidas

1. **Bilingüismo**: El modelo puede mezclar español/inglés en transcripciones
2. **Muletillas**: No se filtran automáticamente ("eh", "este", "como que")
3. **Errores OCR de voz**: Palabras truncas o incoherentes ocasionales
4. **Solapamiento**: Dificultad en separar speakers cuando hablan simultáneamente

### Mejoras Futuras Propuestas

- Post-procesamiento con LLM para limpiar texto
- Filtro de muletillas conocidas
- Validación ortográfica con diccionario español
