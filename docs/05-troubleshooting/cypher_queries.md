# Base de Datos de Consultas Cypher

> **Proyecto:** Sistema de Análisis Cualitativo  
> **Última actualización:** 15 Diciembre 2024

---

## 📁 1. Consultas de Exploración Básica

### 1.1 Ver estructura del grafo
```cypher
// Contar todos los nodos por tipo
CALL db.labels() YIELD label
CALL apoc.cypher.run('MATCH (n:`' + label + '`) RETURN count(n) AS count', {}) YIELD value
RETURN label, value.count AS count
ORDER BY count DESC
```

### 1.2 Ver todos los tipos de relaciones
```cypher
CALL db.relationshipTypes() YIELD relationshipType
RETURN relationshipType
```

### 1.3 Muestra de nodos por tipo
```cypher
// Entrevistas
MATCH (e:Entrevista)
RETURN e.nombre, e.project_id, e.archivo
LIMIT 10

// Fragmentos
MATCH (f:Fragmento)
RETURN f.id, f.speaker, f.char_len, LEFT(f.texto, 100) AS texto_preview
LIMIT 10

// Códigos
MATCH (c:Codigo)
RETURN c.nombre, c.project_id, c.score_centralidad
ORDER BY c.score_centralidad DESC
LIMIT 20

// Categorías
MATCH (cat:Categoria)
RETURN cat.nombre, cat.project_id
LIMIT 10
```

---

## 📊 2. Consultas de Fragmentos y Entrevistas

### 2.1 Fragmentos por entrevista
```cypher
MATCH (e:Entrevista)-[:TIENE_FRAGMENTO]->(f:Fragmento)
RETURN e.nombre AS entrevista, count(f) AS num_fragmentos
ORDER BY num_fragmentos DESC
```

### 2.2 Fragmentos sin codificar (huérfanos)
```cypher
MATCH (e:Entrevista)-[:TIENE_FRAGMENTO]->(f:Fragmento)
WHERE NOT EXISTS {
    MATCH (f)<-[:EVIDENCIA]-(:Codigo)
}
RETURN e.nombre AS entrevista, f.id, f.speaker, LEFT(f.texto, 150) AS texto
LIMIT 50
```

### 2.3 Fragmentos por speaker (entrevistador vs entrevistado)
```cypher
MATCH (e:Entrevista)-[:TIENE_FRAGMENTO]->(f:Fragmento)
RETURN e.nombre, f.speaker, count(*) AS cantidad
ORDER BY e.nombre, f.speaker
```

### 2.4 Fragmentos largos (potencialmente ricos)
```cypher
MATCH (e:Entrevista)-[:TIENE_FRAGMENTO]->(f:Fragmento)
WHERE f.char_len > 500
RETURN e.nombre, f.speaker, f.char_len, LEFT(f.texto, 200) AS preview
ORDER BY f.char_len DESC
LIMIT 20
```

### 2.5 Fragmentos del entrevistado únicamente
```cypher
MATCH (e:Entrevista)-[:TIENE_FRAGMENTO]->(f:Fragmento)
WHERE f.speaker = 'interviewee' OR f.speaker IS NULL
RETURN e.nombre, f.id, LEFT(f.texto, 200) AS texto
LIMIT 50
```

---

## 🏷️ 3. Consultas de Códigos

### 3.1 Códigos más frecuentes (por número de citas)
```cypher
MATCH (c:Codigo)-[:EVIDENCIA]->(f:Fragmento)
RETURN c.nombre AS codigo, count(f) AS num_citas
ORDER BY num_citas DESC
LIMIT 20
```

### 3.2 Códigos sin citas (posibles errores)
```cypher
MATCH (c:Codigo)
WHERE NOT EXISTS {
    MATCH (c)-[:EVIDENCIA]->(:Fragmento)
}
RETURN c.nombre, c.project_id
```

### 3.3 Códigos por centralidad (PageRank)
```cypher
MATCH (c:Codigo)
WHERE c.score_centralidad IS NOT NULL
RETURN c.nombre, c.score_centralidad
ORDER BY c.score_centralidad DESC
LIMIT 15
```

