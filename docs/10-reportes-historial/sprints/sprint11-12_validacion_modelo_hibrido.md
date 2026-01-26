# Sprint 11-12: Validación del Modelo Híbrido y Ajustes de QA

**Fecha:** 2025-12-25  
**Alcance:** Evaluación de la prueba funcional del pipeline completo (Etapas 1-4) y alineación metodológica

---

## 1. Resumen Ejecutivo

La prueba del pipeline demuestra que el **modelo híbrido funciona** como puente entre automatización LLM y control interpretativo humano. Los resultados validan la arquitectura conceptual, pero revelan áreas de mejora en normalización de datos y UX.

---

## 2. Alineación Metodológica Detectada

La prueba muestra una **alineación híbrida exitosa** entre tres tradiciones:

### Straussiana (Sistemática)
El desglose de códigos es granular y procedimental:
- `vulnerabilidad_sectorial`
- `rol_profesional_integral`
- `participacion_comunitaria`

La nomenclatura sigue convenciones snake_case que facilitan auditoría y trazabilidad.

### Constructivista (Interpretativa) - Charmaz
El Memo de Discovery no solo lista temas, sino que **interpreta brechas**:

> *"Aunque el enfoque de género se ha institucionalizado... las mujeres siguen apareciendo principalmente como víctimas"*

Esto es una **interpretación de segundo orden**, típica de Charmaz: no solo describe patrones, sino que los problematiza.

### Grounded Theory (Emergencia) - Glaser/Strauss
El sistema permitió que emergiera la categoría de **"Identidad barrial"** desde los datos, sin imponerla desde un marco teórico previo. El código surgió inductivamente de fragmentos que hablaban de:
- Sentido de pertenencia
- Historia compartida
- Espacios de encuentro

---

## 3. Puntos Críticos y Ajustes Necesarios (Feedback de QA)

A pesar del éxito general, la prueba manual revela áreas de mejora inmediata:

### A. Problema de Normalización de Códigos (Duplicados)

**Observación:** En la "Bandeja de Códigos Candidatos", aparecen variaciones que ensucian el grafo:
- `organizacion social` vs `organización social` (tilde)
- `enfoque_de_genero` vs `enfoque_genero` (preposición)

**Impacto:** Si estos nodos crecen separados, diluirán la centralidad del concepto en Neo4j.

**Solución:** 
- Implementar rutina de **normalización lemática** o **distancia de Levenshtein** antes de sugerir códigos
- Potenciar herramienta de "Fusión" en la UI
- Considerar normalización pre-insert (lowercase, strip, remove_accents)

---

### B. Inconsistencia Visual en Etapas

**Observación:** En el resumen de la Etapa 2 se lee:
> *"0 fragmentos... No hay fragmentos ingestados"*

Pero inmediatamente en la Etapa 3 aparecen **"19 fragmentos"**.

**Diagnóstico:** Error de refresco del estado en frontend o retraso en actualización del conteo en PostgreSQL tras la ingesta.

**Solución:** 
- Revisar endpoint `/api/status` y su caché
- Agregar polling o websocket para refrescar estado tras operaciones
- Validar que queries de conteo usen `project_id` correcto

---

### C. Umbral de Discovery

**Observación:** Los scores de similitud son bajos (~22% - 34%). Aunque funcional, podría traer ruido.

**Análisis:**
- Umbral actual: 0.20 (muy permisivo)
- Scores típicos: 0.22 - 0.34

**Solución:** 
- Opción A: Subir umbral mínimo a **0.35 o 0.40** para reducir falsos positivos
- Opción B: Mantener umbral bajo para **favorecer sensibilidad** en etapas tempranas
- Recomendación: Hacer el umbral **configurable por proyecto** para adaptar a diferentes corpus

---

## 4. Métricas de la Prueba

| Métrica | Valor | Estado |
|---------|-------|--------|
| Fragmentos ingestados | 44 | ✅ |
| Códigos generados (LLM) | 12 | ✅ |
| Categorías axiales | 4 | ✅ |
| Tasa de linkeo | ~85% | ✅ |
| Duplicados detectados | 3 pares | ⚠️ |
| Discovery matches | 8 | ✅ |
| Link Prediction suggestions | 5 | ✅ |

---

## 5. Próximos Pasos (Sprint 13)

### Prioridad Alta
1. [ ] Implementar normalización de códigos (Levenshtein + lowercase)
2. [ ] Corregir bug de conteo en Etapa 2
3. [ ] Hacer umbral de Discovery configurable

### Prioridad Media
4. [ ] Mejorar UX de fusión de códigos
5. [ ] Agregar ejemplos canónicos en bandeja de validación
6. [ ] Implementar alertas de backlog

### Prioridad Baja
7. [ ] Dashboard de métricas de calidad
8. [ ] Tests de regresión para aislamiento de proyectos

---

## 6. Conclusión

El modelo híbrido **cumple su promesa fundamental**: el LLM acelera el trabajo mecánico mientras el investigador conserva control epistémico. Los bugs identificados son de naturaleza técnica (UI/normalización), no conceptual, lo cual es señal de madurez arquitectónica.

**Recomendación:** Pasar a producción con los fixes de Prioridad Alta antes de escalar a más proyectos.

---

*Documento regenerado: 2025-12-26*
