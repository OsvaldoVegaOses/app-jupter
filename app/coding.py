"""
Codificación abierta y comparación constante.

Este módulo implementa la primera fase de codificación según Teoría Fundamentada:
la codificación abierta, donde se asignan códigos emergentes a fragmentos de texto.

También implementa la "comparación constante" - un proceso iterativo donde se
comparan fragmentos nuevos con los ya codificados para refinar los códigos.

Funciones principales:
    - assign_open_code(): Asigna un código a un fragmento
    - suggest_similar_fragments(): Sugiere fragmentos similares no codificados
    - citations_for_code(): Obtiene citas para un código específico
    - coding_statistics(): Estadísticas de codificación del proyecto
    - list_open_codes(): Lista códigos con frecuencias

Comparación constante:
    La función suggest_similar_fragments() implementa esto:
    1. Toma un fragmento "semilla"
    2. Busca fragmentos semánticamente similares
    3. Opcionalmente genera un memo LLM analizando convergencias
    4. Persiste la comparación para auditoría

Clases:
    - CodingError: Error específico de operaciones de codificación

Example:
    >>> from app.coding import assign_open_code
    >>> result = assign_open_code(
    ...     clients, settings,
    ...     fragment_id="frag_001",
    ...     codigo="resiliencia_comunitaria",
    ...     cita="La comunidad se adaptó rápidamente...",
    ...     project="mi_proyecto"
    ... )
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple, cast

import structlog
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import FieldCondition, Filter, MatchValue
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from .clients import ServiceClients
from .postgres_block import (
    coding_stats,
    cumulative_code_curve,
    delete_open_code,
    ensure_axial_table,
    ensure_open_coding_table,
    ensure_candidate_codes_table,
    evaluate_curve_plateau,
    fetch_fragment_by_id,
    get_citations_by_code,
    get_code_history,
    get_fragment_context,
    insert_candidate_codes,
    list_coded_fragment_ids,
    list_codes_summary,
    list_fragments_for_file,
    list_interviews_summary,
    log_code_version,
    log_constant_comparison,
)
from .neo4j_block import delete_fragment_code, ensure_code_constraints, merge_fragment_code
from .settings import AppSettings

_logger = structlog.get_logger()


class CodingError(Exception):
    """Raised when coding operations fail or encounter missing data."""


def assign_open_code(
    clients: ServiceClients,
    settings: AppSettings,
    fragment_id: str,
    codigo: str,
    cita: str,
    fuente: Optional[str] = None,
    memo: Optional[str] = None,
    project: Optional[str] = None,
    logger: Optional[structlog.BoundLogger] = None,
) -> Dict[str, Any]:
    log = logger or _logger
    project_id = project or "default"
    fragment = fetch_fragment_by_id(clients.postgres, fragment_id, project_id)
    if not fragment:
        raise CodingError(f"Fragmento '{fragment_id}' no existe en PostgreSQL")

    # Insertar como candidato para validación (modelo híbrido)
    # Los códigos manuales pasan por la bandeja de validación antes de ser definitivos
    ensure_candidate_codes_table(clients.postgres)
    insert_candidate_codes(
        clients.postgres,
        [{
            "project_id": project_id,
            "codigo": codigo,
            "cita": cita,
            "fragmento_id": fragment_id,
            "archivo": fragment["archivo"],
            "fuente_origen": "manual",
            "fuente_detalle": fuente,
            "score_confianza": 1.0,  # Máxima confianza para códigos manuales
            "memo": memo,
        }],
    )

    payload = {
        "fragmento_id": fragment_id,
        "archivo": fragment["archivo"],
        "codigo": codigo,
        "cita": cita,
        "fuente": fuente,
        "memo": memo,
        "estado": "pendiente",  # Indica que está en bandeja de validación
    }
    log.info("coding.assign.candidate", **payload)
    return payload


def unassign_open_code(
    clients: ServiceClients,
    settings: AppSettings,
    fragment_id: str,
    codigo: str,
    project: Optional[str] = None,
    changed_by: Optional[str] = None,
    logger: Optional[structlog.BoundLogger] = None,
) -> Dict[str, Any]:
    """
    Desvincula un código de un fragmento (operación inversa a assign_open_code).
    
    Elimina:
    - El registro en PostgreSQL (analisis_codigos_abiertos)
    - La relación TIENE_CODIGO en Neo4j
    
    NO elimina:
    - El nodo Código (puede estar usado por otros fragmentos)
    - El nodo Fragmento
    - Otras citas del mismo fragmento con otros códigos
    
    Args:
        clients: ServiceClients con conexiones a DBs
        settings: Configuración de la aplicación
        fragment_id: ID del fragmento
        codigo: Nombre del código a desvincular
        project: ID del proyecto
        logger: Logger opcional
        
    Returns:
        Dict con resultado de la operación
        
    Raises:
        CodingError: Si no se encontró la asignación
    """
    log = logger or _logger
    project_id = project or "default"
    
    # 1. Eliminar de PostgreSQL
    pg_deleted = delete_open_code(clients.postgres, project_id, fragment_id, codigo)
    
    # 2. Eliminar relación de Neo4j
    neo4j_deleted = delete_fragment_code(
        clients.neo4j, 
        settings.neo4j.database, 
        fragment_id, 
        codigo, 
        project_id
    )
    
    if pg_deleted == 0 and neo4j_deleted == 0:
        raise CodingError(f"No se encontró asignación de código '{codigo}' al fragmento '{fragment_id}'")

    # Best-effort version audit: treat unassign as a code mutation event for traceability.
    try:
        history = get_code_history(clients.postgres, project_id, codigo, limit=1)
        previous_memo = history[0]["memo_nuevo"] if history else None
        log_code_version(
            clients.postgres,
            project=project_id,
            codigo=codigo,
            accion="unassign_open_code",
            memo_anterior=previous_memo,
            memo_nuevo=f"unassigned from fragment {fragment_id}",
            changed_by=changed_by,
        )
    except Exception:
        pass
    
    payload = {
        "fragmento_id": fragment_id,
        "codigo": codigo,
        "project_id": project_id,
        "postgres_deleted": pg_deleted,
        "neo4j_deleted": neo4j_deleted,
    }
    log.info("coding.unassign", **payload)
    return payload


def _build_qdrant_filter(filters: Optional[Dict[str, Any]], project_id: str) -> Optional[Filter]:
    if not filters:
        filters = {}
    must_conditions: List[FieldCondition] = []
    must_not: List[FieldCondition] = []
    must_conditions.append(FieldCondition(key="project_id", match=MatchValue(value=project_id)))
    if filters.get("archivo"):
        must_conditions.append(
            FieldCondition(key="archivo", match=MatchValue(value=filters["archivo"]))
        )
    if filters.get("area_tematica"):
        must_conditions.append(
            FieldCondition(
                key="area_tematica", match=MatchValue(value=filters["area_tematica"])
            )
        )
    if filters.get("actor_principal"):
        must_conditions.append(
            FieldCondition(
                key="actor_principal",
                match=MatchValue(value=filters["actor_principal"]),
            )
        )
    if filters.get("requiere_protocolo_lluvia") is not None:
        must_conditions.append(
            FieldCondition(
                key="requiere_protocolo_lluvia",
                match=MatchValue(value=bool(filters["requiere_protocolo_lluvia"])),
            )
        )
    speaker_value = filters.get("speaker") if filters else None
    if speaker_value:
        must_conditions.append(FieldCondition(key="speaker", match=MatchValue(value=speaker_value)))
    else:
        must_not.append(FieldCondition(key="speaker", match=MatchValue(value="interviewer")))
    if not must_conditions:
        return None
    return Filter(must=cast(List[Any], must_conditions), must_not=cast(List[Any], must_not) or None)


def suggest_similar_fragments(
    clients: ServiceClients,
    settings: AppSettings,
    fragment_id: str,
    top_k: int = 5,
    filters: Optional[Dict[str, Any]] = None,
    exclude_coded: bool = True,
    *,
    run_id: Optional[str] = None,
    project: Optional[str] = None,
    persist: bool = False,
    llm_model: Optional[str] = None,
    logger: Optional[structlog.BoundLogger] = None,
) -> Dict[str, Any]:
    start = time.perf_counter()
    log = logger or _logger
    project_id = project or "default"
    fragment = fetch_fragment_by_id(clients.postgres, fragment_id, project_id)
    if not fragment:
        raise CodingError(f"Fragmento '{fragment_id}' no existe en PostgreSQL")

    vector = fragment.get("embedding")
    if not vector:
        raise CodingError(f"Fragmento '{fragment_id}' no tiene embedding almacenado")

    q_filter = _build_qdrant_filter(filters, project_id)
    exclusions = set()
    if exclude_coded:
        exclusions.update(list_coded_fragment_ids(clients.postgres, project_id))
    exclusions.add(fragment_id)

    limit = top_k + len(exclusions)
    try:
        response = clients.qdrant.query_points(
            collection_name=settings.qdrant.collection,
            query=vector,
            limit=limit,
            with_payload=True,
            query_filter=q_filter,
        )
    except UnexpectedResponse as exc:
        error_message = str(exc)
        if "Index required" in error_message:
            raise CodingError(
                "Qdrant requiere un índice para los filtros aplicados. Ejecuta `python scripts/healthcheck.py` "
                "o reejecuta la ingesta para reconstruir los índices (archivo, área temática, actor principal)."
            ) from exc
        raise CodingError(f"No se pudo consultar Qdrant ({error_message})") from exc
    suggestions: List[Dict[str, Any]] = []
    for point in response.points:
        point_id = str(point.id)
        if point_id in exclusions:
            continue
        payload = point.payload or {}
        suggestions.append(
            {
                "fragmento_id": point_id,
                "score": point.score,
                "archivo": payload.get("archivo"),
                "par_idx": payload.get("par_idx"),
                "fragmento": payload.get("fragmento"),
                "area_tematica": payload.get("area_tematica"),
                "actor_principal": payload.get("actor_principal"),
                "requiere_protocolo_lluvia": payload.get("requiere_protocolo_lluvia"),
                "speaker": payload.get("speaker"),
            }
        )
        if len(suggestions) >= top_k:
            break

    llm_summary: Optional[str] = None
    llm_model_resolved: Optional[str] = None
    if llm_model:
        llm_model_resolved = _resolve_llm_model(settings, llm_model)
        try:
            llm_summary = _generate_comparison_memo(
                clients,
                settings,
                seed_fragment_text=fragment.get("fragmento", ""),
                seed_fragment_id=fragment_id,
                suggestions=suggestions[: top_k],
                model_name=llm_model_resolved,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            log.warning("coding.suggest.llm_error", error=str(exc))
            llm_summary = None
            llm_model_resolved = None

    comparison_id: Optional[int] = None
    if persist or llm_summary:
        comparison_id = log_constant_comparison(
            clients.postgres,
            run_id=run_id or "",
            project=project_id,
            fragmento_semilla=fragment_id,
            top_k=top_k,
            filtros=filters or {},
            sugerencias=suggestions,
            llm_model=llm_model_resolved,
            llm_summary=llm_summary,
        )

    log.info(
        "coding.suggest",
        fragmento_id=fragment_id,
        requested=top_k,
        returned=len(suggestions),
        filters=filters or {},
        comparison_id=comparison_id,
        llm_model=llm_model_resolved,
        elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
    )
    return {
        "suggestions": suggestions,
        "comparison_id": comparison_id,
        "llm_summary": llm_summary,
        "llm_model": llm_model_resolved,
    }


def suggest_code_from_fragments(
    clients: ServiceClients,
    settings: AppSettings,
    fragments: List[Dict[str, Any]],
    existing_codes: Optional[List[str]] = None,
    llm_model: Optional[str] = None,
    project: Optional[str] = None,
    logger: Optional[structlog.BoundLogger] = None,
) -> Dict[str, Any]:
    """
    Sugiere nombre de código y memo basado en fragmentos seleccionados.
    
    Sprint 17 - E2: Sugerencia de Acción con IA.
    
    Args:
        clients: ServiceClients con conexiones
        settings: Configuración
        fragments: Lista de fragmentos con texto
        existing_codes: Códigos existentes para evitar duplicados
        llm_model: Modelo LLM a usar
        project: ID del proyecto
        
    Returns:
        Dict con suggested_code, memo, confidence
    """
    log = logger or _logger
    project_id = project or "default"
    
    if not fragments:
        return {
            "suggested_code": None,
            "memo": None,
            "confidence": "ninguna",
            "error": "No hay fragmentos para analizar",
        }
    
    # Resolver modelo
    resolved_model = _resolve_llm_model(settings, llm_model) if llm_model else None
    model_name = resolved_model or settings.azure.deployment_chat
    
    # Construir prompt
    fragment_texts = []
    for i, frag in enumerate(fragments[:5], 1):  # Máximo 5
        texto = (frag.get("fragmento") or frag.get("texto") or "")[:400]
        score = frag.get("score", 0)
        fragment_texts.append(f"[{i}] (score: {score:.2f}) \"{texto}...\"")
    
    existing_list = ""
    if existing_codes:
        existing_list = "\n".join(f"- {c}" for c in existing_codes[:20])
    
    prompt = f"""Analiza los siguientes fragmentos de entrevistas y propón UN código que agrupe el tema central.

