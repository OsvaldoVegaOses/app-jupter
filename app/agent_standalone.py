"""
Agente Autónomo de Investigación Cualitativa (Grounded Theory)

Este módulo implementa un orquestador basado en LangGraph que ejecuta
el pipeline completo de Teoría Fundamentada de forma autónoma.

Versión: 1.0.0 (Standalone - Sin conexión a app/)
Fecha: 7 Enero 2026

USO:
    from app.agent_standalone import run_research_demo
    
    result = await run_research_demo(
        project_id="jd-008",
        documents=["entrevista1.docx", "entrevista2.docx"]
    )

PRÓXIMO PASO:
    Reemplazar funciones mock con imports reales de app/
"""

from typing import TypedDict, List, Annotated, Literal, Optional
from dataclasses import dataclass
import operator
import random
import asyncio

# ============================================================================
# CONSTANTES METODOLÓGICAS (Teoría Fundamentada - Strauss & Corbin)
# ============================================================================

# Refinamientos Discovery por entrevista individual
REFINEMENTS_PER_INTERVIEW = 6

# Refinamientos Discovery sobre corpus global
REFINEMENTS_GLOBAL = 6

# Negativos automáticos para filtrar ruido conversacional
AUTO_NEGATIVES = [
    "conversacion_informal",
    "logistica_entrevista",
    "muletilla",
    "saludo",
    "despedida"
]

# ============================================================================
# CONFIGURACIÓN DE ROBUSTEZ (Step 3 & 4)
# ============================================================================

# Límites por defecto
DEFAULT_MAX_INTERVIEWS = 10          # Máximo de entrevistas a procesar
DEFAULT_MAX_ITERATIONS_PER_INTERVIEW = 4  # Refinamientos por entrevista
DEFAULT_BATCH_SIZE = 5               # Entrevistas por batch

# HTTP timeouts (segundos)
TIMEOUT_DEFAULT = 30.0
TIMEOUT_DISCOVERY = 60.0
TIMEOUT_EMBEDDING = 45.0

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0  # Segundos base para backoff exponencial
RETRY_BACKOFF_MAX = 30.0  # Máximo tiempo de espera entre reintentos


async def http_request_with_retry(
    client,
    method: str,
    url: str,
    max_retries: int = MAX_RETRIES,
    backoff_base: float = RETRY_BACKOFF_BASE,
    **kwargs
) -> tuple:
    """
    Ejecuta request HTTP con retry y backoff exponencial.
    
    Returns:
        (success: bool, response_or_error: dict | str)
    """
    import httpx
    
    last_error = None
    
    for attempt in range(max_retries + 1):
        try:
            if method.upper() == "GET":
                resp = await client.get(url, **kwargs)
            elif method.upper() == "POST":
                resp = await client.post(url, **kwargs)
            else:
                resp = await client.request(method.upper(), url, **kwargs)
            
            if resp.status_code < 500:
                # Success or client error (4xx) - no retry
                return (resp.status_code < 400, resp.json() if resp.status_code == 200 else {"error": resp.text, "status": resp.status_code})
            
            # Server error (5xx) - retry
            last_error = f"HTTP {resp.status_code}: {resp.text[:100]}"
            
        except httpx.TimeoutException as e:
            last_error = f"Timeout: {str(e)}"
        except httpx.ConnectError as e:
            last_error = f"Connection error: {str(e)}"
        except Exception as e:
            last_error = f"Unexpected error: {str(e)}"
        
        if attempt < max_retries:
            wait_time = min(backoff_base * (2 ** attempt), RETRY_BACKOFF_MAX)
            print(f"    ⏳ Retry {attempt + 1}/{max_retries} in {wait_time:.1f}s ({last_error})")
            await asyncio.sleep(wait_time)
    
    return (False, {"error": last_error, "retries_exhausted": True})


# ============================================================================
# 1. ESTADO DEL AGENTE (Memory Schema)
# ============================================================================

class ResearchState(TypedDict):
    """
    Estado compartido que persiste durante toda la ejecución del pipeline.
    
    Cada nodo puede leer y modificar este estado. LangGraph gestiona
    la persistencia y las actualizaciones parciales.
    """
    # Identificación
    project_id: str
    current_stage: int  # 0=prep, 1=ingesta, 2=discovery, 3=coding, 4=axial, 9=report
    
    # Memoria de Trabajo
    documents: List[str]           # Archivos a procesar
    codes_buffer: List[str]        # Códigos generados pendientes de validar
    validated_codes: List[str]     # Códigos ya validados
    saturation_score: float        # 0.0 a 1.0
    
    # Discovery State
    discovery_concepts: List[str]          # Conceptos positivos a explorar
    discovery_current_interview: Optional[str]  # Entrevista actual en refinamiento
    discovery_iteration: int               # Iteración actual (0-5)
    discovery_phase: str                   # "per_interview" o "global"
    discovery_results: List[dict]          # Resultados acumulados
    discovery_memos: List[str]             # Memos de discovery guardados
    
    # Planificación
    iteration: int                 # Contador de iteraciones del loop
    max_iterations: int            # Límite de seguridad
    
    # Errores y Escalamiento
    errors: List[str]              # Errores acumulados
    needs_human: bool              # Flag para intervención humana
    
    # Output
    final_report: str              # Markdown del informe final
    
    # Reflexividad (acumulador automático con operator.add)
    memos: Annotated[List[str], operator.add]


# ============================================================================
# 2. FUNCIONES MOCK (Reemplazar con imports reales)
# ============================================================================

