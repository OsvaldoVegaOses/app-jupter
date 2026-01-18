# Flujo de Investigacion y Codificacion: Etapas 0-4

> **Documento consolidado: Metodologia + Implementacion**
> 
> **Fecha de elaboracion:** 24 de Diciembre de 2024
> **Version:** 2.0 (fusionado)
> **Ambito:** APP_Jupter - Analisis Cualitativo con GraphRAG

---

## Indice

1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Diagrama de Flujo General](#diagrama-de-flujo-general)
3. [Etapa 0: Preparacion y Reflexividad](#etapa-0-preparacion-y-reflexividad)
4. [Etapa 1: Transcripcion e Ingesta](#etapa-1-transcripcion-e-ingesta)
5. [Etapa 2: Analisis Descriptivo Inicial](#etapa-2-analisis-descriptivo-inicial)
6. [Etapa 3: Codificacion Abierta](#etapa-3-codificacion-abierta)
7. [Etapa 4: Codificacion Axial](#etapa-4-codificacion-axial)
8. [Implementacion](#implementacion)
9. [Comandos CLI](#comandos-cli)
10. [Estado de Pruebas](#estado-de-pruebas)
11. [Referencias](#referencias)

---

## Resumen Ejecutivo

El sistema implementa **Teoria Fundamentada (Grounded Theory)** con apoyo de LLM:

| Etapa | Nombre | Objetivo |
|-------|--------|----------|
| E0 | Reflexividad | Revision inicial, observaciones |
| E1 | Ingesta | DOCX -> fragmentos -> embeddings -> 3 BD |
| E2 | Descriptivo | Busqueda hibrida, conteos, QA cobertura |
| E3 | Cod. Abierta | LLM genera codigos candidatos con evidencia |
| E4 | Cod. Axial | Categorias y relaciones tipadas (>=2 fragmentos) |

---

## Diagrama de Flujo General

```
                         DOCX/Audio
                             |
                             v
          +------------------+------------------+
          |                                     |
     documents.py                         transcription.py
    (fragmentacion)                         (Whisper)
          |                                     |
          +------------------+------------------+
                             |
                             v
                      ingestion.py
                             |
       +---------------------+---------------------+
       v                     v                     v
   PostgreSQL             Qdrant                Neo4j
(entrevista_fragmentos)  (vectores)         (Entrevista)
       |                     |                     |
       +---------------------+---------------------+
                             |
                             v
                       analysis.py
                      (LLM Analysis)
                             |
       +---------------------+---------------------+
       |                     |                     |
   ETAPA 0-2             ETAPA 3              ETAPA 4
 (observaciones)    (codigos abiertos)    (categorias axiales)
                         |                     |
                         v                     v
              codigo_candidatos          Neo4j Grafo
                (validacion)        (Categoria-[REL]->Codigo)
```

---

## Etapa 0: Preparacion y Reflexividad

### Proposito
Revision inicial y configuracion del analisis. El investigador registra observaciones y posibles sesgos.

### Proceso
1. Sistema detecta incoherencias en transcripcion
2. Genera observaciones preliminares
3. Investigador registra reflexividad en `docs/reflexividad.md`

### Salida JSON
```json
{ "etapa0_observaciones": "Transcripcion coherente, sin errores..." }
```

---

## Etapa 1: Transcripcion e Ingesta

### Proposito
Procesar documentos, fragmentar y generar embeddings para busqueda semantica.

### Proceso
1. Fragmentar DOCX (`documents.load_fragment_records`)
2. Generar IDs (`make_fragment_id`) y hashes
3. Embeddings batch (`embeddings.embed_batch`)
4. Persistir en 3 bases de datos

### Persistencia

| Base | Tabla/Coleccion | Datos |
|------|-----------------|-------|
| PostgreSQL | `entrevista_fragmentos` | texto, speaker, metadata |
| Qdrant | `fragments` | vectores + payload canonico |
| Neo4j | `Entrevista`, `Fragmento` | nodos con `project_id` |

### Salida JSON
```json
{ "etapa1_resumen": "Entrevista de 45 min con dirigente vecinal..." }
```

---

## Etapa 2: Analisis Descriptivo Inicial

### Proposito
Generar primeras impresiones y validar cobertura antes de codificar.

### Proceso
1. Busqueda hibrida: `semantic_search` (Qdrant vector + BM25 PG)
2. Conteos grafo: `graph_counts` (Neo4j) por entrevista/speaker
3. Muestreo: `sample_postgres` para QA rapida

### Salida JSON
```json
{
  "etapa2_descriptivo": {
    "impresiones": "Entrevista rica en temas de participacion...",
    "lista_codigos_iniciales": ["participacion", "liderazgo", "recursos"]
  }
}
```

---

## Etapa 3: Codificacion Abierta

### Proposito
Asignar codigos emergentes a fragmentos con citas literales.

### Modelo Hibrido

```
LLM genera codigos --> codigo_candidatos (pending)
                              |
                       Validacion UI
                              |
                    +----+----+----+
                    v    v    v    v
               aprobar rechazar editar fusionar
                    |
                    v
         analisis_codigos_abiertos + Neo4j
```

### Proceso Tecnico
1. `analyze_interview_text`: Prompt con fragmentos `[IDX:n]` + contexto GraphRAG
2. `call_llm_chat_json`: LLM -> JSON robusto
3. `persist_analysis`: Valida `fragmento_idx`, inserta candidatos

### Tipos de Relacion

| Tipo | Significado |
|------|-------------|
| `partede` | Agrupacion jerarquica (default) |
| `causa` | A origina B |
| `condicion` | A depende de B |
| `consecuencia` | A resulta en B |

### Salida JSON
```json
{
  "etapa3_matriz_abierta": [
    { "codigo": "participacion", "cita": "La comunidad se organizo...", "fragmento_idx": 5 }
  ]
}
```

---

## Etapa 4: Codificacion Axial

### Proposito
Agrupar codigos en categorias y establecer relaciones con evidencia.

### Proceso
1. `assign_axial_relation`: Valida evidencia (>=2 fragmentos)
2. Persistencia dual: PG (`axial_relationships`) + Neo4j
3. Analisis grafo: GDS o NetworkX (centralidad, comunidades)

### Grafo Resultante
```cypher
(Categoria:Gobernanza)-[:PARTEDE]->(Codigo:liderazgo)
(Codigo:liderazgo)-[:TIENE_CODIGO]->(Fragmento:frag_001)
```

### Salida JSON
```json
{
  "etapa4_axial": [
    {
      "categoria": "Gobernanza",
      "codigos": ["liderazgo", "gestion"],
      "tipo_relacion": "partede",
      "memo": "Notas analiticas..."
    }
  ]
}
```

---

## Implementacion

### Aislamiento por Proyecto

Todas las operaciones filtran por `project_id`:

| Capa | Implementacion |
|------|----------------|
| Qdrant | `Filter(must=[FieldCondition(key="project_id", ...)])` |
| PostgreSQL | `WHERE project_id = %s` |
| Neo4j | `WHERE n.project_id = $project_id` |

**Helpers centralizados** (`app/isolation.py`):
```python
from app.isolation import qdrant_project_filter, neo4j_project_clause
```

**Warning automatico** si `project_id=None`:
```python
if not project_id:
    _logger.warning("no_project_id - using 'default'")
    project_id = "default"
```

### Guardrails Cypher

| Control | Valor |
|---------|-------|
| Whitelist verbos | MATCH, RETURN, WITH, WHERE, ORDER, LIMIT, OPTIONAL, UNWIND, CALL |
| Blocklist patrones | apoc.*, dbms.*, DELETE, DROP, CREATE, MERGE, SET |
| LIMIT automatico | `CALL { query } LIMIT 500` si no existe |
| Timeout | 30 segundos |
| Fetch size | 100 registros |

**Archivo:** `app/queries.py`

### Parser LLM Robusto

| Control | Valor |
|---------|-------|
| Limite tamano | 32,000 caracteres |
| Retries | 3 intentos |
| Schema requerido | `etapa3_matriz_abierta` |
| Logging | Errores truncados |

**Archivo:** `app/analysis.py`

### Conexiones Hardened

| Base | Configuracion |
|------|---------------|
| Neo4j | pool=50, retry=30s, timeout=30s |
| PostgreSQL | sslmode=prefer, statement_timeout=30s |
| Qdrant | Close con gRPC channel |

**Archivo:** `app/clients.py`

### Algoritmos de Grafo

- **GDS disponible:** `gds.louvain`, `gds.pageRank`, `gds.betweenness`
- **Fallback NetworkX:** Comunidades Louvain, centralidad, betweenness

**Archivo:** `app/axial.py`

---

## Comandos CLI

### Ingesta (E1)
```powershell
python main.py ingest "entrevista.docx" --project mi_proyecto
```

### Busqueda/QA (E2)
```powershell
python main.py search "participacion comunitaria" --project mi_proyecto
python main.py counts --project mi_proyecto
```

### Analisis LLM (E0-E4)
```powershell
python main.py analyze "entrevista.docx" --project mi_proyecto
```

### Codificacion Manual (E3)
```powershell
python main.py coding assign \
    --fragment-id <uuid> \
    --codigo "participacion" \
    --cita "Cita literal..."
```

### Axial Manual (E4)
```powershell
python main.py axial relate \
    --categoria "Gobernanza" \
    --codigo "liderazgo" \
    --tipo causa \
    --evidencia <id1> <id2>
```

### Algoritmos Grafo
```powershell
python main.py axial gds --algorithm pagerank --project mi_proyecto
```

---

## Estado de Pruebas

### Sprint 4 - Security Hardening

| Test | Archivo | Resultado |
|------|---------|-----------|
| Aislamiento PostgreSQL | `tests/test_project_isolation.py` | PASS |
| Aislamiento Qdrant | `tests/test_project_isolation.py` | PASS |
| Aislamiento Neo4j | `tests/test_project_isolation.py` | PASS |
| Parser JSON retries | `tests/test_json_parsing.py` | PASS |
| Parser JSON truncamiento | `tests/test_json_parsing.py` | PASS |
| Parser JSON schema | `tests/test_json_parsing.py` | PASS |

### Ejecutar Tests
```powershell
python tests/test_project_isolation.py  # Requiere Docker
python tests/test_json_parsing.py       # Sin dependencias externas
```

---

## Referencias

### Archivos de Codigo

| Etapa | Archivos |
|-------|----------|
| E1 | `ingestion.py`, `documents.py`, `embeddings.py` |
| E2 | `queries.py` |
| E3 | `analysis.py`, `coding.py` |
| E4 | `axial.py`, `neo4j_block.py` |
| Aislamiento | `isolation.py` |
| Conexiones | `clients.py` |

### Bibliografia
- Strauss, A. & Corbin, J. (1990). *Basics of Qualitative Research*
- Charmaz, K. (2006). *Constructing Grounded Theory*

### Documentacion Relacionada
- `docs/02-metodologia/manual_etapas.md`: Manual completo E3-E9
- `docs/04-arquitectura/seguridad_sprint4.md`: Detalles de seguridad
- `docs/fundamentos_teoria/`: Marco teorico

---

*Documento fusionado: 24 de Diciembre de 2024*
*Sistema: APP_Jupter v1.0 - Sprint 4*
