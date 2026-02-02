"""
Sistema de Informes para Análisis Cualitativo.

Este módulo implementa la generación y persistencia de informes por entrevista
y acumulativos para soportar el flujo de Teoría Fundamentada.

Funcionalidades:
    - InterviewReport: Modelo de informe por entrevista individual
    - generate_interview_report(): Genera informe después del análisis
    - save_interview_report(): Persiste en PostgreSQL
    - get_interview_reports(): Lista informes de un proyecto
    - generate_stage4_summary(): Genera resumen para transición a Etapa 5

Flujo:
    1. Después de task_analyze_interview → generate_interview_report()
    2. Guarda en tabla interview_reports
    3. Panel de informes consulta y muestra progreso
    4. Informe final consolida para Etapa 5
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields
from datetime import datetime
from typing import Any, Dict, List, Optional
import json
import re

import structlog

from app.report_artifacts import _get_recent_report_artifacts, get_recent_memos_for_reporting

_logger = structlog.get_logger()


def _parse_llm_json(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    clean = raw.strip()
    clean = re.sub(r"^```json?\s*", "", clean)
    clean = re.sub(r"\s*```$", "", clean)
    try:
        return json.loads(clean)
    except Exception:
        return None


_EPISTEMIC_TYPES = {"OBSERVATION", "INTERPRETATION", "HYPOTHESIS", "NORMATIVE_INFERENCE"}


def _normalize_memo_sintesis(value: Any) -> List[Dict[str, Any]]:
    """Normalize a LLM memo list into safe epistemic statements.

    Rule: never allow OBSERVATION without evidence_ids.
    """
    if not isinstance(value, list):
        return []

    statements: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        stype = str(item.get("type") or "").strip().upper()
        text = str(item.get("text") or "").strip()
        evidence_ids_raw = item.get("evidence_ids")

        if not text:
            continue
        if stype not in _EPISTEMIC_TYPES:
            stype = "INTERPRETATION"

        evidence_ids: List[int] = []
        if isinstance(evidence_ids_raw, list):
            for v in evidence_ids_raw:
                try:
                    evidence_ids.append(int(v))
                except Exception:
                    continue

        if stype == "OBSERVATION" and not evidence_ids:
            stype = "INTERPRETATION"

        entry: Dict[str, Any] = {"type": stype, "text": text}
        if evidence_ids:
            entry["evidence_ids"] = evidence_ids
        statements.append(entry)

    return statements

# =============================================================================
# MODELOS DE INFORME
# =============================================================================

@dataclass
class InterviewReport:
    """
    Informe de análisis por entrevista individual.
    
    Captura métricas de codificación abierta y axial para cada entrevista,
    permitiendo análisis comparativo y seguimiento de saturación.
    """
    # Identificación
    archivo: str
    project_id: str
    fecha_analisis: datetime = field(default_factory=datetime.now)
    
    # Etapa 3 - Codificación Abierta
    codigos_generados: List[str] = field(default_factory=list)
    codigos_nuevos: int = 0
    codigos_reutilizados: int = 0
    fragmentos_analizados: int = 0
    fragmentos_codificados: int = 0
    tasa_cobertura: float = 0.0  # % fragmentos con código
    
    # Etapa 4 - Codificación Axial
    categorias_generadas: List[str] = field(default_factory=list)
    categorias_nuevas: int = 0
    relaciones_creadas: int = 0
    relaciones_por_tipo: Dict[str, int] = field(default_factory=dict)
    fragmentos_con_evidencia: int = 0
    
    # Saturación
    aporte_novedad: float = 0.0  # % códigos nuevos vs total
    contribucion_saturacion: str = "media"  # alta, media, baja
    
    # Sugerencias (Link Prediction)
    sugerencias_link: List[Dict[str, Any]] = field(default_factory=list)
    
    # Memo del investigador
    memo_investigador: Optional[str] = None

    # Briefing IA / Briefing+ (persisted inside report_json for printable reporting)
    briefing: Optional[Dict[str, Any]] = None

    # Archive reference (Azure Blob)
    blob_url: Optional[str] = None
    blob_path: Optional[str] = None
    
    # Metadata
    llm_model: Optional[str] = None
    duracion_segundos: Optional[float] = None

    # Cognitive/version metadata for reproducibility (no CoT)
    cognitive_metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario serializable."""
        data = asdict(self)
        data["fecha_analisis"] = self.fecha_analisis.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InterviewReport":
        """Crea instancia desde diccionario."""
        if isinstance(data.get("fecha_analisis"), str):
            data["fecha_analisis"] = datetime.fromisoformat(data["fecha_analisis"])
        allowed = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in (data or {}).items() if k in allowed}
        return cls(**filtered)
    
    def calcular_contribucion_saturacion(self) -> str:
        """Determina nivel de contribución a saturación teórica."""
        if self.codigos_nuevos == 0:
            return "baja"  # No aporta códigos nuevos
        
        total = self.codigos_nuevos + self.codigos_reutilizados
        if total == 0:
            return "media"
            
        ratio = self.codigos_nuevos / total
        
        if ratio >= 0.6:
            return "alta"  # Mayoría son nuevos
        elif ratio >= 0.3:
            return "media"
        else:
            return "baja"  # Mayoría reutilizados


