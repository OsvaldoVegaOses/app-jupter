# Agente Autónomo de Investigación Cualitativa

> **Sprint 29 - En Desarrollo**  
> Sistema de orquestación autónoma para ejecutar el pipeline completo de Teoría Fundamentada

---

## Introducción

El Agente Autónomo es un sistema basado en **LangGraph** que ejecuta el pipeline de Grounded Theory de forma independiente, desde la ingesta hasta la generación del informe final.

**Nota de diseño (Enero 2026):** Discovery no es solo un módulo; es el **modelo de referencia** para el resto del producto. La UX de Codificación Abierta (E3) debe replicar el patrón Discovery (recuperación → síntesis → candidatos con evidencia → validación), con roles claros para PostgreSQL/Qdrant y “luego Neo4j” como capa de estructura explicable. Ver `contrato_epistemico_y_ux.md`.

### Inspiración

| Startup | Concepto Adoptado |
|---------|-------------------|
| **Hebbia** | Matrix UI para codificación masiva |
| **Devin** | Panel de observabilidad (ver pensar a la IA) |
| **Elicit** | Linkage estricto a citas originales |
| **LangGraph** | Orquestación con grafos de estado |

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                    RESEARCH AGENT                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐            │
│  │Supervisor│────▶│ Ingestor │────▶│Discovery │────┐       │
│  └──────────┘     └──────────┘     └──────────┘    │       │
│       │                                  │    │       │
│       │           ┌──────────┐           │    ▼       │
│       │           │ Reporter │◀────┬───────┌──────────┐ │
│       │           └──────────┘     │       │  Coder   │ │
│       │                ▲           └───────┴──────────┘ │
│       │                │                             │
│       │           ┌──────────┐                       │
│       │           │ Analyst  │◀────────┐              │
│       │           └──────────┘        │              │
│       │                │           ┌──────────┐    │
│       │                └───────────┤Validator │    │
│       │                            └──────────┘    │
│       └────────────────── State Graph Loop ─────────┘
└─────────────────────────────────────────────────────────────┘
```

---

## Componentes

### 1. Estado Compartido (`ResearchState`)

```python
class ResearchState(TypedDict):
    project_id: str
    current_stage: int          # 0-9
    documents: List[str]        # Archivos a procesar
    codes_buffer: List[str]     # Códigos pendientes
    validated_codes: List[str]  # Códigos validados
    saturation_score: float     # 0.0 a 1.0
    final_report: str           # Output final
    memos: Annotated[List[str], operator.add]  # Reflexividad
```

### 2. Nodos Especialistas

| Nodo | Responsabilidad |
|------|-----------------|
| **Supervisor** | Planifica y decide próxima acción |
| **Ingestor** | Procesa docs a Qdrant + Neo4j |
| **Discovery** | **🆕 Búsqueda exploratoria con refinamiento** |
| **Coder** | Codificación abierta con LLM |
| **Validator** | Mueve códigos a validados |
| **Analyst** | Link Prediction + PageRank |
| **Reporter** | Genera informe final |

### 3. Router

```python
def router(state) -> str:
    if state['errors']:
        return "human_help"
    if state['current_stage'] == 1:
        return "discovery"  # Post-ingesta → Discovery
    if state['current_stage'] == 2:
        if state['discovery_phase'] == "complete":
            return "coder"  # Discovery completo → Coding
        return "discovery"  # Loop interno de Discovery
    if state['saturation_score'] < 0.6:
        return "coder"  # Loop
    if state['current_stage'] == 3:
        return "analyst"
    if state['current_stage'] == 4:
        return "reporter"
    return "end"
