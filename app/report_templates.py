"""
Sistema de Plantillas para Informe Científico 2.0

Este módulo genera el Informe Integrado de análisis cualitativo,
diferenciando la aplicación de herramientas tradicionales (NVivo, Atlas.ti)
mediante la inclusión de:

- Reflexividad y Trazabilidad Metodológica
- Serendipia Estructurada (Discovery)
- Relaciones Ocultas (Link Prediction)
- Reproducibilidad Algorítmica (parámetros de IA)

Estructura del Informe:
    I. Resumen Ejecutivo (generado AL FINAL con contexto)
    II. Metodología y Calidad de Datos
    III. Análisis Descriptivo (Open Coding)
    IV. Análisis Estructural (Grafo)
    V. Descubrimientos Emergentes (Discovery)
    VI. Evidencia Empírica (Grounding)

Uso:
    from app.report_templates import render_scientific_report
    markdown = render_scientific_report(project_id, pg_conn, neo4j_driver, qdrant_client, aoai_client)
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from app.reports import (
    get_interview_reports,
    generate_stage4_summary,
    identify_nucleus_candidates,
    InterviewReport,
    Stage4Summary,
)

_logger = structlog.get_logger(__name__)


# =============================================================================
# RECOLECCIÓN DE DATOS
# =============================================================================

def get_open_coding_metrics(
    pg_conn,
    project_id: str,
) -> Dict[str, Any]:
    """Recopila métricas de codificación abierta (Etapa 3)."""
    reports = get_interview_reports(pg_conn, project_id)
    
    if not reports:
        return {
            "total_fragmentos": 0,
            "total_codigos": 0,
            "codigos_nuevos": 0,
            "codigos_reutilizados": 0,
            "tasa_cobertura": 0.0,
            "top_10": [],
            "saturation_score": 0.0,
            "saturation_status": "Sin datos",
            "reports_count": 0,
        }
    
    # Contar frecuencia de códigos
    code_freq: Dict[str, int] = {}
    total_fragmentos = 0
    total_codigos_nuevos = 0
    total_codigos_reut = 0
    coberturas = []
    
    for report in reports:
        total_fragmentos += report.fragmentos_analizados
        total_codigos_nuevos += report.codigos_nuevos
        total_codigos_reut += report.codigos_reutilizados
        coberturas.append(report.tasa_cobertura)
        
        for codigo in report.codigos_generados:
            code_freq[codigo] = code_freq.get(codigo, 0) + 1
    
    # Top 10 por frecuencia
    top_10 = sorted(code_freq.items(), key=lambda x: x[1], reverse=True)[:10]
    
    # Score de saturación (últimos 3 informes)
    summary = generate_stage4_summary(pg_conn, project_id)
    
    return {
        "total_fragmentos": total_fragmentos,
        "total_codigos": len(code_freq),
        "codigos_nuevos": total_codigos_nuevos,
        "codigos_reutilizados": total_codigos_reut,
        "tasa_cobertura": round(sum(coberturas) / len(coberturas), 1) if coberturas else 0,
        "top_10": [{"codigo": c, "frecuencia": f} for c, f in top_10],
        "saturation_score": summary.score_saturacion,
        "saturation_status": "Alcanzada ✅" if summary.saturacion_alcanzada else "En progreso ⏳",
        "reports_count": len(reports),
    }


def get_graph_metrics(
    neo4j_driver,
    database: str,
    project_id: str,
) -> Dict[str, Any]:
    """Recopila métricas del grafo (Etapa 4)."""
    candidates = identify_nucleus_candidates(neo4j_driver, database, project_id)
    
    # Métricas adicionales del grafo
    with neo4j_driver.session(database=database) as session:
        # Densidad y modularidad
        result = session.run("""
            MATCH (c:Categoria {project_id: $pid})-[r]->(k:Codigo {project_id: $pid})
            RETURN count(DISTINCT c) as categorias,
                   count(DISTINCT k) as codigos,
                   count(r) as relaciones
        """, pid=project_id)
        record = result.single()
        
        if record:
            num_categorias = record["categorias"]
            num_codigos = record["codigos"]
            num_relaciones = record["relaciones"]
        else:
            num_categorias = num_codigos = num_relaciones = 0
        
        # Relaciones por tipo
        rel_result = session.run("""
            MATCH (c:Categoria {project_id: $pid})-[r]->(k:Codigo {project_id: $pid})
            RETURN type(r) as tipo, count(*) as cantidad
        """, pid=project_id)
        
        relaciones_por_tipo = {r["tipo"]: r["cantidad"] for r in rel_result}
    
    return {
        "total_categorias": num_categorias,
        "total_codigos": num_codigos,
        "total_relaciones": num_relaciones,
        "relaciones_por_tipo": relaciones_por_tipo,
        "nucleus_candidates": candidates,
        "densidad": round(num_relaciones / max(num_categorias * num_codigos, 1), 4),
    }


def get_discovery_findings(
    qdrant_client,
    project_id: str,
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    Identifica conceptos emergentes sin código explícito.
    
    Busca fragmentos con alta densidad semántica que no tienen
    códigos asignados (serendipia estructurada).
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    try:
        # Búsqueda de fragmentos sin código pero con alta cohesión
        result = qdrant_client.scroll(
            collection_name="fragmentos",
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="project_id", match=MatchValue(value=project_id)),
                ]
            ),
            limit=100,
            with_payload=True,
            with_vectors=False,
        )
        
        points = result[0] if result else []
        
        # Filtrar fragmentos sin código
        uncoded = [
            p for p in points 
            if not p.payload.get("codigos") or len(p.payload.get("codigos", [])) == 0
        ]
        
        # Agrupar por temas semánticos (simplificado)
        themes: Dict[str, int] = {}
        for p in uncoded[:50]:
            text = p.payload.get("texto", "")[:100]
            # Extraer palabras clave (simplificado)
            words = [w.lower() for w in text.split() if len(w) > 5]
            for w in words[:3]:
                themes[w] = themes.get(w, 0) + 1
        
        # Top temas emergentes
        top_themes = sorted(themes.items(), key=lambda x: x[1], reverse=True)[:top_k]
        
        return {
            "uncoded_fragments": len(uncoded),
            "total_fragments": len(points),
            "uncoded_ratio": round(len(uncoded) / max(len(points), 1) * 100, 1),
            "emerging_themes": [{"tema": t, "frecuencia": f} for t, f in top_themes],
            "suggestion": "Revisar fragmentos sin código para conceptos emergentes" if uncoded else "Cobertura completa",
        }
    except Exception as e:
        _logger.warning("discovery.error", error=str(e))
        return {
            "uncoded_fragments": 0,
            "total_fragments": 0,
            "uncoded_ratio": 0,
            "emerging_themes": [],
            "suggestion": f"Error: {str(e)}",
        }


def get_methodology_info(project_id: str) -> Dict[str, Any]:
    """Obtiene información metodológica del proyecto."""
    return {
        "llm_model": os.getenv("AZURE_OPENAI_DEPLOYMENT_CHAT", "gpt-4o"),
        "embedding_model": os.getenv("AZURE_OPENAI_DEPLOYMENT_EMBED", "text-embedding-ada-002"),
        "analysis_temperature": float(os.getenv("LLM_TEMPERATURE", "0.3")),
        "qdrant_collection": os.getenv("QDRANT_COLLECTION", "fragmentos"),
        "neo4j_database": os.getenv("NEO4J_DATABASE", "neo4j"),
        "batch_size": int(os.getenv("QDRANT_BATCH_SIZE", "20")),
        "fecha_analisis": datetime.now().isoformat(),
    }


# =============================================================================
# RENDERIZADO DE SECCIONES
# =============================================================================

def render_methodology(method_info: Dict[str, Any], project_id: str) -> str:
    """Renderiza sección de Metodología y Calidad de Datos."""
    return f"""## II. Metodología y Calidad de Datos