# =============================================================================
# TABLA PostgreSQL
# =============================================================================

def ensure_reports_table(pg_conn) -> None:
    """Asegura que exista la tabla de informes."""
    with pg_conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS interview_reports (
                id SERIAL PRIMARY KEY,
                project_id VARCHAR(100) NOT NULL,
                archivo VARCHAR(500) NOT NULL,
                fecha_analisis TIMESTAMP DEFAULT NOW(),
                report_json JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(project_id, archivo)
            )
        """)
        # Índice para búsqueda por proyecto
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_interview_reports_project 
            ON interview_reports(project_id)
        """)
    pg_conn.commit()


def save_interview_report(pg_conn, report: InterviewReport) -> int:
    """
    Guarda o actualiza un informe de entrevista.
    
    Returns:
        ID del registro insertado/actualizado
    """
    ensure_reports_table(pg_conn)
    
    with pg_conn.cursor() as cur:
        cur.execute("""
            INSERT INTO interview_reports (project_id, archivo, fecha_analisis, report_json)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (project_id, archivo)
            DO UPDATE SET 
                fecha_analisis = EXCLUDED.fecha_analisis,
                report_json = EXCLUDED.report_json,
                created_at = NOW()
            RETURNING id
        """, (
            report.project_id,
            report.archivo,
            report.fecha_analisis,
            json.dumps(report.to_dict(), default=str),
        ))
        result = cur.fetchone()
        report_id = result[0] if result else 0
    
    pg_conn.commit()
    
    _logger.info(
        "report.saved",
        project=report.project_id,
        archivo=report.archivo,
        report_id=report_id,
    )
    
    return report_id


def get_interview_reports(
    pg_conn,
    project_id: str,
    limit: int = 50,
) -> List[InterviewReport]:
    """
    Obtiene los informes de un proyecto.
    
    Returns:
        Lista de InterviewReport ordenados por fecha
    """
    ensure_reports_table(pg_conn)
    
    with pg_conn.cursor() as cur:
        cur.execute("""
            SELECT report_json
            FROM interview_reports
            WHERE project_id = %s
            ORDER BY fecha_analisis DESC
            LIMIT %s
        """, (project_id, limit))
        
        rows = cur.fetchall()
    
    reports = []
    for row in rows:
        try:
            data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            reports.append(InterviewReport.from_dict(data))
        except Exception as e:
            _logger.warning("report.parse_error", error=str(e))
    
    return reports


def get_interview_report(pg_conn, project_id: str, archivo: str) -> Optional[InterviewReport]:
    """Obtiene un informe específico por archivo."""
    ensure_reports_table(pg_conn)
    
    with pg_conn.cursor() as cur:
        cur.execute("""
            SELECT report_json
            FROM interview_reports
            WHERE project_id = %s AND archivo = %s
        """, (project_id, archivo))
        
        row = cur.fetchone()
    
    if not row:
        return None
    
    try:
        data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        return InterviewReport.from_dict(data)
    except Exception:
        return None


# =============================================================================
# GENERADOR DE INFORME
# =============================================================================