### 3.4 Códigos por comunidad (Louvain)
```cypher
MATCH (c:Codigo)
WHERE c.comunidad IS NOT NULL
RETURN c.comunidad AS grupo, collect(c.nombre) AS codigos, count(*) AS cantidad
ORDER BY cantidad DESC
```

### 3.5 Códigos aislados (sin relaciones axiales)
```cypher
MATCH (c:Codigo)
WHERE NOT EXISTS {
    MATCH (c)<-[:AGRUPA|CAUSA|CONDICION|CONSECUENCIA]-(:Categoria)
}
RETURN c.nombre, c.project_id
```

---

## 📂 4. Consultas de Categorías Axiales

### 4.1 Categorías con sus códigos
```cypher
MATCH (cat:Categoria)-[r]->(c:Codigo)
RETURN cat.nombre AS categoria, type(r) AS relacion, collect(c.nombre) AS codigos
ORDER BY categoria
```

### 4.2 Categorías por número de códigos
```cypher
MATCH (cat:Categoria)-[r]->(c:Codigo)
RETURN cat.nombre AS categoria, count(c) AS num_codigos
ORDER BY num_codigos DESC
```

### 4.3 Relaciones causales entre categorías
```cypher
MATCH (cat1:Categoria)-[r:CAUSA|CONDICION|CONSECUENCIA]->(cat2:Categoria)
RETURN cat1.nombre AS origen, type(r) AS relacion, cat2.nombre AS destino
```

### 4.4 Jerarquía completa (categoría → códigos → fragmentos)
```cypher
MATCH (cat:Categoria)-[:AGRUPA]->(c:Codigo)-[:EVIDENCIA]->(f:Fragmento)
RETURN cat.nombre AS categoria, c.nombre AS codigo, count(f) AS evidencias
ORDER BY categoria, evidencias DESC
```

---

## 🔗 5. Consultas de Relaciones

### 5.1 Todas las relaciones entre códigos
```cypher
MATCH (c1:Codigo)-[r]->(c2:Codigo)
RETURN c1.nombre AS origen, type(r) AS tipo, c2.nombre AS destino
LIMIT 50
```

### 5.2 Cadenas causales (A causa B causa C)
```cypher
MATCH path = (c1:Codigo)-[:CAUSA*1..3]->(c2:Codigo)
RETURN [node in nodes(path) | node.nombre] AS cadena_causal
LIMIT 20
```

### 5.3 Códigos conectados a un código específico
```cypher
MATCH (c:Codigo {nombre: 'NOMBRE_DEL_CODIGO'})-[r]-(relacionado)
RETURN type(r) AS relacion, labels(relacionado) AS tipo, 
       CASE WHEN relacionado:Codigo THEN relacionado.nombre 
            WHEN relacionado:Categoria THEN relacionado.nombre 
            ELSE relacionado.id END AS nombre
```

### 5.4 Subgrafo de una categoría
```cypher
MATCH (cat:Categoria {nombre: 'NOMBRE_CATEGORIA'})-[r1]->(c:Codigo)-[r2]->(f:Fragmento)
RETURN cat, r1, c, r2, f
LIMIT 50
```

---

## 📈 6. Consultas Analíticas (GDS)

### 6.1 Nodos más centrales (después de PageRank)
```cypher
MATCH (n)
WHERE n.score_centralidad IS NOT NULL
RETURN labels(n)[0] AS tipo, n.nombre AS nombre, n.score_centralidad AS centralidad
ORDER BY centralidad DESC
LIMIT 20
```

### 6.2 Comunidades detectadas (después de Louvain)
```cypher
MATCH (n)
WHERE n.comunidad IS NOT NULL
RETURN n.comunidad AS comunidad, labels(n)[0] AS tipo, collect(n.nombre) AS miembros
ORDER BY comunidad
```

### 6.3 Betweenness (nodos puente)
```cypher
MATCH (c:Codigo)
WHERE c.betweenness IS NOT NULL
RETURN c.nombre, c.betweenness
ORDER BY c.betweenness DESC
LIMIT 10
```

---

## 🔍 7. Consultas de Búsqueda

### 7.1 Buscar fragmentos por texto
```cypher
MATCH (f:Fragmento)
WHERE f.texto CONTAINS 'participación'
RETURN f.id, LEFT(f.texto, 200) AS preview
LIMIT 20
```

