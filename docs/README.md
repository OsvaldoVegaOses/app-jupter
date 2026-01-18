# Documentacion del Proyecto

> **Sistema de Analisis Cualitativo con GraphRAG**

---

## Estructura de Carpetas

```
docs/
-- 01-arquitectura/     # Arquitectura base y contexto
+-- 01-configuracion/     # Setup y configuracion
+-- 02-metodologia/       # Etapas de Grounded Theory
+-- 03-sprints/           # Planificacion y tracking
+-- 04-arquitectura/      # Diseno y decisiones tecnicas
+-- 05-calidad/           # Lecciones UX/UI
+-- 05-troubleshooting/   # Resolucion de problemas
+-- 05-productos-derivados/ # Reportes y entregables
+-- 06-agente-autonomo/   # [NEW] Agente IA autónomo
+-- fundamentos_teoria/   # Teoria Grounded Theory
+-- Revision_Desarrollo/  # Reviews de codigo
+-- revision_operativa/   # Revisión operativa
```

---

## 01-Configuracion

| Documento | Descripcion |
|-----------|-------------|
| [configuracion_llm.md](01-configuracion/configuracion_llm.md) | Azure OpenAI y modelos LLM |
| [configuracion_infraestructura.md](01-configuracion/configuracion_infraestructura.md) | Qdrant, Neo4j, PostgreSQL, Redis |
| [run_local.md](01-configuracion/run_local.md) | Guia de ejecucion local |
| [guia_despliegue_async.md](01-configuracion/guia_despliegue_async.md) | Despliegue con Celery |
| [data_dictionary.md](01-configuracion/data_dictionary.md) | Diccionario de datos |
| [tech_stack_roles.md](01-configuracion/tech_stack_roles.md) | Stack tecnologico |
| [manual_funcionamiento_uso.md](manual_funcionamiento_uso.md) | **[NEW]** Manual de funcionamiento y uso |

---

## 02-Metodologia

| Documento | Descripcion |
|-----------|-------------|
| [manual_etapas.md](02-metodologia/manual_etapas.md) | Manual completo de etapas |
| [guia_graphrag_discovery.md](02-metodologia/guia_graphrag_discovery.md) | GraphRAG y Discovery |
| [etapa0_reflexividad.md](02-metodologia/etapa0_reflexividad.md) | Etapa 0: Reflexividad |
| [etapa2_codificacion_base.md](02-metodologia/etapa2_codificacion_base.md) | Etapa 2: Codificacion |
| [etapas1-4_informe.md](02-metodologia/etapas1-4_informe.md) | Informe etapas 1-4 |

---

## 03-Sprints

| Documento | Descripcion |
|-----------|-------------|
| [Sprints.md](03-sprints/Sprints.md) | Historial completo |
| [sprint_backlog.md](03-sprints/sprint_backlog.md) | Backlog actual |
| [sprint_tracking.md](03-sprints/sprint_tracking.md) | Tracking |
| [sprint9_graphrag_discovery.md](03-sprints/sprint9_graphrag_discovery.md) | Sprint 9: GraphRAG |
| [sprint28_neo4j_resilience.md](03-sprints/sprint28_neo4j_resilience.md) | **[NEW]** Sprint 28: Neo4j Resilience & PostgreSQL Fallback |

---

## 04-Arquitectura

| Documento | Descripcion |
|-----------|-------------|
| [proyecto.md](04-arquitectura/proyecto.md) | Vision del proyecto |
| [valor_negocio.md](04-arquitectura/valor_negocio.md) | Propuesta de valor |
| [alternativas_gds.md](04-arquitectura/alternativas_gds.md) | Alternativas GDS |

---

## 05-Calidad y Troubleshooting

| Documento | Descripcion |
|-----------|-------------|
| [plan_pruebas_sprint4.md](plan_pruebas_sprint4.md) | **[NEW]** Plan de pruebas Sprint 4 |
| [fix_axial_neo4j.md](05-troubleshooting/fix_axial_neo4j.md) | Fix Neo4j axial |
| [brechas_tecnicas.md](05-troubleshooting/brechas_tecnicas.md) | Brechas tecnicas |
| [lecciones_aprendidas_ux_ui.md](05-calidad/lecciones_aprendidas_ux_ui.md) | Lecciones UX/UI |
| [propuesta_cierre_ux_ui_proceso_investigacion.md](05-calidad/propuesta_cierre_ux_ui_proceso_investigacion.md) | **[NEW]** Cierre UX/UI como proceso investigativo (E2–E4, Discovery/Runner) |
| [revision_operativa.md](revision_operativa.md) | Revisión operativa alineada a GT |

---

## Fundamentos Teoria

| Documento | Descripcion |
|-----------|-------------|
| `fundamentos_teoria/` | 8 documentos sobre Grounded Theory |

---

## Informes de Logs y Auditoría

| Documento | Descripcion |
|-----------|-------------|
| [investigacion_logs_2026-01-04.md](informe_logs/investigacion_logs_2026-01-04.md) | **[NEW]** Investigación de errores 401/500/404 |
| [auditoria_pipeline_2026-01-04.md](informe_logs/auditoria_pipeline_2026-01-04.md) | **[NEW]** Auditoría etapas 0-4, alineación tablas y endpoints |
| [INFORME_COMPLETO_LOGS.md](informe_logs/INFORME_COMPLETO_LOGS.md) | Informe completo de logs |
| [CONTRASTE_ACCIONES_MANUALES.md](informe_logs/CONTRASTE_ACCIONES_MANUALES.md) | Contraste acciones manuales |

---

## 06-Agente Autónomo **[NEW]**

> Sistema de orquestación basado en LangGraph para ejecutar el pipeline de GT de forma autónoma.

| Documento | Descripción |
|-----------|-------------|
| [README.md](06-agente-autonomo/README.md) | Visión general y arquitectura |
| [agent_feasibility_analysis.md](06-agente-autonomo/agent_feasibility_analysis.md) | Análisis de viabilidad técnica |
| [startup_strategy_evaluation.md](06-agente-autonomo/startup_strategy_evaluation.md) | Estrategias inspiradas en Hebbia, Devin, Elicit |

**Código:** [app/agent_standalone.py](../app/agent_standalone.py) - Implementación standalone con mocks

---

## Quick Start

1. **Configurar ambiente**: Ver `01-configuracion/run_local.md`
2. **Manual de uso**: Ver `manual_funcionamiento_uso.md`
3. **Entender metodologia**: Ver `02-metodologia/manual_etapas.md`
4. **Ver arquitectura**: Ver [`app/README.md`](../app/README.md)
5. **Ejecutar tests**: Ver `plan_pruebas_sprint4.md`

---

## Sprint 4: Security Hardening (Diciembre 2024)

### Implementado
- Aislamiento por `project_id` en todas las capas
- Conexiones hardened (SSL, timeouts, pool)
- Guardrails Cypher (whitelist/blocklist, LIMIT)
- JSON parsing robusto (retry, validation)

### Documentacion Nueva
- `plan_pruebas_sprint4.md`: Plan de pruebas con comandos
- `app/isolation.py`: Helpers centralizados

### Tests
- `tests/test_project_isolation.py`: Aislamiento PG/Qdrant/Neo4j
- `tests/test_json_parsing.py`: Robustez JSON LLM

---

*Actualizado: Enero 2026*
