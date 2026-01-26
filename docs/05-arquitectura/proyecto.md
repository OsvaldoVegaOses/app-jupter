# Proyecto Iterativo de Analisis Cualitativo

## Resumen ejecutivo
- Un solo flujo coordinado desde la preparacion reflexiva hasta el informe integrado, reutilizando los agentes descritos en `agents.md`.
- Los sprints documentados en `docs/Sprints.md` alimentan cada etapa; este documento actua como indice maestro y punto de arranque para nuevos ciclos.
- El estado computable vive en `metadata/projects/<proyecto>.json` y se consulta via `python main.py status --project <id>`, lo que permite confirmar avance y ultimos `run_id` por iniciativa.
- Para el encuadre de producto “chat empresarial anti-alucinaciones” (grounded chat), ver `docs/04-arquitectura/chat_empresarial_anti_alucinaciones.md`.

## Etapas, sprints y comandos de verificacion
| Etapa | Objetivo operativo | Sprints asociados | Comando de verificacion |
| --- | --- | --- | --- |
| Etapa 0 - Preparacion y Reflexividad | Healthcheck, credenciales, acuerdos eticos y diario de reflexividad | Sprint 0 - Endurecimiento y gobernanza de datos | `python scripts/healthcheck.py --env .env` |
| Etapa 1 - Ingesta y normalizacion | Fragmentar DOCX, **detectar hablantes (entrevistador/entrevistado)**, vectorizar y persistir en PG/Qdrant/Neo4j | Sprint 1 - Ingesta inicial (ver `docs/Sprints.md`) | `python main.py ingest entrevistas/*.docx --meta-json metadata/entrevistas.json` |
| Etapa 2 - QA descriptivo | Busqueda semantica **(híbrida)**, counts y muestreo rapido para validar cobertura | Sprint 1 y micro-sprints de QA | `python main.py search "termino clave"` / `python main.py counts` |
| Etapa 3 - Codificacion abierta | Matriz codigo-cita y sugerencias semanticas | Sprint 2 - Matrices de codificacion abierta | `python main.py coding stats` |
| Etapa 4 - Codificacion axial | Relaciones categoria <-> codigo, metricas GDS | Sprint 3 - Axial y coherencia | `python main.py axial gds --algorithm pagerank` |
| Etapa 5 - Nucleo selectivo | Triangulacion centralidad, cobertura y probes | Sprint 4 - Seleccion de nucleo | `python main.py nucleus report --categoria "Nombre" --prompt "..."` |
| Etapa 6 - Analisis transversal | Cortes por genero/rol/tiempo en PG/Qdrant/Neo4j | Sprint 5 - Transversal genero/rol | `python main.py transversal dashboard --prompt "..." --attribute genero --values mujeres hombres` |
| Etapa 7 - Modelo explicativo | Generar narrativa y diagrama ASCII consolidado | Sprint 6 - Narrativa y modelo | `python main.py analyze data/entrevista.docx --table` |
| Etapa 8 - Validacion y saturacion | Curvas, outliers, member checking | Sprint 7 - Saturacion y QA final | `python main.py validation curve --window 3 --threshold 0` |
| Etapa 9 - Informe integrado | Ensamblar reporte, anexos y manifiesto reproducible | Sprint 8 - Informe final | `python main.py report build --output informes/informe_integrado.md` |

## Trazabilidad y control
- `python main.py status --project <id>` resume cada etapa con su verificacion recomendada, ultimo `run_id`, log mas reciente y estampa de actualizacion.
- Los comandos clave actualizan `metadata/projects/<proyecto>.json`, lo que habilita dashboards externos o automatizaciones sin tocar la logica de los agentes.
- Los logs estructurados ahora incluyen el campo `etapa`, facilitando correlacion rapida (ej. `transversal.dashboard.begin` -> `etapa6_transversal`).
- Manten `docs/Sprints.md` como bitacora detallada de decisiones y aprendizajes; enlaza desde aqui cada vez que abras un nuevo sprint o ciclo reflexivo.
- Para profundizar en la Etapa 0 (reflexividad, configuracion de llaves y healthcheck), revisa `docs/etapa0_reflexividad.md`.

## Gestion de proyectos
- Crea y lista iniciativas con `python main.py project create --name ...` y `python main.py project list`; el identificador (slug) resultante se usa en `--project`.
- Todos los comandos operativos aceptan `--project`; si se omite se emplea el proyecto `default`.
- Puedes marcar etapas manualmente sin ejecutar el flujo completo con `python main.py workflow complete --project <id> --stage <etapa>`, dejando notas via `--notes` si corresponde.
- Los estados quedan en `metadata/projects/<id>.json`, preservando historicos independientes por frente de investigacion.

## Dashboard React
- El frontend vive en `frontend/` y consume los endpoints locales expuestos por `vite.config.ts` (`/api/projects`, `/api/status?project=...`, `/api/projects/<id>/stages/<etapa>/complete`).
- Ejecuta `npm install` dentro de `frontend/` y luego `npm run dev` para abrir el tablero; la API intenta correr `python main.py status --json --no-update` y, si falla, recurre a los JSON ya persistidos.
- Usa el selector superior para alternar proyectos, crea nuevos directamente desde la UI y marca etapas conforme avances; el boton “Refrescar estado” consulta el snapshot actual.
- Antes de levantar el dashboard, ejecuta `python main.py status --project <id>` (sin `--no-update`) para persisitir un snapshot en `metadata/projects/<id>.json` y mantener `informes/report_manifest.json` alineado.
