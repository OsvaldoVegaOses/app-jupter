# Matriz de validación epistemológica y metodológica (Grounded Theory)

Fecha: 2026-01-08

Este documento traduce los fundamentos de **Teoría Fundamentada** (GT/TF) y el contraste **positivista (Glaser & Strauss)** vs **constructivista (Charmaz)** en un set de **decisiones verificables** para cada proceso del sistema (ingesta, discovery, análisis, codificación y persistencia).

## 1) Fuentes base (fundamentos)
- [docs/fundamentos_teoria/Ejemplificación del proceso metodológico.pdf](../fundamentos_teoria/Ejemplificaci%C3%B3n%20del%20proceso%20metodol%C3%B3gico.pdf)
- [docs/fundamentos_teoria/marco teoria empiricamente fundamentada.pdf](../fundamentos_teoria/marco%20teoria%20empiricamente%20fundamentada.pdf)
- [docs/fundamentos_teoria/La_teoria.pdf](../fundamentos_teoria/La_teoria.pdf)
- [docs/fundamentos_teoria/La Metodología Constructivista  según Kathy Charmaz.pdf](../fundamentos_teoria/La%20Metodolog%C3%ADa%20Constructivista%20%20seg%C3%BAn%20Kathy%20Charmaz.pdf)
- [docs/fundamentos_teoria/El enfoque constructivista de Charmaz en teoría fundamentada.pdf](../fundamentos_teoria/El%20enfoque%20constructivista%20de%20Charmaz%20en%20teor%C3%ADa%20fundamentada.pdf)
- [docs/fundamentos_teoria/Ejercicio_Codificación Comparativa_ Positivista vs Constructivista.pdf](../fundamentos_teoria/Ejercicio_Codificaci%C3%B3n%20Comparativa_%20Positivista%20vs%20Constructivista.pdf)
- [docs/fundamentos_teoria/Prompts para Codificación_ Positivista vs Constructivista.pdf](../fundamentos_teoria/Prompts%20para%20Codificaci%C3%B3n_%20Positivista%20vs%20Constructivista.pdf)
- [docs/fundamentos_teoria/Teoría Empíricamente Fundada_ Análisis Exhaustivo de la Metodología Cualitativa.pdf](../fundamentos_teoria/Teor%C3%ADa%20Emp%C3%ADricamente%20Fundada_%20An%C3%A1lisis%20Exhaustivo%20de%20la%20Metodolog%C3%ADa%20Cualitativa.pdf)

## 2) Decisión epistemológica (para poder validar)

Para “validar epistemológica y metodológicamente” necesitas declarar (aunque sea operacionalmente) una postura de trabajo:

- **Opción A — Enfoque constructivista (Charmaz) (recomendado si tu objetivo es comprensión situada):**
  - El conocimiento es co-construido; el investigador/sistema no es neutro.
  - La trazabilidad exige reflexividad (por qué este prompt, por qué este filtro, por qué esta categoría).
  - La literatura se usa como **concepto sensibilizador**, no como molde rígido.

- **Opción B — Enfoque más objetivista/positivista (Glaser & Strauss):**
  - Se privilegia la “emergencia” y parsimonia; se evita imponer marcos tempranos.
  - La validación se centra en consistencia interna y repetibilidad de reglas de codificación.

**Regla práctica:** si no quieres decidir “filosóficamente”, decide “instrumentalmente”:
- Discovery = **muestreo teórico / conceptos sensibilizadores**.
- Codificación = **comparación constante + memos + saturación**.
- Persistencia = “congelar” versiones de teoría (auditable) sin impedir revisiones.

## 3) Artefactos del sistema que sirven como evidencia
Usa estos artefactos como “pruebas” de validación:

- Logs de eventos (`logs/app.jsonl`): audit trail de decisiones y ejecuciones.
- Memos de Discovery (`notes/<proyecto>/*.md`): reflexividad, cambios de anclas, negativos y texto objetivo.
- Reportes de análisis: salida consolidada (por entrevista) y sus métricas.
- Persistencias (PostgreSQL/Neo4j): estados estabilizados de códigos/categorías/relaciones.

## 4) Matriz de decisiones por proceso

Cada fila es una decisión que puedes “pasar” o “no pasar” (criterio observable).

### 4.1 Ingesta y normalización (datos → fragmentos)
**Decisión:** ¿Cómo segmentas / normalizas sin destruir significado?
- **Riesgo epistemológico:** “limpiar” borra matices (tono, énfasis, contexto) y cambia el fenómeno.
- **Criterio mínimo (metodológico):** toda transformación debe ser:
  - reversible o explicable,
  - parametrizada,
  - auditada.