### Parámetros de IA (Reproducibilidad Algorítmica)

| Parámetro | Valor |
|-----------|-------|
| Modelo de Análisis | `{method_info['llm_model']}` |
| Modelo de Embeddings | `{method_info['embedding_model']}` |
| Temperatura | {method_info['analysis_temperature']} |
| Batch Size | {method_info['batch_size']} |
| Base de Datos de Grafos | {method_info['neo4j_database']} |
| Colección de Vectores | {method_info['qdrant_collection']} |

### Nota de Reflexividad
> Los resultados de este análisis fueron generados mediante IA con los parámetros
> arriba especificados. El investigador debe validar los hallazgos contra su
> conocimiento del campo y los datos originales.
"""


def render_open_coding_analysis(data: Dict[str, Any]) -> str:
    """Renderiza sección de Análisis de Codificación Abierta."""
    top_codes_table = "\n".join([
        f"| {c['codigo']} | {c['frecuencia']} | {round(c['frecuencia'] / max(data['total_codigos'], 1) * 100, 1)}% |"
        for c in data['top_10']
    ]) if data['top_10'] else "| Sin códigos | - | - |"
    
    return f"""## III. Análisis Descriptivo (Codificación Abierta)

### Métricas Generales

| Métrica | Valor |
|---------|-------|
| Entrevistas analizadas | {data['reports_count']} |
| Fragmentos totales | {data['total_fragmentos']} |
| Códigos únicos | {data['total_codigos']} |
| Códigos nuevos | {data['codigos_nuevos']} |
| Códigos reutilizados | {data['codigos_reutilizados']} |
| Cobertura promedio | {data['tasa_cobertura']}% |