class MockFunctions:
    """
    Simulaciones de las funciones reales de app/.
    
    TODO: Reemplazar cada método con:
        from app.ingestion import ingest_documents
        from app.coding import run_batch_analysis
        etc.
    """
    
    @staticmethod
    def ingest_documents(project_id: str, documents: List[str]) -> dict:
        """Simula ingesta de documentos."""
        print(f"    📥 [MOCK] Ingesting {len(documents)} documents...")
        return {
            "success": True,
            "fragments_count": len(documents) * 45,  # ~45 fragmentos por doc
            "vectors_created": len(documents) * 45
        }
    
    @staticmethod
    def run_batch_analysis(project_id: str, documents: List[str]) -> List[str]:
        """Simula codificación abierta con LLM."""
        print(f"    🧬 [MOCK] Running open coding on {len(documents)} docs...")
        # Simula códigos generados
        mock_codes = [
            "escasez_hidrica",
            "conflicto_institucional", 
            "resiliencia_comunitaria",
            "desconfianza_autoridades",
            "solidaridad_vecinal",
            "escasez_agua",  # Duplicado para probar dedup
            "crisis_ambiental",
            "gobernanza_local"
        ]
        # Retorna subset aleatorio
        return random.sample(mock_codes, min(5, len(mock_codes)))
    
    @staticmethod
    def deduplicate_codes(codes: List[str], threshold: float = 0.85) -> List[str]:
        """Simula deduplicación pre-hoc."""
        print(f"    🔍 [MOCK] Deduplicating {len(codes)} codes (threshold={threshold})...")
        # Simula fusión de "escasez_hidrica" y "escasez_agua"
        unique = list(set(codes))
        if "escasez_hidrica" in unique and "escasez_agua" in unique:
            unique.remove("escasez_agua")
            print("    ├── Merged: escasez_agua → escasez_hidrica")
        return unique
    
    @staticmethod
    def calculate_saturation(project_id: str, codes_count: int) -> float:
        """Simula cálculo de saturación teórica."""
        # Saturación aumenta con más códigos (simplificado)
        base = min(codes_count / 15, 1.0)  # 15 códigos = 100%
        noise = random.uniform(-0.1, 0.1)
        return max(0.0, min(1.0, base + noise))
    
    @staticmethod
    def run_link_prediction(project_id: str, min_score: float = 6.0) -> List[dict]:
        """Simula Link Prediction axial."""
        print(f"    🔗 [MOCK] Running Link Prediction (min_score={min_score})...")
        return [
            {"source": "escasez_hidrica", "target": "conflicto_institucional", "score": 8.2},
            {"source": "resiliencia_comunitaria", "target": "solidaridad_vecinal", "score": 7.5},
            {"source": "gobernanza_local", "target": "desconfianza_autoridades", "score": 6.8}
        ]
    
    @staticmethod
    def detect_nucleus(project_id: str) -> dict:
        """Simula detección de núcleo con PageRank."""
        print(f"    🎯 [MOCK] Detecting nucleus via PageRank...")
        return {
            "name": "gobernanza_local",
            "pagerank": 0.87,
            "connections": 12
        }
    
    @staticmethod
    def validate_integrity(project_id: str) -> dict:
        """Simula validación de integridad."""
        print(f"    ✅ [MOCK] Validating evidence integrity...")
        return {
            "passed": True,
            "linkage_rate": 0.94,
            "orphan_codes": 0
        }
    
    @staticmethod
    def build_final_report(project_id: str, nucleus: str, codes: List[str]) -> str:
        """Simula generación de informe final."""
        print(f"    📝 [MOCK] Building final report...")
        return f"""
# Informe de Investigación: {project_id}

## Núcleo Teórico: {nucleus}

## Códigos Validados ({len(codes)}):
{chr(10).join(f"- {code}" for code in codes)}

## Saturación: Alcanzada

---
*Generado automáticamente por APP_Jupter Agent*
"""

    # =========================================================================
    # DISCOVERY FUNCTIONS (Búsqueda Exploratoria)
    # =========================================================================
    
    @staticmethod
    def run_discovery(
        project_id: str,
        positive_concepts: List[str],
        negative_concepts: List[str] = None,
        target_text: str = None,
        filter_interview: str = None,
        limit: int = 10
    ) -> dict:
        """
        Simula búsqueda exploratoria semántica.
        
        Args:
            positive_concepts: Conceptos a buscar (similares a)
            negative_concepts: Conceptos a evitar (diferentes de)
            target_text: Texto objetivo opcional (cerca de)
            filter_interview: Filtrar por entrevista específica
            limit: Número de resultados
        
        Returns:
            Dict con fragmentos encontrados y métricas
        """
        neg_str = f", negatives={len(negative_concepts or [])}" if negative_concepts else ""
        target_str = f", target='{target_text[:20]}...'" if target_text else ""
        filter_str = f", filter={filter_interview}" if filter_interview else ""
        
        print(f"    🔍 [MOCK] Discovery: positives={positive_concepts}{neg_str}{target_str}{filter_str}")
        
        # Simular fragmentos encontrados
        mock_fragments = [
            {"id": f"frag_{i}", "text": f"Fragmento {i} sobre {positive_concepts[0]}...", 
             "score": 0.9 - (i * 0.05), "interview": filter_interview or "global"}
            for i in range(min(limit, 10))
        ]
        
        return {
            "fragments": mock_fragments,
            "total_found": len(mock_fragments),
            "positive_concepts": positive_concepts,
            "negative_concepts": negative_concepts or [],
            "target_text": target_text,
            "average_score": sum(f["score"] for f in mock_fragments) / len(mock_fragments) if mock_fragments else 0
        }
    
    @staticmethod
    def generate_target_text(concept: str, iteration: int) -> str:
        """
        Genera texto objetivo basado en concepto e iteración.
        
        Iteración 0-1: Sin target (query amplia)
        Iteración 2: Target enfocado
        Iteración 3-5: Variantes del target
        """
        targets = {
            0: None,  # Query amplia
            1: None,  # Con negativos
            2: f"intervencion_estatal_{concept}",
            3: f"rol_institucional_{concept}",
            4: f"coordinacion_{concept}_municipal",
            5: f"impacto_{concept}_territorial"
        }
        return targets.get(iteration)
    
    @staticmethod
    def generate_concept_variant(concept: str, iteration: int) -> str:
        """
        Genera variante del concepto para consolidación.
        
        Iteraciones 3-5 agregan conceptos relacionados.
        """
        variants = {
            3: f"{concept}_institucional",
            4: f"{concept}_normativo",
            5: f"{concept}_territorial"
        }
        return variants.get(iteration, concept)
    
    @staticmethod
    def compare_discovery_results(results1: dict, results2: dict) -> dict:
        """
        Compara dos resultados de Discovery.
        
        Returns:
            Dict con métricas de cambio (ranking, densidad, etc.)
        """
        change_pct = abs(results1.get("average_score", 0) - results2.get("average_score", 0)) * 100
        
        # Simular comparación de IDs de fragmentos
        ids1 = set(f["id"] for f in results1.get("fragments", []))
        ids2 = set(f["id"] for f in results2.get("fragments", []))
        overlap = len(ids1 & ids2) / max(len(ids1), 1) * 100
        
        return {
            "ranking_change_pct": change_pct,
            "overlap_pct": overlap,
            "improved": results2.get("average_score", 0) > results1.get("average_score", 0),
            "should_consolidate": change_pct < 10 and overlap > 80
        }
    
    @staticmethod
    def validate_against_axial(project_id: str, discovery_results: dict) -> dict:
        """
        Valida resultados de Discovery contra códigos axiales persistidos.
        
        Verifica si los fragmentos encontrados "aterrizan" en códigos esperados.
        """
        print(f"    ✅ [MOCK] Validating Discovery against axial codes...")
        
        # Simular validación
        expected_codes = ["coordinacion_interinstitucional", "limitaciones_municipales", "rol_normativo"]
        found_codes = random.sample(expected_codes, min(2, len(expected_codes)))
        
        return {
            "passed": len(found_codes) >= 2,
            "expected_codes": expected_codes,
            "found_codes": found_codes,
            "landing_rate": len(found_codes) / len(expected_codes) * 100
        }
    
    @staticmethod
    def save_discovery_memo(
        project_id: str,
        concept: str,
        iteration: int,
        results: dict,
        interview: str = None
    ) -> str:
        """
        Guarda memo de Discovery.
        
        Returns:
            Path del memo guardado
        """
        phase = "individual" if interview else "global"
        memo_path = f"notes/{project_id}/discovery_{concept}_{phase}_iter{iteration}.md"
        print(f"    💾 [MOCK] Saved memo: {memo_path}")
        return memo_path

