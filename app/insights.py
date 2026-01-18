"""
Módulo de Extracción de Insights.

Implementa el muestreo teórico automatizado según la Teoría Fundamentada.
Los insights son hipótesis abductivas que sugieren nuevas búsquedas
basándose en los resultados de análisis previos.

Tipos de Insights:
    - explore: Sugerir explorar un concepto poco saturado
    - validate: Validar una relación predicha en fragmentos
    - saturate: Buscar más evidencia para una categoría
    - merge: Sugerir fusión de códigos similares

Fuentes:
    - Discovery: Síntesis IA y códigos sugeridos
    - Link Prediction: Predicciones con alto score
    - Codificación: Códigos con baja frecuencia
    - Informes: Brechas de saturación
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import structlog

from psycopg2.extensions import connection as PGConnection

from app.postgres_block import save_insight, list_codes_summary, list_candidate_codes_summary

_logger = structlog.get_logger(__name__)


def extract_insights_from_discovery(
    pg: PGConnection,
    *,
    project: str,
    busqueda_id: str,
    positivos: List[str],
    ai_synthesis: Optional[str],
    codigos_sugeridos: Optional[List[str]],
    fragments_count: int,
) -> List[int]:
    """
    Extrae insights desde resultados de Discovery.
    
    Reglas de extracción:
    1. Si hay códigos sugeridos pero no existen → explorar
    2. Si la síntesis menciona relaciones → validar
    3. Si hay pocos fragmentos → saturar
    
    Returns:
        Lista de IDs de insights creados
    """
    insights_created = []
    
    try:
        # 1. Códigos sugeridos que no existen en el proyecto
        if codigos_sugeridos:
            existing_codes = {c["codigo"].lower() for c in list_codes_summary(pg, project, limit=100)}
            
            for codigo in codigos_sugeridos[:5]:  # Limitar a 5
                if codigo.lower() not in existing_codes:
                    insight_id = save_insight(
                        pg,
                        project=project,
                        source_type="discovery",
                        source_id=busqueda_id,
                        insight_type="explore",
                        content=f"Discovery sugiere nuevo código: '{codigo}'. Explorar para confirmar emergencia.",
                        suggested_query={
                            "positivos": [codigo] + positivos[:2],
                            "action": "search",
                            "min_fragments": 5,
                        },
                        priority=0.7,
                    )
                    insights_created.append(insight_id)
        
        # 2. Si la síntesis es rica, sugerir profundizar
        if ai_synthesis and len(ai_synthesis) > 200:
            # Extraer conceptos clave de la síntesis (simplificado)
            words = [w.strip().lower() for w in ai_synthesis.split() if len(w) > 8]
            unique_concepts = list(set(words))[:3]
            
            if unique_concepts and positivos:
                insight_id = save_insight(
                    pg,
                    project=project,
                    source_type="discovery",
                    source_id=busqueda_id,
                    insight_type="explore",
                    content=f"Síntesis rica para '{positivos[0]}'. Profundizar en relaciones emergentes.",
                    suggested_query={
                        "positivos": positivos,
                        "action": "analyze",
                        "context": "axial_coding",
                    },
                    priority=0.6,
                )
                insights_created.append(insight_id)
        
        # 3. Si hay pocos fragmentos, sugerir ampliar búsqueda
        if fragments_count < 3 and positivos:
            insight_id = save_insight(
                pg,
                project=project,
                source_type="discovery",
                source_id=busqueda_id,
                insight_type="saturate",
                content=f"Búsqueda '{positivos[0]}' retornó solo {fragments_count} fragmentos. Ampliar criterios.",
                suggested_query={
                    "positivos": positivos,
                    "action": "search",
                    "expand_semantic": True,
                },
                priority=0.5,
            )
            insights_created.append(insight_id)
        
        _logger.info(
            "insights.discovery.extracted",
            project=project,
            busqueda_id=busqueda_id,
            count=len(insights_created)
        )
        
    except Exception as e:
        _logger.error("insights.discovery.error", error=str(e))
    
    return insights_created


def extract_insights_from_link_prediction(
    pg: PGConnection,
    *,
    project: str,
    predictions: List[Dict[str, Any]],
) -> List[int]:
    """
    Extrae insights desde predicciones de enlaces.
    
    Reglas:
    1. Predicciones con score > 0.7 → validar en fragmentos
    2. Predicciones confirmadas → consolidar relación axial
    
    Returns:
        Lista de IDs de insights creados
    """
    insights_created = []
    
    try:
        for pred in predictions[:10]:  # Limitar a 10 predicciones
            source = pred.get("source", pred.get("from", ""))
            target = pred.get("target", pred.get("to", ""))
            score = pred.get("score", pred.get("probability", 0))
            
            if not source or not target:
                continue
            
            if score >= 0.7:
                insight_id = save_insight(
                    pg,
                    project=project,
                    source_type="link_prediction",
                    source_id=f"{source}___{target}",
                    insight_type="validate",
                    content=f"Link Prediction sugiere relación: {source} → {target} (score: {score:.2f}). Buscar evidencia.",
                    suggested_query={
                        "positivos": [source, target],
                        "action": "search",
                        "find_cooccurrence": True,
                    },
                    priority=min(score, 0.9),  # Usar score como prioridad
                )
                insights_created.append(insight_id)
        
        _logger.info(
            "insights.link_prediction.extracted",
            project=project,
            count=len(insights_created)
        )
        
    except Exception as e:
        _logger.error("insights.link_prediction.error", error=str(e))
    
    return insights_created


def extract_insights_from_coding(
    pg: PGConnection,
    *,
    project: str,
    min_frequency: int = 2,
) -> List[int]:
    """
    Extrae insights desde análisis de codificación.
    
    Reglas:
    1. Códigos con frecuencia < min_frequency → explorar
    2. Códigos con muchas variantes → sugerir merge
    
    Returns:
        Lista de IDs de insights creados
    """
    insights_created = []
    
    try:
        codes = list_codes_summary(pg, project, limit=50)

        # Fallback: si aún no hay códigos definitivos (analisis_codigos_abiertos),
        # intentar generar insights desde la bandeja de candidatos.
        if not codes:
            candidate_codes = list_candidate_codes_summary(pg, project, limit=50)
            if candidate_codes:
                _logger.info(
                    "insights.coding.fallback_candidates",
                    project=project,
                    count=len(candidate_codes),
                )
                codes = candidate_codes
        
        # 1. Códigos poco frecuentes
        low_freq_codes = [c for c in codes if c.get("citas", 0) < min_frequency]
        
        for code in low_freq_codes[:5]:
            codigo = code["codigo"]
            freq = code.get("citas", 0)
            
            insight_id = save_insight(
                pg,
                project=project,
                source_type="coding",
                source_id=codigo,
                insight_type="saturate",
                content=f"Código '{codigo}' tiene solo {freq} cita(s). Buscar más evidencia para saturar.",
                suggested_query={
                    "positivos": [codigo],
                    "action": "search",
                    "min_fragments": 5,
                },
                priority=0.6,
            )
            insights_created.append(insight_id)
        
        # 2. Detectar posibles duplicados (códigos muy similares)
        code_names = [c["codigo"] for c in codes]
        for i, code1 in enumerate(code_names):
            for code2 in code_names[i+1:]:
                # Similitud básica: mismo prefijo o sufijo
                if (code1.split("_")[0] == code2.split("_")[0] or 
                    code1.split("_")[-1] == code2.split("_")[-1]):
                    if len(code1) > 5 and len(code2) > 5:
                        insight_id = save_insight(
                            pg,
                            project=project,
                            source_type="coding",
                            source_id=f"{code1}___{code2}",
                            insight_type="merge",
                            content=f"Códigos similares detectados: '{code1}' y '{code2}'. Considerar fusión.",
                            suggested_query={
                                "codes": [code1, code2],
                                "action": "compare",
                            },
                            priority=0.4,
                        )
                        insights_created.append(insight_id)
                        break  # Solo un insight de merge por código
        
        _logger.info(
            "insights.coding.extracted",
            project=project,
            count=len(insights_created)
        )
        
    except Exception as e:
        _logger.error("insights.coding.error", error=str(e))
    
    return insights_created


def extract_insights_from_report(
    pg: PGConnection,
    *,
    project: str,
    stage: str,
    stats: Dict[str, Any],
) -> List[int]:
    """
    Extrae insights desde informes doctorales.
    
    Reglas:
    1. Baja cobertura de fragmentos → saturar
    2. Pocas categorías axiales → explorar relaciones
    
    Returns:
        Lista de IDs de insights creados
    """
    insights_created = []
    
    try:
        total_fragments = stats.get("total_fragments", 0)
        total_codes = stats.get("total_codes", 0)
        
        # 1. Si hay pocos códigos relativos a fragmentos
        if total_fragments > 50 and total_codes < 10:
            insight_id = save_insight(
                pg,
                project=project,
                source_type="report",
                source_id=f"{stage}_{datetime.now().strftime('%Y%m%d')}",
                insight_type="explore",
                content=f"Ratio bajo: {total_codes} códigos para {total_fragments} fragmentos. Intensificar codificación.",
                suggested_query={
                    "action": "analyze",
                    "target": "uncoded_fragments",
                },
                priority=0.8,
            )
            insights_created.append(insight_id)
        
        # 2. Para Stage 4, verificar relaciones
        if stage == "stage4":
            relationships = stats.get("total_relationships", 0)
            if relationships < 5 and total_codes > 5:
                insight_id = save_insight(
                    pg,
                    project=project,
                    source_type="report",
                    source_id=f"stage4_{datetime.now().strftime('%Y%m%d')}",
                    insight_type="explore",
                    content=f"Solo {relationships} relaciones axiales para {total_codes} códigos. Usar Link Prediction.",
                    suggested_query={
                        "action": "link_prediction",
                        "min_score": 0.6,
                    },
                    priority=0.7,
                )
                insights_created.append(insight_id)
        
        _logger.info(
            "insights.report.extracted",
            project=project,
            stage=stage,
            count=len(insights_created)
        )
        
    except Exception as e:
        _logger.error("insights.report.error", error=str(e))
    
    return insights_created
