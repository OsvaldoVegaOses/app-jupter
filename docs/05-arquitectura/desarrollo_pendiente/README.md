# Desarrollo pendiente (índice)

> Carpeta de ideas, decisiones futuras y diseños en evaluación.

## Documentos

- [docs/04-arquitectura/desarrollo_pendiente/flujo_codificacion_grounded_theory.md](docs/04-arquitectura/desarrollo_pendiente/flujo_codificacion_grounded_theory.md)
  - Flujo propuesto de codificación (Grounded Theory) y consideraciones de producto/metodología.

- [docs/04-arquitectura/desarrollo_pendiente/modelo_ontologico_code_id_y_superseded.md](docs/04-arquitectura/desarrollo_pendiente/modelo_ontologico_code_id_y_superseded.md)
  - Reflexión completa para una fase futura: identidad estable (`code_id`), puntero canónico (`canonical_code_id` con `NULL` en canónicos), opción de estado `superseded` y ruta de migración incremental.

- [docs/04-arquitectura/desarrollo_pendiente/propuesta_sql_migracion_code_id.sql](docs/04-arquitectura/desarrollo_pendiente/propuesta_sql_migracion_code_id.sql)
  - DDL propuesto (diseño futuro): columnas `code_id`/`canonical_code_id`, FK compuesta por proyecto, ampliación de `status` con `superseded` e índices.

- [docs/04-arquitectura/desarrollo_pendiente/fase_1_5_transicion_controlada_a_code_id.md](docs/04-arquitectura/desarrollo_pendiente/fase_1_5_transicion_controlada_a_code_id.md)
  - Plan de transición controlada: compatibilidad dual, backfill, resolver por ID con fallback a texto, criterios de salida y límites deliberados.