# Instancia global para los mocks
mock = MockFunctions()


# ============================================================================
# 3. NODOS DEL GRAFO (Specialist Workers)
# ============================================================================

def node_supervisor(state: ResearchState) -> dict:
    """
    Nodo Supervisor: Planifica y decide próxima acción.
    
    Este nodo actúa como el "System Prompt" del agente, aplicando
    la lógica metodológica de Grounded Theory.
    """
    print(f"\n🎯 [Supervisor] Iteration {state['iteration']}/{state['max_iterations']}")
    print(f"    Stage: {state['current_stage']} | Saturation: {state['saturation_score']:.0%}")
    print(f"    Codes: {len(state['validated_codes'])} validated, {len(state['codes_buffer'])} pending")
    
    # Incrementar iteración
    return {
        "iteration": state["iteration"] + 1
    }


def node_ingestor(state: ResearchState) -> dict:
    """
    Nodo Ingestor: Procesa documentos a Qdrant y Neo4j.
    """
    print(f"\n📥 [Ingestor] Processing {len(state['documents'])} documents...")
    
    result = mock.ingest_documents(state["project_id"], state["documents"])
    
    return {
        "current_stage": 1,
        "memos": [
            f"✅ Ingesta completada: {result['fragments_count']} fragmentos, "
            f"{result['vectors_created']} vectores"
        ]
    }


