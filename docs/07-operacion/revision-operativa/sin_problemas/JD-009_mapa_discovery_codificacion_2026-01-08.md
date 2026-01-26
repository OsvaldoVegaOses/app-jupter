# JD-009 — Mapa Discovery → Codificación (sin problemas)
**Fecha:** 2026-01-08
**Proyecto:** jd-009

## Propósito
Dejar trazabilidad “sin incidentes” del bucle manual de Discovery (búsqueda exploratoria) y cómo ese trabajo se refleja en la codificación persistida por el análisis (eventos `analysis.axial.persisted`).

## Fuentes
- Memos de Discovery (criterios + fragmentos + síntesis IA):
  - `notes/jd-009/2026-01-08_00-28_discovery_estado.md`
  - `notes/jd-009/2026-01-08_00-29_discovery_estado.md`
  - `notes/jd-009/2026-01-08_00-30_discovery_competencias_municipales_instr.md`
  - `notes/jd-009/2026-01-08_11-35_discovery_estado.md`
  - `notes/jd-009/2026-01-08_11-36_discovery_estado_sector_público.md`
- Logs (codificación axial persistida):
  - `logs/app.jsonl` (ver rangos enlazados en cada sección)

## Bucle Discovery (mejora iterativa observada)
**Iteración 1 — amplio:** `estado` (00:28 y 00:29)
- Sin negativos ni texto objetivo.
- Resultado: muchos fragmentos por co-ocurrencia del término; la síntesis IA ya sugiere el patrón “Estado como marco normativo/habilitador”, pero con señal mezclada.

**Iteración 2 — focalizada:** `competencias_municipales, instrumentos_normativos, planificacion_urbana` (00:30)
- Agrega negativos (`conversacion_informal`, `logistica_entrevista`) y texto objetivo (`intervencion_del_estado_en_desarrollo_urbano`).
- Resultado: sube la pertinencia (más foco en competencias, normativas, dependencia de “ente superior”, coordinación interinstitucional).

**Iteración 3 — consolidación temática:** `estado` (11:35) y `estado, sector público, normativa urbana, municipal` (11:36)
- Mantiene el framing normativo y lo “amarra” a municipalidad/sector público.

## Mapa Discovery → codificación persistida
> Nota: el “puente” entre Discovery y codificación se hace por **temas** (competencias, normativa, coordinación, capacidad municipal) y por **documentos** que aparecen en ambos lados.

### A) Query: `estado` (00:28 / 00:29 / 11:35)
**Documentos más visibles en memos:**
- `Entrevista_equipo_Asesor_Urbano_La_Florida_20260108_000523.docx` (predomina en los 3 memos)

**Codificación axial persistida asociada (por documento):**
- Asesoría Urbana La Florida → ver persistencias en `logs/app.jsonl`:
  - Rango: `logs/app.jsonl#L9811-L9820`
  - Categorías/códigos (extracto completo del rango):
    - `Gestion institucional del proyecto`: `responsabilidad_asesoria_urbana`, `coordinacion_municipal`, `alcance_limitado_proyecto`
    - `Problemática histórica de drenaje urbano`: `problematicas_inundacion_historicas`, `infraestructura_historicamente_insuficiente`
    - `Tensiones entre expectativas vecinales y proyecto`: `expectativa_vecinal`, `alcance_limitado_proyecto`, `necesidad_conexion_futura`
    - `Transformacion urbana y presion futura`: `densificacion_asociada_al_metro`, `preocupacion_superficie`

### B) Query: `competencias_municipales, instrumentos_normativos, planificacion_urbana` (00:30)
**Criterios (desde memo):**
- Negativos: `conversacion_informal`, `logistica_entrevista`
- Texto objetivo: `intervencion_del_estado_en_desarrollo_urbano`

**Documentos visibles en memo (fragmentos):**
- `Entrevista_equipo_Asesor_Urbano_La_Florida_20260108_000523.docx`
- `Secpla_I_M_Puente_Alto_20260108_000823.docx`
- `_entrevista_Gerente_Canal_San_Carlos_20260108_000506.docx`
- `Entrevista_Encargada_Emergencia_La_Florida_20260108_000622.docx`

**Codificación axial persistida asociada (por documento):**
- SECPLAN Puente Alto:
  - `logs/app.jsonl#L8975-L8985`
  - Temas/códigos destacados: `coordinacion_interinstitucional`, `planificacion_integral`, `mirada_ecologica_territorial`, `desarrollo_urbano_no_armonico`
- Gerente Canal San Carlos:
  - `logs/app.jsonl#L9971-L9980`
  - Temas/códigos destacados: `convenio_marco_doh`, `coordinacion_municipal`, `necesidad_reunion_tecnica`, `condicion_aprobacion`
- Encargada Emergencia La Florida:
  - `logs/app.jsonl#L9437-L9448`
  - Temas/códigos destacados: `rol_gestion_riesgo`, `prevencion_y_respuesta`, `criterio_punto_critico`, `limite_capacidad_municipal`
- Asesoría Urbana La Florida (mismo documento de A):
  - `logs/app.jsonl#L9811-L9820`

### C) Query: `estado, sector público, normativa urbana, municipal` (11:36)
**Documentos visibles en memo (fragmentos):**
- `Entrevista_equipo_Asesor_Urbano_La_Florida_20260108_000523.docx`
- `Secpla_I_M_Puente_Alto_20260108_000823.docx`
- `Entrevista_Encargada_Emergencia_La_Florida_20260108_000622.docx`