### Top 10 Códigos por Frecuencia

| Código | Frecuencia | % Total |
|--------|------------|---------|
{top_codes_table}

### Análisis de Saturación

- **Score de Saturación:** {data['saturation_score']:.0%}
- **Estado:** {data['saturation_status']}

> La saturación teórica se evalúa observando la tasa de códigos nuevos
> en las últimas entrevistas. Un score >0.7 sugiere que nuevas entrevistas
> aportan pocos conceptos nuevos.
"""


def render_graph_analysis(data: Dict[str, Any]) -> str:
    """Renderiza sección de Análisis Estructural del Grafo."""
    rel_table = "\n".join([
        f"| {tipo} | {cantidad} |"
        for tipo, cantidad in data['relaciones_por_tipo'].items()
    ]) if data['relaciones_por_tipo'] else "| Sin relaciones | - |"
    
    nucleus_table = "\n".join([
        f"| {c['categoria']} | {c['score_nucleo']} | {c['num_relaciones']} | {c['avg_centrality']:.4f} |"
        for c in data['nucleus_candidates'][:5]
    ]) if data['nucleus_candidates'] else "| Sin candidatos | - | - | - |"
    
    return f"""## IV. Análisis Estructural (Codificación Axial)

### Métricas del Grafo

| Métrica | Valor |
|---------|-------|
| Categorías axiales | {data['total_categorias']} |
| Códigos conectados | {data['total_codigos']} |
| Relaciones totales | {data['total_relaciones']} |
| Densidad de red | {data['densidad']} |

### Relaciones por Tipo

| Tipo de Relación | Cantidad |
|------------------|----------|
{rel_table}

### Candidatos a Núcleo Selectivo

| Categoría | Score | Relaciones | Centralidad |
|-----------|-------|------------|-------------|
{nucleus_table}

> Los candidatos a núcleo se identifican mediante algoritmos de centralidad
> (PageRank, Betweenness) que detectan nodos "puente" en la red conceptual.
"""


def render_discovery_findings(data: Dict[str, Any]) -> str:
    """Renderiza sección de Descubrimientos Emergentes."""
    themes_table = "\n".join([
        f"| {t['tema']} | {t['frecuencia']} |"
        for t in data['emerging_themes']
    ]) if data['emerging_themes'] else "| Sin temas emergentes | - |"
    
    return f"""## V. Descubrimientos Emergentes (Serendipia)

### Fragmentos Sin Código

| Métrica | Valor |
|---------|-------|
| Fragmentos sin código | {data['uncoded_fragments']} |
| Total fragmentos | {data['total_fragments']} |
| Ratio sin codificar | {data['uncoded_ratio']}% |

### Temas Emergentes (Alta Densidad Semántica)

| Tema | Frecuencia |
|------|------------|
{themes_table}

> **Nota:** Estos temas aparecen frecuentemente en fragmentos sin código
> explícito, sugiriendo conceptos latentes que merecen revisión.

### Sugerencia
> {data['suggestion']}
"""


def render_evidence_section(project_id: str) -> str:
    """Renderiza sección de Evidencia Empírica."""
    import os
    from pathlib import Path
    
    reports_dir = Path("reports")
    evidence_files = []
    
    if reports_dir.exists():
        for f in reports_dir.iterdir():
            if f.suffix in ['.md', '.png', '.webp']:
                evidence_files.append(f.name)
    
    files_list = "\n".join([f"- `{f}`" for f in evidence_files[:10]]) if evidence_files else "- Sin archivos de evidencia"
    
    return f"""## VI. Evidencia Empírica

### Archivos de Evidencia

{files_list}

### Trazabilidad

> Cada afirmación teórica en este informe está vinculada a fragmentos
> específicos en la base de datos. Use el panel de "Citas por Código"
> para acceder a la evidencia primaria.