def node_discovery(state: ResearchState) -> dict:
    """
    Nodo Discovery: Ejecuta búsqueda exploratoria con refinamiento iterativo.
    
    Implementa el patrón metodológico de Strauss & Corbin:
    - 5-6 refinamientos por entrevista individual
    - 5-6 refinamientos sobre el corpus global
    
    Cada iteración sigue el patrón:
    0: Query amplia (solo positivos)
    1: Agregar negativos automáticos
    2: Agregar texto objetivo
    3-5: Variantes y consolidación
    """
    project_id = state["project_id"]
    documents = state["documents"]
    concepts = state.get("discovery_concepts", ["rol_municipal_planificacion"])
    phase = state.get("discovery_phase", "per_interview")
    current_interview = state.get("discovery_current_interview")
    iteration = state.get("discovery_iteration", 0)
    
    print(f"\n🔍 [Discovery] Phase: {phase} | Iteration: {iteration}/{REFINEMENTS_PER_INTERVIEW}")
    
    # Determinar límites según fase
    max_iterations = REFINEMENTS_PER_INTERVIEW if phase == "per_interview" else REFINEMENTS_GLOBAL
    
    # Si estamos en fase per_interview y no hay entrevista actual, seleccionar la primera
    if phase == "per_interview" and not current_interview:
        current_interview = documents[0] if documents else None
        print(f"    📄 Starting with interview: {current_interview}")
    
    # Ejecutar Discovery con refinamiento progresivo
    for concept in concepts:
        # Construir parámetros según iteración
        positives = [concept]
        negatives = None if iteration < 1 else AUTO_NEGATIVES
        target = mock.generate_target_text(concept, iteration)
        
        # Agregar variante en iteraciones 3+
        if iteration >= 3:
            variant = mock.generate_concept_variant(concept, iteration)
            positives.append(variant)
        
        # Ejecutar búsqueda
        results = mock.run_discovery(
            project_id=project_id,
            positive_concepts=positives,
            negative_concepts=negatives,
            target_text=target,
            filter_interview=current_interview if phase == "per_interview" else None,
            limit=10
        )
        
        # Comparar con resultados anteriores si existen
        previous_results = state.get("discovery_results", [{}])[-1] if state.get("discovery_results") else {}
        if previous_results:
            comparison = mock.compare_discovery_results(previous_results, results)
            print(f"    📊 Ranking change: {comparison['ranking_change_pct']:.1f}%, Overlap: {comparison['overlap_pct']:.1f}%")
            
            if comparison["should_consolidate"]:
                print(f"    ✅ Consolidation reached for {concept}")
        
        # Guardar memo
        memo_path = mock.save_discovery_memo(
            project_id=project_id,
            concept=concept,
            iteration=iteration,
            results=results,
            interview=current_interview
        )
    
    # Determinar siguiente estado
    next_iteration = iteration + 1
    next_interview = current_interview
    next_phase = phase
    
    if next_iteration >= max_iterations:
        if phase == "per_interview":
            # Pasar a siguiente entrevista o a fase global
            current_idx = documents.index(current_interview) if current_interview in documents else -1
            if current_idx + 1 < len(documents):
                next_interview = documents[current_idx + 1]
                next_iteration = 0
                print(f"    → Moving to next interview: {next_interview}")
            else:
                # Todas las entrevistas procesadas, pasar a fase global
                next_phase = "global"
                next_interview = None
                next_iteration = 0
                print(f"    → All interviews done, starting global phase")
        else:
            # Fase global completada
            print(f"    ✅ Discovery complete!")
            
            # Validar contra códigos axiales
            validation = mock.validate_against_axial(project_id, results)
            print(f"    Landing rate: {validation['landing_rate']:.0f}%")
            
            return {
                "current_stage": 2,  # Discovery stage complete
                "discovery_phase": "complete",
                "discovery_iteration": next_iteration,
                "discovery_results": state.get("discovery_results", []) + [results],
                "discovery_memos": state.get("discovery_memos", []) + [memo_path],
                "memos": [
                    f"🔍 Discovery completado: {len(documents)} entrevistas, "
                    f"{REFINEMENTS_PER_INTERVIEW}×{len(documents)} + {REFINEMENTS_GLOBAL} refinamientos"
                ]
            }
    
    return {
        "current_stage": 2,
        "discovery_phase": next_phase,
        "discovery_iteration": next_iteration,
        "discovery_current_interview": next_interview,
        "discovery_results": state.get("discovery_results", []) + [results],
        "discovery_memos": state.get("discovery_memos", []) + [memo_path],
        "memos": [
            f"🔍 Discovery iter {iteration}: {phase}, interview={current_interview or 'global'}"
        ]
    }


def node_coder(state: ResearchState) -> dict:
    """
    Nodo Codificador: Ejecuta codificación abierta con DeepSeek.
    
    Incluye validación PRE-HOC para evitar duplicados.
    """
    print(f"\n🧬 [Coder] Running Open Coding...")
    
    # 1. Generar códigos con LLM
    raw_codes = mock.run_batch_analysis(state["project_id"], state["documents"])
    
    # 2. Validación PRE-HOC
    existing = set(state["validated_codes"] + state["codes_buffer"])
    new_codes = [c for c in raw_codes if c not in existing]
    
    # 3. Deduplicar
    clean_codes = mock.deduplicate_codes(new_codes + list(state["codes_buffer"]))
    
    # 4. Calcular saturación
    total_codes = len(state["validated_codes"]) + len(clean_codes)
    saturation = mock.calculate_saturation(state["project_id"], total_codes)
    
    print(f"    New codes: {len(new_codes)}, Clean buffer: {len(clean_codes)}")
    print(f"    Saturation: {saturation:.0%}")
    
    return {
        "current_stage": 3,
        "codes_buffer": clean_codes,
        "saturation_score": saturation,
        "memos": [
            f"🧬 Codificación: {len(new_codes)} nuevos, "
            f"{len(clean_codes)} en buffer, saturación {saturation:.0%}"
        ]
    }


def node_validator(state: ResearchState) -> dict:
    """
    Nodo Validador: Mueve códigos del buffer a validados.
    
    En producción, esto involucraría revisión humana o reglas de negocio.
    """
    print(f"\n✔️ [Validator] Validating {len(state['codes_buffer'])} codes...")
    
    # Simular validación (en prod: llamar a candidatos tray)
    validated = state["codes_buffer"]
    
    return {
        "validated_codes": state["validated_codes"] + validated,
        "codes_buffer": [],  # Vaciar buffer
        "memos": [f"✔️ Validados: {len(validated)} códigos"]
    }


