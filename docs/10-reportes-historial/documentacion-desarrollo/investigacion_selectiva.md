# Investigación: Codificación Selectiva (Etapa 5)

He auditado el código para verificar el cumplimiento de los 4 criterios solicitados para la Codificación Selectiva:

### 1. Proponer Core Category por Señales (Centralidad/Coverage)
- **Estado**: **Implementado**.
- **Detalle**: La función `identify_nucleus_candidates` en `app/reports.py` y `nucleus_report` en `app/nucleus.py` utilizan PageRank (Neo4j) y métricas de cobertura (PostgreSQL).
- **Lógica**: Se marca como `done: true` solo si cumple umbrales de rango de centralidad (top 5), cobertura de entrevistas (mín. 3) y roles (mín. 2).

### 2. Generar Storyline con GraphRAG + Evidencias
- **Estado**: **Parcial / Infraestructura lista**.
- **Detalle**: Existe un motor potente de GraphRAG en `app/graphrag.py` que genera narrativas con citas. Sin embargo, el reporte del núcleo en `app/nucleus.py` actualmente usa una "sonda semántica" (`probe_semantics`) y una síntesis LLM basada en métricas, no una consulta GraphRAG profunda para el storyline.
- **Acción**: Es posible integrar `graphrag_query` en el flujo de `nucleus_report` para cumplir plenamente con la generación de la narrativa estructurada.

### 3. Registrar Artefacto Selectivo con Audit Trail
- **Estado**: **Implementado**.
- **Detalle**: Existe la tabla `analisis_nucleo_notas` en PostgreSQL.
- **Auditoría**: Guarda el `run_id`, la categoría, el memo humano, el resumen de la IA y el `payload` completo de la triangulación (JSONB), permitiendo reconstruir el estado del análisis en ese momento.

### 4. Validación Humana (Cierre de Teoría)
- **Estado**: **Implementado (por diseño preventivo)**.
- **Detalle**: El sistema genera el artefacto como una "Propuesta/Nota". No existe un mecanismo de "Cierre Automático".
- **Flujo**: El usuario debe revisar el reporte generado y realizar el "H-in-the-loop". No hay una transición de estado a "Cerrado" sin intervención, cumpliendo con la premisa de que el humano valida.

---
**Conclusión**: El sistema tiene la base técnica para operar según el modelo solicitado, faltando únicamente el "cableado" final para que el Storyline use el motor de GraphRAG en lugar de la sonda semántica simple.