def generate_interview_report(
    archivo: str,
    project_id: str,
    analysis_result: Dict[str, Any],
    existing_codes: Optional[List[str]] = None,
    existing_categories: Optional[List[str]] = None,
    fragments_total: int = 0,
    llm_model: Optional[str] = None,
) -> InterviewReport:
    """
    Genera un informe estructurado a partir del resultado del análisis LLM.
    
    Args:
        archivo: Nombre del archivo analizado
        project_id: ID del proyecto
        analysis_result: JSON del análisis (etapa3 + etapa4)
        existing_codes: Códigos ya existentes en el proyecto (para calcular novedad)
        existing_categories: Categorías ya existentes
        fragments_total: Total de fragmentos en el archivo
        llm_model: Modelo LLM usado
        
    Returns:
        InterviewReport con métricas calculadas
    """
    # Extract Briefing+ (if present). Frontend persists it under analysis_result['briefing'].
    briefing = None
    try:
        b = analysis_result.get("briefing")
        if isinstance(b, dict):
            briefing = b
    except Exception:
        briefing = None

    # Optional: archive hints if upstream included them
    blob_url = None
    blob_path = None
    try:
        v = analysis_result.get("blob_url")
        if isinstance(v, str) and v.strip():
            blob_url = v.strip()
    except Exception:
        blob_url = None
    try:
        v = analysis_result.get("blob_path")
        if isinstance(v, str) and v.strip():
            blob_path = v.strip()
    except Exception:
        blob_path = None

    cognitive_metadata = None
    try:
        v = analysis_result.get("cognitive_metadata")
        if isinstance(v, dict):
            cognitive_metadata = v
    except Exception:
        cognitive_metadata = None
    existing_codes_set = set((c.lower().strip() for c in (existing_codes or [])))
    existing_categories_set = set((c.lower().strip() for c in (existing_categories or [])))
    
    # Extraer datos de Etapa 3
    rows3 = analysis_result.get("etapa3_matriz_abierta", []) or []
    codigos_generados = list(set(
        row.get("codigo", "").strip() 
        for row in rows3 
        if row.get("codigo")
    ))
    
    codigos_nuevos = 0
    codigos_reutilizados = 0
    fragmentos_codificados = len(set(row.get("fragmento_idx") for row in rows3 if row.get("fragmento_idx") is not None))
    
    for codigo in codigos_generados:
        if codigo.lower().strip() in existing_codes_set:
            codigos_reutilizados += 1
        else:
            codigos_nuevos += 1
    
    # Extraer datos de Etapa 4
    rows4 = analysis_result.get("etapa4_axial", []) or []
    categorias_generadas = list(set(
        row.get("categoria", "").strip()
        for row in rows4
        if row.get("categoria")
    ))
    
    categorias_nuevas = 0
    relaciones_creadas = 0
    relaciones_por_tipo: Dict[str, int] = {}
    
    for row in rows4:
        categoria = row.get("categoria", "").strip()
        if categoria and categoria.lower() not in existing_categories_set:
            categorias_nuevas += 1
        
        codigos_en_cat = row.get("codigos", []) or []
        relaciones_creadas += len(codigos_en_cat)
        
        tipo = row.get("tipo_relacion", "partede")
        relaciones_por_tipo[tipo] = relaciones_por_tipo.get(tipo, 0) + len(codigos_en_cat)
    
    # Calcular métricas
    tasa_cobertura = (fragmentos_codificados / max(fragments_total, 1)) * 100 if fragments_total else 0
    total_codigos = codigos_nuevos + codigos_reutilizados
    aporte_novedad = (codigos_nuevos / max(total_codigos, 1)) * 100 if total_codigos else 0
    
    # Crear informe
    report = InterviewReport(
        archivo=archivo,
        project_id=project_id,
        fecha_analisis=datetime.now(),
        codigos_generados=codigos_generados,
        codigos_nuevos=codigos_nuevos,
        codigos_reutilizados=codigos_reutilizados,
        fragmentos_analizados=fragments_total,
        fragmentos_codificados=fragmentos_codificados,
        tasa_cobertura=round(tasa_cobertura, 1),
        categorias_generadas=categorias_generadas,
        categorias_nuevas=categorias_nuevas,
        relaciones_creadas=relaciones_creadas,
        relaciones_por_tipo=relaciones_por_tipo,
        aporte_novedad=round(aporte_novedad, 1),
        llm_model=llm_model,
        briefing=briefing,
        blob_url=blob_url,
        blob_path=blob_path,
        cognitive_metadata=cognitive_metadata,
    )
    
    # Calcular contribución a saturación
    report.contribucion_saturacion = report.calcular_contribucion_saturacion()
    
    _logger.info(
        "report.generated",
        archivo=archivo,
        codigos_nuevos=codigos_nuevos,
        codigos_reutilizados=codigos_reutilizados,
        categorias=len(categorias_generadas),
        saturacion=report.contribucion_saturacion,
    )
    
    return report


