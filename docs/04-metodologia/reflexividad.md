# Diario de Reflexividad

Este documento propone la estructura para un diario de reflexividad versionado (git) que acompañe cada sprint de análisis cualitativo.

## Propósito
- Registrar supuestos, sesgos, decisiones metodológicas y cambios en criterios de codificación.
- Dejar trazabilidad de rotación de credenciales, ajustes técnicos y validaciones de calidad de datos.
- Facilitar auditorías internas y la reproducción del proceso.

## Estructura Recomendada
Mantén una entrada por sesión de trabajo usando el siguiente bloque Markdown:

```
## YYYY-MM-DD - Nombre / Rol
### Contexto
- Objetivo de la sesión.
- Materiales analizados (entrevistas, fragmentos, scripts).

### Observaciones
- Dudas sobre fidelidad de transcripción.
- Notas sobre sesgos personales o del equipo.
- Incidencias técnicas (errores, tiempos de respuesta de APIs, drift de embeddings).

### Decisiones Tomadas
- Ajustes en unidad de análisis o criterios de inclusión/exclusión.
- Cambios en catálogos (áreas temáticas, actores, banderas booleanas).
- Acciones sobre credenciales o configuraciones (.env, rotaciones).

### Próximos Pasos
- Tareas pendientes.
- Validaciones requeridas (health checks, revisiones cruzadas).
```

## Buenas Prácticas
- Versionar el diario dentro de `docs/reflexividad.md` o dividirlo por semana (`docs/reflexividad/2025-W45.md`).
- Usar commits específicos del diario (`chore(reflexividad): entrada 2025-10-30`).
- Referenciar issues o tareas del backlog cuando corresponda.
- Adjuntar capturas o hashes (colocar en almacenamiento seguro) cuando se evalúen fragmentos sensibles.

## Integración con el Pipeline
- Al finalizar cada ingesta (`python main.py … ingest`), agregar nota con el lote de archivos y hash del commit de configuración.
- Si se detecta drift de dimensiones (`len(vector) != EMBED_DIMS`), documentar la incidencia, el despliegue afectado y la acción correctiva.
- Registrar pruebas de `scripts/healthcheck.py` y su resultado (verde/rojo) para mantener evidencia de gobernanza de datos.

Mantener este diario es clave para asegurar reflexividad constante y cumplir con los estándares de investigación cualitativa rigurosa.
