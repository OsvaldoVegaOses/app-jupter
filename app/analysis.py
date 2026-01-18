"""
Análisis cualitativo de entrevistas con apoyo de LLM.

Este módulo implementa el flujo de análisis basado en Teoría Fundamentada (Grounded Theory):
1. Etapa 0: Preparación y reflexividad
2. Etapa 1: Transcripción y resumen
3. Etapa 2: Análisis descriptivo inicial
4. Etapa 3: Codificación abierta (códigos emergentes)
5. Etapa 4: Codificación axial (relaciones entre códigos)

Componentes principales:
    - QUAL_SYSTEM_PROMPT: Prompt del sistema para guiar al LLM
    - run_qualitative_analysis(): Ejecuta el análisis completo
    - persist_analysis(): Guarda resultados en PostgreSQL y Neo4j
    - _infer_relation_type(): Infiere tipo de relación desde texto

Estructura de salida JSON del LLM:
    {
        "etapa0_observaciones": "...",
        "etapa1_resumen": "...",
        "etapa2_descriptivo": {...},
        "etapa3_matriz_abierta": [{"codigo": "...", "cita": "...", "fragmento_idx": N}],
        "etapa4_axial": [{"categoria": "...", "codigos": [...], "tipo_relacion": "partede"}]
    }

Tipos de relación válidos (etapa4):
    - "partede": Agrupación jerárquica (default)
    - "causa": Relación causal (A origina B)
    - "condicion": Dependencia condicional
    - "consecuencia": Resultado de

Estrategia de persistencia:
    - Etapa 3 → open_codes (PostgreSQL)
    - Etapa 4 → Categoria/Codigo (Neo4j con relaciones tipadas)

Métricas de logging:
    - analysis.persist.linkage_metrics: Tasa de linkeo fragmento-código
    - analysis.axial.persisted: Código axial guardado en Neo4j
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

import structlog

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - lightweight environments
    pd = None

from .axial import AxialError, assign_axial_relation
from .clients import ServiceClients
from .postgres_block import (
    ensure_axial_table,
    ensure_open_coding_table,
    ensure_candidate_codes_table,
    insert_candidate_codes,
    insert_analysis_memo,
    ensure_analysis_memos_table,
)
from .neo4j_block import (
    ensure_category_constraints,
    ensure_code_constraints,
    merge_category_code_relationship,
)
from .documents import make_fragment_id, match_citation_to_fragment
from .settings import AppSettings


QUAL_SYSTEM_PROMPT = """Eres un asistente AI experto en metodologia cualitativa y analisis de entrevistas.
Se te suministraran entrevistas transcritas previamente revisadas y verificadas en su fidelidad.

Instrucciones:
Etapa 0 - Preparacion, Reflexividad y Configuracion del Analisis: Revisa el texto buscando incoherencias en la transcripcion.
Etapa 1 - Transcripcion y resumen: Verifica literalidad y elabora un resumen breve.
Etapa 2 - Analisis Descriptivo Inicial: Resume primeras impresiones y temas superficiales. Justifica codigos iniciales.
Etapa 3 - Codificacion Abierta: Propon codigos y citas (matriz).
Etapa 4 - Codificacion Axial: Agrupa en categorias axiales, con notas/memos y relaciones.

Devuelve SIEMPRE un JSON valido con esta forma minima:
{
    "memo_sintesis": [
        {"type": "OBSERVATION", "text": "...", "evidence_ids": [1, 2]},
        {"type": "INTERPRETATION", "text": "...", "evidence_ids": [1, 2]},
        {"type": "HYPOTHESIS", "text": "..."},
        {"type": "NORMATIVE_INFERENCE", "text": "..."}
    ],
  "etapa0_observaciones": "...",
  "etapa1_resumen": "...",
  "etapa2_descriptivo": { "impresiones": "...", "lista_codigos_iniciales": ["..."] },
  "etapa3_matriz_abierta": [ { "codigo": "...", "cita": "...", "fragmento_idx": 12, "fuente": "Entrevistado/a" } ],
  "etapa4_axial": [ { 
    "categoria": "...", 
    "codigos": ["..."], 
    "tipo_relacion": "partede",
    "relaciones": ["A->B", "B<->C"], 
    "memo": "..." 
  } ]
}

