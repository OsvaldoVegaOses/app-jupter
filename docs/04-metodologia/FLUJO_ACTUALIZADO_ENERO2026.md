# Flujo de Investigación Cualitativa: Guía Actualizada

> **Versión:** 3.0  
> **Fecha:** 23 de Enero de 2026  
> **Ámbito:** APP_Jupter - Análisis Cualitativo con GraphRAG + Grounded Theory

---

## Índice

1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Arquitectura Actualizada](#arquitectura-actualizada)
3. [Flujo de Codificación con Bandeja de Candidatos](#flujo-de-codificación-con-bandeja-de-candidatos)
4. [Modos Epistémicos](#modos-epistémicos)
5. [Etapas del Ciclo Cualitativo](#etapas-del-ciclo-cualitativo)
6. [Sincronización Neo4j](#sincronización-neo4j)
7. [Uso del Frontend](#uso-del-frontend)
8. [Comandos CLI](#comandos-cli)
9. [Troubleshooting](#troubleshooting)

---

## Resumen Ejecutivo

El sistema implementa **Teoría Fundamentada (Grounded Theory)** con apoyo de LLM y GraphRAG. La versión 3.0 introduce:

| Característica | Descripción |
|----------------|-------------|
| **Bandeja de Candidatos** | Todos los códigos pasan por validación antes de ser definitivos |
| **Modos Epistémicos** | Constructivista o Post-Positivista según marco teórico |
| **Sync Neo4j al Promover** | El grafo se actualiza automáticamente al promover candidatos |
| **GraphRAG Contextual** | LLM recibe contexto del grafo (centralidad, comunidades) |

### Diagrama de Etapas

```
┌─────────┬─────────────┬─────────────┬─────────────┬─────────────┐
│ Etapa 0 │   Etapa 1   │   Etapa 2   │   Etapa 3   │   Etapa 4   │
│Reflexi- │  Ingesta    │ Descriptivo │ Cod.Abierta │ Cod. Axial  │
│ vidad   │ DOCX→3 BD   │ Discovery   │ Candidatos  │ Categorías  │
└────┬────┴──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┘
     │           │             │             │             │
     ▼           ▼             ▼             ▼             ▼
┌─────────┐ ┌─────────┐ ┌─────────────┐ ┌───────────┐ ┌─────────────┐
│Observa- │ │PG+Qdrant│ │ Búsqueda    │ │ Validar/  │ │ Relaciones  │
│ciones   │ │ +Neo4j  │ │ Semántica   │ │ Promover  │ │ Tipadas     │
│Iniciales│ │         │ │             │ │           │ │             │
└─────────┘ └─────────┘ └─────────────┘ └─────┬─────┘ └──────┬──────┘
                                              │              │
                                              ▼              ▼
                                        ┌─────────────────────────┐
                                        │   Neo4j Graph Sync      │
                                        │ (automático al promover)│
                                        └─────────────────────────┘
```

---

## Arquitectura Actualizada

### Persistencia por Capas

```
┌─────────────────────────────────────────────────────────────────┐
│                     CAPA DE PRESENTACIÓN                        │
│  Frontend React + TypeScript (Puerto 5174)                      │
│  - Dashboard del Ciclo Cualitativo                              │
│  - Panel de Codificación (E3)                                   │
│  - Neo4j Explorer (E4)                                          │
│  - Bandeja de Candidatos                                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     CAPA DE API (FastAPI)                       │
│  Backend Python (Puerto 8000)                                   │
│  - /api/projects/* (gestión proyectos)                          │
│  - /api/ingest (ingesta DOCX)                                   │
│  - /api/analyze (análisis LLM)                                  │
│  - /api/codes/candidates/* (bandeja de candidatos) ← NUEVO      │
│  - /neo4j/* (consultas Cypher)                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  CAPA DE PERSISTENCIA                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  PostgreSQL  │  │    Qdrant    │  │    Neo4j     │           │
│  │ (Relacional) │  │  (Vectores)  │  │   (Grafo)    │           │
│  ├──────────────┤  ├──────────────┤  ├──────────────┤           │
│  │entrevista_   │  │ Collection:  │  │ :Entrevista  │           │
│  │ fragmentos   │  │  fragments   │  │ :Fragmento   │           │
│  │codigos_      │  │ (embeddings) │  │ :Codigo      │           │
│  │ candidatos   │  │              │  │ :Categoria   │           │
│  │analisis_     │  │              │  │ -[:TIENE_*]->│           │
│  │ codigos_     │  │              │  │              │           │
│  │ abiertos     │  │              │  │              │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

### Aislamiento por Proyecto

| Capa | Implementación |
|------|----------------|
| Qdrant | Colección global + filtro `project_id` en payload |
| PostgreSQL | `WHERE project_id = $1` en todas las queries |
| Neo4j | `WHERE n.project_id = $project_id` en Cypher |
| Blob Storage | Path: `interviews/{project_id}/{archivo}.docx` |

---

## Flujo de Codificación con Bandeja de Candidatos

### Modelo Híbrido Actualizado (Enero 2026)

```
┌──────────────────────────────────────────────────────────────────┐
│                    FUENTES DE CÓDIGOS                            │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. LLM Analysis        2. Discovery          3. Sugerencias     │
│     (analyze.py)           (triplets)            Semánticas      │
│         │                    │                      │            │
│         └────────────────────┴──────────────────────┘            │
│                              │                                   │
│                              ▼                                   │
│              ┌───────────────────────────────┐                   │
│              │    codigos_candidatos         │                   │
│              │    (estado: pendiente)        │                   │
│              │    origen: llm/discovery/     │                   │
│              │           sugerencia          │                   │
│              └───────────────┬───────────────┘                   │
│                              │                                   │
│                              ▼                                   │
│              ┌───────────────────────────────┐                   │
│              │   Bandeja de Validación UI    │                   │
│              │   (CodeValidationPanel)       │                   │
│              └───────────────┬───────────────┘                   │
│                              │                                   │
│            ┌─────────────────┼─────────────────┐                 │
│            ▼                 ▼                 ▼                 │
│       ┌────────┐        ┌────────┐        ┌────────┐             │
│       │Rechazar│        │ Editar │        │Validar │             │
│       └────────┘        └────────┘        └────┬───┘             │
│                                                │                 │
│                                                ▼                 │
│                              ┌───────────────────────────────┐   │
│                              │      Promover Código          │   │
│                              │  (promote_to_definitive)      │   │
│                              └───────────────┬───────────────┘   │
│                                              │                   │
│                    ┌─────────────────────────┼─────────────────┐ │
│                    ▼                         ▼                 │ │
│    ┌───────────────────────────┐  ┌─────────────────────────┐  │ │
│    │ analisis_codigos_abiertos │  │      Neo4j Sync         │  │ │
│    │     (PostgreSQL)          │  │ merge_fragment_codes_   │  │ │
│    │                           │  │       bulk()            │  │ │
│    └───────────────────────────┘  │ (TIENE_CODIGO relation) │  │ │
│                                   └─────────────────────────┘  │ │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Estados de Candidatos

| Estado | Descripción | Acción |
|--------|-------------|--------|
| `pendiente` | Recién creado, sin revisar | Requiere validación |
| `validado` | Aprobado por investigador | Listo para promover |
| `rechazado` | Descartado | Archivado |
| `fusionado` | Unificado con otro código | Referencia al destino |

### Métricas de Sincronización

Al promover códigos, el sistema reporta:

```json
{
  "success": true,
  "promoted_count": 15,
  "eligible_total": 17,
  "skipped_total": 2,
  "neo4j_merged": 15,
  "neo4j_missing_fragments": 2
}
```

| Métrica | Significado |
|---------|-------------|
| `promoted_count` | Códigos insertados en lista definitiva |
| `neo4j_merged` | Relaciones TIENE_CODIGO creadas en Neo4j |
| `neo4j_missing_fragments` | Fragmentos no sincronizados aún en Neo4j |

---

## Modos Epistémicos

El sistema soporta dos marcos epistemológicos que afectan los prompts de análisis:

### Constructivista (por defecto)

- **Enfoque:** Interpretación situada, reflexividad
- **Objetivo:** Capturar significados construidos por participantes
- **Prompts:** Énfasis en voz del participante, contexto sociocultural
- **Ubicación:** `app/prompts/constructivist/`

### Post-Positivista

- **Enfoque:** Objetividad, triangulación, verificabilidad
- **Objetivo:** Identificar patrones replicables
- **Prompts:** Énfasis en evidencia, citas textuales, frecuencias
- **Ubicación:** `app/prompts/post_positivist/`

### Configuración

```bash
# .env
EPISTEMIC_MODE=constructivist  # o post_positivist
```

O selecciónalo en el UI del proyecto (Panel de Investigación → Modo Epistemológico).

### Estructura de Prompts

```
app/prompts/
├── constructivist/
│   ├── etapa0_reflexividad.txt
│   ├── etapa1_ingesta.txt
│   ├── etapa2_descriptivo.txt
│   ├── etapa3_cod_abierta.txt
│   ├── etapa4_cod_axial.txt
│   ├── etapa5_nucleo.txt
│   ├── etapa6_transversal.txt
│   ├── etapa7_validacion.txt
│   ├── etapa8_integracion.txt
│   └── etapa9_reporte.txt
├── post_positivist/
│   └── [misma estructura]
└── loader.py  # Cargador según modo activo
```

---

## Etapas del Ciclo Cualitativo

### Etapa 0: Reflexividad

**Propósito:** Registro inicial de sesgos y posicionamiento del investigador.

**UI:** Panel "Observaciones" en Dashboard

**Proceso:**
1. Revisar coherencia de transcripciones
2. Registrar posición epistemológica
3. Documentar supuestos iniciales

### Etapa 1: Ingesta

**Propósito:** Procesar documentos DOCX/TXT y generar embeddings.

**UI:** Panel "Entrevistas Ingestadas" + botón "Usar"

**Proceso:**
1. Subir archivo DOCX
2. Fragmentación automática (párrafos)
3. Embeddings → Qdrant
4. Metadatos → PostgreSQL
5. Nodos → Neo4j

**Comando CLI:**
```powershell
python main.py ingest "entrevista.docx" --project mi_proyecto
```

### Etapa 2: Análisis Descriptivo

**Propósito:** Exploración semántica antes de codificar.

**UI:** Panel "Discovery - Búsqueda Exploratoria"

**Características:**
- Conceptos positivos/negativos para búsqueda contrastiva
- Triplets semánticos (ver fragmentos relacionados)
- "Proponer como código" → envía a bandeja de candidatos

**Comando CLI:**
```powershell
python main.py search "participación comunitaria" --project mi_proyecto
```

### Etapa 3: Codificación Abierta

**Propósito:** Asignar códigos emergentes a fragmentos.

**UI:** Panel "Codificación Abierta" + "Bandeja de Códigos Candidatos"

**Flujo:**
1. Seleccionar fragmento recomendado
2. Ver sugerencias semánticas de códigos
3. Asignar código (crea candidato en estado `pendiente`)
4. Validar en bandeja
5. Promover a lista definitiva → **Sync automático a Neo4j**

**Nuevo comportamiento (Enero 2026):**
- Al promover, se crea relación `(:Fragmento)-[:TIENE_CODIGO]->(:Codigo)` en Neo4j
- El grafo refleja solo códigos **definitivos** (no candidatos)

### Etapa 4: Codificación Axial

**Propósito:** Crear categorías y relaciones entre códigos.

**UI:** Panel "Neo4j Explorer" + "Codificación Axial"

**Tipos de Relación:**

| Tipo | Significado | Ejemplo |
|------|-------------|---------|
| `partede` | Jerárquica | "Liderazgo" es parte de "Gobernanza" |
| `causa` | Causal | "Desconfianza" causa "Baja participación" |
| `condicion` | Dependencia | "Recursos" es condición de "Organización" |
| `consecuencia` | Resultado | "Organización" consecuencia de "Capacitación" |

**Algoritmos disponibles (GDS/NetworkX):**
- Louvain (comunidades)
- PageRank (centralidad)
- Betweenness (intermediación)

### Etapas 5-9: Avanzadas

| Etapa | Descripción | Comando CLI |
|-------|-------------|-------------|
| E5 Núcleo | Categoría central | `python main.py nucleus report --categoria "X"` |
| E6 Transversal | Comparaciones | `python main.py transversal dashboard` |
| E7 Validación | Saturación | `python main.py validation curve` |
| E8-9 Reporte | Informe final | `python main.py report build` |

---

## Sincronización Neo4j

### Arquitectura de Sync

```
┌────────────────────────────────────────────────────────────────┐
│                    SYNC AL PROMOVER                            │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  POST /api/codes/candidates/promote                            │
│         │                                                      │
│         ▼                                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  promote_to_definitive() (postgres_block.py)            │   │
│  │    - INSERT INTO analisis_codigos_abiertos              │   │
│  │    - RETORNA: [(fragmento_id, canonical_codigo), ...]   │   │
│  └──────────────────────────┬──────────────────────────────┘   │
│                             │                                  │
│         ┌───────────────────┴───────────────────┐              │
│         │ Si SYNC_NEO4J_ON_PROMOTE=true         │              │
│         │ (default: true)                        │              │
│         ▼                                        │              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  merge_fragment_codes_bulk() (neo4j_block.py)           │   │
│  │    - UNWIND $rows AS row                                │   │
│  │    - MATCH (f:Fragmento {fragmento_id: row.frag_id})    │   │
│  │    - MERGE (c:Codigo {nombre: row.codigo, project_id})  │   │
│  │    - MERGE (f)-[:TIENE_CODIGO]->(c)                     │   │
│  │                                                         │   │
│  │  RETORNA: { merged: N, missing_fragments: M }           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Feature Flag

```bash
# .env
SYNC_NEO4J_ON_PROMOTE=true   # Habilitar sync automático (default)
SYNC_NEO4J_ON_PROMOTE=false  # Deshabilitar para rollback
```

### Verificar Sincronización

```cypher
// Ver códigos con sus fragmentos
MATCH (f:Fragmento)-[:TIENE_CODIGO]->(c:Codigo)
WHERE c.project_id = 'jd-007'
RETURN c.nombre AS codigo, count(f) AS fragmentos
ORDER BY fragmentos DESC

// Ver si hay códigos sin fragmentos (huérfanos)
MATCH (c:Codigo)
WHERE c.project_id = 'jd-007'
  AND NOT ((:Fragmento)-[:TIENE_CODIGO]->(c))
RETURN c.nombre AS codigo_huerfano
```

---

## Uso del Frontend

### Dashboard Principal

```
┌─────────────────────────────────────────────────────────────────┐
│  Dashboard del Ciclo Cualitativo         [jd-007] ▼   [Usuario]│
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Proyecto Activo: jd-007                                │   │
│  │  Modo Epistemológico: [CONSTRUCTIVISTA ▾]               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────┐ ┌──────────────┐ ┌──────────────┐ ┌───────────┐  │
│  │ Inicio   │ │ Flujo Trabajo│ │ Investigación│ │ Reportes  │  │
│  └──────────┘ └──────────────┘ └──────────────┘ └───────────┘  │
│                                                                 │
│  ═══════════════════════════════════════════════════════════   │
│                    [Contenido del Tab]                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Bandeja de Códigos Candidatos

| Columna | Descripción |
|---------|-------------|
| Código | Nombre del código candidato |
| Origen | `llm`, `discovery`, `sugerencia`, `manual` |
| Estado | 🟡 Pendiente, 🟢 Validado, 🔴 Rechazado |
| Score | Confianza semántica (0-1) |
| Cita | Fragmento de evidencia |
| Acciones | ✓ Validar, ✗ Rechazar, 🔗 Ver en contexto |

### Botones Principales

| Botón | Acción |
|-------|--------|
| **Promover validados** | Mueve todos los validados a lista definitiva + Sync Neo4j |
| **Fusionar duplicados** | Detecta y unifica códigos similares |
| **Actualizar** | Recarga la bandeja |

### Métricas Mostradas

Al promover, el sistema muestra:

```
✅ 15 fila(s) promovida(s) a la lista definitiva.
(elegibles: 17 · omitidos (sin evidencia): 2)
🔗 Neo4j: 15 relación(es) sincronizada(s), 2 fragmento(s) pendiente(s)
```

---

## Comandos CLI

### Gestión de Proyecto

```powershell
# Listar proyectos
python main.py projects list

# Crear proyecto
python main.py projects create mi_proyecto --description "Descripción"
```

### Ingesta

```powershell
# Ingestar DOCX
python main.py ingest "entrevista.docx" --project mi_proyecto

# Ingestar con metadata
python main.py ingest "entrevista.docx" --project mi_proyecto \
    --metadata genero=F --metadata rol="dirigente"
```

### Codificación

```powershell
# Ver estadísticas de codificación
python main.py coding stats --project mi_proyecto

# Asignar código
python main.py coding assign \
    --fragment-id <uuid> \
    --codigo "participación" \
    --cita "La comunidad se organiza..."
```

### Axial

```powershell
# Crear relación axial
python main.py axial relate \
    --categoria "Gobernanza" \
    --codigo "liderazgo" \
    --tipo causa \
    --evidencia <id1> <id2>

# Ejecutar algoritmo de grafo
python main.py axial gds --algorithm louvain --project mi_proyecto
```

### GraphRAG

```powershell
# Consulta GraphRAG
python main.py graphrag query \
    --question "¿Qué factores afectan la participación?" \
    --project mi_proyecto
```

---

## Troubleshooting

### Síntomas Comunes

| Síntoma | Causa Probable | Solución |
|---------|----------------|----------|
| "neo4j_missing_fragments" alto | Entrevistas no sincronizadas | Ejecutar sync de fragmentos primero |
| Códigos no aparecen en grafo | No promovidos | Promover desde bandeja |
| Promover falla | Sin `fragmento_id` | Verificar que candidatos tengan evidencia |
| Discovery no encuentra | Proyecto incorrecto | Verificar selector de proyecto |

### Verificar Estado del Sistema

```powershell
# Verificar conexiones
python scripts/healthcheck.py

# Ver logs
Get-Content logs/app.jsonl -Tail 50 | ConvertFrom-Json | Format-Table timestamp, event, level
```

### Forzar Sync Manual

```powershell
# Sync fragmentos a Neo4j
python scripts/sync_neo4j_axial.py --project mi_proyecto

# Re-sync específico
python -c "
from app.neo4j_block import merge_fragment_codes_bulk
from app.clients import get_neo4j_driver
from app.settings import load_settings

settings = load_settings()
driver = get_neo4j_driver(settings.neo4j)

rows = [
    {'fragmento_id': 'xxx', 'codigo': 'participación'},
    {'fragmento_id': 'yyy', 'codigo': 'liderazgo'}
]

result = merge_fragment_codes_bulk(driver, settings.neo4j.database, rows, 'mi_proyecto')
print(result)
"
```

---

## Referencias

### Archivos Clave

| Función | Archivo |
|---------|---------|
| Bandeja candidatos | `app/postgres_block.py` → `promote_to_definitive()` |
| Sync Neo4j | `app/neo4j_block.py` → `merge_fragment_codes_bulk()` |
| UI candidatos | `frontend/src/components/CodeValidationPanel.tsx` |
| API promoción | `backend/app.py` → `/api/codes/candidates/promote` |
| Modos epistémicos | `app/settings.py` → `EpistemicMode` |
| Prompts | `app/prompts/` → `loader.py` |

### Documentación Relacionada

- `docs/02-metodologia/guia_modos_epistemicos.md` - Guía detallada de modos
- `docs/02-metodologia/guia_graphrag_discovery.md` - Uso de Discovery
- `docs/05-troubleshooting/brechas_tecnicas.md` - Issues conocidos
- `CLAUDE.md` - Guía de desarrollo

---

*Documento actualizado: 23 de Enero de 2026*  
*Sistema: APP_Jupter v3.0*
