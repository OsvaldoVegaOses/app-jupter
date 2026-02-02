"""
Generación de reportes de análisis cualitativo.

Este módulo genera reportes integrales que combinan datos de las tres
bases de datos para documentar el análisis realizado.

Funciones principales:
    - graph_outline(): Estructura teórica desde Neo4j
    - category_citations(): Citas representativas por categoría
    - export_cross_tabs(): Exportar tablas cruzadas a CSV
    - analysis_snapshot(): Resumen de estado del análisis
    - build_integrated_report(): Reporte Markdown completo

Salidas generadas:
    - informes/informe_integrado.md: Documento principal
    - informes/anexos/*.csv: Tablas cruzadas exportadas
    - informes/report_manifest.json: Metadatos y checksums

Características:
    - Anonimización opcional de fuentes (P01, P02, etc.)
    - Checksums SHA256 para verificación
    - Integración con análisis de núcleo y saturación

Example:
    >>> from app.reporting import build_integrated_report
    >>> result = build_integrated_report(
    ...     clients, settings,
    ...     categoria_nucleo="resiliencia_comunitaria",
    ...     prompt_nucleo="adaptación climática"
    ... )
    >>> print(result["report_path"])
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import structlog

from .clients import ServiceClients
from .nucleus import nucleus_report
from .settings import AppSettings
from .transversal import pg_cross_tab
from .validation import saturation_curve
from .postgres_block import quotes_for_category, member_checking_packets

_logger = structlog.get_logger()


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _compute_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _compute_file_hash(path: Path) -> str:
    return _compute_hash(path.read_bytes())


def _json_default(obj: Any):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def graph_outline(clients: ServiceClients, settings: AppSettings, project: Optional[str] = None) -> List[Dict[str, Any]]:
    query = """
        MATCH (cat:Categoria {project_id: $project_id})
        OPTIONAL MATCH (cat)-[rel:REL]->(cod:Codigo {project_id: $project_id})
        OPTIONAL MATCH (cod)<-[:TIENE_CODIGO]-(f:Fragmento {project_id: $project_id})
        WITH cat, rel, cod, f
        ORDER BY cod.nombre
        RETURN cat.nombre AS categoria,
               collect(DISTINCT cod.nombre) AS codigos,
               collect(DISTINCT rel.tipo) AS tipos_relacion,
               collect({codigo: cod.nombre, tipo: rel.tipo, evidencia: rel.evidencia}) AS relaciones,
               count(DISTINCT f) AS citas
        ORDER BY categoria
    """
    project_id = project or "default"
    with clients.neo4j.session(database=settings.neo4j.database) as session:
        data = session.run(query, project_id=project_id).data()
    outline: List[Dict[str, Any]] = []
    for row in data:
        outline.append(
            {
                "categoria": row.get("categoria"),
                "codigos": [c for c in row.get("codigos", []) if c],
                "tipos_relacion": [t for t in row.get("tipos_relacion", []) if t],
                "relaciones": [rel for rel in row.get("relaciones", []) if rel.get("codigo")],
                "citas": row.get("citas", 0),
            }
        )
    return outline


def anonymize_source(source: Optional[str], mapping: Dict[Optional[str], str]) -> str:
    if source in mapping:
        return mapping[source]
    alias = f"P{len(mapping) + 1:02d}"
    mapping[source] = alias
    return alias


def category_citations(
    clients: ServiceClients,
    categoria: str,
    *,
    project: Optional[str] = None,
    limit: int = 5,
    anonymize: bool = True,
) -> List[Dict[str, Any]]:
    quotes = quotes_for_category(clients.postgres, categoria, project or "default", limite=limit)
    mapping: Dict[Optional[str], str] = {}
    sanitized: List[Dict[str, Any]] = []
    for quote in quotes:
        fuente = quote.get("fuente")
        alias = anonymize_source(fuente, mapping) if anonymize else fuente or "(sin fuente)"
        sanitized.append(
            {
                "fragmento_id": quote.get("fragmento_id"),
                "codigo": quote.get("codigo"),
                "cita": quote.get("cita"),
                "fuente": alias,
                "archivo": quote.get("archivo"),
            }
        )
    return sanitized


def export_cross_tabs(
    clients: ServiceClients,
    *,
    dimensions: Sequence[str],
    categoria: Optional[str],
    limit: int,
    directory: Path,
    project: Optional[str] = None,
) -> List[Dict[str, Any]]:
    exports: List[Dict[str, Any]] = []
    _ensure_directory(directory)
    for dimension in dimensions:
        payload = pg_cross_tab(
            clients,
            dimension,
            categoria=categoria,
            project=project,
            limit=limit,
            refresh=False,
        )
        filename = f"cross_tab_{dimension}.csv"
        target = directory / filename
        rows = payload.get("rows", [])
        with target.open("w", encoding="utf-8", newline="") as fh:
            headers = ["categoria", "grupo", "entrevistas", "codigos", "relaciones"]
            fh.write(",".join(headers) + "\n")
            for row in rows:
                values = [
                    str(row.get("categoria", "")),
                    str(row.get("grupo", "")),
                    str(row.get("entrevistas", 0)),
                    str(row.get("codigos", 0)),
                    str(row.get("relaciones", 0)),
                ]
                fh.write(",".join(value.replace(",", ";") for value in values) + "\n")
        exports.append(
            {
                "dimension": dimension,
                "file": str(target.relative_to(directory.parent)),
                "rows": len(rows),
                "hash": _compute_file_hash(target),
            }
        )
    return exports


def analysis_snapshot(clients: ServiceClients, project: Optional[str] = None) -> Dict[str, Any]:
    project_id = project or "default"
    sql_statements: List[Tuple[str, str]] = [
        ("fragmentos", "SELECT COUNT(*) FROM entrevista_fragmentos WHERE project_id = %s"),
        ("codigos", "SELECT COUNT(*) FROM analisis_codigos_abiertos WHERE project_id = %s"),
        ("categorias", "SELECT COUNT(DISTINCT categoria) FROM analisis_axial WHERE project_id = %s"),
    ]
    snapshot: Dict[str, Any] = {}
    with clients.postgres.cursor() as cur:
        for key, query in sql_statements:
            cur.execute(query, (project_id,))
            row = cur.fetchone()
            snapshot[key] = row[0] if row else 0
    snapshot["miembros"] = len(member_checking_packets(clients.postgres, project=project_id, limit=10))
    return snapshot


def build_integrated_report(
    clients: ServiceClients,
    settings: AppSettings,
    *,
    project: Optional[str] = None,
    categoria_nucleo: Optional[str] = None,
    prompt_nucleo: Optional[str] = None,
    quote_limit: int = 5,
    cross_tab_limit: int = 50,
    dimensions: Sequence[str] = ("rol", "genero", "periodo"),
    output_path: Path = Path("informes/informe_integrado.md"),
    annex_dir: Path = Path("informes/anexos"),
    manifest_path: Path = Path("informes/report_manifest.json"),
) -> Dict[str, Any]:
    project_id = project or "default"
    logger = _logger.bind(action="report.build", output=str(output_path), project=project_id)
    outline = graph_outline(clients, settings, project=project_id)

    citas_por_categoria: Dict[str, List[Dict[str, Any]]] = {}
    for entry in outline:
        categoria = entry.get("categoria")
        if not categoria:
            continue
        citas_por_categoria[categoria] = category_citations(
            clients,
            categoria,
            project=project_id,
            limit=quote_limit,
        )

    annex_info = export_cross_tabs(
        clients,
        dimensions=dimensions,
        categoria=None,
        limit=cross_tab_limit,
        directory=annex_dir,
        project=project_id,
    )

    nucleus_payload = None
    if categoria_nucleo:
        nucleus_payload = nucleus_report(
            clients,
            settings,
            categoria=categoria_nucleo,
            prompt=prompt_nucleo,
            project=project_id,
        )

    saturation_payload = saturation_curve(clients.postgres, project=project_id)
    snapshot = analysis_snapshot(clients, project=project_id)

    timestamp = dt.datetime.utcnow().isoformat() + "Z"

    markdown_lines: List[str] = []
    markdown_lines.append("# Informe Integrado de Análisis Cualitativo")
    markdown_lines.append("")
    markdown_lines.append(f"Generado: {timestamp}")
    markdown_lines.append("")
    markdown_lines.append("## 1. Resumen Ejecutivo")
    markdown_lines.append("")
    markdown_lines.append(
        f"- Fragmentos analizados: {snapshot.get('fragmentos', 0)} | Códigos abiertos: {snapshot.get('codigos', 0)} | Categorías axiales: {snapshot.get('categorias', 0)}"
    )
    plateau = saturation_payload.get("plateau", {})
    markdown_lines.append(
        f"- Saturación (ventana {plateau.get('window', 0)}): nuevos códigos {plateau.get('nuevos_codigos', [])} → plateau={'sí' if plateau.get('plateau') else 'no'}"
    )
    if nucleus_payload:
        candidate = nucleus_payload.get("centrality", {}).get("candidate") or {}
        nucleus_name = candidate.get("nombre") or categoria_nucleo
        markdown_lines.append(f"- Núcleo propuesto: {nucleus_name} (rank {candidate.get('rank', 'NA')})")
    markdown_lines.append("")
    # --- Etapa 5: Núcleo (incluye Storyline GraphRAG si existe) ---
    markdown_lines.append("## 2. Núcleo (Etapa 5)")
    markdown_lines.append("")
    if nucleus_payload:
        memo = nucleus_payload.get("memo") or ""
        llm_summary = nucleus_payload.get("llm_summary") or nucleus_payload.get("summary") or ""
        
        markdown_lines.append("**Memo (investigador):**")
        markdown_lines.append("")
        markdown_lines.append(memo if memo else "_(sin memo)_")
        markdown_lines.append("")
        markdown_lines.append("**Propuesta / Resumen (IA):**")
        markdown_lines.append("")
        markdown_lines.append(llm_summary if llm_summary else "_(sin resumen)_")
        markdown_lines.append("")

            # Sección dedicada a GraphRAG Storyline (versión PRO)
        storyline = nucleus_payload.get("storyline_graphrag") or nucleus_payload.get("graphrag")
        summary_metrics = nucleus_payload.get("summary_metrics")
        exploratory = nucleus_payload.get("graphrag_exploratory")
        if storyline and isinstance(storyline, dict):
            markdown_lines.append("### Storyline (GraphRAG)")
            markdown_lines.append("")
            # Smart Detection de Rechazo/Abstención
            is_grounded = storyline.get("is_grounded", False)
            if not is_grounded:
                markdown_lines.append("⚠️ GraphRAG se abstuvo por falta de evidencia suficiente o señal débil.")
                rejection = storyline.get("rejection")
                if rejection:
                    if isinstance(rejection, dict):
                        markdown_lines.append(f"- **Razón:** {rejection.get('reason')}")
                        markdown_lines.append(f"- **Sugerencia:** {rejection.get('suggestion')}")
                    else:
                        markdown_lines.append(f"- {str(rejection)}")
                markdown_lines.append("")

            graph_summary = storyline.get("answer") or storyline.get("graph_summary")
            if graph_summary:
                markdown_lines.append("**Inferencia Estructural / Storyline:**")
                markdown_lines.append("")
                markdown_lines.append(str(graph_summary))
                markdown_lines.append("")

            # Auditoría Cuantitativa del Subgrafo
            central_nodes = storyline.get("nodes") or []
            if central_nodes:
                markdown_lines.append("**Nodos Clave (Auditoría Cuantitativa):**")
                markdown_lines.append("")
                for n in central_nodes[:15]:
                    name = n.get("label") or n.get("id")
                    score = n.get("score")
                    try:
                        score_fmt = f"{float(score):.3f}"
                    except Exception:
                        score_fmt = str(score)
                    markdown_lines.append(f"- {name} (score={score_fmt})")
                markdown_lines.append("")

            evidence = storyline.get("evidence") or []
            if evidence:
                markdown_lines.append("**Evidencia Citable (Grounding):**")
                markdown_lines.append("")
                for ev in evidence[:20]:
                    doc = ev.get("source_doc") or ev.get("archivo") or "desconocido"
                    frag = ev.get("fragment_id") or ev.get("id")
                    rel = ev.get("relevance")
                    text = (ev.get("quote") or ev.get("snippet") or ev.get("texto") or "").strip().replace("\n", " ")
                    markdown_lines.append(f"- ({doc}) frag={frag} rel={rel}: {text}")
                markdown_lines.append("")

            confidence = storyline.get("confidence")
            if confidence:
                level = confidence.get("level") if isinstance(confidence, dict) else confidence
                markdown_lines.append(f"**Nivel de Confianza:** {level}")
                markdown_lines.append("")
            # Mostrar resumen de métricas de auditoría si existe
            if summary_metrics and isinstance(summary_metrics, dict):
                markdown_lines.append("**Audit Summary (métricas):**")
                markdown_lines.append("")
                markdown_lines.append(summary_metrics.get("text_summary") or "_(sin summary metrics)_")
                markdown_lines.append("")
            # Mostrar Exploratory Scan si existe
            if exploratory and isinstance(exploratory, dict):
                markdown_lines.append("### Exploratory Scan (fallback)")
                markdown_lines.append("")
                expl_answer = exploratory.get("answer") or exploratory.get("graph_summary")
                if expl_answer:
                    markdown_lines.append("**Exploratory (no causal):**")
                    markdown_lines.append("")
                    markdown_lines.append(str(expl_answer))
                    markdown_lines.append("")
                expl_clusters = exploratory.get("clusters") or exploratory.get("top_clusters")
                if expl_clusters:
                    markdown_lines.append("**Clusters detectados:**")
                    for c in expl_clusters[:10]:
                        markdown_lines.append(f"- {c}")
                    markdown_lines.append("")
                # Indicar huecos de datos si provistos
                gaps = exploratory.get("gaps") or exploratory.get("huecos")
                if gaps:
                    markdown_lines.append("**Huecos de datos / Qué falta para hipótesis:**")
                    for g in gaps[:10]:
                        markdown_lines.append(f"- {g}")
                    markdown_lines.append("")
    else:
        markdown_lines.append("_(No hay datos del núcleo disponibles)_")
        markdown_lines.append("")

    markdown_lines.append("## 3. Estructura Teórica (Neo4j)")
    markdown_lines.append("")
    for entry in outline:
        categoria = entry.get("categoria") or "(sin nombre)"
        markdown_lines.append(f"### {categoria}")
        codigos = entry.get("codigos", [])
        if codigos:
            markdown_lines.append(f"- **Códigos vinculados**: {', '.join(codigos)}")
        tipos = entry.get("tipos_relacion", [])
        if tipos:
            markdown_lines.append(f"- **Tipos de relación**: {', '.join(sorted(tipos))}")
        relaciones = entry.get("relaciones", [])
        if relaciones:
            evidencias = []
            for rel in relaciones:
                if rel.get("evidencia"):
                    evidencias.extend(rel.get("evidencia") or [])
            evidencias = sorted(set(evidencias))
            if evidencias:
                markdown_lines.append(f"- **Evidence-at-hand**: {', '.join(evidencias)}")
        citas = citas_por_categoria.get(categoria, [])
        if citas:
            markdown_lines.append("- **Citas representativas**:")
            for cita in citas:
                markdown_lines.append(
                    f"  - > {cita.get('cita', '').strip()} (#{cita.get('fragmento_id')}, {cita.get('fuente')})"
                )
        markdown_lines.append("")

    markdown_lines.append("## 3. Anexos y Tablas (PostgreSQL)")
    markdown_lines.append("")
    for annex in annex_info:
        markdown_lines.append(
            f"- [{annex['dimension']}]: {annex['file']} (hash `{annex['hash'][:12]}`)")
    markdown_lines.append("")

    markdown_lines.append("## 4. Validación y Limitaciones")
    markdown_lines.append("")
    markdown_lines.append(
        "- Saturación cuantitativa y semántica registrada en `validation curve|outliers`. Referencias cruzadas disponibles en manifiesto."
    )
    markdown_lines.append(
        "- Revisión por pares: utilice los fragmento_id en cada categoría para auditar evidencia en PostgreSQL/Qdrant."
    )

    content = "\n".join(markdown_lines) + "\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    report_hash = _compute_file_hash(output_path)

    manifest = {
        "generated_at": timestamp,
        "report": {
            "path": str(output_path),
            "hash": report_hash,
            "categories": len(outline),
            "quotes_per_category": quote_limit,
        },
        "nucleus": nucleus_payload,
        "nucleus_storyline": (nucleus_payload or {}).get("storyline_graphrag") if nucleus_payload else None,
        "nucleus_summary_metrics": (nucleus_payload or {}).get("summary_metrics") if nucleus_payload else None,
        "snapshot": snapshot,
        "saturation": saturation_payload,
        "annexes": annex_info,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )

    logger.info("report.build.complete", report=str(output_path), hash=report_hash)
    return {
        "report_path": str(output_path),
        "report_hash": report_hash,
        "manifest_path": str(manifest_path),
        "annexes": annex_info,
    }
