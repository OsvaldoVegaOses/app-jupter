"""
GraphRAG: Retrieval Augmented Generation con Contexto de Grafo.

Este modulo implementa GraphRAG, que combina busqueda semantica con
contexto estructurado del grafo Neo4j para respuestas mas precisas.

Funcionalidades:
    - extract_relevant_subgraph(): Extrae subgrafo relevante a una consulta
    - format_subgraph_for_prompt(): Formatea subgrafo para inyeccion en prompt
    - graphrag_query(): Consulta LLM con contexto de grafo

Flujo:
    1. Usuario hace pregunta
    2. Busqueda semantica en Qdrant para fragmentos relevantes
    3. Extraccion de codigos/categorias relacionados desde Neo4j
    4. Construccion de contexto con relaciones
    5. Inyeccion en prompt del LLM
    6. Respuesta contextualizada

Ejemplo:
    >>> from app.graphrag import graphrag_query
    >>> result = graphrag_query(
    ...     clients, settings,
    ...     query="Que causa la inseguridad en el barrio?",
    ...     project="mi_proyecto"
    ... )
    >>> print(result["answer"])
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import structlog

from .clients import ServiceClients
from .settings import AppSettings
from .queries import semantic_search

_logger = structlog.get_logger()

# =============================================================================
# Configuración de Gates Anti-Alucinaciones
# =============================================================================

# Umbrales configurables (pueden venir de settings/env)
EVIDENCE_MIN_SCORE = 0.5  # Score mínimo del fragmento top-1
EVIDENCE_MIN_FRAGMENTS = 2  # Mínimo de fragmentos requeridos
CONFIDENCE_HIGH_THRESHOLD = 0.7  # Score para confianza "alta"
CONFIDENCE_MEDIUM_THRESHOLD = 0.5  # Score para confianza "media"


def validate_evidence(
    fragments: List[Dict[str, Any]],
    min_score: float = EVIDENCE_MIN_SCORE,
    min_fragments: int = EVIDENCE_MIN_FRAGMENTS,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Valida si hay evidencia suficiente para responder una consulta.
    
    Gate de Evidencia Mínima (Sprint 15 - E1).
    
    Args:
        fragments: Lista de fragmentos con score de relevancia
        min_score: Score mínimo requerido para el fragmento top-1
        min_fragments: Cantidad mínima de fragmentos requeridos
        
    Returns:
        Tuple de (is_valid, rejection_reason, metadata)
    """
    metadata = {
        "fragments_count": len(fragments),
        "top_score": 0.0,
        "scores": [],
    }
    
    if not fragments:
        return False, "No se encontraron fragmentos relevantes en el corpus", metadata
    
    # Extraer scores
    scores = [f.get("score", 0) for f in fragments]
    metadata["scores"] = scores[:5]
    metadata["top_score"] = scores[0] if scores else 0
    
    # Validar score mínimo
    if metadata["top_score"] < min_score:
        return (
            False,
            f"Relevancia insuficiente (score máximo: {metadata['top_score']:.2f}, requerido: {min_score})",
            metadata,
        )
    
    # Validar cantidad mínima
    if len(fragments) < min_fragments:
        return (
            False,
            f"Evidencia limitada (solo {len(fragments)} fragmento(s), requerido: {min_fragments})",
            metadata,
        )
    
    return True, "", metadata


def calculate_confidence(
    fragments: List[Dict[str, Any]],
    high_threshold: float = CONFIDENCE_HIGH_THRESHOLD,
    medium_threshold: float = CONFIDENCE_MEDIUM_THRESHOLD,
) -> Tuple[str, str]:
    """
    Calcula nivel de confianza basado en evidencia disponible.
    
    Returns:
        Tuple de (confidence_level, reason)
    """
    if not fragments:
        return "baja", "Sin fragmentos de evidencia"
    
    scores = [f.get("score", 0) for f in fragments]
    top_score = scores[0] if scores else 0
    high_score_count = sum(1 for s in scores if s >= high_threshold)
    
    if top_score >= high_threshold and high_score_count >= 2:
        return "alta", f"{high_score_count} fragmentos con score ≥{high_threshold}"
    elif top_score >= medium_threshold:
        return "media", f"Top score: {top_score:.2f}"
    else:
        return "baja", f"Score máximo bajo: {top_score:.2f}"


