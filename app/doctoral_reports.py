"""
Generación de Informes Doctorales.

Este módulo genera informes formales de avance doctoral para las etapas 3 y 4
del análisis cualitativo con Teoría Fundamentada.

Etapa 3 (Codificación Abierta):
    - Metodología aplicada
    - Códigos emergentes con definiciones
    - Análisis de saturación teórica
    - Memos analíticos consolidados

Etapa 4 (Codificación Axial):
    - Modelo relacional emergente
    - Análisis de comunidades
    - Candidatos a categoría nuclear
    - Síntesis integrada
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import json
import re

import structlog

from app.postgres_block import (
    list_codes_summary,
    coding_stats,
    cumulative_code_curve,
    list_interviews_summary,
)
from app.settings import AppSettings
from app.clients import ServiceClients
from app.report_artifacts import _get_recent_report_artifacts

_logger = structlog.get_logger(__name__)


def _sanitize_llm_report_body(content: str) -> str:
    """Normalize LLM output so the final report has a single consistent header.

    The API wrappers in this module already prepend a deterministic H1 header.
    Some LLM responses still include their own H1/title + metadata block.
    We strip any leading content before the first "## 1." section header.
    """
    if not content:
        return content
    text = str(content).lstrip()

    # Find the first section header "## 1." (optionally preceded by whitespace/newlines).
    match = re.search(r"(^|\n)##\s*1\.", text)
    if match:
        return text[match.start(0) :].lstrip("\n")

    return text


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
    if not isinstance(value, list):
        return []
    statements: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        stype = str(item.get("type") or "").strip().upper()
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        if stype not in _EPISTEMIC_TYPES:
            stype = "INTERPRETATION"
        evidence_ids_raw = item.get("evidence_ids")
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


def _format_interviews_archive_appendix(interviews: List[Dict[str, Any]]) -> str:
    """Deterministic printable appendix: one row per interview with archive URL."""
    if not interviews:
        return "## Anexo: Entrevistas archivadas\n\n(Sin entrevistas registradas)\n"

    lines: List[str] = []
    lines.append("## Anexo: Entrevistas archivadas")
    lines.append("")
    lines.append("| Archivo | Fragmentos | Actualizado | Archivo en Azure Blob |")
    lines.append("|---|---:|---|---|")
    for it in interviews:
        archivo = (it.get("archivo") or "").replace("|", "\\|")
        fragmentos = it.get("fragmentos") or 0
        actualizado = it.get("actualizado") or ""
        blob_url = it.get("blob_url") or ""
        blob_cell = f"[{blob_url}]({blob_url})" if blob_url else "(no archivado)"
        lines.append(f"| {archivo} | {fragmentos} | {actualizado} | {blob_cell} |")

    lines.append("")
    lines.append("Nota: Si aparece '(no archivado)', revise `AZURE_STORAGE_CONNECTION_STRING` y re-ingeste el DOCX.")
    return "\n".join(lines) + "\n"


# =============================================================================
# PROMPTS PARA GENERACIÓN LLM
# =============================================================================

STAGE3_PROMPT = """Eres un asistente experto en metodología de Teoría Fundamentada para investigación doctoral.

Tu tarea es generar un informe de avance doctoral para la ETAPA 3: CODIFICACIÓN ABIERTA.

DATOS DEL PROYECTO:
- Proyecto: {project}
- Fecha: {date}
- Total fragmentos analizados: {total_fragments}
- Total códigos emergentes: {total_codes}
- Entrevistas procesadas: {total_interviews}

CÓDIGOS EMERGENTES (top 20 por frecuencia):
{codes_list}

CURVA DE SATURACIÓN:
{saturation_data}

MEMOS DEL INVESTIGADOR:
{memos}

ARTEFACTOS RECIENTES (salidas ya generadas, runner/informes/insights):
{recent_artifacts}

INSTRUCCIONES:
Genera un informe académico formal con las siguientes secciones:

## 1. Metodología Aplicada
Describe el proceso de codificación abierta seguido, incluyendo el uso de asistencia IA.

