# Limitaciones Técnicas y Metodológicas del Sistema

Este documento registra las limitaciones conocidas del sistema para contexto académico y de desarrollo.

---

## 1. Sensibilidad del Evidence Gate en GraphRAG

### Descripción
El módulo GraphRAG incluye un **Evidence Gate** que rechaza consultas cuando la relevancia semántica de los fragmentos recuperados es insuficiente (score < 0.50).

### Observaciones
Durante pruebas con consultas sobre conceptos abstractos (ej: "identidad cultural", "vida comunitaria"), se observaron scores de relevancia entre **0.23 - 0.45**, activando el rechazo del gate.

### Implicaciones
- Conceptos de alto nivel no tienen un "ancla" única en el texto; están semánticamente dispersos
- El sistema puede requerir múltiples reformulaciones de la consulta
- Se activan mecanismos de fallback (búsqueda vectorial ponderada) cuando el método primario falla

### Mitigación Implementada (Sprint 20)
- El sistema ahora retorna un **mensaje explicativo** cuando el gate rechaza, en lugar de un error técnico
- Se proporciona feedback sobre el score obtenido y el mínimo requerido
- Se sugieren estrategias de reformulación al usuario

---

## 2. Sesgo del Algoritmo Preferential Attachment

### Descripción
El algoritmo de Link Prediction "Preferential Attachment" favorece códigos que ya tienen alta conectividad (grado alto).

### Implicaciones
- Los códigos frecuentemente codificados manualmente tienden a recibir más sugerencias automáticas
- Esto refuerza patrones existentes (consolidación) más que descubrir novedades (serendipia)

### Recomendación
- Para **consolidación estructural**: usar Preferential Attachment
- Para **descubrimiento/serendipia**: usar Adamic-Adar o búsqueda Discovery
- Interpretar scores altos como "rutas de confirmación" más que "descubrimientos"

---

## 3. Dependencia de Fallbacks en Discovery

### Descripción
La búsqueda Discovery usa la API Recommend de Qdrant cuando hay IDs ancla con score >= 0.55. Si no los hay, activa un **fallback ponderado**.

### Observaciones
Conceptos abstractos frecuentemente activan el fallback porque no alcanzan el umbral de ancla.

### Implicación
Los resultados del fallback son válidos pero metodológicamente diferentes:
- **Método primario**: Triangulación vectorial con anclajes fuertes
- **Fallback**: Búsqueda vectorial ponderada sin anclajes

---

## 4. Propiedad Inexistente en Neo4j (Corregido)

### Descripción
La query de extracción de subgrafo incluía una cláusula redundante buscando `f.fragmento_id` que no existía en el schema.

### Corrección (Sprint 20)
- Eliminada la cláusula `OR f.fragmento_id IN $fragment_ids`
- La query ahora usa únicamente `f.id`

---

## Registro de Cambios

| Fecha | Versión | Cambio |
|-------|---------|--------|
| 2025-12-30 | Sprint 20 | Fix NoneType error en GraphRAG, eliminación cláusula Neo4j redundante |