- **Evidencia esperada:** parámetros de ingesta y resúmenes por archivo (nº fragmentos, issues) + capacidad de reconstruir qué salió de qué.

Checklist operativo:
- ¿Definiste explícitamente `min_chars/max_chars` y el criterio de coalescencia?
- ¿Guardaste un resumen por archivo (fragmentos, flagged, issues)?
- ¿Puedes rastrear un fragmento a su origen (archivo + posición)?

### 4.2 Discovery (refinamientos) (conceptos sensibilizadores → muestreo)
**Decisión:** ¿Tus “refinamientos” son exploración o imposición?
- **Interpretación GT:** refinamientos ≈ **muestreo teórico** y ajuste de conceptos sensibilizadores.
- **Riesgo epistemológico:** “confirmación” (buscar solo lo que esperas).
- **Criterio mínimo:** cada refinamiento debe dejar:
  - intención (qué intento aclarar),
  - cambio (qué anclas/negativos agregué y por qué),
  - resultado (qué trajo y qué dejó fuera).
- **Evidencia esperada:** memo guardado + registro de búsqueda (start/complete) + top_k/resultados.

Checklist operativo:
- ¿El memo declara por qué cambiaste positivos/negativos?
- ¿Mantienes un set pequeño de negativos “anti-ruido” (logística, conversación informal) para no contaminar?
- ¿Registras cuándo la búsqueda cae en fallback (anclas débiles) para no sobreinterpretar?

### 4.3 Discovery analyze (fragmentos seleccionados → síntesis)
**Decisión:** ¿La síntesis proviene del muestreo o está “sobreajustada” a la query?
- **Riesgo metodológico:** tratar 10 fragmentos como “la entrevista” o “el proyecto”.
- **Criterio mínimo:** toda síntesis debe declarar alcance:
  - “esto describe estos fragmentos bajo esta query”, no “describe todo”.
- **Evidencia esperada:** `fragment_count` y memo con alcance/limitaciones.

Checklist operativo:
- ¿La síntesis explicita límites (representatividad, sesgos)?
- ¿Comparas con al menos 1 refinamiento alternativo (contraste)?

### 4.4 Análisis por entrevista (entrevista → propuesta de códigos)
**Decisión:** ¿El análisis por entrevista es un episodio analítico trazable?
- **Riesgo epistemológico (Charmaz):** el sistema produce interpretaciones; debe hacerse visible la mediación (prompt/criterios).
- **Criterio mínimo:** para cada entrevista:
  - request_id trazable,
  - reporte generado/guardado,
  - lista de códigos con evidencia.
- **Evidencia esperada:** eventos de completitud del LLM + `report.saved` por archivo.

Checklist operativo:
- ¿Separaste claramente “análisis por entrevista” de “Discovery/refinamientos”?
- ¿Los códigos están formulados como procesos/acciones cuando corresponde (estilo Charmaz)?
- ¿Guardas versiones (si vuelves a correr, se nota qué cambió y por qué)?

### 4.5 Persistencia axial (códigos → categorías/relaciones)
**Decisión:** ¿Cuándo “congelas” una relación axial como parte de la teoría?
- **Interpretación GT:** axial ≈ organizar condiciones/causas/consecuencias; constructivista = aceptar que es un modelo situado y revisable.
- **Riesgo:** cristalizar temprano; o no cristalizar nunca.
- **Criterio mínimo:** una relación persistida debe tener:
  - justificación (memo o regla),
  - evidencia asociada (aunque sea conteo/links),
  - trazabilidad a entrevista(s).
- **Evidencia esperada:** persistencias por `archivo`, `categoria`, `codigo`, `relacion`, `evidencia_count`.

Checklist operativo:
- ¿Cada relación axial tiene definición operacional (qué significa “causa”, “condición”, “consecuencia” aquí)?
- ¿Se registran discrepancias (mismatch/índices) como parte del control de calidad?

## 5) Plantilla de “decisión validada” (para usar cada vez)

Copia/pega en un memo o en un registro del proyecto:

- **Proceso:** (ingesta | discovery | analyze | codificación | persistencia)
- **Decisión:**
- **Motivo epistemológico:** (constructivista/objetivista; co-construcción; emergente; etc.)
- **Motivo metodológico:** (comparación constante; muestreo teórico; saturación; audit trail)
- **Qué cambió (inputs/parámetros/prompts):**
- **Evidencia (logs/memo/reporte):**
- **Impacto esperado:**
- **Riesgo/limitación:**
- **Próxima verificación:**

---

Sugerencia: si quieres, puedo integrar esta matriz como una sección breve dentro de la documentación operativa de JD-009 para que quede “cerrado” en el paquete de entrega.