## 2. Códigos Emergentes
Lista los códigos principales con una breve definición operacional basada en su uso.

## 3. Análisis de Saturación Teórica
Analiza la curva de saturación y justifica si se alcanzó saturación o qué falta.

## 4. Memos Analíticos
Sintetiza las reflexiones del investigador en categorías temáticas.

## 5. Decisiones Metodológicas
Identifica patrones en los códigos y sugiere posibles fusiones o reorganizaciones.

## 6. Conclusiones Preliminares
Resume los hallazgos principales de esta etapa.

## 7. Anexo: Artefactos recientes considerados
Incluye una lista enumerada de **3 a 6** artefactos **del bloque ARTEFACTOS RECIENTES** que realmente utilizaste para fundamentar el informe.
Para cada artefacto, incluye: (a) tipo (runner / informe por entrevista / informe doctoral / insight), (b) identificador (nombre de archivo o etiqueta), (c) 1 línea explicando cómo influyó.

REQUISITO:
- Integra los ARTEFACTOS RECIENTES cuando aporten evidencia, progreso o contradicciones; si los usas, menciona explícitamente el tipo (runner / informe por entrevista / informe doctoral / insight) para trazabilidad.

REGLA DE AUDITORÍA:
- Debe aparecer exactamente el encabezado: "## Anexo: Artefactos recientes considerados".
- En el anexo lista **solo** artefactos provistos en ARTEFACTOS RECIENTES.

FORMATO (CRÍTICO):
- NO incluyas un título H1 ("# ...") ni portada ni metadatos del informe.
- NO repitas "Informe de Avance Doctoral".
- Comienza directamente en "## 1. Metodología Aplicada" y continúa con el resto de secciones.

Usa lenguaje académico formal apropiado para una tesis doctoral. Incluye citas textuales cuando sea relevante.
"""

STAGE4_PROMPT = """Eres un asistente experto en metodología de Teoría Fundamentada para investigación doctoral.

Tu tarea es generar un informe de avance doctoral para la ETAPA 4: CODIFICACIÓN AXIAL.

DATOS DEL PROYECTO:
- Proyecto: {project}
- Fecha: {date}
- Total categorías: {total_categories}
- Total relaciones axiales: {total_relationships}
- Comunidades detectadas: {communities_count}

CATEGORÍAS Y RELACIONES:
{axial_structure}

CÓDIGOS POR CENTRALIDAD (PageRank):
{centrality_data}

COMUNIDADES DETECTADAS (Louvain):
{communities_data}

PREDICCIONES DE ENLACES CONFIRMADAS:
{predictions}

SÍNTESIS DE GRAPHRAG:
{graphrag_summaries}

MEMOS DEL INVESTIGADOR:
{memos}

ARTEFACTOS RECIENTES (salidas ya generadas, runner/informes/insights):
{recent_artifacts}

INSTRUCCIONES:
Genera un informe académico formal con las siguientes secciones:

## 1. Modelo Relacional Emergente
Describe la estructura axial que ha emergido del análisis.

## 2. Análisis de Comunidades
Interpreta los clusters detectados y su significado teórico.

## 3. Nodos Centrales
Analiza los códigos con mayor centralidad y su rol estructural.

## 4. Candidatos a Categoría Nuclear
Identifica qué categorías podrían convertirse en el núcleo de la teoría.

## 5. Síntesis Integrada
Consolida las reflexiones de GraphRAG y Discovery.

## 6. Hacia la Teoría Sustantiva
Propón los próximos pasos para la codificación selectiva (Etapa 5).

## 7. Anexo: Artefactos recientes considerados
Incluye una lista enumerada de **3 a 6** artefactos **del bloque ARTEFACTOS RECIENTES** que realmente utilizaste para fundamentar el informe.
Para cada artefacto, incluye: (a) tipo (runner / informe por entrevista / informe doctoral / insight), (b) identificador (nombre de archivo o etiqueta), (c) 1 línea explicando cómo influyó.

