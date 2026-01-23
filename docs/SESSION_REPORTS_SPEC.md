# 📊 Sistema de Informes de Sesión - Especificación

> **Versión:** 1.0  
> **Fecha:** 2026-01-18  
> **Estado:** Implementado

---

## 1. Visión General

Este sistema genera informes estructurados de cada sesión de usuario, transformando logs crudos en insights accionables que alimentan el ciclo de mejora continua de la aplicación.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FLUJO DE MEJORA CONTINUA                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────┐    ┌───────────┐    ┌──────────┐    ┌───────────┐            │
│   │  LOGS    │───▶│ ANÁLISIS  │───▶│ INSIGHTS │───▶│  MEJORAS  │            │
│   │ (JSONL)  │    │ (Script)  │    │ (Report) │    │  (Code)   │            │
│   └──────────┘    └───────────┘    └──────────┘    └───────────┘            │
│        │                                                  │                 │
│        └──────────────────◀───────────────────────────────┘                 │
│                         Ciclo continuo                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Estructura de Directorios de Logs

```
logs/
├── app.jsonl                          # Log global del backend
├── app.jsonl.YYYY-MM-DD              # Logs rotados por fecha
├── llm_errors.jsonl                   # Errores específicos de LLM
├── {project_id}/                      # Logs por proyecto
│   └── {session_id}/                  # Logs por sesión
│       └── app.jsonl                  # Log de sesión específica
├── runner_checkpoints/                # Checkpoints del runner
│   └── {project_id}/
│       ├── coding_suggest_*.jsonl     # Estado del runner
│       └── _errors.jsonl              # Errores del runner
└── runner_reports/                    # Reportes generados
    └── {project_id}/
        └── coding_suggest_*.md        # Informes markdown
```

---

## 3. Estructura del Informe de Sesión

Cada informe contiene las siguientes secciones:

### 3.1 Métricas Generales

| Campo | Tipo | Descripción | Uso para Mejoras |
|-------|------|-------------|------------------|
| `total_requests` | int | Total de requests HTTP | Volumen de uso |
| `successful_requests` | int | Requests con status 2xx/3xx | Tasa de éxito |
| `failed_requests` | int | Requests con status 4xx/5xx | Identificar problemas |
| `warning_count` | int | Eventos de nivel warning | Detectar degradación |
| `duration_minutes` | float | Duración de la sesión | Engagement |

### 3.2 Métricas de Autenticación

| Campo | Tipo | Descripción | Uso para Mejoras |
|-------|------|-------------|------------------|
| `auth_failures` | int | Errores 401 | Problemas de token |
| `auth_success_after_retry` | bool | ¿Se recuperó? | Resiliencia de UX |

### 3.3 Métricas de Infraestructura

| Campo | Tipo | Descripción | Uso para Mejoras |
|-------|------|-------------|------------------|
| `pool_warnings` | int | Warnings de pool PostgreSQL | Configuración de pool |
| `pool_exhaustion_events` | int | Agotamiento de pool | Escalabilidad |

### 3.4 Métricas de LLM

| Campo | Tipo | Descripción | Uso para Mejoras |
|-------|------|-------------|------------------|
| `llm_calls` | int | Llamadas exitosas a Azure OpenAI | Uso de IA |
| `llm_failures` | int | Llamadas fallidas | Fiabilidad de IA |
| `llm_avg_latency_ms` | float | Latencia promedio | Performance de IA |

### 3.5 Métricas de Runner

| Campo | Tipo | Descripción | Uso para Mejoras |
|-------|------|-------------|------------------|
| `runner_executions` | int | Ejecuciones del runner | Adopción de feature |
| `runner_steps_total` | int | Pasos totales ejecutados | Profundidad de uso |
| `runner_memos_generated` | int | Memos generados | Output productivo |

### 3.6 Métricas de UX

