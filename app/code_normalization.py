"""
Normalización y detección de duplicados de códigos.

Este módulo implementa fuzzy matching para detectar códigos similares
y prevenir fragmentación del grafo de codificación.

Funciones principales:
    - normalize_code(): Normaliza texto (tildes, espacios, etc.)
    - find_similar_codes(): Detecta códigos similares usando rapidfuzz
    - suggest_code_merge(): Sugiere fusión de códigos duplicados

Estrategia Pre-Hoc:
    Interceptar ANTES de insertar códigos para detectar:
    - 'organizacion' vs 'organización' (tildes)
    - 'enfoque_de_genero' vs 'enfoque_genero' (preposición)

Example:
    >>> from app.code_normalization import find_similar_codes
    >>> existing = ['organización', 'territorio', 'género']
    >>> similar = find_similar_codes('organizacion', existing, threshold=0.85)
    >>> # [('organización', 0.92)]
"""

from __future__ import annotations

import unicodedata
import re
from typing import List, Tuple, Optional, Dict, Any

import structlog

# Intentar importar rapidfuzz, con fallback a difflib
try:
    from rapidfuzz import fuzz
    from rapidfuzz import process as fuzz_process
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    from difflib import SequenceMatcher

_logger = structlog.get_logger()


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Umbral de similitud para detectar duplicados (0.0 - 1.0)
SIMILARITY_THRESHOLD = 0.85

# Umbral mínimo para Discovery (subido de 0.22 para reducir ruido)
DISCOVERY_THRESHOLD = 0.35


# =============================================================================
# NORMALIZACIÓN DE TEXTO
# =============================================================================