FRAGMENTOS:
{chr(10).join(fragment_texts)}

{"CÓDIGOS EXISTENTES (evitar duplicados):" + chr(10) + existing_list if existing_list else ""}

INSTRUCCIONES:
1. Propón UN nombre de código en snake_case (2-4 palabras, español)
2. Escribe un memo de 2-3 oraciones explicando la convergencia temática
3. Indica nivel de confianza: alta (tema claro), media (tema inferido), baja (fragmentario)

Responde SOLO en formato JSON válido:
{{"suggested_code": "nombre_del_codigo", "memo": "Explicación del agrupamiento...", "confidence": "alta|media|baja"}}"""

    messages: List[ChatCompletionMessageParam] = [
        ChatCompletionSystemMessageParam(
            role="system",
            content="Eres un analista cualitativo experto en Teoría Fundamentada. Propones códigos significativos basados en datos.",
        ),
        ChatCompletionUserMessageParam(role="user", content=prompt),
    ]

    try:
        response = clients.aoai.chat.completions.create(
            model=model_name,
            messages=messages,
            max_completion_tokens=400,  # Increased from 300 to reduce truncation
        )
        
        # Handle potential None content safely
        content = (response.choices[0].message.content or "") if response.choices else ""
        
        # Parsear JSON de respuesta
        import json
        import re
        
        # Extraer JSON del contenido
        json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
            except json.JSONDecodeError as je:
                log.warning(
                    "coding.suggest_code.json_decode_error",
                    error=str(je),
                    raw_match=json_match.group()[:500],
                    full_content=content[:1000],
                    content_length=len(content),
                    model=model_name,
                    fragments_count=len(fragments),
                )
                return {
                    "suggested_code": None,
                    "memo": content,
                    "confidence": "baja",
                    "error": f"JSON decode error: {je}",
                }
            
            result["llm_model"] = model_name
            result["fragments_count"] = len(fragments)
            
            # Validar que suggested_code exista y no esté vacío
            suggested_code = (result.get("suggested_code") or "").strip()
            if not suggested_code:
                log.warning(
                    "coding.suggest_code.missing_suggested_code",
                    parsed_result=result,
                    full_content=content[:1000],
                    content_length=len(content),
                    model=model_name,
                    fragments_count=len(fragments),
                )
            
            log.info(
                "coding.suggest_code",
                suggested_code=result.get("suggested_code"),
                confidence=result.get("confidence"),
                fragments=len(fragments),
            )
            
            return result
        else:
            # No se encontró JSON en la respuesta - log detallado para diagnóstico
            log.warning(
                "coding.suggest_code.no_json_found",
                full_content=content[:1000],
                content_length=len(content),
                content_empty=len(content.strip()) == 0,
                model=model_name,
                fragments_count=len(fragments),
            )
            return {
                "suggested_code": None,
                "memo": content,
                "confidence": "baja",
                "error": "No se pudo parsear respuesta JSON",
            }
            
    except Exception as e:
        log.error("coding.suggest_code.error", error=str(e))
        return {
            "suggested_code": None,
            "memo": None,
            "confidence": "ninguna",
            "error": str(e),
        }


def citations_for_code(clients: ServiceClients, codigo: str, project: Optional[str]) -> List[Dict[str, Any]]:
    return get_citations_by_code(clients.postgres, codigo, project or "default")


def coding_statistics(clients: ServiceClients, project: Optional[str]) -> Dict[str, Any]:
    ensure_open_coding_table(clients.postgres)
    ensure_axial_table(clients.postgres)
    return coding_stats(clients.postgres, project or "default")


def _order_interviews_summary(interviews: List[Dict[str, Any]], order: str) -> List[Dict[str, Any]]:
    from datetime import datetime

    def _parse_ts(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        raw = str(value)
        try:
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def _archivo(it: Dict[str, Any]) -> str:
        return str(it.get("archivo") or "")

    def _updated(it: Dict[str, Any]) -> Optional[datetime]:
        return _parse_ts(it.get("actualizado"))

    def _fragmentos(it: Dict[str, Any]) -> int:
        try:
            return int(it.get("fragmentos") or 0)
        except (TypeError, ValueError):
            return 0

    normalized = (order or "").strip().lower()
    if not normalized or normalized == "ingest-desc":
        # Ya viene ordenado por SQL, pero reforzamos determinismo.
        return sorted(interviews, key=lambda it: (_updated(it) is None, _updated(it) or datetime.min, _archivo(it)), reverse=True)
    if normalized == "ingest-asc":
        return sorted(interviews, key=lambda it: (_updated(it) is None, _updated(it) or datetime.max, _archivo(it)))
    if normalized == "alpha":
        return sorted(interviews, key=lambda it: _archivo(it))
    if normalized == "fragments-desc":
        return sorted(interviews, key=lambda it: (_fragmentos(it), _archivo(it)), reverse=True)
    if normalized == "fragments-asc":
        return sorted(interviews, key=lambda it: (_fragmentos(it), _archivo(it)))
    if normalized == "max-variation":
        # Muestreo de máxima variación: intercalar estratos (area_tematica, actor_principal)
        # para cubrir diversidad temprano de forma reproducible.
        buckets: Dict[tuple, List[Dict[str, Any]]] = {}
        for it in interviews:
            key = (
                str(it.get("area_tematica") or ""),
                str(it.get("actor_principal") or ""),
            )
            buckets.setdefault(key, []).append(it)

        # Dentro de cada estrato: más reciente primero (proxy de orden de ingesta).
        for key in list(buckets.keys()):
            buckets[key] = sorted(
                buckets[key],
                key=lambda it: (_updated(it) is None, _updated(it) or datetime.min, _archivo(it)),
                reverse=True,
            )

        # Estratos pequeños primero: prioriza cubrir "casos raros".
        group_keys = sorted(buckets.keys(), key=lambda k: (len(buckets[k]), k))

        out: List[Dict[str, Any]] = []
        remaining = True
        while remaining:
            remaining = False
            for k in group_keys:
                if buckets[k]:
                    out.append(buckets[k].pop(0))
                    remaining = True
        return out

    # Fallback: no cambiar el orden.
    return interviews


def _order_interviews_theoretical_sampling(
    *,
    pg_conn: Any,
    project_id: str,
    interviews: List[Dict[str, Any]],
    include_analyzed: bool,
    focus_codes: Optional[str],
    recent_window: int,
    saturation_new_codes_threshold: int,
) -> List[Dict[str, Any]]:
    """Orden epistemológico: prioriza gaps + densidad + recencia si hay saturación.

    Nota: este MVP NO asume backlog de reclutamiento. Usa solo metadatos ya presentes
    en entrevistas y señales de `interview_reports` / `analisis_codigos_abiertos`.
    """
    ordered, _debug = _order_interviews_theoretical_sampling_with_debug(
        pg_conn=pg_conn,
        project_id=project_id,
        interviews=interviews,
        include_analyzed=include_analyzed,
        focus_codes=focus_codes,
        recent_window=recent_window,
        saturation_new_codes_threshold=saturation_new_codes_threshold,
    )
    return ordered


def _order_interviews_theoretical_sampling_with_debug(
    *,
    pg_conn: Any,
    project_id: str,
    interviews: List[Dict[str, Any]],
    include_analyzed: bool,
    focus_codes: Optional[str],
    recent_window: int,
    saturation_new_codes_threshold: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Como `_order_interviews_theoretical_sampling`, pero retorna `ranking_debug`.

    `ranking_debug` está pensado para auditoría/UX:
    - explica por entrevista: segment_key, gap_norm, richness_norm, recency_norm, score
    - incluye contexto global: saturated, new_codes_recent, threshold, pesos
    """
    import json
    import math
    from datetime import datetime

    def _parse_ts(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        raw = str(value)
        try:
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def _archivo(it: Dict[str, Any]) -> str:
        return str(it.get("archivo") or "")

    def _fragmentos(it: Dict[str, Any]) -> int:
        try:
            return int(it.get("fragmentos") or 0)
        except (TypeError, ValueError):
            return 0

    def _segment_key(it: Dict[str, Any]) -> Tuple[str, str]:
        return (
            str(it.get("area_tematica") or ""),
            str(it.get("actor_principal") or ""),
        )

    # 1) Detectar cuáles entrevistas ya tienen report.
    reports_by_archivo: Dict[str, Dict[str, Any]] = {}
    try:
        with pg_conn.cursor() as cur:
            cur.execute(
                """
                SELECT archivo, report_json
                  FROM interview_reports
                 WHERE project_id = %s
                """,
                (project_id,),
            )
            for archivo, report_json in cur.fetchall():
                try:
                    if isinstance(report_json, dict):
                        data = report_json
                    else:
                        data = json.loads(report_json)
                    reports_by_archivo[str(archivo)] = data
                except Exception:
                    continue
    except Exception:
        # Tabla inexistente o sin permisos: degradar a orden operacional.
        ordered = _order_interviews_summary(interviews, order="ingest-desc")
        return ordered, [
            {
                "archivo": str(it.get("archivo") or ""),
                "reason": "degraded_to_ingest_desc",
                "error": "interview_reports_unavailable",
            }
            for it in ordered
        ]

    # 2) Señal de saturación (CDR en ventana reciente).
    recent_window = max(1, int(recent_window or 3))
    threshold = max(0, int(saturation_new_codes_threshold or 2))

    new_codes_recent = 0
    try:
        with pg_conn.cursor() as cur:
            cur.execute(
                """
                SELECT report_json
                  FROM interview_reports
                 WHERE project_id = %s
                 ORDER BY fecha_analisis DESC
                 LIMIT %s
                """,
                (project_id, recent_window),
            )
            rows = cur.fetchall()
        for (report_json,) in rows:
            try:
                data = report_json if isinstance(report_json, dict) else json.loads(report_json)
                new_codes_recent += int(data.get("codigos_nuevos") or 0)
            except Exception:
                continue
    except Exception:
        new_codes_recent = 0

    saturated = new_codes_recent < threshold

    # 3) Focus codes (sin probe semántico): activar modo gap-first si hay baja evidencia.
    focus_mode_active = False
    focus_list: List[str] = []
    if focus_codes and str(focus_codes).strip():
        focus_list = [c.strip() for c in str(focus_codes).split(",") if c.strip()]
    if focus_list:
        try:
            with pg_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT codigo, COUNT(DISTINCT fragmento_id) AS evidencias
                      FROM analisis_codigos_abiertos
                     WHERE project_id = %s
                       AND codigo = ANY(%s)
                     GROUP BY codigo
                    """,
                    (project_id, focus_list),
                )
                found = {str(c): int(e or 0) for c, e in cur.fetchall()}
            for c in focus_list:
                if found.get(c, 0) <= 2:
                    focus_mode_active = True
                    break
        except Exception:
            focus_mode_active = False

    # 4) Segment gap: contar entrevistas analizadas por segmento.
    segment_analyzed_counts: Dict[Tuple[str, str], int] = {}
    for it in interviews:
        archivo = _archivo(it)
        if archivo and archivo in reports_by_archivo:
            key = _segment_key(it)
            segment_analyzed_counts[key] = segment_analyzed_counts.get(key, 0) + 1

    # 5) Normalizaciones
    max_frags = max((_fragmentos(it) for it in interviews), default=0)
    max_frags = max(1, max_frags)

    updated_ts = [dt for dt in (_parse_ts(it.get("actualizado")) for it in interviews) if dt is not None]
    min_dt = min(updated_ts) if updated_ts else None
    max_dt = max(updated_ts) if updated_ts else None

    def _recency_norm(it: Dict[str, Any]) -> float:
        if not min_dt or not max_dt or min_dt == max_dt:
            return 0.0
        dt = _parse_ts(it.get("actualizado"))
        if not dt:
            return 0.0
        span = (max_dt - min_dt).total_seconds()
        if span <= 0:
            return 0.0
        return float(max(0.0, min(1.0, (dt - min_dt).total_seconds() / span)))

    def _richness_norm(it: Dict[str, Any]) -> float:
        return float(math.log1p(_fragmentos(it)) / math.log1p(max_frags))

    def _gap_norm(it: Dict[str, Any]) -> float:
        n = segment_analyzed_counts.get(_segment_key(it), 0)
        return float(1.0 / math.sqrt(1.0 + float(n)))

    # 6) Pesos
    if saturated or focus_mode_active:
        w_gap, w_rich, w_rec = 0.70, 0.20, 0.10
    else:
        w_gap, w_rich, w_rec = 0.55, 0.25, 0.20

    # 7) Scoring: no analizadas primero; analizadas al final si include_analyzed.
    scored: List[Tuple[float, Dict[str, Any]]] = []
    analyzed_tail: List[Dict[str, Any]] = []
    debug_by_archivo: Dict[str, Dict[str, Any]] = {}
    for it in interviews:
        archivo = _archivo(it)
        has_report = bool(archivo and archivo in reports_by_archivo)

        debug_entry: Dict[str, Any] = {
            "archivo": archivo,
            "has_report": has_report,
            "segment_key": {
                "area_tematica": str(it.get("area_tematica") or ""),
                "actor_principal": str(it.get("actor_principal") or ""),
            },
            "segment_analyzed_count": int(segment_analyzed_counts.get(_segment_key(it), 0)),
            "fragmentos": _fragmentos(it),
            "actualizado": it.get("actualizado"),
            "signals": {
                "saturated": bool(saturated),
                "new_codes_recent": int(new_codes_recent),
                "recent_window": int(recent_window),
                "threshold": int(threshold),
                "focus_mode_active": bool(focus_mode_active),
                "focus_codes": focus_list,
            },
            "weights": {
                "w_gap": float(w_gap),
                "w_rich": float(w_rich),
                "w_recency": float(w_rec),
            },
        }

        if has_report and not include_analyzed:
            debug_entry["excluded"] = True
            debug_entry["reason"] = "already_analyzed"
            debug_by_archivo[archivo] = debug_entry
            continue
        if has_report:
            debug_entry["excluded"] = False
            debug_entry["reason"] = "already_analyzed_included_tail"
            debug_by_archivo[archivo] = debug_entry
            analyzed_tail.append(it)
            continue

        gap = _gap_norm(it)
        rich = _richness_norm(it)
        rec = _recency_norm(it)
        score = w_gap * gap + w_rich * rich + w_rec * rec
        debug_entry.update(
            {
                "excluded": False,
                "gap_norm": float(gap),
                "richness_norm": float(rich),
                "recency_norm": float(rec),
                "score": float(score),
            }
        )
        debug_by_archivo[archivo] = debug_entry
        scored.append((float(score), it))

    scored.sort(
        key=lambda t: (
            t[0],
            _parse_ts(t[1].get("actualizado")) or datetime.min,
            _archivo(t[1]),
        ),
        reverse=True,
    )
    ordered = [it for _, it in scored]

    if include_analyzed and analyzed_tail:
        ordered.extend(_order_interviews_summary(analyzed_tail, order="ingest-desc"))

    # Ensamblar ranking_debug respetando el orden final
    ranking_debug: List[Dict[str, Any]] = []
    for it in ordered:
        archivo = _archivo(it)
        entry = debug_by_archivo.get(archivo)
        if entry:
            ranking_debug.append(entry)
        else:
            ranking_debug.append({"archivo": archivo, "reason": "no_debug"})

    return ordered, ranking_debug


def list_available_interviews_with_ranking_debug(
    clients: ServiceClients,
    project: Optional[str],
    limit: int = 25,
    order: str = "ingest-desc",
    include_analyzed: bool = False,
    focus_codes: Optional[str] = None,
    recent_window: int = 3,
    saturation_new_codes_threshold: int = 2,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    interviews = list_interviews_summary(clients.postgres, project or "default", limit=limit)
    normalized = (order or "").strip().lower()
    if normalized == "theoretical-sampling":
        return _order_interviews_theoretical_sampling_with_debug(
            pg_conn=clients.postgres,
            project_id=str(project or "default"),
            interviews=interviews,
            include_analyzed=bool(include_analyzed),
            focus_codes=focus_codes,
            recent_window=int(recent_window or 3),
            saturation_new_codes_threshold=int(saturation_new_codes_threshold or 2),
        )

    ordered = _order_interviews_summary(interviews, order=order)
    return ordered, []


def list_available_interviews(
    clients: ServiceClients,
    project: Optional[str],
    limit: int = 25,
    order: str = "ingest-desc",
    include_analyzed: bool = False,
    focus_codes: Optional[str] = None,
    recent_window: int = 3,
    saturation_new_codes_threshold: int = 2,
) -> List[Dict[str, Any]]:
    ordered, _debug = list_available_interviews_with_ranking_debug(
        clients,
        project,
        limit=limit,
        order=order,
        include_analyzed=include_analyzed,
        focus_codes=focus_codes,
        recent_window=recent_window,
        saturation_new_codes_threshold=saturation_new_codes_threshold,
    )
    return ordered


def list_open_codes(clients: ServiceClients, project: Optional[str], limit: int = 50, search: Optional[str] = None, archivo: Optional[str] = None) -> List[Dict[str, Any]]:
    ensure_open_coding_table(clients.postgres)
    from app.postgres_block import ensure_codes_catalog_table

    ensure_codes_catalog_table(clients.postgres)
    return list_codes_summary(clients.postgres, project or "default", limit=limit, search=search, archivo=archivo)


def list_interview_fragments(clients: ServiceClients, project: Optional[str], archivo: str, limit: int = 25) -> List[Dict[str, Any]]:
    return list_fragments_for_file(clients.postgres, project or "default", archivo, limit=limit)


def fetch_fragment_context(clients: ServiceClients, project: Optional[str], fragment_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene el contexto completo de un fragmento para visualización en modal.
    
    Retorna:
        - fragment: Datos completos del fragmento
        - codes: Lista de códigos asignados
        - codes_count: Total de códigos
        - adjacent_fragments: Fragmentos adyacentes para contexto
    """
    return get_fragment_context(clients.postgres, fragment_id, project or "default")


def get_all_codes_for_project(pg_conn, project_id: str) -> List[str]:
    """
    Obtiene lista de todos los códigos únicos en un proyecto.
    
    Usado para calcular novedad de códigos nuevos en análisis.
    """
    ensure_open_coding_table(pg_conn)
    with pg_conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT codigo FROM open_codes
            WHERE project_id = %s
        """, (project_id,))
        rows = cur.fetchall()
    return [row[0] for row in rows if row[0]]


def get_saturation_data(clients: ServiceClients, project: Optional[str], window: int = 3, threshold: int = 2) -> Dict[str, Any]:
    """
    Obtiene datos de saturación teórica para el indicador visual.
    
    Returns:
        - curve: Lista de entrevistas con códigos nuevos y acumulados
        - plateau: Información sobre si se alcanzó saturación
        - summary: Resumen de estadísticas
    """
    ensure_open_coding_table(clients.postgres)
    curve = cumulative_code_curve(clients.postgres, project or "default")
    plateau_info = evaluate_curve_plateau(curve, window=window, threshold=threshold)
    
    total_codigos = curve[-1]["codigos_acumulados"] if curve else 0
    total_entrevistas = len(curve)
    
    return {
        "curve": curve,
        "plateau": plateau_info,
        "summary": {
            "total_codigos": total_codigos,
            "total_entrevistas": total_entrevistas,
            "saturacion_alcanzada": plateau_info.get("plateau", False),
            "ultimos_nuevos": plateau_info.get("nuevos_codigos", []),
        }
    }


def export_codes_refi_qda(clients: ServiceClients, project: Optional[str]) -> str:
    """
    Exporta códigos y citas en formato REFI-QDA XML (compatible con Atlas.ti 9+).
    """
    ensure_open_coding_table(clients.postgres)
    codes = list_codes_summary(clients.postgres, project or "default", limit=1000)
    
    # Construir XML REFI-QDA
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Project xmlns="urn:QDA-XML:project:1.0" name="' + (project or "default") + '">',
        '  <CodeBook>',
        '    <Codes>',
    ]
    
    for idx, code in enumerate(codes, start=1):
        lines.append(f'      <Code guid="code-{idx}" name="{code["codigo"]}" isCodable="true">')
        lines.append(f'        <Description>Citas: {code["citas"]}, Fragmentos: {code["fragmentos"]}</Description>')
        lines.append('      </Code>')
    
    lines.extend([
        '    </Codes>',
        '  </CodeBook>',
        '</Project>',
    ])
    
    return '\n'.join(lines)


def export_codes_maxqda_csv(clients: ServiceClients, project: Optional[str]) -> str:
    """
    Exporta códigos y citas en formato CSV compatible con MAXQDA.
    """
    ensure_open_coding_table(clients.postgres)
    codes = list_codes_summary(clients.postgres, project or "default", limit=1000)
    
    lines = ["Code,Quotations,Fragments,FirstQuote,LastQuote"]
    for code in codes:
        primera = code.get("primera_cita") or ""
        ultima = code.get("ultima_cita") or ""
        lines.append(f'"{code["codigo"]}",{code["citas"]},{code["fragmentos"]},"{primera}","{ultima}"')
    
    return '\n'.join(lines)


def fetch_code_history(clients: ServiceClients, project: Optional[str], codigo: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Obtiene el historial de versiones de un código."""
    return get_code_history(clients.postgres, project or "default", codigo, limit=limit)


def _resolve_llm_model(settings: AppSettings, alias: Optional[str]) -> Optional[str]:
    if not alias:
        return None
    normalized = alias.strip().lower()
    if normalized in {"gpt-5-mini", "gpt5-mini", "mini"}:
        return settings.azure.deployment_chat_mini or settings.azure.deployment_chat
    if normalized in {"gpt-5.2-chat", "gpt-5-chat", "gpt5-chat", "chat"}:
        return settings.azure.deployment_chat
    return alias


def _generate_comparison_memo(
    clients: ServiceClients,
    settings: AppSettings,
    *,
    seed_fragment_text: str,
    seed_fragment_id: str,
    suggestions: List[Dict[str, Any]],
    model_name: Optional[str],
    max_items: int = 3,
) -> Optional[str]:
    if not model_name:
        return None
    trimmed_seed = seed_fragment_text.strip()
    summary_items: List[Tuple[str, str]] = []
    for idx, item in enumerate(suggestions[:max_items], start=1):
        fragmento = (item.get("fragmento") or "").strip()
        if not fragmento:
            continue
        fragment_excerpt = fragmento[:450]
        summary_items.append((item.get("fragmento_id", f"sugerencia_{idx}"), fragment_excerpt))
    if not trimmed_seed or not summary_items:
        return None

    lines = [
        "Analiza la comparación constante entre un fragmento semilla y sugerencias semánticas.",
        "Resume convergencias, divergencias y oportunidades de refinamiento de códigos.",
        "Responde en español con máximo 4 viñetas.",
        f"Fragmento semilla ({seed_fragment_id}): {trimmed_seed[:600]}",
    ]
    for frag_id, excerpt in summary_items:
        lines.append(f"Sugerencia {frag_id}: {excerpt}")
    lines.append("Genera viñetas breves y una recomendación final.")

    messages: List[ChatCompletionMessageParam] = [
        ChatCompletionSystemMessageParam(
            role="system",
            content="Eres un analista cualitativo experto en teoría fundamentada.",
        ),
        ChatCompletionUserMessageParam(role="user", content="\n".join(lines)),
    ]

    kwargs = {
        "model": model_name,
        "messages": messages,
    }
    
    # gpt-5.x models no soportan temperature != 1, no enviar el parámetro
    kwargs["max_completion_tokens"] = 400

    response = clients.aoai.chat.completions.create(**kwargs)
    return response.choices[0].message.content if response.choices else None


def find_similar_codes(
    clients: ServiceClients,
    settings: AppSettings,
    codigo: str,
    project: Optional[str] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    Encuentra códigos semánticamente similares en el proyecto.
    
    Usado para sugerir sinónimos o fusiones al validar códigos candidatos.
    
    Estrategia:
    1. Obtiene los embeddings de las citas asociadas al código
    2. Busca otros fragmentos con códigos similares
    3. Agrupa por código y calcula un score promedio
    
    Args:
        clients: ServiceClients con conexiones a DBs
        settings: Configuración de la aplicación
        codigo: Nombre del código a buscar similares
        project: ID del proyecto
        top_k: Número máximo de códigos similares a retornar
    
    Returns:
        Lista de códigos similares con score de similitud
    """
    project_id = project or "default"
    
    # 1. Obtener citas del código actual
    citations = get_citations_by_code(clients.postgres, codigo, project_id)
    if not citations:
        return []
    
    # 2. Obtener embeddings de los fragmentos asociados
    fragment_ids = [c["fragmento_id"] for c in citations if c.get("fragmento_id")]
    if not fragment_ids:
        return []
    
    # Tomar el primer fragmento como referencia
    first_fragment = fetch_fragment_by_id(clients.postgres, fragment_ids[0], project_id)
    if not first_fragment or not first_fragment.get("embedding"):
        return []
    
    vector = first_fragment["embedding"]
    
    # 3. Buscar fragmentos similares en Qdrant
    q_filter = Filter(
        must=[
            FieldCondition(key="project_id", match=MatchValue(value=project_id)),
        ]
    )
    
    try:
        response = clients.qdrant.query_points(
            collection_name=settings.qdrant.collection,
            query=vector,
            limit=50,  # Obtener suficientes para agrupar por código
            with_payload=True,
            query_filter=q_filter,
        )
    except Exception:
        return []
    
    # 4. Obtener códigos asociados a los fragmentos encontrados
    similar_fragment_ids = [str(p.id) for p in response.points if str(p.id) not in fragment_ids]
    
    if not similar_fragment_ids:
        return []
    
    # Consultar códigos de esos fragmentos
    placeholders = ",".join(["%s"] * len(similar_fragment_ids))
    sql = f"""
    SELECT fragmento_id, codigo, COUNT(*) as frecuencia
      FROM analisis_codigos_abiertos
     WHERE project_id = %s AND fragmento_id IN ({placeholders})
       AND codigo != %s
     GROUP BY fragmento_id, codigo
    """
    
    code_scores: Dict[str, List[float]] = {}
    fragment_score_map = {str(p.id): p.score for p in response.points}
    
    with clients.postgres.cursor() as cur:
        cur.execute(sql, [project_id] + similar_fragment_ids + [codigo])
        rows = cur.fetchall()
        
        for fragment_id, other_codigo, _ in rows:
            score = fragment_score_map.get(fragment_id, 0.5)
            if other_codigo not in code_scores:
                code_scores[other_codigo] = []
            code_scores[other_codigo].append(score)
    
    # 5. Calcular score promedio y ordenar
    results = []
    for code_name, scores in code_scores.items():
        avg_score = sum(scores) / len(scores)
        results.append({
            "codigo": code_name,
            "score": round(avg_score, 4),
            "occurrences": len(scores),
        })
    
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]

