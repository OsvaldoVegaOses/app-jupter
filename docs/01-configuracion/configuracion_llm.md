# Configuración del LLM (Azure OpenAI)

> **Última actualización:** Diciembre 2024

---

## Resumen

Esta aplicación utiliza **Azure OpenAI** para el análisis cualitativo asistido por IA. El LLM procesa fragmentos de entrevistas y genera códigos, categorías y relaciones axiales siguiendo la metodología de Grounded Theory.

---

## Configuración Principal

### Archivo: `.env`

```env
# Azure OpenAI
AZURE_OPENAI_ENDPOINT="https://eastus2.api.cognitive.microsoft.com/"
AZURE_OPENAI_API_KEY="tu-api-key"
AZURE_OPENAI_API_VERSION="2024-12-01-preview"
AZURE_OPENAI_DEPLOYMENT_EMBED=text-embedding-3-large
AZURE_OPENAI_DEPLOYMENT_CHAT="gpt-5.2-chat"
AZURE_DEPLOYMENT_GPT5_MINI=gpt-5-mini
```

| Variable | Propósito |
|----------|-----------|
| `AZURE_OPENAI_ENDPOINT` | URL del recurso Azure OpenAI |
| `AZURE_OPENAI_API_KEY` | Clave de autenticación |
| `AZURE_OPENAI_API_VERSION` | Versión de la API (ej: 2024-12-01-preview) |
| `AZURE_OPENAI_DEPLOYMENT_EMBED` | Modelo para embeddings (vectores) |
| `AZURE_OPENAI_DEPLOYMENT_CHAT` | Modelo principal para análisis LLM |
| `AZURE_DEPLOYMENT_GPT5_MINI` | Modelo alternativo para tareas ligeras |

---

## Archivos de Configuración

### 1. `app/settings.py`

Carga las variables de entorno y las expone como `AppSettings`:

```python
# Líneas 245-255
azure = AzureSettings(
    endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    deployment_embed=os.getenv("AZURE_OPENAI_DEPLOYMENT_EMBED"),
    deployment_chat=os.getenv("AZURE_OPENAI_DEPLOYMENT_CHAT"),
    deployment_chat_mini=os.getenv("AZURE_DEPLOYMENT_GPT5_MINI"),
)
```

### 2. `app/clients.py`

Construye el cliente `AzureOpenAI`:

```python
from openai import AzureOpenAI

client = AzureOpenAI(
    azure_endpoint=settings.azure.endpoint,
    api_key=settings.azure.api_key,
    api_version=settings.azure.api_version
)
```

---

## Uso del LLM en la Aplicación

### Funcionalidades Principales

| Módulo | Función | Propósito |
|--------|---------|-----------|
| `app/analysis.py` | `analyze_interview_text()` | Análisis completo (Etapas 0-4) |
| `app/coding.py` | `suggest_codes()` | Sugerencia de códigos similares |
| `app/nucleus.py` | `generate_nucleus_summary()` | Resumen del núcleo teórico |
| `app/graphrag.py` | `graphrag_query()` | Consultas con contexto de grafo |

### Flujo de Análisis (Etapas 0-4)

```
Fragmentos → LLM → JSON estructurado
                    ├── etapa0: Observaciones reflexivas
                    ├── etapa1: Resumen general
                    ├── etapa2: Análisis descriptivo
                    ├── etapa3: Matriz de códigos abiertos
                    └── etapa4: Codificación axial
```

---

## Resolución de Modelos

Los archivos `app/coding.py` y `app/nucleus.py` contienen funciones para resolver aliases de modelos:

```python
def _resolve_llm_model(settings, alias):
    normalized = alias.strip().lower()
    if normalized in {"gpt-5-mini", "mini"}:
        return settings.azure.deployment_chat_mini
    if normalized in {"gpt-5.2-chat", "gpt-5-chat", "chat"}:
        return settings.azure.deployment_chat
    return alias
```

### Modelos Soportados (CLI)

```bash
--llm-model gpt-5.2-chat   # Modelo principal
--llm-model gpt-5-chat     # Alias
--llm-model gpt-5-mini     # Modelo ligero
--llm-model gpt-4o-mini    # Alternativa
```

---

## Endpoints que Usan LLM

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/analyze` | POST | Ejecuta análisis completo |
| `/api/graphrag/query` | POST | Consulta con contexto de grafo |
| `/api/coding/suggest` | POST | Sugerencias de códigos |

---

## Celery Worker

El análisis LLM se ejecuta en background usando Celery:

```
backend/celery_worker.py → task_analyze_interview()
                           ├── load_settings()
                           ├── build_service_clients()
                           └── analyze_interview_text()
```

**Importante:** El worker debe reiniciarse después de cambiar el `.env`.

---

## Prompts del Sistema

### Ubicación

El prompt principal para análisis cualitativo está en `app/analysis.py`:

```python
QUAL_SYSTEM_PROMPT = """
Eres un analista cualitativo experto en Grounded Theory...
"""
```

### Estructura de Salida Esperada

```json
{
  "etapa0_observaciones": "...",
  "etapa1_resumen": "...",
  "etapa2_descriptivo": {...},
  "etapa3_matriz_abierta": [...],
  "etapa4_axial": [...]
}
```

---

## Verificación

### Test de Conexión

```bash
python scripts/test_azure_openai.py
```

### Verificar Configuración Cargada

```python
from app.settings import load_settings
settings = load_settings()
print(settings.azure.deployment_chat)  # gpt-5.2-chat
```

---

## Troubleshooting

| Problema | Causa | Solución |
|----------|-------|----------|
| `try again` | Rate limit o modelo incorrecto | Verificar deployment name en Azure |
| `PENDING` | Worker no procesa | Reiniciar Celery worker |
| `Unauthorized` | API key inválida | Verificar `AZURE_OPENAI_API_KEY` |
| Modelo incorrecto | Variable desalineada | Verificar que `.env` coincida con portal Azure |

---

*Documento generado: Diciembre 2024*