REQUISITO:
- Integra MEMOS y ARTEFACTOS RECIENTES cuando sea relevante; si los usas, menciona explícitamente el tipo (runner / informe por entrevista / informe doctoral / insight) para trazabilidad.

REGLA DE AUDITORÍA:
- Debe aparecer exactamente el encabezado: "## Anexo: Artefactos recientes considerados".
- En el anexo lista **solo** artefactos provistos en ARTEFACTOS RECIENTES.

FORMATO (CRÍTICO):
- NO incluyas un título H1 ("# ...") ni portada ni metadatos del informe.
- NO repitas "Informe de Avance Doctoral".
- Comienza directamente en "## 1. Modelo Relacional Emergente" y continúa con el resto de secciones.

Usa lenguaje académico formal apropiado para una tesis doctoral.
"""


# =============================================================================
# FUNCIONES DE RECOLECCIÓN DE DATOS
# =============================================================================

def _get_codes_list(pg, project: str, limit: int = 20) -> str:
    """Obtiene lista formateada de códigos con frecuencia."""
    codes = list_codes_summary(pg, project)[:limit]
    if not codes:
        return "(No hay códigos registrados)"
    
    lines = []
    for c in codes:
        lines.append(f"- **{c['codigo']}** ({c['citas']} ocurrencias)")
    return "\n".join(lines)


def _get_saturation_data(pg, project: str) -> str:
    """Obtiene datos de curva de saturación."""
    try:
        curve = cumulative_code_curve(pg, project)
        if not curve or len(curve) < 2:
            return "(Datos insuficientes para análisis de saturación)"
        
        last_point = curve[-1]
        lines = [
            f"- Fragmentos analizados: {last_point.get('fragmentos', 'N/A')}",
            f"- Códigos acumulados: {last_point.get('codigos_acumulados', 'N/A')}",
        ]
        
        # Detectar estabilización
        if len(curve) >= 5:
            recent = curve[-5:]
            codes_recent = [p.get('codigos_nuevos', 0) for p in recent]
            avg_new = sum(codes_recent) / len(codes_recent)
            if avg_new < 1:
                lines.append("- **Estado:** Saturación alcanzada (promedio < 1 código nuevo)")
            else:
                lines.append(f"- **Estado:** En progreso (promedio {avg_new:.1f} códigos nuevos)")
        
        return "\n".join(lines)
    except Exception as e:
        return f"(Error obteniendo saturación: {e})"


def _get_memos(pg, project: str) -> str:
    """
    Obtiene memos consolidados del proyecto desde múltiples fuentes.
    
    Fuentes:
    1. discovery_navigation_log - Síntesis de IA de Discovery
    2. codigos_candidatos - Memos de códigos candidatos
    3. Archivos .md en notes/{project}/ - Memos guardados
    """
    memos = []
    
    try:
        # 1. Memos de Discovery (síntesis IA) - Fuente principal
        sql_discovery = """
        SELECT ai_synthesis, positivos, created_at
        FROM discovery_navigation_log 
        WHERE project_id = %s AND ai_synthesis IS NOT NULL AND ai_synthesis != ''
        ORDER BY created_at DESC
        LIMIT 8
        """
        with pg.cursor() as cur:
            cur.execute(sql_discovery, (project,))
            discovery_rows = cur.fetchall()
        
        for r in discovery_rows:
            synthesis = r[0][:300] + "..." if len(r[0]) > 300 else r[0]
            positivos = ", ".join(r[1][:3]) if r[1] else "(sin conceptos)"
            memos.append(f"**[Discovery: {positivos}]**\n  {synthesis}")
        
        # 2. Memos de códigos candidatos
        sql_candidates = """
        SELECT DISTINCT memo 
        FROM codigos_candidatos 
        WHERE project_id = %s AND memo IS NOT NULL AND memo != ''
        LIMIT 5
        """
        with pg.cursor() as cur:
            cur.execute(sql_candidates, (project,))
            candidate_rows = cur.fetchall()
        
        for r in candidate_rows:
            memo = r[0][:200] + "..." if len(r[0]) > 200 else r[0]
            memos.append(f"**[Código Candidato]**\n  {memo}")
        
    except Exception as e:
        _logger.warning("doctoral.memos.db_error", error=str(e))
    
    # 3. Memos de archivos .md en notes/{project}/
    try:
        from pathlib import Path
        notes_dir = Path("notes") / project
        if notes_dir.exists():
            for md_file in sorted(notes_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:3]:
                content = md_file.read_text(encoding="utf-8")
                # Extraer sección "Síntesis y Sugerencias (IA)" si existe
                if "## 🧠 Síntesis" in content:
                    start = content.find("## 🧠 Síntesis")
                    end = content.find("---", start)
                    if end == -1:
                        end = len(content)
                    synthesis = content[start:end].strip()
                    # Limpiar encabezado
                    synthesis = synthesis.replace("## 🧠 Síntesis y Sugerencias (IA)", "").strip()
                    if synthesis:
                        filename = md_file.stem[:40]
                        memos.append(f"**[Archivo: {filename}]**\n  {synthesis[:250]}...")
    except Exception as e:
        _logger.warning("doctoral.memos.file_error", error=str(e))
    
    if not memos:
        return "(No hay memos registrados. Genera análisis con IA en Discovery o GraphRAG.)"
    
    return "\n\n".join(memos)


def _get_axial_structure(pg, project: str) -> str:
    """Obtiene estructura axial formateada."""
    sql = """
    SELECT categoria, codigo, relacion, COUNT(*) as count
    FROM analisis_axial
    WHERE project_id = %s
    GROUP BY categoria, codigo, relacion
    ORDER BY count DESC
    LIMIT 20
    """
    try:
        with pg.cursor() as cur:
            cur.execute(sql, (project,))
            rows = cur.fetchall()
        
        if not rows:
            return "(No hay relaciones axiales registradas)"
        
        lines = []
        for cat, code, rel, count in rows:
            lines.append(f"- {cat} --[{rel}]--> {code} (evidencia: {count})")
        return "\n".join(lines)
    except Exception:
        return "(Error obteniendo estructura axial)"


def _get_centrality_data(clients: ServiceClients, settings: AppSettings, project: str) -> str:
    """Obtiene datos de centralidad.

    Preferencia:
    1) Neo4j (si ya existen propiedades persistidas)
    2) Fallback: ejecutar PageRank via GraphAlgorithms (Postgres/NetworkX)
    """
    try:
        cypher = """
        MATCH (k:Codigo)
        WHERE k.project_id = $project AND k.score_centralidad IS NOT NULL
        RETURN k.nombre AS codigo, k.score_centralidad AS centralidad
        ORDER BY centralidad DESC
        LIMIT 10
        """
        with clients.neo4j.session() as session:
            result = session.run(cypher, project=project)
            records = list(result)
        
        if not records:
            raise ValueError("no neo4j centrality records")
        
        lines = []
        for r in records:
            lines.append(f"- **{r['codigo']}**: {r['centralidad']:.4f}")
        return "\n".join(lines)
    except Exception:
        # Fallback: compute from unified wrapper (may use Postgres+NetworkX).
        try:
            from .graph_algorithms import GraphAlgorithms

            ga = GraphAlgorithms(clients, settings)
            results = ga.pagerank(project_id=project, persist=False)
            if not results:
                return "(No hay datos de centralidad)"
            lines = [f"- **{r['nombre']}**: {float(r['score']):.4f}" for r in results[:10]]
            return "\n".join(lines)
        except Exception as e:
            return f"(Error: {e})"


def _get_communities_data(clients: ServiceClients, settings: AppSettings, project: str) -> tuple[str, int]:
    """Obtiene datos de comunidades.

    Preferencia:
    1) Neo4j (si ya existen propiedades persistidas)
    2) Fallback: ejecutar Louvain via GraphAlgorithms (Postgres/NetworkX)
    """
    try:
        cypher = """
        MATCH (k:Codigo)
        WHERE k.project_id = $project AND k.community_id IS NOT NULL
        RETURN k.community_id AS community, collect(k.nombre) AS codigos
        ORDER BY size(codigos) DESC
        LIMIT 5
        """
        with clients.neo4j.session() as session:
            result = session.run(cypher, project=project)
            records = list(result)
        
        if not records:
            raise ValueError("no neo4j community records")
        
        lines = []
        for r in records:
            codes = ", ".join(r['codigos'][:5])
            if len(r['codigos']) > 5:
                codes += f"... (+{len(r['codigos']) - 5} más)"
            lines.append(f"- Comunidad {r['community']}: {codes}")
        communities_count = len({r["community"] for r in records if r.get("community") is not None})
        return "\n".join(lines), communities_count
    except Exception:
        # Fallback: compute from unified wrapper.
        try:
            from .graph_algorithms import GraphAlgorithms

            ga = GraphAlgorithms(clients, settings)
            results = ga.louvain(project_id=project, persist=False)
            if not results:
                return "(No hay comunidades detectadas)", 0

            by_comm: dict[int, list[str]] = {}
            for r in results:
                cid = int(r.get("community_id", 0))
                by_comm.setdefault(cid, []).append(str(r.get("nombre") or ""))

            # Top 5 by size.
            top = sorted(by_comm.items(), key=lambda kv: len(kv[1]), reverse=True)[:5]
            lines = []
            for cid, names in top:
                preview = ", ".join(sorted(n for n in names if n)[:5])
                if len(names) > 5:
                    preview += f"... (+{len(names) - 5} más)"
                lines.append(f"- Comunidad {cid}: {preview}")

            return "\n".join(lines), len(by_comm)
        except Exception as e:
            return f"(Error: {e})", 0


def _get_graphrag_summaries(pg, project: str) -> str:
    """Obtiene síntesis de Discovery/GraphRAG."""
    try:
        sql = """
        SELECT ai_synthesis 
        FROM discovery_navigation_log 
        WHERE project_id = %s AND ai_synthesis IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 5
        """
        with pg.cursor() as cur:
            cur.execute(sql, (project,))
            rows = cur.fetchall()
        
        if not rows:
            return "(No hay síntesis de GraphRAG/Discovery)"
        
        lines = []
        for r in rows:
            summary = r[0][:300] + "..." if len(r[0]) > 300 else r[0]
            lines.append(f"- {summary}")
        return "\n".join(lines)
    except Exception:
        return "(No hay síntesis disponibles)"


# =============================================================================
# FUNCIONES PRINCIPALES DE GENERACIÓN
# =============================================================================

def generate_stage3_report(
    clients: ServiceClients,
    settings: AppSettings,
    project: str,
) -> Dict[str, Any]:
    """
    Genera informe doctoral para Etapa 3: Codificación Abierta.
    
    Returns:
        Dict con 'content' (Markdown) y metadatos
    """
    _logger.info("doctoral.stage3.generating", project=project)
    
    pg = clients.postgres
    
    # Recolectar datos
    stats = coding_stats(pg, project)
    interviews = list_interviews_summary(pg, project)
    
    codes_list = _get_codes_list(pg, project)
    saturation_data = _get_saturation_data(pg, project)
    memos = _get_memos(pg, project)
    recent_artifacts = _get_recent_report_artifacts(pg, project, max_items=10)
    
    # Construir prompt
    prompt = STAGE3_PROMPT.format(
        project=project,
        date=datetime.now().strftime("%Y-%m-%d"),
        total_fragments=stats.get("fragmentos_totales", 0),
        total_codes=stats.get("codigos_unicos", 0),
        total_interviews=len(interviews),
        codes_list=codes_list,
        saturation_data=saturation_data,
        memos=memos,
        recent_artifacts=recent_artifacts,
    )
    
    # Llamar LLM
    try:
        prompt_json = (
            prompt
            + "\n\nIMPORTANTE: Responde ÚNICAMENTE con un JSON válido (sin markdown, sin ```).\n"
            + "El JSON debe tener esta estructura exacta:\n\n"
            + "{\n"
            + "  \"content_markdown\": \"(Markdown del informe)\",\n"
            + "  \"memo_sintesis\": [\n"
            + "    {\"type\": \"OBSERVATION\", \"text\": \"...\", \"evidence_ids\": [1]},\n"
            + "    {\"type\": \"INTERPRETATION\", \"text\": \"...\"},\n"
            + "    {\"type\": \"HYPOTHESIS\", \"text\": \"...\"},\n"
            + "    {\"type\": \"NORMATIVE_INFERENCE\", \"text\": \"...\"}\n"
            + "  ]\n"
            + "}\n\n"
            + "REGLAS:\n"
            + "1. content_markdown debe ser el informe completo en Markdown.\n"
            + "2. memo_sintesis: 3-6 statements con estatus epistemológico.\n"
            + "3. PROHIBIDO: OBSERVATION sin evidence_ids no vacíos.\n"
        )

        response = clients.aoai.chat.completions.create(
            model=settings.azure.deployment_chat,
            messages=[
                {"role": "system", "content": "Eres un experto en metodología cualitativa doctoral. Respondes SOLO con JSON válido."},
                {"role": "user", "content": prompt_json},
            ],
            max_completion_tokens=3000,
        )
        raw = response.choices[0].message.content or ""
        parsed = _parse_llm_json(raw)
        if isinstance(parsed, dict) and (parsed.get("content_markdown") is not None):
            content = str(parsed.get("content_markdown") or "")
            memo_statements = _normalize_memo_sintesis(parsed.get("memo_sintesis"))
            structured = parsed.get("memo_sintesis") is not None
        else:
            content = raw
            memo_statements = []
            structured = False
    except Exception as e:
        _logger.error("doctoral.stage3.llm_error", error=str(e))
        content = f"# Error generando informe\n\nError: {e}"
        memo_statements = []
        structured = False
    
    # Agregar encabezado
    header = f"""# Informe de Avance Doctoral - Etapa 3: Codificación Abierta