def format_evidence_block(fragments: List[Dict[str, Any]], max_items: int = 5) -> List[Dict[str, Any]]:
    """
    Formatea fragmentos como bloque de evidencia estructurado.
    
    Returns:
        Lista de evidencias con rank, archivo, fragmento_id, texto, score
    """
    evidence = []
    for i, frag in enumerate(fragments[:max_items], 1):
        text = (frag.get("fragmento", "") or "").strip()
        # snippet: 1-2 short sentences (approx first 150 chars)
        snippet = (text[:150] + "...") if len(text) > 150 else text
        evidence.append({
            "rank": i,
            "fragmento_id": frag.get("fragmento_id", frag.get("id", "")),
            "archivo": frag.get("archivo", "desconocido"),
            "doc_ref": frag.get("archivo", "desconocido"),
            "snippet": snippet,
            "texto": text[:400],
            "score": round(frag.get("score", 0), 3),
            # origen de la evidencia cuando esté presente en el fragmento
            "evidence_source": frag.get("source", frag.get("evidence_source", "qdrant_topk")),
            # soporte esperado: OBSERVATION/INTERPRETATION (rellenado por LLM si es necesario)
            "supports": frag.get("supports", None),
            # citation for human-readable cross-reference (e.g. [1])
            "citation": f"[{i}]",
        })
    return evidence