IMPORTANTE para memo_sintesis:
- memo_sintesis DEBE ser una lista (no string).
- type DEBE ser uno de: OBSERVATION | INTERPRETATION | HYPOTHESIS | NORMATIVE_INFERENCE.
- OBSERVATION requiere evidence_ids no vacio.
- evidence_ids referencia bloques [IDX: n] usando indices 1..N (es decir, evidence_id = n + 1).

IMPORTANTE para etapa4_axial:
- tipo_relacion DEBE ser uno de: "partede" (agrupacion), "causa" (origina/genera), "condicion" (depende de), "consecuencia" (resultado de).
- Si no estas seguro, usa "partede" como valor por defecto.

Usa citas literales cortas (<= 60 palabras). Mantener anonimato.
"""

_logger = structlog.get_logger()

# Versioning / reproducibility metadata (no chain-of-thought persisted)
ANALYSIS_MEMO_SCHEMA_VERSION = 2
PROMPT_VERSION = "qual_system_prompt_v1"
PROMPT_HASH = hashlib.sha256(QUAL_SYSTEM_PROMPT.encode("utf-8")).hexdigest()

# Valid axial relation types (must match axial.py ALLOWED_REL_TYPES)
ALLOWED_REL_TYPES = {"causa", "condicion", "consecuencia", "partede"}

_EPISTEMIC_TYPES = {"OBSERVATION", "INTERPRETATION", "HYPOTHESIS", "NORMATIVE_INFERENCE"}


def _normalize_memo_sintesis(raw: Any) -> List[Dict[str, Any]]:
    """Normalize LLM output into a stable list of epistemic statements.

    Rule: never allow OBSERVATION without evidence_ids.
    """
    if not raw:
        return []
    if isinstance(raw, str):
        return []
    if not isinstance(raw, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        stype = str(item.get("type") or "").upper().strip()
        if stype not in _EPISTEMIC_TYPES:
            stype = "INTERPRETATION"

        text = str(item.get("text") or "").strip()
        if not text:
            continue

        evidence_raw = item.get("evidence_ids")
        evidence_ids: List[int] = []
        if isinstance(evidence_raw, list):
            for ev in evidence_raw:
                try:
                    ev_int = int(ev)
                except Exception:
                    continue
                if ev_int > 0:
                    evidence_ids.append(ev_int)
        evidence_ids = sorted(set(evidence_ids))

        if stype == "OBSERVATION" and not evidence_ids:
            stype = "INTERPRETATION"

        normalized.append(
            {
                "type": stype,
                "text": text,
                "evidence_ids": evidence_ids or None,
            }
        )
    return normalized


def _load_fragments_from_db(pg_conn, archivo: str, project_id: str) -> List[str]:
    """
    Carga los textos de fragmentos reales desde PostgreSQL ordenados por par_idx.
    
    Args:
        pg_conn: Conexión a PostgreSQL
        archivo: Nombre del archivo de entrevista
        project_id: ID del proyecto
        
    Returns:
        Lista de textos de fragmentos ordenados por par_idx (índice = par_idx)
    """
    sql = """
    SELECT fragmento FROM entrevista_fragmentos
    WHERE archivo = %s AND project_id = %s
    ORDER BY par_idx ASC
    """
    with pg_conn.cursor() as cur:
        cur.execute(sql, (archivo, project_id))
        rows = cur.fetchall()
    return [r[0] for r in rows]


def _cita_exists_in_fragment(cita: str, fragmento: str, min_overlap: float = 0.4) -> bool:
    """
    Verifica si la cita existe (o es semánticamente similar) al fragmento.
    
    Usa coincidencia parcial para tolerar variaciones menores en la transcripción.
    
    Args:
        cita: Cita literal del análisis LLM
        fragmento: Texto completo del fragmento
        min_overlap: Proporción mínima de palabras coincidentes (default 0.4)
        
    Returns:
        True si la cita está en el fragmento o tiene overlap suficiente
    """
    if not cita or not fragmento:
        return False
    
    cita_lower = cita.lower().strip()
    fragmento_lower = fragmento.lower()
    
    # Caso ideal: la cita está literalmente en el fragmento
    if cita_lower in fragmento_lower:
        return True
    
    # Caso alternativo: overlap de palabras significativo
    cita_words = set(cita_lower.split())
    frag_words = set(fragmento_lower.split())
    
    if not cita_words:
        return False
    
    overlap = len(cita_words & frag_words) / len(cita_words)
    return overlap >= min_overlap


def _infer_relation_type(relaciones: List[str], memo: str | None) -> str:
    """Infers the relation type from LLM annotations when not explicitly provided.
    
    Uses keyword matching to detect the semantic intent of the relationship.
    Falls back to 'partede' (conceptual grouping) when uncertain.
    """
    text = " ".join(relaciones).lower() + " " + (memo or "").lower()
    
    if any(kw in text for kw in ["causa", "provoca", "genera", "origina", "produce"]):
        return "causa"
    if any(kw in text for kw in ["condición", "condicion", "requiere", "depende", "necesita", "si"]):
        return "condicion"
    if any(kw in text for kw in ["consecuencia", "resultado", "efecto", "lleva", "deriva"]):
        return "consecuencia"
    
    return "partede"  # Default: conceptual grouping


MAX_LLM_RESPONSE_SIZE = 32000
REQUIRED_JSON_KEYS = {"etapa3_matriz_abierta"}


def call_llm_chat_json(
    clients: ServiceClients,
    settings: AppSettings,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """
    Llama al LLM y parsea respuesta JSON con robustez.
    
    Security/Reliability:
        - Retry automático hasta max_retries
        - Límite de tamaño de respuesta (32k chars)
        - Validación de schema mínimo
        - Logging de errores truncado
    
    Args:
        clients: ServiceClients
        settings: AppSettings
        system_prompt: Prompt del sistema
        user_prompt: Prompt del usuario
        temperature: No usado en gpt-5.x
        max_retries: Máximo de reintentos
        
    Returns:
        Dict parseado del JSON
        
    Raises:
        json.JSONDecodeError: Si no se puede parsear después de reintentos
        ValueError: Si el schema no es válido
    """
    import time
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    
    last_error = None
    
    for attempt in range(max_retries):
        start = time.perf_counter()
        
        try:
            kwargs = {
                "model": settings.azure.deployment_chat,
                "messages": messages,
            }
            
            response = clients.aoai.chat.completions.create(**kwargs)
            
            # Log metrics
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            usage = getattr(response, "usage", None)
            _logger.info(
                "llm.chat.complete",
                model=settings.azure.deployment_chat,
                prompt_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
                completion_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
                elapsed_ms=elapsed_ms,
                attempt=attempt + 1,
            )
            
            content = response.choices[0].message.content or ""
            
            # Size limit
            if len(content) > MAX_LLM_RESPONSE_SIZE:
                _logger.warning(
                    "llm.response_truncated",
                    original_size=len(content),
                    truncated_to=MAX_LLM_RESPONSE_SIZE,
                )
                content = content[:MAX_LLM_RESPONSE_SIZE]
            
            # Extract JSON
            start_json = content.find("{")
            end_json = content.rfind("}")
            if start_json == -1 or end_json == -1 or end_json <= start_json:
                raise json.JSONDecodeError("No JSON object found", content[:100], 0)
            
            json_str = content[start_json : end_json + 1]
            data = json.loads(json_str)
            
            # Schema validation
            missing_keys = REQUIRED_JSON_KEYS - set(data.keys())
            if missing_keys:
                raise ValueError(f"JSON missing required keys: {missing_keys}")
            
            return data
            
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            _logger.warning(
                "llm.json_parse_retry",
                attempt=attempt + 1,
                max_retries=max_retries,
                error=str(e)[:100],
            )
            
            if attempt < max_retries - 1:
                # Add correction prompt for retry
                messages.append({
                    "role": "assistant",
                    "content": content[:500] if 'content' in dir() else "(respuesta vacía)",
                })
                messages.append({
                    "role": "user",
                    "content": f"Tu respuesta no fue JSON válido. Error: {str(e)[:100]}. Por favor, devuelve SOLO un JSON válido.",
                })
    
    # All retries failed
    _logger.error(
        "llm.json_parse_failed",
        attempts=max_retries,
        error=str(last_error)[:200],
    )
    raise last_error



def get_graph_context(clients: ServiceClients, settings: AppSettings, project_id: str | None = None) -> str:
    """Retrieves high-level graph insights (GraphRAG) to ground the LLM.
    
    IMPORTANTE: Filtra por project_id para garantizar aislamiento entre proyectos.
    
    Args:
        clients: ServiceClients
        settings: AppSettings
        project_id: ID del proyecto (requerido para aislamiento)
    """
    pid = project_id or "default"
    try:
        session = clients.neo4j.session(database=settings.neo4j.database)
        
        # 1. Top Central Codes (PageRank) - FILTRADO POR PROJECT_ID
        res_central = session.run(
            "MATCH (n:Codigo) WHERE n.score_centralidad IS NOT NULL AND n.project_id = $project_id "
            "RETURN n.nombre AS nombre, n.score_centralidad AS score "
            "ORDER BY n.score_centralidad DESC LIMIT 8",
            project_id=pid
        ).data()
        
        # 2. Communities (Louvain) - FILTRADO POR PROJECT_ID
        res_communities = session.run(
            "MATCH (n:Codigo) WHERE n.community_id IS NOT NULL AND n.project_id = $project_id "
            "WITH n.community_id AS comm, collect(n.nombre) AS members "
            "RETURN comm, members[0..6] AS example_members "
            "ORDER BY size(members) DESC LIMIT 5",
            project_id=pid
        ).data()
        
        session.close()

        if not res_central and not res_communities:
            return ""

        context = ["\nCONTEXTO GLOBAL (Teoria Fundamentada Existente - Grafo Vivo):"]
        
        if res_central:
            names = [f"{r['nombre']} ({r['score']:.2f})" for r in res_central]
            context.append(f"- Codigos Centrales (Top Influencia): {', '.join(names)}")
            
        if res_communities:
            context.append("- Comunidades Tematicas Detectadas:")
            for r in res_communities:
                context.append(f"  * Grupo {r['comm']}: {', '.join(r['example_members'])}")
        
        return "\n".join(context)
        
    except Exception as e:
        _logger.warning("graph_rag.context_failed", error=str(e), project_id=pid)
        return ""


def analyze_interview_text(
    clients: ServiceClients,
    settings: AppSettings,
    fragments: List[str],
    fuente: str,
    temperature: float = 0.2,
    project_id: str | None = None,
    run_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Ejecuta an\u00e1lisis cualitativo de entrevista con LLM.
    
    Args:
        clients: ServiceClients
        settings: AppSettings
        fragments: Lista de fragmentos de texto
        fuente: Nombre de la fuente/entrevista
        temperature: Temperatura para LLM (no usado en gpt-5.x)
        project_id: ID del proyecto para aislamiento de contexto
    """
    # Estrategia Pre-Hoc: Ingesta virtual en el prompt
    text_construction = []
    for idx, frag in enumerate(fragments):
        text_construction.append(f"[IDX: {idx}] {frag}")
    
    joined_text = "\n\n".join(text_construction)
    
    # GraphRAG Injection - FILTRADO POR PROJECT_ID
    graph_context = get_graph_context(clients, settings, project_id=project_id)
    
    user_prompt = f"""Analiza la siguiente transcripcion (fuente: {fuente}) siguiendo las Etapas 0-4. 
IMPORTANTE: Para cada cita en 'etapa3_matriz_abierta', debes indicar el campo integer 'fragmento_idx' correspondiente al bloque [IDX: n] de donde extrajiste la cita.

{graph_context}

Devuelve SOLO el JSON.

{joined_text}"""
    out = call_llm_chat_json(clients, settings, QUAL_SYSTEM_PROMPT, user_prompt, temperature=temperature)
    memo_statements = _normalize_memo_sintesis(out.get("memo_sintesis"))

    # Fallback: if model didn't provide memo_sintesis, expose labeled statements from Etapa 4 memos.
    if not memo_statements:
        axial_rows = out.get("etapa4_axial", []) or []
        if isinstance(axial_rows, list):
            fallback: List[Dict[str, Any]] = []
            for row in axial_rows:
                if not isinstance(row, dict):
                    continue
                memo = str(row.get("memo") or "").strip()
                if not memo:
                    continue
                categoria = str(row.get("categoria") or "").strip()
                text = f"[{categoria}] {memo}" if categoria else memo
                fallback.append({"type": "INTERPRETATION", "text": text, "evidence_ids": None})
            memo_statements = fallback[:20]

    out["memo_statements"] = memo_statements
    out["structured"] = bool(memo_statements)

    out["cognitive_metadata"] = {
        "schema_version": ANALYSIS_MEMO_SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": PROMPT_HASH,
        "llm_provider": "azure_openai",
        "llm_deployment": settings.azure.deployment_chat,
        "llm_api_version": settings.azure.api_version,
        "run_id": run_id,
        "request_id": request_id,
    }
    return out