# =============================================================================
# RESUMEN ETAPA 4 (para transición a Etapa 5)
# =============================================================================

@dataclass
class Stage4Summary:
    """Resumen consolidado de Etapa 4 para transición a Etapa 5."""
    project_id: str
    fecha_generacion: datetime = field(default_factory=datetime.now)
    
    # Totales
    total_entrevistas: int = 0
    total_codigos_unicos: int = 0
    total_categorias: int = 0
    total_relaciones: int = 0
    
    # Por tipo de relación
    relaciones_por_tipo: Dict[str, int] = field(default_factory=dict)
    
    # Saturación
    score_saturacion: float = 0.0
    saturacion_alcanzada: bool = False
    
    # Candidatos a núcleo
    candidatos_nucleo: List[Dict[str, Any]] = field(default_factory=list)
    
    # Informes individuales
    informes_entrevistas: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["fecha_generacion"] = self.fecha_generacion.isoformat()
        return data


def generate_stage4_summary(
    pg_conn,
    project_id: str,
    nucleus_candidates: Optional[List[Dict[str, Any]]] = None,
) -> Stage4Summary:
    """
    Genera resumen consolidado de Etapa 4.
    
    Consolida todos los informes por entrevista y calcula métricas
    globales para la transición a Etapa 5 (Selección del Núcleo).
    """
    reports = get_interview_reports(pg_conn, project_id)
    
    if not reports:
        return Stage4Summary(project_id=project_id)
    
    # Consolidar métricas
    all_codes = set()
    all_categories = set()
    total_relaciones = 0
    relaciones_por_tipo: Dict[str, int] = {}
    
    informes_dict = []
    for report in reports:
        all_codes.update(c.lower().strip() for c in report.codigos_generados)
        all_categories.update(c.lower().strip() for c in report.categorias_generadas)
        total_relaciones += report.relaciones_creadas
        
        for tipo, count in report.relaciones_por_tipo.items():
            relaciones_por_tipo[tipo] = relaciones_por_tipo.get(tipo, 0) + count
        
        informes_dict.append({
            "archivo": report.archivo,
            "fecha": report.fecha_analisis.isoformat(),
            "codigos_nuevos": report.codigos_nuevos,
            "saturacion": report.contribucion_saturacion,
        })
    
    # Calcular score de saturación (basado en últimos 3 informes)
    ultimos = reports[:3]
    if len(ultimos) >= 2:
        codigos_nuevos_recientes = sum(r.codigos_nuevos for r in ultimos)
        if codigos_nuevos_recientes <= 2:
            score_saturacion = 0.9
            saturacion_alcanzada = True
        elif codigos_nuevos_recientes <= 5:
            score_saturacion = 0.7
            saturacion_alcanzada = False
        else:
            score_saturacion = 0.4
            saturacion_alcanzada = False
    else:
        score_saturacion = 0.3
        saturacion_alcanzada = False
    
    return Stage4Summary(
        project_id=project_id,
        total_entrevistas=len(reports),
        total_codigos_unicos=len(all_codes),
        total_categorias=len(all_categories),
        total_relaciones=total_relaciones,
        relaciones_por_tipo=relaciones_por_tipo,
        score_saturacion=score_saturacion,
        saturacion_alcanzada=saturacion_alcanzada,
        candidatos_nucleo=nucleus_candidates or [],
        informes_entrevistas=informes_dict,
    )


# =============================================================================
# CANDIDATOS A NÚCLEO SELECTIVO
# =============================================================================