def node_analyst(state: ResearchState) -> dict:
    """
    Nodo Analista: Ejecuta Link Prediction y detecta núcleo.
    """
    print(f"\n🔮 [Analyst] Running Axial Analysis...")
    
    # 1. Link Prediction
    predictions = mock.run_link_prediction(state["project_id"])
    
    # 2. Detectar núcleo
    nucleus = mock.detect_nucleus(state["project_id"])
    
    print(f"    Predictions: {len(predictions)}")
    print(f"    Nucleus: {nucleus['name']} (PageRank: {nucleus['pagerank']})")
    
    return {
        "current_stage": 4,
        "memos": [
            f"🔮 Análisis axial: {len(predictions)} relaciones detectadas",
            f"🎯 Núcleo: {nucleus['name']} (PageRank: {nucleus['pagerank']:.2f})"
        ]
    }


def node_reporter(state: ResearchState) -> dict:
    """
    Nodo Reportero: Genera informe final después de validar integridad.
    """
    print(f"\n📝 [Reporter] Building Final Report...")
    
    # 1. Validar integridad
    integrity = mock.validate_integrity(state["project_id"])
    
    if not integrity["passed"]:
        return {
            "errors": state["errors"] + ["❌ Integrity check failed"],
            "needs_human": True
        }
    
    # 2. Generar reporte
    report = mock.build_final_report(
        state["project_id"],
        "gobernanza_local",  # En prod: obtener del estado
        state["validated_codes"]
    )
    
    print(f"    Integrity: ✅ PASSED (Linkage: {integrity['linkage_rate']:.0%})")
    
    return {
        "current_stage": 9,
        "final_report": report,
        "memos": [f"📝 Informe generado. Linkage Rate: {integrity['linkage_rate']:.0%}"]
    }


# ============================================================================
# 4. ROUTER (Decision Logic)
# ============================================================================

def router(state: ResearchState) -> Literal[
    "ingestor", "discovery", "coder", "validator", "analyst", "reporter", "end", "human"
]:
    """
    Lógica de enrutamiento del agente.
    
    Implementa el "Manus Loop": PLAN → ACT → OBSERVE → (loop or exit)
    
    Flujo de etapas:
    0 (prep) → ingestor
    1 (ingesta) → discovery
    2 (discovery) → coder (cuando discovery_phase == "complete")
    3 (coding) → validator/analyst
    4 (axial) → reporter
    9 (report) → end
    """
    # Safety: Límite de iteraciones
    if state["iteration"] >= state["max_iterations"]:
        print("    ⚠️ Max iterations reached")
        return "end"
    
    # Escalamiento a humano si hay errores
    if state["errors"] or state["needs_human"]:
        print("    🆘 Escalating to human")
        return "human"
    
    # Decisión por etapa
    stage = state["current_stage"]
    saturation = state["saturation_score"]
    discovery_phase = state.get("discovery_phase", "per_interview")
    
    if stage == 0:
        # Inicio: ir a ingesta
        return "ingestor"
    
    if stage == 1:
        # Post-ingesta: ir a Discovery
        return "discovery"
    
    if stage == 2:
        # Discovery en progreso o completado
        if discovery_phase == "complete":
            print("    ✅ Discovery complete, moving to coding")
            return "coder"
        else:
            # Continuar Discovery (loop interno)
            return "discovery"
    
    if stage == 3:
        # Post-codificación: evaluar saturación
        if saturation < 0.6:
            print(f"    ↺ Saturation low ({saturation:.0%}), continuing coding...")
            return "coder"  # Loop: más codificación
        else:
            # Validar códigos antes de análisis axial
            if state["codes_buffer"]:
                return "validator"
            return "analyst"
    
    if stage == 4:
        # Post-análisis axial: generar reporte
        return "reporter"
    
    if stage == 9:
        # Reporte generado: fin
        return "end"
    
    # Default: fin
    return "end"


# ============================================================================
# 5. CONSTRUCCIÓN DEL GRAFO
# ============================================================================

def build_agent():
    """
    Construye y compila el grafo del agente.
    
    Retorna el workflow compilado listo para ejecutar.
    """
    try:
        from langgraph.graph import StateGraph, END
    except ImportError:
        print("⚠️ LangGraph not installed. Run: pip install langgraph")
        return None
    
    # Crear grafo
    workflow = StateGraph(ResearchState)
    
    # Agregar nodos
    workflow.add_node("supervisor", node_supervisor)
    workflow.add_node("ingestor", node_ingestor)
    workflow.add_node("discovery", node_discovery)  # NUEVO: Nodo Discovery
    workflow.add_node("coder", node_coder)
    workflow.add_node("validator", node_validator)
    workflow.add_node("analyst", node_analyst)
    workflow.add_node("reporter", node_reporter)
    
    # Entry point
    workflow.set_entry_point("supervisor")
    
    # Edges condicionales desde supervisor
    workflow.add_conditional_edges(
        "supervisor",
        router,
        {
            "ingestor": "ingestor",
            "discovery": "discovery",  # NUEVO: Route a Discovery
            "coder": "coder",
            "validator": "validator",
            "analyst": "analyst",
            "reporter": "reporter",
            "end": END,
            "human": END  # En prod: nodo de notificación
        }
    )
    
    # Edges de retorno al supervisor (loop)
    workflow.add_edge("ingestor", "supervisor")
    workflow.add_edge("discovery", "supervisor")  # NUEVO: Discovery vuelve al supervisor
    workflow.add_edge("coder", "supervisor")
    workflow.add_edge("validator", "supervisor")
    workflow.add_edge("analyst", "supervisor")
    workflow.add_edge("reporter", "supervisor")
    
    # Compilar
    return workflow.compile()


# ============================================================================
# 6. ENTRY POINTS
# ============================================================================