def matriz_etapa3(json_out: Dict[str, Any]) -> pd.DataFrame:
    if pd is None:
        raise RuntimeError("pandas es requerido para exportar la matriz de etapa 3")
    rows = json_out.get("etapa3_matriz_abierta", []) or []
    df = pd.DataFrame(rows, columns=["codigo", "cita", "fuente"])
    return df.rename(
        columns={
            "codigo": "Codigo Abierto",
            "cita": "Cita Textual / Ejemplo Relevante",
            "fuente": "Fuente (Entrevistado/a)",
        }
    )


def matriz_etapa4(json_out: Dict[str, Any]) -> pd.DataFrame:
    if pd is None:
        raise RuntimeError("pandas es requerido para exportar la matriz de etapa 4")
    rows = json_out.get("etapa4_axial", []) or []
    expanded: List[Dict[str, Any]] = []
    for row in rows:
        categoria = row.get("categoria", "")
        memo = row.get("memo", "")
        relaciones = "; ".join(row.get("relaciones", []) or [])
        for codigo in row.get("codigos", []) or []:
            expanded.append(
                {
                    "Categoria Axial": categoria,
                    "Codigo Abierto": codigo,
                    "Relaciones": relaciones,
                    "Notas/Memos": memo,
                }
            )
    return pd.DataFrame(expanded, columns=["Categoria Axial", "Codigo Abierto", "Relaciones", "Notas/Memos"])


