# Manual de uso (resumen operativo)

Este manual describe el flujo de trabajo recomendado para operar la plataforma de analisis, codificacion y monitoreo.

## Objetivo
- Ingestar entrevistas o documentos.
- Generar contexto semantico y topologico.
- Proponer codigos, validar candidatos y consolidar resultados.
- Ejecutar analisis GDS y generar reportes.
- Monitorear salud del sistema y alertas.

## Prerrequisitos
- Backend y servicios activos (PostgreSQL, Neo4j, Qdrant, Azure OpenAI).
- Variables de entorno configuradas (ver .env y env.example).
- API Key valida para el frontend.

## Flujo recomendado (paso a paso)

### 1) Preparar proyecto
- Crear proyecto desde el frontend o via API.
- Validar que el proyecto tenga conexiones activas.

### 2) Ingesta
- Cargar documentos (DOCX) y ejecutar ingesta.
- Verificar que se generen fragmentos y embeddings.
- Confirmar persistencia en PostgreSQL, Neo4j y Qdrant.

### 3) Descubrimiento y codificacion
- Usar Discovery para explorar semanticamente.
- Proponer codigos desde resultados de busqueda.
- Revisar sugerencias de codificacion asistida.

### 4) Validacion de codigos candidatos
- Abrir CodeValidationPanel.
- Aprobar, rechazar o fusionar candidatos.
- Promover a codigos definitivos cuando aplique.

### 5) Analisis GDS
- Usar Neo4jExplorer para calcular comunidades y centralidad.
- Persistir resultados en el grafo cuando sea necesario.

### 6) Reportes
- Revisar reportes integrados en el panel de reportes.
- Generar reportes diarios (scripts/daily_logs_reporter.py).

### 7) Monitoreo y salud
- Usar BackendStatus y SystemHealthDashboard.
- Revisar alertas de error rate, slow rate y schema health.

## KPIs y analiticas esperadas
- Ingesta: documentos procesados por dia, fragmentos generados, tasa de error de ingesta.
- Semantica: cobertura de embeddings, latencia de busqueda, top consultas.
- Codificacion: candidatos propuestos vs aprobados, tasa de rechazo, tiempo medio de validacion.
- Grafo: comunidades detectadas, centralidad promedio, relaciones nuevas sugeridas vs aceptadas.
- Calidad: porcentaje de request con schema completo, parseabilidad JSON, error rate y slow rate.
- Operacion: disponibilidad de servicios, latencia promedio por endpoint critico, volumen por build.

## Buenas practicas
- Usar X-Test-Run-Id para pruebas controladas.
- Mantener logs en JSON y evitar PII.
- Ajustar umbrales de alertas segun trafico real.
- Documentar incidentes y soluciones en docs/09-troubleshooting-incidentes.

## Troubleshooting rapido
- Verificar logs en logs/app.jsonl.
- Revisar alertas en Azure Monitor.
- Confirmar conectividad de servicios (scripts/healthcheck.py).

## Rutas clave (frontend)
- /api/ingest
- /api/codes/candidates
- /api/health/full

## Notas finales
- Este manual es un punto de partida. Ajustar el flujo segun el tipo de proyecto y el estado de la operacion.