### 7.2 Buscar códigos por nombre parcial
```cypher
MATCH (c:Codigo)
WHERE toLower(c.nombre) CONTAINS 'seguridad'
RETURN c.nombre, c.project_id
```

### 7.3 Fragmentos que mencionan múltiples conceptos
```cypher
MATCH (f:Fragmento)
WHERE f.texto CONTAINS 'participación' AND f.texto CONTAINS 'comunidad'
RETURN f.id, LEFT(f.texto, 300) AS texto
LIMIT 10
```

---

## 🧹 8. Consultas de Mantenimiento

### 8.1 Verificar integridad (fragmentos sin entrevista)
```cypher
MATCH (f:Fragmento)
WHERE NOT EXISTS {
    MATCH (:Entrevista)-[:TIENE_FRAGMENTO]->(f)
}
RETURN f.id, f.project_id
```

### 8.2 Códigos duplicados (mismo nombre)
```cypher
MATCH (c:Codigo)
WITH c.nombre AS nombre, collect(c) AS codigos, count(*) AS cantidad
WHERE cantidad > 1
RETURN nombre, cantidad
```

### 8.3 Contar por proyecto
```cypher
MATCH (n)
WHERE n.project_id IS NOT NULL
RETURN n.project_id AS proyecto, labels(n)[0] AS tipo, count(*) AS cantidad
ORDER BY proyecto, tipo
```

### 8.4 Eliminar proyecto completo (¡PELIGROSO!)
```cypher
// PRECAUCIÓN: Elimina todos los datos del proyecto
MATCH (n {project_id: 'NOMBRE_PROYECTO'})
DETACH DELETE n
```

---

## 📊 9. Consultas para Reportes

### 9.1 Resumen del corpus
```cypher
MATCH (e:Entrevista)-[:TIENE_FRAGMENTO]->(f:Fragmento)
WITH e.project_id AS proyecto, count(DISTINCT e) AS entrevistas, count(f) AS fragmentos
MATCH (c:Codigo {project_id: proyecto})
WITH proyecto, entrevistas, fragmentos, count(c) AS codigos
MATCH (cat:Categoria {project_id: proyecto})
RETURN proyecto, entrevistas, fragmentos, codigos, count(cat) AS categorias
```

### 9.2 Matriz de co-ocurrencia (códigos que aparecen juntos)
```cypher
MATCH (c1:Codigo)-[:EVIDENCIA]->(f:Fragmento)<-[:EVIDENCIA]-(c2:Codigo)
WHERE id(c1) < id(c2)
RETURN c1.nombre AS codigo_1, c2.nombre AS codigo_2, count(f) AS coocurrencias
ORDER BY coocurrencias DESC
LIMIT 20
```

### 9.3 Densidad de codificación por entrevista
```cypher
MATCH (e:Entrevista)-[:TIENE_FRAGMENTO]->(f:Fragmento)
OPTIONAL MATCH (c:Codigo)-[:EVIDENCIA]->(f)
WITH e.nombre AS entrevista, count(DISTINCT f) AS fragmentos, count(DISTINCT c) AS codigos_usados
RETURN entrevista, fragmentos, codigos_usados, 
       round(100.0 * codigos_usados / fragmentos, 1) AS densidad_pct
ORDER BY densidad_pct DESC
```

---

## 🎯 10. Consultas Específicas del Proyecto

### 10.1 Tu consulta original (fragmentos sin relación específica)
```cypher
MATCH (e:Entrevista)-[t:TIENE_FRAGMENTO]->(f:Fragmento)
WHERE NOT EXISTS {
    MATCH (e)-[r]->(f)
    WHERE type(r) <> 'TIENE_FRAGMENTO'
}
RETURN e.nombre, f.speaker, LEFT(f.texto, 200) AS texto, t.char_len
LIMIT 50
```

### 10.2 [Agregar tu segunda consulta aquí]
```cypher
// Descripción:
// Consulta:
```

---

## Uso desde la API

```bash
# Ejecutar consulta Cypher
curl -X POST http://localhost:8000/api/neo4j/query \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cypher": "MATCH (c:Codigo) RETURN c.nombre LIMIT 10",
    "project": "default",
    "formats": ["raw"]
  }'
```

---

*Documento mantenido por el equipo de investigación*
