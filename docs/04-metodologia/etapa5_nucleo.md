# Etapa 5 - Selección del Núcleo Selectivo

> **Objetivo**: Identificar y validar la categoría central que integra todas las demás y representa el fenómeno principal de la investigación.

---

## Prerrequisitos

Antes de ejecutar la Etapa 5, debes haber completado:

| Etapa | Verificación | Comando |
|-------|--------------|---------|
| E0 - Preparación | Servicios funcionando | `python scripts/healthcheck.py` |
| E1 - Ingesta | Fragmentos en Qdrant/PostgreSQL | `python main.py ingest *.docx` |
| E3 - Codificación Abierta | Códigos creados | `python main.py coding stats` |
| E4 - Codificación Axial | Centralidad calculada | `python main.py axial gds --algorithm pagerank` |

---

## Comando Principal

```bash
python main.py nucleus report \
  --categoria "Nombre de la Categoría" \
  --prompt "descripción semántica del fenómeno" \
  --project <proyecto> \
  --llm-model gpt-5-mini \
  --persist
```

### Parámetros

| Parámetro | Descripción | Default |
|-----------|-------------|---------|
| `--categoria` | Nombre de la categoría candidata a núcleo | **Requerido** |
| `--prompt` | Texto para probe semántico en Qdrant | Opcional |
| `--project` | ID del proyecto | `default` |
| `--min-interviews` | Mínimo de entrevistas cubiertas | 3 |
| `--min-roles` | Mínimo de roles cubiertos | 2 |
| `--min-quotes` | Mínimo de citas icónicas | 5 |
| `--llm-model` | Modelo para generar resumen analítico | Opcional |
| `--persist` | Guardar resultado en PostgreSQL | `false` |

---

## Criterios de Validación (Checks)

El núcleo se considera **válido** (`done: true`) cuando los 4 checks pasan:

### 1. Centralidad (Neo4j)
```
centrality_ok = categoria.rank <= 5
```
- Usa PageRank o similar calculado en Etapa 4
- La categoría debe estar en el top 5 de centralidad

### 2. Cobertura (PostgreSQL)
```
coverage_ok = entrevistas >= 3 AND roles >= 2
```
- La categoría debe aparecer en múltiples entrevistas
- Debe cubrir al menos 2 roles diferentes (ej: vecinos, funcionarios)

### 3. Citas Icónicas (PostgreSQL)
```
quotes_ok = citas_totales >= 5
```
- Debe tener suficientes fragmentos codificados
- Las citas se usan como evidencia en el informe final

### 4. Probe Semántico (Qdrant)
```
probe_ok = entrevistas_en_resultados >= 3
```
- El prompt debe retornar fragmentos de al menos 3 entrevistas diferentes
- Valida que el concepto tiene relevancia semántica transversal

---

## Flujo de Datos

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Neo4j     │     │ PostgreSQL  │     │   Qdrant    │
│  (Grafo)    │     │   (Datos)   │     │ (Vectores)  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       ▼                   ▼                   ▼
 centrality_overview  coverage_report    probe_semantics
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
                    nucleus_report()
                           │
                           ▼
                   ┌───────────────┐
                   │  done: true   │
                   │  o            │
                   │  done: false  │
                   │  + acciones   │
                   └───────────────┘
```

---

## Ejemplo de Resultado

```json
{
  "categoria": "Participación Ciudadana",
  "done": true,
  "checks": {
    "centrality": true,
    "coverage": true,
    "quotes": true,
    "probe": true
  },
  "centrality": {
    "candidate": {
      "nombre": "Participación Ciudadana",
      "rank": 1,
      "score": 0.234
    }
  },
  "coverage": {
    "entrevistas_cubiertas": 8,
    "roles_cubiertos": 4,
    "quote_count": 23
  },
  "llm_summary": "La categoría presenta alta centralidad y cobertura..."
}
```

---

## Acciones Correctivas

Si algún check falla:

| Check | Acción |
|-------|--------|
| `centrality: false` | Re-ejecutar `axial gds --algorithm pagerank` o revisar estructura del grafo |
| `coverage: false` | Analizar más entrevistas o completar metadatos (roles, áreas temáticas) |
| `quotes: false` | Codificar más fragmentos con esa categoría |
| `probe: false` | Ajustar el prompt o verificar indexación en Qdrant |

---

## Siguiente Etapa

Una vez `done: true`, proceder a:

**Etapa 6 - Análisis Transversal**
```bash
python main.py transversal dashboard \
  --prompt "participación ciudadana" \
  --attribute genero \
  --values mujeres hombres
```
