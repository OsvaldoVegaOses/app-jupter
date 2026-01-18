# JD-009 — Resumen ejecutivo (1 página)
**Fecha:** 2026-01-08
**Proyecto:** jd-009

## Qué se hizo (sin problemas)
- Se ejecutó el ciclo completo: ingesta de entrevistas (DOCX) → análisis → persistencia de resultados.
- Se realizó Discovery iterativo (búsqueda exploratoria) para afinar hipótesis y foco temático.
- Se verificó que la codificación axial persistida (`analysis.axial.persisted`) refleja los temas emergentes por documento.

## Loop Discovery (patrón de mejora)
- Iteración amplia: `estado` (00:28 / 00:29) → señal mezclada.
- Iteración focalizada: `competencias_municipales, instrumentos_normativos, planificacion_urbana` + negativos + texto objetivo → mayor pertinencia.
- Iteración de consolidación: `estado, sector público, normativa urbana, municipal` (11:36) → framing estable y reutilizable.

## Codificación persistida — 6 archivos (3 temas/códigos top)

### 1) Secpla_I_M_Puente_Alto_20260108_000823.docx
Fuente: `logs/app.jsonl#L8975-L8985`
- Planificación integral / mirada territorial: `planificacion_integral`, `mirada_ecologica_territorial`
- Gobernanza/coord.: `coordinacion_interinstitucional`
- Déficit estructural aguas lluvia: `infraestructura_insuficiente`

### 2) Jefa_Territorial_Municipalidad_La_Florida_20260108_000709.docx
Fuente: `logs/app.jsonl#L9261-L9268`
- Gestión territorial municipal: `rol_coordinacion_territorial`
- Emergencias/operación: `gestion_emergencias`
- Problema aguas lluvia (causas): `infraestructura_insuficiente`, `urbanizacion_acelerada`

### 3) Entrevista_Encargada_Emergencia_La_Florida_20260108_000622.docx
Fuente: `logs/app.jsonl#L9437-L9448`
- Gestión del riesgo: `rol_gestion_riesgo`, `prevencion_y_respuesta`
- Déficit estructural: `deficit_colectores`
- Capacidad municipal: `limite_capacidad_municipal`

### 4) Entrevista_DIPMA_La_Florida_20260108_000611.docx
Fuente: `logs/app.jsonl#L9641-L9647`
- Falta de marco normativo: `ausencia_normativa_aguas_lluvia`
- Crecimiento urbano desordenado: `crecimiento_urbano_desordenado`
- Restricciones municipales: `limitaciones_municipales`

### 5) Entrevista_equipo_Asesor_Urbano_La_Florida_20260108_000523.docx
Fuente: `logs/app.jsonl#L9811-L9820`
- Coordinación municipal/rol institucional: `coordinacion_municipal`, `responsabilidad_asesoria_urbana`
- Alcance y límites del proyecto: `alcance_limitado_proyecto`
- Presión futura (densificación/metro): `densificacion_asociada_al_metro`

### 6) _entrevista_Gerente_Canal_San_Carlos_20260108_000506.docx
Fuente: `logs/app.jsonl#L9971-L9980`
- Gobernanza formal: `convenio_marco_doh`
- Coordinación/gestión: `coordinacion_municipal`, `necesidad_reunion_tecnica`
- Condiciones técnicas: `limitacion_capacidad_descarga`

## 3 conclusiones (operativas)
- La narrativa “Estado/sector público” baja a terreno como **capacidad municipal limitada + necesidad de coordinación interinstitucional + brechas normativas**, consistente en varios documentos.
- El tema aguas lluvia aparece como problema estructural transversal, con drivers recurrentes: infraestructura insuficiente, urbanización acelerada y presión por densificación.
- El loop de Discovery es automatizable (variante con negativos + variante con texto objetivo) y puede validarse contra los códigos persistidos esperables para cerrar el ciclo.

## Referencias
- Mapa completo (trazabilidad): `docs/revision_operativa/sin_problemas/JD-009_mapa_discovery_codificacion_2026-01-08.md`
- Informe operativo (alertas/acciones): `docs/revision_operativa/informe_revision_operativa_JD-009_2026-01-08.md`