| Campo | Tipo | Descripción | Uso para Mejoras |
|-------|------|-------------|------------------|
| `time_to_first_action_ms` | float | Tiempo hasta primera acción exitosa | Onboarding |
| `errors_per_minute` | float | Tasa de errores | Calidad de UX |
| `latency_percentiles` | dict | P50/P90/P99 de latencia | Performance percibida |

### 3.7 Patrones de Uso

| Campo | Tipo | Descripción | Uso para Mejoras |
|-------|------|-------------|------------------|
| `coding_cycles` | int | Ciclos de codificación detectados | Feature más usada |
| `discovery_sessions` | int | Sesiones de búsqueda semántica | Adopción de discovery |
| `validation_actions` | int | Acciones de validación de códigos | Flujo de trabajo |
| `idle_periods` | list | Períodos de inactividad (>5min) | Engagement gaps |

---

## 4. Sistema de Insights Automáticos

El generador de informes produce **insights accionables** basados en umbrales:

### 4.1 Categorías de Insights

| Categoría | Prioridades | Ejemplos de Issues |
|-----------|-------------|-------------------|
| `authentication` | high, critical | Muchos errores 401, refresh token |
| `infrastructure` | medium, critical | Pool warnings, exhaustion |
| `ai_integration` | high, medium | Fallos LLM, latencia alta |
| `performance` | medium, high | P90 > 500ms, queries lentas |
| `ux` | low, medium | Períodos idle, abandono |
| `reliability` | high, critical | Endpoints con baja tasa de éxito |

### 4.2 Prioridades

| Prioridad | Emoji | Acción Esperada |
|-----------|-------|-----------------|
| `critical` | 🔴 | Resolver en <24h |
| `high` | 🟠 | Resolver en <1 semana |
| `medium` | 🟡 | Planificar para próximo sprint |
| `low` | 🟢 | Backlog de mejoras |

### 4.3 Umbrales Configurables

```python
# En session_report_generator.py
THRESHOLDS = {
    "auth_failures_high": 5,           # >5 errores 401 = insight high
    "pool_warnings_medium": 3,         # >3 pool warnings = insight medium
    "llm_failure_rate_high": 5.0,      # >5% fallos LLM = insight high
    "p90_latency_medium": 500,         # >500ms P90 = insight medium
    "idle_periods_low": 3,             # >3 períodos idle = insight low
    "endpoint_success_rate_high": 95,  # <95% éxito = insight high
}
```

---

## 5. Cómo los Informes Alimentan Mejoras

### 5.1 Pipeline de Mejora Continua

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PIPELINE DE MEJORA                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  PASO 1: RECOLECCIÓN (Automático)                                           │
│  ─────────────────────────────────                                          │
│  • Cada request genera evento en logs/                                      │
│  • Logs por sesión en logs/{project}/{session}/                             │
│  • Errores LLM en logs/llm_errors.jsonl                                     │
│                                                                              │
│  PASO 2: ANÁLISIS (Manual/Scheduled)                                        │
│  ────────────────────────────────────                                       │
│  • Ejecutar: python scripts/session_report_generator.py                     │
│  • Generar informes por sesión                                              │
│  • Agregar insights automáticos                                             │
│                                                                              │
│  PASO 3: PRIORIZACIÓN (Revisión Humana)                                     │
│  ──────────────────────────────────────                                     │
│  • Revisar insights con prioridad critical/high                             │
│  • Agrupar issues similares                                                 │
│  • Crear tickets en backlog                                                 │
│                                                                              │
│  PASO 4: IMPLEMENTACIÓN (Desarrollo)                                        │
│  ────────────────────────────────────                                       │
│  • Resolver issues según prioridad                                          │
│  • Agregar logging mejorado si es necesario                                 │
│  • Desplegar cambios                                                        │
│                                                                              │
│  PASO 5: VALIDACIÓN (Post-Deploy)                                           │
│  ─────────────────────────────────                                          │
│  • Comparar métricas antes/después                                          │
│  • Verificar que insights desaparecen                                       │
│  • Documentar mejora en CHANGELOG                                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Mapeo Insight → Mejora

