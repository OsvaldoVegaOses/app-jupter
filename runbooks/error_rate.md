# Runbook: Alerta Error Rate (5xx)

## Informacion de alerta
- Tipo: Error rate (>5% requests 5xx)
- Severidad: Sev1/Sev2 segun impacto
- Fuente: Azure Monitor Log Alert
- Workbook asociado: "Logs MVP (Fase 1)"

## Pasos inmediatos
1) Verificar alerta y abrir Workbook.
2) TimeRange: ultimos 15m. Filtrar status_code >= 500.
3) Confirmar:
   - error_rate
   - endpoints afectados
   - top request_id
   - build_version
4) Revisar dependencias:
   - DB / Neo4j / Qdrant / LLM
5) Mitigar:
   - rollback si coincide con ultimo build
   - hotfix / feature flag si aplica
6) Verificacion post-cambio:
   - error_rate baja en 10-15m
7) Registrar evidencia:
   - build_version, request_id, causa, accion, resultado

## Escalacion
- Error rate > 20%: escalar inmediato.
- Persistente > 1h: escalar a arquitectura.