def extract_relevant_subgraph(
    clients: ServiceClients,
    settings: AppSettings,
    query: str,
    project: Optional[str] = None,
    depth: int = 2,
    max_nodes: int = 20,
    context_node_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Extrae un subgrafo relevante a la consulta desde Neo4j.
    
    Args:
        clients: Clientes de servicios
        settings: Configuracion
        query: Consulta del usuario
        project: ID del proyecto
        depth: Profundidad de navegacion en el grafo
        max_nodes: Maximo de nodos a retornar
        
    Returns:
        Dict con nodos, relaciones y metadatos del subgrafo
    """
    project_id = project or "default"
    
    # 1. Buscar fragmentos relevantes via semantica
    semantic_results = semantic_search(
        clients, settings,
        query=query,
        top_k=5,
        project=project_id,
    )
    
    if not semantic_results:
        _logger.info("graphrag.no_semantic_results", query=query[:50])
        return {"nodes": [], "relationships": [], "context": ""}
    
    # 2. Extraer codigos relacionados a esos fragmentos
    fragment_ids = [r["fragmento_id"] for r in semantic_results if r.get("fragmento_id")]

    # Scope estricto (Vista Actual): limitar evidencia y subgrafo a nodos visibles.
    node_ids: Optional[List[int]] = None
    if context_node_ids:
        cleaned: List[int] = []
        for x in context_node_ids:
            try:
                cleaned.append(int(x))
            except Exception:
                continue
        node_ids = cleaned[:200] if cleaned else None
    
    # 3. Consultar Neo4j para obtener el subgrafo
    # IMPORTANTE: Todos los MATCH filtran por project_id para aislamiento
    # Sprint 20: Eliminada cláusula redundante 'OR f.fragmento_id' que causaba warning
    cypher = """
        MATCH (f:Fragmento)-[:TIENE_CODIGO]->(c:Codigo)
        WHERE f.id IN $fragment_ids
            AND f.project_id = $project_id
            AND c.project_id = $project_id
            AND ($node_ids IS NULL OR id(c) IN $node_ids)
        WITH c
        OPTIONAL MATCH (cat:Categoria {project_id: $project_id})-[r:REL]->(c)
        WITH c, cat, r
        OPTIONAL MATCH (c)-[r2:REL]->(c2:Codigo {project_id: $project_id})
        RETURN DISTINCT 
                c.nombre AS codigo,
                c.score_centralidad AS centralidad,
                c.community_id AS comunidad,
                cat.nombre AS categoria,
                type(r) AS rel_tipo,
                r.tipo AS rel_subtipo,
                c2.nombre AS codigo_relacionado
                LIMIT $max_nodes
                """
    
    nodes = []
    relationships = []
    
    try:
        with clients.neo4j.session(database=settings.neo4j.database) as session:
            if node_ids:
                # Filtrar evidencia: quedarse solo con fragmentos conectados a los nodos visibles.
                res_allowed = session.run(
                    """
                    MATCH (f:Fragmento)-[:TIENE_CODIGO]->(c:Codigo)
                    WHERE f.id IN $fragment_ids
                      AND f.project_id = $project_id
                      AND c.project_id = $project_id
                      AND id(c) IN $node_ids
                    RETURN DISTINCT f.id AS fid
                    """,
                    fragment_ids=fragment_ids,
                    project_id=project_id,
                    node_ids=node_ids,
                )
                allowed = {r.get("fid") for r in res_allowed}
                semantic_results = [r for r in semantic_results if r.get("fragmento_id") in allowed]
                fragment_ids = [r["fragmento_id"] for r in semantic_results if r.get("fragmento_id")]
                if not fragment_ids:
                    _logger.info("graphrag.no_view_scoped_evidence", query=query[:50], project=project_id)
                    return {"nodes": [], "relationships": [], "context": "", "fragments": []}

                result = session.run(
                    cypher,
                    fragment_ids=fragment_ids,
                    max_nodes=max_nodes,
                    project_id=project_id,
                    node_ids=node_ids,
                )
            else:
                result = session.run(
                    cypher,
                    fragment_ids=fragment_ids,
                    max_nodes=max_nodes,
                    project_id=project_id,
                    node_ids=None,
                )
            
            seen_nodes = set()
            for record in result:
                codigo = record.get("codigo")
                categoria = record.get("categoria")
                codigo_rel = record.get("codigo_relacionado")
                
                # Agregar nodos
                if codigo and codigo not in seen_nodes:
                    nodes.append({
                        "id": codigo,
                        "type": "Codigo",
                        "centralidad": record.get("centralidad"),
                        "comunidad": record.get("comunidad"),
                    })
                    seen_nodes.add(codigo)
                
                if categoria and categoria not in seen_nodes:
                    nodes.append({
                        "id": categoria,
                        "type": "Categoria",
                    })
                    seen_nodes.add(categoria)
                
                # Agregar relaciones
                if categoria and codigo:
                    relationships.append({
                        "from": categoria,
                        "to": codigo,
                        "type": record.get("rel_subtipo") or "partede",
                    })
                
                if codigo and codigo_rel:
                    relationships.append({
                        "from": codigo,
                        "to": codigo_rel,
                        "type": "relacionado",
                    })
    except Exception as e:
        _logger.warning("graphrag.neo4j_error", error=str(e))
        return {"nodes": [], "relationships": [], "context": ""}
    
    # 4. Construir contexto textual
    context = format_subgraph_for_prompt(nodes, relationships)
    
    _logger.info(
        "graphrag.subgraph_extracted",
        nodes=len(nodes),
        relationships=len(relationships),
        query=query[:50],
    )
    
    return {
        "nodes": nodes,
        "relationships": relationships,
        "context": context,
        "fragments": semantic_results[:3],  # Top 3 fragmentos
    }


def format_subgraph_for_prompt(
    nodes: List[Dict[str, Any]],
    relationships: List[Dict[str, Any]],
) -> str:
    """
    Formatea el subgrafo como texto para inyectar en el prompt del LLM.
    
    Args:
        nodes: Lista de nodos con id, type, y propiedades
        relationships: Lista de relaciones con from, to, type
        
    Returns:
        Texto formateado para el prompt
    """
    if not nodes:
        return ""
    
    lines = ["CONTEXTO DEL GRAFO DE CONOCIMIENTO:"]
    lines.append("")
    
    # Categorias
    categorias = [n for n in nodes if n.get("type") == "Categoria"]
    if categorias:
        lines.append("Categorias principales:")
        for cat in categorias:
            lines.append(f"  - {cat['id']}")
    
    # Codigos con centralidad
    codigos = [n for n in nodes if n.get("type") == "Codigo"]
    if codigos:
        lines.append("")
        lines.append("Codigos (ordenados por importancia):")
        codigos_sorted = sorted(
            codigos, 
            key=lambda x: x.get("centralidad") or 0, 
            reverse=True
        )
        for cod in codigos_sorted[:10]:
            centralidad = cod.get("centralidad")
            if centralidad:
                lines.append(f"  - {cod['id']} (importancia: {centralidad:.3f})")
            else:
                lines.append(f"  - {cod['id']}")
    
    # Relaciones
    if relationships:
        lines.append("")
        lines.append("Relaciones:")
        seen = set()
        for rel in relationships[:15]:
            key = (rel["from"], rel["to"], rel["type"])
            if key not in seen:
                lines.append(f"  {rel['from']} --[{rel['type']}]--> {rel['to']}")
                seen.add(key)
    
    return "\n".join(lines)


def graphrag_query(
    clients: ServiceClients,
    settings: AppSettings,
    query: str,
    project: Optional[str] = None,
    include_fragments: bool = True,
    llm_model: Optional[str] = None,
    enforce_grounding: bool = True,
    context_node_ids: Optional[List[int]] = None,
    filters_applied: Optional[Dict[str, Any]] = None,
    force_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ejecuta una consulta GraphRAG con gates anti-alucinaciones.
    
    Sprint 15: Incluye validación de evidencia, rechazo seguro y
    formato de respuesta estructurado con evidencias citables.
    
    Args:
        clients: Clientes de servicios
        settings: Configuracion
        query: Pregunta del usuario
        project: ID del proyecto
        include_fragments: Incluir fragmentos en contexto
        llm_model: Modelo LLM a usar (default: gpt-4)
        enforce_grounding: Si True, aplica gates de evidencia (default: True)
        force_mode: Forzar modo 'deep' o 'exploratory' (bypass thresholds)
        
    Returns:
        Dict con answer, evidence, confidence, is_grounded, y metadata
    """
    project_id = project or "default"
    model = llm_model or settings.azure.deployment_chat
    
    _logger.info("graphrag.query_start", query=query[:50], project=project_id)
    
    # 1. Extraer subgrafo relevante
    subgraph = extract_relevant_subgraph(
        clients, settings,
        query=query,
        project=project_id,
        context_node_ids=context_node_ids,
    )
    
    fragments = subgraph.get("fragments", [])
    
    # 2. GATE DE EVIDENCIA MÍNIMA (Sprint 15 - E1)
    if enforce_grounding:
        is_valid, rejection_reason, evidence_meta = validate_evidence(fragments)
        
        if not is_valid:
            _logger.info(
                "graphrag.evidence_gate_rejected",
                query=query[:50],
                reason=rejection_reason,
                fragments_count=evidence_meta["fragments_count"],
                top_score=evidence_meta["top_score"],
            )
            
            # RECHAZO SEGURO (Sprint 15 - E2) - Corregido Sprint 20
            # Retornamos mensaje explicativo en lugar de None para evitar NoneType errors
            rejection_message = (
                f"⚠️ **No encontré evidencia suficiente para responder con rigor.**\n\n"
                f"**Razón:** {rejection_reason}\n\n"
                f"**Sugerencia:** Intente reformular la pregunta con términos más específicos "
                f"que aparezcan en las entrevistas, o verifique que el tema existe en los "
                f"documentos ingresados.\n\n"
                f"*Score de relevancia: {evidence_meta['top_score']:.2f} (mínimo requerido: {EVIDENCE_MIN_SCORE})*"
            )
            
            return {
                "query": query,
                "answer": rejection_message,  # Mensaje explicativo en lugar de None
                "is_grounded": False,
                "rejection": {
                    "reason": rejection_reason,
                    "suggestion": "Intente reformular la pregunta con términos más específicos, "
                                  "o verifique que el tema existe en los documentos ingresados.",
                    "fragments_found": evidence_meta["fragments_count"],
                    "top_score": evidence_meta["top_score"],
                },
                "context": subgraph["context"],
                "nodes": subgraph["nodes"],
                "relationships": subgraph["relationships"],
                "evidence": [],
                "confidence": "ninguna",
                "confidence_reason": rejection_reason,
                "model": model,
            }
    
    # 3. Calcular confianza
    # 3. Calcular confianza y determinar MODO DE ESCANEO
    confidence, confidence_reason = calculate_confidence(fragments)
    
    # Calcular score máximo para decisión de modo
    max_score = max([f.get("score", 0) for f in fragments]) if fragments else 0
    
    # Lógica de Auto-Switch (Smart Fallback)
    # Default: Deep Scan si hay buena señal, sino Exploratory, sino Abstain
    scan_mode = "deep"
    fallback_reason = None
    
    THRESHOLD_DEEP = 0.5
    THRESHOLD_EXPLORATORY = 0.25
    
    if force_mode and force_mode in ["deep", "exploratory"]:
        scan_mode = force_mode
        if force_mode == "deep" and max_score < THRESHOLD_DEEP:
            fallback_reason = f"⚠️ ALERTA: Modo Deep forzado con señal débil ({max_score:.2f}). Riesgo de alucinación."
    else:
        if max_score < THRESHOLD_DEEP:
            if max_score >= THRESHOLD_EXPLORATORY:
                scan_mode = "exploratory"
                fallback_reason = f"Señal insuficiente para Deep Scan (max_score {max_score:.2f} < {THRESHOLD_DEEP}). Cambiando a modo Exploratorio."
                if settings.debug:
                    print(f"[GraphRAG] Auto-switch a Exploratory: {fallback_reason}")
            else:
                scan_mode = "insufficient"
                fallback_reason = f"Señal demasiado baja incluso para exploración ({max_score:.2f} < {THRESHOLD_EXPLORATORY})."
    
    # Si la señal es insuficiente, intentamos generar "Research Feedback" en lugar de fallar silenciosamente
    if scan_mode == "insufficient":
        # System Prompt para el Coach Metodológico
        SYSTEM_RESEARCH_COACH = """Eres un EXPERTO COACH METODOLÓGICO en investigación cualitativa (Grounded Theory).
El usuario intentó buscar evidencia para una pregunta, pero la recuperación vectorial falló (scores muy bajos).
Tu trabajo NO es responder la pregunta, sino DIAGNOSTICAR por qué falló y sugerir ACCIONES INVESTIGATIVAS.

ENTRADA:
- Query: Pregunta exacta del usuario.
- Evidencia Débil: Fragmentos recuperados pero con bajo score (irrelevantes semánticamente).
- Contexto de Grafo: Nodos visibles (si los hay).

OBJETIVO JSON:
Genera un objeto JSON con:
1. "diagnosis": Análisis de la brecha. Ejemplo: "La pregunta usa términos teóricos ('gobernanza') que no aparecen en las entrevistas ('reuniones de vecinos')."
2. "actionable_suggestions": Lista de 3 cosas concretas que el investigador puede hacer. Ejemplo: "Codificar incidentes de toma de decisiones", "Buscar sinónimos locales para 'infraestructura'".
3. "suggested_questions": 2 preguntas alternativas usando lenguaje más cercano a los fragmentos visibles.

OUTPUT FORMATO JSON ÚNICO.
"""
        # Solo ejecutamos el coach si hay ALGO de evidencia (aunque sea mala > 0.15)
        # Si no hay nada de nada, retornamos error simple.
        if fragments:
            user_content_parts = [f"QUERY: {query}", "EVIDENCIA DÉBIL RECUPERADA:"]
            for f in fragments[:5]:
                user_content_parts.append(f"- [{f.get('score',0):.2f}] {f.get('fragmento',' ')[:150]}...")
            
            try:
                coach_response = clients.aoai.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_RESEARCH_COACH},
                        {"role": "user", "content": "\n".join(user_content_parts)}
                    ],
                    temperature=0.3,
                    max_tokens=500,
                    response_format={ "type": "json_object" }
                )
                feedback_json = json.loads(coach_response.choices[0].message.content)
            except Exception as e:
                _logger.error(f"Error generando research feedback: {e}")
                feedback_json = None
        else:
            feedback_json = None

        return {
            "query": query,
            "answer": "⚠️ No se encontró evidencia suficiente para responder con rigor. (Score < 0.25).",
            "mode": "insufficient",
            "relevance_score": max_score,
            "fallback_reason": fallback_reason,
            "evidence": [],
            "graph_summary": "Sin datos suficientes.",
            "confidence": "baja",
            "confidence_reason": fallback_reason,
            "research_feedback": feedback_json, # Nuevo campo
            "recommendations": feedback_json.get("actionable_suggestions", []) if feedback_json else ["Intenta usar términos más específicos del dominio."]
        }

    # SELECCIÓN DE PROMPT SEGÚN MODO
    if scan_mode == "deep":
        # Prompt Deep Scan (Causal/Hipótesis) - El original mejorado
        system_prompt = """Eres un asistente que resume un subgrafo Neo4j y genera evidencia trazable para investigación cualitativa (Teoría Fundamentada).
Responde ÚNICAMENTE con un objeto JSON válido (sin texto adicional, sin markdown). Debes cumplir estrictamente el esquema solicitado.

CONTEXTO Y ENTRADA (no inventes nada que no esté en los datos):
- query: pregunta del usuario.
- project_id: identificador del proyecto.
- view_nodes, graph_metrics, graph_edges, communities_detected, evidence_candidates, filters, max_central.

OBJETIVO (DEEP SCAN):
Generar un resumen breve y verificable del subgrafo, destacando RELACIONES CAUSALES, TENSIONES y COHERENCIA ESTRUCTURAL, soportado por:
(a) nodos centrales listados con métrica y score,
(b) 3 fragmentos textuales (snippet) de ALTA RELEVANCIA,
(c) nota explícita de filtros aplicados.

REGLAS EPISTEMOLÓGICAS:
- OBSERVATION: debe estar sustentada por fragmentos.
- INTERPRETATION: inferencias razonables.
- HYPOTHESIS: proposiciones tentativas sobre causalidad ("A podría influir en B").
- No inventes fragmentos ni snippets.

REGLAS ANTI-PLACEHOLDER:
- Si communities_detected vacío -> communities: [].
- graph_summary describe estructura y causalidad observada.

SALIDA JSON REQUERIDA:
{
  "graph_summary": string,
  "central_nodes": [{"code_id": string, "label": string, "metric_name": "pagerank|degree|betweenness", "score": number}],
  "bridges": [{"code_id": string, "label": string, "metric_name": "betweenness", "score": number, "connects": [string, string]}],
  "communities": [{"community_id": string, "label_hint": string, "top_nodes": [string]}],
  "paths": [{"from": string, "to": string, "path_nodes": [string], "rationale": string}],
  "evidence": [{"fragment_id": string, "doc_id": string, "snippet": string, "score": number, "evidence_source": "qdrant_topk", "supports": "OBSERVATION|INTERPRETATION|HYPOTHESIS"}],
  "filters_applied": object,
  "epistemic_labels": object,
  "confidence": {"level": "alta|media|baja", "reason": string, "evidence_counts": number},
  "questions": [string],
  "recommendations": [string]
}
"""
    else:
        # Prompt Exploratory Scan (Descriptivo/No Causal)
        system_prompt = """Eres un asistente de investigación que realiza un ESCANEO EXPLORATORIO de un subgrafo Neo4j.
La relevancia de la evidencia es BAJA/MEDIA. TU OBJETIVO ES DESCRIBIR, NO EXPLICAR NI INFERIR CAUSALIDAD.

Responde ÚNICAMENTE con un objeto JSON válido.

OBJETIVO (EXPLORATORY SCAN):
Generar un mapa descriptivo de "qué hay" y "qué falta".
- Describir temas visibles sin asumir relaciones fuertes.
- Identificar nodos centrales solo por topología (grado).
- Generar PREGUNTAS SUGERIDAS para profundizar, en lugar de hipótesis.

REGLAS ESTRICTAS (MODO EXPLORATORIO):
1. PROHIBIDO usar lenguaje causal ("provoca", "causa", "se debe a"). Usa lenguaje descriptivo ("aparece junto a", "coexiste con").
2. En `evidence`, etiqueta el soporte como "OBSERVATION" (nunca HYPOTHESIS fuerte).
3. `confidence.level` debe ser "baja" o "media".
4. `graph_summary` debe enfatizar la naturaleza preliminar de los hallazgos.

SALIDA JSON REQUERIDA (Compatible):
{
  "graph_summary": string (descripción tentativa),
  "central_nodes": [{"code_id": string, "label": string, "metric_name": "degree", "score": number}],
  "bridges": [],
  "communities": [],
  "paths": [], 
  "evidence": [{"fragment_id": string, "doc_id": string, "snippet": string, "score": number, "evidence_source": "qdrant_topk", "supports": "OBSERVATION"}],
  "filters_applied": object,
  "epistemic_labels": {"observation": "low_signal", "interpretation": "tentative", "hypothesis": "none"},
  "confidence": {"level": "baja", "reason": string, "evidence_counts": number},
  "questions": [string] (preguntas clave para guiar investigación futura),
  "recommendations": [string] (acciones para mejorar la señal, ej. densificar códigos)
}
"""

    user_content_parts = [f"PREGUNTA: {query}", f"MODO: {scan_mode.upper()} (Relevancia max: {max_score:.2f})", ""]
    
    # Agregar contexto del grafo
    if subgraph["context"]:
        user_content_parts.append(subgraph["context"])
        user_content_parts.append("")
    
    # Agregar datos estructurados para el prompt
    import json as json_module
    
    # view_nodes: nodos del subgrafo con métricas
    view_nodes = []
    for n in (subgraph.get("nodes") or []):
        view_nodes.append({
            "code_id": n.get("id"),
            "label": n.get("id"),
            "type": n.get("type"),
            "pagerank": float(n.get("centralidad") or 0),
            "community": n.get("comunidad"),
        })
    if view_nodes:
        user_content_parts.append("VIEW_NODES (nodos visibles con métricas):")
        user_content_parts.append(json_module.dumps(view_nodes[:20], ensure_ascii=False, indent=None))
        user_content_parts.append("")
    
    # graph_edges: relaciones del subgrafo
    graph_edges = []
    for r in (subgraph.get("relationships") or []):
        graph_edges.append({
            "from": r.get("from"),
            "to": r.get("to"),
            "type": r.get("type"),
        })
    if graph_edges:
        user_content_parts.append("GRAPH_EDGES (relaciones):")
        user_content_parts.append(json_module.dumps(graph_edges[:30], ensure_ascii=False, indent=None))
        user_content_parts.append("")
    
    # communities_detected (solo para deep, o si hay muy buena estructura)
    communities_detected = []
    if scan_mode == "deep":
        comm_map: Dict[str, List[str]] = {}
        for n in view_nodes:
            comm = n.get("community")
            if comm is not None and str(comm) not in ("", "None", "-"):
                comm_key = str(comm)
                if comm_key not in comm_map:
                    comm_map[comm_key] = []
                comm_map[comm_key].append(n.get("code_id"))
        for comm_id, members in comm_map.items():
            communities_detected.append({
                "community_id": comm_id,
                "top_nodes": members[:5],
            })
        if communities_detected:
            user_content_parts.append("COMMUNITIES_DETECTED (comunidades reales):")
            user_content_parts.append(json_module.dumps(communities_detected, ensure_ascii=False, indent=None))
            user_content_parts.append("")
    
    # evidence_candidates: fragmentos con snippets
    if include_fragments and fragments:
        user_content_parts.append("EVIDENCE_CANDIDATES (fragmentos ordenados por score):")
        evidence_candidates = []
        # En exploratory permitimos ver un poco más abajo para dar contexto
        limit_ev = 5 if scan_mode == "deep" else 5
        for i, frag in enumerate(fragments[:limit_ev], 1):
            text = (frag.get("fragmento", "") or "").strip()
            archivo = frag.get("archivo", "desconocido")
            score = frag.get("score", 0)
            frag_id = frag.get("fragmento_id", frag.get("id", ""))
            snippet = (text[:200] + "...") if len(text) > 200 else text
            source = frag.get("source", frag.get("evidence_source", "qdrant_topk"))
            evidence_candidates.append({
                "fragment_id": frag_id,
                "doc_id": archivo,
                "snippet": snippet,
                "score": round(score, 3),
                "evidence_source": source,
            })
        user_content_parts.append(json_module.dumps(evidence_candidates, ensure_ascii=False, indent=2))
        user_content_parts.append("")

    # Agregar filtros aplicados (si vienen de la UI)
    user_content_parts.append("FILTERS:")
    filters_dict = filters_applied if isinstance(filters_applied, dict) else {}
    filters_dict["project_id"] = project_id
    filters_dict.setdefault("scope", "proyecto")
    filters_dict.setdefault("k_qdrant", 5)
    filters_dict.setdefault("include_discovery", False)
    user_content_parts.append(json_module.dumps(filters_dict, ensure_ascii=False, indent=None))
    user_content_parts.append("")
    
    user_content = "\n".join(user_content_parts)
    
    # 5. Llamar al LLM
    import json
    parse_error = None
    llm_raw = ""
    try:
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "max_completion_tokens": 1000
        }

        response = clients.aoai.chat.completions.create(**kwargs)
        llm_raw = response.choices[0].message.content or ""

        # Intentar extraer JSON puro de la respuesta
        json_text = None
        # Buscar primer '{' y último '}' para extraer posible JSON
        start = llm_raw.find('{')
        end = llm_raw.rfind('}')
        if start != -1 and end != -1 and end > start:
            json_text = llm_raw[start:end+1]

        if not json_text:
            raise ValueError("No JSON encontrado en la respuesta del modelo.")

        parsed = json.loads(json_text)
        
        # Inyectar metadatos de modo en la respuesta parseada
        parsed["mode"] = scan_mode
        parsed["relevance_score"] = max_score
        if fallback_reason:
            parsed["fallback_reason"] = fallback_reason
            
    except Exception as e:
        _logger.error("graphrag.llm_error_or_parse", error=str(e))
        parse_error = str(e)
        parsed = None
    
    # 6. Formatear evidencia estructurada (Sprint 15 - E3)
    # Limitamos a 3 citas por defecto para la UI (puede ajustarse)
    evidence = format_evidence_block(fragments, max_items=3)
    
    _logger.info(
        "graphrag.query_complete",
        query=query[:50],
        nodes=len(subgraph.get("nodes") or []),
        answer_len=len(llm_raw or ""),
        confidence=confidence,
        is_grounded=True,
    )
    
    # CONTRATO DE RESPUESTA (Sprint 15 - E3)
    # Construir resultado final basado en JSON parseado del LLM si está disponible
    # Pre-calcualte fallback structured fields from subgraph so UI has deterministic data
    # Central nodes (top by centralidad)
    central_nodes_calc: List[Dict[str, Any]] = []
    try:
        codigo_nodes = [n for n in (subgraph.get("nodes") or []) if n.get("type") == "Codigo"]
        codigo_sorted = sorted(codigo_nodes, key=lambda x: float(x.get("centralidad") or 0), reverse=True)
        for n in codigo_sorted[: min(10, len(codigo_sorted))]:
            central_nodes_calc.append({
                "code_id": n.get("id"),
                "label": n.get("id"),
                "metric": "pagerank",
                "score": float(n.get("centralidad") or 0),
            })
    except Exception:
        central_nodes_calc = []

    # Communities
    communities_calc: List[Dict[str, Any]] = []
    try:
        comm_map: Dict[str, List[Dict[str, Any]]] = {}
        for n in (subgraph.get("nodes") or []):
            comm = n.get("comunidad", "-")
            if comm not in comm_map:
                comm_map[comm] = []
            comm_map[comm].append({"id": n.get("id"), "centralidad": float(n.get("centralidad") or 0)})
        for comm_k, members in comm_map.items():
            top_nodes = [m["id"] for m in sorted(members, key=lambda x: x.get("centralidad", 0), reverse=True)[:5]]
            communities_calc.append({"community_id": comm_k, "label_hint": str(comm_k), "top_nodes": top_nodes})
    except Exception:
        communities_calc = []

    # Bridges (relationships connecting different communities)
    bridges_calc: List[Dict[str, Any]] = []
    try:
        node_comm = {n.get("id"): n.get("comunidad") for n in (subgraph.get("nodes") or [])}
        for rel in (subgraph.get("relationships") or []):
            f = rel.get("from")
            t = rel.get("to")
            if f in node_comm and t in node_comm and node_comm.get(f) != node_comm.get(t):
                bridges_calc.append({
                    "from": f,
                    "to": t,
                    "metric": "community_bridge",
                    "score": 1.0,
                    "connects": [str(node_comm.get(f)), str(node_comm.get(t))],
                })
    except Exception:
        bridges_calc = []

    if parsed and isinstance(parsed, dict):
        # Merge: asegurar campos obligatorios y fallback
        parsed_result = {
            "query": query,
            "graph_summary": parsed.get("graph_summary", ""),
            "central_nodes": parsed.get("central_nodes", central_nodes_calc),
            "bridges": parsed.get("bridges", bridges_calc),
            "communities": parsed.get("communities", communities_calc),
            "paths": parsed.get("paths", []),
            "evidence": parsed.get("evidence", evidence),
            "filters_applied": parsed.get("filters_applied", filters_applied or {}),
            "epistemic_labels": parsed.get("epistemic_labels", {"is_inference": False, "unsupported_claims": []}),
            "confidence": parsed.get("confidence", confidence),
            "confidence_reason": parsed.get("confidence_reason", confidence_reason),
            "context": subgraph.get("context"),
            "nodes": subgraph.get("nodes"),
            "relationships": subgraph.get("relationships"),
            "fragments": fragments,
            "model": model,
        }
        result = parsed_result
    else:
        # Parseo fallido -> rechazo seguro
        rejection_message = (
            "⚠️ No se pudo obtener una respuesta JSON válida del modelo."
            f" Detalle: {parse_error or 'respuesta vacía'}."
        )
        result = {
            "query": query,
            "answer": rejection_message,
            "is_grounded": False,
            "evidence": [],
            "confidence": "baja",
            "confidence_reason": parse_error or "no_parse",
            "context": subgraph.get("context"),
            "nodes": subgraph.get("nodes"),
            "relationships": subgraph.get("relationships"),
            "fragments": fragments,
            "model": model,
        }
    
    # PERSISTIR MÉTRICAS (Sprint 16 - E6) - Async para no bloquear
    try:
        import threading
        from app.graphrag_metrics import GraphRAGMetric, persist_metric
        
        metric = GraphRAGMetric.from_response(project_id, query, result)
        
        def _persist_async(pg_conn, m):
            try:
                persist_metric(pg_conn, m)
            except Exception as e:
                _logger.debug("graphrag.metrics_persist_error", error=str(e))
        
        # Nota: Usamos clients.postgres directamente (conexión compartida)
        # En producción considerar pool separado para métricas
        threading.Thread(
            target=_persist_async,
            args=(clients.postgres, metric),
            daemon=True,
        ).start()
    except Exception as e:
        _logger.debug("graphrag.metrics_error", error=str(e))
    
    return result