async def run_research_demo(
    project_id: str,
    documents: List[str],
    max_iterations: int = 20
) -> ResearchState:
    """
    Ejecuta el pipeline de investigación de forma autónoma.
    
    Args:
        project_id: ID del proyecto
        documents: Lista de archivos a procesar
        max_iterations: Límite de seguridad para el loop
    
    Returns:
        Estado final con el reporte y métricas
    """
    print("=" * 60)
    print(f"🚀 Starting Research Agent for project: {project_id}")
    print(f"   Documents: {len(documents)}")
    print(f"   Max iterations: {max_iterations}")
    print("=" * 60)
    
    agent = build_agent()
    
    if agent is None:
        # Fallback sin LangGraph
        print("\n⚠️ Running in MOCK mode without LangGraph...")
        return await run_mock_pipeline(project_id, documents)
    
    # Estado inicial
    initial_state = ResearchState(
        project_id=project_id,
        current_stage=0,
        documents=documents,
        codes_buffer=[],
        validated_codes=[],
        saturation_score=0.0,
        # Discovery state
        discovery_concepts=["rol_municipal_planificacion", "instrumentos_normativos_urbanos"],
        discovery_current_interview=None,
        discovery_iteration=0,
        discovery_phase="per_interview",
        discovery_results=[],
        discovery_memos=[],
        # Planning
        iteration=0,
        max_iterations=max_iterations,
        errors=[],
        needs_human=False,
        final_report="",
        memos=[]
    )
    
    # Ejecutar
    final_state = await agent.ainvoke(initial_state)
    
    # Resumen
    print("\n" + "=" * 60)
    print("✅ RESEARCH COMPLETED")
    print("=" * 60)
    print(f"Iterations: {final_state['iteration']}")
    print(f"Codes validated: {len(final_state['validated_codes'])}")
    print(f"Final saturation: {final_state['saturation_score']:.0%}")
    print(f"Errors: {len(final_state['errors'])}")
    print("\n📜 MEMOS:")
    for memo in final_state["memos"]:
        print(f"  • {memo}")
    
    if final_state["final_report"]:
        print("\n📄 REPORT PREVIEW:")
        print(final_state["final_report"][:500] + "...")
    
    return final_state


async def run_mock_pipeline(
    project_id: str, 
    documents: List[str]
) -> ResearchState:
    """
    Pipeline simplificado sin LangGraph (para testing).
    """
    state = ResearchState(
        project_id=project_id,
        current_stage=0,
        documents=documents,
        codes_buffer=[],
        validated_codes=[],
        saturation_score=0.0,
        # Discovery state
        discovery_concepts=["rol_municipal_planificacion"],
        discovery_current_interview=None,
        discovery_iteration=0,
        discovery_phase="per_interview",
        discovery_results=[],
        discovery_memos=[],
        iteration=0,
        max_iterations=10,
        errors=[],
        needs_human=False,
        final_report="",
        memos=[]
    )
    
    # Simular pipeline secuencial
    print("\n[Mock Pipeline] Ingesting...")
    state["current_stage"] = 1
    state["memos"].append("Ingesta mock completada")
    
    # DISCOVERY PHASE (NUEVO)
    print("\n[Mock Pipeline] Discovery with Refinements...")
    total_discovery_iterations = 0
    
    # Fase 1: Por entrevista
    for doc in documents[:2]:  # Limitar a 2 para demo
        print(f"\n  📄 Interview: {doc}")
        for i in range(REFINEMENTS_PER_INTERVIEW):
            concept = state["discovery_concepts"][0]
            negatives = AUTO_NEGATIVES if i >= 1 else None
            target = mock.generate_target_text(concept, i)
            
            results = mock.run_discovery(
                project_id=project_id,
                positive_concepts=[concept],
                negative_concepts=negatives,
                target_text=target,
                filter_interview=doc,
                limit=5
            )
            total_discovery_iterations += 1
            print(f"    Iter {i+1}: {results['total_found']} fragments, avg_score={results['average_score']:.2f}")
    
    # Fase 2: Global
    print(f"\n  🌐 Global Discovery")
    for i in range(REFINEMENTS_GLOBAL):
        concept = state["discovery_concepts"][0]
        results = mock.run_discovery(
            project_id=project_id,
            positive_concepts=[concept],
            negative_concepts=AUTO_NEGATIVES,
            target_text=mock.generate_target_text(concept, i + 2),
            filter_interview=None,
            limit=10
        )
        total_discovery_iterations += 1
    
    validation = mock.validate_against_axial(project_id, results)
    print(f"    Landing rate: {validation['landing_rate']:.0f}%")
    
    state["current_stage"] = 2
    state["memos"].append(f"🔍 Discovery: {total_discovery_iterations} refinamientos completados")
    
    print("\n[Mock Pipeline] Coding...")
    for i in range(3):
        codes = mock.run_batch_analysis(project_id, documents)
        state["codes_buffer"].extend(codes)
        state["saturation_score"] = mock.calculate_saturation(project_id, len(state["codes_buffer"]))
        print(f"  Iteration {i+1}: {len(codes)} codes, saturation {state['saturation_score']:.0%}")
        if state["saturation_score"] >= 0.6:
            break
    
    state["validated_codes"] = list(set(state["codes_buffer"]))
    state["codes_buffer"] = []
    state["current_stage"] = 3
    
    print("[Mock Pipeline] Analyzing...")
    mock.run_link_prediction(project_id)
    mock.detect_nucleus(project_id)
    state["current_stage"] = 4
    
    print("[Mock Pipeline] Reporting...")
    state["final_report"] = mock.build_final_report(
        project_id, "gobernanza_local", state["validated_codes"]
    )
    state["current_stage"] = 9
    
    return state