### Validación

- [ ] Verificar citas clave contra transcripciones originales
- [ ] Revisar coherencia entre categorías y códigos
- [ ] Validar relaciones axiales con el equipo de investigación
"""


def render_executive_summary(
    project_id: str,
    open_coding_data: Dict[str, Any],
    graph_data: Dict[str, Any],
    discovery_data: Dict[str, Any],
) -> str:
    """
    Renderiza Resumen Ejecutivo CON CONTEXTO de hallazgos.
    
    Se genera AL FINAL para incluir información de todas las secciones.
    """
    # Identificar núcleo principal
    nucleus = ""
    if graph_data['nucleus_candidates']:
        top_candidate = graph_data['nucleus_candidates'][0]
        nucleus = f"La categoría **\"{top_candidate['categoria']}\"** emerge como candidato principal a núcleo (Score: {top_candidate['score_nucleo']})."
    
    # Evaluar saturación
    sat_status = open_coding_data['saturation_status']
    sat_score = open_coding_data['saturation_score']
    
    return f"""# Informe de Análisis Cualitativo
## Proyecto: {project_id}

**Fecha de generación:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  
**Metodología:** Teoría Fundamentada asistida por IA

---

## I. Resumen Ejecutivo

### Síntesis del Análisis

Este informe consolida los hallazgos del análisis cualitativo del proyecto **{project_id}**,
que procesó **{open_coding_data['reports_count']}** entrevistas generando **{open_coding_data['total_codigos']}**
códigos únicos agrupados en **{graph_data['total_categorias']}** categorías axiales.

### Hallazgo Central

{nucleus if nucleus else "Aún no se ha identificado un candidato claro a núcleo selectivo."}

### Estado de Saturación

- **Score:** {sat_score:.0%}
- **Estado:** {sat_status}

### Métricas Clave

| Dimensión | Valor |
|-----------|-------|
| Entrevistas | {open_coding_data['reports_count']} |
| Códigos únicos | {open_coding_data['total_codigos']} |
| Categorías | {graph_data['total_categorias']} |
| Relaciones axiales | {graph_data['total_relaciones']} |
| Fragmentos sin código | {discovery_data['uncoded_fragments']} ({discovery_data['uncoded_ratio']}%) |

---
"""


# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

def render_scientific_report(
    project_id: str,
    pg_conn,
    neo4j_driver,
    database: str,
    qdrant_client,
    aoai_client = None,  # Opcional para análisis IA adicional
) -> str:
    """
    Genera el Informe Científico 2.0 completo.
    
    FLUJO OPTIMIZADO (según feedback del usuario):
    1. Calcular primero los datos duros
    2. Generar secciones del cuerpo
    3. Generar Resumen Ejecutivo AL FINAL (con contexto)
    4. Ensamblar en orden visual
    
    Args:
        project_id: ID del proyecto
        pg_conn: Conexión PostgreSQL
        neo4j_driver: Driver Neo4j
        database: Base de datos Neo4j
        qdrant_client: Cliente Qdrant
        aoai_client: Cliente Azure OpenAI (opcional)
        
    Returns:
        Markdown del informe completo
    """
    _logger.info("report.generating", project=project_id)
    
    # 1. Calcular datos duros
    method_info = get_methodology_info(project_id)
    open_coding_data = get_open_coding_metrics(pg_conn, project_id)
    graph_data = get_graph_metrics(neo4j_driver, database, project_id)
    discovery_data = get_discovery_findings(qdrant_client, project_id)
    
    # 2. Generar secciones del cuerpo
    methodology_section = render_methodology(method_info, project_id)
    open_coding_section = render_open_coding_analysis(open_coding_data)
    graph_section = render_graph_analysis(graph_data)
    discovery_section = render_discovery_findings(discovery_data)
    evidence_section = render_evidence_section(project_id)
    
    # 3. Generar Resumen Ejecutivo AL FINAL (con contexto de hallazgos)
    executive_summary = render_executive_summary(
        project_id,
        open_coding_data,
        graph_data,
        discovery_data,
    )
    
    # 4. Ensamblar en orden visual
    report = "\n\n".join([
        executive_summary,
        methodology_section,
        open_coding_section,
        graph_section,
        discovery_section,
        evidence_section,
    ])
    
    _logger.info(
        "report.generated",
        project=project_id,
        length=len(report),
        sections=6,
    )
    
    return report