**Proyecto:** {project}  
**Fecha de generación:** {datetime.now().strftime("%Y-%m-%d %H:%M")}  
**Generado por:** Sistema de Análisis Cualitativo Asistido por IA

---

"""
    
    content = _sanitize_llm_report_body(content)
    full_content = header + content

    # Append printable archive appendix (deterministic, not LLM-generated)
    full_content = full_content.rstrip() + "\n\n---\n\n" + _format_interviews_archive_appendix(interviews)
    
    _logger.info("doctoral.stage3.completed", project=project, chars=len(full_content))
    
    return {
        "stage": "stage3",
        "project": project,
        "content": full_content,
        "structured": bool(structured),
        "memo_statements": memo_statements,
        "generated_at": datetime.now().isoformat(),
        "stats": {
            "total_codes": stats.get("codigos_unicos", 0),
            "total_fragments": stats.get("fragmentos_totales", 0),
        }
    }


def generate_stage4_report(
    clients: ServiceClients,
    settings: AppSettings,
    project: str,
) -> Dict[str, Any]:
    """
    Genera informe doctoral para Etapa 4: Codificación Axial.
    
    Returns:
        Dict con 'content' (Markdown) y metadatos
    """
    _logger.info("doctoral.stage4.generating", project=project)
    
    pg = clients.postgres
    
    # Contar categorías y relaciones
    try:
        with pg.cursor() as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT categoria), COUNT(*) FROM analisis_axial WHERE project_id = %s",
                (project,)
            )
            row = cur.fetchone()
            total_categories = row[0] if row else 0
            total_relationships = row[1] if row else 0
    except Exception:
        total_categories = 0
        total_relationships = 0
    
    # Recolectar datos
    axial_structure = _get_axial_structure(pg, project)
    centrality_data = _get_centrality_data(clients, settings, project)
    communities_data, communities_count = _get_communities_data(clients, settings, project)
    graphrag_summaries = _get_graphrag_summaries(pg, project)
    memos = _get_memos(pg, project)
    recent_artifacts = _get_recent_report_artifacts(pg, project, max_items=10)
    
    # communities_count is derived from either persisted Neo4j properties or computed fallback.
    
    # Construir prompt
    prompt = STAGE4_PROMPT.format(
        project=project,
        date=datetime.now().strftime("%Y-%m-%d"),
        total_categories=total_categories,
        total_relationships=total_relationships,
        communities_count=communities_count,
        axial_structure=axial_structure,
        centrality_data=centrality_data,
        communities_data=communities_data,
        predictions="(Ver sección de Link Prediction)",
        graphrag_summaries=graphrag_summaries,
        memos=memos,
        recent_artifacts=recent_artifacts,
    )
    
    # Llamar LLM
    try:
        prompt_json = (
            prompt
            + "\n\nIMPORTANTE: Responde ÚNICAMENTE con un JSON válido (sin markdown, sin ```).\n"
            + "El JSON debe tener esta estructura exacta:\n\n"
            + "{\n"
            + "  \"content_markdown\": \"(Markdown del informe)\",\n"
            + "  \"memo_sintesis\": [\n"
            + "    {\"type\": \"OBSERVATION\", \"text\": \"...\", \"evidence_ids\": [1]},\n"
            + "    {\"type\": \"INTERPRETATION\", \"text\": \"...\"},\n"
            + "    {\"type\": \"HYPOTHESIS\", \"text\": \"...\"},\n"
            + "    {\"type\": \"NORMATIVE_INFERENCE\", \"text\": \"...\"}\n"
            + "  ]\n"
            + "}\n\n"
            + "REGLAS:\n"
            + "1. content_markdown debe ser el informe completo en Markdown.\n"
            + "2. memo_sintesis: 3-6 statements con estatus epistemológico.\n"
            + "3. PROHIBIDO: OBSERVATION sin evidence_ids no vacíos.\n"
        )

        response = clients.aoai.chat.completions.create(
            model=settings.azure.deployment_chat,
            messages=[
                {"role": "system", "content": "Eres un experto en metodología cualitativa doctoral. Respondes SOLO con JSON válido."},
                {"role": "user", "content": prompt_json},
            ],
            max_completion_tokens=3000,
        )
        raw = response.choices[0].message.content or ""
        parsed = _parse_llm_json(raw)
        if isinstance(parsed, dict) and (parsed.get("content_markdown") is not None):
            content = str(parsed.get("content_markdown") or "")
            memo_statements = _normalize_memo_sintesis(parsed.get("memo_sintesis"))
            structured = parsed.get("memo_sintesis") is not None
        else:
            content = raw
            memo_statements = []
            structured = False
    except Exception as e:
        _logger.error("doctoral.stage4.llm_error", error=str(e))
        content = f"# Error generando informe\n\nError: {e}"
        memo_statements = []
        structured = False
    
    # Agregar encabezado
    header = f"""# Informe de Avance Doctoral - Etapa 4: Codificación Axial

**Proyecto:** {project}  
**Fecha de generación:** {datetime.now().strftime("%Y-%m-%d %H:%M")}  
**Generado por:** Sistema de Análisis Cualitativo Asistido por IA

---

"""
    
    content = _sanitize_llm_report_body(content)
    full_content = header + content

    # Append printable archive appendix (deterministic, not LLM-generated)
    # Stage-4 prompt may omit operational details; keep appendix explicit.
    try:
        interviews = list_interviews_summary(pg, project)
    except Exception:
        interviews = []
    full_content = full_content.rstrip() + "\n\n---\n\n" + _format_interviews_archive_appendix(interviews)
    
    _logger.info("doctoral.stage4.completed", project=project, chars=len(full_content))
    
    return {
        "stage": "stage4",
        "project": project,
        "content": full_content,
        "structured": bool(structured),
        "memo_statements": memo_statements,
        "generated_at": datetime.now().isoformat(),
        "stats": {
            "total_categories": total_categories,
            "total_relationships": total_relationships,
            "communities_count": communities_count,
        }
    }