| Insight | Archivo a Modificar | Tipo de Cambio |
|---------|---------------------|----------------|
| Pool exhaustion | `app/clients.py` | Aumentar `pool_maxconn` |
| LLM failures | `app/coding.py` | Mejorar parsing JSON, retry |
| P90 latency alta | `backend/routers/*.py` | Optimizar queries, índices |
| Auth failures | `frontend/src/services/api.ts` | Implementar refresh token |
| Endpoint baja tasa éxito | `backend/routers/{endpoint}.py` | Fix específico |

### 5.3 KPIs de Mejora

Estos KPIs deben mejorar con cada ciclo:

| KPI | Fórmula | Meta |
|-----|---------|------|
| **Tasa de Éxito Global** | `successful_requests / total_requests` | >99% |
| **P90 Latency** | Percentil 90 de latencias | <300ms |
| **LLM Success Rate** | `llm_calls / (llm_calls + llm_failures)` | >98% |
| **Time to First Action** | Tiempo hasta primera acción exitosa | <2000ms |
| **Pool Warnings/Session** | Promedio de pool warnings | <1 |
| **Errores/Minuto** | Promedio de errores por minuto | <0.5 |

---

## 6. Uso del Generador de Informes

### 6.1 Comandos Básicos

```powershell
# Analizar la última sesión de un proyecto
python scripts/session_report_generator.py --project jd-007 --latest

# Analizar una sesión específica
python scripts/session_report_generator.py --project jd-007 --session 1768744412691-5f4ue11na

# Generar en formato JSON
python scripts/session_report_generator.py --project jd-007 --latest --format json

# Guardar en directorio de reportes
python scripts/session_report_generator.py --project jd-007 --latest --output reports/sessions/
```

### 6.2 Automatización (Opcional)

Para ejecutar automáticamente al final de cada día:

```powershell
# En Task Scheduler o cron
# Ejecutar a las 23:55 cada día
python scripts/session_report_generator.py --all-recent --days 1 --output reports/sessions/
```

### 6.3 Integración con CI/CD

```yaml
# En GitHub Actions o Azure DevOps
- name: Generate Session Reports
  run: |
    python scripts/session_report_generator.py --all-recent --days 7 --output reports/
    
- name: Check Critical Insights
  run: |
    # Fallar si hay insights críticos
    grep -r '"priority": "critical"' reports/ && exit 1 || exit 0
```

---

## 7. Roadmap de Mejoras del Sistema

### Fase 1 (Actual) ✅
- [x] Generador de informes por sesión
- [x] Insights automáticos con umbrales
- [x] Formato Markdown y JSON

### Fase 2 (Próximo Sprint)
- [ ] Dashboard web para visualizar informes
- [ ] Agregación de métricas por día/semana
- [ ] Alertas automáticas por email/Slack

### Fase 3 (Futuro)
- [ ] Machine Learning para detectar anomalías
- [ ] Predicción de problemas antes de que ocurran
- [ ] A/B testing con métricas de sesión

---

## 8. Ejemplo de Informe Generado

Ver [LOG_MONITORING_REPORT.md](../LOG_MONITORING_REPORT.md) para un ejemplo real de informe de sesión.

---

## 9. Troubleshooting

### Error: "Session log not found"
- Verificar que el proyecto y sesión existen en `logs/{project}/{session}/`
- Los logs de sesión solo se crean si el frontend envía `X-Session-ID` header

### Error: "No events found"
- El archivo `app.jsonl` de la sesión puede estar vacío
- Verificar que el backend está escribiendo logs correctamente

### Insights vacíos
- La sesión puede haber sido muy corta o exitosa
- Los umbrales pueden necesitar ajuste para el proyecto específico

---

*Documento creado: 2026-01-18*