def modelo_ascii(json_out: Dict[str, Any]) -> str:
    return json_out.get("etapa7_modelo_ascii", "(sin diagrama)")


def ensure_analysis_tables(pg_conn) -> None:
    ensure_open_coding_table(pg_conn)
    ensure_axial_table(pg_conn)
    ensure_analysis_memos_table(pg_conn)


def persist_analysis(
    clients: ServiceClients,
    settings: AppSettings,
    archivo: str,
    json_out: Dict[str, Any],
    project_id: str = "default",
    run_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    logger = _logger.bind(archivo=archivo, project_id=project_id)
    ensure_analysis_tables(clients.postgres)

    # Persist memo epistemológico (si existe) como snapshot para trazabilidad.
    try:
        memo_statements = json_out.get("memo_statements")
        if not isinstance(memo_statements, list):
            memo_statements = []
        structured = bool(json_out.get("structured")) or bool(memo_statements)

        # Derivar un texto compacto para consultas rápidas/legacy.
        memo_lines: List[str] = []
        for st in memo_statements[:50]:
            if not isinstance(st, dict):
                continue
            stype = str(st.get("type") or "").strip() or "INTERPRETATION"
            text = str(st.get("text") or "").strip()
            if not text:
                continue
            memo_lines.append(f"[{stype}] {text}")
        memo_text = "\n".join(memo_lines).strip() or None

        cognitive_metadata = json_out.get("cognitive_metadata")
        if not isinstance(cognitive_metadata, dict):
            cognitive_metadata = None

        insert_analysis_memo(
            clients.postgres,
            project_id=project_id,
            archivo=archivo,
            memo_text=memo_text,
            memo_statements=memo_statements,
            structured=structured,
            run_id=run_id,
            request_id=request_id,
            cognitive_metadata=cognitive_metadata,
            schema_version=ANALYSIS_MEMO_SCHEMA_VERSION,
        )
        logger.info(
            "analysis.persist.memo_saved",
            structured=structured,
            statements=len(memo_statements),
        )
    except Exception as exc:
        # Nunca bloquear persistencia principal (códigos/axial) por memo.
        logger.warning("analysis.persist.memo_save_failed", error=str(exc)[:200])

    rows3 = json_out.get("etapa3_matriz_abierta", []) or []
    
    # Mapa de código → lista de fragmento_ids para vincular evidencia a Etapa 4
    code_fragments: Dict[str, List[str]] = {}
    
    if rows3:
        open_rows = []
        
        # Cargar fragmentos REALES desde PostgreSQL para validación
        fragments_text = _load_fragments_from_db(clients.postgres, archivo, project_id)
        if not fragments_text:
            logger.warning(
                "analysis.persist.no_fragments_in_db",
                archivo=archivo,
                hint="Los fragmentos deben ser ingestados antes del análisis",
            )
        
        # Linkage metrics
        linked_count = 0
        recovered_count = 0
        corrected_count = 0
        skipped_count = 0
        
        for row in rows3:
            f_idx = row.get("fragmento_idx")
            cita = row.get("cita", "")
            codigo = row.get("codigo", "").lower().strip()
            
            # Fallback: Try to recover index from citation if not provided
            if f_idx is None and cita and fragments_text:
                # Attempt citation-based matching
                f_idx = match_citation_to_fragment(cita, fragments_text, threshold=0.5)
                if f_idx is not None:
                    recovered_count += 1
                    logger.info(
                        "analysis.persist.idx_recovered",
                        codigo=row.get("codigo"),
                        idx=f_idx,
                        method="citation_match",
                    )
            
            if f_idx is None:
                skipped_count += 1
                cita_preview = cita[:30] if cita else "(sin cita)"
                logger.warning(
                    "analysis.persist.skip_no_idx",
                    codigo=row.get("codigo"),
                    cita=cita_preview,
                )
                continue
            
            # VALIDACIÓN: Verificar que la cita existe en el fragmento real
            if fragments_text and 0 <= f_idx < len(fragments_text):
                fragmento_texto = fragments_text[f_idx]
                if not _cita_exists_in_fragment(cita, fragmento_texto):
                    # El LLM se equivocó, intentar corregir
                    corrected_idx = match_citation_to_fragment(cita, fragments_text, threshold=0.5)
                    if corrected_idx is not None and corrected_idx != f_idx:
                        original_idx = f_idx
                        f_idx = corrected_idx
                        corrected_count += 1
                        logger.info(
                            "analysis.persist.idx_corrected",
                            codigo=row.get("codigo"),
                            original_idx=original_idx,
                            corrected_idx=f_idx,
                            cita_preview=cita[:40],
                        )
                    else:
                        # No se pudo corregir, skip
                        logger.warning(
                            "analysis.persist.idx_mismatch_unfixable",
                            codigo=row.get("codigo"),
                            idx=f_idx,
                            cita_preview=cita[:40],
                        )
                        skipped_count += 1
                        continue
                
            try:
                fragmento_id = make_fragment_id(archivo, int(f_idx))
                linked_count += 1
                
                # Agregar al mapa de código → fragmentos para evidencia en Etapa 4
                if codigo:
                    code_fragments.setdefault(codigo, []).append(fragmento_id)
                    
            except (ValueError, TypeError):
                skipped_count += 1
                logger.warning("analysis.persist.invalid_idx", idx=f_idx)
                continue

            open_rows.append(
                (
                    project_id,
                    fragmento_id,
                    row.get("codigo", ""),
                    archivo,
                    cita,
                    row.get("fuente"),
                    None,  # memo
                )
            )
        
        # Log linkage metrics
        total = len(rows3)
        logger.info(
            "analysis.persist.linkage_metrics",
            total=total,
            linked=linked_count,
            recovered=recovered_count,
            corrected=corrected_count,
            skipped=skipped_count,
            linkage_rate=round(linked_count / max(total, 1) * 100, 1),
            codes_with_evidence=len(code_fragments),
        )
        
        # Insertar como candidatos para validación (modelo híbrido)
        # Los códigos del LLM pasan por la bandeja de validación antes de ser definitivos
        ensure_candidate_codes_table(clients.postgres)
        candidates = [
            {
                "project_id": row[0],
                "codigo": row[2],
                "cita": row[4],
                "fragmento_id": row[1],
                "archivo": row[3],
                "fuente_origen": "llm",
                "fuente_detalle": f"Análisis automático: {archivo}",
                "score_confianza": 0.7,  # Confianza base para LLM
                "memo": row[6],
            }
            for row in open_rows
        ]
        insert_candidate_codes(clients.postgres, candidates)
        
        logger.info(
            "analysis.persist.candidates_inserted",
            total=len(candidates),
            fuente="llm",
        )

    rows4 = json_out.get("etapa4_axial", []) or []
    
    # Ensure Neo4j constraints exist before persisting
    if rows4:
        ensure_category_constraints(clients.neo4j, settings.neo4j.database)
        ensure_code_constraints(clients.neo4j, settings.neo4j.database)
    
    for row in rows4:
        categoria = row.get("categoria", "")
        if not categoria:
            logger.warning("analysis.axial.skip", razon="sin categoria")
            continue
            
        memo = row.get("memo") or ""
        relaciones_text = row.get("relaciones", []) or []
        
        # Intelligent relation type resolution:
        # 1. Try explicit tipo_relacion (new prompt format)
        # 2. Try legacy tipo/relacion fields
        # 3. Infer from relaciones/memo text
        # 4. Fallback to 'partede' (valid default)
        raw_tipo = row.get("tipo_relacion") or row.get("tipo") or row.get("relacion")
        if raw_tipo and raw_tipo.lower().strip() in ALLOWED_REL_TYPES:
            relacion = raw_tipo.lower().strip()
        else:
            relacion = _infer_relation_type(relaciones_text, memo)
        
        codigos = row.get("codigos", []) or []
        if not codigos:
            logger.warning("analysis.axial.skip", razon="sin codigos", categoria=categoria)
            continue
            
        for codigo in codigos:
            try:
                # Obtener evidencia de fragmentos vinculados en Etapa 3
                codigo_normalized = codigo.lower().strip()
                evidencia_list = code_fragments.get(codigo_normalized, [])
                
                merge_category_code_relationship(
                    clients.neo4j,
                    settings.neo4j.database,
                    categoria=categoria,
                    codigo=codigo,
                    relacion=relacion,
                    evidencia=evidencia_list,  # ✅ Ahora con fragmentos de Etapa 3
                    memo=memo,
                    project_id=project_id,
                )
                logger.info(
                    "analysis.axial.persisted",
                    categoria=categoria,
                    codigo=codigo,
                    relacion=relacion,
                    evidencia_count=len(evidencia_list),
                )
            except Exception as exc:
                logger.warning(
                    "analysis.axial.error",
                    categoria=categoria,
                    codigo=codigo,
                    relacion=relacion,
                    error=str(exc),
                )