def graphrag_chain_of_thought(
    clients: ServiceClients,
    settings: AppSettings,
    query: str,
    project: Optional[str] = None,
    context_node_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Consulta GraphRAG con razonamiento paso a paso (Chain of Thought).
    
    Util para preguntas complejas que requieren inferencia sobre el grafo.
    """
    project_id = project or "default"
    
    # Extraer subgrafo
    subgraph = extract_relevant_subgraph(
        clients, settings,
        query=query,
        project=project_id,
        depth=3,
        max_nodes=30,
        context_node_ids=context_node_ids,
    )
    
    # Prompt con CoT - Explícito para modelos GPT-5/O1 que ocultan razonamiento interno
    system_prompt = """Eres un asistente de investigación cualitativa experto en Teoría Fundamentada.

IMPORTANTE: Tu respuesta DEBE seguir EXACTAMENTE este formato con los 4 pasos visibles en el texto:

## PASO 1: ANÁLISIS DEL GRAFO
[Aquí describes qué nodos, relaciones y fragmentos son relevantes para la pregunta]

## PASO 2: IDENTIFICACIÓN DE RELACIONES CAUSALES
[Aquí identificas conexiones causales entre códigos/categorías]

## PASO 3: SÍNTESIS INTERPRETATIVA
[Aquí elaboras la respuesta basada en evidencia]

## PASO 4: CITAS DE RESPALDO
[Aquí listas los fragmentos [1], [2], etc. que sustentan tu análisis]

## CONCLUSIÓN
[Aquí presentas la respuesta final breve]

NO resumas ni omitas ningún paso. Cada sección debe aparecer en tu respuesta."""


    user_content = f"""PREGUNTA: {query}

{subgraph['context']}

FRAGMENTOS:
""" + "\n".join([
        f"[{i+1}] {f.get('fragmento', '')[:200]}..." 
        for i, f in enumerate(subgraph.get("fragments", []))
    ])
    
    try:
        kwargs = {
            "model": settings.azure.deployment_chat,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        
        # gpt-5.x models no soportan temperature != 1, no enviar el parámetro
        kwargs["max_completion_tokens"] = 1500

        response = clients.aoai.chat.completions.create(**kwargs)
        answer = response.choices[0].message.content or ""
    except Exception as e:
        answer = f"Error: {str(e)}"
    
    return {
        "query": query,
        "answer": answer,
        "reasoning": "chain_of_thought",
        "subgraph": subgraph,
        "nodes": subgraph.get("nodes", []),
        "relationships": subgraph.get("relationships", []),
        "context": subgraph.get("context", ""),
        "fragments": subgraph.get("fragments", []),
    }
