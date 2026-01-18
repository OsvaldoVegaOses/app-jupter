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
        evidence.append({
            "rank": i,
            "archivo": frag.get("archivo", "desconocido"),
            "fragmento_id": frag.get("fragmento_id", frag.get("id", "")),
            "texto": (frag.get("fragmento", "") or "")[:200],
            "score": round(frag.get("score", 0), 3),
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
    confidence, confidence_reason = calculate_confidence(fragments)
    
    # 4. Construir prompt con contrato de respuesta (Sprint 15 - E3)
    system_prompt = """Eres un asistente de investigación cualitativa riguroso.

REGLAS ESTRICTAS:
1. Responde ÚNICAMENTE basándote en los fragmentos proporcionados.
2. Cita las fuentes usando [1], [2], etc. para cada afirmación importante.
3. Si no hay evidencia suficiente para una afirmación, NO LA HAGAS.
4. Sé conciso: 3-6 oraciones máximo.
5. Si los fragmentos no contienen información relevante, di "No encontré información específica sobre esto en los fragmentos disponibles."

FORMATO DE RESPUESTA:
- Primera parte: Respuesta directa con citas [1], [2]
- Si hay contradicciones entre fuentes, mencionarlas
- Termina con grado de certeza: "Confianza: alta/media/baja" basado en evidencia"""
    
    user_content_parts = [f"PREGUNTA: {query}", ""]
    
    # Agregar contexto del grafo
    if subgraph["context"]:
        user_content_parts.append(subgraph["context"])
        user_content_parts.append("")
    
    # Agregar fragmentos relevantes
    if include_fragments and fragments:
        user_content_parts.append("FRAGMENTOS DE EVIDENCIA:")
        for i, frag in enumerate(fragments, 1):
            text = frag.get("fragmento", "")[:300]
            archivo = frag.get("archivo", "desconocido")
            score = frag.get("score", 0)
            user_content_parts.append(f"\n[{i}] Fuente: {archivo} (relevancia: {score:.2f})")
            user_content_parts.append(f"    \"{text}...\"")
    
    user_content = "\n".join(user_content_parts)
    
    # 5. Llamar al LLM
    try:
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        
        # gpt-5.x models no soportan temperature != 1, no enviar el parámetro
        kwargs["max_completion_tokens"] = 1000

        response = clients.aoai.chat.completions.create(**kwargs)
        answer = response.choices[0].message.content or ""
    except Exception as e:
        _logger.error("graphrag.llm_error", error=str(e))
        answer = f"Error al procesar la consulta: {str(e)}"
    
    # 6. Formatear evidencia estructurada (Sprint 15 - E3)
    evidence = format_evidence_block(fragments)
    
    _logger.info(
        "graphrag.query_complete",
        query=query[:50],
        nodes=len(subgraph.get("nodes") or []),
        answer_len=len(answer or ""),
        confidence=confidence,
        is_grounded=True,
    )
    
    # CONTRATO DE RESPUESTA (Sprint 15 - E3)
    result = {
        "query": query,
        "answer": answer,
        "is_grounded": True,
        "evidence": evidence,
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "context": subgraph["context"],
        "nodes": subgraph["nodes"],
        "relationships": subgraph["relationships"],
        "fragments": fragments,  # Backward compatible
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
