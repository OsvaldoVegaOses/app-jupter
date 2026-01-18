# Etapa 2 – Descriptivo inicial y base de codificación

> **Actualizado: Diciembre 2024**

## 1. Ficha de entrevistas institucionales

| Nº | Nombre completo | Sexo | Cargo / Rol | Organización | Sector |
|---:|-----------------|:----:|-------------|--------------|--------|
| 1 | Eduardo Camilo Durán González | M | Jefe de UTP | Escuela Cayenel | Sector Oriente y Poniente |
| 2 | Pablo Fábrega | M | Investigador / gestor territorial | Programa Quiero Mi Barrio | Sector Oriente y Poniente |
| 3 | Natalia Molina | F | Asesora en materias indígenas | SEREMI de las Culturas | Sector Oriente y Poniente |
| 4 | Claudia Schwerter | F | Área social / Trabajo comunitario | CESFAM Techo Para Todos | Sector Poniente |

Estos registros alimentan la metadata de ingesta para análisis por rol, género y territorio.

## 2. Pipeline de ingesta actual

### Flujo verificado (Dic 2024)
```
DOCX → documents.py (fragmentación)
     → embeddings.py (Azure OpenAI)
     → qdrant_block.py (vectores + 9 índices)
     → neo4j_block.py (grafo)
     → postgres_block.py (códigos)
```

### Metadatos indexados
| Campo | Tipo | Filtrable |
|-------|------|-----------|
| `project_id` | keyword | ✅ |
| `archivo` | keyword | ✅ |
| `speaker` | keyword | ✅ |
| `area_tematica` | keyword | ✅ |
| `actor_principal` | keyword | ✅ |
| `genero` | keyword | ✅ |
| `periodo` | keyword | ✅ |

## 3. Análisis descriptivo inicial

### Temas emergentes (institucional)

| Tema | Fuentes | Estado |
|------|---------|--------|
| Déficits urbano-territoriales | Camilo, Claudia | ✅ Codificado |
| Rol de infraestructura social | Claudia | ✅ Codificado |
| Participación/organización | Pablo, Claudia | ✅ Codificado |
| Memoria territorial | Camilo, Claudia | ✅ Codificado |

## 4. Códigos abiertos (Etapa 3)

| Código | Fuente | Estado |
|--------|--------|--------|
| Déficit de equipamientos | Camilo | ✅ Persistido |
| Riesgo / inundaciones | Camilo | ✅ Persistido |
| Coordinación intersectorial | Camilo | ✅ Persistido |
| Anclaje escuela | Natalia | ✅ Persistido |
| Anclaje salud (CESFAM) | Claudia | ✅ Persistido |
| Movilización dirigencial | Pablo | ✅ Persistido |
| Mezcla / transformación social | Camilo | ✅ Persistido |
| Memoria territorial | Claudia | ✅ Persistido |

## 5. Herramientas disponibles

### Dashboard
- **CodingPanel**: 4 pestañas para codificación manual
- **AnalysisPanel**: Análisis LLM asistido
- **Neo4jExplorer**: Visualización de grafo + GDS

### CLI
```bash
# Ingesta
python main.py ingest "entrevistas/*.docx" --project mi-proyecto

# Análisis LLM
python main.py analyze entrevistas/Camilo.docx --persist

# Estadísticas
python main.py coding stats --project mi-proyecto
```

### API
| Endpoint | Propósito |
|----------|-----------|
| `POST /api/ingest` | Ingesta de DOCX |
| `POST /api/coding/assign` | Asignar código |
| `POST /api/coding/suggest` | Sugerencias semánticas |
| `GET /api/coding/stats` | Estadísticas |

## 6. Nota de sesgo

La selección prioriza categorías de gestión, infraestructura y gobernanza. Se recomienda complementar con voces comunitarias para balancear la narrativa institucional.

---

*Última actualización: 13 Diciembre 2024*
