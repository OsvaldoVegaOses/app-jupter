# Plan de cambios (2026-01-02)

## Orden propuesto (mínimo riesgo)
1) **PostgreSQL – Alineación de esquema**
   - Ejecutar el bloque SQL de alteraciones (sessions.is_revoked/last_active_at, analysis_insights.project_id + índice, entrevista_fragmentos.actor_principal, analisis_axial.relacion + índice único).
   - Ruta recomendada: `docker exec -i <pg_container> psql -U $POSTGRES_USER -d $POSTGRES_DB -c "<SQL>"`.
   - Verificar que psql exista en el contenedor; si no, usar contenedor postgres auxiliar.

2) **Qdrant – Índice por proyecto**
   - Confirmar colección de fragments y crear índice keyword en `project`:
     - `POST $QDRANT_URL/collections/fragments/index` body `{ "field_name": "project", "field_schema": "keyword" }` con header `api-key`.
   - Validar que payloads de discovery/análisis envíen embeddings planos (no lista de listas).

3) **Neo4j – Labels/relaciones mínimas**
   - Chequear presencia de labels `Categoria` y `Codigo` y tipos permitidos para relaciones GDS/GraphRAG.
   - Proteger rutas GDS con fallback/flag si faltan labels (sin añadir scipy).

4) **Health/observabilidad**
   - Probar `/healthz` y registrar latencias/errores con `request_id`.
   - Homogeneizar timeouts/reintentos de clientes HTTP.
   - Preparar vars de Redis para Azure (no habilitar local todavía).

5) **Valor de negocio (búsqueda asistida)**
   - En la tabla de resultados: mostrar semilla/similares con score, explicación de ranking, y “siguiente mejor acción” (proponer vs codificar) con reglas de umbral interpretables.
   - Métricas de cobertura/avance y citas exportables con trazabilidad (alineado a interoperabilidad CAQDAS).

## Estado actual
- Lote LLM/transcripción ajustado: reintentos + backoff y `request_id` en [app/transcription.py](../../app/transcription.py).
- Infra Fase 0 (según plan consolidado): esquema PG, índice Qdrant por proyecto, health/observabilidad y UX de búsqueda asistida completados.
- Runner Semántico: checkpoints en `logs/runner_checkpoints/` y reportes en `logs/runner_reports/` para post-mortem.

## Notas
- No añadir `scipy` a dependencias.
- Mantener `app.py` monolítico; solo extraer utilidades transversales si es bajo riesgo.
- Redis se activará cuando se despliegue en Azure; solo preparar configuración.