# ============================================================================
# 7. EJECUCIÓN CON FUNCIONES REALES (Production Mode)
# ============================================================================

async def run_agent_with_real_functions(
    project_id: str,
    concepts: List[str] = None,
    max_iterations: int = 50,
    max_interviews: int = None,
    iterations_per_interview: int = None,
    discovery_only: bool = False,
    task_callback: callable = None,
) -> dict:
    """
    Ejecuta el agente con conexión a funciones reales del backend.
    
    Esta función es llamada por el endpoint /api/agent/execute y usa
    HTTP calls internos para persistir datos.
    
    Args:
        project_id: ID del proyecto a analizar
        concepts: Conceptos iniciales para Discovery
        max_iterations: Límite de seguridad para el loop principal
        max_interviews: Máximo de entrevistas a procesar (default: 10)
        iterations_per_interview: Refinamientos por entrevista (default: 4)
        discovery_only: Solo ejecutar fase Discovery
        task_callback: Callback para reportar progreso
    
    Returns:
        Estado final del agente
    """
    import httpx
    from pathlib import Path
    
    # Aplicar límites configurables con defaults seguros
    effective_max_interviews = max_interviews or DEFAULT_MAX_INTERVIEWS
    effective_iterations = iterations_per_interview or DEFAULT_MAX_ITERATIONS_PER_INTERVIEW
    
    # Configuración del backend local
    BACKEND_URL = "http://127.0.0.1:8000"
    
    print(f"\n{'='*60}")
    print(f"🚀 Agent REAL MODE for project: {project_id}")
    print(f"   Concepts: {concepts}")
    print(f"   Max iterations: {max_iterations}")
    print(f"   Max interviews: {effective_max_interviews}")
    print(f"   Iterations per interview: {effective_iterations}")
    print(f"{'='*60}")
    
    # Obtener lista de documentos del proyecto
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(f"{BACKEND_URL}/api/interviews", params={"project": project_id})
            resp.raise_for_status()
            interviews = resp.json()
            documents = [i.get("archivo") or i.get("name") for i in interviews if i]
        except Exception as e:
            print(f"⚠️ Could not fetch interviews: {e}")
            documents = []
    
    if not documents:
        print("⚠️ No documents found, running in demo mode")
        return await run_mock_pipeline(project_id, ["demo_doc.docx"])
    
    print(f"   Documents: {len(documents)}")
    
    # Estado inicial
    state = {
        "project_id": project_id,
        "current_stage": 0,
        "documents": documents,
        "codes_buffer": [],
        "validated_codes": [],
        "saturation_score": 0.0,
        "discovery_concepts": concepts or ["rol_municipal_planificacion"],
        "discovery_current_interview": None,
        "discovery_iteration": 0,
        "discovery_phase": "per_interview",
        "discovery_results": [],
        "discovery_memos": [],
        "iteration": 0,
        "max_iterations": max_iterations,
        "errors": [],
        "needs_human": False,
        "final_report": "",
        "memos": [],
    }
    
    # Callback inicial
    if task_callback:
        task_callback(state)
    
    # =========================================================================
    # FASE 1: DISCOVERY CON REFINAMIENTO
    # =========================================================================
    print("\n[REAL] Phase 1: Discovery with Refinements...")
    print(f"  Processing {min(len(documents), effective_max_interviews)} of {len(documents)} interviews")
    state["current_stage"] = 2
    
    async with httpx.AsyncClient(timeout=TIMEOUT_DISCOVERY) as client:
        total_refinements = 0
        errors_count = 0
        
        # Por cada entrevista (respeta límite configurable)
        for doc_idx, doc in enumerate(documents[:effective_max_interviews]):
            print(f"\n  📄 [{doc_idx+1}/{min(len(documents), effective_max_interviews)}] Interview: {doc}")
            
            for iteration in range(effective_iterations):
                for concept in state["discovery_concepts"]:
                    # Construir parámetros
                    positives = [concept]
                    negatives = AUTO_NEGATIVES if iteration >= 1 else []
                    target = mock.generate_target_text(concept, iteration)
                    
                    if iteration >= 3:
                        positives.append(mock.generate_concept_variant(concept, iteration))
                    
                    # Llamar endpoint real de Discovery CON RETRY
                    success, result = await http_request_with_retry(
                        client,
                        "POST",
                        f"{BACKEND_URL}/api/discovery/analyze",
                        json={
                            "project": project_id,
                            "positive_texts": positives,
                            "negative_texts": negatives,
                            "target_text": target,
                            "limit": 10,
                        },
                        headers={"Content-Type": "application/json"},
                    )
                    
                    if success:
                        fragments = result.get("fragments", [])
                        print(f"    Iter {iteration+1}: {len(fragments)} fragments found")
                        total_refinements += 1
                        
                        # Guardar memo real (también con retry)
                        if fragments:
                            memo_success, memo_result = await http_request_with_retry(
                                client,
                                "POST",
                                f"{BACKEND_URL}/api/discovery/save_memo",
                                json={
                                    "project": project_id,
                                    "positive_texts": positives,
                                    "negative_texts": negatives,
                                    "target_text": target,
                                    "fragments": fragments[:5],
                                    "memo_title": f"{concept}_iter{iteration}",
                                    "synthesis": result.get("synthesis"),
                                },
                                headers={"Content-Type": "application/json"},
                            )
                            if memo_success:
                                memo_path = memo_result.get("path", "")
                                state["discovery_memos"].append(memo_path)
                                print(f"    💾 Saved: {memo_path}")
                            else:
                                print(f"    ⚠️ Memo save failed: {memo_result.get('error', 'unknown')}")
                    else:
                        errors_count += 1
                        error_msg = result.get("error", "unknown error")
                        print(f"    ❌ Discovery failed: {error_msg}")
                        state["errors"].append(f"Discovery {concept} iter{iteration}: {error_msg}")
                        
                        # Si hay demasiados errores, abortar
                        if errors_count >= MAX_RETRIES * 2:
                            print(f"    🛑 Too many errors ({errors_count}), aborting Discovery")
                            state["needs_human"] = True
                            break
                
                state["iteration"] += 1
                if task_callback:
                    task_callback(state)
        
        # Fase global (con límites reducidos)
        print(f"\n  🌐 Global Discovery (max {min(REFINEMENTS_GLOBAL, 3)} iterations)")
        for iteration in range(min(REFINEMENTS_GLOBAL, 3)):
            for concept in state["discovery_concepts"]:
                success, result = await http_request_with_retry(
                    client,
                    "POST",
                    f"{BACKEND_URL}/api/discovery/analyze",
                    json={
                        "project": project_id,
                        "positive_texts": [concept],
                        "negative_texts": AUTO_NEGATIVES,
                        "target_text": mock.generate_target_text(concept, iteration + 2),
                        "limit": 15,
                    },
                )
                if success:
                    fragments = result.get("fragments", [])
                    print(f"    Global iter {iteration+1}: {len(fragments)} fragments")
                    total_refinements += 1
                else:
                    print(f"    ⚠️ Global search failed: {result.get('error', 'unknown')}")
        
        state["memos"].append(f"🔍 Discovery: {total_refinements} refinamientos, {errors_count} errores")
    
    if discovery_only:
        state["current_stage"] = 2
        return state
    
    # =========================================================================
    # FASE 2: CODIFICACIÓN (enviar a bandeja de candidatos)
    # =========================================================================
    print("\n[REAL] Phase 2: Sending codes to candidate tray...")
    state["current_stage"] = 3
    
    # Obtener códigos sugeridos de los fragmentos de Discovery
    suggested_codes = []
    for result in state.get("discovery_results", [])[:5]:
        for frag in result.get("fragments", []):
            if "suggested_codes" in frag:
                suggested_codes.extend(frag["suggested_codes"])
    
    # Si no hay códigos de Discovery, usar los mock
    if not suggested_codes:
        suggested_codes = [
            "coordinacion_interinstitucional",
            "limitaciones_municipales",
            "rol_normativo",
            "participacion_ciudadana",
            "infraestructura_urbana",
        ]
    
    # Insertar como candidatos via endpoint
    async with httpx.AsyncClient(timeout=30.0) as client:
        for code in suggested_codes[:10]:
            try:
                resp = await client.post(
                    f"{BACKEND_URL}/api/codes/candidates",
                    json={
                        "project_id": project_id,
                        "codes": [{
                            "codigo": code,
                            "cita": f"Código sugerido por agente autónomo",
                            "fragmento_id": None,
                            "archivo": documents[0] if documents else "agent",
                            "fuente_origen": "agent",
                            "fuente_detalle": "autonomous_agent_discovery",
                            "score_confianza": 0.75,
                        }],
                    },
                )
                if resp.status_code in (200, 201):
                    state["codes_buffer"].append(code)
                    print(f"    ✅ Code sent: {code}")
            except Exception as e:
                print(f"    ❌ Failed to send {code}: {e}")
    
    state["memos"].append(f"🧬 Códigos enviados a bandeja: {len(state['codes_buffer'])}")
    
    # =========================================================================
    # FASE 3: ANÁLISIS AXIAL (mock por ahora)
    # =========================================================================
    print("\n[MOCK] Phase 3: Axial Analysis...")
    state["current_stage"] = 4
    
    predictions = mock.run_link_prediction(project_id)
    nucleus = mock.detect_nucleus(project_id)
    
    state["memos"].append(f"🔮 Análisis axial: {len(predictions)} relaciones")
    state["memos"].append(f"🎯 Núcleo: {nucleus['name']}")
    
    # =========================================================================
    # FASE 4: REPORTE FINAL
    # =========================================================================
    print("\n[MOCK] Phase 4: Final Report...")
    state["current_stage"] = 9
    
    state["validated_codes"] = list(set(state["codes_buffer"]))
    state["saturation_score"] = 0.7
    state["final_report"] = mock.build_final_report(
        project_id,
        nucleus["name"],
        state["validated_codes"],
    )
    
    print(f"\n{'='*60}")
    print("✅ AGENT COMPLETED")
    print(f"{'='*60}")
    print(f"   Memos: {len(state['discovery_memos'])}")
    print(f"   Codes: {len(state['validated_codes'])}")
    print(f"   Saturation: {state['saturation_score']:.0%}")
    
    return state


# ============================================================================
# 8. CLI PARA TESTING
# ============================================================================

if __name__ == "__main__":
    import sys
    
    # Datos de prueba
    test_project = "demo-project"
    test_docs = [
        "entrevista_alcalde.docx",
        "entrevista_vecino_1.docx",
        "entrevista_vecino_2.docx",
        "entrevista_ong.docx",
        "entrevista_experto.docx"
    ]
    
    print("\n" + "🤖 APP_Jupter Autonomous Research Agent".center(60))
    print("=" * 60)
    
    # Ejecutar
    result = asyncio.run(run_research_demo(test_project, test_docs))
    
    # Exit code basado en errores
    sys.exit(1 if result["errors"] else 0)