def identify_nucleus_candidates(
    neo4j_driver,
    database: str,
    project_id: str,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    Identifica categorías candidatas a núcleo selectivo.
    
    Usa métricas del grafo (PageRank, grado, community_id) para
    priorizar categorías que podrían ser el núcleo central.
    
    Returns:
        Lista de candidatos con scores y justificación
    """
    candidates = []
    
    with neo4j_driver.session(database=database) as session:
        # Query: Categorías con más códigos conectados y mayor centralidad
        result = session.run("""
            MATCH (c:Categoria {project_id: $project_id})-[r:REL]->(k:Codigo {project_id: $project_id})
            WHERE coalesce(r.origen, '') <> 'descubierta'
              AND coalesce(r.source, '') <> 'descubierta'
            WITH c, 
                 count(DISTINCT k) as num_codigos,
                 count(r) as num_relaciones,
                 collect(DISTINCT k.nombre) as codigos,
                 avg(coalesce(k.score_centralidad, 0)) as avg_centrality
            RETURN c.nombre as categoria,
                   num_codigos,
                   num_relaciones,
                   codigos[0..5] as sample_codigos,
                   avg_centrality,
                   coalesce(c.community_id, -1) as community_id
            ORDER BY num_relaciones DESC, avg_centrality DESC
            LIMIT $top_k
        """, project_id=project_id, top_k=top_k)
        
        for record in result:
            score = (record["num_relaciones"] * 0.4 + 
                    record["num_codigos"] * 0.3 + 
                    record["avg_centrality"] * 100 * 0.3)
            
            candidates.append({
                "categoria": record["categoria"],
                "num_codigos": record["num_codigos"],
                "num_relaciones": record["num_relaciones"],
                "sample_codigos": record["sample_codigos"],
                "avg_centrality": round(record["avg_centrality"], 4),
                "community_id": record["community_id"],
                "score_nucleo": round(score, 2),
            })
    
    _logger.info(
        "nucleus.candidates_identified",
        project=project_id,
        count=len(candidates),
    )
    
    return candidates


# =============================================================================
# INFORME FINAL ETAPA 4 CON IA
# =============================================================================

def generate_stage4_final_report(
    pg_conn,
    neo4j_driver,
    database: str,
    aoai_client,
    deployment_chat: str,
    project_id: str,
    *,
    org_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Genera el informe final de Etapa 4 con análisis IA.
    
    Este informe sirve como entrada para Etapa 5 (Selección del Núcleo).
    
    Incluye:
    1. Resumen ejecutivo
    2. Métricas consolidadas
    3. Candidatos a núcleo con justificación
    4. Análisis IA de patrones emergentes
    5. Recomendaciones para Etapa 5
    """
    # Obtener candidatos a núcleo
    candidates = identify_nucleus_candidates(neo4j_driver, database, project_id)
    
    # Generar resumen base
    summary = generate_stage4_summary(pg_conn, project_id, candidates)
    
    # Preparar prompt para análisis IA
    reports_text = "\n".join([
        f"- {r['archivo']}: {r['codigos_nuevos']} códigos nuevos, saturación: {r['saturacion']}"
        for r in summary.informes_entrevistas[:10]
    ])
    
    candidates_text = "\n".join([
        f"- {c['categoria']}: {c['num_codigos']} códigos, {c['num_relaciones']} relaciones, score: {c['score_nucleo']}"
        for c in candidates[:5]
    ])

    recent_memos = get_recent_memos_for_reporting(pg_conn, project_id)
    recent_artifacts = _get_recent_report_artifacts(pg_conn, project_id, org_id=org_id, max_items=10)
    
    prompt = f"""Analiza los resultados de la Etapa 4 (Codificación Axial) de un estudio cualitativo.

**Métricas del proyecto:**
- Total entrevistas analizadas: {summary.total_entrevistas}
- Códigos únicos generados: {summary.total_codigos_unicos}
- Categorías axiales: {summary.total_categorias}
- Relaciones axiales: {summary.total_relaciones}
- Score de saturación: {summary.score_saturacion:.0%}

**Resumen por entrevista:**
{reports_text}

**Candidatos a núcleo selectivo (por densidad de relaciones):**
{candidates_text}

**Memos analíticos recientes (Discovery + candidatos):**
{recent_memos}

**Artefactos recientes (runner/informes/insights ya generados):**
{recent_artifacts}

Por favor proporciona:

1. **Evaluación de saturación**: ¿Los datos sugieren que se ha alcanzado saturación teórica? Justifica.

2. **Análisis de candidatos a núcleo**: De los candidatos listados, ¿cuál parece más prometedor como categoría central y por qué?

3. **Patrones emergentes**: ¿Qué patrones conceptuales detectas en la estructura de categorías?

4. **Recomendaciones**: Próximos pasos específicos para la Etapa 5 (Selección del Núcleo).

5. **Anexo: Artefactos recientes considerados**: Incluye una lista enumerada de **3 a 6** artefactos tomados exclusivamente desde "Artefactos recientes" (runner / informe por entrevista / informe doctoral / insight). Para cada uno: identificador (archivo/etiqueta) + 1 línea de cómo influyó.

REGLA DE AUDITORÍA:
- Debe aparecer exactamente el encabezado: "Anexo: Artefactos recientes considerados".
- No inventes artefactos: usa solo los provistos en el bloque.

IMPORTANTE: Responde ÚNICAMENTE con un JSON válido (sin markdown, sin ```).

El JSON debe tener esta estructura exacta:

{{
    "analysis_text": "(texto en español, máx 400 palabras; incluye exactamente el encabezado 'Anexo: Artefactos recientes considerados' cuando corresponda)",
    "memo_sintesis": [
        {{"type": "OBSERVATION", "text": "...", "evidence_ids": [1]}},
        {{"type": "INTERPRETATION", "text": "..."}},
        {{"type": "HYPOTHESIS", "text": "..."}},
        {{"type": "NORMATIVE_INFERENCE", "text": "..."}}
    ]
}}

REGLAS:
1. memo_sintesis: 3-6 statements.
2. type: uno de OBSERVATION | INTERPRETATION | HYPOTHESIS | NORMATIVE_INFERENCE.
3. evidence_ids: opcional; si usas números, refiérete a ítems del bloque "Artefactos recientes" (1..10) o de "Candidatos a núcleo" (1..5).
4. PROHIBIDO: OBSERVATION sin evidence_ids no vacíos.
"""

    # Llamar a IA
    try:
        response = aoai_client.chat.completions.create(
            model=deployment_chat,
            messages=[
                {"role": "system", "content": "Eres un experto en Teoría Fundamentada y análisis cualitativo. Respondes SOLO con JSON válido."},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=600,
        )
        raw = response.choices[0].message.content if response.choices else ""

        parsed = _parse_llm_json(raw)
        if isinstance(parsed, dict):
            ia_analysis = str(parsed.get("analysis_text") or "").strip() or raw
            memo_statements = _normalize_memo_sintesis(parsed.get("memo_sintesis"))
            ia_structured = parsed.get("memo_sintesis") is not None
        else:
            ia_analysis = raw
            memo_statements = []
            ia_structured = False
    except Exception as e:
        _logger.error("stage4_report.ia_error", error=str(e))
        ia_analysis = f"Error al generar análisis IA: {str(e)}"
        memo_statements = []
        ia_structured = False
    
    # Printable appendix: interview archive list (Blob URLs surfaced from fragment metadata)
    try:
        from app.postgres_block import list_interviews_summary

        interviews = list_interviews_summary(pg_conn, project_id, limit=250)
    except Exception:
        interviews = []

    appendix_lines: List[str] = []
    appendix_lines.append("## Anexo: Entrevistas archivadas")
    appendix_lines.append("")
    appendix_lines.append("| Archivo | Fragmentos | Actualizado | Archivo en Azure Blob |")
    appendix_lines.append("|---|---:|---|---|")
    for it in interviews:
        archivo = (it.get("archivo") or "").replace("|", "\\|")
        fragmentos = it.get("fragmentos") or 0
        actualizado = it.get("actualizado") or ""
        blob_url = it.get("blob_url") or ""
        blob_cell = f"[{blob_url}]({blob_url})" if blob_url else "(no archivado)"
        appendix_lines.append(f"| {archivo} | {fragmentos} | {actualizado} | {blob_cell} |")
    appendix_markdown = "\n".join(appendix_lines) + "\n"

    # Construir informe final
    final_report = {
        "project_id": project_id,
        "fecha_generacion": datetime.now().isoformat(),
        "summary": summary.to_dict(),
        "candidatos_nucleo": candidates,
        "ia_analysis": ia_analysis,
        "structured": bool(ia_structured),
        "memo_statements": memo_statements,
        "recomendacion_etapa5": (
            "Proceder a Etapa 5" if summary.saturacion_alcanzada 
            else "Continuar análisis hasta saturación"
        ),
        "interviews_archive": interviews,
        "interviews_archive_markdown": appendix_markdown,
    }
    
    _logger.info(
        "stage4_report.generated",
        project=project_id,
        candidates=len(candidates),
        saturacion=summary.saturacion_alcanzada,
    )
    
    return final_report