```

### 4. 🆕 Discovery con Refinamiento Iterativo

El nodo Discovery implementa la metodología de **Strauss & Corbin** con refinamiento progresivo:

#### Constantes Metodológicas
```python
REFINEMENTS_PER_INTERVIEW = 6  # Iteraciones por entrevista individual
REFINEMENTS_GLOBAL = 6         # Iteraciones sobre corpus completo
AUTO_NEGATIVES = ["conversacion_informal", "logistica_entrevista", "muletilla"]
```

#### Patrón de Refinamiento (por concepto)

| Iteración | Acción | Parámetros |
|-----------|--------|------------|
| 0 | Query amplia | Solo positivos |
| 1 | Filtrar ruido | +Negativos automáticos |
| 2 | Enfocar | +Texto objetivo |
| 3-5 | Variantes y consolidación | +Conceptos relacionados |

#### Fases de Ejecución

```
┌────────────────────────────────────────────────────────────┐
│ FASE 1: PER_INTERVIEW                                      │
│   Para cada entrevista:                                    │
│     6 iteraciones × N conceptos                            │
│     → Guardar memo por iteración                           │
│     → Comparar resultados entre iteraciones                │
│                                                            │
│ FASE 2: GLOBAL                                             │
│   Sobre todo el corpus:                                    │
│     6 iteraciones × N conceptos                            │
│     → Validar contra códigos axiales persistidos           │
│     → Calcular landing rate                                │
└────────────────────────────────────────────────────────────┘
```

#### Criterios de Consolidación
- **Cambio de ranking < 10%** y **Overlap > 80%** → Consolidar concepto
- **Landing rate** contra códigos axiales → Validación metodológica
---

## Archivos

| Archivo | Descripción |
|---------|-------------|
| [agent_standalone.py](file:///c:/Users/osval/Downloads/APP_Jupter/app/agent_standalone.py) | Implementación completa (mock functions) |
| [agent_feasibility_analysis.md](agent_feasibility_analysis.md) | Análisis de viabilidad técnica |
| [contrato_epistemico_y_ux.md](contrato_epistemico_y_ux.md) | Contrato epistémico + requisitos UX/UI (pluralismo metodológico) |
| [criterios_aceptacion_ux_e3_discovery_first.md](criterios_aceptacion_ux_e3_discovery_first.md) | Backlog implementable: criterios de aceptación UX para E3 siguiendo el patrón Discovery-first |
| [backlog_tecnico_e3_discovery_first.md](backlog_tecnico_e3_discovery_first.md) | Issues/tareas técnicas mapeadas a endpoints y componentes (incluye memos+reportes en informes) |
| [algoritmo_bucle_manual_semilla.md](algoritmo_bucle_manual_semilla.md) | Formalización del bucle manual E3 (semilla → sugerencias → código → memo → candidatos) + métricas de calidad |
| [seed_loop_agent_mvp.md](seed_loop_agent_mvp.md) | Guía MVP para ejecutar el bucle semilla como herramienta reproducible (script) |
| [orden_epistemologico_entrevistas_project_sweep.md](orden_epistemologico_entrevistas_project_sweep.md) | Orden defendible de entrevistas para `project-sweep`: ingesta/cronología, máxima variación, casos ricos, y backlog hacia theoretical sampling |
| [spec_order_theoretical_sampling.md](spec_order_theoretical_sampling.md) | Spec exacta para implementar `order=theoretical-sampling`: señales, tablas/queries, umbrales por defecto, scoring function y fallbacks sin backlog |
| [startup_strategy_evaluation.md](startup_strategy_evaluation.md) | Evaluación de estrategias (Hebbia, Devin, etc.) |

---

## Uso

### Modo UI (Discovery + Runner)

En el Frontend coexisten dos modos:

- **Discovery manual**: usa el triplete **Positivos / Negativos / Target** y ejecuta una búsqueda única (botón **Buscar**).
- **Runner automatizado (MVP)**: ejecuta iteraciones del pipeline de Discovery (botón **🚀 Runner**) y muestra el progreso vía el agente.

**Importante (MVP):** el botón **🚀 Runner** toma únicamente los **Conceptos Positivos** como `concepts` y actualmente **ignora Negativos y Target**.

Qué verás al ejecutar **🚀 Runner**:

- **Estado / stage / iteraciones** (polling del status del agente).
- **Errores** (`errors`) si ocurrieron durante la ejecución.
- **Landing rate final** (`final_landing_rate`) como validación contra códigos persistidos (cuando está disponible).

### Modo Demo (Mock)

```bash
python app/agent_standalone.py
```

Output:
```
🤖 APP_Jupter Autonomous Research Agent
[Mock Pipeline] Ingesting...
[Mock Pipeline] Coding...
  Iteration 1: 5 codes, saturation 33%
  Iteration 2: 5 codes, saturation 67%
[Mock Pipeline] Analyzing...
[Mock Pipeline] Reporting...
Exit code: 0
```

### Integración Futura

```python
from app.agent_standalone import run_research_demo

result = await run_research_demo(
    project_id="jd-008",
    documents=["entrevista1.docx", "entrevista2.docx"],
    max_iterations=20
)

print(result["final_report"])
```

---

## Roadmap

### Sprint 29 (Actual)
- [x] Crear esqueleto del agente (mock functions)
- [x] Definir `ResearchState`
- [x] Implementar nodos básicos
- [ ] Instalar LangGraph en entorno Docker
- [ ] Probar con proyecto real

### Sprint 30
- [ ] Conectar nodos a funciones reales de `app/`
- [ ] Añadir Panel de Observabilidad (WebSocket)
- [ ] Implementar Matrix UI (Hebbia-style)

### Sprint 31
- [ ] Integrar DeepSeek R1 para loops baratos
- [ ] Añadir checkpoints/resume
- [ ] Dashboard de métricas del agente

---

## Dependencias

Añadidas a `requirements.txt`:
```
langgraph>=0.2.0
langchain-core>=0.2.0
```

---

## Referencias

- [LangGraph Documentation](https://python.langchain.com/docs/langgraph)
- [Sprint 28: Neo4j Resilience](../03-sprints/sprint28_neo4j_resilience.md)
- [Estrategia Grafos Fallback](../04-arquitectura/estrategia_grafos_fallback.md)