def normalize_code(codigo: str) -> str:
    """
    Normaliza un código para comparación.
    
    Transformaciones:
    - Minúsculas
    - Eliminar acentos/tildes
    - Reemplazar guiones y underscores por espacios
    - Colapsar espacios múltiples
    - Strip whitespace
    
    Args:
        codigo: Código original
        
    Returns:
        Código normalizado para comparación
        
    Example:
        >>> normalize_code("Organización_Social")
        'organizacion social'
    """
    if not codigo:
        return ""
    
    # Minúsculas
    text = codigo.lower()
    
    # Eliminar acentos (ñ se preserva como n)
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    
    # Reemplazar guiones y underscores por espacios
    text = re.sub(r'[-_]', ' ', text)
    
    # Colapsar espacios múltiples
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calcula similitud entre dos textos.
    
    Usa rapidfuzz si está disponible, sino difflib.
    
    Args:
        text1: Primer texto
        text2: Segundo texto
        
    Returns:
        Similitud entre 0.0 y 1.0
    """
    if not text1 or not text2:
        return 0.0
    
    # Normalizar antes de comparar
    norm1 = normalize_code(text1)
    norm2 = normalize_code(text2)
    
    if RAPIDFUZZ_AVAILABLE:
        # rapidfuzz devuelve 0-100, convertir a 0-1
        return fuzz.ratio(norm1, norm2) / 100.0
    else:
        # difflib devuelve 0-1 directamente
        return SequenceMatcher(None, norm1, norm2).ratio()


def find_similar_codes(
    codigo: str,
    existing_codes: List[str],
    threshold: float = SIMILARITY_THRESHOLD,
    limit: int = 5,
) -> List[Tuple[str, float]]:
    """
    Encuentra códigos similares al propuesto.
    
    Args:
        codigo: Código nuevo propuesto
        existing_codes: Lista de códigos existentes
        threshold: Umbral mínimo de similitud (default 0.85)
        limit: Máximo de resultados
        
    Returns:
        Lista de tuplas (codigo_existente, similitud) ordenadas por similitud desc
        
    Example:
        >>> find_similar_codes('organizacion', ['organización', 'territorio'])
        [('organización', 0.92)]
    """
    if not codigo or not existing_codes:
        return []
    
    norm_codigo = normalize_code(codigo)
    results = []
    
    if RAPIDFUZZ_AVAILABLE:
        # Usar rapidfuzz.process para búsqueda eficiente
        # Normalizar todos los códigos existentes para comparación
        normalized_existing = {normalize_code(c): c for c in existing_codes}
        
        matches = fuzz_process.extract(
            norm_codigo,
            list(normalized_existing.keys()),
            limit=limit,
            score_cutoff=threshold * 100,  # rapidfuzz usa 0-100
        )
        
        results = [
            (normalized_existing[match[0]], match[1] / 100.0)
            for match in matches
            if match[0] != norm_codigo  # Excluir coincidencia exacta consigo mismo
        ]
    else:
        # Fallback con difflib
        for existing in existing_codes:
            similarity = calculate_similarity(codigo, existing)
            if similarity >= threshold and normalize_code(existing) != norm_codigo:
                results.append((existing, similarity))
        
        results.sort(key=lambda x: x[1], reverse=True)
        results = results[:limit]
    
    return results


def suggest_code_merge(
    new_codes: List[Dict[str, Any]],
    existing_codes: List[str],
    threshold: float = SIMILARITY_THRESHOLD,
    deduplicate_batch: bool = True,
) -> List[Dict[str, Any]]:
    """
    Procesa códigos nuevos y marca los que tienen similares existentes.
    
    INCLUYE deduplicación intra-batch para evitar "Batch Blindness".
    
    Para cada código nuevo, busca similares en:
    1. existing_codes (de la BD)
    2. Otros códigos en el mismo batch (si deduplicate_batch=True)
    
    Args:
        new_codes: Lista de códigos candidatos (dicts con 'codigo')
        existing_codes: Lista de nombres de códigos existentes
        threshold: Umbral de similitud
        deduplicate_batch: Si True, elimina duplicados dentro del batch
        
    Returns:
        Lista de códigos con campo 'similar_existing' añadido si hay duplicados
        Si deduplicate_batch=True, los duplicados intra-batch se fusionan
        
    Example:
        >>> codes = [{'codigo': 'organizacion', 'cita': 'A'},
        ...          {'codigo': 'organizacion', 'cita': 'B'}]  # Duplicado!
        >>> existing = ['territorio']
        >>> result = suggest_code_merge(codes, existing, deduplicate_batch=True)
        >>> len(result)  # Solo 1, con evidencias combinadas
        1
    """
    if not new_codes:
        return new_codes
    
    # =========================================================================
    # PASO 1: Deduplicación Intra-Batch (Evitar Batch Blindness)
    # =========================================================================
    
    if deduplicate_batch:
        from collections import defaultdict
        
        # Agrupar por código normalizado
        batch_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        for code_dict in new_codes:
            codigo = code_dict.get('codigo', '')
            if not codigo:
                continue
            
            # Normalizar para agrupar variantes idénticas
            norm_key = normalize_code(codigo)
            batch_groups[norm_key].append(code_dict)
        
        # Detectar duplicados intra-batch
        deduplicated = []
        batch_duplicates_found = 0
        
        for norm_key, group in batch_groups.items():
            if len(group) == 1:
                # Código único en el batch
                deduplicated.append(group[0])
            else:
                # ¡DUPLICADOS INTRA-BATCH DETECTADOS!
                batch_duplicates_found += len(group) - 1
                
                # Tomar el primero como base
                merged = dict(group[0])
                
                # Combinar citas de todos los duplicados
                all_citas = []
                all_fragmentos = set()
                all_archivos = set()
                max_score = 0.0
                
                for item in group:
                    if item.get('cita'):
                        all_citas.append(item['cita'])
                    if item.get('fragmento_id'):
                        all_fragmentos.add(item['fragmento_id'])
                    if item.get('archivo'):
                        all_archivos.add(item['archivo'])
                    if item.get('score_confianza'):
                        max_score = max(max_score, item.get('score_confianza', 0))
                
                # Fusionar información
                if len(all_citas) > 1:
                    merged['cita'] = " | ".join(all_citas[:3])  # Max 3 citas
                    if len(all_citas) > 3:
                        merged['cita'] += f" (+{len(all_citas)-3} más)"
                
                if max_score > 0:
                    merged['score_confianza'] = max_score
                
                # Marcar como fusionado
                merged['_batch_merged'] = True
                merged['_batch_count'] = len(group)
                
                # Nota en memo
                existing_memo = merged.get('memo') or ''
                merge_note = f"[BATCH-MERGE] {len(group)} entradas idénticas fusionadas"
                merged['memo'] = f"{merge_note} {existing_memo}".strip()
                
                _logger.info(
                    "code_normalization.batch_duplicates_merged",
                    codigo=merged.get('codigo'),
                    count=len(group),
                    sources=[c.get('archivo') for c in group],
                )
                
                deduplicated.append(merged)
        
        if batch_duplicates_found > 0:
            _logger.warning(
                "code_normalization.batch_blindness_prevented",
                duplicates_found=batch_duplicates_found,
                unique_codes=len(deduplicated),
                original_count=len(new_codes),
            )
        
        # Usar lista deduplicada
        new_codes = deduplicated
    
    # =========================================================================
    # PASO 2: Comparar contra códigos existentes en BD
    # =========================================================================
    
    if not existing_codes:
        return new_codes
    
    result = []
    for code_dict in new_codes:
        codigo = code_dict.get('codigo', '')
        if not codigo:
            result.append(code_dict)
            continue
        
        similar = find_similar_codes(codigo, existing_codes, threshold)
        
        if similar:
            # Clonar dict y agregar info de similares
            updated = dict(code_dict)
            updated['similar_existing'] = similar
            updated['has_similar'] = True
            
            # Agregar nota al memo
            best_match = similar[0]
            similarity_note = f"[SIMILAR] '{best_match[0]}' ({best_match[1]:.0%})"
            existing_memo = updated.get('memo') or ''
            updated['memo'] = f"{similarity_note} {existing_memo}".strip()
            
            _logger.info(
                "code_normalization.similar_found",
                new_code=codigo,
                similar_to=best_match[0],
                similarity=best_match[1],
            )
            
            result.append(updated)
        else:
            result.append(code_dict)
    
    return result



def get_existing_codes_for_project(pg_conn, project_id: str) -> List[str]:
    """
    Obtiene lista de códigos únicos existentes en un proyecto.
    
    Consulta tanto códigos validados como candidatos pendientes.
    
    Args:
        pg_conn: Conexión PostgreSQL
        project_id: ID del proyecto
        
    Returns:
        Lista de nombres de códigos únicos
    """
    sql = """
    SELECT DISTINCT codigo FROM (
        -- Códigos validados (definitivos)
        SELECT codigo FROM analisis_codigos_abiertos WHERE project_id = %s
        UNION
        -- Códigos candidatos pendientes/validados
        SELECT codigo FROM codigos_candidatos 
        WHERE project_id = %s AND estado IN ('pendiente', 'validado')
    ) AS all_codes
    """
    
    try:
        with pg_conn.cursor() as cur:
            cur.execute(sql, (project_id, project_id))
            rows = cur.fetchall()
        return [row[0] for row in rows if row[0]]
    except Exception as e:
        _logger.warning("code_normalization.get_existing_failed", error=str(e))
        return []
