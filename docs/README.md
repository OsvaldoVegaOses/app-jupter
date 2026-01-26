# Documentación del Proyecto

> **Sistema de Análisis Cualitativo con GraphRAG**

## Estructura (2026-01)

```
docs/
  01-inicio-rapido/             # Guías rápidas (en construcción)
  02-configuracion/             # Setup y configuración
  03-manuales-usuario/          # Manuales por etapa (usuario)
  04-metodologia/               # Grounded Theory + guías del flujo
  05-arquitectura/              # Diseño, decisiones técnicas y UX
  06-referencia/                # Referencia (API/BD/specs)
  07-operacion/                 # Operación y despliegue
  08-calidad-testing/           # QA, auditorías, pruebas
  09-troubleshooting-incidentes/# Incidentes, root-cause, fixes
  10-reportes-historial/        # Reportes, sprints, historial
```

## 02 - Configuración

| Documento | Descripción |
|---|---|
| `02-configuracion/configuracion_llm.md` | Azure OpenAI y modelos LLM |
| `02-configuracion/configuracion_infraestructura.md` | Qdrant, Neo4j, PostgreSQL, Redis |
| `02-configuracion/run_local.md` | Guía de ejecución local |
| `02-configuracion/guia_despliegue_async.md` | Despliegue con Celery |
| `02-configuracion/data_dictionary.md` | Diccionario de datos |
| `02-configuracion/tech_stack_roles.md` | Stack tecnológico |
| `02-configuracion/azure_deployment.md` | Despliegue en Azure |

## 03 - Manuales de usuario

- Índice: `03-manuales-usuario/README.md`
- Etapa 0: `03-manuales-usuario/etapa0_preparacion.md`

## 04 - Metodología

| Documento | Descripción |
|---|---|
| `04-metodologia/manual_etapas.md` | Manual completo de etapas |
| `04-metodologia/guia_graphrag_discovery.md` | GraphRAG y Discovery |
| `04-metodologia/guia_modos_epistemicos.md` | Modos epistémicos |
| `04-metodologia/FLUJO_ACTUALIZADO_ENERO2026.md` | Flujo actualizado (enero 2026) |
| `04-metodologia/etapas1-4_informe.md` | Informe etapas 1–4 |

## 05 - Arquitectura

| Documento | Descripción |
|---|---|
| `05-arquitectura/proyecto.md` | Visión del proyecto |
| `05-arquitectura/paneles_frontend.md` | Paneles frontend (UX/flujo) |
| `05-arquitectura/funcionalidades_avanzadas_qdrant_neo4j.md` | Qdrant/Neo4j avanzado |
| `05-arquitectura/estrategia_grafos_fallback.md` | Estrategia fallback |
| `05-arquitectura/fusion_duplicados_api_spec.md` | Spec API fusión duplicados |

## 08 - Calidad y testing

| Documento | Descripción |
|---|---|
| `08-calidad-testing/plan-pruebas-sprint4.md` | Plan de pruebas Sprint 4 |
| `08-calidad-testing/lecciones_aprendidas_ux_ui.md` | Lecciones UX/UI |

## 09 - Troubleshooting e incidentes

| Documento | Descripción |
|---|---|
| `09-troubleshooting-incidentes/connection_pool_issues.md` | Connection pool (root cause + solución) |
| `09-troubleshooting-incidentes/discovery_session_logs.md` | Logs de sesiones Discovery |
| `09-troubleshooting-incidentes/cypher_queries.md` | Queries Cypher útiles |

## 10 - Reportes e historial

- Productos derivados: `10-reportes-historial/productos-derivados/README.md`
- Sprints: `10-reportes-historial/sprints/`

---

*Actualizado: Enero 2026*