**Codificación axial persistida asociada (por documento):**
- Asesoría Urbana La Florida: `logs/app.jsonl#L9811-L9820`
- SECPLAN Puente Alto: `logs/app.jsonl#L8975-L8985`
- Encargada Emergencia La Florida: `logs/app.jsonl#L9437-L9448`

## Anexo — Codificación axial persistida (por archivo)

### Secpla_I_M_Puente_Alto_20260108_000823.docx
Fuente: `logs/app.jsonl#L8975-L8985`
- `Problematica estructural de aguas lluvias`: `inundaciones_historicas`, `infraestructura_insuficiente`, `obsolescencia_estandar`
- `Limitaciones del proyecto actual`: `limitacion_estudio_actual`, `preocupacion_sector_sur`
- `Necesidad de planificacion integral`: `planificacion_integral`, `mirada_ecologica_territorial`, `desarrollo_urbano_no_armonico`
- `Contexto y factores condicionantes`: `cambio_climatico`, `piedemonte_y_geografia`
- `Gobernanza y articulacion institucional`: `coordinacion_interinstitucional`

### Jefa_Territorial_Municipalidad_La_Florida_20260108_000709.docx
Fuente: `logs/app.jsonl#L9261-L9268`
- `Gestion_Territorial_Municipal`: `rol_coordinacion_territorial`, `organizaciones_comunitarias`, `gestion_emergencias`
- `Problematica_Aguas_Lluvias`: `zonas_criticas_inundacion`, `infraestructura_insuficiente`, `urbanizacion_acelerada`
- `Gobernanza_y_Recursos`: `limitaciones_financieras`, `beneficios_colector`

### Entrevista_Encargada_Emergencia_La_Florida_20260108_000622.docx
Fuente: `logs/app.jsonl#L9437-L9448`
- `Gestion_del_Riesgo_Comunal`: `rol_gestion_riesgo`, `prevencion_y_respuesta`, `criterio_punto_critico`
- `Amenazas_Naturales_y_Historicas`: `anegamientos_comuna`, `evento_historico_aluvion`, `quebradas_precordillera`
- `Infraestructura_y_Deficit_Estructural`: `deficit_colectores`, `obras_mitigacion_mop`, `cambio_climatico_precipitaciones`
- `Urbanizacion_y_Vulnerabilidad_Social`: `campamento_zona_exclusion`, `densificacion_impacto`, `limite_capacidad_municipal`

### Entrevista_DIPMA_La_Florida_20260108_000611.docx
Fuente: `logs/app.jsonl#L9641-L9647`
- `Problemas estructurales de drenaje urbano`: `crecimiento_urbano_desordenado`, `ausencia_normativa_aguas_lluvia`, `segregacion_hidraulica`
- `Estrategias de mitigación existentes`: `canales_regadio_como_colectores`, `soluciones_temporales`
- `Nuevo colector Avenida La Florida`: `colector_avenida_la_florida`, `limitaciones_municipales`

### Entrevista_equipo_Asesor_Urbano_La_Florida_20260108_000523.docx
Fuente: `logs/app.jsonl#L9811-L9820`
- `Gestion institucional del proyecto`: `responsabilidad_asesoria_urbana`, `coordinacion_municipal`, `alcance_limitado_proyecto`
- `Problemática histórica de drenaje urbano`: `problematicas_inundacion_historicas`, `infraestructura_historicamente_insuficiente`
- `Tensiones entre expectativas vecinales y proyecto`: `expectativa_vecinal`, `alcance_limitado_proyecto`, `necesidad_conexion_futura`
- `Transformacion urbana y presion futura`: `densificacion_asociada_al_metro`, `preocupacion_superficie`

### _entrevista_Gerente_Canal_San_Carlos_20260108_000506.docx
Fuente: `logs/app.jsonl#L9971-L9980`
- `Gobernanza y coordinacion institucional`: `convenio_marco_doh`, `coordinacion_municipal`, `necesidad_reunion_tecnica`, `condicion_aprobacion`
- `Riesgos sociales asociados a la infraestructura`: `presencia_tomas`, `riesgo_uso_recreacional`, `seguridad_infraestructura`
- `Intervencion hidraulica y capacidad tecnica`: `preocupacion_conexion_canal`, `limitacion_capacidad_descarga`, `desconocimiento_inicial`

## Oportunidad de automatización (bucle manual Discovery)
**Observación:** el bucle se está haciendo “a mano” pero sigue un patrón repetible: query amplia → agregar negativos → agregar texto objetivo → consolidar.

**Automatización mínima (sin cambiar UX):**
- Dado un memo/consulta base, generar 2 variantes automáticas:
  1) Variante con negativos (filtra charla logística)
  2) Variante con texto objetivo (enfoca el “rol del Estado”)
- Ejecutar Discovery para las variantes y comparar:
  - documentos top (cambios de ranking)
  - densidad de fragmentos relevantes
- Cerrar el loop con un “chequeo de aterrizaje” contra codificación ya persistida:
  - ¿aparecen categorías/códigos esperables (ej. `coordinacion_interinstitucional`, `limitaciones_municipales`) en los documentos top?

---
Fin.
