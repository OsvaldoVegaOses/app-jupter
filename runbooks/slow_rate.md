# Runbook: Alerta Slow Rate en /validate

## Informacion de alerta
- Tipo: Slow rate (>15% requests >5s o p95 alto)
- Severidad: Sev2 (warning)
- Fuente: Azure Monitor Log Alert
- Workbook asociado: "Logs MVP (Fase 1)"

## Pasos inmediatos
1) Verificar alerta (portal o CLI) y abrir el Workbook.
2) TimeRange: ultimos 15m. Filtrar route=/api/codes/candidates/{id}/validate.
3) Confirmar:
   - slow_rate
   - p95
   - top request_id
   - build_version
4) Revisar "Segmentos dominantes" si existe:
   - db / neo4j / qdrant / llm
5) Accion segun dominante:
   - db: revisar indices / pool / queries lentas
   - neo4j: batch / async / retries
   - qdrant: latencia vector DB / payload
   - llm: timeouts / caching
6) Verificacion post-cambio:
   - comparar p95/slow_rate en 15-30m
7) Registrar evidencia:
   - build_version, request_id, dominante, accion, resultado

## Escalacion
- Si p95 > 10s o slow_rate > 30%: escalar inmediato.
- Si no mejora en 30m: notificar equipo.
