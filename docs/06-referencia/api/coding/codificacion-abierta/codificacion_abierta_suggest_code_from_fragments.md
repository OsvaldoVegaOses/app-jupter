# Ficha metodológica: `suggest_code_from_fragments()` (Sugerencia de código con IA)

> **Fecha**: 2026-01-20
>
> **Código fuente**: `app/coding.py`
>
> **Endpoint relacionado**: `POST /api/coding/suggest-code`

## 1) Resumen

`suggest_code_from_fragments()` propone un **nombre de código** y un **memo** a partir de una selección de fragmentos, usando un LLM. Es un asistente: no valida ni fusiona automáticamente; entrega una propuesta con nivel de confianza.

## 2) Fundamento teórico

En codificación abierta asistida, el LLM se usa como apoyo para:

- Sintetizar convergencias temáticas entre incidentes.
- Proponer un rótulo consistente.
- Redactar un memo breve que capture propiedades y alcance.

La decisión final permanece en el analista (gobernanza).

## 3) Firma e inputs

- `fragments`: lista de fragmentos (texto, score opcional).
- `existing_codes`: lista de códigos existentes (para reducir duplicación nominal).
- `llm_model`: alias/modelo.
- `project`: proyecto.

La función limita el análisis a un máximo de 5 fragmentos (por costo y latencia).

## 4) Salida

`dict` con:

- `suggested_code`: string en `snake_case`.
- `memo`: 2–3 oraciones.
- `confidence`: `alta|media|baja`.
- En fallos: `error` + degradación de contenido.

## 5) Flujo interno (alto nivel)

1. Valida que existan fragmentos.
2. Resuelve modelo (`_resolve_llm_model`) o usa `settings.azure.deployment_chat`.
3. Construye prompt con:
   - excerpt de fragmentos,
   - lista parcial de códigos existentes (hasta 20).
4. Llama a AOAI Chat Completions.
5. Intenta parsear JSON del contenido (regex + `json.loads`).
6. Si no hay JSON o falla parseo, retorna respuesta degradada con memo/diagnóstico.

## 6) Persistencia y side-effects

- No escribe en DB por sí misma.
- Efecto principal: llamada al LLM.

## 7) Errores y validaciones

- Manejo robusto de:
  - contenido vacío,
  - JSON incompleto,
  - truncación.

Registra logs (`coding.suggest_code.*`) para diagnóstico.

## 8) Parámetros operativos / calibración

- Si el modelo devuelve JSON inválido con frecuencia, bajar complejidad del prompt o subir `max_completion_tokens`.
- Recomendar al usuario: si confianza es `baja`, tratar como hipótesis, no como código definitivo.

## 9) Referencias internas

- `app/coding.py` (`suggest_code_from_fragments`, `_resolve_llm_model`)
- `backend/app.py` (`POST /api/coding/suggest-code`)
